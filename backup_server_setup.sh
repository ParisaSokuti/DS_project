#!/bin/bash

# Backup Server Setup Script
# This script sets up a complete backup server deployment for the Hokm game

set -e  # Exit on any error

# Configuration
BACKUP_SERVER_USER="gameserver"
BACKUP_SERVER_HOST="backup.yourdomain.com"  # Replace with actual backup server IP/hostname
PRIMARY_SERVER_USER="gameserver"
PRIMARY_SERVER_HOST="primary.yourdomain.com"  # Replace with actual primary server IP/hostname
DEPLOY_DIR="/opt/hokm-game"
REPO_URL="https://github.com/ParisaSokuti/DS_project.git"
BRANCH="load-balancer"

echo "🚀 Starting Backup Server Setup for Hokm Game"
echo "=============================================="

# Function to run commands on backup server
run_remote() {
    ssh ${BACKUP_SERVER_USER}@${BACKUP_SERVER_HOST} "$1"
}

# Function to copy files to backup server
copy_to_backup() {
    scp -r "$1" ${BACKUP_SERVER_USER}@${BACKUP_SERVER_HOST}:"$2"
}

echo "📋 Step 1: Installing system dependencies on backup server..."

# Install system dependencies
run_remote "sudo apt-get update && sudo apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    git \
    docker.io \
    docker-compose \
    nginx \
    postgresql-client \
    redis-tools \
    rsync \
    cron \
    supervisor \
    htop \
    curl \
    wget \
    unzip"

echo "✅ System dependencies installed"

echo "📋 Step 2: Setting up deployment directory..."

# Create deployment directory
run_remote "sudo mkdir -p ${DEPLOY_DIR}"
run_remote "sudo chown ${BACKUP_SERVER_USER}:${BACKUP_SERVER_USER} ${DEPLOY_DIR}"

echo "✅ Deployment directory created"

echo "📋 Step 3: Cloning repository..."

# Clone the repository
run_remote "cd ${DEPLOY_DIR} && git clone -b ${BRANCH} ${REPO_URL} ."

echo "✅ Repository cloned"

echo "📋 Step 4: Setting up Python environment..."

# Set up Python virtual environment
run_remote "cd ${DEPLOY_DIR} && python3 -m venv venv"
run_remote "cd ${DEPLOY_DIR} && source venv/bin/activate && pip install --upgrade pip"

# Install Python dependencies
run_remote "cd ${DEPLOY_DIR} && source venv/bin/activate && pip install -r requirements.txt"
run_remote "cd ${DEPLOY_DIR} && source venv/bin/activate && pip install -r requirements-postgresql.txt"

echo "✅ Python environment and dependencies installed"

echo "📋 Step 5: Setting up configuration sync..."

# Create sync script
cat > backup_sync_script.sh << 'EOF'
#!/bin/bash

# Backup Server Sync Script
# Syncs code and configuration from primary server

set -e

DEPLOY_DIR="/opt/hokm-game"
PRIMARY_SERVER="gameserver@primary.yourdomain.com"  # Replace with actual primary
BACKUP_LOG="/var/log/backup-sync.log"

echo "$(date): Starting backup sync..." >> $BACKUP_LOG

# Function to log with timestamp
log() {
    echo "$(date): $1" >> $BACKUP_LOG
    echo "$1"
}

# Sync code from Git repository
log "Pulling latest code from Git..."
cd $DEPLOY_DIR
git fetch origin
git reset --hard origin/load-balancer
git clean -fd

# Install/update dependencies if requirements changed
if git diff-tree --name-only HEAD@{1} HEAD | grep -E "requirements.*\.txt$"; then
    log "Requirements files changed, updating dependencies..."
    source venv/bin/activate
    pip install -r requirements.txt
    pip install -r requirements-postgresql.txt
fi

# Sync configuration files from primary server
log "Syncing configuration files from primary server..."
rsync -avz --delete \
    $PRIMARY_SERVER:$DEPLOY_DIR/postgresql_replication/ \
    $DEPLOY_DIR/postgresql_replication/ || log "Warning: Could not sync postgresql_replication"

rsync -avz \
    $PRIMARY_SERVER:$DEPLOY_DIR/.env \
    $DEPLOY_DIR/.env 2>/dev/null || log "Warning: Could not sync .env file"

# Sync SSL certificates if they exist
rsync -avz \
    $PRIMARY_SERVER:/etc/ssl/certs/hokm-game/ \
    /etc/ssl/certs/hokm-game/ 2>/dev/null || log "Info: No SSL certificates to sync"

# Restart services if needed
log "Checking if services need restart..."
if systemctl is-active --quiet hokm-game-server; then
    log "Restarting game server..."
    sudo systemctl restart hokm-game-server
fi

if systemctl is-active --quiet nginx; then
    log "Reloading nginx configuration..."
    sudo nginx -t && sudo systemctl reload nginx
