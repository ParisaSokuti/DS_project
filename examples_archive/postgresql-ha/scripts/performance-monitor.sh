#!/bin/bash

# Real-time PostgreSQL Performance Monitor for Hokm Game Server
# Provides live metrics and performance insights

set -euo pipefail

# Configuration
PGHOST="${PGHOST:-postgresql-primary}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-postgres}"
PGDATABASE="${PGDATABASE:-hokm_game}"
REFRESH_INTERVAL="${1:-5}"  # seconds

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m' # No Color

# Clear screen function
clear_screen() {
    clear
    echo -e "${CYAN}╔══════════════════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║                    HOKM GAME SERVER - POSTGRESQL MONITOR                     ║${NC}"
    echo -e "${CYAN}║                           $(date '+%Y-%m-%d %H:%M:%S')                           ║${NC}"
    echo -e "${CYAN}╚══════════════════════════════════════════════════════════════════════════════╝${NC}"
    echo
}

# Execute SQL query
execute_query() {
    local query="$1"
    psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -t -c "$query" 2>/dev/null || echo "N/A"
}

# Format large numbers
format_number() {
    local num="$1"
    if [[ "$num" =~ ^[0-9]+$ ]]; then
        printf "%'d" "$num"
    else
        echo "$num"
    fi
}

# Show database overview
show_database_overview() {
    echo -e "${BLUE}📊 DATABASE OVERVIEW${NC}"
    echo "─────────────────────────────────────────────────────────────────────────────"
    
    local db_size=$(execute_query "SELECT pg_size_pretty(pg_database_size('$PGDATABASE'))")
    local connections=$(execute_query "SELECT COUNT(*) FROM pg_stat_activity WHERE datname = '$PGDATABASE'")
    local active_connections=$(execute_query "SELECT COUNT(*) FROM pg_stat_activity WHERE datname = '$PGDATABASE' AND state = 'active'")
    local cache_hit_ratio=$(execute_query "SELECT ROUND(sum(blks_hit)*100.0/sum(blks_hit+blks_read), 2) FROM pg_stat_database WHERE datname = '$PGDATABASE'")
    
    printf "%-20s %-15s %-20s %-15s\n" "Database Size:" "$db_size" "Cache Hit Ratio:" "${cache_hit_ratio}%"
    printf "%-20s %-15s %-20s %-15s\n" "Total Connections:" "$connections" "Active Connections:" "$active_connections"
    echo
}

# Show gaming metrics
show_gaming_metrics() {
    echo -e "${GREEN}🎮 GAMING METRICS${NC}"
    echo "─────────────────────────────────────────────────────────────────────────────"
    
    local active_games=$(execute_query "SELECT COUNT(*) FROM game_sessions WHERE status IN ('waiting', 'active', 'in_progress')")
    local total_players=$(execute_query "SELECT COUNT(DISTINCT player_id) FROM websocket_connections WHERE status = 'active'")
    local games_last_hour=$(execute_query "SELECT COUNT(*) FROM game_sessions WHERE created_at > NOW() - INTERVAL '1 hour'")
    local avg_game_duration=$(execute_query "SELECT ROUND(AVG(EXTRACT(EPOCH FROM (completed_at - created_at))/60), 1) FROM game_sessions WHERE status = 'completed' AND completed_at > NOW() - INTERVAL '1 hour'")
    
    printf "%-20s %-15s %-20s %-15s\n" "Active Games:" "$active_games" "Online Players:" "$total_players"
    printf "%-20s %-15s %-20s %-15s\n" "Games/Hour:" "$games_last_hour" "Avg Duration:" "${avg_game_duration}m"
    echo
}

# Show performance metrics
show_performance_metrics() {
    echo -e "${YELLOW}⚡ PERFORMANCE METRICS${NC}"
    echo "─────────────────────────────────────────────────────────────────────────────"
    
    # Query response times
    local game_query_time=$(execute_query "SELECT ROUND(AVG(mean_exec_time), 2) FROM pg_stat_statements WHERE query ILIKE '%game_sessions%' AND calls > 5")
    local move_query_time=$(execute_query "SELECT ROUND(AVG(mean_exec_time), 2) FROM pg_stat_statements WHERE query ILIKE '%game_moves%' AND calls > 5")
    local player_query_time=$(execute_query "SELECT ROUND(AVG(mean_exec_time), 2) FROM pg_stat_statements WHERE query ILIKE '%players%' AND calls > 5")
    
    # Throughput metrics
    local queries_per_sec=$(execute_query "SELECT ROUND(SUM(calls) / GREATEST(EXTRACT(EPOCH FROM (NOW() - stats_reset)), 1), 1) FROM pg_stat_statements, pg_stat_database WHERE pg_stat_database.datname = '$PGDATABASE'")
    
    printf "%-20s %-15s %-20s %-15s\n" "Game Queries:" "${game_query_time}ms" "Move Queries:" "${move_query_time}ms"
    printf "%-20s %-15s %-20s %-15s\n" "Player Queries:" "${player_query_time}ms" "Queries/Sec:" "$queries_per_sec"
    echo
}

