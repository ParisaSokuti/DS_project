# 🔄 Hokm Game Failover System

## Overview

This document describes the comprehensive failover system implemented for the Hokm game server, providing enterprise-grade high availability through multiple redundancy mechanisms.

## 🏗️ Architecture

The failover system consists of three layers of redundancy:

1. **Virtual IP Failover** (Keepalived + VRRP)
2. **DNS-based Failover** (Alternative for cloud environments)
3. **Application-level Recovery** (Automatic reconnection)

## 📁 Failover Components

### Core Scripts
- `setup_keepalived_failover.sh` - Complete keepalived installation and configuration
- `dns_failover_monitor.sh` - DNS-based failover monitoring system
- `update_dns.sh` - Multi-provider DNS update script
- `test_failover.sh` - Comprehensive failover testing script

### Health Check Scripts
- `/usr/local/bin/check_game_server.sh` - WebSocket port and health endpoint monitoring
- `/usr/local/bin/keepalived_master.sh` - Master state transition handler
- `/usr/local/bin/keepalived_backup.sh` - Backup state transition handler
- `/usr/local/bin/keepalived_fault.sh` - Fault state transition handler

## 🚀 Quick Setup

### 1. Keepalived Setup (Recommended)

```bash
# Run on both primary and backup servers
chmod +x setup_keepalived_failover.sh
sudo ./setup_keepalived_failover.sh

# The script will auto-detect server role and configure appropriately
```

### 2. DNS-based Setup (Alternative)

```bash
# Configure DNS provider credentials
export DNS_PROVIDER="cloudflare"  # or "aws" or "digitalocean"
export CF_API_TOKEN="your_token"  # for Cloudflare
# export AWS_ACCESS_KEY_ID="your_key"  # for AWS
# export DO_API_TOKEN="your_token"     # for DigitalOcean

# Start DNS monitoring
chmod +x dns_failover_monitor.sh
./dns_failover_monitor.sh start
```

## ⚙️ Configuration

### Network Configuration
```
Virtual IP: 192.168.1.25
Primary Server: 192.168.1.26
Backup Server: 192.168.1.27
Game Port: 8765
```

### Keepalived Parameters
- **Priority**: Primary=110, Backup=100
- **Check Interval**: 5 seconds
- **Failure Threshold**: 3 consecutive failures
- **VRRP Authentication**: Enabled with shared password

### Health Check Parameters
- **WebSocket Check**: Connect to port 8765
- **HTTP Health Check**: GET /health endpoint
- **Timeout**: 10 seconds per check
- **Retry Logic**: 3 attempts with exponential backoff

## 🧪 Testing

### Comprehensive Testing
```bash
# Run all tests
chmod +x test_failover.sh
./test_failover.sh

# Run specific test categories
./test_failover.sh connectivity  # Basic connectivity
./test_failover.sh health       # Health endpoints
./test_failover.sh game         # Game connections
./test_failover.sh keepalived   # Service status
./test_failover.sh failover     # Failover simulation
```

### Manual Testing
```bash
# Test basic game functionality
python demo_test.py

# Test fault tolerance
python fault_tolerance_demo_simple.py

# Test specific scenarios
python test_reconnection_fix.py
python test_redis_connection.py
```

## 🔄 Failover Scenarios

### 1. Primary Server Failure
1. **Detection**: Health checks fail (3 consecutive failures)
2. **Action**: Backup server takes virtual IP (VRRP priority)
3. **Recovery**: Clients automatically reconnect to virtual IP
4. **Time**: < 30 seconds total recovery time

### 2. Network Partition
1. **Detection**: VRRP communication loss
2. **Action**: Both servers enter backup state initially
3. **Resolution**: Higher priority server claims virtual IP
4. **Prevention**: VRRP authentication prevents split-brain

### 3. Service-level Failure
1. **Detection**: WebSocket port unreachable but server alive
2. **Action**: Health script marks node as failed
3. **Failover**: Keepalived removes virtual IP from failed node
4. **Recovery**: Service restart triggers automatic recovery

## 📊 Monitoring & Alerting

### Log Files
```
/var/log/keepalived.log         - Keepalived state changes
/var/log/game_health.log        - Health check results
/var/log/dns_failover.log       - DNS failover events
/var/log/syslog                 - System events
```

### Notifications
- **Email**: Automatic alerts on state changes
- **Slack**: Real-time notifications (configure webhook)
- **SMS**: Critical failure alerts (configure provider)

### Metrics Monitoring
```bash
# Check current status
systemctl status keepalived
ip addr show | grep 192.168.1.25  # Check virtual IP
./dns_failover_monitor.sh status  # DNS failover status
```

