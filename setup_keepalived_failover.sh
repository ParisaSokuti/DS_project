#!/bin/bash

# Keepalived Installation and Configuration Script
# Sets up automatic failover with virtual IP management

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PRIMARY_SERVER_IP="192.168.1.26"      # Replace with actual primary server IP
BACKUP_SERVER_IP="192.168.1.27"       # Replace with actual backup server IP
VIRTUAL_IP="192.168.1.25"             # Virtual IP that will float between servers
INTERFACE="eth0"                       # Network interface (adjust as needed)
ROUTER_ID=51                           # VRRP router ID (must be unique in network)
GAME_PORT=8765                         # WebSocket port to monitor
BACKUP_USER="gameserver"               # User to run game server

log() {
    echo -e "${BLUE}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1"
}

success() {
    echo -e "${GREEN}✅ $1${NC}"
}

warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

error() {
    echo -e "${RED}❌ $1${NC}"
}

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    error "This script must be run as root"
    exit 1
fi

log "Starting Keepalived Failover Setup"
echo "===================================="

# Step 1: Install keepalived
log "Installing keepalived..."
if command -v apt-get >/dev/null 2>&1; then
    apt-get update
    apt-get install -y keepalived
elif command -v yum >/dev/null 2>&1; then
    yum install -y keepalived
else
    error "Unsupported package manager. Please install keepalived manually."
    exit 1
fi
success "Keepalived installed"

# Step 2: Create health check script
log "Creating health check script..."
cat > /usr/local/bin/check_game_server.sh << 'EOF'
#!/bin/bash

# Health check script for Hokm game server
# Returns 0 if healthy, 1 if unhealthy

GAME_PORT=8765
MAX_FAILURES=3
FAILURE_FILE="/tmp/game_server_failures"
LOG_FILE="/var/log/keepalived/health_check.log"

# Create log directory
mkdir -p /var/log/keepalived

# Function to log with timestamp
log_health() {
    echo "$(date '+%Y-%m-%d %H:%M:%S'): $1" >> "$LOG_FILE"
}

# Get current failure count
get_failure_count() {
    if [ -f "$FAILURE_FILE" ]; then
        cat "$FAILURE_FILE"
    else
        echo "0"
    fi
}

# Set failure count
set_failure_count() {
    echo "$1" > "$FAILURE_FILE"
}

# Reset failure count
reset_failure_count() {
    rm -f "$FAILURE_FILE"
}

# Check if game server is responding
check_server() {
    # Check if port is listening
    if ! netstat -ln | grep -q ":$GAME_PORT "; then
        log_health "ERROR: Game server port $GAME_PORT not listening"
        return 1
    fi
    
    # Check WebSocket health endpoint
    if ! curl -f -s -m 5 "http://localhost:$GAME_PORT/health" >/dev/null 2>&1; then
        log_health "ERROR: Health endpoint check failed"
        return 1
    fi
    
    log_health "INFO: Health check passed"
    return 0
}

# Main health check logic
if check_server; then
    # Server is healthy
    reset_failure_count
    log_health "SUCCESS: Game server is healthy"
    exit 0
else
    # Server is unhealthy
    failure_count=$(get_failure_count)
    failure_count=$((failure_count + 1))
    set_failure_count "$failure_count"
    
    log_health "FAILURE: Health check failed ($failure_count/$MAX_FAILURES)"
    
    if [ "$failure_count" -ge "$MAX_FAILURES" ]; then
        log_health "CRITICAL: Maximum failures reached, triggering failover"
        exit 1
    else
        log_health "WARNING: Failure $failure_count/$MAX_FAILURES, continuing..."
        exit 0  # Don't trigger failover yet
    fi
fi
EOF

chmod +x /usr/local/bin/check_game_server.sh
success "Health check script created"

# Step 3: Create master startup script
log "Creating master startup script..."
cat > /usr/local/bin/keepalived_master.sh << 'EOF'
#!/bin/bash

# Script executed when this server becomes MASTER

LOG_FILE="/var/log/keepalived/master.log"
GAME_SERVICE="hokm-game-backup"

# Create log directory
mkdir -p /var/log/keepalived

log_master() {
    echo "$(date '+%Y-%m-%d %H:%M:%S'): $1" | tee -a "$LOG_FILE"
}

log_master "=== BECOMING MASTER ==="
log_master "This server is now the PRIMARY (has virtual IP)"

