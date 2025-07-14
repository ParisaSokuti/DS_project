# Lightweight Health Check System

A robust, lightweight health monitoring solution for the Hokm game server that provides automatic failover capabilities with multiple connectivity testing methods.

## Features

- **Multiple Check Methods**: Uses netcat, curl, or telnet for WebSocket port monitoring
- **Configurable Failure Thresholds**: Set custom failure counts before triggering failover
- **Comprehensive Logging**: Detailed audit trail of all health check events
- **Automatic Failover**: Triggers failover procedures when failures exceed threshold
- **Recovery Monitoring**: Automatically detects when primary server recovers
- **Notification Support**: Email and webhook notifications for alerts
- **Systemd Integration**: Can run as a system service for production deployments

## Quick Start

### Basic Usage

```bash
# Run a single health check
./lightweight_health_check.sh check

# Start continuous monitoring (default)
./lightweight_health_check.sh monitor

# Show current status
./lightweight_health_check.sh status

# Test all available check methods
./lightweight_health_check.sh test
```

### Environment Configuration

```bash
# Monitor different server
PRIMARY_SERVER=10.0.0.5 ./lightweight_health_check.sh monitor

# Allow 5 failures before failover
MAX_FAILURES=5 ./lightweight_health_check.sh monitor

# Check every 15 seconds with 5-second timeout
CHECK_INTERVAL=15 TIMEOUT=5 ./lightweight_health_check.sh monitor
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PRIMARY_SERVER` | 192.168.1.26 | Primary server IP address |
| `WEBSOCKET_PORT` | 8765 | WebSocket port to monitor |
| `BACKUP_SERVER` | 192.168.1.27 | Backup server IP address |
| `VIRTUAL_IP` | 192.168.1.25 | Virtual IP for failover |
| `MAX_FAILURES` | 3 | Consecutive failures before failover |
| `CHECK_INTERVAL` | 30 | Seconds between health checks |
| `TIMEOUT` | 10 | Timeout for each check attempt |
| `ENABLE_FAILOVER` | true | Enable/disable automatic failover |
| `LOG_FILE` | /var/log/hokm-game/health-check.log | Log file path |
| `FAILOVER_SCRIPT` | ./trigger_failover.sh | Failover script path |
| `ALERT_EMAIL` | "" | Email for notifications |
| `NOTIFICATION_WEBHOOK` | "" | Webhook URL for alerts |

### Configuration File

You can also use the `health-check.conf` file for persistent configuration:

```bash
# Copy and edit configuration
cp health-check.conf.example health-check.conf
# Edit the file with your settings
nano health-check.conf
# Load configuration
source health-check.conf && ./lightweight_health_check.sh monitor
```

## Health Check Methods

The script tries multiple methods in order of preference:

### 1. Netcat (nc) - Preferred
```bash
nc -z 192.168.1.26 8765
```
- Fast and lightweight
- Direct TCP connection test
- Minimal overhead

### 2. Curl - HTTP/WebSocket
```bash
curl -f -s -m 10 http://192.168.1.26:8765/health
```
- Can test HTTP health endpoints
- Fallback to basic TCP connection
- More detailed error information

### 3. Telnet - Legacy Support
```bash
echo '' | telnet 192.168.1.26 8765
```
- Universal availability
- Works on older systems
- Basic connectivity test

## Logging and Auditing

### Log Format
```
[2025-07-14 10:30:15] [INFO] Performing health check on 192.168.1.26:8765
[2025-07-14 10:30:15] [SUCCESS] Health check passed using netcat
[2025-07-14 10:30:45] [ERROR] Health check failed (1/3)
[2025-07-14 10:31:15] [ERROR] Health check failed (2/3)
[2025-07-14 10:31:45] [ERROR] TRIGGERING FAILOVER PROCEDURE
```

### Log Levels
- **INFO**: Normal operations and status updates
- **SUCCESS**: Successful health checks and recoveries
- **WARN**: Failed checks below threshold, warnings
- **ERROR**: Failed checks, failover triggers, critical issues

### Log Management
- Automatic log rotation (configure with logrotate)
- Configurable log levels
- Structured format for analysis
- Separate audit trail for failover events

## Failover Process