fi

log "Backup sync completed successfully"
EOF

# Copy sync script to backup server
copy_to_backup "backup_sync_script.sh" "/tmp/"
run_remote "sudo mv /tmp/backup_sync_script.sh /usr/local/bin/"
run_remote "sudo chmod +x /usr/local/bin/backup_sync_script.sh"

echo "✅ Sync script installed"

echo "📋 Step 6: Setting up environment variables..."

# Create environment file template for backup server
cat > backup.env << 'EOF'
# Backup Server Environment Configuration
NODE_ENV=production
DEBUG=false

# Server Configuration
SERVER_HOST=0.0.0.0
SERVER_PORT=8765
BACKUP_SERVER=true

# Database Configuration (Point to primary or backup DB)
DB_HOST=backup-postgres.yourdomain.com  # Replace with actual backup DB host
DB_PORT=5432
DB_NAME=hokm_game
DB_USER=hokm_user
DB_PASSWORD=your_secure_db_password  # Use same as primary
DB_SSL=true

# Redis Configuration (Point to backup Redis or Redis Sentinel)
REDIS_HOST=backup-redis.yourdomain.com  # Replace with actual backup Redis host
REDIS_PORT=6379
REDIS_PASSWORD=redis_game_password123  # Use same as primary
REDIS_DB=0

# Redis Sentinel Configuration (if using Redis HA)
REDIS_SENTINEL_SERVICE=hokm-master
REDIS_SENTINEL_HOSTS=sentinel1:26379,sentinel2:26379,sentinel3:26379

# JWT and Security
JWT_SECRET=your_jwt_secret_key_here  # Use same as primary
SESSION_SECRET=your_session_secret_here  # Use same as primary
BCRYPT_ROUNDS=12

# Logging
LOG_LEVEL=info
LOG_FILE=/var/log/hokm-game/backup-server.log

# Health Check
HEALTH_CHECK_INTERVAL=30000
HEALTH_CHECK_TIMEOUT=5000

# Backup Server Specific
PRIMARY_SERVER_URL=https://primary.yourdomain.com
SYNC_INTERVAL=300  # 5 minutes
FAILOVER_MODE=false
EOF

# Copy environment file to backup server
copy_to_backup "backup.env" "${DEPLOY_DIR}/.env"

echo "✅ Environment configuration created"

echo "📋 Step 7: Setting up systemd service..."

# Create systemd service file for backup server
cat > hokm-game-backup.service << 'EOF'
[Unit]
Description=Hokm Game Backup Server
After=network.target postgresql.service redis.service
Wants=postgresql.service redis.service

[Service]
Type=simple
User=gameserver
Group=gameserver
WorkingDirectory=/opt/hokm-game
Environment=PATH=/opt/hokm-game/venv/bin
ExecStart=/opt/hokm-game/venv/bin/python backend/server.py
ExecReload=/bin/kill -HUP $MAINPID
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=hokm-game-backup

# Security settings
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/hokm-game /var/log/hokm-game

[Install]
WantedBy=multi-user.target
EOF

# Copy and enable systemd service
copy_to_backup "hokm-game-backup.service" "/tmp/"
run_remote "sudo mv /tmp/hokm-game-backup.service /etc/systemd/system/"
run_remote "sudo systemctl daemon-reload"
run_remote "sudo systemctl enable hokm-game-backup"

echo "✅ Systemd service configured"

echo "📋 Step 8: Setting up Nginx configuration..."

# Create Nginx configuration for backup server
cat > backup-nginx.conf << 'EOF'
# Nginx configuration for Hokm Game Backup Server

upstream hokm_backup_server {
    server 127.0.0.1:8765;
    keepalive 32;
}

