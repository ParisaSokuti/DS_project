#!/bin/bash

# PostgreSQL Comprehensive Monitoring Setup Script
# Implements complete monitoring for Hokm game server database

set -euo pipefail

# Configuration
PGHOST="${PGHOST:-postgresql-primary}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-postgres}"
PGDATABASE="${PGDATABASE:-hokm_game}"
MONITORING_MODE="${1:-setup}"  # setup, collect, report, alert
LOG_FILE="/var/log/postgresql-monitoring-setup.log"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m'

log() {
    echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

success() {
    log "${GREEN}✓ $*${NC}"
}

warning() {
    log "${YELLOW}⚠ $*${NC}"
}

error() {
    log "${RED}✗ $*${NC}"
}

info() {
    log "${BLUE}ℹ $*${NC}"
}

highlight() {
    log "${CYAN}🔍 $*${NC}"
}

monitor() {
    log "${MAGENTA}📊 $*${NC}"
}

# Execute SQL with error handling
execute_sql() {
    local sql="$1"
    local description="$2"
    
    info "Executing: $description"
    
    if psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -c "$sql" >> "$LOG_FILE" 2>&1; then
        success "$description completed"
        return 0
    else
        error "$description failed"
        return 1
    fi
}

# Execute SQL and return result
execute_query() {
    local query="$1"
    psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -t -c "$query" 2>/dev/null | xargs
}

# Setup monitoring infrastructure
setup_monitoring() {
    highlight "SETTING UP POSTGRESQL MONITORING INFRASTRUCTURE"
    echo "======================================================"
    
    # Enable required extensions
    info "Enabling monitoring extensions..."
    execute_sql "CREATE EXTENSION IF NOT EXISTS pg_stat_statements;" "Enable pg_stat_statements"
    execute_sql "CREATE EXTENSION IF NOT EXISTS pg_buffercache;" "Enable pg_buffercache"
    
    # Configure monitoring settings
    info "Configuring monitoring parameters..."
    execute_sql "ALTER SYSTEM SET pg_stat_statements.max = 10000;" "Set pg_stat_statements max queries"
    execute_sql "ALTER SYSTEM SET pg_stat_statements.track = 'all';" "Enable all query tracking"
    execute_sql "ALTER SYSTEM SET pg_stat_statements.track_utility = 'on';" "Enable utility statement tracking"
    execute_sql "ALTER SYSTEM SET pg_stat_statements.save = 'on';" "Enable query statistics persistence"
    
    # Configure logging for monitoring
    execute_sql "ALTER SYSTEM SET log_min_duration_statement = 1000;" "Log slow queries (>1s)"
    execute_sql "ALTER SYSTEM SET log_checkpoints = 'on';" "Enable checkpoint logging"
    execute_sql "ALTER SYSTEM SET log_lock_waits = 'on';" "Enable lock wait logging"
    execute_sql "ALTER SYSTEM SET log_temp_files = 0;" "Log temporary file creation"
    execute_sql "ALTER SYSTEM SET log_autovacuum_min_duration = 0;" "Log autovacuum activity"
    
    # Reload configuration
    execute_sql "SELECT pg_reload_conf();" "Reload PostgreSQL configuration"
    
    # Create monitoring schema and tables
    info "Creating monitoring schema..."
    
    cat << 'EOF' | psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" >> "$LOG_FILE" 2>&1
-- Create monitoring schema
CREATE SCHEMA IF NOT EXISTS monitoring;

-- Monitoring configuration table
CREATE TABLE IF NOT EXISTS monitoring.config (
    metric_name VARCHAR(100) PRIMARY KEY,
    enabled BOOLEAN DEFAULT true,
    threshold_warning DECIMAL,
    threshold_critical DECIMAL,
    check_interval_seconds INTEGER DEFAULT 60,
    description TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Monitoring history table
CREATE TABLE IF NOT EXISTS monitoring.metrics_history (
    id SERIAL PRIMARY KEY,
    metric_name VARCHAR(100) NOT NULL,
    metric_value DECIMAL NOT NULL,
    metric_labels JSONB,
    recorded_at TIMESTAMP DEFAULT NOW()
);

-- Alerts table
CREATE TABLE IF NOT EXISTS monitoring.alerts (
    id SERIAL PRIMARY KEY,
    metric_name VARCHAR(100) NOT NULL,
    alert_level VARCHAR(20) NOT NULL,
    alert_message TEXT NOT NULL,
    metric_value DECIMAL NOT NULL,
    threshold_value DECIMAL NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    resolved_at TIMESTAMP,
    acknowledged_at TIMESTAMP,
    acknowledged_by VARCHAR(100)
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_metrics_history_name_time ON monitoring.metrics_history(metric_name, recorded_at);
CREATE INDEX IF NOT EXISTS idx_metrics_history_labels ON monitoring.metrics_history USING GIN(metric_labels);
CREATE INDEX IF NOT EXISTS idx_alerts_unresolved ON monitoring.alerts(created_at) WHERE resolved_at IS NULL;
EOF
    
    success "Monitoring schema created"
    
    # Insert monitoring configuration
    info "Configuring monitoring thresholds..."
    
    cat << 'EOF' | psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" >> "$LOG_FILE" 2>&1
INSERT INTO monitoring.config (metric_name, threshold_warning, threshold_critical, description) VALUES
('connection_usage_percent', 80.0, 90.0, 'Connection pool usage percentage'),
('cache_hit_ratio_percent', 95.0, 90.0, 'Buffer cache hit ratio'),
('disk_usage_percent', 80.0, 90.0, 'Disk space usage percentage'),
('long_running_queries_minutes', 5.0, 10.0, 'Long-running query duration'),
('lock_wait_seconds', 30.0, 60.0, 'Lock wait time threshold'),
('avg_query_time_ms', 100.0, 500.0, 'Average query execution time'),
('replication_lag_mb', 100.0, 500.0, 'Replication lag in megabytes'),
('dead_tuple_ratio_percent', 20.0, 30.0, 'Dead tuple ratio threshold'),
('temp_file_size_mb', 100.0, 500.0, 'Temporary file size threshold'),
('active_games_count', 1.0, 0.0, 'Minimum active games threshold'),
('online_players_count', 1.0, 0.0, 'Minimum online players threshold'),
('moves_per_minute', 10.0, 5.0, 'Minimum moves per minute threshold')
ON CONFLICT (metric_name) DO UPDATE SET
    threshold_warning = EXCLUDED.threshold_warning,
    threshold_critical = EXCLUDED.threshold_critical,
    description = EXCLUDED.description,
    updated_at = NOW();
EOF
    
    success "Monitoring thresholds configured"
    
    # Create monitoring views and functions
    create_monitoring_views
    create_monitoring_functions
    
    success "Monitoring infrastructure setup completed"
}

# Create monitoring views
create_monitoring_views() {
    info "Creating monitoring views..."
    
    cat << 'EOF' | psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" >> "$LOG_FILE" 2>&1
-- Database health overview view
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

-- Query performance view
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

-- Gaming query performance view
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
    pg_locks.mode,
    pg_locks.granted,
    LEFT(pg_stat_activity.query, 150) as query_snippet
FROM pg_locks
LEFT JOIN pg_stat_activity ON pg_locks.pid = pg_stat_activity.pid
LEFT JOIN pg_class ON pg_locks.relation = pg_class.oid
WHERE NOT pg_locks.granted
ORDER BY query_duration_seconds DESC;

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
AND EXTRACT(EPOCH FROM (NOW() - xact_start)) > 60
ORDER BY transaction_duration_seconds DESC;

-- Disk usage view
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
EOF
    
    success "Monitoring views created"
}

# Create monitoring functions
create_monitoring_functions() {
    info "Creating monitoring functions..."
    
    cat << 'EOF' | psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" >> "$LOG_FILE" 2>&1
-- Health check function
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
    connection_pct DECIMAL;
    cache_hit_pct DECIMAL;
    long_queries INTEGER;
    lock_waits INTEGER;
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
    AND EXTRACT(EPOCH FROM (NOW() - query_start)) > 300;
    
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

-- Gaming metrics function
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
        COALESCE(COUNT(*)::DECIMAL, 0),
        'games'::TEXT,
        'Number of active games'::TEXT,
        NOW()
    FROM game_sessions WHERE status IN ('waiting', 'active', 'in_progress');
    
    -- Online players count
    RETURN QUERY 
    SELECT 
        'online_players'::TEXT,
        COALESCE(COUNT(DISTINCT player_id)::DECIMAL, 0),
        'players'::TEXT,
        'Number of online players'::TEXT,
        NOW()
    FROM websocket_connections WHERE status = 'active';
    
    -- Games created in last hour
    RETURN QUERY 
    SELECT 
        'games_per_hour'::TEXT,
        COALESCE(COUNT(*)::DECIMAL, 0),
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

-- Metrics collection function
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
    
END;
$$ LANGUAGE plpgsql;

-- Alert generation function
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
                AND created_at > NOW() - INTERVAL '1 hour';
                
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
EOF
    
    success "Monitoring functions created"
}

# Collect metrics
collect_metrics() {
    highlight "COLLECTING POSTGRESQL METRICS"
    echo "================================"
    
    info "Running metrics collection..."
    execute_sql "SELECT monitoring.collect_metrics();" "Collect all metrics"
    
    info "Checking for alerts..."
    psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -c "
    SELECT * FROM monitoring.generate_alerts();
    " 2>/dev/null
    
    success "Metrics collection completed"
}

# Generate monitoring report
generate_report() {
    highlight "GENERATING MONITORING REPORT"
    echo "=============================="
    
    local report_file="/tmp/postgresql-monitoring-report-$(date +%Y%m%d-%H%M%S).html"
    
    info "Generating monitoring report: $report_file"
    
    cat << EOF > "$report_file"
<!DOCTYPE html>
<html>
<head>
    <title>PostgreSQL Gaming Database Monitoring Report</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }
        .container { max-width: 1200px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        .header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 5px; margin-bottom: 20px; }
        .metric-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; margin: 20px 0; }
        .metric-card { background: #f8f9fa; border: 1px solid #e9ecef; border-radius: 5px; padding: 15px; }
        .metric-title { font-weight: bold; color: #495057; margin-bottom: 10px; }
        .metric-value { font-size: 24px; font-weight: bold; margin-bottom: 5px; }
        .metric-desc { color: #6c757d; font-size: 14px; }
        .status-ok { color: #28a745; }
        .status-warning { color: #ffc107; }
        .status-critical { color: #dc3545; }
        .alert-section { background: #fff3cd; border: 1px solid #ffeaa7; border-radius: 5px; padding: 15px; margin: 20px 0; }
        .alert-critical { background: #f8d7da; border-color: #f5c6cb; }
        table { width: 100%; border-collapse: collapse; margin: 10px 0; }
        th, td { border: 1px solid #dee2e6; padding: 8px; text-align: left; }
        th { background-color: #e9ecef; font-weight: bold; }
        .section { margin: 30px 0; }
        .section-title { background: #e9ecef; padding: 10px; border-radius: 5px; font-weight: bold; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🎮 PostgreSQL Gaming Database Monitoring Report</h1>
            <p><strong>Generated:</strong> $(date)</p>
            <p><strong>Database:</strong> $PGDATABASE@$PGHOST:$PGPORT</p>
        </div>

        <div class="section">
            <div class="section-title">📊 Database Health Overview</div>
            <div class="metric-grid">
EOF
    
    # Add database health metrics
    psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -t -c "
    SELECT 
        '<div class=\"metric-card\">',
        '<div class=\"metric-title\">' || metric_name || '</div>',
        '<div class=\"metric-value\">' || display_value || '</div>',
        '<div class=\"metric-desc\">Current value</div>',
        '</div>'
    FROM monitoring.v_database_health;
    " 2>/dev/null | sed 's/|//g' >> "$report_file"
    
    cat << EOF >> "$report_file"
            </div>
        </div>

        <div class="section">
            <div class="section-title">🎮 Gaming Metrics</div>
            <div class="metric-grid">
EOF
    
    # Add gaming metrics
    psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -t -c "
    SELECT 
        '<div class=\"metric-card\">',
        '<div class=\"metric-title\">' || metric_description || '</div>',
        '<div class=\"metric-value\">' || metric_value || ' ' || metric_unit || '</div>',
        '<div class=\"metric-desc\">As of ' || measured_at || '</div>',
        '</div>'
    FROM monitoring.gaming_metrics();
    " 2>/dev/null | sed 's/|//g' >> "$report_file"
    
    cat << EOF >> "$report_file"
            </div>
        </div>

        <div class="section">
            <div class="section-title">🚨 Current Alerts</div>
EOF
    
    # Add alerts
    local alert_count=$(execute_query "SELECT COUNT(*) FROM monitoring.alerts WHERE resolved_at IS NULL")
    
    if [[ "$alert_count" -gt 0 ]]; then
        cat << EOF >> "$report_file"
            <table>
                <tr>
                    <th>Metric</th>
                    <th>Level</th>
                    <th>Message</th>
                    <th>Value</th>
                    <th>Threshold</th>
                    <th>Created</th>
                </tr>
EOF
        
        psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -t -c "
        SELECT 
            '<tr>',
            '<td>' || metric_name || '</td>',
            '<td class=\"status-' || LOWER(alert_level) || '\">' || alert_level || '</td>',
            '<td>' || alert_message || '</td>',
            '<td>' || metric_value || '</td>',
            '<td>' || threshold_value || '</td>',
            '<td>' || created_at || '</td>',
            '</tr>'
        FROM monitoring.alerts 
        WHERE resolved_at IS NULL 
        ORDER BY created_at DESC;
        " 2>/dev/null | sed 's/|//g' >> "$report_file"
        
        echo "</table>" >> "$report_file"
    else
        echo "<p class=\"status-ok\">✓ No active alerts</p>" >> "$report_file"
    fi
    
    cat << EOF >> "$report_file"
        </div>

        <div class="section">
            <div class="section-title">⚡ Query Performance (Top 10 by Average Time)</div>
            <table>
                <tr>
                    <th>Operation Type</th>
                    <th>Query Count</th>
                    <th>Avg Time (ms)</th>
                    <th>Max Time (ms)</th>
                    <th>Total Calls</th>
                    <th>Cache Hit %</th>
                </tr>
EOF
    
    psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -t -c "
    SELECT 
        '<tr>',
        '<td>' || operation_type || '</td>',
        '<td>' || query_count || '</td>',
        '<td>' || avg_response_time_ms || '</td>',
        '<td>' || max_response_time_ms || '</td>',
        '<td>' || total_calls || '</td>',
        '<td>' || COALESCE(avg_cache_hit_ratio::text, 'N/A') || '</td>',
        '</tr>'
    FROM monitoring.v_gaming_query_performance 
    LIMIT 10;
    " 2>/dev/null | sed 's/|//g' >> "$report_file"
    
    cat << EOF >> "$report_file"
            </table>
        </div>

        <div class="section">
            <div class="section-title">🔒 Connection Pool Status</div>
            <table>
                <tr>
                    <th>Database</th>
                    <th>State</th>
                    <th>Count</th>
                    <th>Usage %</th>
                    <th>Longest Query (s)</th>
                    <th>Waiting</th>
                </tr>
EOF
    
    psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -t -c "
    SELECT 
        '<tr>',
        '<td>' || datname || '</td>',
        '<td>' || state || '</td>',
        '<td>' || connection_count || '</td>',
        '<td>' || usage_percent || '</td>',
        '<td>' || COALESCE(longest_query_seconds::text, 'N/A') || '</td>',
        '<td>' || waiting_connections || '</td>',
        '</tr>'
    FROM monitoring.v_connection_pool 
    WHERE datname = current_database();
    " 2>/dev/null | sed 's/|//g' >> "$report_file"
    
    cat << EOF >> "$report_file"
            </table>
        </div>

        <div class="section">
            <div class="section-title">📈 Recommendations</div>
            <ul>
                <li>Monitor connection pool usage and scale accordingly</li>
                <li>Review slow queries and optimize indexes</li>
                <li>Ensure cache hit ratio stays above 95%</li>
                <li>Monitor disk usage and plan for growth</li>
                <li>Set up automated alerting for critical thresholds</li>
                <li>Regular vacuum and maintenance scheduling</li>
            </ul>
        </div>

        <div class="section">
            <p><em>Report generated by PostgreSQL Gaming Monitor at $(date)</em></p>
            <p><em>Monitoring log: $LOG_FILE</em></p>
        </div>
    </div>
</body>
</html>
EOF
    
    success "Monitoring report generated: $report_file"
    info "Open the report in a web browser to view detailed results"
}

# Check and display alerts
check_alerts() {
    highlight "CHECKING FOR ALERTS"
    echo "==================="
    
    info "Running health checks..."
    psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -c "
    SELECT 
        check_name,
        status,
        value,
        threshold,
        message
    FROM monitoring.health_check()
    ORDER BY 
        CASE status 
            WHEN 'CRITICAL' THEN 1 
            WHEN 'WARNING' THEN 2 
            ELSE 3 
        END;
    " 2>/dev/null
    
    echo
    
    info "Current unresolved alerts:"
    local alert_count=$(execute_query "SELECT COUNT(*) FROM monitoring.alerts WHERE resolved_at IS NULL")
    
    if [[ "$alert_count" -gt 0 ]]; then
        psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -c "
        SELECT 
            metric_name,
            alert_level,
            alert_message,
            metric_value,
            created_at
        FROM monitoring.alerts 
        WHERE resolved_at IS NULL 
        ORDER BY created_at DESC;
        " 2>/dev/null
    else
        success "No active alerts found"
    fi
    
    echo
}

# Show help
show_help() {
    echo "PostgreSQL Comprehensive Monitoring Setup"
    echo
    echo "Usage: $0 [mode]"
    echo
    echo "Modes:"
    echo "  setup     Set up monitoring infrastructure (default)"
    echo "  collect   Collect metrics and generate alerts"
    echo "  report    Generate comprehensive monitoring report"
    echo "  alert     Check current alerts and health status"
    echo
    echo "Environment Variables:"
    echo "  PGHOST        PostgreSQL host (default: postgresql-primary)"
    echo "  PGPORT        PostgreSQL port (default: 5432)"
    echo "  PGUSER        PostgreSQL user (default: postgres)"
    echo "  PGDATABASE    PostgreSQL database (default: hokm_game)"
    echo
    echo "Examples:"
    echo "  $0 setup     # Set up monitoring infrastructure"
    echo "  $0 collect   # Collect metrics"
    echo "  $0 report    # Generate HTML report"
    echo "  $0 alert     # Check alerts"
    echo
}

# Main function
main() {
    case "$MONITORING_MODE" in
        "setup")
            setup_monitoring
            ;;
        "collect")
            collect_metrics
            ;;
        "report")
            generate_report
            ;;
        "alert")
            check_alerts
            ;;
        *)
            error "Unknown monitoring mode: $MONITORING_MODE"
            show_help
            exit 1
            ;;
    esac
}

# Check arguments
if [[ "${1:-}" == "--help" ]] || [[ "${1:-}" == "-h" ]]; then
    show_help
    exit 0
fi

# Check dependencies
if ! command -v psql &> /dev/null; then
    error "psql command not found. Please install PostgreSQL client."
    exit 1
fi

# Test database connection
if ! psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -c "SELECT 1;" > /dev/null 2>&1; then
    error "Cannot connect to PostgreSQL database"
    error "Check connection parameters: $PGUSER@$PGHOST:$PGPORT/$PGDATABASE"
    exit 1
fi

# Initialize log
log "Starting PostgreSQL Monitoring (mode: $MONITORING_MODE)"

# Run main function
main

success "PostgreSQL monitoring operation completed!"
