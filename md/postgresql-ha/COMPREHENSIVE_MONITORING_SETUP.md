# PostgreSQL Comprehensive Monitoring Guide

## Overview

This document provides a complete monitoring solution for the Hokm game server's PostgreSQL database, focusing on real-time health monitoring, performance tracking, and proactive alerting.

## Monitoring Architecture

```
PostgreSQL Database → pg_stat_statements → Prometheus → Grafana Dashboard
        ↓                    ↓                  ↓            ↓
Custom Metrics      Query Analytics    Alert Manager   Real-time Alerts
Health Checks      Performance Data    Notifications   Capacity Planning
```

## 1. Database Monitoring Setup

### 1.1 Enable Required Extensions

```sql
-- Enable monitoring extensions
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
CREATE EXTENSION IF NOT EXISTS pg_buffercache;
CREATE EXTENSION IF NOT EXISTS pg_stat_kcache;

-- Configure pg_stat_statements
ALTER SYSTEM SET shared_preload_libraries = 'pg_stat_statements';
ALTER SYSTEM SET pg_stat_statements.max = 10000;
ALTER SYSTEM SET pg_stat_statements.track = 'all';
ALTER SYSTEM SET pg_stat_statements.track_utility = 'on';
ALTER SYSTEM SET pg_stat_statements.save = 'on';

-- Enable detailed logging
ALTER SYSTEM SET log_min_duration_statement = 1000;  -- Log queries > 1s
ALTER SYSTEM SET log_checkpoints = 'on';
ALTER SYSTEM SET log_connections = 'on';
ALTER SYSTEM SET log_disconnections = 'on';
ALTER SYSTEM SET log_lock_waits = 'on';
ALTER SYSTEM SET log_temp_files = 0;
ALTER SYSTEM SET log_autovacuum_min_duration = 0;

-- Apply configuration
SELECT pg_reload_conf();
```

### 1.2 Custom Monitoring Schema

```sql
-- Create monitoring schema
CREATE SCHEMA IF NOT EXISTS monitoring;

-- Monitoring configuration table
CREATE TABLE monitoring.config (
    metric_name VARCHAR(100) PRIMARY KEY,
    enabled BOOLEAN DEFAULT true,
    threshold_warning DECIMAL,
    threshold_critical DECIMAL,
    check_interval_seconds INTEGER DEFAULT 60,
    description TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Insert monitoring thresholds
INSERT INTO monitoring.config (metric_name, threshold_warning, threshold_critical, description) VALUES
('connection_usage_percent', 80.0, 90.0, 'Connection pool usage percentage'),
('cache_hit_ratio_percent', 95.0, 90.0, 'Buffer cache hit ratio'),
('disk_usage_percent', 80.0, 90.0, 'Disk space usage percentage'),
('long_running_queries_minutes', 5.0, 10.0, 'Long-running query duration'),
('lock_wait_seconds', 30.0, 60.0, 'Lock wait time threshold'),
('avg_query_time_ms', 100.0, 500.0, 'Average query execution time'),
('replication_lag_mb', 100.0, 500.0, 'Replication lag in megabytes'),
('dead_tuple_ratio_percent', 20.0, 30.0, 'Dead tuple ratio threshold'),
('temp_file_size_mb', 100.0, 500.0, 'Temporary file size threshold');

-- Monitoring history table
CREATE TABLE monitoring.metrics_history (
    id SERIAL PRIMARY KEY,
    metric_name VARCHAR(100) NOT NULL,
    metric_value DECIMAL NOT NULL,
    metric_labels JSONB,
    recorded_at TIMESTAMP DEFAULT NOW()
);

-- Create indexes for performance
CREATE INDEX idx_metrics_history_name_time ON monitoring.metrics_history(metric_name, recorded_at);
CREATE INDEX idx_metrics_history_labels ON monitoring.metrics_history USING GIN(metric_labels);

-- Alerts table
CREATE TABLE monitoring.alerts (
    id SERIAL PRIMARY KEY,
    metric_name VARCHAR(100) NOT NULL,
    alert_level VARCHAR(20) NOT NULL, -- 'warning', 'critical'
    alert_message TEXT NOT NULL,
    metric_value DECIMAL NOT NULL,
    threshold_value DECIMAL NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    resolved_at TIMESTAMP,
    acknowledged_at TIMESTAMP,
    acknowledged_by VARCHAR(100)
);

CREATE INDEX idx_alerts_unresolved ON monitoring.alerts(created_at) WHERE resolved_at IS NULL;
```