server {
    listen 80;
    listen [::]:80;
    server_name backup.yourdomain.com;  # Replace with actual backup domain

    # Redirect HTTP to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name backup.yourdomain.com;  # Replace with actual backup domain

    # SSL Configuration
    ssl_certificate /etc/ssl/certs/hokm-game/fullchain.pem;
    ssl_certificate_key /etc/ssl/private/hokm-game/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-RSA-AES128-GCM-SHA256:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;

    # Security headers
    add_header X-Frame-Options DENY;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";
    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload";

    # Backup server indicator
    add_header X-Server-Type "backup";

    # WebSocket configuration
    location /ws {
        proxy_pass http://hokm_backup_server;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400;
        proxy_send_timeout 86400;
        proxy_connect_timeout 60s;
    }

    # API endpoints
    location /api {
        proxy_pass http://hokm_backup_server;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    # Health check endpoint
    location /health {
        proxy_pass http://hokm_backup_server;
        access_log off;
    }

    # Static files (if any)
    location /static {
        alias /opt/hokm-game/static;
        expires 1d;
        add_header Cache-Control "public, immutable";
    }

    # Default location
    location / {
        proxy_pass http://hokm_backup_server;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Logging
    access_log /var/log/nginx/hokm-backup-access.log;
    error_log /var/log/nginx/hokm-backup-error.log;
}
EOF

# Copy Nginx configuration
copy_to_backup "backup-nginx.conf" "/tmp/"
run_remote "sudo mv /tmp/backup-nginx.conf /etc/nginx/sites-available/hokm-backup"
run_remote "sudo ln -sf /etc/nginx/sites-available/hokm-backup /etc/nginx/sites-enabled/"
run_remote "sudo nginx -t"

echo "✅ Nginx configuration installed"

echo "📋 Step 9: Setting up cron jobs for automatic sync..."

# Create cron job for regular sync
cat > backup-crontab << 'EOF'
# Hokm Game Backup Server Cron Jobs

# Sync from primary server every 5 minutes
*/5 * * * * /usr/local/bin/backup_sync_script.sh

# Health check every minute
* * * * * curl -f http://localhost:8765/health > /dev/null 2>&1 || systemctl restart hokm-game-backup

# Log rotation daily
0 2 * * * find /var/log/hokm-game -name "*.log" -mtime +7 -delete

# Database backup daily at 3 AM
0 3 * * * pg_dump -h backup-postgres.yourdomain.com -U hokm_user hokm_game | gzip > /opt/hokm-game/backups/db-$(date +\%Y\%m\%d).sql.gz
EOF

# Install cron jobs
copy_to_backup "backup-crontab" "/tmp/"
run_remote "crontab /tmp/backup-crontab"

echo "✅ Cron jobs configured"

echo "📋 Step 10: Setting up log directories..."

# Create log directories
run_remote "sudo mkdir -p /var/log/hokm-game /opt/hokm-game/backups"
run_remote "sudo chown ${BACKUP_SERVER_USER}:${BACKUP_SERVER_USER} /var/log/hokm-game /opt/hokm-game/backups"

echo "✅ Log directories created"

echo "📋 Step 11: Setting up monitoring and health checks..."

# Create health check script
cat > backup_health_check.sh << 'EOF'
#!/bin/bash

# Backup Server Health Check Script

HEALTH_LOG="/var/log/hokm-game/health.log"
PRIMARY_URL="https://primary.yourdomain.com/health"
BACKUP_URL="http://localhost:8765/health"

log() {
    echo "$(date): $1" | tee -a $HEALTH_LOG
}

# Check if backup server is running
if ! curl -f $BACKUP_URL > /dev/null 2>&1; then
    log "ERROR: Backup server health check failed"
    systemctl restart hokm-game-backup
    sleep 10
    
    if ! curl -f $BACKUP_URL > /dev/null 2>&1; then
        log "CRITICAL: Backup server restart failed"
        # Send alert (add your notification method here)
    else
        log "INFO: Backup server restarted successfully"
    fi
else
    log "INFO: Backup server healthy"
fi

# Check connectivity to primary server
if ! curl -f $PRIMARY_URL > /dev/null 2>&1; then
    log "WARNING: Cannot reach primary server"
    # Could trigger failover mode here
else
    log "INFO: Primary server reachable"
fi
EOF

copy_to_backup "backup_health_check.sh" "/tmp/"
run_remote "sudo mv /tmp/backup_health_check.sh /usr/local/bin/"
run_remote "sudo chmod +x /usr/local/bin/backup_health_check.sh"

echo "✅ Health check script installed"

echo "📋 Step 12: Running initial sync..."

# Run initial sync
run_remote "/usr/local/bin/backup_sync_script.sh"

echo "✅ Initial sync completed"

echo "📋 Step 13: Starting services..."

# Start services
run_remote "sudo systemctl start hokm-game-backup"
run_remote "sudo systemctl reload nginx"

echo "✅ Services started"

echo "🎉 Backup Server Setup Complete!"
echo "================================="
echo ""
echo "📋 Summary:"
echo "- Backup server deployed at: ${BACKUP_SERVER_HOST}"
echo "- Code syncs every 5 minutes from primary"
echo "- Health checks run every minute"
echo "- Logs available in: /var/log/hokm-game/"
echo "- Service: hokm-game-backup"
echo ""
echo "🔧 Next Steps:"
echo "1. Update DNS records if needed for failover"
echo "2. Configure SSL certificates"
echo "3. Test failover procedures"
echo "4. Set up monitoring alerts"
echo "5. Update environment variables with actual values"
echo ""
echo "🧪 To test the backup server:"
echo "ssh ${BACKUP_SERVER_USER}@${BACKUP_SERVER_HOST}"
echo "curl http://localhost:8765/health"
echo "systemctl status hokm-game-backup"

# Cleanup local files
rm -f backup_sync_script.sh backup.env hokm-game-backup.service backup-nginx.conf backup-crontab backup_health_check.sh

echo ""
echo "✅ Backup server setup script completed successfully!"
