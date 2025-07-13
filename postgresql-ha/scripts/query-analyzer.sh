#!/bin/bash

# Gaming Query Analyzer for Hokm Game Server
# Analyzes and optimizes gaming-specific PostgreSQL queries

set -euo pipefail

# Configuration
PGHOST="${PGHOST:-postgresql-primary}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-postgres}"
PGDATABASE="${PGDATABASE:-hokm_game}"
LOG_FILE="/var/log/postgresql-query-analyzer.log"
ANALYSIS_MODE="${1:-performance}"  # performance, bloat, indexes, gaming

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

recommend() {
    log "${MAGENTA}💡 $*${NC}"
}

# Execute SQL query with error handling
execute_query() {
    local query="$1"
    local format="${2:-}"
    
    if [[ -n "$format" ]]; then
        psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -c "$query" --no-align --tuples-only 2>/dev/null || echo "N/A"
    else
        psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -c "$query" 2>/dev/null || echo "N/A"
    fi
}

# Execute and format query results
execute_formatted() {
    local query="$1"
    psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -c "$query" 2>/dev/null
}

# Analyze gaming-specific query performance
analyze_gaming_performance() {
    highlight "GAMING QUERY PERFORMANCE ANALYSIS"
    echo "=============================================="
    
    # Game session operations
    info "Game Session Operations:"
    execute_formatted "
    SELECT 
        CASE 
            WHEN query ILIKE '%INSERT INTO game_sessions%' THEN 'Game Creation'
            WHEN query ILIKE '%UPDATE game_sessions%SET status%' THEN 'Game Status Updates'
            WHEN query ILIKE '%SELECT%game_sessions%WHERE room_id%' THEN 'Game Lookup by Room'
            WHEN query ILIKE '%SELECT%game_sessions%WHERE status%' THEN 'Active Game Queries'
            ELSE 'Other Game Operations'
        END as operation_type,
        COUNT(*) as query_count,
        ROUND(AVG(mean_exec_time)::numeric, 2) as avg_time_ms,
        ROUND(MAX(max_exec_time)::numeric, 2) as max_time_ms,
        ROUND(SUM(total_exec_time)::numeric, 2) as total_time_ms,
        ROUND(AVG(rows)::numeric, 1) as avg_rows_returned
    FROM pg_stat_statements 
    WHERE query ILIKE '%game_sessions%' 
    AND calls > 5
    GROUP BY operation_type
    ORDER BY avg_time_ms DESC;
    "
    
    echo
    
    # Player operations
    info "Player Operations:"
    execute_formatted "
    SELECT 
        CASE 
            WHEN query ILIKE '%INSERT INTO game_participants%' THEN 'Player Join Game'
            WHEN query ILIKE '%UPDATE game_participants%' THEN 'Player Updates'
            WHEN query ILIKE '%SELECT%game_participants%JOIN%' THEN 'Player Game Lookup'
            WHEN query ILIKE '%DELETE FROM game_participants%' THEN 'Player Leave Game'
            ELSE 'Other Player Operations'
        END as operation_type,
        COUNT(*) as query_count,
        ROUND(AVG(mean_exec_time)::numeric, 2) as avg_time_ms,
        ROUND(MAX(max_exec_time)::numeric, 2) as max_time_ms,
        ROUND(SUM(total_exec_time)::numeric, 2) as total_time_ms
    FROM pg_stat_statements 
    WHERE query ILIKE '%game_participants%' 
    AND calls > 5
    GROUP BY operation_type
    ORDER BY avg_time_ms DESC;
    "
    
    echo
    
    # Game move operations
    info "Game Move Operations:"
    execute_formatted "
    SELECT 
        CASE 
            WHEN query ILIKE '%INSERT INTO game_moves%' THEN 'Card Play Recording'
            WHEN query ILIKE '%SELECT%game_moves%ORDER BY timestamp%' THEN 'Move History Queries'
            WHEN query ILIKE '%SELECT%game_moves%WHERE game_id%' THEN 'Game Move Lookup'
            ELSE 'Other Move Operations'
        END as operation_type,
        COUNT(*) as query_count,
        ROUND(AVG(mean_exec_time)::numeric, 2) as avg_time_ms,
        ROUND(MAX(max_exec_time)::numeric, 2) as max_time_ms,
        ROUND(SUM(total_exec_time)::numeric, 2) as total_time_ms
    FROM pg_stat_statements 
    WHERE query ILIKE '%game_moves%' 
    AND calls > 5
    GROUP BY operation_type
    ORDER BY avg_time_ms DESC;
    "
    
    echo
    
    # WebSocket connection operations
    info "WebSocket Connection Operations:"
    execute_formatted "
    SELECT 
        CASE 
            WHEN query ILIKE '%INSERT INTO websocket_connections%' THEN 'Connection Establishment'
            WHEN query ILIKE '%UPDATE websocket_connections%SET status%' THEN 'Connection Status Updates'
            WHEN query ILIKE '%DELETE FROM websocket_connections%' THEN 'Connection Cleanup'
            WHEN query ILIKE '%SELECT%websocket_connections%WHERE status%' THEN 'Active Connection Queries'
            ELSE 'Other Connection Operations'
        END as operation_type,
        COUNT(*) as query_count,
        ROUND(AVG(mean_exec_time)::numeric, 2) as avg_time_ms,
        ROUND(MAX(max_exec_time)::numeric, 2) as max_time_ms,
        ROUND(SUM(total_exec_time)::numeric, 2) as total_time_ms
    FROM pg_stat_statements 
    WHERE query ILIKE '%websocket_connections%' 
    AND calls > 5
    GROUP BY operation_type
    ORDER BY avg_time_ms DESC;
    "
    
    echo
}