## 2. Comprehensive Monitoring Views

### 2.1 Database Health Overview

```sql
-- Database health dashboard view
CREATE OR REPLACE VIEW monitoring.v_database_health AS
SELECT 
    'database_size' as metric_name,
    pg_size_pretty(pg_database_size(current_database())) as display_value,
    ROUND(pg_database_size(current_database()) / 1024.0 / 1024.0, 2) as numeric_value,
    'MB' as unit,
    NOW() as measured_at
UNION ALL
SELECT 
    'connection_count' as metric_name,
    COUNT(*)::text as display_value,
    COUNT(*)::decimal as numeric_value,
    'connections' as unit,
    NOW() as measured_at
FROM pg_stat_activity WHERE datname = current_database()
UNION ALL
SELECT 
    'active_connections' as metric_name,
    COUNT(*)::text as display_value,
    COUNT(*)::decimal as numeric_value,
    'connections' as unit,
    NOW() as measured_at
FROM pg_stat_activity WHERE datname = current_database() AND state = 'active'
UNION ALL
SELECT 
    'cache_hit_ratio' as metric_name,
    ROUND(sum(blks_hit)*100.0/sum(blks_hit+blks_read), 2)::text || '%' as display_value,
    ROUND(sum(blks_hit)*100.0/sum(blks_hit+blks_read), 2) as numeric_value,
    'percent' as unit,
    NOW() as measured_at
FROM pg_stat_database WHERE datname = current_database()
UNION ALL
SELECT 
    'transactions_per_second' as metric_name,
    ROUND(sum(xact_commit + xact_rollback) / GREATEST(EXTRACT(EPOCH FROM (NOW() - stats_reset)), 1), 2)::text as display_value,
    ROUND(sum(xact_commit + xact_rollback) / GREATEST(EXTRACT(EPOCH FROM (NOW() - stats_reset)), 1), 2) as numeric_value,
    'tps' as unit,
    NOW() as measured_at
FROM pg_stat_database WHERE datname = current_database();
```

### 2.2 Query Performance Monitoring

```sql
-- Query performance analysis view
CREATE OR REPLACE VIEW monitoring.v_query_performance AS
SELECT 
    query,
    calls,
    ROUND(total_exec_time::numeric, 2) as total_time_ms,
    ROUND(mean_exec_time::numeric, 2) as mean_time_ms,
    ROUND(stddev_exec_time::numeric, 2) as stddev_time_ms,
    ROUND(min_exec_time::numeric, 2) as min_time_ms,
    ROUND(max_exec_time::numeric, 2) as max_time_ms,
    rows,
    ROUND(100.0 * shared_blks_hit / nullif(shared_blks_hit + shared_blks_read, 0), 2) as cache_hit_ratio,
    CASE 
        WHEN mean_exec_time > 1000 THEN 'critical'
        WHEN mean_exec_time > 500 THEN 'warning'
        ELSE 'normal'
    END as performance_status,
    NOW() as measured_at
FROM pg_stat_statements 
WHERE calls > 5
ORDER BY mean_exec_time DESC;

-- Gaming-specific query performance
CREATE OR REPLACE VIEW monitoring.v_gaming_query_performance AS
SELECT 
    CASE 
        WHEN query ILIKE '%game_sessions%INSERT%' THEN 'Game Creation'
        WHEN query ILIKE '%game_sessions%UPDATE%' THEN 'Game Updates'
        WHEN query ILIKE '%game_moves%INSERT%' THEN 'Move Recording'
        WHEN query ILIKE '%game_participants%' THEN 'Player Operations'
        WHEN query ILIKE '%websocket_connections%' THEN 'Connection Management'
        WHEN query ILIKE '%SELECT%game_sessions%' THEN 'Game Queries'
        ELSE 'Other Operations'
    END as operation_type,
    COUNT(*) as query_count,
    ROUND(AVG(mean_exec_time)::numeric, 2) as avg_response_time_ms,
    ROUND(MAX(max_exec_time)::numeric, 2) as max_response_time_ms,
    ROUND(SUM(total_exec_time)::numeric, 2) as total_time_ms,
    SUM(calls) as total_calls,
    ROUND(AVG(100.0 * shared_blks_hit / nullif(shared_blks_hit + shared_blks_read, 0))::numeric, 2) as avg_cache_hit_ratio
FROM pg_stat_statements 
WHERE calls > 1
GROUP BY operation_type
ORDER BY avg_response_time_ms DESC;
```

