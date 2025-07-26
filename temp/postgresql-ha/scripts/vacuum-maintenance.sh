#!/bin/bash

# PostgreSQL Vacuum and Maintenance Automation Script
# Optimized for gaming workloads with minimal impact on active games

set -euo pipefail

# Configuration
PGHOST="${PGHOST:-postgresql-primary}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-postgres}"
PGDATABASE="${PGDATABASE:-hokm_game}"
LOG_FILE="/var/log/postgresql-vacuum.log"
MAINTENANCE_SCHEDULE="${1:-auto}"  # auto, aggressive, gentle

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
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

# Execute SQL with timing
execute_sql() {
    local sql="$1"
    local description="$2"
    local start_time=$(date +%s)
    
    info "Starting: $description"
    
    if psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" \
        -c "\\timing on" -c "$sql" >> "$LOG_FILE" 2>&1; then
        local end_time=$(date +%s)
        local duration=$((end_time - start_time))
        success "$description completed in ${duration}s"
        return 0
    else
        error "$description failed"
        return 1
    fi
}

# Check current database activity
check_database_activity() {
    local active_games=$(psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -tAc \
        "SELECT COUNT(*) FROM game_sessions WHERE status IN ('active', 'in_progress');")
    
    local active_connections=$(psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -tAc \
        "SELECT COUNT(*) FROM pg_stat_activity WHERE state = 'active';")
    
    info "Current activity: $active_games active games, $active_connections active connections"
    
    # Return activity level for scheduling decisions
    if [ "$active_games" -gt 100 ] || [ "$active_connections" -gt 500 ]; then
        echo "high"
    elif [ "$active_games" -gt 50 ] || [ "$active_connections" -gt 200 ]; then
        echo "medium"
    else
        echo "low"
    fi
}

# Analyze table bloat and vacuum requirements
analyze_table_bloat() {
    info "Analyzing table bloat and vacuum requirements..."
    
    execute_sql "
    CREATE TEMP TABLE vacuum_analysis AS
    SELECT 
        schemaname,
        tablename,
        n_live_tup,
        n_dead_tup,
        CASE 
            WHEN n_live_tup > 0 
            THEN round((n_dead_tup::float / n_live_tup) * 100, 2)
            ELSE 0 
        END as dead_tuple_percent,
        pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as table_size,
        last_vacuum,
        last_autovacuum,
        CASE 
            WHEN n_dead_tup::float / NULLIF(n_live_tup, 0) > 0.25 THEN 'URGENT'
            WHEN n_dead_tup::float / NULLIF(n_live_tup, 0) > 0.15 THEN 'HIGH'
            WHEN n_dead_tup::float / NULLIF(n_live_tup, 0) > 0.10 THEN 'MEDIUM'
            WHEN n_dead_tup::float / NULLIF(n_live_tup, 0) > 0.05 THEN 'LOW'
            ELSE 'NONE'
        END as vacuum_priority,
        -- Estimate vacuum duration based on table size
        CASE 
            WHEN pg_total_relation_size(schemaname||'.'||tablename) > 1073741824 THEN 'LONG'  -- > 1GB
            WHEN pg_total_relation_size(schemaname||'.'||tablename) > 104857600 THEN 'MEDIUM' -- > 100MB
            ELSE 'SHORT'
        END as estimated_duration
    FROM pg_stat_user_tables
    WHERE n_live_tup > 100  -- Only tables with significant data
    ORDER BY dead_tuple_percent DESC, n_dead_tup DESC;
    
    SELECT 'TABLE BLOAT ANALYSIS' as analysis_type;
    SELECT tablename, dead_tuple_percent, table_size, vacuum_priority, estimated_duration
    FROM vacuum_analysis
    WHERE vacuum_priority != 'NONE'
    ORDER BY 
        CASE vacuum_priority 
            WHEN 'URGENT' THEN 1 
            WHEN 'HIGH' THEN 2 
            WHEN 'MEDIUM' THEN 3 
            WHEN 'LOW' THEN 4 
        END;
    " "Table bloat analysis"
}