# Identify slow gaming queries
identify_slow_queries() {
    highlight "SLOW GAMING QUERIES ANALYSIS"
    echo "=================================="
    
    info "Queries slower than 50ms (gaming critical):"
    execute_formatted "
    SELECT 
        LEFT(query, 100) as query_snippet,
        calls,
        ROUND(mean_exec_time::numeric, 2) as avg_time_ms,
        ROUND(max_exec_time::numeric, 2) as max_time_ms,
        ROUND(total_exec_time::numeric, 2) as total_time_ms,
        ROUND((100.0 * shared_blks_hit / nullif(shared_blks_hit + shared_blks_read, 0))::numeric, 2) as cache_hit_ratio
    FROM pg_stat_statements 
    WHERE mean_exec_time > 50 
    AND calls > 5
    AND query NOT ILIKE '%pg_stat%'
    AND query NOT ILIKE '%EXPLAIN%'
    ORDER BY mean_exec_time DESC
    LIMIT 10;
    "
    
    echo
    
    info "Most time-consuming queries (total time):"
    execute_formatted "
    SELECT 
        LEFT(query, 100) as query_snippet,
        calls,
        ROUND(mean_exec_time::numeric, 2) as avg_time_ms,
        ROUND(total_exec_time::numeric, 2) as total_time_ms,
        ROUND((total_exec_time / (SELECT SUM(total_exec_time) FROM pg_stat_statements) * 100)::numeric, 2) as percent_total_time
    FROM pg_stat_statements 
    WHERE calls > 10
    AND query NOT ILIKE '%pg_stat%'
    ORDER BY total_exec_time DESC
    LIMIT 10;
    "
    
    echo
}