### 2.3 Connection Pool Monitoring

```sql
-- Connection pool monitoring view
CREATE OR REPLACE VIEW monitoring.v_connection_pool AS
SELECT 
    datname,
    state,
    COUNT(*) as connection_count,
    ROUND(COUNT(*) * 100.0 / (SELECT setting::numeric FROM pg_settings WHERE name = 'max_connections'), 2) as usage_percent,
    MAX(EXTRACT(EPOCH FROM (NOW() - query_start))) as longest_query_seconds,
    MAX(EXTRACT(EPOCH FROM (NOW() - state_change))) as longest_state_seconds,
    COUNT(CASE WHEN wait_event_type IS NOT NULL THEN 1 END) as waiting_connections
FROM pg_stat_activity 
WHERE datname IS NOT NULL
GROUP BY datname, state
ORDER BY datname, usage_percent DESC;

-- Active connections detail
CREATE OR REPLACE VIEW monitoring.v_active_connections AS
SELECT 
    pid,
    datname,
    usename,
    application_name,
    client_addr,
    state,
    EXTRACT(EPOCH FROM (NOW() - query_start)) as query_duration_seconds,
    EXTRACT(EPOCH FROM (NOW() - state_change)) as state_duration_seconds,
    wait_event_type,
    wait_event,
    LEFT(query, 100) as query_snippet,
    backend_start,
    query_start
FROM pg_stat_activity 
WHERE datname = current_database() 
AND state = 'active'
ORDER BY query_duration_seconds DESC;
```

### 2.4 Lock Monitoring

```sql
-- Lock monitoring view
CREATE OR REPLACE VIEW monitoring.v_locks AS
SELECT 
    pg_stat_activity.pid,
    pg_stat_activity.usename,
    pg_stat_activity.query_start,
    EXTRACT(EPOCH FROM (NOW() - pg_stat_activity.query_start)) as query_duration_seconds,
    pg_locks.locktype,
    pg_locks.database,
    pg_locks.relation,
    pg_class.relname,
    pg_locks.page,
    pg_locks.tuple,
    pg_locks.virtualxid,
    pg_locks.transactionid,
    pg_locks.mode,
    pg_locks.granted,
    LEFT(pg_stat_activity.query, 150) as query_snippet
FROM pg_locks
LEFT JOIN pg_stat_activity ON pg_locks.pid = pg_stat_activity.pid
LEFT JOIN pg_class ON pg_locks.relation = pg_class.oid
WHERE NOT pg_locks.granted
ORDER BY query_duration_seconds DESC;

-- Lock wait analysis
CREATE OR REPLACE VIEW monitoring.v_lock_waits AS
WITH lock_waits AS (
    SELECT 
        waiting.locktype,
        waiting.database,
        waiting.relation,
        waiting.page,
        waiting.tuple,
        waiting.virtualxid,
        waiting.transactionid,
        waiting.mode as waiting_mode,
        waiting.pid as waiting_pid,
        other.mode as other_mode,
        other.pid as other_pid,
        other.granted as other_granted
    FROM pg_locks waiting
    JOIN pg_locks other ON (
        waiting.database = other.database AND
        waiting.relation = other.relation AND
        waiting.page = other.page AND
        waiting.tuple = other.tuple AND
        waiting.virtualxid = other.virtualxid AND
        waiting.transactionid = other.transactionid
    )
    WHERE NOT waiting.granted AND other.granted
)
SELECT 
    lw.*,
    wa.usename as waiting_user,
    wa.query as waiting_query,
    wa.query_start as waiting_query_start,
    oa.usename as other_user,
    oa.query as other_query,
    oa.query_start as other_query_start,
    EXTRACT(EPOCH FROM (NOW() - wa.query_start)) as waiting_duration_seconds
FROM lock_waits lw
JOIN pg_stat_activity wa ON lw.waiting_pid = wa.pid
JOIN pg_stat_activity oa ON lw.other_pid = oa.pid
ORDER BY waiting_duration_seconds DESC;
```

### 2.5 Disk Usage and Growth Monitoring

