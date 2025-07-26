#!/bin/bash

# Backup Server Configuration Sync Script
# This script keeps the backup server in perfect sync with the primary

set -e

# Configuration
DEPLOY_DIR="/opt/hokm-game"
PRIMARY_SERVER="gameserver@primary.yourdomain.com"  # Replace with actual primary server
BACKUP_LOG="/var/log/hokm-game/sync.log"
MAX_LOG_SIZE=10485760  # 10MB

# Create log directory if it doesn't exist
mkdir -p "$(dirname "$BACKUP_LOG")"

# Rotate log if it's too large
if [ -f "$BACKUP_LOG" ] && [ $(stat -f%z "$BACKUP_LOG" 2>/dev/null || stat -c%s "$BACKUP_LOG") -gt $MAX_LOG_SIZE ]; then
    mv "$BACKUP_LOG" "${BACKUP_LOG}.old"
fi

# Function to log with timestamp
log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S'): $1" | tee -a "$BACKUP_LOG"
}

# Function to handle errors
handle_error() {
    log "ERROR: $1"
    exit 1
}

log "Starting backup server sync process..."

# Check if we're running as the correct user
if [ "$(whoami)" != "gameserver" ]; then
    handle_error "This script must be run as the gameserver user"
fi

# Change to deployment directory
cd "$DEPLOY_DIR" || handle_error "Could not change to deployment directory: $DEPLOY_DIR"

# Sync code from Git repository
log "Pulling latest code from Git repository..."
git fetch origin || handle_error "Failed to fetch from origin"

# Check if there are new commits
LOCAL_COMMIT=$(git rev-parse HEAD)
REMOTE_COMMIT=$(git rev-parse origin/load-balancer)

if [ "$LOCAL_COMMIT" != "$REMOTE_COMMIT" ]; then
    log "New commits detected. Local: $LOCAL_COMMIT, Remote: $REMOTE_COMMIT"
    
    # Stash any local changes
    git stash push -m "Auto-stash before sync $(date)" || log "Warning: Nothing to stash"
    
    # Reset to remote state
    git reset --hard origin/load-balancer || handle_error "Failed to reset to remote state"
    
    # Clean untracked files
    git clean -fd || log "Warning: Nothing to clean"
    
    log "Code updated successfully"
    CODE_UPDATED=true
else
    log "Code is up to date"
    CODE_UPDATED=false
fi

# Check for requirements changes
REQUIREMENTS_CHANGED=false
if [ "$CODE_UPDATED" = true ]; then
    if git diff-tree --name-only HEAD@{1} HEAD 2>/dev/null | grep -E "requirements.*\.txt$"; then
        REQUIREMENTS_CHANGED=true
        log "Requirements files changed, updating Python dependencies..."
        
        # Activate virtual environment
        source venv/bin/activate || handle_error "Failed to activate virtual environment"
        
        # Update pip
        pip install --upgrade pip || log "Warning: Failed to upgrade pip"
        
        # Install requirements
        pip install -r requirements.txt || handle_error "Failed to install requirements.txt"
        
        if [ -f "requirements-postgresql.txt" ]; then
            pip install -r requirements-postgresql.txt || handle_error "Failed to install requirements-postgresql.txt"
        fi
        
        if [ -f "requirements-auth.txt" ]; then
            pip install -r requirements-auth.txt || log "Warning: Failed to install requirements-auth.txt"
        fi
        
        log "Python dependencies updated successfully"
    fi
fi

# Sync configuration files from primary server
log "Syncing configuration files from primary server..."

# Sync PostgreSQL replication configuration
if rsync -avz --delete --timeout=30 \
    "$PRIMARY_SERVER:$DEPLOY_DIR/postgresql_replication/" \
    "$DEPLOY_DIR/postgresql_replication/" 2>/dev/null; then
    log "PostgreSQL replication configuration synced successfully"
else
    log "Warning: Could not sync postgresql_replication directory"
fi

# Sync environment file (but don't overwrite if backup-specific)
if [ ! -f "$DEPLOY_DIR/.env.backup" ]; then
    if rsync -avz --timeout=30 \
        "$PRIMARY_SERVER:$DEPLOY_DIR/.env" \
        "$DEPLOY_DIR/.env.primary" 2>/dev/null; then
        log "Environment file synced from primary"
        
        # Merge with backup-specific settings
        if [ -f "$DEPLOY_DIR/.env" ]; then
            # Create backup of current env
            cp "$DEPLOY_DIR/.env" "$DEPLOY_DIR/.env.backup.$(date +%Y%m%d_%H%M%S)"
        fi
        
        # Use primary env as base, but preserve backup-specific overrides
        cp "$DEPLOY_DIR/.env.primary" "$DEPLOY_DIR/.env"
        
        # Apply backup server specific settings
        cat >> "$DEPLOY_DIR/.env" << 'EOF'