## 🛠️ Troubleshooting

### Common Issues

#### 1. Virtual IP Not Assigned
```bash
# Check keepalived status
systemctl status keepalived
journalctl -u keepalived -f

# Verify configuration
cat /etc/keepalived/keepalived.conf

# Check network interface
ip addr show
```

#### 2. Health Checks Failing
```bash
# Test health script manually
/usr/local/bin/check_game_server.sh

# Check game server status
netstat -tlpn | grep 8765
curl -f http://localhost:8765/health
```

#### 3. VRRP Communication Issues
```bash
# Check firewall rules
iptables -L | grep 224.0.0.18

# Verify network connectivity
tcpdump -i any vrrp

# Check authentication
grep auth_pass /etc/keepalived/keepalived.conf
```

#### 4. DNS Failover Issues
```bash
# Test DNS updates
./update_dns.sh test
./dns_failover_monitor.sh test

# Verify credentials
env | grep -E "(CF_|AWS_|DO_)"

# Check connectivity
curl -s "https://api.cloudflare.com/client/v4/user/tokens/verify"
```

### Emergency Procedures

#### Manual Failover
```bash
# Stop keepalived on current master
sudo systemctl stop keepalived

# Force backup to become master
sudo systemctl restart keepalived
```

#### DNS Emergency Switch
```bash
# Manually update DNS
./update_dns.sh manual backup_server_ip

# Or update hosts file for testing
echo "192.168.1.27 game.yourdomain.com" >> /etc/hosts
```

#### Service Recovery
```bash
# Restart game server
sudo systemctl restart hokm-game

# Reset Redis connections
redis-cli FLUSHDB

# Clear connection state
./backend/clear_room.py
```

## 🔐 Security Considerations

### Firewall Rules
```bash
# VRRP multicast traffic
iptables -I INPUT -d 224.0.0.18/32 -j ACCEPT
iptables -I OUTPUT -d 224.0.0.18/32 -j ACCEPT

# Game server port
iptables -I INPUT -p tcp --dport 8765 -j ACCEPT

# Health check port
iptables -I INPUT -p tcp --dport 8765 -j ACCEPT
```

### SSH Security
```bash
# Use key-based authentication for server communication
ssh-keygen -t rsa -b 4096
ssh-copy-id backup-server

# Restrict SSH access
# In /etc/ssh/sshd_config:
# PermitRootLogin no
# PasswordAuthentication no
```

### API Security
- Store DNS provider tokens securely
- Use environment variables, not hardcoded values
- Rotate API keys regularly
- Monitor API usage for anomalies

## 📈 Performance Optimization

### Tuning Parameters
```bash
# Keepalived timing
vrrp_instance VI_1 {
    advert_int 1          # Faster detection
    preempt_delay 10      # Prevent flapping
}

# Health check frequency
check_interval=3          # More frequent checks
fail_count=2             # Faster failover trigger
```

### Resource Optimization
- Run health checks on separate thread
- Cache DNS queries to reduce API calls
- Use connection pooling for database connections
- Implement circuit breaker pattern

## 🚀 Deployment Checklist

### Pre-deployment
- [ ] Test all failover scenarios
- [ ] Verify network connectivity between servers
- [ ] Configure firewall rules
- [ ] Set up monitoring and alerting
- [ ] Document runbook procedures

### Deployment
- [ ] Deploy keepalived configuration
- [ ] Start DNS monitoring (if using)
- [ ] Verify virtual IP assignment
- [ ] Test client connections
- [ ] Monitor logs for errors

### Post-deployment
- [ ] Run comprehensive test suite
- [ ] Verify alerting mechanisms
- [ ] Document any issues encountered
- [ ] Schedule regular failover drills
- [ ] Update disaster recovery procedures

## 📚 References

- [Keepalived Documentation](http://keepalived.org/documentation.html)
- [VRRP RFC 5798](https://tools.ietf.org/html/rfc5798)
- [Linux Virtual Server](http://www.linuxvirtualserver.org/)
- [Redis Sentinel](https://redis.io/topics/sentinel)
- [PostgreSQL Streaming Replication](https://www.postgresql.org/docs/current/warm-standby.html)

## 🤝 Support

For issues with the failover system:

1. Check logs: `/var/log/keepalived.log`
2. Run diagnostics: `./test_failover.sh`
3. Review configuration: `/etc/keepalived/keepalived.conf`
4. Test manually: `/usr/local/bin/check_game_server.sh`

---

**Status**: ✅ Ready for Production
**Last Updated**: $(date)
**Version**: 1.0.0
