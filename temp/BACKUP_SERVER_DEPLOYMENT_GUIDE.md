# Backup Server Deployment Guide

## 🚀 Complete Backup Server Setup for Hokm Game

This guide provides step-by-step instructions for setting up a complete backup server deployment that stays in sync with the primary server.

### 📋 Prerequisites

- Ubuntu 20.04+ or Debian 11+ server for backup deployment
- SSH access to backup server
- Domain name or IP address for backup server
- Same network access as primary server (database, Redis, etc.)
- Git repository access

### 🔧 Quick Setup

1. **Run the automated setup script:**
   ```bash
   chmod +x backup_server_setup.sh
   ./backup_server_setup.sh
   ```

2. **Update configuration with your actual values:**
   ```bash
   # Edit the environment file on backup server
   ssh gameserver@backup.yourdomain.com
   cd /opt/hokm-game
   nano .env
   ```

3. **Test the deployment:**
   ```bash
   chmod +x test_backup_server.sh
   ./test_backup_server.sh
   ```

### 📁 Deployed Components

#### Core Files
- `/opt/hokm-game/` - Main application directory
- `/opt/hokm-game/.env` - Environment configuration
- `/opt/hokm-game/venv/` - Python virtual environment
- `/opt/hokm-game/temp/postgresql_replication/` - HA configuration

#### System Services
- `hokm-game-backup.service` - Main game server service
- `/etc/nginx/sites-available/hokm-backup` - Nginx configuration
- `/usr/local/bin/sync_backup_server.sh` - Sync script
- `/usr/local/bin/backup_health_monitor.sh` - Health monitoring

#### Monitoring & Logs
- `/var/log/hokm-game/` - Application logs
- `/var/log/hokm-game/sync.log` - Sync process logs
- `/var/log/hokm-game/health.log` - Health check logs
- `/opt/hokm-game/backups/` - Database and config backups

### ⚙️ Configuration

#### Environment Variables (backup.env)
Update these key settings in `/opt/hokm-game/.env`:

```bash
# Server Configuration
SERVER_HOST=0.0.0.0
SERVER_PORT=8765
BACKUP_SERVER=true

# Database (point to backup or primary DB)
DB_HOST=backup-postgres.yourdomain.com
DB_PASSWORD=your_secure_db_password

# Redis (point to backup or Redis Sentinel)
REDIS_HOST=backup-redis.yourdomain.com
REDIS_PASSWORD=redis_game_password123

# Security (MUST match primary server)
JWT_SECRET=your_jwt_secret_key_here
SESSION_SECRET=your_session_secret_here

# Primary Server
PRIMARY_SERVER_URL=https://primary.yourdomain.com
```

#### Sync Configuration
The backup server syncs every 5 minutes via cron:
```bash
*/5 * * * * /usr/local/bin/sync_backup_server.sh
```

### 🔄 Synchronization Process

#### What Gets Synced
1. **Code Repository** - Latest commits from `load-balancer` branch
2. **Configuration Files** - PostgreSQL, Redis, Nginx configs
3. **Environment Settings** - Merged with backup-specific overrides
4. **SSL Certificates** - Security certificates from primary
5. **Dependencies** - Python packages when requirements change

#### Sync Script Features
- Automatic Git pull and reset
- Dependency updates when requirements change
- Service restart when needed
- Health verification after changes
- Comprehensive logging

### 🏥 Health Monitoring

#### Automated Checks
- **Every minute**: Service status and health endpoint
- **Every 5 minutes**: Database and Redis connectivity
- **Every 10 minutes**: System resources (disk, memory, load)
- **Daily**: Full system health report

#### Alert Conditions
- Service failures (3 consecutive failures trigger critical alert)
- High resource usage (>90% disk/memory)
- Primary server unreachable
- SSL certificate expiration (7 days warning)

### 🎮 Game Testing

#### Test Game Functionality
```bash
# Test backup server connectivity
curl http://backup.yourdomain.com:8765/health

# Test WebSocket connection
python3 demo_test.py

# Run comprehensive tests
./test_backup_server.sh

# Test game client connection
python3 backend/client.py
```

#### Validate Sync Process
```bash
# Check sync logs
tail -f /var/log/hokm-game/sync.log

# Manual sync test
/usr/local/bin/sync_backup_server.sh

# Check service status
systemctl status hokm-game-backup
```