### Automatic Failover Trigger
1. **Health Check Failure**: N consecutive failures detected
2. **Alert Notification**: Send critical alert via email/webhook
3. **Failover Execution**: Run configured failover script
4. **State Transition**: Switch to recovery monitoring mode
5. **Confirmation**: Verify failover success

### Failover Actions
1. **Stop Primary**: Attempt to stop keepalived on primary server
2. **Start Backup**: Start/restart keepalived on backup server
3. **Virtual IP**: Wait for virtual IP assignment
4. **DNS Update**: Update DNS records if configured
5. **Verification**: Confirm new setup is operational

### Recovery Process
1. **Continuous Monitoring**: Check primary server recovery
2. **Recovery Detection**: Primary server responds again
3. **Notification**: Send recovery alert
4. **Manual Failback**: Optionally return to primary (manual process)

## Production Deployment

### As Systemd Service

1. **Install Service File**:
```bash
sudo cp hokm-health-check.service /etc/systemd/system/
sudo systemctl daemon-reload
```

2. **Configure Service**:
```bash
# Edit service file for your environment
sudo nano /etc/systemd/system/hokm-health-check.service
```

3. **Enable and Start**:
```bash
sudo systemctl enable hokm-health-check
sudo systemctl start hokm-health-check
```

4. **Monitor Service**:
```bash
sudo systemctl status hokm-health-check
sudo journalctl -u hokm-health-check -f
```

### Directory Structure
```
/opt/hokm-game/
├── lightweight_health_check.sh    # Main health check script
├── health-check.conf              # Configuration file
├── trigger_failover.sh            # Failover script
├── update_dns.sh                  # DNS update script (optional)
└── logs/
    └── health-check.log           # Health check logs
```

### Permissions Setup
```bash
# Create service user
sudo useradd -r -s /bin/false hokm-health

# Set up directories
sudo mkdir -p /opt/hokm-game/logs
sudo chown -R hokm-health:hokm-health /opt/hokm-game

# Make scripts executable
chmod +x /opt/hokm-game/*.sh
```

## Notifications

### Email Alerts
```bash
# Requires mail command (postfix, sendmail, etc.)
ALERT_EMAIL="admin@example.com" ./lightweight_health_check.sh monitor
```

### Webhook Notifications

#### Slack
```bash
NOTIFICATION_WEBHOOK="https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK"
```

#### Discord
```bash
NOTIFICATION_WEBHOOK="https://discord.com/api/webhooks/YOUR/DISCORD/WEBHOOK"
```

#### Microsoft Teams
```bash
NOTIFICATION_WEBHOOK="https://outlook.office.com/webhook/YOUR/TEAMS/WEBHOOK"
```

### Notification Events
- **Health Check Warnings**: Failed checks below threshold
- **Failover Triggered**: Critical failure threshold reached
- **Server Recovery**: Primary server back online
- **Failover Success/Failure**: Failover procedure results

## Testing and Validation

### Run Test Suite
```bash
# Run comprehensive tests
./test_health_check.sh
```

### Manual Testing
```bash
# Test single health check
./lightweight_health_check.sh check

# Test with unreachable server
PRIMARY_SERVER=192.168.1.999 ./lightweight_health_check.sh check

# Test failover trigger
./lightweight_health_check.sh failover

# Monitor for short interval
MAX_FAILURES=2 CHECK_INTERVAL=5 ./lightweight_health_check.sh monitor
```

### Simulate Failures
```bash
# Simulate primary server failure
sudo iptables -A OUTPUT -d 192.168.1.26 -p tcp --dport 8765 -j DROP

# Remove simulation
sudo iptables -D OUTPUT -d 192.168.1.26 -p tcp --dport 8765 -j DROP
```

## Troubleshooting

### Common Issues

#### "No available tools for health check"
**Solution**: Install required tools:
```bash
# Ubuntu/Debian
sudo apt-get install netcat-traditional curl telnet

# CentOS/RHEL
sudo yum install nc curl telnet

# Alpine Linux
sudo apk add netcat-openbsd curl busybox-extras
```

#### "Permission denied" for failover script
**Solution**: Check script permissions:
```bash
chmod +x ./trigger_failover.sh
ls -la ./trigger_failover.sh
```