```sql
-- Disk usage monitoring view
CREATE OR REPLACE VIEW monitoring.v_disk_usage AS
SELECT 
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as total_size,
    pg_size_pretty(pg_relation_size(schemaname||'.'||tablename)) as table_size,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename) - pg_relation_size(schemaname||'.'||tablename)) as index_size,
    ROUND(pg_total_relation_size(schemaname||'.'||tablename) / 1024.0 / 1024.0, 2) as total_size_mb,
    n_tup_ins + n_tup_upd + n_tup_del as total_modifications,
    n_live_tup,
    n_dead_tup,
    ROUND(n_dead_tup * 100.0 / GREATEST(n_live_tup + n_dead_tup, 1), 2) as dead_tuple_ratio,
    last_vacuum,
    last_autovacuum,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

-- Database growth tracking
CREATE OR REPLACE VIEW monitoring.v_database_growth AS
SELECT 
    current_database() as database_name,
    pg_size_pretty(pg_database_size(current_database())) as current_size,
    ROUND(pg_database_size(current_database()) / 1024.0 / 1024.0, 2) as current_size_mb,
    -- Growth calculation would require historical data
    NOW() as measured_at;

-- Index usage and bloat
CREATE OR REPLACE VIEW monitoring.v_index_analysis AS
SELECT 
    schemaname,
    tablename,
    indexname,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch,
    pg_size_pretty(pg_relation_size(schemaname||'.'||indexname)) as index_size,
    ROUND(pg_relation_size(schemaname||'.'||indexname) / 1024.0 / 1024.0, 2) as index_size_mb,
    CASE 
        WHEN idx_scan = 0 THEN 'UNUSED'
        WHEN idx_scan < 100 THEN 'LOW_USAGE'
        WHEN idx_scan < 1000 THEN 'MEDIUM_USAGE'
        ELSE 'HIGH_USAGE'
    END as usage_category,
    ROUND(100.0 * idx_tup_read / GREATEST(idx_tup_fetch, 1), 2) as selectivity_ratio
FROM pg_stat_user_indexes
ORDER BY pg_relation_size(schemaname||'.'||indexname) DESC;
```

### 2.6 Long-Running Transaction Detection

```sql
-- Long-running transactions view
CREATE OR REPLACE VIEW monitoring.v_long_running_transactions AS
SELECT 
    pid,
    usename,
    datname,
    application_name,
    client_addr,
    backend_start,
    xact_start,
    query_start,
    state_change,
    state,
    EXTRACT(EPOCH FROM (NOW() - xact_start)) as transaction_duration_seconds,
    EXTRACT(EPOCH FROM (NOW() - query_start)) as query_duration_seconds,
    wait_event_type,
    wait_event,
    LEFT(query, 200) as query_snippet,
    CASE 
        WHEN EXTRACT(EPOCH FROM (NOW() - xact_start)) > 3600 THEN 'CRITICAL'
        WHEN EXTRACT(EPOCH FROM (NOW() - xact_start)) > 600 THEN 'WARNING'
        ELSE 'NORMAL'
    END as severity_level
FROM pg_stat_activity 
WHERE xact_start IS NOT NULL
AND datname = current_database()
AND EXTRACT(EPOCH FROM (NOW() - xact_start)) > 60  -- Transactions longer than 1 minute
ORDER BY transaction_duration_seconds DESC;

-- Idle in transaction monitoring
CREATE OR REPLACE VIEW monitoring.v_idle_in_transaction AS
SELECT 
    pid,
    usename,
    datname,
    application_name,
    client_addr,
    state,
    EXTRACT(EPOCH FROM (NOW() - state_change)) as idle_duration_seconds,
    EXTRACT(EPOCH FROM (NOW() - query_start)) as since_last_query_seconds,
    LEFT(query, 200) as last_query,
    backend_start,
    query_start,
    state_change
FROM pg_stat_activity 
WHERE state = 'idle in transaction'
AND datname = current_database()
AND EXTRACT(EPOCH FROM (NOW() - state_change)) > 300  -- Idle for more than 5 minutes
ORDER BY idle_duration_seconds DESC;
```

## 3. Custom Monitoring Functions

### 3.1 Health Check Function

