#!/bin/bash

# Dynamic PostgreSQL Performance Tuner for Hokm Game Server
# Automatically adjusts database settings based on current workload and system resources

set -euo pipefail

# Configuration
PGHOST="${PGHOST:-postgresql-primary}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-postgres}"
PGDATABASE="${PGDATABASE:-hokm_game}"
LOG_FILE="/var/log/postgresql-tuner.log"
DRY_RUN="${1:-false}"  # Set to 'true' to only show recommendations without applying

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
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

recommend() {
    log "${CYAN}💡 $*${NC}"
}

# Execute SQL query
execute_query() {
    local query="$1"
    psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -t -c "$query" 2>/dev/null || echo "N/A"
}

# Apply configuration change
apply_config() {
    local setting="$1"
    local value="$2"
    local reason="$3"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        recommend "WOULD SET $setting = '$value' ($reason)"
        return
    fi
    
    info "Setting $setting = '$value' ($reason)"
    
    if execute_query "ALTER SYSTEM SET $setting = '$value';" > /dev/null; then
        success "Applied: $setting = '$value'"
        echo "-- $reason" >> "$LOG_FILE"
    else
        error "Failed to set $setting = '$value'"
    fi
}

# Get system memory in GB
get_system_memory() {
    local memory_kb
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        memory_kb=$(grep MemTotal /proc/meminfo | awk '{print $2}')
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        memory_kb=$(sysctl -n hw.memsize | awk '{print $1/1024}')
    else
        memory_kb=8388608  # Default 8GB
    fi
    echo $((memory_kb / 1024 / 1024))
}

# Analyze current workload
analyze_workload() {
    info "Analyzing current database workload..."
    
    # Get basic metrics
    local connections=$(execute_query "SELECT COUNT(*) FROM pg_stat_activity WHERE datname = '$PGDATABASE'")
    local active_connections=$(execute_query "SELECT COUNT(*) FROM pg_stat_activity WHERE datname = '$PGDATABASE' AND state = 'active'")
    local active_games=$(execute_query "SELECT COUNT(*) FROM game_sessions WHERE status IN ('waiting', 'active', 'in_progress')" 2>/dev/null || echo "0")
    local online_players=$(execute_query "SELECT COUNT(DISTINCT player_id) FROM websocket_connections WHERE status = 'active'" 2>/dev/null || echo "0")
    local queries_per_sec=$(execute_query "SELECT ROUND(SUM(calls) / GREATEST(EXTRACT(EPOCH FROM (NOW() - stats_reset)), 1), 1) FROM pg_stat_statements, pg_stat_database WHERE pg_stat_database.datname = '$PGDATABASE'")
    
    # Calculate workload characteristics
    local workload_type="low"
    if [[ "$active_games" -gt 50 ]] || [[ "$online_players" -gt 200 ]] || [[ "$queries_per_sec" -gt 100 ]]; then
        workload_type="high"
    elif [[ "$active_games" -gt 10 ]] || [[ "$online_players" -gt 50 ]] || [[ "$queries_per_sec" -gt 50 ]]; then
        workload_type="medium"
    fi
    
    echo "$connections,$active_connections,$active_games,$online_players,$queries_per_sec,$workload_type"
}

# Tune memory settings
tune_memory_settings() {
    local workload_info="$1"
    local workload_type=$(echo "$workload_info" | cut -d',' -f6)
    local system_memory=$(get_system_memory)
    
    info "Tuning memory settings for $workload_type workload (System RAM: ${system_memory}GB)"
    
    # shared_buffers
    local shared_buffers
    case "$workload_type" in
        "high")
            shared_buffers=$((system_memory * 1024 / 3))  # 33% of RAM
            ;;
        "medium")
            shared_buffers=$((system_memory * 1024 / 4))  # 25% of RAM
            ;;
        *)
            shared_buffers=$((system_memory * 1024 / 5))  # 20% of RAM
            ;;
    esac
    apply_config "shared_buffers" "${shared_buffers}MB" "Optimized for $workload_type gaming workload"
    
    # effective_cache_size
    local effective_cache_size=$((system_memory * 1024 * 3 / 4))  # 75% of RAM
    apply_config "effective_cache_size" "${effective_cache_size}MB" "Total system cache available"
    
    # work_mem
    local work_mem
    case "$workload_type" in
        "high")
            work_mem=32  # Higher for complex queries
            ;;
        "medium")
            work_mem=16
            ;;
        *)
            work_mem=8
            ;;
    esac
    apply_config "work_mem" "${work_mem}MB" "Memory for each query operation"
    
    # maintenance_work_mem
    local maintenance_work_mem=$((system_memory * 1024 / 16))  # 6.25% of RAM, max 2GB
    if [[ $maintenance_work_mem -gt 2048 ]]; then
        maintenance_work_mem=2048
    fi
    apply_config "maintenance_work_mem" "${maintenance_work_mem}MB" "Memory for maintenance operations"
}