# Ensure game server is running
if systemctl is-active --quiet "$GAME_SERVICE"; then
    log_master "Game server is already running"
else
    log_master "Starting game server..."
    systemctl start "$GAME_SERVICE"
    
    if systemctl is-active --quiet "$GAME_SERVICE"; then
        log_master "Game server started successfully"
    else
        log_master "ERROR: Failed to start game server"
    fi
fi

# Update local DNS/hosts file to point to self
sed -i '/hokm-game-server/d' /etc/hosts
echo "127.0.0.1 hokm-game-server" >> /etc/hosts

# Send notification (if configured)
if command -v mail >/dev/null 2>&1; then
    echo "Server $(hostname) became MASTER at $(date)" | mail -s "Hokm Game Failover: MASTER" admin@yourdomain.com 2>/dev/null || true
fi

log_master "Master transition completed"
EOF

chmod +x /usr/local/bin/keepalived_master.sh
success "Master startup script created"

# Step 4: Create backup startup script
log "Creating backup startup script..."
cat > /usr/local/bin/keepalived_backup.sh << 'EOF'
#!/bin/bash

# Script executed when this server becomes BACKUP

LOG_FILE="/var/log/keepalived/backup.log"
GAME_SERVICE="hokm-game-backup"

# Create log directory
mkdir -p /var/log/keepalived

log_backup() {
    echo "$(date '+%Y-%m-%d %H:%M:%S'): $1" | tee -a "$LOG_FILE"
}

log_backup "=== BECOMING BACKUP ==="
log_backup "This server is now in BACKUP mode"

# Optionally stop game server to save resources (comment out if you want hot standby)
# if systemctl is-active --quiet "$GAME_SERVICE"; then
#     log_backup "Stopping game server (backup mode)"
#     systemctl stop "$GAME_SERVICE"
# fi

# Update local DNS/hosts file to point to primary
sed -i '/hokm-game-server/d' /etc/hosts
echo "VIRTUAL_IP hokm-game-server" >> /etc/hosts  # Will be replaced by actual IP

# Send notification (if configured)
if command -v mail >/dev/null 2>&1; then
    echo "Server $(hostname) became BACKUP at $(date)" | mail -s "Hokm Game Failover: BACKUP" admin@yourdomain.com 2>/dev/null || true
fi

log_backup "Backup transition completed"
EOF

chmod +x /usr/local/bin/keepalived_backup.sh
success "Backup startup script created"

# Step 5: Create fault script
log "Creating fault script..."
cat > /usr/local/bin/keepalived_fault.sh << 'EOF'
#!/bin/bash

# Script executed when keepalived enters FAULT state

LOG_FILE="/var/log/keepalived/fault.log"

# Create log directory
mkdir -p /var/log/keepalived

log_fault() {
    echo "$(date '+%Y-%m-%d %H:%M:%S'): $1" | tee -a "$LOG_FILE"
}

log_fault "=== ENTERING FAULT STATE ==="
log_fault "Keepalived detected a fault condition"

# Send critical alert
if command -v mail >/dev/null 2>&1; then
    echo "CRITICAL: Server $(hostname) entered FAULT state at $(date)" | mail -s "Hokm Game CRITICAL: Keepalived FAULT" admin@yourdomain.com 2>/dev/null || true
fi

log_fault "Fault notification sent"
EOF

chmod +x /usr/local/bin/keepalived_fault.sh
success "Fault script created"

# Step 6: Determine server role and create appropriate configuration
if [ "$(hostname -I | tr -d ' \n')" = "$PRIMARY_SERVER_IP" ]; then
    SERVER_ROLE="MASTER"
    PRIORITY=110
    log "Configuring as PRIMARY server (MASTER)"
else
    SERVER_ROLE="BACKUP"
    PRIORITY=100
    log "Configuring as BACKUP server"
fi

# Step 7: Create keepalived configuration
log "Creating keepalived configuration..."
cat > /etc/keepalived/keepalived.conf << EOF
# Keepalived configuration for Hokm Game Failover
# Generated on $(date)

global_defs {
    router_id $(hostname)
    enable_script_security
    script_user root
}

# Health check script
vrrp_script chk_game_server {
    script "/usr/local/bin/check_game_server.sh"
    interval 10          # Check every 10 seconds
    timeout 5            # Script timeout
    weight -10           # Reduce priority by 10 on failure
    fall 3              # 3 failures to consider down
    rise 2              # 2 successes to consider up
}