#### Health checks pass but game is unresponsive
**Solution**: Add application-level health checks:
```bash
# Test actual WebSocket connection
curl -i -N -H "Connection: Upgrade" -H "Upgrade: websocket" \
     -H "Sec-WebSocket-Key: SGVsbG8sIHdvcmxkIQ==" \
     -H "Sec-WebSocket-Version: 13" \
     http://192.168.1.26:8765/
```

#### Failover not triggering
**Solution**: Check configuration:
```bash
# Verify environment variables
./lightweight_health_check.sh status

# Check failover script exists
ls -la ./trigger_failover.sh

# Test failover manually
./lightweight_health_check.sh failover
```

### Debug Mode
```bash
# Enable debug logging
LOG_LEVEL=DEBUG ./lightweight_health_check.sh monitor

# Verbose output
set -x ./lightweight_health_check.sh check
```

### Log Analysis
```bash
# Show recent failures
grep "ERROR" /var/log/hokm-game/health-check.log | tail -10

# Count failures by hour
grep "$(date '+%Y-%m-%d %H:')" /var/log/hokm-game/health-check.log | \
  grep "ERROR" | wc -l

# Show failover events
grep "FAILOVER" /var/log/hokm-game/health-check.log
```

## Integration with Existing Systems

### With Keepalived
The health check script works seamlessly with keepalived:
```bash
# In keepalived.conf
vrrp_script chk_game_server {
    script "/opt/hokm-game/lightweight_health_check.sh check"
    interval 30
    timeout 10
    fall 3
    rise 2
}
```

### With Load Balancers
Use as backend health check:
```bash
# HAProxy backend check
backend game_servers
    option httpchk GET /health
    server primary 192.168.1.26:8765 check
    server backup 192.168.1.27:8765 check backup
```

### With Monitoring Systems
Export metrics for monitoring:
```bash
# Prometheus metrics endpoint
echo "health_check_failures $(cat /tmp/health_check_failures 2>/dev/null || echo 0)" > /var/lib/node_exporter/textfile_collector/health_check.prom
```

## Performance Considerations

### Resource Usage
- **CPU**: Minimal (< 1% during checks)
- **Memory**: < 10MB RSS
- **Network**: 1-2 packets per check
- **Disk**: Log files (rotated automatically)

### Scalability
- **Multiple Servers**: Run on each potential failover node
- **Check Frequency**: Balance responsiveness vs. resource usage
- **Timeout Values**: Account for network latency

### Optimization Tips
```bash
# Reduce check interval for faster detection
CHECK_INTERVAL=15

# Increase timeout for slow networks
TIMEOUT=30

# Use local health endpoint for faster checks
curl http://localhost:8765/health
```

## Security Considerations

### SSH Key Management
```bash
# Generate dedicated SSH key for health checks
ssh-keygen -t ed25519 -f ~/.ssh/health_check_key -N ""

# Configure SSH config
cat >> ~/.ssh/config << EOF
Host primary-server
    HostName 192.168.1.26
    User root
    IdentityFile ~/.ssh/health_check_key
    ConnectTimeout 10
    StrictHostKeyChecking no
EOF
```

### Firewall Configuration
```bash
# Allow health check traffic
sudo ufw allow from 192.168.1.27 to 192.168.1.26 port 8765
sudo ufw allow from 192.168.1.26 to 192.168.1.27 port 22
```

### Log Security
```bash
# Secure log directory
chmod 750 /var/log/hokm-game
chown root:adm /var/log/hokm-game

# Configure log rotation
cat > /etc/logrotate.d/hokm-health-check << EOF
/var/log/hokm-game/health-check.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    create 640 root adm
}
EOF
```

## Support and Maintenance

### Regular Maintenance Tasks
1. **Log Rotation**: Ensure logs don't fill disk space
2. **SSH Key Rotation**: Update SSH keys regularly
3. **Test Failover**: Periodic failover testing
4. **Update Thresholds**: Adjust based on performance data

### Monitoring the Monitor
```bash
# Check if health check service is running
systemctl is-active hokm-health-check

# Monitor resource usage
ps aux | grep health_check
```

### Version Updates
```bash
# Backup current configuration
cp health-check.conf health-check.conf.backup

# Update script
git pull origin main

# Restore configuration
cp health-check.conf.backup health-check.conf
```

This lightweight health check system provides enterprise-grade monitoring capabilities while maintaining simplicity and reliability for your Hokm game server infrastructure.
