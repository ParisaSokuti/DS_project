# PostgreSQL High Availability Deployment Guide

This guide provides step-by-step instructions for deploying the PostgreSQL HA cluster for the Hokm gaming platform.

## Prerequisites

### System Requirements

#### Hardware Requirements (Per Node)
- **CPU**: 4+ vCPUs (8+ recommended for production)
- **RAM**: 8GB minimum (16GB+ recommended)
- **Storage**: 100GB+ SSD storage
- **Network**: 1Gbps+ network connectivity

#### Software Requirements
- Docker 20.10+
- Docker Compose 2.0+
- Linux kernel 4.0+ (Ubuntu 20.04+ or CentOS 8+ recommended)
- Sufficient file descriptors (ulimit -n 65536)

### Pre-deployment Checklist
- [ ] Verify Docker and Docker Compose installation
- [ ] Configure firewall rules
- [ ] Set up NTP synchronization
- [ ] Configure DNS resolution
- [ ] Prepare SSL certificates (if using SSL)
- [ ] Set up monitoring infrastructure
- [ ] Configure backup storage (S3 or equivalent)

## Quick Start Deployment

### 1. Clone and Setup

```bash
# Navigate to project directory
cd "/Users/parisasokuti/my git repo/DS_project"

# Create required directories
mkdir -p postgresql-ha/data/{primary,replica1,replica2}
mkdir -p postgresql-ha/backup
mkdir -p postgresql-ha/logs

# Set proper permissions
chmod 700 postgresql-ha/data/*
chmod 755 postgresql-ha/backup
chmod 755 postgresql-ha/logs
```

### 2. Environment Configuration

```bash
# Copy environment template
cp postgresql-ha/.env.example postgresql-ha/.env

# Edit environment variables
vim postgresql-ha/.env
```

#### Environment Variables (.env)
```bash
# PostgreSQL Configuration
POSTGRES_VERSION=15
POSTGRES_PASSWORD=your_secure_primary_password
POSTGRES_REPLICATION_PASSWORD=your_secure_replication_password

# Patroni Configuration
PATRONI_SCOPE=hokm-cluster
PATRONI_NAMESPACE=/db/

# etcd Configuration
ETCD_VERSION=3.5.9
ETCD_CLUSTER_TOKEN=hokm-etcd-cluster

# HAProxy Configuration
HAPROXY_VERSION=2.8
HAPROXY_STATS_PASSWORD=your_stats_password

# PgBouncer Configuration
PGBOUNCER_VERSION=1.20.1
PGBOUNCER_ADMIN_PASSWORD=your_admin_password

# Monitoring Configuration
PROMETHEUS_VERSION=2.45.0
GRAFANA_VERSION=10.0.0
GRAFANA_ADMIN_PASSWORD=your_grafana_password

# Backup Configuration
BACKUP_RETENTION_DAYS=7
S3_BUCKET=your-backup-bucket
AWS_ACCESS_KEY_ID=your_aws_key
AWS_SECRET_ACCESS_KEY=your_aws_secret
```

### 3. Network Configuration

```bash
# Create Docker network
docker network create --driver bridge \
  --subnet=172.20.0.0/16 \
  --ip-range=172.20.240.0/20 \
  postgresql-ha-network
```

### 4. Deploy the Stack

```bash
# Start etcd cluster first
docker-compose -f postgresql-ha/docker-compose.yml up -d etcd1 etcd2 etcd3

# Wait for etcd cluster to be ready
sleep 30

# Start PostgreSQL cluster
docker-compose -f postgresql-ha/docker-compose.yml up -d postgresql-primary postgresql-replica1 postgresql-replica2

# Wait for PostgreSQL cluster to initialize
sleep 60

# Start supporting services
docker-compose -f postgresql-ha/docker-compose.yml up -d haproxy pgbouncer

# Start monitoring stack
docker-compose -f postgresql-ha/docker-compose.yml up -d prometheus grafana alertmanager postgres-exporter-primary postgres-exporter-replica1 postgres-exporter-replica2

# Verify deployment
docker-compose -f postgresql-ha/docker-compose.yml ps
```

### 5. Initial Verification

```bash
# Check cluster status
docker-compose -f postgresql-ha/docker-compose.yml exec postgresql-primary \
  curl -s http://localhost:8008/cluster | jq '.'

# Test database connection
docker-compose -f postgresql-ha/docker-compose.yml exec postgresql-primary \
  psql -U postgres -c "SELECT version();"

# Check replication status
docker-compose -f postgresql-ha/docker-compose.yml exec postgresql-primary \
  psql -U postgres -c "SELECT * FROM pg_stat_replication;"

# Test HAProxy
curl -s http://localhost:8080/stats

# Test monitoring
curl -s http://localhost:9090/api/v1/status/targets
curl -s http://localhost:3000/api/health
```