```sql
-- Comprehensive health check function
CREATE OR REPLACE FUNCTION monitoring.health_check()
RETURNS TABLE(
    check_name TEXT,
    status TEXT,
    value DECIMAL,
    threshold DECIMAL,
    message TEXT,
    severity TEXT
) AS $$
DECLARE
    rec RECORD;
    connection_pct DECIMAL;
    cache_hit_pct DECIMAL;
    long_queries INTEGER;
    lock_waits INTEGER;
    disk_usage_pct DECIMAL;
BEGIN
    -- Connection usage check
    SELECT COUNT(*)::DECIMAL * 100.0 / (SELECT setting::DECIMAL FROM pg_settings WHERE name = 'max_connections')
    INTO connection_pct
    FROM pg_stat_activity WHERE datname = current_database();
    
    RETURN QUERY SELECT 
        'connection_usage'::TEXT,
        CASE WHEN connection_pct >= 90 THEN 'CRITICAL'
             WHEN connection_pct >= 80 THEN 'WARNING'
             ELSE 'OK' END,
        connection_pct,
        80.0::DECIMAL,
        'Connection pool usage: ' || ROUND(connection_pct, 2) || '%',
        CASE WHEN connection_pct >= 90 THEN 'CRITICAL'
             WHEN connection_pct >= 80 THEN 'WARNING'
             ELSE 'INFO' END;
    
    -- Cache hit ratio check
    SELECT ROUND(sum(blks_hit)*100.0/sum(blks_hit+blks_read), 2)
    INTO cache_hit_pct
    FROM pg_stat_database WHERE datname = current_database();
    
    RETURN QUERY SELECT 
        'cache_hit_ratio'::TEXT,
        CASE WHEN cache_hit_pct < 90 THEN 'CRITICAL'
             WHEN cache_hit_pct < 95 THEN 'WARNING'
             ELSE 'OK' END,
        cache_hit_pct,
        95.0::DECIMAL,
        'Buffer cache hit ratio: ' || ROUND(cache_hit_pct, 2) || '%',
        CASE WHEN cache_hit_pct < 90 THEN 'CRITICAL'
             WHEN cache_hit_pct < 95 THEN 'WARNING'
             ELSE 'INFO' END;
    
    -- Long-running queries check
    SELECT COUNT(*)::INTEGER
    INTO long_queries
    FROM pg_stat_activity 
    WHERE state = 'active' 
    AND datname = current_database()
    AND EXTRACT(EPOCH FROM (NOW() - query_start)) > 300;  -- 5 minutes
    
    RETURN QUERY SELECT 
        'long_running_queries'::TEXT,
        CASE WHEN long_queries > 5 THEN 'CRITICAL'
             WHEN long_queries > 0 THEN 'WARNING'
             ELSE 'OK' END,
        long_queries::DECIMAL,
        0::DECIMAL,
        'Long-running queries (>5min): ' || long_queries,
        CASE WHEN long_queries > 5 THEN 'CRITICAL'
             WHEN long_queries > 0 THEN 'WARNING'
             ELSE 'INFO' END;
    
    -- Lock waits check
    SELECT COUNT(*)::INTEGER
    INTO lock_waits
    FROM pg_locks WHERE NOT granted;
    
    RETURN QUERY SELECT 
        'lock_waits'::TEXT,
        CASE WHEN lock_waits > 10 THEN 'CRITICAL'
             WHEN lock_waits > 0 THEN 'WARNING'
             ELSE 'OK' END,
        lock_waits::DECIMAL,
        0::DECIMAL,
        'Lock waits: ' || lock_waits,
        CASE WHEN lock_waits > 10 THEN 'CRITICAL'
             WHEN lock_waits > 0 THEN 'WARNING'
             ELSE 'INFO' END;
    
    RETURN;
END;
$$ LANGUAGE plpgsql;
```

### 3.2 Gaming Metrics Function

