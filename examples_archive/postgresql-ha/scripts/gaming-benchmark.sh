#!/bin/bash

# PostgreSQL Gaming Performance Benchmark
# Comprehensive performance testing for Hokm game server database

set -euo pipefail

# Configuration
PGHOST="${PGHOST:-postgresql-primary}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-postgres}"
PGDATABASE="${PGDATABASE:-hokm_game}"
BENCHMARK_MODE="${1:-quick}"  # quick, full, stress, custom
CONCURRENT_USERS="${2:-50}"
TEST_DURATION="${3:-300}"     # seconds
LOG_FILE="/var/log/postgresql-gaming-benchmark.log"

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
    log "${CYAN}🎯 $*${NC}"
}

benchmark() {
    log "${MAGENTA}📊 $*${NC}"
}

# Execute SQL with timing
execute_timed() {
    local query="$1"
    local description="$2"
    local iterations="${3:-1}"
    
    info "Running: $description ($iterations iterations)"
    
    local start_time=$(date +%s.%3N)
    
    for ((i=1; i<=iterations; i++)); do
        psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -c "$query" > /dev/null 2>&1
    done
    
    local end_time=$(date +%s.%3N)
    local duration=$(echo "$end_time - $start_time" | bc)
    local avg_time=$(echo "scale=3; $duration / $iterations" | bc)
    
    benchmark "$description: ${avg_time}s avg (${duration}s total, $iterations iterations)"
    echo "$avg_time"
}

# Execute SQL and return result
execute_query() {
    local query="$1"
    psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -t -c "$query" 2>/dev/null | xargs
}

# Create test data if needed
create_test_data() {
    info "Checking and creating test data..."
    
    # Check if test data exists
    local player_count=$(execute_query "SELECT COUNT(*) FROM players WHERE username LIKE 'testplayer%'")
    
    if [[ "$player_count" -lt 1000 ]]; then
        info "Creating test players..."
        psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" << 'EOF'
DO $$
BEGIN
    FOR i IN 1..1000 LOOP
        INSERT INTO players (username, email, password_hash, is_active, created_at)
        VALUES (
            'testplayer' || i,
            'testplayer' || i || '@example.com',
            'hashed_password_' || i,
            true,
            NOW() - (random() * INTERVAL '30 days')
        ) ON CONFLICT (username) DO NOTHING;
    END LOOP;
END $$;
EOF
        success "Created test players"
    else
        success "Test players already exist ($player_count found)"
    fi
    
    # Create test game sessions
    local session_count=$(execute_query "SELECT COUNT(*) FROM game_sessions WHERE room_id LIKE 'TEST%'")
    
    if [[ "$session_count" -lt 100 ]]; then
        info "Creating test game sessions..."
        psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" << 'EOF'
DO $$
DECLARE
    player_ids INTEGER[];
    session_id INTEGER;
BEGIN
    -- Get test player IDs
    SELECT ARRAY(SELECT player_id FROM players WHERE username LIKE 'testplayer%' LIMIT 400) INTO player_ids;
    
    FOR i IN 1..100 LOOP
        INSERT INTO game_sessions (room_id, status, created_at, participant_count)
        VALUES (
            'TEST' || LPAD(i::text, 6, '0'),
            CASE WHEN i % 4 = 0 THEN 'completed' ELSE 'active' END,
            NOW() - (random() * INTERVAL '7 days'),
            4
        ) RETURNING session_id INTO session_id;
        
        -- Add participants
        FOR j IN 1..4 LOOP
            INSERT INTO game_participants (session_id, player_id, team, joined_at)
            VALUES (
                session_id,
                player_ids[((i-1)*4 + j)],
                CASE WHEN j <= 2 THEN 'team_a' ELSE 'team_b' END,
                NOW() - (random() * INTERVAL '7 days')
            );
        END LOOP;
        
        -- Add some game moves for completed games
        IF i % 4 = 0 THEN
            FOR k IN 1..52 LOOP  -- Full deck of moves
                INSERT INTO game_moves (session_id, player_id, move_type, move_data, timestamp)
                VALUES (
                    session_id,
                    player_ids[((i-1)*4 + (k % 4) + 1)],
                    'play_card',
                    '{"card": "' || (k % 13 + 1) || '", "suit": "' || 
                    (ARRAY['hearts', 'diamonds', 'clubs', 'spades'])[k % 4 + 1] || '"}',
                    NOW() - (random() * INTERVAL '6 days')
                );
            END LOOP;
        END IF;
    END LOOP;
END $$;
EOF
        success "Created test game sessions and moves"
    else
        success "Test game sessions already exist ($session_count found)"
    fi
}