# Tune connection settings
tune_connection_settings() {
    local workload_info="$1"
    local connections=$(echo "$workload_info" | cut -d',' -f1)
    local active_connections=$(echo "$workload_info" | cut -d',' -f2)
    local workload_type=$(echo "$workload_info" | cut -d',' -f6)
    
    info "Tuning connection settings (Current: $connections total, $active_connections active)"
    
    # max_connections
    local max_connections
    case "$workload_type" in
        "high")
            max_connections=300
            ;;
        "medium")
            max_connections=200
            ;;
        *)
            max_connections=100
            ;;
    esac
    
    if [[ "$connections" -gt $((max_connections * 80 / 100)) ]]; then
        max_connections=$((connections * 120 / 100))  # 20% buffer above current
        warning "Current connections ($connections) are high, increasing max_connections"
    fi
    
    apply_config "max_connections" "$max_connections" "Optimized for $workload_type workload"
    
    # Connection timeouts for gaming
    apply_config "statement_timeout" "30s" "Prevent long-running queries in gaming"
    apply_config "idle_in_transaction_session_timeout" "5min" "Clean up idle gaming sessions"
}

# Tune WAL and checkpoint settings
tune_wal_settings() {
    local workload_info="$1"
    local workload_type=$(echo "$workload_info" | cut -d',' -f6)
    local queries_per_sec=$(echo "$workload_info" | cut -d',' -f5)
    
    info "Tuning WAL and checkpoint settings for $workload_type workload (${queries_per_sec} queries/sec)"
    
    # WAL settings based on write intensity
    if [[ "$workload_type" == "high" ]]; then
        apply_config "max_wal_size" "4GB" "High write workload"
        apply_config "min_wal_size" "1GB" "High write workload"
        apply_config "wal_buffers" "64MB" "High write workload"
        apply_config "checkpoint_completion_target" "0.9" "Spread checkpoint I/O"
        apply_config "checkpoint_timeout" "10min" "More frequent checkpoints for high activity"
    elif [[ "$workload_type" == "medium" ]]; then
        apply_config "max_wal_size" "2GB" "Medium write workload"
        apply_config "min_wal_size" "512MB" "Medium write workload"
        apply_config "wal_buffers" "32MB" "Medium write workload"
        apply_config "checkpoint_completion_target" "0.7" "Balanced checkpoint I/O"
        apply_config "checkpoint_timeout" "15min" "Standard checkpoint frequency"
    else
        apply_config "max_wal_size" "1GB" "Low write workload"
        apply_config "min_wal_size" "256MB" "Low write workload"
        apply_config "wal_buffers" "16MB" "Low write workload"
        apply_config "checkpoint_completion_target" "0.5" "Standard checkpoint I/O"
        apply_config "checkpoint_timeout" "30min" "Less frequent checkpoints"
    fi
    
    # Enable WAL compression for efficiency
    apply_config "wal_compression" "on" "Reduce WAL size"
}