# Analyze index usage for gaming tables
analyze_gaming_indexes() {
    highlight "GAMING INDEX USAGE ANALYSIS"
    echo "================================"
    
    info "Index usage for gaming tables:"
    execute_formatted "
    SELECT 
        schemaname,
        tablename,
        indexname,
        idx_scan,
        idx_tup_read,
        idx_tup_fetch,
        CASE 
            WHEN idx_scan = 0 THEN 'UNUSED'
            WHEN idx_scan < 100 THEN 'LOW USAGE'
            WHEN idx_scan < 1000 THEN 'MEDIUM USAGE'
            ELSE 'HIGH USAGE'
        END as usage_level
    FROM pg_stat_user_indexes 
    WHERE tablename IN ('game_sessions', 'game_participants', 'game_moves', 'websocket_connections', 'players', 'player_statistics')
    ORDER BY tablename, idx_scan DESC;
    "
    
    echo
    
    info "Tables without indexes on foreign keys:"
    execute_formatted "
    SELECT 
        t.table_name,
        kcu.column_name,
        ccu.table_name AS foreign_table_name,
        ccu.column_name AS foreign_column_name
    FROM information_schema.table_constraints AS tc
    JOIN information_schema.key_column_usage AS kcu
        ON tc.constraint_name = kcu.constraint_name
        AND tc.table_schema = kcu.table_schema
    JOIN information_schema.constraint_column_usage AS ccu
        ON ccu.constraint_name = tc.constraint_name
        AND ccu.table_schema = tc.table_schema
    WHERE tc.constraint_type = 'FOREIGN KEY'
    AND t.table_name IN ('game_sessions', 'game_participants', 'game_moves', 'websocket_connections')
    AND NOT EXISTS (
        SELECT 1 FROM pg_indexes 
        WHERE tablename = t.table_name 
        AND indexdef ILIKE '%' || kcu.column_name || '%'
    );
    "
    
    echo
    
    info "Missing indexes recommendations:"
    
    # Check for missing indexes on common WHERE clauses
    local missing_indexes=""
    
    # Check if game_sessions has index on (status, room_id)
    local status_room_index=$(execute_query "SELECT COUNT(*) FROM pg_indexes WHERE tablename = 'game_sessions' AND indexdef ILIKE '%status%' AND indexdef ILIKE '%room_id%'" "raw")
    if [[ "$status_room_index" == "0" ]]; then
        recommend "CREATE INDEX CONCURRENTLY idx_game_sessions_status_room ON game_sessions(status, room_id);"
    fi
    
    # Check if game_moves has index on (game_id, timestamp)
    local moves_game_time_index=$(execute_query "SELECT COUNT(*) FROM pg_indexes WHERE tablename = 'game_moves' AND indexdef ILIKE '%game_id%' AND indexdef ILIKE '%timestamp%'" "raw")
    if [[ "$moves_game_time_index" == "0" ]]; then
        recommend "CREATE INDEX CONCURRENTLY idx_game_moves_game_time ON game_moves(game_id, timestamp);"
    fi
    
    # Check if websocket_connections has index on (status, player_id)
    local ws_status_player_index=$(execute_query "SELECT COUNT(*) FROM pg_indexes WHERE tablename = 'websocket_connections' AND indexdef ILIKE '%status%' AND indexdef ILIKE '%player_id%'" "raw")
    if [[ "$ws_status_player_index" == "0" ]]; then
        recommend "CREATE INDEX CONCURRENTLY idx_websocket_connections_status_player ON websocket_connections(status, player_id);"
    fi
    
    echo
}

# Analyze table bloat
analyze_table_bloat() {
    highlight "TABLE BLOAT ANALYSIS"
    echo "====================="
    
    info "Table bloat analysis for gaming tables:"
    execute_formatted "
    SELECT 
        schemaname,
        tablename,
        n_live_tup,
        n_dead_tup,
        ROUND((n_dead_tup * 100.0 / GREATEST(n_live_tup + n_dead_tup, 1))::numeric, 2) as dead_tuple_percent,
        pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as total_size,
        CASE 
            WHEN n_dead_tup * 100.0 / GREATEST(n_live_tup + n_dead_tup, 1) > 20 THEN 'NEEDS VACUUM'
            WHEN n_dead_tup * 100.0 / GREATEST(n_live_tup + n_dead_tup, 1) > 10 THEN 'CONSIDER VACUUM'
            ELSE 'OK'
        END as vacuum_recommendation
    FROM pg_stat_user_tables 
    WHERE schemaname = 'public'
    AND tablename IN ('game_sessions', 'game_participants', 'game_moves', 'websocket_connections', 'players', 'player_statistics')
    ORDER BY dead_tuple_percent DESC;
    "
    
    echo
    
    info "Index bloat analysis:"
    execute_formatted "
    SELECT 
        schemaname,
        tablename,
        indexname,
        idx_scan,
        pg_size_pretty(pg_relation_size(schemaname||'.'||indexname)) as index_size,
        CASE 
            WHEN idx_scan = 0 THEN 'UNUSED - CONSIDER DROPPING'
            WHEN idx_scan < 100 THEN 'LOW USAGE'
            ELSE 'ACTIVE'
        END as usage_status
    FROM pg_stat_user_indexes 
    WHERE schemaname = 'public'
    AND tablename IN ('game_sessions', 'game_participants', 'game_moves', 'websocket_connections', 'players', 'player_statistics')
    ORDER BY pg_relation_size(schemaname||'.'||indexname) DESC;
    "
    
    echo
}

