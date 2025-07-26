#!/bin/bash

# PostgreSQL Gaming Performance Optimization Script
# Automatically applies optimizations for Hokm game workloads

set -euo pipefail

# Configuration
PGHOST="${PGHOST:-postgresql-primary}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-postgres}"
PGDATABASE="${PGDATABASE:-hokm_game}"
LOG_FILE="/var/log/postgresql-optimization.log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

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

# Check if index exists
index_exists() {
    local index_name="$1"
    psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -tAc \
        "SELECT EXISTS(SELECT 1 FROM pg_indexes WHERE indexname = '$index_name');" 2>/dev/null | grep -q "t"
}

# Create gaming-optimized indexes
create_gaming_indexes() {
    info "Creating gaming-optimized indexes..."
    
    # Game Sessions Indexes
    if ! index_exists "idx_game_sessions_active_lookup"; then
        execute_sql "
        CREATE INDEX CONCURRENTLY idx_game_sessions_active_lookup 
        ON game_sessions (status, room_id) 
        WHERE status IN ('waiting', 'active', 'in_progress');
        " "Game sessions active lookup index"
    fi
    
    if ! index_exists "idx_game_sessions_player_active"; then
        execute_sql "
        CREATE INDEX CONCURRENTLY idx_game_sessions_player_active 
        ON game_sessions (player_id, status, created_at DESC) 
        WHERE status IN ('active', 'in_progress');
        " "Game sessions player active index"
    fi
    
    if ! index_exists "idx_game_sessions_recent"; then
        execute_sql "
        CREATE INDEX CONCURRENTLY idx_game_sessions_recent 
        ON game_sessions (created_at DESC, status) 
        WHERE created_at > NOW() - INTERVAL '24 hours';
        " "Game sessions recent index"
    fi
    
    # Game Participants Indexes
    if ! index_exists "idx_game_participants_room_player"; then
        execute_sql "
        CREATE INDEX CONCURRENTLY idx_game_participants_room_player 
        ON game_participants (room_id, player_id) 
        INCLUDE (team, position, joined_at);
        " "Game participants room-player index"
    fi
    
    # Game Moves Indexes
    if ! index_exists "idx_game_moves_game_sequence"; then
        execute_sql "
        CREATE INDEX CONCURRENTLY idx_game_moves_game_sequence 
        ON game_moves (game_id, move_sequence) 
        INCLUDE (player_id, move_type, move_data);
        " "Game moves sequence index"
    fi
    
    if ! index_exists "idx_game_moves_recent_by_game"; then
        execute_sql "
        CREATE INDEX CONCURRENTLY idx_game_moves_recent_by_game 
        ON game_moves (game_id, created_at DESC) 
        WHERE created_at > NOW() - INTERVAL '6 hours';
        " "Game moves recent index"
    fi
    
    # Player Statistics Indexes
    if ! index_exists "idx_player_stats_ranking"; then
        execute_sql "
        CREATE INDEX CONCURRENTLY idx_player_stats_ranking 
        ON player_stats (total_score DESC, games_won DESC, games_played ASC) 
        WHERE active = true;
        " "Player statistics ranking index"
    fi
    
    # WebSocket Connections Indexes
    if ! index_exists "idx_websocket_connections_active"; then
        execute_sql "
        CREATE INDEX CONCURRENTLY idx_websocket_connections_active 
        ON websocket_connections (connection_id, status) 
        WHERE status = 'active';
        " "WebSocket connections active index"
    fi
    
    success "Gaming indexes creation completed"
}

