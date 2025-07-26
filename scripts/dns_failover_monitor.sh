#!/bin/bash

# Manual DNS-based Failover Script
# Alternative to keepalived for environments where virtual IP is not available

set -e

# Configuration
PRIMARY_SERVER="primary.yourdomain.com"       # Primary server hostname/IP
BACKUP_SERVER="backup.yourdomain.com"         # Backup server hostname/IP
GAME_PORT=8765                                # WebSocket port to monitor
CHECK_INTERVAL=30                             # Check interval in seconds
MAX_FAILURES=3                               # Max failures before failover
DNS_UPDATE_SCRIPT="/usr/local/bin/update_dns.sh"  # DNS update script
GAME_SERVICE="hokm-game-backup"               # Service name on backup server

# State files
STATE_DIR="/var/lib/hokm-failover"
FAILURE_COUNT_FILE="$STATE_DIR/failure_count"
CURRENT_MASTER_FILE="$STATE_DIR/current_master"
LOG_FILE="/var/log/hokm-failover.log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Create state directory
mkdir -p "$STATE_DIR"
mkdir -p "$(dirname "$LOG_FILE")"

# Logging function
log() {
    local message="$1"
    echo "$(date '+%Y-%m-%d %H:%M:%S'): $message" | tee -a "$LOG_FILE"
}

# Get failure count
get_failure_count() {
    if [ -f "$FAILURE_COUNT_FILE" ]; then
        cat "$FAILURE_COUNT_FILE"
    else
        echo "0"
    fi
}

# Set failure count
set_failure_count() {
    echo "$1" > "$FAILURE_COUNT_FILE"
}

# Reset failure count
reset_failure_count() {
    rm -f "$FAILURE_COUNT_FILE"
}

# Get current master
get_current_master() {
    if [ -f "$CURRENT_MASTER_FILE" ]; then
        cat "$CURRENT_MASTER_FILE"
    else
        echo "$PRIMARY_SERVER"
    fi
}

# Set current master
set_current_master() {
    echo "$1" > "$CURRENT_MASTER_FILE"
}

# Check if server is healthy
check_server_health() {
    local server="$1"
    local port="$2"
    
    # Check port connectivity
    if ! timeout 10 bash -c "cat < /dev/null > /dev/tcp/$server/$port" 2>/dev/null; then
        return 1
    fi
    
    # Check HTTP health endpoint
    if ! curl -f -s -m 10 "http://$server:$port/health" >/dev/null 2>&1; then
        return 1
    fi
    
    return 0
}

# Send notification
send_notification() {
    local subject="$1"
    local message="$2"
    
    # Email notification
    if command -v mail >/dev/null 2>&1; then
        echo "$message" | mail -s "$subject" admin@yourdomain.com 2>/dev/null || true
    fi
    
    # Slack notification (if webhook configured)
    local slack_webhook="${SLACK_WEBHOOK:-}"
    if [ -n "$slack_webhook" ] && command -v curl >/dev/null 2>&1; then
        curl -X POST -H 'Content-type: application/json' \
            --data "{\"text\":\"🚨 Hokm Game Failover: $subject\\n$message\"}" \
            "$slack_webhook" 2>/dev/null || true
    fi
    
    log "Notification sent: $subject"
}

# Update DNS to point to new server
update_dns() {
    local new_server="$1"
    
    log "Updating DNS to point to: $new_server"
    
    # Call custom DNS update script if it exists
    if [ -x "$DNS_UPDATE_SCRIPT" ]; then
        "$DNS_UPDATE_SCRIPT" "$new_server"
        return $?
    fi
    
    # Example DNS updates for common providers
    # Uncomment and modify based on your DNS provider
    
    # Cloudflare example:
    # curl -X PUT "https://api.cloudflare.com/client/v4/zones/ZONE_ID/dns_records/RECORD_ID" \
    #      -H "Authorization: Bearer YOUR_API_TOKEN" \
    #      -H "Content-Type: application/json" \
    #      --data '{"type":"A","name":"hokm-game","content":"'$new_server'","ttl":300}'
    
    # AWS Route53 example:
    # aws route53 change-resource-record-sets --hosted-zone-id YOUR_ZONE_ID \
    #     --change-batch '{"Changes":[{"Action":"UPSERT","ResourceRecordSet":{"Name":"hokm-game.yourdomain.com","Type":"A","TTL":300,"ResourceRecords":[{"Value":"'$new_server'"}]}}]}'
    
    # For testing, just update /etc/hosts
    sed -i '/hokm-game-server/d' /etc/hosts
    echo "$new_server hokm-game-server" >> /etc/hosts
    
    log "DNS update completed (local hosts file updated)"
    return 0
}

# Start game service on backup server
start_backup_service() {
    log "Starting game service on backup server..."
    
    # SSH to backup server and start service
    if ssh "$BACKUP_SERVER" "systemctl start $GAME_SERVICE"; then
        log "Game service started on backup server"
        return 0
    else
        log "ERROR: Failed to start game service on backup server"
        return 1
    fi
}

# Stop game service on backup server (when primary recovers)
stop_backup_service() {
    log "Stopping game service on backup server..."
    
    # SSH to backup server and stop service
    if ssh "$BACKUP_SERVER" "systemctl stop $GAME_SERVICE"; then
        log "Game service stopped on backup server"
        return 0
    else
        log "WARNING: Failed to stop game service on backup server"
        return 1
    fi
}

