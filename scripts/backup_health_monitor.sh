#!/bin/bash

# Backup Server Health Check and Monitoring Script
# Monitors the backup server health and handles failover scenarios

set -e

# Configuration
HEALTH_LOG="/var/log/hokm-game/health.log"
ALERT_LOG="/var/log/hokm-game/alerts.log"
PRIMARY_URL="https://primary.yourdomain.com/health"
BACKUP_URL="http://localhost:8765/health"
SERVICE_NAME="hokm-game-backup"
MAX_FAILURES=3
FAILURE_COUNT_FILE="/tmp/backup_health_failures"

# Email/webhook settings (configure as needed)
ALERT_EMAIL="admin@yourdomain.com"
SLACK_WEBHOOK=""  # Add your Slack webhook URL if using

# Create log directories
mkdir -p "$(dirname "$HEALTH_LOG")"
mkdir -p "$(dirname "$ALERT_LOG")"

# Function to log with timestamp
log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S'): $1" | tee -a "$HEALTH_LOG"
}

# Function to send alerts
send_alert() {
    local severity="$1"
    local message="$2"
    
    log "[$severity] $message"
    echo "$(date '+%Y-%m-%d %H:%M:%S'): [$severity] $message" >> "$ALERT_LOG"
    
    # Send email alert if configured
    if [ -n "$ALERT_EMAIL" ] && command -v mail >/dev/null 2>&1; then
        echo "$message" | mail -s "Hokm Game Backup Server Alert - $severity" "$ALERT_EMAIL" 2>/dev/null || true
    fi
    
    # Send Slack alert if configured
    if [ -n "$SLACK_WEBHOOK" ] && command -v curl >/dev/null 2>&1; then
        curl -X POST -H 'Content-type: application/json' \
            --data "{\"text\":\"🚨 Hokm Game Backup Server Alert [$severity]: $message\"}" \
            "$SLACK_WEBHOOK" 2>/dev/null || true
    fi
}

# Function to get failure count
get_failure_count() {
    if [ -f "$FAILURE_COUNT_FILE" ]; then
        cat "$FAILURE_COUNT_FILE"
    else
        echo "0"
    fi
}

# Function to set failure count
set_failure_count() {
    echo "$1" > "$FAILURE_COUNT_FILE"
}

# Function to reset failure count
reset_failure_count() {
    rm -f "$FAILURE_COUNT_FILE"
}

# Function to check service status
check_service_status() {
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        return 0
    else
        return 1
    fi
}

# Function to restart service
restart_service() {
    log "Attempting to restart $SERVICE_NAME..."
    
    if systemctl restart "$SERVICE_NAME"; then
        log "Service restart initiated successfully"
        sleep 10  # Wait for service to start
        
        if check_service_status; then
            log "Service is now running"
            return 0
        else
            log "Service failed to start after restart"
            return 1
        fi
    else
        log "Failed to restart service"
        return 1
    fi
}