```sql
-- Gaming-specific metrics function
CREATE OR REPLACE FUNCTION monitoring.gaming_metrics()
RETURNS TABLE(
    metric_name TEXT,
    metric_value DECIMAL,
    metric_unit TEXT,
    metric_description TEXT,
    measured_at TIMESTAMP
) AS $$
BEGIN
    -- Active games count
    RETURN QUERY 
    SELECT 
        'active_games'::TEXT,
        COUNT(*)::DECIMAL,
        'games'::TEXT,
        'Number of active games'::TEXT,
        NOW()
    FROM game_sessions WHERE status IN ('waiting', 'active', 'in_progress');
    
    -- Online players count
    RETURN QUERY 
    SELECT 
        'online_players'::TEXT,
        COUNT(DISTINCT player_id)::DECIMAL,
        'players'::TEXT,
        'Number of online players'::TEXT,
        NOW()
    FROM websocket_connections WHERE status = 'active';
    
    -- Games created in last hour
    RETURN QUERY 
    SELECT 
        'games_per_hour'::TEXT,
        COUNT(*)::DECIMAL,
        'games/hour'::TEXT,
        'Games created in the last hour'::TEXT,
        NOW()
    FROM game_sessions WHERE created_at > NOW() - INTERVAL '1 hour';
    
    -- Average game duration
    RETURN QUERY 
    SELECT 
        'avg_game_duration'::TEXT,
        COALESCE(ROUND(AVG(EXTRACT(EPOCH FROM (completed_at - created_at))/60), 2), 0),
        'minutes'::TEXT,
        'Average game duration'::TEXT,
        NOW()
    FROM game_sessions 
    WHERE status = 'completed' 
    AND completed_at > NOW() - INTERVAL '24 hours';
    
    -- Move rate (moves per minute)
    RETURN QUERY 
    SELECT 
        'moves_per_minute'::TEXT,
        COALESCE(ROUND(COUNT(*) / GREATEST(EXTRACT(EPOCH FROM (MAX(timestamp) - MIN(timestamp))) / 60, 1), 2), 0),
        'moves/min'::TEXT,
        'Game moves per minute'::TEXT,
        NOW()
    FROM game_moves WHERE timestamp > NOW() - INTERVAL '1 hour';
    
    RETURN;
END;
$$ LANGUAGE plpgsql;
```

### 3.3 Alert Generation Function

```sql
-- Alert generation and management function
CREATE OR REPLACE FUNCTION monitoring.generate_alerts()
RETURNS TABLE(
    alert_id INTEGER,
    metric_name TEXT,
    alert_level TEXT,
    alert_message TEXT,
    metric_value DECIMAL,
    threshold_value DECIMAL
) AS $$
DECLARE
    health_rec RECORD;
    config_rec RECORD;
    existing_alert_id INTEGER;
BEGIN
    -- Check all health metrics against thresholds
    FOR health_rec IN SELECT * FROM monitoring.health_check() LOOP
        -- Get configuration for this metric
        SELECT * INTO config_rec 
        FROM monitoring.config 
        WHERE metric_name = health_rec.check_name AND enabled = true;
        
        IF FOUND THEN
            -- Check if alert should be generated
            IF (health_rec.status = 'WARNING' AND health_rec.value >= config_rec.threshold_warning) OR
               (health_rec.status = 'CRITICAL' AND health_rec.value >= config_rec.threshold_critical) THEN
                
                -- Check if alert already exists
                SELECT id INTO existing_alert_id
                FROM monitoring.alerts
                WHERE metric_name = health_rec.check_name
                AND alert_level = health_rec.status
                AND resolved_at IS NULL
                AND created_at > NOW() - INTERVAL '1 hour';  -- Don't duplicate recent alerts
                
                -- Create new alert if none exists
                IF NOT FOUND THEN
                    INSERT INTO monitoring.alerts (metric_name, alert_level, alert_message, metric_value, threshold_value)
                    VALUES (
                        health_rec.check_name,
                        health_rec.status,
                        health_rec.message,
                        health_rec.value,
                        CASE WHEN health_rec.status = 'CRITICAL' THEN config_rec.threshold_critical 
                             ELSE config_rec.threshold_warning END
                    )
                    RETURNING id INTO existing_alert_id;
                END IF;
                
                RETURN QUERY SELECT 
                    existing_alert_id,
                    health_rec.check_name,
                    health_rec.status,
                    health_rec.message,
                    health_rec.value,
                    CASE WHEN health_rec.status = 'CRITICAL' THEN config_rec.threshold_critical 
                         ELSE config_rec.threshold_warning END;
            END IF;
        END IF;
    END LOOP;
    
    RETURN;
END;
$$ LANGUAGE plpgsql;
```

## 4. Monitoring Data Collection

### 4.1 Metrics Collection Function