# Benchmark basic CRUD operations
benchmark_crud_operations() {
    highlight "BENCHMARKING CRUD OPERATIONS"
    echo "================================"
    
    # Player lookup (most common operation)
    execute_timed "SELECT * FROM players WHERE username = 'testplayer1'" "Player lookup by username" 100
    
    # Game session lookup
    execute_timed "SELECT * FROM game_sessions WHERE room_id = 'TEST000001'" "Game session lookup by room_id" 100
    
    # Active games query
    execute_timed "SELECT * FROM game_sessions WHERE status = 'active' LIMIT 10" "Active games query" 50
    
    # Player game participation
    execute_timed "
    SELECT gs.room_id, gs.status, gp.team 
    FROM game_sessions gs 
    JOIN game_participants gp ON gs.session_id = gp.session_id 
    WHERE gp.player_id = 1" "Player game participation query" 50
    
    # Game state with participants
    execute_timed "
    SELECT gs.*, 
           json_agg(json_build_object('player_id', gp.player_id, 'team', gp.team)) as participants
    FROM game_sessions gs
    JOIN game_participants gp ON gs.session_id = gp.session_id
    WHERE gs.room_id = 'TEST000001'
    GROUP BY gs.session_id" "Complete game state query" 50
    
    echo
}

# Benchmark write operations
benchmark_write_operations() {
    highlight "BENCHMARKING WRITE OPERATIONS"
    echo "================================="
    
    # Game creation
    local create_time=$(execute_timed "
    WITH new_game AS (
        INSERT INTO game_sessions (room_id, status, created_at)
        VALUES ('BENCH' || extract(epoch from now()), 'waiting', NOW())
        RETURNING session_id
    )
    INSERT INTO game_participants (session_id, player_id, team, joined_at)
    SELECT session_id, 1, 'team_a', NOW() FROM new_game" "Game creation with participant" 20)
    
    # Move recording
    execute_timed "
    INSERT INTO game_moves (session_id, player_id, move_type, move_data, timestamp)
    VALUES (1, 1, 'play_card', '{\"card\": \"ace\", \"suit\": \"spades\"}', NOW())" "Move recording" 100
    
    # Player statistics update
    execute_timed "
    UPDATE player_statistics 
    SET games_played = games_played + 1, 
        last_game_at = NOW() 
    WHERE player_id = 1" "Player statistics update" 50
    
    # WebSocket connection management
    execute_timed "
    INSERT INTO websocket_connections (connection_id, player_id, status, connected_at, last_ping)
    VALUES (md5(random()::text), 1, 'active', NOW(), NOW())
    ON CONFLICT (connection_id) DO UPDATE SET last_ping = NOW()" "WebSocket connection upsert" 50
    
    echo
}

# Benchmark complex gaming queries
benchmark_complex_queries() {
    highlight "BENCHMARKING COMPLEX GAMING QUERIES"
    echo "====================================="
    
    # Leaderboard query
    execute_timed "
    SELECT p.username, ps.total_score, ps.games_won, ps.games_played,
           ROUND(ps.games_won * 100.0 / GREATEST(ps.games_played, 1), 2) as win_rate,
           ROW_NUMBER() OVER (ORDER BY ps.total_score DESC) as rank
    FROM players p
    JOIN player_statistics ps ON p.player_id = ps.player_id
    WHERE p.is_active = true AND ps.games_played >= 5
    ORDER BY ps.total_score DESC
    LIMIT 20" "Leaderboard query (top 20)" 20
    
    # Game history query
    execute_timed "
    SELECT gs.room_id, gs.status, gs.created_at, gs.completed_at,
           json_agg(json_build_object('username', p.username, 'team', gp.team)) as players
    FROM game_sessions gs
    JOIN game_participants gp ON gs.session_id = gp.session_id
    JOIN players p ON gp.player_id = p.player_id
    WHERE gs.created_at > NOW() - INTERVAL '24 hours'
    AND gs.status = 'completed'
    GROUP BY gs.session_id
    ORDER BY gs.completed_at DESC
    LIMIT 10" "Recent completed games query" 20
    
    # Player activity analysis
    execute_timed "
    SELECT p.username, 
           COUNT(DISTINCT gs.session_id) as games_today,
           MAX(gm.timestamp) as last_move,
           COUNT(gm.move_id) as moves_today
    FROM players p
    LEFT JOIN game_participants gp ON p.player_id = gp.player_id
    LEFT JOIN game_sessions gs ON gp.session_id = gs.session_id AND gs.created_at > CURRENT_DATE
    LEFT JOIN game_moves gm ON gs.session_id = gm.session_id AND gm.timestamp > CURRENT_DATE
    WHERE p.username LIKE 'testplayer%'
    GROUP BY p.player_id, p.username
    HAVING COUNT(DISTINCT gs.session_id) > 0
    ORDER BY games_today DESC
    LIMIT 10" "Player activity analysis" 10
    
    # Game move analysis
    execute_timed "
    SELECT gs.room_id,
           COUNT(gm.move_id) as total_moves,
           EXTRACT(EPOCH FROM (MAX(gm.timestamp) - MIN(gm.timestamp))) / 60 as game_duration_minutes,
           COUNT(gm.move_id) / GREATEST(EXTRACT(EPOCH FROM (MAX(gm.timestamp) - MIN(gm.timestamp))) / 60, 1) as moves_per_minute
    FROM game_sessions gs
    JOIN game_moves gm ON gs.session_id = gm.session_id
    WHERE gs.status = 'completed'
    AND gs.completed_at > NOW() - INTERVAL '24 hours'
    GROUP BY gs.session_id, gs.room_id
    HAVING COUNT(gm.move_id) > 20
    ORDER BY moves_per_minute DESC
    LIMIT 10" "Game move analysis" 10
    
    echo
}

# Benchmark concurrent operations
benchmark_concurrent_operations() {
    highlight "BENCHMARKING CONCURRENT OPERATIONS"
    echo "==================================="
    
    info "Simulating $CONCURRENT_USERS concurrent users for $TEST_DURATION seconds"
    
    # Create a temporary SQL script for concurrent testing
    cat << 'EOF' > /tmp/concurrent_test.sql
-- Simulate typical gaming operations
\set player_id random(1, 1000)
\set room_num random(1, 100)

-- Player login check
SELECT player_id, username FROM players WHERE player_id = :player_id;

-- Check for active games
SELECT gs.room_id, gs.status FROM game_sessions gs
JOIN game_participants gp ON gs.session_id = gp.session_id
WHERE gp.player_id = :player_id AND gs.status IN ('waiting', 'active');

-- Look for available games
SELECT room_id, participant_count FROM game_sessions 
WHERE status = 'waiting' AND participant_count < 4 
ORDER BY created_at LIMIT 5;

-- Simulate move recording (20% chance)
\if random(1, 5) = 1
INSERT INTO game_moves (session_id, player_id, move_type, move_data, timestamp)
VALUES (1, :player_id, 'play_card', '{"card": "test"}', NOW());
\endif

-- Update last seen (heartbeat)
UPDATE websocket_connections SET last_ping = NOW() 
WHERE player_id = :player_id AND status = 'active';
EOF
    
    # Run pgbench concurrent test
    info "Starting concurrent benchmark..."
    local start_time=$(date +%s)
    
    if command -v pgbench &> /dev/null; then
        pgbench -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" \
                -c "$CONCURRENT_USERS" -j 4 -T "$TEST_DURATION" \
                -f /tmp/concurrent_test.sql -r 2>&1 | tee -a "$LOG_FILE"
    else
        warning "pgbench not available, skipping concurrent test"
    fi
    
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    
    # Clean up
    rm -f /tmp/concurrent_test.sql
    
    success "Concurrent benchmark completed in ${duration}s"
    echo
}

# Benchmark index performance
benchmark_index_performance() {
    highlight "BENCHMARKING INDEX PERFORMANCE"
    echo "==============================="
    
    # Test with and without indexes
    info "Testing queries with existing indexes..."
    
    # Indexed query
    execute_timed "SELECT * FROM players WHERE username = 'testplayer500'" "Indexed player lookup" 100
    
    # Indexed join query
    execute_timed "
    SELECT gs.room_id, p.username 
    FROM game_sessions gs 
    JOIN game_participants gp ON gs.session_id = gp.session_id 
    JOIN players p ON gp.player_id = p.player_id 
    WHERE gs.status = 'active'" "Indexed join query" 20
    
    # Range query on timestamp
    execute_timed "
    SELECT COUNT(*) FROM game_moves 
    WHERE timestamp > NOW() - INTERVAL '1 day'" "Timestamp range query" 20
    
    echo
}

# Analyze query performance
analyze_query_performance() {
    highlight "QUERY PERFORMANCE ANALYSIS"
    echo "=========================="
    
    info "Top 10 slowest queries during benchmark:"
    psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -c "
    SELECT 
        LEFT(query, 80) as query_snippet,
        calls,
        ROUND(mean_exec_time::numeric, 2) as avg_time_ms,
        ROUND(total_exec_time::numeric, 2) as total_time_ms
    FROM pg_stat_statements 
    WHERE calls > 5
    ORDER BY mean_exec_time DESC 
    LIMIT 10;
    "
    
    echo
    
    info "Cache hit ratio during benchmark:"
    psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -c "
    SELECT 
        'Buffer Cache Hit Ratio' as metric,
        ROUND((sum(blks_hit) * 100.0 / sum(blks_hit + blks_read))::numeric, 2) as percentage
    FROM pg_stat_database 
    WHERE datname = '$PGDATABASE';
    "
    
    echo
    
    info "Index usage during benchmark:"
    psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -c "
    SELECT 
        tablename,
        indexname,
        idx_scan,
        idx_tup_read,
        idx_tup_fetch
    FROM pg_stat_user_indexes 
    WHERE tablename IN ('players', 'game_sessions', 'game_participants', 'game_moves')
    AND idx_scan > 0
    ORDER BY idx_scan DESC;
    "
    
    echo
}

# Generate benchmark report
generate_benchmark_report() {
    local report_file="/tmp/gaming-benchmark-report.html"
    
    info "Generating benchmark report: $report_file"
    
    cat << EOF > "$report_file"
<!DOCTYPE html>
<html>
<head>
    <title>PostgreSQL Gaming Benchmark Report</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; }
        .header { background: #f5f5f5; padding: 20px; border-radius: 5px; }
        .section { margin: 20px 0; }
        .metric { background: #e8f4f8; padding: 10px; margin: 5px 0; border-left: 4px solid #007acc; }
        .warning { background: #fff3cd; border-left: 4px solid #ffc107; }
        .success { background: #d4edda; border-left: 4px solid #28a745; }
        table { border-collapse: collapse; width: 100%; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        th { background-color: #f2f2f2; }
        pre { background: #f8f9fa; padding: 15px; overflow-x: auto; }
    </style>
</head>
<body>
    <div class="header">
        <h1>🎮 PostgreSQL Gaming Benchmark Report</h1>
        <p><strong>Generated:</strong> $(date)</p>
        <p><strong>Database:</strong> $PGDATABASE@$PGHOST:$PGPORT</p>
        <p><strong>Benchmark Mode:</strong> $BENCHMARK_MODE</p>
        <p><strong>Concurrent Users:</strong> $CONCURRENT_USERS</p>
        <p><strong>Test Duration:</strong> ${TEST_DURATION}s</p>
    </div>

    <div class="section">
        <h2>📊 Performance Summary</h2>
        <div class="metric">
            <strong>Database Size:</strong> $(execute_query "SELECT pg_size_pretty(pg_database_size('$PGDATABASE'))")
        </div>
        <div class="metric">
            <strong>Cache Hit Ratio:</strong> $(execute_query "SELECT ROUND((sum(blks_hit) * 100.0 / sum(blks_hit + blks_read))::numeric, 2) || '%' FROM pg_stat_database WHERE datname = '$PGDATABASE'")
        </div>
        <div class="metric">
            <strong>Active Connections:</strong> $(execute_query "SELECT COUNT(*) FROM pg_stat_activity WHERE datname = '$PGDATABASE'")
        </div>
        <div class="metric">
            <strong>Total Queries:</strong> $(execute_query "SELECT SUM(calls) FROM pg_stat_statements")
        </div>
    </div>

    <div class="section">
        <h2>🔥 Performance Hotspots</h2>
        <p>Queries that may need optimization:</p>
        <pre>$(psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -c "
        SELECT 
            LEFT(query, 100) as query_snippet,
            calls,
            ROUND(mean_exec_time::numeric, 2) as avg_time_ms
        FROM pg_stat_statements 
        WHERE mean_exec_time > 50 AND calls > 5
        ORDER BY mean_exec_time DESC 
        LIMIT 5;" --no-align --tuples-only 2>/dev/null || echo "No slow queries found")</pre>
    </div>

    <div class="section">
        <h2>💡 Recommendations</h2>
        <div class="$([ $(execute_query "SELECT ROUND((sum(blks_hit) * 100.0 / sum(blks_hit + blks_read))::numeric, 2) FROM pg_stat_database WHERE datname = '$PGDATABASE'" | cut -d. -f1) -lt 95 ] && echo "warning" || echo "success")">
            Cache hit ratio: Consider increasing shared_buffers if below 95%
        </div>
        <div class="metric">
            Index usage: Monitor unused indexes and create missing ones for gaming queries
        </div>
        <div class="metric">
            Query optimization: Focus on queries with high execution time and frequency
        </div>
        <div class="metric">
            Connection pooling: Use pgBouncer for high-concurrency gaming workloads
        </div>
    </div>

    <div class="section">
        <h2>📈 Next Steps</h2>
        <ol>
            <li>Review slow queries and add appropriate indexes</li>
            <li>Consider query optimization for frequently used gaming operations</li>
            <li>Monitor performance during peak gaming hours</li>
            <li>Implement connection pooling if not already in use</li>
            <li>Set up automated performance monitoring</li>
        </ol>
    </div>

    <div class="section">
        <p><em>Full benchmark log: $LOG_FILE</em></p>
    </div>
</body>
</html>
EOF
    
    success "Benchmark report generated: $report_file"
    info "Open the report in a web browser to view detailed results"
}

# Cleanup test data
cleanup_test_data() {
    if [[ "${CLEANUP_TEST_DATA:-false}" == "true" ]]; then
        info "Cleaning up test data..."
        psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" << 'EOF'
DELETE FROM game_moves WHERE session_id IN (SELECT session_id FROM game_sessions WHERE room_id LIKE 'TEST%' OR room_id LIKE 'BENCH%');
DELETE FROM game_participants WHERE session_id IN (SELECT session_id FROM game_sessions WHERE room_id LIKE 'TEST%' OR room_id LIKE 'BENCH%');
DELETE FROM game_sessions WHERE room_id LIKE 'TEST%' OR room_id LIKE 'BENCH%';
DELETE FROM websocket_connections WHERE player_id IN (SELECT player_id FROM players WHERE username LIKE 'testplayer%');
DELETE FROM player_statistics WHERE player_id IN (SELECT player_id FROM players WHERE username LIKE 'testplayer%');
DELETE FROM players WHERE username LIKE 'testplayer%';
EOF
        success "Test data cleaned up"
    fi
}

# Main benchmark function
main() {
    log "Starting PostgreSQL Gaming Benchmark (mode: $BENCHMARK_MODE)"
    
    # Create test data
    create_test_data
    
    # Reset pg_stat_statements
    execute_query "SELECT pg_stat_statements_reset();" > /dev/null 2>&1 || true
    
    case "$BENCHMARK_MODE" in
        "quick")
            benchmark_crud_operations
            benchmark_write_operations
            ;;
        "full")
            benchmark_crud_operations
            benchmark_write_operations
            benchmark_complex_queries
            benchmark_index_performance
            ;;
        "stress")
            benchmark_crud_operations
            benchmark_write_operations
            benchmark_complex_queries
            benchmark_concurrent_operations
            ;;
        "custom")
            # Allow for custom benchmark configuration
            benchmark_crud_operations
            benchmark_write_operations
            if [[ "$TEST_DURATION" -gt 60 ]]; then
                benchmark_concurrent_operations
            fi
            ;;
        *)
            error "Unknown benchmark mode: $BENCHMARK_MODE"
            echo "Available modes: quick, full, stress, custom"
            exit 1
            ;;
    esac
    
    # Analyze results
    analyze_query_performance
    
    # Generate report
    generate_benchmark_report
    
    # Cleanup if requested
    cleanup_test_data
    
    success "Gaming benchmark completed!"
}

# Show help
show_help() {
    echo "PostgreSQL Gaming Performance Benchmark"
    echo
    echo "Usage: $0 [mode] [concurrent_users] [duration_seconds]"
    echo
    echo "Modes:"
    echo "  quick      Basic CRUD operations (default)"
    echo "  full       CRUD + complex queries + index tests"
    echo "  stress     Full benchmark + concurrent load testing"
    echo "  custom     Configurable benchmark"
    echo
    echo "Parameters:"
    echo "  concurrent_users   Number of concurrent connections (default: 50)"
    echo "  duration_seconds   Test duration for concurrent tests (default: 300)"
    echo
    echo "Environment Variables:"
    echo "  PGHOST               PostgreSQL host (default: postgresql-primary)"
    echo "  PGPORT               PostgreSQL port (default: 5432)"
    echo "  PGUSER               PostgreSQL user (default: postgres)"
    echo "  PGDATABASE           PostgreSQL database (default: hokm_game)"
    echo "  CLEANUP_TEST_DATA    Set to 'true' to cleanup test data after benchmark"
    echo
    echo "Examples:"
    echo "  $0                           # Quick benchmark"
    echo "  $0 full                      # Full benchmark"
    echo "  $0 stress 100 600            # Stress test with 100 users for 10 minutes"
    echo "  CLEANUP_TEST_DATA=true $0    # Run benchmark and cleanup test data"
    echo
}

# Check arguments
if [[ "${1:-}" == "--help" ]] || [[ "${1:-}" == "-h" ]]; then
    show_help
    exit 0
fi

# Validate parameters
if ! [[ "$CONCURRENT_USERS" =~ ^[0-9]+$ ]] || [[ "$CONCURRENT_USERS" -lt 1 ]]; then
    error "Invalid concurrent_users: $CONCURRENT_USERS (must be positive integer)"
    exit 1
fi

if ! [[ "$TEST_DURATION" =~ ^[0-9]+$ ]] || [[ "$TEST_DURATION" -lt 10 ]]; then
    error "Invalid duration_seconds: $TEST_DURATION (must be at least 10)"
    exit 1
fi

# Check dependencies
if ! command -v psql &> /dev/null; then
    error "psql command not found. Please install PostgreSQL client."
    exit 1
fi

if ! command -v bc &> /dev/null; then
    error "bc command not found. Please install bc for calculations."
    exit 1
fi

# Test database connection
if ! psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -c "SELECT 1;" > /dev/null 2>&1; then
    error "Cannot connect to PostgreSQL database"
    error "Check connection parameters: $PGUSER@$PGHOST:$PGPORT/$PGDATABASE"
    exit 1
fi

# Run benchmark
main