# Gaming-optimized vacuum strategy
vacuum_gaming_tables() {
    local activity_level="$1"
    local vacuum_mode="$2"  # gentle, normal, aggressive
    
    info "Starting vacuum with mode: $vacuum_mode, activity level: $activity_level"
    
    # Set vacuum parameters based on activity level and mode
    case "$vacuum_mode" in
        "gentle")
            local cost_delay=20
            local cost_limit=500
            ;;
        "normal")
            local cost_delay=10
            local cost_limit=1000
            ;;
        "aggressive")
            local cost_delay=2
            local cost_limit=2000
            ;;
    esac
    
    # Adjust for activity level
    if [ "$activity_level" = "high" ]; then
        cost_delay=$((cost_delay * 2))
        cost_limit=$((cost_limit / 2))
        warning "High activity detected, using gentler vacuum settings"
    fi
    
    # Set vacuum cost parameters
    execute_sql "
    SET vacuum_cost_delay = ${cost_delay};
    SET vacuum_cost_limit = ${cost_limit};
    " "Setting vacuum cost parameters"
    
    # Vacuum critical gaming tables in order of priority
    local gaming_tables=(
        "game_sessions"
        "game_moves" 
        "game_participants"
        "websocket_connections"
        "player_stats"
        "players"
    )
    
    for table in "${gaming_tables[@]}"; do
        info "Vacuuming table: $table"
        
        # Check if table needs vacuum
        local bloat_check=$(psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -tAc \
            "SELECT CASE WHEN n_dead_tup::float / NULLIF(n_live_tup, 0) > 0.05 THEN 'yes' ELSE 'no' END 
             FROM pg_stat_user_tables WHERE tablename = '$table';")
        
        if [ "$bloat_check" = "yes" ]; then
            # Use different vacuum strategies based on activity
            if [ "$activity_level" = "high" ] && [ "$table" = "game_sessions" ]; then
                # For active game sessions, use gentle vacuum during high activity
                execute_sql "VACUUM (VERBOSE, ANALYZE) $table;" "Gentle vacuum of $table"
            else
                # Standard vacuum for other tables or during low activity
                execute_sql "VACUUM (VERBOSE, ANALYZE) $table;" "Vacuum of $table"
            fi
            
            # Brief pause between tables during high activity
            if [ "$activity_level" = "high" ]; then
                sleep 5
            fi
        else
            info "Table $table doesn't need vacuum (low bloat)"
        fi
    done
    
    success "Gaming tables vacuum completed"
}

# Vacuum indexes specifically
vacuum_indexes() {
    info "Starting index maintenance..."
    
    # Reindex bloated indexes
    execute_sql "
    WITH index_bloat AS (
        SELECT 
            schemaname,
            tablename,
            indexname,
            idx_tup_read,
            idx_tup_fetch,
            pg_size_pretty(pg_relation_size(indexrelid)) as index_size,
            pg_relation_size(indexrelid) as index_size_bytes
        FROM pg_stat_user_indexes
        WHERE idx_tup_read > 1000  -- Only frequently used indexes
        AND pg_relation_size(indexrelid) > 10485760  -- > 10MB
    )
    SELECT 'LARGE INDEXES ANALYSIS' as analysis_type;
    SELECT indexname, index_size, idx_tup_read, idx_tup_fetch
    FROM index_bloat
    ORDER BY index_size_bytes DESC
    LIMIT 20;
    " "Index bloat analysis"
    
    # Reindex critical gaming indexes if needed
    local critical_indexes=(
        "idx_game_sessions_active_lookup"
        "idx_game_moves_game_sequence"
        "idx_game_participants_room_player"
        "idx_websocket_connections_active"
    )
    
    for index in "${critical_indexes[@]}"; do
        # Check if index exists and is bloated
        local index_exists=$(psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -tAc \
            "SELECT EXISTS(SELECT 1 FROM pg_indexes WHERE indexname = '$index');")
        
        if [ "$index_exists" = "t" ]; then
            info "Checking index: $index"
            # Could add specific reindex logic here if needed
            # For now, let autovacuum handle index maintenance
        fi
    done
    
    success "Index maintenance completed"
}

# Update table statistics
update_statistics() {
    info "Updating table statistics for query optimization..."
    
    # Analyze all gaming tables
    local gaming_tables=(
        "game_sessions"
        "game_moves"
        "game_participants"
        "websocket_connections"
        "player_stats"
        "players"
    )
    
    for table in "${gaming_tables[@]}"; do
        execute_sql "ANALYZE $table;" "Analyzing statistics for $table"
    done
    
    # Update pg_stat_statements if available
    execute_sql "SELECT pg_stat_statements_reset();" "Resetting query statistics" || warning "pg_stat_statements not available"
    
    success "Statistics update completed"
}

