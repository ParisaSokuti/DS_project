# PostgreSQL Streaming Replication Setup Guide

## Overview

This guide provides step-by-step instructions for setting up PostgreSQL streaming replication for the Hokm Game Server. Streaming replication allows you to maintain one or more standby servers that stay synchronized with the primary server.

## Architecture

```
┌─────────────┐    WAL Stream    ┌─────────────┐
│   Primary   │ ────────────────► │  Standby 1  │
│  (R/W)      │                   │  (R/O)      │
└─────────────┘                   └─────────────┘
       │                                 │
       │        WAL Stream               │
       └────────────────────────────────► │
                                ┌─────────────┐
                                │  Standby 2  │
                                │  (R/O)      │
                                └─────────────┘
```

## Prerequisites

1. **PostgreSQL 12+ installed** on all servers
2. **Network connectivity** between primary and standby servers
3. **Same PostgreSQL version** on all servers
4. **Sufficient disk space** for WAL files
5. **Proper firewall configuration** (port 5432 open)

## Configuration Files

### Primary Server Configuration (`primary.conf`)
- `wal_level = replica` - Enable WAL logging for replication
- `max_wal_senders = 3` - Allow up to 3 standby servers
- `hot_standby = on` - Enable hot standby mode
- `wal_keep_size = 1GB` - Keep WAL files for replication
- `archive_mode = on` - Enable WAL archiving

### Standby Server Configuration (`standby.conf`)
- `hot_standby = on` - Allow read queries on standby
- `max_standby_streaming_delay = 30s` - Max delay before cancelling queries
- `hot_standby_feedback = on` - Send feedback to primary

### pg_hba.conf Configuration
```
# Replication connections
host    replication     replicator      192.168.1.100/32        md5
host    replication     replicator      192.168.1.101/32        md5
host    replication     replicator      192.168.1.102/32        md5
```

## Setup Instructions

### Step 1: Configure Primary Server

1. **Run the primary setup script:**
   ```bash
   cd /path/to/hokm_game_final/postgresql-ha
   chmod +x scripts/setup_primary.sh
   sudo ./scripts/setup_primary.sh
   ```

2. **Manual setup (if script fails):**
   ```bash
   # Create replication user
   sudo -u postgres psql -c "CREATE USER replicator WITH REPLICATION ENCRYPTED PASSWORD 'replicator_password';"
   
   # Copy configuration files
   sudo cp config/postgresql/primary.conf /etc/postgresql/postgresql.conf
   sudo cp config/postgresql/pg_hba_replication.conf /etc/postgresql/pg_hba.conf
   
   # Create WAL archive directory
   sudo mkdir -p /var/lib/postgresql/wal_archive
   sudo chown postgres:postgres /var/lib/postgresql/wal_archive
   
   # Restart PostgreSQL
   sudo systemctl restart postgresql
   ```

3. **Verify primary configuration:**
   ```bash
   sudo -u postgres psql -c "SHOW wal_level;"
   sudo -u postgres psql -c "SHOW max_wal_senders;"
   sudo -u postgres psql -c "SELECT * FROM pg_replication_slots;"
   ```

### Step 2: Configure Standby Server

1. **Run the standby setup script:**
   ```bash
   cd /path/to/hokm_game_final/postgresql-ha
   chmod +x scripts/setup_standby.sh
   sudo ./scripts/setup_standby.sh [PRIMARY_SERVER_IP]
   ```

2. **Manual setup (if script fails):**
   ```bash
   # Stop PostgreSQL
   sudo systemctl stop postgresql
   
   # Backup existing data
   sudo mv /var/lib/postgresql/data /var/lib/postgresql/data.backup
   
   # Clone primary server
   sudo -u postgres pg_basebackup -h [PRIMARY_IP] -U replicator -D /var/lib/postgresql/data -P -v -R -W
   
   # Create standby.signal file (PostgreSQL 12+)
   sudo -u postgres touch /var/lib/postgresql/data/standby.signal
   
   # Configure connection to primary
   sudo -u postgres bash -c "echo \"primary_conninfo = 'host=[PRIMARY_IP] port=5432 user=replicator password=replicator_password'\" >> /var/lib/postgresql/data/postgresql.auto.conf"
   
   # Start PostgreSQL
   sudo systemctl start postgresql
   ```

3. **Verify standby configuration:**
   ```bash
   sudo -u postgres psql -c "SELECT pg_is_in_recovery();"
   sudo -u postgres psql -c "SELECT * FROM pg_stat_wal_receiver;"
   ```

### Step 3: Monitor Replication

1. **Use the monitoring script:**
   ```bash
   chmod +x scripts/monitor_replication.sh
   ./scripts/monitor_replication.sh
   ```

2. **Manual monitoring commands:**
   ```bash
   # On primary server
   sudo -u postgres psql -c "SELECT * FROM pg_stat_replication;"
   
   # On standby server
   sudo -u postgres psql -c "SELECT * FROM pg_stat_wal_receiver;"
   sudo -u postgres psql -c "SELECT EXTRACT(EPOCH FROM now() - pg_last_xact_replay_timestamp()) AS lag_seconds;"
   ```