# Tune query planner settings
tune_planner_settings() {
    local workload_info="$1"
    local workload_type=$(echo "$workload_info" | cut -d',' -f6)
    
    info "Tuning query planner for gaming workload patterns"
    
    # Gaming workloads typically have good SSD storage
    apply_config "random_page_cost" "1.1" "SSD storage optimization"
    apply_config "seq_page_cost" "1.0" "SSD storage optimization"
    
    # CPU costs for gaming queries
    apply_config "cpu_tuple_cost" "0.01" "Gaming query optimization"
    apply_config "cpu_index_tuple_cost" "0.005" "Gaming query optimization"
    apply_config "cpu_operator_cost" "0.0025" "Gaming query optimization"
    
    # Statistics for better planning
    local stats_target
    case "$workload_type" in
        "high")
            stats_target=200  # More detailed statistics
            ;;
        "medium")
            stats_target=100
            ;;
        *)
            stats_target=50
            ;;
    esac
    apply_config "default_statistics_target" "$stats_target" "Query planning for $workload_type workload"
    
    # Parallelism settings
    if [[ "$workload_type" == "high" ]]; then
        apply_config "max_parallel_workers_per_gather" "4" "High workload parallelism"
        apply_config "max_parallel_workers" "8" "High workload parallelism"
        apply_config "parallel_tuple_cost" "0.1" "Gaming parallel query cost"
    else
        apply_config "max_parallel_workers_per_gather" "2" "Standard parallelism"
        apply_config "max_parallel_workers" "4" "Standard parallelism"
    fi
}

# Tune gaming-specific settings
tune_gaming_settings() {
    local workload_info="$1"
    local workload_type=$(echo "$workload_info" | cut -d',' -f6)
    
    info "Applying gaming-specific optimizations"
    
    # Lock settings for concurrent gaming operations
    apply_config "deadlock_timeout" "1s" "Quick deadlock detection for gaming"
    apply_config "lock_timeout" "10s" "Prevent lock waits in gaming"
    
    # Logging for gaming performance monitoring
    apply_config "log_min_duration_statement" "100ms" "Log slow gaming queries"
    apply_config "log_checkpoints" "on" "Monitor checkpoint performance"
    apply_config "log_connections" "off" "Reduce log noise from frequent connections"
    apply_config "log_disconnections" "off" "Reduce log noise from frequent disconnections"
    
    # Background writer for write-heavy gaming
    if [[ "$workload_type" == "high" ]]; then
        apply_config "bgwriter_delay" "100ms" "More frequent background writes"
        apply_config "bgwriter_lru_maxpages" "200" "More aggressive background writing"
        apply_config "bgwriter_lru_multiplier" "4.0" "More aggressive background writing"
    fi
    
    # Autovacuum tuning for gaming tables
    apply_config "autovacuum_naptime" "30s" "More frequent autovacuum for gaming"
    apply_config "autovacuum_vacuum_threshold" "25" "Lower threshold for small gaming tables"
    apply_config "autovacuum_analyze_threshold" "25" "Lower threshold for small gaming tables"
    apply_config "autovacuum_vacuum_scale_factor" "0.1" "More aggressive vacuum for gaming"
    apply_config "autovacuum_analyze_scale_factor" "0.05" "More aggressive analyze for gaming"
}

# Check for specific performance issues
check_performance_issues() {
    info "Checking for specific performance issues..."
    
    # Check cache hit ratio
    local cache_hit=$(execute_query "SELECT ROUND(sum(blks_hit)*100.0/sum(blks_hit+blks_read), 2) FROM pg_stat_database WHERE datname = '$PGDATABASE'")
    if (( $(echo "$cache_hit < 95" | bc -l 2>/dev/null || echo "0") )); then
        warning "Cache hit ratio is ${cache_hit}% (target: >95%)"
        recommend "Consider increasing shared_buffers or effective_cache_size"
    fi
    
    # Check for unused indexes
    local unused_indexes=$(execute_query "SELECT COUNT(*) FROM pg_stat_user_indexes WHERE idx_scan = 0")
    if [[ "$unused_indexes" -gt 0 ]]; then
        warning "Found $unused_indexes unused indexes"
        recommend "Review and drop unused indexes to improve write performance"
    fi
    
    # Check for tables needing vacuum
    local tables_need_vacuum=$(execute_query "SELECT COUNT(*) FROM pg_stat_user_tables WHERE n_dead_tup > 1000 AND n_dead_tup * 100.0 / GREATEST(n_live_tup + n_dead_tup, 1) > 10")
    if [[ "$tables_need_vacuum" -gt 0 ]]; then
        warning "$tables_need_vacuum tables need vacuum"
        recommend "Run vacuum on tables with high dead tuple ratios"
    fi
    
    # Check for long-running queries
    local long_queries=$(execute_query "SELECT COUNT(*) FROM pg_stat_activity WHERE state = 'active' AND query_start < NOW() - INTERVAL '1 minute'")
    if [[ "$long_queries" -gt 0 ]]; then
        warning "$long_queries queries running longer than 1 minute"
        recommend "Investigate long-running queries that may impact gaming performance"
    fi
}