# Create materialized views
create_materialized_views() {
    info "Creating materialized views for performance..."
    
    # Player Leaderboard Materialized View
    execute_sql "
    DROP MATERIALIZED VIEW IF EXISTS mv_player_leaderboard CASCADE;
    
    CREATE MATERIALIZED VIEW mv_player_leaderboard AS
    WITH player_stats AS (
        SELECT 
            p.id,
            p.username,
            p.created_at as player_since,
            COUNT(gp.game_id) as games_played,
            COUNT(CASE WHEN gp.game_result = 'won' THEN 1 END) as games_won,
            COUNT(CASE WHEN gp.game_result = 'lost' THEN 1 END) as games_lost,
            COALESCE(AVG(gp.score), 0) as avg_score,
            COALESCE(MAX(gp.score), 0) as best_score,
            MAX(gs.created_at) as last_game_at,
            SUM(CASE WHEN gs.created_at > NOW() - INTERVAL '7 days' THEN 1 ELSE 0 END) as games_this_week,
            1500 + (COUNT(CASE WHEN gp.game_result = 'won' THEN 1 END) * 25) - 
                   (COUNT(CASE WHEN gp.game_result = 'lost' THEN 1 END) * 20) as rating
        FROM players p
        LEFT JOIN game_participants gp ON p.id = gp.player_id
        LEFT JOIN game_sessions gs ON gp.game_id = gs.id AND gs.status = 'completed'
        WHERE p.is_active = true
        GROUP BY p.id, p.username, p.created_at
        HAVING COUNT(gp.game_id) > 0
    ),
    ranked_stats AS (
        SELECT *,
               ROW_NUMBER() OVER (ORDER BY rating DESC, games_won DESC, avg_score DESC) as ranking,
               PERCENT_RANK() OVER (ORDER BY rating DESC) as percentile_rank
        FROM player_stats
    )
    SELECT * FROM ranked_stats;
    " "Player leaderboard materialized view"
    
    # Create indexes on materialized view
    execute_sql "
    CREATE UNIQUE INDEX idx_mv_leaderboard_ranking ON mv_player_leaderboard (ranking);
    CREATE INDEX idx_mv_leaderboard_username ON mv_player_leaderboard (username);
    CREATE INDEX idx_mv_leaderboard_rating ON mv_player_leaderboard (rating DESC);
    " "Leaderboard materialized view indexes"
    
    # Game Statistics Materialized View
    execute_sql "
    DROP MATERIALIZED VIEW IF EXISTS mv_game_statistics CASCADE;
    
    CREATE MATERIALIZED VIEW mv_game_statistics AS
    WITH daily_stats AS (
        SELECT 
            DATE(created_at) as game_date,
            COUNT(*) as total_games,
            COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed_games,
            COUNT(CASE WHEN status = 'abandoned' THEN 1 END) as abandoned_games,
            AVG(EXTRACT(EPOCH FROM (updated_at - created_at))/60) as avg_duration_minutes,
            COUNT(DISTINCT EXTRACT(HOUR FROM created_at)) as active_hours
        FROM game_sessions
        WHERE created_at >= CURRENT_DATE - INTERVAL '30 days'
        GROUP BY DATE(created_at)
    ),
    player_engagement AS (
        SELECT 
            DATE(gs.created_at) as game_date,
            COUNT(DISTINCT gp.player_id) as unique_players
        FROM game_sessions gs
        JOIN game_participants gp ON gs.id = gp.game_id
        WHERE gs.created_at >= CURRENT_DATE - INTERVAL '30 days'
        GROUP BY DATE(gs.created_at)
    )
    SELECT 
        ds.game_date,
        ds.total_games,
        ds.completed_games,
        ds.abandoned_games,
        ROUND(ds.avg_duration_minutes, 2) as avg_duration_minutes,
        ds.active_hours,
        pe.unique_players,
        ROUND((ds.completed_games::float / NULLIF(ds.total_games, 0)) * 100, 2) as completion_rate
    FROM daily_stats ds
    LEFT JOIN player_engagement pe ON ds.game_date = pe.game_date
    ORDER BY ds.game_date DESC;
    " "Game statistics materialized view"
    
    execute_sql "
    CREATE UNIQUE INDEX idx_mv_game_stats_date ON mv_game_statistics (game_date DESC);
    " "Game statistics materialized view index"
    
    success "Materialized views creation completed"
}

# Apply PostgreSQL configuration optimizations
apply_postgresql_config() {
    info "Applying PostgreSQL configuration optimizations..."
    
    # Gaming-optimized parameters
    local config_params=(
        "shared_buffers = '2GB'"
        "effective_cache_size = '6GB'"
        "work_mem = '32MB'"
        "maintenance_work_mem = '512MB'"
        "random_page_cost = 1.1"
        "effective_io_concurrency = 200"
        "default_statistics_target = 250"
        "checkpoint_completion_target = 0.8"
        "max_wal_size = '4GB'"
        "min_wal_size = '1GB'"
        "tcp_keepalives_idle = 300"
        "tcp_keepalives_interval = 30"
        "tcp_keepalives_count = 3"
        "synchronous_commit = off"
        "wal_writer_delay = '200ms'"
        "autovacuum_naptime = '30s'"
        "autovacuum_vacuum_scale_factor = 0.1"
        "autovacuum_analyze_scale_factor = 0.05"
        "log_min_duration_statement = 100"
        "track_io_timing = on"
        "track_functions = 'all'"
    )
    
    for param in "${config_params[@]}"; do
        if execute_sql "ALTER SYSTEM SET $param;" "Setting $param"; then
            success "Applied: $param"
        else
            warning "Failed to apply: $param"
        fi
    done
    
    # Reload configuration
    execute_sql "SELECT pg_reload_conf();" "Reloading PostgreSQL configuration"
    
    success "PostgreSQL configuration optimization completed"
}