## Production Deployment

### 1. Infrastructure Preparation

#### DNS Configuration
```bash
# Add DNS entries for your deployment
# postgresql-primary.yourdomain.com -> 10.0.1.10
# postgresql-replica1.yourdomain.com -> 10.0.1.11
# postgresql-replica2.yourdomain.com -> 10.0.1.12
# haproxy.yourdomain.com -> 10.0.1.20
# monitoring.yourdomain.com -> 10.0.1.30
```

#### Firewall Configuration
```bash
# PostgreSQL ports
ufw allow 5432/tcp  # PostgreSQL
ufw allow 6432/tcp  # PgBouncer
ufw allow 8008/tcp  # Patroni REST API
ufw allow 8009/tcp  # Patroni REST API
ufw allow 8010/tcp  # Patroni REST API

# etcd ports
ufw allow 2379/tcp  # etcd client
ufw allow 2380/tcp  # etcd peer

# HAProxy ports
ufw allow 5432/tcp  # PostgreSQL proxy
ufw allow 5433/tcp  # Read replica proxy
ufw allow 8080/tcp  # HAProxy stats

# Monitoring ports
ufw allow 9090/tcp  # Prometheus
ufw allow 3000/tcp  # Grafana
ufw allow 9093/tcp  # AlertManager
ufw allow 9187/tcp  # postgres-exporter
```

### 2. SSL/TLS Configuration

#### Generate SSL Certificates
```bash
# Create CA certificate
openssl genrsa -out ca-key.pem 4096
openssl req -new -x509 -days 3650 -key ca-key.pem -out ca.pem

# Generate server certificates
openssl genrsa -out server-key.pem 4096
openssl req -new -key server-key.pem -out server.csr
openssl x509 -req -days 365 -in server.csr -CA ca.pem -CAkey ca-key.pem -out server.pem

# Generate client certificates
openssl genrsa -out client-key.pem 4096
openssl req -new -key client-key.pem -out client.csr
openssl x509 -req -days 365 -in client.csr -CA ca.pem -CAkey ca-key.pem -out client.pem

# Copy certificates to config directory
mkdir -p postgresql-ha/config/ssl
cp *.pem postgresql-ha/config/ssl/
chmod 600 postgresql-ha/config/ssl/*-key.pem
chmod 644 postgresql-ha/config/ssl/*.pem
```

#### Update PostgreSQL Configuration for SSL
```yaml
# In patroni-primary.yml
postgresql:
  parameters:
    ssl: 'on'
    ssl_cert_file: '/etc/ssl/certs/server.pem'
    ssl_key_file: '/etc/ssl/private/server-key.pem'
    ssl_ca_file: '/etc/ssl/certs/ca.pem'
    ssl_ciphers: 'ECDHE-RSA-AES128-GCM-SHA256:ECDHE-RSA-AES256-GCM-SHA384'
    ssl_prefer_server_ciphers: 'on'
    ssl_min_protocol_version: 'TLSv1.2'
```

### 3. Production Docker Compose Override

Create `docker-compose.prod.yml`:
```yaml
version: '3.8'

services:
  postgresql-primary:
    deploy:
      resources:
        limits:
          memory: 4G
          cpus: '2'
        reservations:
          memory: 2G
          cpus: '1'
    volumes:
      - /data/postgresql/primary:/home/postgres/pgdata
      - /logs/postgresql:/var/log/postgresql
      - ./config/ssl:/etc/ssl/certs:ro
    environment:
      - PATRONI_LOG_LEVEL=INFO
    logging:
      driver: "json-file"
      options:
        max-size: "100m"
        max-file: "5"

  postgresql-replica1:
    deploy:
      resources:
        limits:
          memory: 4G
          cpus: '2'
        reservations:
          memory: 2G
          cpus: '1'
    volumes:
      - /data/postgresql/replica1:/home/postgres/pgdata
      - /logs/postgresql:/var/log/postgresql
      - ./config/ssl:/etc/ssl/certs:ro

  postgresql-replica2:
    deploy:
      resources:
        limits:
          memory: 4G
          cpus: '2'
        reservations:
          memory: 2G
          cpus: '1'
    volumes:
      - /data/postgresql/replica2:/home/postgres/pgdata
      - /logs/postgresql:/var/log/postgresql
      - ./config/ssl:/etc/ssl/certs:ro

  haproxy:
    deploy:
      resources:
        limits:
          memory: 512M
          cpus: '0.5'
    volumes:
      - /logs/haproxy:/var/log/haproxy
    ports:
      - "5432:5432"
      - "5433:5433"
      - "8080:8080"

  prometheus:
    volumes:
      - /data/prometheus:/prometheus
      - /logs/prometheus:/var/log/prometheus
    ports:
      - "9090:9090"

  grafana:
    volumes:
      - /data/grafana:/var/lib/grafana
      - /logs/grafana:/var/log/grafana
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_ADMIN_PASSWORD}
      - GF_SMTP_ENABLED=true
      - GF_SMTP_HOST=smtp.yourdomain.com:587
      - GF_SMTP_USER=alerts@yourdomain.com
      - GF_SMTP_PASSWORD=${SMTP_PASSWORD}
```