# Perform failover to backup server
failover_to_backup() {
    log "=== INITIATING FAILOVER TO BACKUP ==="
    
    # Start service on backup
    if start_backup_service; then
        # Wait for service to be ready
        sleep 10
        
        # Check if backup is healthy
        if check_server_health "$BACKUP_SERVER" "$GAME_PORT"; then
            # Update DNS
            if update_dns "$BACKUP_SERVER"; then
                set_current_master "$BACKUP_SERVER"
                reset_failure_count
                send_notification "Failover Completed" "Game server failed over to backup: $BACKUP_SERVER"
                log "=== FAILOVER COMPLETED SUCCESSFULLY ==="
                return 0
            else
                log "ERROR: DNS update failed during failover"
                return 1
            fi
        else
            log "ERROR: Backup server is not responding after startup"
            return 1
        fi
    else
        log "ERROR: Failed to start backup service"
        return 1
    fi
}

# Perform failback to primary server
failback_to_primary() {
    log "=== INITIATING FAILBACK TO PRIMARY ==="
    
    # Check if primary is really healthy
    if check_server_health "$PRIMARY_SERVER" "$GAME_PORT"; then
        # Update DNS back to primary
        if update_dns "$PRIMARY_SERVER"; then
            set_current_master "$PRIMARY_SERVER"
            reset_failure_count
            
            # Optionally stop backup service to save resources
            # stop_backup_service
            
            send_notification "Failback Completed" "Game server failed back to primary: $PRIMARY_SERVER"
            log "=== FAILBACK COMPLETED SUCCESSFULLY ==="
            return 0
        else
            log "ERROR: DNS update failed during failback"
            return 1
        fi
    else
        log "ERROR: Primary server is not actually healthy for failback"
        return 1
    fi
}

# Main monitoring loop
monitor_servers() {
    log "Starting DNS-based failover monitoring..."
    log "Primary: $PRIMARY_SERVER, Backup: $BACKUP_SERVER"
    log "Check interval: ${CHECK_INTERVAL}s, Max failures: $MAX_FAILURES"
    
    while true; do
        current_master=$(get_current_master)
        failure_count=$(get_failure_count)
        
        log "Checking $current_master (failures: $failure_count/$MAX_FAILURES)"
        
        if check_server_health "$current_master" "$GAME_PORT"; then
            # Server is healthy
            if [ "$failure_count" -gt 0 ]; then
                log "Server recovered after $failure_count failures"
                reset_failure_count
            fi
            
            # If we're on backup and primary is healthy, consider failback
            if [ "$current_master" = "$BACKUP_SERVER" ]; then
                log "Currently on backup, checking if primary has recovered..."
                if check_server_health "$PRIMARY_SERVER" "$GAME_PORT"; then
                    log "Primary server has recovered, initiating failback..."
                    if failback_to_primary; then
                        continue
                    else
                        log "Failback failed, staying on backup"
                    fi
                fi
            fi
            
        else
            # Server is unhealthy
            failure_count=$((failure_count + 1))
            set_failure_count "$failure_count"
            
            log "Health check failed ($failure_count/$MAX_FAILURES)"
            send_notification "Health Check Failed" "Server $current_master failed health check ($failure_count/$MAX_FAILURES)"
            
            # Check if we need to failover
            if [ "$failure_count" -ge "$MAX_FAILURES" ]; then
                if [ "$current_master" = "$PRIMARY_SERVER" ]; then
                    log "Maximum failures reached, initiating failover to backup..."
                    if failover_to_backup; then
                        continue
                    else
                        log "Failover failed, will retry next cycle"
                    fi
                else
                    log "CRITICAL: Backup server is also failing!"
                    send_notification "CRITICAL: Both Servers Down" "Both primary and backup servers are failing health checks!"
                fi
            fi
        fi
        
        sleep "$CHECK_INTERVAL"
    done
}

# Handle script termination
cleanup() {
    log "Failover monitoring stopped"
    exit 0
}

trap cleanup SIGTERM SIGINT

# Command line interface
case "${1:-monitor}" in
    "monitor")
        monitor_servers
        ;;
    "status")
        current_master=$(get_current_master)
        failure_count=$(get_failure_count)
        echo "Current Master: $current_master"
        echo "Failure Count: $failure_count"
        echo "Primary Health: $(check_server_health "$PRIMARY_SERVER" "$GAME_PORT" && echo "OK" || echo "FAILED")"
        echo "Backup Health: $(check_server_health "$BACKUP_SERVER" "$GAME_PORT" && echo "OK" || echo "FAILED")"
        ;;
    "failover")
        if [ "$(get_current_master)" = "$PRIMARY_SERVER" ]; then
            echo "Forcing failover to backup..."
            failover_to_backup
        else
            echo "Already on backup server"
        fi
        ;;
    "failback")
        if [ "$(get_current_master)" = "$BACKUP_SERVER" ]; then
            echo "Forcing failback to primary..."
            failback_to_primary
        else
            echo "Already on primary server"
        fi
        ;;
    "test")
        echo "Testing server connectivity..."
        echo "Primary ($PRIMARY_SERVER): $(check_server_health "$PRIMARY_SERVER" "$GAME_PORT" && echo "OK" || echo "FAILED")"
        echo "Backup ($BACKUP_SERVER): $(check_server_health "$BACKUP_SERVER" "$GAME_PORT" && echo "OK" || echo "FAILED")"
        ;;
    *)
        echo "Usage: $0 {monitor|status|failover|failback|test}"
        echo "  monitor   - Start continuous monitoring (default)"
        echo "  status    - Show current status"
        echo "  failover  - Force failover to backup"
        echo "  failback  - Force failback to primary"
        echo "  test      - Test server connectivity"
        exit 1
        ;;
esac