# Create performance monitoring views
create_monitoring_views() {
    info "Creating performance monitoring views..."
    
    # Slow queries view
    execute_sql "
    CREATE OR REPLACE VIEW v_slow_queries AS
    SELECT 
        query,
        calls,
        total_exec_time,
        round(mean_exec_time::numeric, 2) as mean_exec_time_ms,
        round((100 * total_exec_time / sum(total_exec_time) OVER())::numeric, 2) as percentage_cpu,
        rows as total_rows,
        round((rows / calls)::numeric, 2) as rows_per_call
    FROM pg_stat_statements 
    WHERE calls > 100
    ORDER BY total_exec_time DESC
    LIMIT 20;
    " "Slow queries monitoring view"
    
    # Index usage view
    execute_sql "
    CREATE OR REPLACE VIEW v_index_usage AS
    SELECT 
        schemaname,
        tablename,
        indexname,
        idx_tup_read,
        idx_tup_fetch,
        pg_size_pretty(pg_relation_size(indexrelid)) as index_size,
        CASE 
            WHEN idx_tup_read = 0 THEN 'Unused'
            WHEN idx_tup_read < idx_tup_fetch THEN 'Low Selectivity'
            ELSE 'Good'
        END as index_efficiency
    FROM pg_stat_user_indexes
    ORDER BY idx_tup_read DESC;
    " "Index usage monitoring view"
    
    # Gaming performance metrics view
    execute_sql "
    CREATE OR REPLACE VIEW v_gaming_performance AS
    SELECT 
        'Active Games' as metric,
        COUNT(*) as value,
        'games' as unit
    FROM game_sessions 
    WHERE status IN ('active', 'in_progress')
    UNION ALL
    SELECT 
        'Games per Hour' as metric,
        COUNT(*)::float as value,
        'games/hour' as unit
    FROM game_sessions
    WHERE created_at > NOW() - INTERVAL '1 hour'
    UNION ALL
    SELECT 
        'Average Game Duration' as metric,
        AVG(EXTRACT(EPOCH FROM (completed_at - created_at))/60) as value,
        'minutes' as unit
    FROM game_sessions
    WHERE status = 'completed' 
    AND completed_at > NOW() - INTERVAL '24 hours'
    UNION ALL
    SELECT 
        'Active Players' as metric,
        COUNT(DISTINCT player_id) as value,
        'players' as unit
    FROM websocket_connections
    WHERE status = 'active'
    AND last_heartbeat > NOW() - INTERVAL '5 minutes';
    " "Gaming performance metrics view"
    
    success "Performance monitoring views created"
}

# Analyze and optimize existing queries
analyze_query_performance() {
    info "Analyzing query performance..."
    
    # Update table statistics
    execute_sql "ANALYZE;" "Updating table statistics"
    
    # Check for missing indexes
    execute_sql "
    SELECT 
        schemaname,
        tablename,
        seq_scan,
        seq_tup_read,
        idx_scan,
        idx_tup_fetch,
        CASE 
            WHEN seq_scan > idx_scan THEN 'Consider adding indexes'
            ELSE 'OK'
        END as recommendation
    FROM pg_stat_user_tables
    WHERE seq_scan > 1000
    ORDER BY seq_tup_read DESC;
    " "Checking for missing indexes"
    
    success "Query performance analysis completed"
}