### 4. Deploy Production Stack

```bash
# Deploy with production overrides
docker-compose -f postgresql-ha/docker-compose.yml -f postgresql-ha/docker-compose.prod.yml up -d

# Verify deployment
docker-compose -f postgresql-ha/docker-compose.yml -f postgresql-ha/docker-compose.prod.yml ps
```

### 5. Initial Database Setup

```bash
# Create hokm_game database
docker-compose exec postgresql-primary \
  psql -U postgres -c "CREATE DATABASE hokm_game;"

# Create application users
docker-compose exec postgresql-primary \
  psql -U postgres -d hokm_game -c "
    CREATE USER hokm_app WITH PASSWORD 'secure_app_password';
    CREATE USER hokm_read WITH PASSWORD 'secure_read_password';
    
    GRANT CONNECT ON DATABASE hokm_game TO hokm_app;
    GRANT CONNECT ON DATABASE hokm_game TO hokm_read;
    
    GRANT USAGE ON SCHEMA public TO hokm_app;
    GRANT USAGE ON SCHEMA public TO hokm_read;
    
    GRANT CREATE ON SCHEMA public TO hokm_app;
    GRANT SELECT ON ALL TABLES IN SCHEMA public TO hokm_read;
    
    ALTER DEFAULT PRIVILEGES IN SCHEMA public 
    GRANT SELECT ON TABLES TO hokm_read;
  "

# Install extensions
docker-compose exec postgresql-primary \
  psql -U postgres -d hokm_game -c "
    CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
    CREATE EXTENSION IF NOT EXISTS uuid-ossp;
    CREATE EXTENSION IF NOT EXISTS btree_gin;
  "
```

## Testing and Validation

### 1. Run Recovery Tests

```bash
# Run comprehensive test suite
./postgresql-ha/scripts/test-recovery.sh all

# Run specific tests
./postgresql-ha/scripts/test-recovery.sh failover
./postgresql-ha/scripts/test-recovery.sh backup
./postgresql-ha/scripts/test-recovery.sh monitoring
```

### 2. Performance Baseline

```bash
# Install pgbench
docker-compose exec postgresql-primary \
  psql -U postgres -c "CREATE DATABASE pgbench_test;"

# Initialize pgbench
docker-compose exec postgresql-primary \
  pgbench -i -s 100 -U postgres pgbench_test

# Run performance test
docker-compose exec postgresql-primary \
  pgbench -c 50 -j 10 -t 1000 -U postgres pgbench_test
```

### 3. Load Testing

```bash
# Create test script for gaming workload
cat > test_gaming_load.py << 'EOF'
import psycopg2
import time
import threading
import random

def simulate_game_session(thread_id):
    conn = psycopg2.connect(
        host='localhost',
        port=5432,
        database='hokm_game',
        user='hokm_app',
        password='secure_app_password'
    )
    
    for i in range(100):
        with conn.cursor() as cur:
            # Simulate game operations
            cur.execute("INSERT INTO game_sessions (player_id, game_data) VALUES (%s, %s)", 
                       (thread_id, f"game_data_{i}"))
            cur.execute("SELECT * FROM game_sessions WHERE player_id = %s", (thread_id,))
            results = cur.fetchall()
        conn.commit()
        time.sleep(random.uniform(0.1, 0.5))
    
    conn.close()

# Run load test
threads = []
for i in range(20):
    t = threading.Thread(target=simulate_game_session, args=(i,))
    threads.append(t)
    t.start()

for t in threads:
    t.join()

print("Load test completed")
EOF

python3 test_gaming_load.py
```

## Monitoring Setup

### 1. Configure Grafana Dashboards

```bash
# Import PostgreSQL dashboard
curl -X POST http://admin:${GRAFANA_ADMIN_PASSWORD}@localhost:3000/api/dashboards/db \
  -H "Content-Type: application/json" \
  -d @postgresql-ha/dashboards/postgresql-overview.json

# Import gaming dashboard
curl -X POST http://admin:${GRAFANA_ADMIN_PASSWORD}@localhost:3000/api/dashboards/db \
  -H "Content-Type: application/json" \
  -d @postgresql-ha/dashboards/gaming-performance.json
```