# Refresh materialized views
refresh_materialized_views() {
    info "Refreshing materialized views..."
    
    # Refresh leaderboard (most critical for gaming)
    if psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -tAc \
        "SELECT EXISTS(SELECT 1 FROM pg_matviews WHERE matviewname = 'mv_player_leaderboard');" | grep -q "t"; then
        execute_sql "REFRESH MATERIALIZED VIEW CONCURRENTLY mv_player_leaderboard;" "Refreshing player leaderboard"
    else
        warning "Player leaderboard materialized view not found"
    fi
    
    # Refresh game statistics
    if psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -tAc \
        "SELECT EXISTS(SELECT 1 FROM pg_matviews WHERE matviewname = 'mv_game_statistics');" | grep -q "t"; then
        execute_sql "REFRESH MATERIALIZED VIEW CONCURRENTLY mv_game_statistics;" "Refreshing game statistics"
    else
        warning "Game statistics materialized view not found"
    fi
    
    success "Materialized views refresh completed"
}

# Clean up old data
cleanup_old_data() {
    local retention_days="${1:-30}"
    
    info "Cleaning up old data (retention: $retention_days days)..."
    
    # Clean old completed games
    execute_sql "
    DELETE FROM game_sessions 
    WHERE status = 'completed' 
    AND completed_at < NOW() - INTERVAL '$retention_days days';
    " "Cleaning old completed games"
    
    # Clean old connection logs
    execute_sql "
    DELETE FROM websocket_connections 
    WHERE status = 'disconnected' 
    AND updated_at < NOW() - INTERVAL '7 days';
    " "Cleaning old connection logs"
    
    # Clean old maintenance logs
    execute_sql "
    DELETE FROM maintenance_log 
    WHERE completed_at < NOW() - INTERVAL '90 days';
    " "Cleaning old maintenance logs"
    
    success "Old data cleanup completed"
}

# Generate maintenance report
generate_maintenance_report() {
    info "Generating maintenance report..."
    
    execute_sql "
    SELECT 'MAINTENANCE REPORT - ' || NOW()::text as report_header;
    
    SELECT 'DATABASE SIZE ANALYSIS' as section;
    SELECT 
        pg_size_pretty(pg_database_size(current_database())) as database_size,
        (SELECT COUNT(*) FROM game_sessions) as total_games,
        (SELECT COUNT(*) FROM game_sessions WHERE status IN ('active', 'in_progress')) as active_games,
        (SELECT COUNT(*) FROM players WHERE is_active = true) as active_players;
    
    SELECT 'TOP 10 LARGEST TABLES' as section;
    SELECT 
        schemaname,
        tablename,
        pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size,
        n_live_tup as live_tuples,
        n_dead_tup as dead_tuples
    FROM pg_stat_user_tables
    ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
    LIMIT 10;
    
    SELECT 'VACUUM EFFECTIVENESS' as section;
    SELECT 
        tablename,
        last_vacuum,
        last_autovacuum,
        vacuum_count,
        autovacuum_count,
        CASE 
            WHEN n_live_tup > 0 
            THEN round((n_dead_tup::float / n_live_tup) * 100, 2)
            ELSE 0 
        END as dead_tuple_percent
    FROM pg_stat_user_tables
    WHERE n_live_tup > 1000
    ORDER BY dead_tuple_percent DESC
    LIMIT 10;
    
    SELECT 'RECENT MAINTENANCE ACTIVITIES' as section;
    SELECT operation, status, completed_at, duration_seconds
    FROM maintenance_log
    WHERE completed_at > NOW() - INTERVAL '7 days'
    ORDER BY completed_at DESC
    LIMIT 20;
    " "Maintenance report generation"
    
    success "Maintenance report generated"
}

# Log maintenance activity
log_maintenance_activity() {
    local operation="$1"
    local status="$2"
    local duration="${3:-0}"
    
    execute_sql "
    INSERT INTO maintenance_log (operation, status, duration_seconds, completed_at)
    VALUES ('$operation', '$status', $duration, NOW());
    " "Logging maintenance activity"
}