# Generate gaming-specific recommendations
generate_gaming_recommendations() {
    highlight "GAMING-SPECIFIC PERFORMANCE RECOMMENDATIONS"
    echo "============================================="
    
    # Analyze connection patterns
    local avg_connection_duration=$(execute_query "SELECT ROUND(AVG(EXTRACT(EPOCH FROM (COALESCE(disconnected_at, NOW()) - connected_at)))) FROM websocket_connections WHERE connected_at > NOW() - INTERVAL '1 hour'" "raw")
    if [[ "$avg_connection_duration" != "N/A" ]] && [[ "$avg_connection_duration" -lt 300 ]]; then
        recommend "Short connection duration detected (${avg_connection_duration}s avg). Consider connection pooling optimization."
    fi
    
    # Analyze game duration patterns
    local avg_game_duration=$(execute_query "SELECT ROUND(AVG(EXTRACT(EPOCH FROM (completed_at - created_at))/60)) FROM game_sessions WHERE status = 'completed' AND completed_at > NOW() - INTERVAL '1 day'" "raw")
    if [[ "$avg_game_duration" != "N/A" ]]; then
        info "Average game duration: ${avg_game_duration} minutes"
        if [[ "$avg_game_duration" -gt 60 ]]; then
            recommend "Long game duration detected. Consider partitioning game_moves table by time."
        fi
    fi
    
    # Analyze move frequency
    local moves_per_minute=$(execute_query "SELECT ROUND(COUNT(*) / GREATEST(EXTRACT(EPOCH FROM (MAX(timestamp) - MIN(timestamp))) / 60, 1)) FROM game_moves WHERE timestamp > NOW() - INTERVAL '1 hour'" "raw")
    if [[ "$moves_per_minute" != "N/A" ]] && [[ "$moves_per_minute" -gt 100 ]]; then
        recommend "High move frequency detected (${moves_per_minute}/min). Consider optimizing game_moves indexes."
    fi
    
    # Check for common anti-patterns
    info "Checking for common gaming anti-patterns..."
    
    # Check for N+1 queries
    local high_call_queries=$(execute_query "SELECT COUNT(*) FROM pg_stat_statements WHERE calls > 1000 AND mean_exec_time < 5 AND query ILIKE '%SELECT%WHERE%=%$%'" "raw")
    if [[ "$high_call_queries" -gt 0 ]]; then
        warning "Potential N+1 query pattern detected ($high_call_queries queries with >1000 calls)"
        recommend "Review application code for batch loading opportunities"
    fi
    
    # Check for missing LIMIT clauses
    local unlimited_queries=$(execute_query "SELECT COUNT(*) FROM pg_stat_statements WHERE query ILIKE '%SELECT%' AND query NOT ILIKE '%LIMIT%' AND query NOT ILIKE '%COUNT%' AND mean_exec_time > 10" "raw")
    if [[ "$unlimited_queries" -gt 0 ]]; then
        warning "Queries without LIMIT clauses detected ($unlimited_queries queries)"
        recommend "Add LIMIT clauses to prevent large result sets in gaming queries"
    fi
    
    echo
    
    # Specific gaming optimizations
    info "Gaming-specific optimization suggestions:"
    
    cat << 'EOF'
    
    🎮 HOKM GAME OPTIMIZATIONS:
    
    1. Game State Management:
       - Use JSONB for game_state with GIN indexes for fast lookups
       - Consider Redis for active game state caching
       - Implement game state checkpointing for long games
    
    2. Real-time Features:
       - Use LISTEN/NOTIFY for real-time updates
       - Batch WebSocket connection updates
       - Consider connection pooling for WebSocket backends
    
    3. Leaderboard Optimization:
       - Use materialized views for complex leaderboard queries
       - Refresh materialized views during low-activity periods
       - Consider separate read replicas for leaderboard queries
    
    4. Move Recording:
       - Batch insert multiple moves when possible
       - Use prepared statements for move recording
       - Consider partitioning by game_id or timestamp
    
    5. Player Statistics:
       - Update statistics asynchronously when possible
       - Use triggers for automatic statistic updates
       - Consider using window functions for ranking queries
    
EOF
    
    echo
}