# Set up automated maintenance
setup_automated_maintenance() {
    info "Setting up automated maintenance..."
    
    # Create maintenance functions
    execute_sql "
    CREATE OR REPLACE FUNCTION refresh_materialized_views()
    RETURNS void AS \$\$
    BEGIN
        -- Refresh leaderboard (most frequently accessed)
        REFRESH MATERIALIZED VIEW CONCURRENTLY mv_player_leaderboard;
        
        -- Refresh game statistics
        REFRESH MATERIALIZED VIEW CONCURRENTLY mv_game_statistics;
        
        -- Log the refresh
        INSERT INTO maintenance_log (operation, status, completed_at)
        VALUES ('materialized_view_refresh', 'completed', NOW());
    END;
    \$\$ LANGUAGE plpgsql;
    " "Materialized view refresh function"
    
    # Create vacuum monitoring function
    execute_sql "
    CREATE OR REPLACE FUNCTION gaming_vacuum_analysis()
    RETURNS TABLE(
        table_name text,
        dead_tuple_percent numeric,
        bloat_size text,
        recommendation text
    ) AS \$\$
    BEGIN
        RETURN QUERY
        SELECT 
            (schemaname || '.' || tablename)::text,
            CASE 
                WHEN n_live_tup > 0 
                THEN round((n_dead_tup::float / n_live_tup) * 100, 2)
                ELSE 0 
            END as dead_tuple_percent,
            pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as bloat_size,
            CASE 
                WHEN n_dead_tup::float / NULLIF(n_live_tup, 0) > 0.2 THEN 'VACUUM RECOMMENDED'
                WHEN n_dead_tup::float / NULLIF(n_live_tup, 0) > 0.1 THEN 'Monitor closely'
                ELSE 'OK'
            END::text as recommendation
        FROM pg_stat_user_tables
        WHERE n_live_tup > 1000
        ORDER BY (n_dead_tup::float / NULLIF(n_live_tup, 0)) DESC NULLS LAST;
    END;
    \$\$ LANGUAGE plpgsql;
    " "Gaming vacuum analysis function"
    
    # Create performance monitoring function
    execute_sql "
    CREATE OR REPLACE FUNCTION gaming_performance_report()
    RETURNS TABLE(
        metric_category text,
        metric_name text,
        current_value numeric,
        threshold_warning numeric,
        threshold_critical numeric,
        status text
    ) AS \$\$
    BEGIN
        RETURN QUERY
        -- Connection metrics
        SELECT 
            'Connections'::text,
            'Active Connections'::text,
            COUNT(*)::numeric,
            800::numeric,
            950::numeric,
            CASE 
                WHEN COUNT(*) > 950 THEN 'CRITICAL'
                WHEN COUNT(*) > 800 THEN 'WARNING'
                ELSE 'OK'
            END::text
        FROM pg_stat_activity
        WHERE state = 'active'
        
        UNION ALL
        
        -- Query performance
        SELECT 
            'Performance'::text,
            'Slow Queries (>100ms)'::text,
            COUNT(*)::numeric,
            50::numeric,
            100::numeric,
            CASE 
                WHEN COUNT(*) > 100 THEN 'CRITICAL'
                WHEN COUNT(*) > 50 THEN 'WARNING'
                ELSE 'OK'
            END::text
        FROM pg_stat_statements
        WHERE mean_exec_time > 100
        
        UNION ALL
        
        -- Gaming specific metrics
        SELECT 
            'Gaming'::text,
            'Active Games'::text,
            COUNT(*)::numeric,
            500::numeric,
            800::numeric,
            CASE 
                WHEN COUNT(*) > 800 THEN 'CRITICAL'
                WHEN COUNT(*) > 500 THEN 'WARNING'
                ELSE 'OK'
            END::text
        FROM game_sessions
        WHERE status IN ('active', 'in_progress');
    END;
    \$\$ LANGUAGE plpgsql;
    " "Gaming performance report function"
    
    success "Automated maintenance setup completed"
}

# Create maintenance log table
create_maintenance_log() {
    execute_sql "
    CREATE TABLE IF NOT EXISTS maintenance_log (
        id SERIAL PRIMARY KEY,
        operation VARCHAR(100) NOT NULL,
        status VARCHAR(50) NOT NULL,
        details TEXT,
        duration_seconds NUMERIC,
        completed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    );
    
    CREATE INDEX IF NOT EXISTS idx_maintenance_log_operation_date 
    ON maintenance_log (operation, completed_at DESC);
    " "Maintenance log table"
}

# Run performance analysis
run_performance_analysis() {
    info "Running comprehensive performance analysis..."
    
    # Generate performance report
    execute_sql "
    SELECT 'GAMING PERFORMANCE REPORT - ' || NOW()::text as report_header;
    SELECT * FROM gaming_performance_report();
    
    SELECT '--- SLOW QUERIES ---' as section;
    SELECT * FROM v_slow_queries LIMIT 10;
    
    SELECT '--- INDEX USAGE ---' as section;
    SELECT * FROM v_index_usage WHERE index_efficiency != 'Good' LIMIT 10;
    
    SELECT '--- VACUUM ANALYSIS ---' as section;
    SELECT * FROM gaming_vacuum_analysis() WHERE recommendation != 'OK';
    " "Performance analysis report"
    
    success "Performance analysis completed"
}

# Main execution function
main() {
    info "Starting PostgreSQL Gaming Performance Optimization"
    
    # Create maintenance log
    create_maintenance_log
    
    # Apply optimizations
    create_gaming_indexes
    create_materialized_views
    apply_postgresql_config
    create_monitoring_views
    analyze_query_performance
    setup_automated_maintenance
    run_performance_analysis
    
    success "PostgreSQL Gaming Performance Optimization completed successfully!"
    info "Check the log file at: $LOG_FILE"
    info "Run 'SELECT * FROM gaming_performance_report();' to monitor performance"
    info "Run 'SELECT * FROM v_slow_queries;' to check slow queries"
    info "Run 'SELECT * FROM gaming_vacuum_analysis();' to check table maintenance needs"
}

# Trap for cleanup
trap 'error "Optimization script interrupted"' INT TERM

# Check dependencies
if ! command -v psql &> /dev/null; then
    error "psql command not found. Please install PostgreSQL client."
    exit 1
fi

# Test database connection
if ! psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -c "SELECT 1;" &> /dev/null; then
    error "Cannot connect to PostgreSQL database. Please check connection parameters."
    exit 1
fi

# Execute main function
main "$@"
