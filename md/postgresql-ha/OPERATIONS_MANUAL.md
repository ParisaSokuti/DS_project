# PostgreSQL High Availability - Operations Manual

This manual provides comprehensive guidance for operating and maintaining the PostgreSQL HA cluster for the Hokm gaming platform.

## Table of Contents

1. [Daily Operations](#daily-operations)
2. [Monitoring and Alerting](#monitoring-and-alerting)
3. [Backup and Recovery](#backup-and-recovery)
4. [Failover Procedures](#failover-procedures)
5. [Maintenance Operations](#maintenance-operations)
6. [Troubleshooting](#troubleshooting)
7. [Performance Tuning](#performance-tuning)
8. [Security Operations](#security-operations)

## Daily Operations

### 1. Health Check Procedures

#### Quick Health Check
```bash
# Check cluster status
docker-compose exec postgresql-primary \
  curl -s http://localhost:8008/cluster | jq '.'

# Check replication lag
docker-compose exec postgresql-primary \
  psql -U postgres -c "SELECT * FROM pg_stat_replication;"

# Check connection counts
docker-compose exec postgresql-primary \
  psql -U postgres -c "SELECT count(*) as connections FROM pg_stat_activity;"
```

#### Detailed Health Assessment
```bash
# Run comprehensive health check
./scripts/test-recovery.sh status

# Check HAProxy status
docker-compose exec haproxy \
  curl -s http://localhost:8080/stats

# Check PgBouncer pools
docker-compose exec pgbouncer \
  psql -h localhost -p 6432 -U postgres -d pgbouncer -c "SHOW POOLS;"
```

### 2. Log Monitoring

#### PostgreSQL Logs
```bash
# View primary logs
docker-compose logs -f postgresql-primary

# View replica logs
docker-compose logs -f postgresql-replica1
docker-compose logs -f postgresql-replica2

# Search for errors in logs
docker-compose logs postgresql-primary 2>&1 | grep -i error

# Monitor Patroni logs
docker-compose logs -f postgresql-primary | grep patroni
```

#### Application Logs
```bash
# Check for database connection errors
grep -i "connection.*failed\|timeout\|refused" /var/log/hokm-game/*.log

# Monitor slow queries
grep -i "slow\|duration" /var/log/postgresql/*.log
```

### 3. Performance Monitoring

#### Key Metrics to Monitor
```bash
# Check current connections
docker-compose exec postgresql-primary \
  psql -U postgres -c "
    SELECT 
      count(*) as total_connections,
      count(*) FILTER (WHERE state = 'active') as active_connections,
      count(*) FILTER (WHERE state = 'idle') as idle_connections
    FROM pg_stat_activity;"

# Monitor query performance
docker-compose exec postgresql-primary \
  psql -U postgres -c "
    SELECT 
      query,
      mean_exec_time,
      calls,
      total_exec_time
    FROM pg_stat_statements 
    ORDER BY mean_exec_time DESC 
    LIMIT 10;"

# Check database size
docker-compose exec postgresql-primary \
  psql -U postgres -c "
    SELECT 
      datname,
      pg_size_pretty(pg_database_size(datname)) as size
    FROM pg_database 
    WHERE datname NOT IN ('template0', 'template1');"
```

## Monitoring and Alerting

### 1. Prometheus Metrics

#### Key Metrics to Monitor
- `pg_up`: Database availability
- `pg_stat_replication_lag_seconds`: Replication lag
- `pg_stat_database_numbackends`: Connection count
- `pg_stat_database_tup_inserted_per_sec`: Insert rate
- `pg_stat_database_tup_updated_per_sec`: Update rate
- `pg_locks_count`: Lock contention

#### Custom Queries for Gaming Metrics
```sql
-- Active game sessions
SELECT count(*) as active_games 
FROM game_sessions 
WHERE status = 'active' 
AND updated_at > NOW() - INTERVAL '5 minutes';

-- Player connection rate
SELECT count(*) as player_connections 
FROM pg_stat_activity 
WHERE application_name LIKE 'hokm%';

-- Slow queries affecting gaming
SELECT query, mean_exec_time 
FROM pg_stat_statements 
WHERE query LIKE '%game_%' 
AND mean_exec_time > 1000;
```

### 2. Alert Configuration

#### Critical Alerts (Immediate Response)
- Primary database down
- All replicas down
- Replication lag > 30 seconds
- Connection exhaustion (>95% of max_connections)
- Disk space < 10%

#### Warning Alerts (Monitor Closely)
- Single replica down
- Replication lag > 10 seconds
- High connection usage (>80%)
- Slow queries (>5 seconds average)
- High error rate

### 3. Grafana Dashboards

#### PostgreSQL Overview Dashboard
- Cluster topology and status
- Connection metrics
- Query performance
- Replication lag
- Resource utilization

#### Gaming Performance Dashboard
- Active game sessions
- Player connection patterns
- Game-specific query performance
- Session duration metrics

## Backup and Recovery

### 1. Automated Backup Procedures

#### Full Backup (Daily)
```bash
# Run full backup
./scripts/backup.sh full

# Verify backup
./scripts/backup.sh full && \
  ls -la /backup/postgresql/full_backup_*.sql.gz
```

#### WAL Archiving (Continuous)
```bash
# Check WAL archiving status
docker-compose exec postgresql-primary \
  psql -U postgres -c "SELECT * FROM pg_stat_archiver;"

# Manual WAL archive
./scripts/backup.sh wal /path/to/wal/file
```

### 2. Backup Verification

#### Test Restore Procedure
```bash
# Create test database
docker-compose exec postgresql-primary \
  psql -U postgres -c "CREATE DATABASE hokm_test_restore;"

# Restore backup to test database
docker-compose exec postgresql-primary \
  pg_restore -U postgres -d hokm_test_restore /backup/latest_backup.custom

# Verify data integrity
docker-compose exec postgresql-primary \
  psql -U postgres -d hokm_test_restore -c "
    SELECT 
      schemaname,
      tablename,
      n_tup_ins as inserts,
      n_tup_upd as updates,
      n_tup_del as deletes
    FROM pg_stat_user_tables
    ORDER BY schemaname, tablename;"

# Cleanup test database
docker-compose exec postgresql-primary \
  psql -U postgres -c "DROP DATABASE hokm_test_restore;"
```

### 3. Recovery Procedures

#### Point-in-Time Recovery
```bash
# Stop replica for recovery
docker-compose stop postgresql-replica1

# Restore from base backup
pg_basebackup -h postgresql-primary -D /recovery/data -U replicator -P -W

# Configure recovery
cat > /recovery/data/postgresql.conf << EOF
restore_command = 'cp /backup/wal/%f %p'
recovery_target_time = '2024-01-15 14:30:00'
EOF

# Start recovery
docker run --rm -v /recovery/data:/var/lib/postgresql/data postgres:15 \
  postgres -D /var/lib/postgresql/data
```

## Failover Procedures

### 1. Automatic Failover (Patroni)

#### Monitor Failover Process
```bash
# Watch cluster state during failover
watch -n 2 "docker-compose exec postgresql-primary \
  curl -s http://localhost:8008/cluster | jq '.'"

# Check failover logs
docker-compose logs -f postgresql-replica1 | grep -i failover
```

### 2. Manual Failover

#### Planned Failover (Maintenance)
```bash
# Step 1: Ensure replicas are caught up
docker-compose exec postgresql-primary \
  psql -U postgres -c "SELECT * FROM pg_stat_replication;"

# Step 2: Perform switchover
docker-compose exec postgresql-replica1 \
  curl -X POST http://localhost:8009/switchover

# Step 3: Verify new primary
docker-compose exec postgresql-replica1 \
  curl -s http://localhost:8009/cluster | jq '.members[] | select(.role=="Leader")'
```

#### Emergency Failover
```bash
# Force failover to specific replica
docker-compose exec postgresql-replica1 \
  curl -X POST http://localhost:8009/failover

# Update application configuration
# Update HAProxy configuration if needed
# Verify application connectivity
```

### 3. Recovery After Failover

#### Re-integrate Former Primary
```bash
# Wait for former primary to start as replica
docker-compose logs -f postgresql-primary | grep "replica"

# Verify replication status
docker-compose exec postgresql-replica1 \
  psql -U postgres -c "SELECT * FROM pg_stat_replication;"

# Check cluster status
docker-compose exec postgresql-replica1 \
  curl -s http://localhost:8009/cluster | jq '.'
```

## Maintenance Operations

### 1. PostgreSQL Updates

#### Minor Version Updates
```bash
# Step 1: Update replica images
docker-compose pull postgresql-replica1 postgresql-replica2

# Step 2: Rolling update replicas
docker-compose stop postgresql-replica2
docker-compose up -d postgresql-replica2

# Wait for replica to catch up, then repeat for replica1

# Step 3: Failover to updated replica
docker-compose exec postgresql-replica1 \
  curl -X POST http://localhost:8009/switchover

# Step 4: Update former primary
docker-compose stop postgresql-primary
docker-compose up -d postgresql-primary
```

#### Major Version Updates
```bash
# Step 1: Create backup
./scripts/backup.sh full

# Step 2: Test upgrade on replica
# (Detailed procedure varies by version)

# Step 3: Perform planned maintenance window
# - Drain connections
# - Stop applications
# - Perform upgrade
# - Test thoroughly
# - Resume operations
```

### 2. Configuration Changes

#### PostgreSQL Configuration Updates
```bash
# Step 1: Update configuration files
vim postgresql-ha/config/postgresql/patroni-primary.yml

# Step 2: Apply changes via Patroni
docker-compose exec postgresql-primary \
  curl -X PATCH http://localhost:8008/config \
  -H "Content-Type: application/json" \
  -d '{"postgresql": {"parameters": {"shared_buffers": "512MB"}}}'

# Step 3: Restart if required
docker-compose exec postgresql-primary \
  curl -X POST http://localhost:8008/restart
```

#### HAProxy Configuration Updates
```bash
# Step 1: Update configuration
vim postgresql-ha/config/haproxy/haproxy.cfg

# Step 2: Validate configuration
docker-compose exec haproxy haproxy -f /usr/local/etc/haproxy/haproxy.cfg -c

# Step 3: Reload HAProxy
docker-compose exec haproxy \
  kill -USR2 $(pidof haproxy)
```

### 3. Scaling Operations

#### Add New Replica
```bash
# Step 1: Create replica configuration
cp postgresql-ha/config/postgresql/patroni-replica1.yml \
   postgresql-ha/config/postgresql/patroni-replica3.yml

# Step 2: Update docker-compose.yml
# Add new replica service

# Step 3: Start new replica
docker-compose up -d postgresql-replica3

# Step 4: Verify replication
docker-compose exec postgresql-primary \
  psql -U postgres -c "SELECT * FROM pg_stat_replication;"
```

## Troubleshooting

### 1. Common Issues

#### High Replication Lag
```bash
# Check network connectivity
docker-compose exec postgresql-primary ping postgresql-replica1

# Check WAL generation rate
docker-compose exec postgresql-primary \
  psql -U postgres -c "SELECT * FROM pg_stat_wal;"

# Check replica apply rate
docker-compose exec postgresql-replica1 \
  psql -U postgres -c "SELECT * FROM pg_stat_wal_receiver;"

# Possible solutions:
# - Increase wal_buffers
# - Check disk I/O performance
# - Verify network bandwidth
```

#### Connection Pool Exhaustion
```bash
# Check PgBouncer status
docker-compose exec pgbouncer \
  psql -h localhost -p 6432 -U postgres -d pgbouncer -c "SHOW POOLS;"

# Check for idle connections
docker-compose exec postgresql-primary \
  psql -U postgres -c "
    SELECT 
      state,
      count(*),
      max(now() - state_change) as max_idle_time
    FROM pg_stat_activity 
    GROUP BY state;"

# Kill idle connections if needed
docker-compose exec postgresql-primary \
  psql -U postgres -c "
    SELECT pg_terminate_backend(pid)
    FROM pg_stat_activity
    WHERE state = 'idle'
    AND now() - state_change > interval '1 hour';"
```

#### Split-Brain Scenarios
```bash
# Check cluster status on all nodes
for node in postgresql-primary postgresql-replica1 postgresql-replica2; do
  echo "=== $node ==="
  docker-compose exec $node \
    curl -s http://localhost:800{8,9,10}/cluster | jq '.members[] | select(.role=="Leader")'
done

# If multiple leaders detected:
# 1. Stop all nodes
# 2. Clear DCS state
# 3. Restart with fresh bootstrap
```

### 2. Performance Issues

#### Slow Query Analysis
```bash
# Enable query logging
docker-compose exec postgresql-primary \
  psql -U postgres -c "ALTER SYSTEM SET log_min_duration_statement = 1000;"

# Reload configuration
docker-compose exec postgresql-primary \
  psql -U postgres -c "SELECT pg_reload_conf();"

# Analyze slow queries
docker-compose exec postgresql-primary \
  psql -U postgres -c "
    SELECT 
      query,
      calls,
      total_exec_time,
      mean_exec_time,
      rows
    FROM pg_stat_statements 
    WHERE mean_exec_time > 1000
    ORDER BY mean_exec_time DESC 
    LIMIT 10;"
```

#### Lock Contention
```bash
# Check current locks
docker-compose exec postgresql-primary \
  psql -U postgres -c "
    SELECT 
      l.locktype,
      l.mode,
      l.granted,
      a.query,
      a.pid
    FROM pg_locks l
    JOIN pg_stat_activity a ON l.pid = a.pid
    WHERE NOT l.granted
    ORDER BY l.pid;"

# Check blocking queries
docker-compose exec postgresql-primary \
  psql -U postgres -c "
    SELECT 
      blocked_locks.pid AS blocked_pid,
      blocked_activity.query AS blocked_statement,
      blocking_locks.pid AS blocking_pid,
      blocking_activity.query AS blocking_statement
    FROM pg_catalog.pg_locks blocked_locks
    JOIN pg_catalog.pg_stat_activity blocked_activity ON blocked_activity.pid = blocked_locks.pid
    JOIN pg_catalog.pg_locks blocking_locks ON blocking_locks.locktype = blocked_locks.locktype
    JOIN pg_catalog.pg_stat_activity blocking_activity ON blocking_activity.pid = blocking_locks.pid
    WHERE NOT blocked_locks.granted AND blocking_locks.granted;"
```

## Performance Tuning

### 1. Gaming-Specific Optimizations

#### Connection Pool Tuning
```sql
-- Optimize for gaming workload
ALTER SYSTEM SET max_connections = 200;
ALTER SYSTEM SET shared_buffers = '512MB';
ALTER SYSTEM SET effective_cache_size = '2GB';
ALTER SYSTEM SET work_mem = '16MB';
ALTER SYSTEM SET maintenance_work_mem = '128MB';

-- Gaming-specific settings
ALTER SYSTEM SET tcp_keepalives_idle = 600;
ALTER SYSTEM SET tcp_keepalives_interval = 30;
ALTER SYSTEM SET tcp_keepalives_count = 3;

-- Apply changes
SELECT pg_reload_conf();
```

#### Index Optimization
```sql
-- Analyze gaming query patterns
SELECT 
  query,
  calls,
  total_exec_time,
  mean_exec_time
FROM pg_stat_statements 
WHERE query LIKE '%game_%' 
ORDER BY total_exec_time DESC;

-- Create gaming-specific indexes
CREATE INDEX CONCURRENTLY idx_game_sessions_active 
ON game_sessions (player_id, status) 
WHERE status = 'active';

CREATE INDEX CONCURRENTLY idx_game_moves_recent 
ON game_moves (game_id, created_at) 
WHERE created_at > NOW() - interval '1 hour';
```

### 2. Monitoring Query Performance

#### Set up pg_stat_statements
```sql
-- Enable extension
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- Configure collection
ALTER SYSTEM SET shared_preload_libraries = 'pg_stat_statements';
ALTER SYSTEM SET pg_stat_statements.track = 'all';
ALTER SYSTEM SET pg_stat_statements.max = 10000;

-- Restart required for shared_preload_libraries changes
```

## Security Operations

### 1. User Management

#### Create Application Users
```sql
-- Create read-only user for reports
CREATE USER hokm_reports WITH PASSWORD 'secure_password';
GRANT CONNECT ON DATABASE hokm_game TO hokm_reports;
GRANT USAGE ON SCHEMA public TO hokm_reports;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO hokm_reports;

-- Create limited user for game operations
CREATE USER hokm_game_user WITH PASSWORD 'secure_password';
GRANT CONNECT ON DATABASE hokm_game TO hokm_game_user;
GRANT USAGE ON SCHEMA public TO hokm_game_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON game_sessions TO hokm_game_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON game_moves TO hokm_game_user;
```

#### Password Rotation
```bash
# Generate new passwords
NEW_PASSWORD=$(openssl rand -base64 32)

# Update database user
docker-compose exec postgresql-primary \
  psql -U postgres -c "ALTER USER hokm_app PASSWORD '$NEW_PASSWORD';"

# Update PgBouncer userlist
# Update application configuration
# Test connections
```

### 2. SSL/TLS Configuration

#### Enable SSL
```sql
-- Configure SSL
ALTER SYSTEM SET ssl = 'on';
ALTER SYSTEM SET ssl_cert_file = '/etc/ssl/certs/server.crt';
ALTER SYSTEM SET ssl_key_file = '/etc/ssl/private/server.key';
ALTER SYSTEM SET ssl_ca_file = '/etc/ssl/certs/ca.crt';

-- Restart required
```

### 3. Access Control

#### Network Security
```bash
# Update pg_hba.conf for stricter access
echo "host all all 10.0.0.0/8 md5" >> /etc/postgresql/pg_hba.conf
echo "hostssl all all 0.0.0.0/0 md5" >> /etc/postgresql/pg_hba.conf

# Reload configuration
docker-compose exec postgresql-primary \
  psql -U postgres -c "SELECT pg_reload_conf();"
```

## Maintenance Schedule

### Daily Tasks
- [ ] Check cluster health status
- [ ] Review error logs
- [ ] Verify backup completion
- [ ] Monitor key performance metrics

### Weekly Tasks
- [ ] Analyze slow query reports
- [ ] Review capacity planning metrics
- [ ] Test backup restore procedure
- [ ] Update security patches

### Monthly Tasks
- [ ] Performance tuning review
- [ ] Failover testing
- [ ] Capacity planning assessment
- [ ] Security audit

### Quarterly Tasks
- [ ] Disaster recovery testing
- [ ] Configuration review
- [ ] Performance benchmarking
- [ ] Documentation updates

This operations manual provides comprehensive guidance for maintaining the PostgreSQL HA cluster. Regular execution of these procedures ensures optimal performance, reliability, and security for the Hokm gaming platform.