# Create optimization script
create_optimization_script() {
    local script_file="/tmp/gaming_optimizations.sql"
    
    info "Creating optimization script: $script_file"
    
    cat << 'EOF' > "$script_file"
-- Gaming-Specific PostgreSQL Optimizations
-- Generated by gaming query analyzer

-- Enable pg_stat_statements if not already enabled
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- Optimize shared_buffers for gaming workload
-- ALTER SYSTEM SET shared_buffers = '1GB';  -- Adjust based on available RAM

-- Gaming-specific configuration
ALTER SYSTEM SET statement_timeout = '30s';  -- Prevent long-running queries
ALTER SYSTEM SET idle_in_transaction_session_timeout = '5min';  -- Clean up idle connections
ALTER SYSTEM SET deadlock_timeout = '1s';  -- Quick deadlock detection
ALTER SYSTEM SET log_min_duration_statement = '100ms';  -- Log slow queries

-- Optimize autovacuum for gaming tables
ALTER SYSTEM SET autovacuum_naptime = '30s';
ALTER SYSTEM SET autovacuum_vacuum_scale_factor = 0.1;
ALTER SYSTEM SET autovacuum_analyze_scale_factor = 0.05;

-- Create missing indexes (uncomment as needed)
-- CREATE INDEX CONCURRENTLY idx_game_sessions_status_room ON game_sessions(status, room_id);
-- CREATE INDEX CONCURRENTLY idx_game_moves_game_time ON game_moves(game_id, timestamp);
-- CREATE INDEX CONCURRENTLY idx_websocket_connections_status_player ON websocket_connections(status, player_id);
-- CREATE INDEX CONCURRENTLY idx_game_participants_game_player ON game_participants(game_id, player_id);

-- Create partial indexes for active data
-- CREATE INDEX CONCURRENTLY idx_active_games ON game_sessions(room_id, created_at) 
--     WHERE status IN ('waiting', 'active', 'in_progress');
-- CREATE INDEX CONCURRENTLY idx_active_connections ON websocket_connections(player_id, last_ping) 
--     WHERE status = 'active';

-- Create materialized view for leaderboards
-- CREATE MATERIALIZED VIEW mv_player_leaderboard AS
-- SELECT 
--     p.player_id,
--     p.username,
--     ps.total_score,
--     ps.games_won,
--     ps.games_played,
--     ROUND(ps.games_won * 100.0 / GREATEST(ps.games_played, 1), 2) as win_percentage,
--     ROW_NUMBER() OVER (ORDER BY ps.total_score DESC) as rank
-- FROM players p
-- JOIN player_statistics ps ON p.player_id = ps.player_id
-- WHERE p.is_active = true AND ps.games_played >= 10
-- ORDER BY ps.total_score DESC;

-- Create index on materialized view
-- CREATE INDEX idx_mv_player_leaderboard_rank ON mv_player_leaderboard(rank);
-- CREATE INDEX idx_mv_player_leaderboard_score ON mv_player_leaderboard(total_score DESC);

-- Function to refresh materialized views
-- CREATE OR REPLACE FUNCTION refresh_gaming_views() RETURNS void AS $$
-- BEGIN
--     REFRESH MATERIALIZED VIEW CONCURRENTLY mv_player_leaderboard;
-- END;
-- $$ LANGUAGE plpgsql;

-- Apply configuration (requires superuser privileges)
-- SELECT pg_reload_conf();

EOF
    
    success "Optimization script created: $script_file"
    echo "Review and uncomment the desired optimizations, then run:"
    echo "psql -h $PGHOST -p $PGPORT -U $PGUSER -d $PGDATABASE -f $script_file"
    
    echo
}

# Main analysis function
main() {
    case "$ANALYSIS_MODE" in
        "performance")
            analyze_gaming_performance
            identify_slow_queries
            ;;
        "indexes")
            analyze_gaming_indexes
            ;;
        "bloat")
            analyze_table_bloat
            ;;
        "gaming")
            generate_gaming_recommendations
            ;;
        "all")
            analyze_gaming_performance
            identify_slow_queries
            analyze_gaming_indexes
            analyze_table_bloat
            generate_gaming_recommendations
            create_optimization_script
            ;;
        *)
            error "Unknown analysis mode: $ANALYSIS_MODE"
            echo "Available modes: performance, indexes, bloat, gaming, all"
            exit 1
            ;;
    esac
}

# Show help
show_help() {
    echo "Gaming Query Analyzer for PostgreSQL"
    echo
    echo "Usage: $0 [mode]"
    echo
    echo "Modes:"
    echo "  performance   Analyze gaming query performance (default)"
    echo "  indexes       Analyze index usage for gaming tables"
    echo "  bloat         Analyze table and index bloat"
    echo "  gaming        Generate gaming-specific recommendations"
    echo "  all           Run all analyses and generate optimization script"
    echo
    echo "Environment Variables:"
    echo "  PGHOST        PostgreSQL host (default: postgresql-primary)"
    echo "  PGPORT        PostgreSQL port (default: 5432)"
    echo "  PGUSER        PostgreSQL user (default: postgres)"
    echo "  PGDATABASE    PostgreSQL database (default: hokm_game)"
    echo
    echo "Examples:"
    echo "  $0                    # Analyze performance"
    echo "  $0 indexes            # Analyze index usage"
    echo "  $0 all                # Complete analysis"
    echo
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

# Initialize log
log "Starting Gaming Query Analysis (mode: $ANALYSIS_MODE)"

# Run analysis
main

success "Analysis completed. Log file: $LOG_FILE"