# Function to check backup server health
check_backup_health() {
    if curl -f -s -m 10 "$BACKUP_URL" > /dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

# Function to check primary server health
check_primary_health() {
    if curl -f -s -m 10 "$PRIMARY_URL" > /dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

# Function to check system resources
check_system_resources() {
    local issues=""
    
    # Check disk space
    local disk_usage=$(df /opt/hokm-game | tail -1 | awk '{print $5}' | sed 's/%//')
    if [ "$disk_usage" -gt 90 ]; then
        issues="$issues Disk usage critical: ${disk_usage}%."
    elif [ "$disk_usage" -gt 80 ]; then
        log "WARNING: High disk usage: ${disk_usage}%"
    fi
    
    # Check memory usage
    local mem_usage=$(free | grep Mem | awk '{printf "%.0f", $3/$2 * 100.0}')
    if [ "$mem_usage" -gt 90 ]; then
        issues="$issues Memory usage critical: ${mem_usage}%."
    elif [ "$mem_usage" -gt 80 ]; then
        log "WARNING: High memory usage: ${mem_usage}%"
    fi
    
    # Check load average
    local load_avg=$(uptime | awk -F'load average:' '{print $2}' | awk '{print $1}' | sed 's/,//')
    local cpu_cores=$(nproc)
    local load_threshold=$(echo "$cpu_cores * 2" | bc)
    
    if (( $(echo "$load_avg > $load_threshold" | bc -l) )); then
        issues="$issues High load average: $load_avg (cores: $cpu_cores)."
    fi
    
    if [ -n "$issues" ]; then
        send_alert "WARNING" "System resource issues detected:$issues"
        return 1
    fi
    
    return 0
}

# Function to check database connectivity
check_database() {
    local db_host="${DB_HOST:-localhost}"
    local db_port="${DB_PORT:-5432}"
    local db_name="${DB_NAME:-hokm_game}"
    local db_user="${DB_USER:-hokm_user}"
    
    if command -v pg_isready >/dev/null 2>&1; then
        if pg_isready -h "$db_host" -p "$db_port" -d "$db_name" -U "$db_user" >/dev/null 2>&1; then
            log "Database connectivity: OK"
            return 0
        else
            log "WARNING: Database connectivity failed"
            return 1
        fi
    else
        log "INFO: pg_isready not available, skipping database check"
        return 0
    fi
}

# Function to check Redis connectivity
check_redis() {
    local redis_host="${REDIS_HOST:-localhost}"
    local redis_port="${REDIS_PORT:-6379}"
    
    if command -v redis-cli >/dev/null 2>&1; then
        if redis-cli -h "$redis_host" -p "$redis_port" ping >/dev/null 2>&1; then
            log "Redis connectivity: OK"
            return 0
        else
            log "WARNING: Redis connectivity failed"
            return 1
        fi
    else
        log "INFO: redis-cli not available, skipping Redis check"
        return 0
    fi
}

# Main health check logic
main() {
    log "Starting health check..."
    
    local failure_count=$(get_failure_count)
    local health_ok=true
    
    # Check if service is running
    if ! check_service_status; then
        log "ERROR: Service $SERVICE_NAME is not running"
        health_ok=false
        
        # Try to start the service
        if restart_service; then
            log "Service restarted successfully"
            reset_failure_count
            health_ok=true
        else
            send_alert "CRITICAL" "Failed to restart backup server service"
        fi
    fi
    
    # Check backup server health endpoint
    if ! check_backup_health; then
        log "ERROR: Backup server health check failed"
        health_ok=false
        
        # If service is running but health check fails, try restart
        if check_service_status; then
            log "Service is running but health check failed, attempting restart..."
            if restart_service; then
                log "Service restarted due to failed health check"
                # Wait and check again
                sleep 5
                if check_backup_health; then
                    log "Health check now passing after restart"
                    reset_failure_count
                    health_ok=true
                else
                    log "Health check still failing after restart"
                fi
            fi
        fi
    fi
    
    # Update failure count
    if [ "$health_ok" = false ]; then
        failure_count=$((failure_count + 1))
        set_failure_count "$failure_count"
        
        if [ "$failure_count" -ge "$MAX_FAILURES" ]; then
            send_alert "CRITICAL" "Backup server has failed $failure_count consecutive health checks. Manual intervention required."
        else
            send_alert "WARNING" "Backup server health check failed ($failure_count/$MAX_FAILURES)"
        fi
    else
        # Health check passed
        if [ "$failure_count" -gt 0 ]; then
            log "Health check recovered after $failure_count failures"
            send_alert "INFO" "Backup server health check recovered"
        fi
        reset_failure_count
        log "Health check: PASSED"
    fi
    
    # Check primary server connectivity
    if check_primary_health; then
        log "Primary server connectivity: OK"
    else
        log "WARNING: Cannot reach primary server"
        send_alert "WARNING" "Primary server is not reachable from backup server"
    fi
    
    # Check system resources
    check_system_resources
    
    # Check database and Redis connectivity
    check_database
    check_redis
    
    # Log current status
    local service_status=$(systemctl is-active "$SERVICE_NAME" 2>/dev/null || echo "inactive")
    local uptime=$(systemctl show "$SERVICE_NAME" --property=ActiveEnterTimestamp --value 2>/dev/null || echo "unknown")
    
    log "Service status: $service_status"
    log "Service uptime: $uptime"
    log "Health check completed"
}

# Handle script arguments
case "${1:-check}" in
    "check")
        main
        ;;
    "status")
        echo "Service Status: $(systemctl is-active "$SERVICE_NAME" 2>/dev/null || echo "inactive")"
        echo "Failure Count: $(get_failure_count)"
        echo "Last Health Check: $(tail -1 "$HEALTH_LOG" 2>/dev/null || echo "No logs found")"
        ;;
    "reset")
        reset_failure_count
        echo "Failure count reset"
        ;;
    "test-alert")
        send_alert "INFO" "Test alert from backup server health check script"
        echo "Test alert sent"
        ;;
    *)
        echo "Usage: $0 {check|status|reset|test-alert}"
        echo "  check       - Run health check (default)"
        echo "  status      - Show current status"
        echo "  reset       - Reset failure count"
        echo "  test-alert  - Send test alert"
        exit 1
        ;;
esac