# Generate performance report
generate_report() {
    local workload_info="$1"
    
    info "Generating performance tuning report..."
    
    cat << EOF > "/tmp/postgresql-tuning-report.txt"

PostgreSQL Gaming Performance Tuning Report
==========================================
Generated: $(date)
Database: $PGDATABASE
Host: $PGHOST:$PGPORT

Current Workload Analysis:
- Total Connections: $(echo "$workload_info" | cut -d',' -f1)
- Active Connections: $(echo "$workload_info" | cut -d',' -f2)
- Active Games: $(echo "$workload_info" | cut -d',' -f3)
- Online Players: $(echo "$workload_info" | cut -d',' -f4)
- Queries/Second: $(echo "$workload_info" | cut -d',' -f5)
- Workload Type: $(echo "$workload_info" | cut -d',' -f6)

System Information:
- System Memory: $(get_system_memory)GB
- Tuning Mode: $([ "$DRY_RUN" == "true" ] && echo "DRY RUN" || echo "APPLIED")

$(if [[ "$DRY_RUN" != "true" ]]; then
    echo "Configuration changes have been applied."
    echo "Run 'SELECT pg_reload_conf();' to reload configuration."
    echo "Some changes may require a database restart."
else
    echo "This was a dry run. Use './$(basename $0) false' to apply changes."
fi)

For detailed logs, see: $LOG_FILE

EOF
    
    success "Report generated: /tmp/postgresql-tuning-report.txt"
    cat "/tmp/postgresql-tuning-report.txt"
}

# Main function
main() {
    log "Starting PostgreSQL Gaming Performance Tuning"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        warning "Running in DRY RUN mode - no changes will be applied"
    fi
    
    # Analyze current workload
    local workload_info
    workload_info=$(analyze_workload)
    
    if [[ "$workload_info" == *"N/A"* ]]; then
        error "Failed to analyze workload. Check database connection."
        exit 1
    fi
    
    info "Workload analysis: $workload_info"
    
    # Apply tuning based on workload
    tune_memory_settings "$workload_info"
    tune_connection_settings "$workload_info"
    tune_wal_settings "$workload_info"
    tune_planner_settings "$workload_info"
    tune_gaming_settings "$workload_info"
    
    # Check for issues
    check_performance_issues
    
    # Generate report
    generate_report "$workload_info"
    
    if [[ "$DRY_RUN" != "true" ]]; then
        info "Reloading PostgreSQL configuration..."
        execute_query "SELECT pg_reload_conf();" > /dev/null
        success "Configuration reloaded. Some changes may require a restart."
    fi
    
    success "Performance tuning completed"
}

# Help function
show_help() {
    echo "PostgreSQL Gaming Performance Tuner"
    echo
    echo "Usage: $0 [dry_run]"
    echo
    echo "Arguments:"
    echo "  dry_run    Set to 'true' for dry run mode (default: false)"
    echo
    echo "Environment Variables:"
    echo "  PGHOST     PostgreSQL host (default: postgresql-primary)"
    echo "  PGPORT     PostgreSQL port (default: 5432)"
    echo "  PGUSER     PostgreSQL user (default: postgres)"
    echo "  PGDATABASE PostgreSQL database (default: hokm_game)"
    echo
    echo "Examples:"
    echo "  $0              # Apply tuning changes"
    echo "  $0 true         # Dry run mode (show recommendations only)"
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

if ! command -v bc &> /dev/null; then
    warning "bc command not found. Some calculations may not work properly."
fi

# Run main function
main