# VRRP instance for virtual IP
vrrp_instance VI_1 {
    state $SERVER_ROLE
    interface $INTERFACE
    virtual_router_id $ROUTER_ID
    priority $PRIORITY
    advert_int 1
    
    authentication {
        auth_type PASS
        auth_pass hokm_game_2025
    }
    
    virtual_ipaddress {
        $VIRTUAL_IP
    }
    
    # Track the game server script
    track_script {
        chk_game_server
    }
    
    # Notify scripts
    notify_master "/usr/local/bin/keepalived_master.sh"
    notify_backup "/usr/local/bin/keepalived_backup.sh"
    notify_fault "/usr/local/bin/keepalived_fault.sh"
    
    # Don't preempt unless priority difference is significant
    nopreempt
}
EOF

success "Keepalived configuration created"

# Step 8: Configure log rotation
log "Setting up log rotation..."
cat > /etc/logrotate.d/keepalived-hokm << 'EOF'
/var/log/keepalived/*.log {
    daily
    missingok
    rotate 14
    compress
    delaycompress
    notifempty
    create 644 root root
    postrotate
        systemctl reload keepalived > /dev/null 2>&1 || true
    endscript
}
EOF

success "Log rotation configured"

# Step 9: Enable and start keepalived
log "Enabling and starting keepalived..."
systemctl enable keepalived
systemctl daemon-reload

# Check if keepalived is already running and restart it
if systemctl is-active --quiet keepalived; then
    log "Restarting keepalived to apply new configuration..."
    systemctl restart keepalived
else
    log "Starting keepalived..."
    systemctl start keepalived
fi

# Wait a moment and check status
sleep 3
if systemctl is-active --quiet keepalived; then
    success "Keepalived is running"
else
    error "Keepalived failed to start"
    systemctl status keepalived
    exit 1
fi

# Step 10: Configure firewall (if needed)
log "Configuring firewall..."
if command -v ufw >/dev/null 2>&1; then
    ufw allow in on $INTERFACE to 224.0.0.0/8
    ufw allow in on $INTERFACE proto vrrp
    success "UFW firewall configured"
elif command -v firewall-cmd >/dev/null 2>&1; then
    firewall-cmd --permanent --add-rich-rule="rule protocol value='vrrp' accept"
    firewall-cmd --permanent --add-rich-rule="rule destination address='224.0.0.0/8' accept"
    firewall-cmd --reload
    success "Firewalld configured"
else
    warning "No supported firewall found. You may need to manually configure firewall rules for VRRP."
fi

# Step 11: Final verification
log "Performing final verification..."

# Check virtual IP
sleep 5
if ip addr show | grep -q "$VIRTUAL_IP"; then
    success "Virtual IP $VIRTUAL_IP is active on this server"
    CURRENT_ROLE="MASTER"
else
    log "Virtual IP not active on this server (normal for BACKUP)"
    CURRENT_ROLE="BACKUP"
fi

# Test health check
if /usr/local/bin/check_game_server.sh; then
    success "Health check script is working"
else
    warning "Health check script failed (game server may not be running)"
fi

echo ""
echo -e "${GREEN}🎉 Keepalived Failover Setup Complete!${NC}"
echo "========================================"
echo ""
echo "Configuration Summary:"
echo "- Server Role: $SERVER_ROLE (Priority: $PRIORITY)"
echo "- Current Role: $CURRENT_ROLE"
echo "- Virtual IP: $VIRTUAL_IP"
echo "- Interface: $INTERFACE"
echo "- Health Check: Port $GAME_PORT every 10 seconds"
echo ""
echo "Log Files:"
echo "- Keepalived: /var/log/keepalived/"
echo "- Health Check: /var/log/keepalived/health_check.log"
echo "- Master Events: /var/log/keepalived/master.log"
echo "- Backup Events: /var/log/keepalived/backup.log"
echo ""
echo "Commands:"
echo "- Check status: systemctl status keepalived"
echo "- View logs: journalctl -u keepalived -f"
echo "- Manual failover test: systemctl stop keepalived"
echo ""
echo "⚠️  Next Steps:"
echo "1. Configure the other server with this script"
echo "2. Update client connections to use VIP: $VIRTUAL_IP"
echo "3. Test failover by stopping keepalived on master"
echo "4. Configure email notifications if desired"

exit 0