# Backup Server Specific Overrides
BACKUP_SERVER=true
SERVER_ROLE=backup
EOF
    else
        log "Warning: Could not sync .env file from primary server"
    fi
fi

# Sync SSL certificates if they exist
if rsync -avz --timeout=30 \
    "$PRIMARY_SERVER:/etc/ssl/certs/hokm-game/" \
    "/etc/ssl/certs/hokm-game/" 2>/dev/null; then
    log "SSL certificates synced successfully"
else
    log "Info: No SSL certificates to sync or sync failed"
fi

# Sync Nginx configuration
if rsync -avz --timeout=30 \
    "$PRIMARY_SERVER:/etc/nginx/sites-available/hokm-game" \
    "/etc/nginx/sites-available/hokm-backup-from-primary" 2>/dev/null; then
    log "Nginx configuration synced from primary"
else
    log "Warning: Could not sync Nginx configuration"
fi

# Check if services need restart
RESTART_NEEDED=false

# Check if code or dependencies changed
if [ "$CODE_UPDATED" = true ] || [ "$REQUIREMENTS_CHANGED" = true ]; then
    RESTART_NEEDED=true
fi

# Check if systemd service file changed
if [ -f "/etc/systemd/system/hokm-game-backup.service" ]; then
    if git diff-tree --name-only HEAD@{1} HEAD 2>/dev/null | grep -E ".*\.service$"; then
        log "Service files changed, reloading systemd..."
        sudo systemctl daemon-reload
        RESTART_NEEDED=true
    fi
fi

# Restart services if needed
if [ "$RESTART_NEEDED" = true ]; then
    log "Changes detected, restarting services..."
    
    # Check if service is running before restart
    if systemctl is-active --quiet hokm-game-backup; then
        log "Restarting game server..."
        sudo systemctl restart hokm-game-backup || handle_error "Failed to restart game server"
        
        # Wait for service to start
        sleep 5
        
        # Verify service is running
        if systemctl is-active --quiet hokm-game-backup; then
            log "Game server restarted successfully"
        else
            handle_error "Game server failed to start after restart"
        fi
    else
        log "Game server was not running, starting it..."
        sudo systemctl start hokm-game-backup || handle_error "Failed to start game server"
    fi
else
    log "No restart needed"
fi

# Test Nginx configuration and reload if valid
if sudo nginx -t 2>/dev/null; then
    if systemctl is-active --quiet nginx; then
        log "Reloading Nginx configuration..."
        sudo systemctl reload nginx || log "Warning: Failed to reload Nginx"
    fi
else
    log "Warning: Nginx configuration test failed, not reloading"
fi

# Health check
log "Performing health check..."
sleep 2  # Give services time to fully start

if curl -f -s http://localhost:8765/health > /dev/null 2>&1; then
    log "Health check passed - backup server is responding"
else
    log "Warning: Health check failed - backup server may not be responding"
    
    # Try to restart one more time
    if systemctl is-active --quiet hokm-game-backup; then
        log "Attempting service restart due to failed health check..."
        sudo systemctl restart hokm-game-backup
        sleep 5
        
        if curl -f -s http://localhost:8765/health > /dev/null 2>&1; then
            log "Health check passed after restart"
        else
            log "ERROR: Health check still failing after restart"
        fi
    fi
fi

# Check disk space
DISK_USAGE=$(df "$DEPLOY_DIR" | tail -1 | awk '{print $5}' | sed 's/%//')
if [ "$DISK_USAGE" -gt 85 ]; then
    log "WARNING: Disk usage is ${DISK_USAGE}% - consider cleanup"
fi

# Log current status
log "Sync process completed successfully"
log "Current commit: $(git rev-parse --short HEAD)"
log "Service status: $(systemctl is-active hokm-game-backup 2>/dev/null || echo 'not running')"
log "Disk usage: ${DISK_USAGE}%"

# Clean up old log files
find /var/log/hokm-game -name "*.log.old" -mtime +7 -delete 2>/dev/null || true

log "Backup server sync process finished"