### 2. Set up Alerting

```bash
# Test alert configuration
curl http://localhost:9093/api/v1/alerts

# Send test alert
curl -X POST http://localhost:9093/api/v1/alerts \
  -H "Content-Type: application/json" \
  -d '[{
    "labels": {
      "alertname": "TestAlert",
      "severity": "warning"
    },
    "annotations": {
      "summary": "Test alert from deployment"
    }
  }]'
```

## Backup Configuration

### 1. Set up Automated Backups

```bash
# Create backup cron job
cat > /etc/cron.d/postgresql-backup << 'EOF'
# PostgreSQL HA Backup Schedule
# Full backup daily at 2 AM
0 2 * * * root /path/to/postgresql-ha/scripts/backup.sh full

# WAL archiving every 5 minutes
*/5 * * * * root /path/to/postgresql-ha/scripts/backup.sh wal

# Cleanup old backups weekly
0 3 * * 0 root find /backup/postgresql -type f -mtime +7 -delete
EOF

# Make scripts executable
chmod +x postgresql-ha/scripts/backup.sh
chmod +x postgresql-ha/scripts/test-recovery.sh
```

### 2. Test Backup and Restore

```bash
# Perform initial backup
./postgresql-ha/scripts/backup.sh full

# Test restore to verify backup integrity
./postgresql-ha/scripts/test-recovery.sh backup
```

## Application Integration

### 1. Update Application Configuration

```python
# Example configuration for Hokm game backend
DATABASE_CONFIG = {
    'primary': {
        'host': 'haproxy.yourdomain.com',
        'port': 5432,
        'database': 'hokm_game',
        'user': 'hokm_app',
        'password': 'secure_app_password',
        'sslmode': 'require'
    },
    'read_replica': {
        'host': 'haproxy.yourdomain.com',
        'port': 5433,
        'database': 'hokm_game',
        'user': 'hokm_read',
        'password': 'secure_read_password',
        'sslmode': 'require'
    }
}
```

### 2. Health Check Integration

```bash
# Add health check endpoint to your application
curl http://your-app:8080/health/database
```

## Post-Deployment Checklist

- [ ] Verify all services are running
- [ ] Test database connectivity from application
- [ ] Verify replication is working
- [ ] Test failover procedures
- [ ] Confirm backup automation
- [ ] Set up monitoring alerts
- [ ] Test alert notifications
- [ ] Verify SSL/TLS connectivity
- [ ] Document connection strings
- [ ] Train operations team
- [ ] Create runbooks for common issues
- [ ] Schedule regular maintenance windows

## Troubleshooting Deployment Issues

### Common Issues and Solutions

#### 1. etcd Cluster Not Starting
```bash
# Check etcd logs
docker-compose logs etcd1 etcd2 etcd3

# Reset etcd data if needed
docker-compose down
docker volume rm $(docker volume ls -q | grep etcd)
docker-compose up -d etcd1 etcd2 etcd3
```

#### 2. PostgreSQL Not Starting
```bash
# Check PostgreSQL logs
docker-compose logs postgresql-primary

# Check Patroni configuration
docker-compose exec postgresql-primary patronictl list

# Reset PostgreSQL data if needed (WARNING: Data loss)
docker-compose down
docker volume rm $(docker volume ls -q | grep postgresql)
docker-compose up -d
```

#### 3. Replication Not Working
```bash
# Check replication status
docker-compose exec postgresql-primary \
  psql -U postgres -c "SELECT * FROM pg_stat_replication;"

# Check replica logs
docker-compose logs postgresql-replica1

# Restart replica
docker-compose restart postgresql-replica1
```

#### 4. HAProxy Not Routing Traffic
```bash
# Check HAProxy configuration
docker-compose exec haproxy haproxy -f /usr/local/etc/haproxy/haproxy.cfg -c

# Check HAProxy stats
curl http://localhost:8080/stats

# Restart HAProxy
docker-compose restart haproxy
```

## Maintenance and Updates

### Regular Maintenance Tasks

1. **Weekly**: Review monitoring dashboards and alerts
2. **Monthly**: Test backup and restore procedures
3. **Quarterly**: Perform failover testing
4. **Semi-annually**: Update PostgreSQL and related components

### Update Procedures

```bash
# Update Docker images
docker-compose pull

# Rolling update (minimal downtime)
docker-compose up -d --no-deps postgresql-replica2
docker-compose up -d --no-deps postgresql-replica1
# Perform switchover
docker-compose up -d --no-deps postgresql-primary
```

This deployment guide provides comprehensive instructions for setting up and maintaining the PostgreSQL HA cluster. Follow the procedures carefully and test thoroughly before deploying to production.