```sql
-- Metrics collection and storage function
CREATE OR REPLACE FUNCTION monitoring.collect_metrics()
RETURNS VOID AS $$
BEGIN
    -- Collect database health metrics
    INSERT INTO monitoring.metrics_history (metric_name, metric_value, metric_labels, recorded_at)
    SELECT 
        metric_name,
        numeric_value,
        jsonb_build_object('unit', unit, 'display_value', display_value),
        measured_at
    FROM monitoring.v_database_health;
    
    -- Collect gaming metrics
    INSERT INTO monitoring.metrics_history (metric_name, metric_value, metric_labels, recorded_at)
    SELECT 
        metric_name,
        metric_value,
        jsonb_build_object('unit', metric_unit, 'description', metric_description),
        measured_at
    FROM monitoring.gaming_metrics();
    
    -- Collect query performance metrics
    INSERT INTO monitoring.metrics_history (metric_name, metric_value, metric_labels, recorded_at)
    SELECT 
        'query_' || operation_type,
        avg_response_time_ms,
        jsonb_build_object(
            'query_count', query_count,
            'total_calls', total_calls,
            'cache_hit_ratio', avg_cache_hit_ratio
        ),
        NOW()
    FROM monitoring.v_gaming_query_performance;
    
    -- Clean up old metrics (keep last 7 days)
    DELETE FROM monitoring.metrics_history 
    WHERE recorded_at < NOW() - INTERVAL '7 days';
    
    -- Generate alerts
    PERFORM monitoring.generate_alerts();
    
END;
$$ LANGUAGE plpgsql;
```

### 4.2 Automated Collection Setup

```sql
-- Create function to set up automated monitoring
CREATE OR REPLACE FUNCTION monitoring.setup_automated_collection()
RETURNS VOID AS $$
BEGIN
    -- Note: This would typically be done via cron or pg_cron extension
    -- For demonstration, we'll show the commands that would be scheduled
    
    RAISE NOTICE 'To set up automated monitoring, add these to your cron or pg_cron:';
    RAISE NOTICE '# Every minute - collect basic metrics';
    RAISE NOTICE 'SELECT monitoring.collect_metrics();';
    RAISE NOTICE '# Every 5 minutes - detailed health check';
    RAISE NOTICE 'SELECT monitoring.generate_alerts();';
    RAISE NOTICE '# Every hour - cleanup and maintenance';
    RAISE NOTICE 'VACUUM monitoring.metrics_history;';
    RAISE NOTICE 'ANALYZE monitoring.metrics_history;';
END;
$$ LANGUAGE plpgsql;

-- If pg_cron is available, uncomment these:
-- SELECT cron.schedule('collect-metrics', '* * * * *', 'SELECT monitoring.collect_metrics();');
-- SELECT cron.schedule('cleanup-monitoring', '0 * * * *', 'VACUUM monitoring.metrics_history; ANALYZE monitoring.metrics_history;');
```

## 5. Prometheus Integration

### 5.1 Prometheus Exporter Queries

```sql
-- Create view for Prometheus postgres_exporter
CREATE OR REPLACE VIEW monitoring.prometheus_metrics AS
SELECT 
    'postgresql_database_size_bytes' as metric_name,
    pg_database_size(current_database()) as metric_value,
    jsonb_build_object('database', current_database()) as labels
UNION ALL
SELECT 
    'postgresql_connections_total',
    COUNT(*)::DECIMAL,
    jsonb_build_object('database', current_database(), 'state', COALESCE(state, 'unknown'))
FROM pg_stat_activity 
WHERE datname = current_database()
GROUP BY state
UNION ALL
SELECT 
    'postgresql_cache_hit_ratio',
    ROUND(sum(blks_hit)*100.0/sum(blks_hit+blks_read), 2),
    jsonb_build_object('database', current_database())
FROM pg_stat_database WHERE datname = current_database()
UNION ALL
SELECT 
    'postgresql_gaming_active_games',
    COUNT(*)::DECIMAL,
    jsonb_build_object('database', current_database())
FROM game_sessions WHERE status IN ('waiting', 'active', 'in_progress')
UNION ALL
SELECT 
    'postgresql_gaming_online_players',
    COUNT(DISTINCT player_id)::DECIMAL,
    jsonb_build_object('database', current_database())
FROM websocket_connections WHERE status = 'active';
```

## Summary

This comprehensive monitoring setup provides:

1. **Real-time Health Monitoring**: Database health, connections, cache performance
2. **Gaming-Specific Metrics**: Active games, player counts, move rates
3. **Performance Tracking**: Query performance, slow query detection
4. **Proactive Alerting**: Threshold-based alerts with severity levels
5. **Capacity Planning**: Growth tracking, resource utilization
6. **Prometheus Integration**: Metrics export for external monitoring systems

The monitoring system is designed to provide early warning of potential issues and support capacity planning for your Hokm game server's PostgreSQL database.