## Failover Procedure

### Automatic Failover (Using pg_ctl promote)

1. **On the standby server to promote:**
   ```bash
   chmod +x scripts/promote_standby.sh
   sudo ./scripts/promote_standby.sh
   ```

2. **Manual promotion:**
   ```bash
   # Method 1: Using pg_ctl (recommended)
   sudo -u postgres pg_ctl promote -D /var/lib/postgresql/data
   
   # Method 2: Using trigger file
   sudo -u postgres touch /tmp/promote_trigger
   ```

### Manual Failover Steps

1. **Stop the primary server** (if possible):
   ```bash
   sudo systemctl stop postgresql
   ```

2. **Promote standby to primary:**
   ```bash
   sudo -u postgres pg_ctl promote -D /var/lib/postgresql/data
   ```

3. **Verify promotion:**
   ```bash
   sudo -u postgres psql -c "SELECT pg_is_in_recovery();"  # Should return 'f'
   ```

4. **Update application connection strings** to point to new primary

5. **Set up new standby servers** if needed

## Monitoring and Maintenance

### Key Metrics to Monitor

1. **Replication Lag:**
   ```sql
   SELECT EXTRACT(EPOCH FROM now() - pg_last_xact_replay_timestamp()) AS lag_seconds;
   ```

2. **WAL Receiver Status:**
   ```sql
   SELECT * FROM pg_stat_wal_receiver;
   ```

3. **Replication Slots:**
   ```sql
   SELECT slot_name, active, restart_lsn FROM pg_replication_slots;
   ```

4. **Active Connections:**
   ```sql
   SELECT * FROM pg_stat_replication;
   ```

### Maintenance Tasks

1. **Regular WAL cleanup:**
   ```bash
   # WAL files are automatically cleaned up, but monitor disk space
   du -sh /var/lib/postgresql/wal_archive/
   ```

2. **Monitor replication lag:**
   ```bash
   # Set up alerts for lag > 60 seconds
   ./scripts/monitor_replication.sh --watch
   ```

3. **Test failover procedures:**
   ```bash
   # Regular failover testing in non-production environment
   ./scripts/promote_standby.sh
   ```

## Troubleshooting

### Common Issues

1. **Connection refused:**
   - Check pg_hba.conf for replication user
   - Verify network connectivity
   - Check firewall settings

2. **Authentication failed:**
   - Verify replication user password
   - Check pg_hba.conf authentication method

3. **WAL receiver not starting:**
   - Check primary_conninfo in postgresql.auto.conf
   - Verify replication slot exists
   - Check logs: `tail -f /var/log/postgresql/postgresql-*.log`

4. **High replication lag:**
   - Check network bandwidth
   - Monitor primary server load
   - Consider increasing max_wal_senders

### Log Files

- **Primary server logs:** `/var/log/postgresql/postgresql-*.log`
- **Standby server logs:** `/var/log/postgresql/postgresql-standby-*.log`
- **WAL receiver logs:** Check PostgreSQL logs for WAL receiver messages

## Security Considerations

1. **Use strong passwords** for replication user
2. **Limit replication connections** in pg_hba.conf
3. **Enable SSL** for replication connections (optional)
4. **Monitor access logs** for unauthorized connection attempts
5. **Regular security updates** for PostgreSQL

## Performance Tuning

### Primary Server
- Increase `wal_buffers` for write-heavy workloads
- Adjust `checkpoint_completion_target` for smoother I/O
- Monitor `max_wal_senders` based on number of standbys

### Standby Server
- Increase `max_parallel_workers` for read queries
- Tune `work_mem` for analytical queries
- Consider `hot_standby_feedback = on` to reduce query cancellations

## Scripts Reference

| Script | Purpose |
|--------|---------|
| `setup_primary.sh` | Configure primary server for replication |
| `setup_standby.sh` | Set up standby server |
| `promote_standby.sh` | Promote standby to primary |
| `monitor_replication.sh` | Monitor replication status |

## Testing

### Replication Test
1. **Create test data on primary:**
   ```sql
   CREATE TABLE replication_test (id serial, data text, created timestamp default now());
   INSERT INTO replication_test (data) VALUES ('test data');
   ```

2. **Verify on standby:**
   ```sql
   SELECT * FROM replication_test;
   ```

### Failover Test
1. **Stop primary server**
2. **Promote standby**
3. **Verify write capability on new primary**
4. **Test application connectivity**

## Best Practices

1. **Regular monitoring** of replication lag and health
2. **Automated failover** using tools like Patroni (see docker-compose.yml)
3. **Regular backup** of primary server
4. **Testing failover procedures** in non-production environment
5. **Documentation** of failover procedures for operations team
6. **Alerting** for replication failures or high lag

## Support

For issues with this setup:
1. Check PostgreSQL logs first
2. Use monitoring scripts to diagnose issues
3. Consult PostgreSQL documentation for advanced configuration
4. Consider using Patroni for automatic failover (configured in docker-compose.yml)

---

**Note:** This setup is optimized for the Hokm Game Server but can be adapted for other applications. Always test in a non-production environment first.