### 🚨 Failover Procedures

#### Manual Failover
1. **Update DNS** to point to backup server
2. **Enable failover mode** in backup server:
   ```bash
   echo "FAILOVER_MODE=true" >> /opt/hokm-game/.env
   systemctl restart hokm-game-backup
   ```
3. **Verify all services** are responding
4. **Monitor** backup server performance

#### Automatic Failover (Future Enhancement)
- DNS-based failover with health checks
- Load balancer automatic switching
- Database promotion procedures

### 📊 Monitoring & Maintenance

#### Daily Tasks (Automated)
- Sync from primary server (every 5 minutes)
- Health checks and alerts
- Log rotation and cleanup
- Database backups
- System updates (weekly)

#### Manual Maintenance
- Review error logs weekly
- Test failover procedures monthly
- Update SSL certificates as needed
- Monitor resource usage trends

### 🔐 Security Considerations

#### Network Security
- Same firewall rules as primary server
- VPN access for management
- Secure SSH key authentication
- Rate limiting on public endpoints

#### Data Security
- Encrypted database connections
- Secure Redis authentication
- SSL/TLS for all web traffic
- Regular security updates

### 🛠️ Troubleshooting

#### Common Issues

**Service Won't Start**
```bash
# Check service status
systemctl status hokm-game-backup

# Check logs
journalctl -u hokm-game-backup -f

# Verify configuration
cd /opt/hokm-game && source venv/bin/activate && python -c "from backend import server"
```

**Sync Failures**
```bash
# Check sync logs
tail -50 /var/log/hokm-game/sync.log

# Test Git connectivity
cd /opt/hokm-game && git fetch origin

# Test SSH to primary
ssh gameserver@primary.yourdomain.com echo "Connection test"
```

**Health Check Failures**
```bash
# Run manual health check
/usr/local/bin/backup_health_monitor.sh status

# Test endpoints
curl -v http://localhost:8765/health

# Check system resources
df -h && free -h && uptime
```

### 📈 Performance Optimization

#### Resource Allocation
- **RAM**: Minimum 2GB, recommended 4GB+
- **CPU**: 2+ cores for production load
- **Storage**: SSD recommended, 20GB+ free space
- **Network**: Low latency connection to primary

#### Scaling Considerations
- Load balancer integration
- Multiple backup server regions
- Database read replicas
- Redis cluster setup

### 🔄 Update Procedures

#### Code Updates
Automatic via sync script every 5 minutes. Manual override:
```bash
cd /opt/hokm-game
/usr/local/bin/sync_backup_server.sh
```

#### System Updates
```bash
# Automated weekly (Sundays 5 AM)
apt-get update && apt-get upgrade -y

# Manual update
sudo apt-get update && sudo apt-get upgrade
sudo systemctl restart hokm-game-backup
```

#### Configuration Updates
1. Update primary server configuration
2. Wait for automatic sync (5 minutes)
3. Verify changes applied:
   ```bash
   systemctl status hokm-game-backup
   /usr/local/bin/backup_health_monitor.sh check
   ```

### 📞 Support & Contact

#### Log Locations
- Application: `/var/log/hokm-game/backup-server.log`
- Sync Process: `/var/log/hokm-game/sync.log`
- Health Checks: `/var/log/hokm-game/health.log`
- System: `journalctl -u hokm-game-backup`

#### Emergency Procedures
1. Check service status: `systemctl status hokm-game-backup`
2. Review recent logs: `tail -100 /var/log/hokm-game/backup-server.log`
3. Test connectivity: `curl http://localhost:8765/health`
4. Manual restart: `systemctl restart hokm-game-backup`
5. Contact system administrator if issues persist

---

## ✅ Deployment Checklist

- [ ] Backup server provisioned and accessible
- [ ] `backup_server_setup.sh` executed successfully
- [ ] Environment variables updated with actual values
- [ ] SSL certificates installed
- [ ] DNS records configured (if needed)
- [ ] Health monitoring alerts configured
- [ ] Test suite passes (`test_backup_server.sh`)
- [ ] Game client connects successfully
- [ ] Sync process working (check logs)
- [ ] Failover procedures documented and tested

**Backup server deployment is complete and ready for production use! 🎉**