# Main maintenance function
run_maintenance() {
    local schedule="$1"
    local start_time=$(date +%s)
    
    info "Starting PostgreSQL maintenance with schedule: $schedule"
    
    # Check current database activity
    local activity_level=$(check_database_activity)
    info "Database activity level: $activity_level"
    
    # Determine maintenance strategy based on schedule and activity
    case "$schedule" in
        "gentle")
            vacuum_mode="gentle"
            skip_aggressive_ops=true
            ;;
        "aggressive")
            vacuum_mode="aggressive"
            skip_aggressive_ops=false
            ;;
        "auto")
            if [ "$activity_level" = "high" ]; then
                vacuum_mode="gentle"
                skip_aggressive_ops=true
                warning "High activity detected, using gentle maintenance mode"
            else
                vacuum_mode="normal"
                skip_aggressive_ops=false
            fi
            ;;
        *)
            vacuum_mode="normal"
            skip_aggressive_ops=false
            ;;
    esac
    
    # Run maintenance operations
    analyze_table_bloat
    vacuum_gaming_tables "$activity_level" "$vacuum_mode"
    vacuum_indexes
    update_statistics
    refresh_materialized_views
    
    # Skip aggressive operations during high activity
    if [ "$skip_aggressive_ops" = false ]; then
        cleanup_old_data 30
    else
        info "Skipping aggressive operations due to high activity"
    fi
    
    generate_maintenance_report
    
    # Calculate and log total duration
    local end_time=$(date +%s)
    local total_duration=$((end_time - start_time))
    
    log_maintenance_activity "full_maintenance" "completed" "$total_duration"
    
    success "PostgreSQL maintenance completed in ${total_duration}s"
}

# Quick maintenance for frequent execution
run_quick_maintenance() {
    info "Running quick maintenance (frequent execution)..."
    local start_time=$(date +%s)
    
    # Only run essential operations
    local activity_level=$(check_database_activity)
    
    # Quick vacuum of most critical tables only
    if [ "$activity_level" != "high" ]; then
        execute_sql "VACUUM (ANALYZE) game_sessions;" "Quick vacuum of game_sessions"
        execute_sql "VACUUM (ANALYZE) websocket_connections;" "Quick vacuum of websocket_connections"
    fi
    
    # Always refresh materialized views (they're critical for gaming)
    refresh_materialized_views
    
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    
    log_maintenance_activity "quick_maintenance" "completed" "$duration"
    success "Quick maintenance completed in ${duration}s"
}

# Emergency maintenance (when things are broken)
run_emergency_maintenance() {
    warning "Running EMERGENCY maintenance - this may impact game performance!"
    local start_time=$(date +%s)
    
    # Force aggressive vacuum regardless of activity
    execute_sql "SET vacuum_cost_delay = 0;" "Disabling vacuum cost limits"
    
    # Vacuum all tables aggressively
    execute_sql "VACUUM FULL ANALYZE;" "Emergency full vacuum"
    
    # Reindex system catalogs if needed
    execute_sql "REINDEX DATABASE $PGDATABASE;" "Emergency reindex"
    
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    
    log_maintenance_activity "emergency_maintenance" "completed" "$duration"
    warning "Emergency maintenance completed in ${duration}s"
}

# Main execution
main() {
    local schedule="${1:-auto}"
    
    # Test database connection
    if ! psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -c "SELECT 1;" &> /dev/null; then
        error "Cannot connect to PostgreSQL database"
        exit 1
    fi
    
    # Create maintenance log table if it doesn't exist
    execute_sql "
    CREATE TABLE IF NOT EXISTS maintenance_log (
        id SERIAL PRIMARY KEY,
        operation VARCHAR(100) NOT NULL,
        status VARCHAR(50) NOT NULL,
        details TEXT,
        duration_seconds NUMERIC,
        completed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    );
    " "Creating maintenance log table"
    
    case "$schedule" in
        "quick")
            run_quick_maintenance
            ;;
        "emergency")
            run_emergency_maintenance
            ;;
        *)
            run_maintenance "$schedule"
            ;;
    esac
    
    info "Maintenance log available at: $LOG_FILE"
    info "Database maintenance report generated in PostgreSQL logs"
}

# Trap for cleanup
trap 'error "Maintenance script interrupted"' INT TERM

# Execute main function
main "$@"