# Show connection details
show_connection_details() {
    echo -e "${MAGENTA}🔗 CONNECTION DETAILS${NC}"
    echo "─────────────────────────────────────────────────────────────────────────────"
    
    local result=$(execute_query "
        SELECT 
            state,
            COUNT(*) as count,
            MAX(EXTRACT(EPOCH FROM (NOW() - query_start))) as longest_query
        FROM pg_stat_activity 
        WHERE datname = '$PGDATABASE' 
        GROUP BY state 
        ORDER BY count DESC
    ")
    
    echo "$result" | while IFS='|' read -r state count longest_query; do
        if [[ -n "$state" ]]; then
            state=$(echo "$state" | xargs)
            count=$(echo "$count" | xargs)
            longest_query=$(echo "$longest_query" | xargs)
            printf "%-20s %-15s %-20s %-15s\n" "$state:" "$count" "Longest Query:" "${longest_query}s"
        fi
    done
    echo
}

# Show top queries
show_top_queries() {
    echo -e "${RED}🔥 TOP QUERIES (by avg time)${NC}"
    echo "─────────────────────────────────────────────────────────────────────────────"
    
    local result=$(execute_query "
        SELECT 
            LEFT(query, 60) as query_snippet,
            calls,
            ROUND(mean_exec_time, 2) as avg_time,
            ROUND(total_exec_time, 2) as total_time
        FROM pg_stat_statements 
        WHERE calls > 5 
        ORDER BY mean_exec_time DESC 
        LIMIT 5
    ")
    
    printf "%-62s %-8s %-10s %-10s\n" "Query" "Calls" "Avg(ms)" "Total(ms)"
    printf "%-62s %-8s %-10s %-10s\n" "────────────────────────────────────────────────────────────" "─────" "──────" "────────"
    echo "$result" | while IFS='|' read -r query_snippet calls avg_time total_time; do
        if [[ -n "$query_snippet" ]]; then
            query_snippet=$(echo "$query_snippet" | xargs)
            calls=$(echo "$calls" | xargs)
            avg_time=$(echo "$avg_time" | xargs)
            total_time=$(echo "$total_time" | xargs)
            printf "%-62s %-8s %-10s %-10s\n" "$query_snippet" "$calls" "$avg_time" "$total_time"
        fi
    done
    echo
}

# Show index usage
show_index_usage() {
    echo -e "${CYAN}📇 INDEX USAGE${NC}"
    echo "─────────────────────────────────────────────────────────────────────────────"
    
    local result=$(execute_query "
        SELECT 
            LEFT(schemaname||'.'||tablename||'.'||indexname, 50) as index_name,
            idx_scan,
            idx_tup_read,
            idx_tup_fetch
        FROM pg_stat_user_indexes 
        WHERE idx_scan > 0 
        ORDER BY idx_scan DESC 
        LIMIT 8
    ")
    
    printf "%-52s %-10s %-12s %-12s\n" "Index" "Scans" "Tup Read" "Tup Fetch"
    printf "%-52s %-10s %-12s %-12s\n" "──────────────────────────────────────────────────" "─────" "────────" "─────────"
    echo "$result" | while IFS='|' read -r index_name idx_scan idx_tup_read idx_tup_fetch; do
        if [[ -n "$index_name" ]]; then
            index_name=$(echo "$index_name" | xargs)
            idx_scan=$(echo "$idx_scan" | xargs)
            idx_tup_read=$(echo "$idx_tup_read" | xargs)
            idx_tup_fetch=$(echo "$idx_tup_fetch" | xargs)
            printf "%-52s %-10s %-12s %-12s\n" "$index_name" "$(format_number $idx_scan)" "$(format_number $idx_tup_read)" "$(format_number $idx_tup_fetch)"
        fi
    done
    echo
}

# Show table statistics
show_table_statistics() {
    echo -e "${BLUE}📊 TABLE STATISTICS${NC}"
    echo "─────────────────────────────────────────────────────────────────────────────"
    
    local result=$(execute_query "
        SELECT 
            LEFT(schemaname||'.'||tablename, 30) as table_name,
            n_tup_ins + n_tup_upd + n_tup_del as total_changes,
            n_live_tup,
            n_dead_tup,
            ROUND(n_dead_tup * 100.0 / GREATEST(n_live_tup + n_dead_tup, 1), 1) as dead_ratio
        FROM pg_stat_user_tables 
        WHERE n_tup_ins + n_tup_upd + n_tup_del > 0
        ORDER BY total_changes DESC 
        LIMIT 8
    ")
    
    printf "%-32s %-12s %-12s %-10s %-10s\n" "Table" "Changes" "Live Tup" "Dead Tup" "Dead %"
    printf "%-32s %-12s %-12s %-10s %-10s\n" "──────────────────────────────" "───────" "────────" "────────" "──────"
    echo "$result" | while IFS='|' read -r table_name total_changes n_live_tup n_dead_tup dead_ratio; do
        if [[ -n "$table_name" ]]; then
            table_name=$(echo "$table_name" | xargs)
            total_changes=$(echo "$total_changes" | xargs)
            n_live_tup=$(echo "$n_live_tup" | xargs)
            n_dead_tup=$(echo "$n_dead_tup" | xargs)
            dead_ratio=$(echo "$dead_ratio" | xargs)
            printf "%-32s %-12s %-12s %-10s %-10s\n" "$table_name" "$(format_number $total_changes)" "$(format_number $n_live_tup)" "$(format_number $n_dead_tup)" "${dead_ratio}%"
        fi
    done
    echo
}

# Show alerts
show_alerts() {
    echo -e "${RED}🚨 PERFORMANCE ALERTS${NC}"
    echo "─────────────────────────────────────────────────────────────────────────────"
    
    # Check for high connection count
    local connections=$(execute_query "SELECT COUNT(*) FROM pg_stat_activity WHERE datname = '$PGDATABASE'")
    if [[ "$connections" -gt 150 ]]; then
        echo -e "${RED}⚠ HIGH CONNECTION COUNT: $connections/200${NC}"
    fi
    
    # Check for slow queries
    local slow_queries=$(execute_query "SELECT COUNT(*) FROM pg_stat_activity WHERE state = 'active' AND query_start < NOW() - INTERVAL '30 seconds'")
    if [[ "$slow_queries" -gt 0 ]]; then
        echo -e "${RED}⚠ SLOW QUERIES DETECTED: $slow_queries active queries > 30s${NC}"
    fi
    
    # Check cache hit ratio
    local cache_hit=$(execute_query "SELECT ROUND(sum(blks_hit)*100.0/sum(blks_hit+blks_read), 2) FROM pg_stat_database WHERE datname = '$PGDATABASE'")
    if (( $(echo "$cache_hit < 95" | bc -l) )); then
        echo -e "${RED}⚠ LOW CACHE HIT RATIO: ${cache_hit}% (target: >95%)${NC}"
    fi
    
    # Check for high dead tuple ratio
    local high_dead_tables=$(execute_query "SELECT COUNT(*) FROM pg_stat_user_tables WHERE n_dead_tup * 100.0 / GREATEST(n_live_tup + n_dead_tup, 1) > 20")
    if [[ "$high_dead_tables" -gt 0 ]]; then
        echo -e "${RED}⚠ TABLES NEED VACUUM: $high_dead_tables tables with >20% dead tuples${NC}"
    fi
    
    echo
}

# Main monitoring loop
main() {
    echo -e "${GREEN}Starting PostgreSQL Gaming Monitor (refresh every ${REFRESH_INTERVAL}s)${NC}"
    echo -e "${YELLOW}Press Ctrl+C to exit${NC}"
    echo
    
    while true; do
        clear_screen
        show_database_overview
        show_gaming_metrics
        show_performance_metrics
        show_connection_details
        show_top_queries
        show_index_usage
        show_table_statistics
        show_alerts
        
        echo -e "${CYAN}Next refresh in ${REFRESH_INTERVAL} seconds...${NC}"
        sleep "$REFRESH_INTERVAL"
    done
}

# Handle Ctrl+C
trap 'echo -e "\n${GREEN}Monitoring stopped.${NC}"; exit 0' INT

# Check if psql is available
if ! command -v psql &> /dev/null; then
    echo -e "${RED}Error: psql command not found. Please install PostgreSQL client.${NC}"
    exit 1
fi

# Check if bc is available (for floating point comparisons)
if ! command -v bc &> /dev/null; then
    echo -e "${YELLOW}Warning: bc command not found. Some alerts may not work properly.${NC}"
fi

# Start monitoring
main
