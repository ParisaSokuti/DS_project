# PostgreSQL Performance Optimization for Hokm Game Server

## Overview

This document provides comprehensive performance optimization strategies specifically designed for the Hokm card game server. The optimizations focus on minimizing query latency for real-time gaming operations while maintaining scalability for concurrent players.

## Gaming Workload Analysis

### Typical Hokm Game Query Patterns

1. **High-Frequency Operations** (Sub-10ms target)
   - Player authentication and session validation
   - Game state retrieval and updates
   - Card play validation and recording
   - Turn management and game phase transitions

2. **Medium-Frequency Operations** (Sub-50ms target)
   - Game room creation and joining
   - Player statistics updates
   - Game completion and scoring
   - Leaderboard queries

3. **Low-Frequency Operations** (Sub-200ms target)
   - Historical game analysis
   - Player profile aggregations
   - Administrative queries
   - Backup and maintenance operations

### Performance Targets

- **Active Game Operations**: < 5ms average latency
- **Game Setup/Teardown**: < 25ms average latency
- **Analytics Queries**: < 100ms average latency
- **Concurrent Connections**: 1000+ simultaneous players
- **Throughput**: 10,000+ game operations per second

## Index Optimization Strategy

### 1. Core Gaming Indexes

```sql
-- Game Sessions - Primary access patterns
CREATE INDEX CONCURRENTLY idx_game_sessions_active_lookup 
ON game_sessions (status, room_id) 
WHERE status IN ('waiting', 'active', 'in_progress');

CREATE INDEX CONCURRENTLY idx_game_sessions_player_active 
ON game_sessions (player_id, status, created_at DESC) 
WHERE status IN ('active', 'in_progress');

CREATE INDEX CONCURRENTLY idx_game_sessions_recent 
ON game_sessions (created_at DESC, status) 
WHERE created_at > NOW() - INTERVAL '24 hours';

-- Game Participants - Join operations
CREATE INDEX CONCURRENTLY idx_game_participants_room_player 
ON game_participants (room_id, player_id) 
INCLUDE (team, position, joined_at);

CREATE INDEX CONCURRENTLY idx_game_participants_active_games 
ON game_participants (player_id, game_status) 
WHERE game_status IN ('active', 'in_progress');

-- Game Moves - Card play operations
CREATE INDEX CONCURRENTLY idx_game_moves_game_sequence 
ON game_moves (game_id, move_sequence) 
INCLUDE (player_id, move_type, move_data);

CREATE INDEX CONCURRENTLY idx_game_moves_recent_by_game 
ON game_moves (game_id, created_at DESC) 
WHERE created_at > NOW() - INTERVAL '6 hours';

CREATE INDEX CONCURRENTLY idx_game_moves_player_recent 
ON game_moves (player_id, created_at DESC) 
WHERE created_at > NOW() - INTERVAL '1 hour';

-- Player Statistics - Leaderboard queries
CREATE INDEX CONCURRENTLY idx_player_stats_ranking 
ON player_stats (total_score DESC, games_won DESC, games_played ASC) 
WHERE active = true;

CREATE INDEX CONCURRENTLY idx_player_stats_recent_activity 
ON player_stats (last_game_at DESC) 
WHERE last_game_at > NOW() - INTERVAL '30 days';

-- WebSocket Connections - Session management
CREATE INDEX CONCURRENTLY idx_websocket_connections_active 
ON websocket_connections (connection_id, status) 
WHERE status = 'active';

CREATE INDEX CONCURRENTLY idx_websocket_connections_player_room 
ON websocket_connections (player_id, room_id, status) 
WHERE status = 'active';
```

### 2. Composite Indexes for Complex Queries

```sql
-- Multi-column indexes for common WHERE clauses
CREATE INDEX CONCURRENTLY idx_games_status_type_created 
ON game_sessions (status, game_type, created_at DESC) 
WHERE status IN ('completed', 'active');

CREATE INDEX CONCURRENTLY idx_moves_game_round_trick 
ON game_moves (game_id, round_number, trick_number, move_sequence) 
WHERE move_type = 'play_card';

-- Covering indexes to avoid table lookups
CREATE INDEX CONCURRENTLY idx_players_auth_covering 
ON players (username, email) 
INCLUDE (id, password_hash, is_active, created_at);

CREATE INDEX CONCURRENTLY idx_game_state_covering 
ON game_sessions (room_id) 
INCLUDE (status, current_phase, current_player, game_data, updated_at);
```

### 3. Partial Indexes for Gaming-Specific Patterns

```sql
-- Only index active/recent data
CREATE INDEX CONCURRENTLY idx_active_games_only 
ON game_sessions (room_id, status, created_at) 
WHERE status IN ('waiting', 'active', 'in_progress') 
AND created_at > NOW() - INTERVAL '12 hours';

-- Index only winning games for leaderboards
CREATE INDEX CONCURRENTLY idx_winning_games 
ON game_participants (player_id, game_id, score) 
WHERE game_result = 'won' 
AND score > 0;

-- Index only recent player activity
CREATE INDEX CONCURRENTLY idx_recent_player_activity 
ON player_activity_log (player_id, activity_type, created_at DESC) 
WHERE created_at > NOW() - INTERVAL '7 days';
```

## Query Optimization Examples

### 1. Game State Retrieval (Critical Path)

```sql
-- BEFORE: Slow game state query
SELECT gs.*, gp.player_id, gp.team, gp.position, p.username
FROM game_sessions gs
LEFT JOIN game_participants gp ON gs.id = gp.game_id
LEFT JOIN players p ON gp.player_id = p.id
WHERE gs.room_id = 'ROOM123';

-- AFTER: Optimized with covering index and JSON aggregation
WITH game_info AS (
    SELECT id, room_id, status, current_phase, current_player, 
           game_data, created_at, updated_at
    FROM game_sessions 
    WHERE room_id = 'ROOM123'
),
participants AS (
    SELECT game_id,
           json_agg(
               json_build_object(
                   'player_id', gp.player_id,
                   'username', p.username,
                   'team', gp.team,
                   'position', gp.position
               ) ORDER BY gp.position
           ) as players
    FROM game_participants gp
    JOIN players p ON gp.player_id = p.id
    WHERE gp.game_id = (SELECT id FROM game_info)
    GROUP BY game_id
)
SELECT gi.*, p.players
FROM game_info gi
LEFT JOIN participants p ON gi.id = p.game_id;

-- Index support
CREATE INDEX CONCURRENTLY idx_game_state_optimized 
ON game_sessions (room_id) 
INCLUDE (id, status, current_phase, current_player, game_data, created_at, updated_at);
```

### 2. Active Games Lookup

```sql
-- BEFORE: Inefficient active games query
SELECT * FROM game_sessions 
WHERE status = 'active' 
ORDER BY created_at DESC;

-- AFTER: Optimized with partial index
SELECT room_id, status, current_phase, player_count, created_at
FROM game_sessions 
WHERE status = 'active' 
AND created_at > NOW() - INTERVAL '6 hours'
ORDER BY created_at DESC
LIMIT 50;

-- Supporting index
CREATE INDEX CONCURRENTLY idx_active_games_recent 
ON game_sessions (created_at DESC) 
WHERE status = 'active' 
AND created_at > NOW() - INTERVAL '6 hours';
```

### 3. Player Game History

```sql
-- BEFORE: Slow player history
SELECT * FROM game_sessions gs
JOIN game_participants gp ON gs.id = gp.game_id
WHERE gp.player_id = 12345
ORDER BY gs.created_at DESC;

-- AFTER: Optimized with denormalized approach
WITH player_games AS (
    SELECT 
        gs.room_id,
        gs.status,
        gs.game_type,
        gs.created_at,
        gp.team,
        gp.score,
        gp.game_result,
        ROW_NUMBER() OVER (ORDER BY gs.created_at DESC) as rn
    FROM game_sessions gs
    JOIN game_participants gp ON gs.id = gp.game_id
    WHERE gp.player_id = 12345
    AND gs.created_at > NOW() - INTERVAL '30 days'
)
SELECT * FROM player_games 
WHERE rn <= 20;

-- Supporting index
CREATE INDEX CONCURRENTLY idx_player_game_history 
ON game_participants (player_id, game_id) 
INCLUDE (team, score, game_result);
```

### 4. Leaderboard Queries

```sql
-- BEFORE: Slow leaderboard calculation
SELECT p.username, COUNT(*) as games_played, 
       SUM(CASE WHEN gp.game_result = 'won' THEN 1 ELSE 0 END) as games_won,
       AVG(gp.score) as avg_score
FROM players p
JOIN game_participants gp ON p.id = gp.player_id
JOIN game_sessions gs ON gp.game_id = gs.id
WHERE gs.status = 'completed'
GROUP BY p.id, p.username
ORDER BY games_won DESC, avg_score DESC;

-- AFTER: Use materialized view (see materialized views section)
SELECT username, games_played, games_won, avg_score, ranking
FROM mv_player_leaderboard
ORDER BY ranking
LIMIT 100;
```

## Materialized Views Implementation

### 1. Player Leaderboard

```sql
-- Create materialized view for leaderboard
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
        -- Calculate ELO-style rating
        1500 + (COUNT(CASE WHEN gp.game_result = 'won' THEN 1 END) * 25) - 
               (COUNT(CASE WHEN gp.game_result = 'lost' THEN 1 END) * 20) as rating
    FROM players p
    LEFT JOIN game_participants gp ON p.id = gp.player_id
    LEFT JOIN game_sessions gs ON gp.game_id = gs.id AND gs.status = 'completed'
    WHERE p.is_active = true
    GROUP BY p.id, p.username, p.created_at
    HAVING COUNT(gp.game_id) > 0  -- Only players with games
),
ranked_stats AS (
    SELECT *,
           ROW_NUMBER() OVER (ORDER BY rating DESC, games_won DESC, avg_score DESC) as ranking,
           PERCENT_RANK() OVER (ORDER BY rating DESC) as percentile_rank
    FROM player_stats
)
SELECT * FROM ranked_stats;

-- Index for fast leaderboard queries
CREATE UNIQUE INDEX idx_mv_leaderboard_ranking ON mv_player_leaderboard (ranking);
CREATE INDEX idx_mv_leaderboard_username ON mv_player_leaderboard (username);
CREATE INDEX idx_mv_leaderboard_rating ON mv_player_leaderboard (rating DESC);

-- Refresh procedure
CREATE OR REPLACE FUNCTION refresh_player_leaderboard()
RETURNS void AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_player_leaderboard;
    
    -- Log refresh
    INSERT INTO maintenance_log (operation, status, duration)
    VALUES ('leaderboard_refresh', 'completed', 
            EXTRACT(EPOCH FROM (clock_timestamp() - statement_timestamp())));
END;
$$ LANGUAGE plpgsql;
```

### 2. Game Statistics Dashboard

```sql
-- Materialized view for game statistics
CREATE MATERIALIZED VIEW mv_game_statistics AS
WITH daily_stats AS (
    SELECT 
        DATE(created_at) as game_date,
        COUNT(*) as total_games,
        COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed_games,
        COUNT(CASE WHEN status = 'abandoned' THEN 1 END) as abandoned_games,
        AVG(EXTRACT(EPOCH FROM (updated_at - created_at))/60) as avg_duration_minutes,
        COUNT(DISTINCT EXTRACT(HOUR FROM created_at)) as active_hours,
        -- Peak concurrent games
        MAX((
            SELECT COUNT(*) 
            FROM game_sessions gs2 
            WHERE gs2.created_at <= gs1.created_at 
            AND gs2.updated_at >= gs1.created_at
            AND gs2.status IN ('active', 'in_progress')
        )) as peak_concurrent_games
    FROM game_sessions gs1
    WHERE created_at >= CURRENT_DATE - INTERVAL '30 days'
    GROUP BY DATE(created_at)
),
player_engagement AS (
    SELECT 
        DATE(gs.created_at) as game_date,
        COUNT(DISTINCT gp.player_id) as unique_players,
        AVG(COUNT(gp.player_id)) OVER (
            ORDER BY DATE(gs.created_at) 
            ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
        ) as avg_players_7day
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
    ds.peak_concurrent_games,
    pe.unique_players,
    ROUND(pe.avg_players_7day, 0) as avg_players_7day_rolling,
    ROUND((ds.completed_games::float / NULLIF(ds.total_games, 0)) * 100, 2) as completion_rate
FROM daily_stats ds
LEFT JOIN player_engagement pe ON ds.game_date = pe.game_date
ORDER BY ds.game_date DESC;

-- Index for dashboard queries
CREATE UNIQUE INDEX idx_mv_game_stats_date ON mv_game_statistics (game_date DESC);
```

### 3. Real-time Game Metrics

```sql
-- Materialized view for real-time monitoring
CREATE MATERIALIZED VIEW mv_realtime_metrics AS
SELECT 
    -- Current active games
    COUNT(CASE WHEN status IN ('active', 'in_progress') THEN 1 END) as active_games,
    
    -- Current players online
    (SELECT COUNT(DISTINCT player_id) 
     FROM websocket_connections 
     WHERE status = 'active' 
     AND last_heartbeat > NOW() - INTERVAL '5 minutes') as players_online,
    
    -- Games waiting for players
    COUNT(CASE WHEN status = 'waiting' THEN 1 END) as games_waiting,
    
    -- Average game duration for completed games today
    AVG(CASE 
        WHEN status = 'completed' 
        AND created_at > CURRENT_DATE 
        THEN EXTRACT(EPOCH FROM (updated_at - created_at))/60 
    END) as avg_game_duration_today,
    
    -- Games per hour in last 24 hours
    (SELECT COUNT(*) 
     FROM game_sessions 
     WHERE created_at > NOW() - INTERVAL '24 hours') / 24.0 as games_per_hour_24h,
    
    -- Last update timestamp
    NOW() as last_updated
    
FROM game_sessions
WHERE created_at > NOW() - INTERVAL '24 hours';

-- Fast refresh for real-time data
CREATE INDEX idx_mv_realtime_metrics_single ON mv_realtime_metrics ((1));
```

## Partitioning Strategy

### 1. Game History Partitioning by Date

```sql
-- Create partitioned table for game history
CREATE TABLE game_sessions_partitioned (
    id BIGSERIAL,
    room_id VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL,
    game_type VARCHAR(20) DEFAULT 'hokm',
    player_count INTEGER DEFAULT 0,
    current_phase VARCHAR(30),
    current_player INTEGER,
    game_data JSONB,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    
    PRIMARY KEY (id, created_at)
) PARTITION BY RANGE (created_at);

-- Create monthly partitions
CREATE TABLE game_sessions_y2024m01 PARTITION OF game_sessions_partitioned
    FOR VALUES FROM ('2024-01-01') TO ('2024-02-01');

CREATE TABLE game_sessions_y2024m02 PARTITION OF game_sessions_partitioned
    FOR VALUES FROM ('2024-02-01') TO ('2024-03-01');

-- Create indexes on each partition
CREATE INDEX idx_game_sessions_y2024m01_room_id ON game_sessions_y2024m01 (room_id);
CREATE INDEX idx_game_sessions_y2024m01_status ON game_sessions_y2024m01 (status) WHERE status IN ('active', 'waiting');

-- Automated partition creation function
CREATE OR REPLACE FUNCTION create_monthly_partitions()
RETURNS void AS $$
DECLARE
    start_date DATE;
    end_date DATE;
    partition_name TEXT;
BEGIN
    -- Create partitions for next 3 months
    FOR i IN 0..2 LOOP
        start_date := date_trunc('month', CURRENT_DATE + (i || ' months')::INTERVAL);
        end_date := start_date + INTERVAL '1 month';
        partition_name := 'game_sessions_y' || 
                         EXTRACT(YEAR FROM start_date) || 'm' || 
                         LPAD(EXTRACT(MONTH FROM start_date)::TEXT, 2, '0');
        
        -- Create partition if it doesn't exist
        EXECUTE format('CREATE TABLE IF NOT EXISTS %I PARTITION OF game_sessions_partitioned
                       FOR VALUES FROM (%L) TO (%L)', 
                       partition_name, start_date, end_date);
        
        -- Create indexes
        EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_room_id ON %I (room_id)', 
                       partition_name, partition_name);
        EXECUTE format('CREATE INDEX IF NOT EXISTS idx_%s_status ON %I (status) WHERE status IN (''active'', ''waiting'')', 
                       partition_name, partition_name);
    END LOOP;
END;
$$ LANGUAGE plpgsql;

-- Schedule partition creation
SELECT cron.schedule('create-partitions', '0 0 25 * *', 'SELECT create_monthly_partitions();');
```

### 2. Game Moves Partitioning by Hash

```sql
-- Partition game moves by hash of game_id for even distribution
CREATE TABLE game_moves_partitioned (
    id BIGSERIAL,
    game_id BIGINT NOT NULL,
    player_id BIGINT NOT NULL,
    move_sequence INTEGER NOT NULL,
    move_type VARCHAR(30) NOT NULL,
    move_data JSONB,
    round_number INTEGER,
    trick_number INTEGER,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    
    PRIMARY KEY (id, game_id)
) PARTITION BY HASH (game_id);

-- Create 8 hash partitions for good distribution
CREATE TABLE game_moves_hash_0 PARTITION OF game_moves_partitioned
    FOR VALUES WITH (modulus 8, remainder 0);
CREATE TABLE game_moves_hash_1 PARTITION OF game_moves_partitioned
    FOR VALUES WITH (modulus 8, remainder 1);
-- ... continue for all 8 partitions

-- Indexes on each partition
CREATE INDEX idx_game_moves_hash_0_game_seq ON game_moves_hash_0 (game_id, move_sequence);
CREATE INDEX idx_game_moves_hash_0_player ON game_moves_hash_0 (player_id, created_at);
-- ... create for all partitions
```

## Configuration Tuning for Gaming Workloads

### 1. PostgreSQL Configuration (postgresql.conf)

```ini
# Gaming-Optimized PostgreSQL Configuration

# Connection Settings
max_connections = 1000                    # High concurrent player support
superuser_reserved_connections = 10

# Memory Settings
shared_buffers = 2GB                      # 25% of RAM for 8GB system
effective_cache_size = 6GB                # 75% of RAM for optimizer
work_mem = 32MB                           # For sorting/hashing operations
maintenance_work_mem = 512MB              # For maintenance operations
dynamic_shared_memory_type = posix

# Query Performance
random_page_cost = 1.1                    # SSD-optimized
effective_io_concurrency = 200            # SSD concurrent I/O
seq_page_cost = 1.0                       # Sequential scan cost

# Gaming-Specific Performance
default_statistics_target = 250           # Better query planning
from_collapse_limit = 12                  # Complex join optimization
join_collapse_limit = 12
constraint_exclusion = partition          # Partition pruning

# Write Performance
checkpoint_completion_target = 0.8        # Spread checkpoints
checkpoint_timeout = 15min                # Gaming workload balance
max_wal_size = 4GB                        # Handle bursts
min_wal_size = 1GB

# Connection Performance
tcp_keepalives_idle = 300                 # Gaming session keepalive
tcp_keepalives_interval = 30
tcp_keepalives_count = 3
tcp_user_timeout = 30000                  # 30 second timeout

# Real-time Performance
synchronous_commit = off                  # Faster writes (with risk)
wal_writer_delay = 200ms                  # Frequent WAL writes
commit_delay = 1000                       # Batch commits (microseconds)
commit_siblings = 8                       # Commit batching threshold

# Parallel Query (for analytics)
max_parallel_workers_per_gather = 4
max_parallel_workers = 8
max_parallel_maintenance_workers = 4

# Logging for Performance Monitoring
log_min_duration_statement = 100          # Log slow queries (100ms+)
log_checkpoints = on
log_connections = on
log_disconnections = on
log_lock_waits = on
log_statement_stats = off
log_parser_stats = off
log_planner_stats = off
log_executor_stats = off

# Statistics Collection
track_activities = on
track_counts = on
track_io_timing = on
track_functions = all
track_activity_query_size = 2048

# Autovacuum for Gaming Workload
autovacuum = on
autovacuum_max_workers = 6                # More workers for high write load
autovacuum_naptime = 30s                  # More frequent checks
autovacuum_vacuum_threshold = 25          # Lower threshold
autovacuum_vacuum_scale_factor = 0.1      # 10% table size
autovacuum_analyze_threshold = 25
autovacuum_analyze_scale_factor = 0.05    # 5% for statistics
autovacuum_vacuum_cost_delay = 10ms       # Reduce vacuum impact
autovacuum_vacuum_cost_limit = 1000       # Higher limit for faster vacuum
```

### 2. PgBouncer Gaming Configuration

```ini
# PgBouncer Gaming-Optimized Configuration

[databases]
hokm_game = host=postgresql-primary port=5432 dbname=hokm_game pool_size=50 max_db_connections=60
hokm_game_read = host=postgresql-replica1 port=5432 dbname=hokm_game pool_size=30 max_db_connections=40

[pgbouncer]
# Pool Configuration for Gaming
pool_mode = transaction                   # Fast transaction turnover
max_client_conn = 2000                   # Support many concurrent players
default_pool_size = 50                   # Large pools for high throughput
min_pool_size = 10                       # Always-ready connections
reserve_pool_size = 15                   # Emergency connections
max_db_connections = 100                 # Total DB connections

# Gaming Performance Timeouts
server_connect_timeout = 5               # Fast connection establishment
query_timeout = 30                       # Gaming queries should be fast
query_wait_timeout = 60                  # Queue timeout
client_idle_timeout = 300                # 5 minutes for idle players
server_idle_timeout = 300
server_lifetime = 3600                   # 1 hour connection lifetime

# Performance Settings
server_reset_query = DISCARD ALL         # Clean connection state
server_reset_query_always = 0
server_check_delay = 10                  # Health check frequency
tcp_defer_accept = 1                     # Network optimization
tcp_keepalive = 1
```

## EXPLAIN Analysis Examples

### 1. Game State Query Analysis

```sql
-- Analyze game state retrieval query
EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
SELECT gs.room_id, gs.status, gs.current_phase, gs.game_data,
       json_agg(
           json_build_object(
               'player_id', gp.player_id,
               'username', p.username,
               'team', gp.team,
               'position', gp.position
           )
       ) as players
FROM game_sessions gs
JOIN game_participants gp ON gs.id = gp.game_id
JOIN players p ON gp.player_id = p.id
WHERE gs.room_id = 'ROOM123'
GROUP BY gs.id, gs.room_id, gs.status, gs.current_phase, gs.game_data;

-- Expected plan with proper indexes:
-- Nested Loop (cost=0.71..45.23 rows=1 width=XXX) (actual time=0.123..0.456 rows=4 loops=1)
--   Buffers: shared hit=12
--   -> Index Scan using idx_game_sessions_room_id on game_sessions gs
--   -> Nested Loop
--        -> Index Scan using idx_game_participants_game_id on game_participants gp
--        -> Index Scan using players_pkey on players p
```

### 2. Leaderboard Query Analysis

```sql
-- Analyze leaderboard query performance
EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
SELECT username, games_played, games_won, rating, ranking
FROM mv_player_leaderboard
ORDER BY ranking
LIMIT 100;

-- Expected plan with materialized view:
-- Limit (cost=0.29..8.31 rows=100 width=XXX) (actual time=0.023..0.145 rows=100 loops=1)
--   Buffers: shared hit=3
--   -> Index Scan using idx_mv_leaderboard_ranking on mv_player_leaderboard
```

### 3. Recent Games Query Analysis

```sql
-- Analyze recent games query
EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
SELECT room_id, status, created_at, player_count
FROM game_sessions
WHERE created_at > NOW() - INTERVAL '1 hour'
AND status IN ('active', 'completed')
ORDER BY created_at DESC
LIMIT 50;

-- Check for index usage and performance
-- Look for: Index Scan, low cost, minimal buffers
```

### 4. Player Game History Analysis

```sql
-- Analyze player history query
EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
WITH player_recent_games AS (
    SELECT gs.room_id, gs.status, gs.created_at, gp.score, gp.game_result
    FROM game_sessions gs
    JOIN game_participants gp ON gs.id = gp.game_id
    WHERE gp.player_id = 12345
    AND gs.created_at > NOW() - INTERVAL '30 days'
    ORDER BY gs.created_at DESC
    LIMIT 20
)
SELECT * FROM player_recent_games;

-- Monitor for: proper index usage, no sequential scans
```

## Performance Monitoring Queries

### 1. Query Performance Monitoring

```sql
-- Create monitoring queries for regular execution
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
WHERE calls > 100  -- Only frequent queries
ORDER BY total_exec_time DESC
LIMIT 20;

-- Index usage monitoring
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

-- Table bloat monitoring
CREATE OR REPLACE VIEW v_table_bloat AS
SELECT 
    schemaname,
    tablename,
    n_tup_ins as inserts,
    n_tup_upd as updates,
    n_tup_del as deletes,
    n_dead_tup as dead_tuples,
    CASE 
        WHEN n_live_tup > 0 
        THEN round((n_dead_tup::float / n_live_tup) * 100, 2)
        ELSE 0 
    END as bloat_percentage,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as table_size,
    last_vacuum,
    last_autovacuum
FROM pg_stat_user_tables
WHERE n_live_tup > 1000  -- Only significant tables
ORDER BY bloat_percentage DESC;
```

### 2. Gaming-Specific Monitoring

```sql
-- Active game performance metrics
CREATE OR REPLACE VIEW v_gaming_performance AS
SELECT 
    'Active Games' as metric,
    COUNT(*) as value,
    'games' as unit
FROM game_sessions 
WHERE status IN ('active', 'in_progress')
UNION ALL
SELECT 
    'Games per Minute (last hour)' as metric,
    COUNT(*)::float / 60 as value,
    'games/min' as unit
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
    'Active Player Connections' as metric,
    COUNT(DISTINCT player_id) as value,
    'players' as unit
FROM websocket_connections
WHERE status = 'active'
AND last_heartbeat > NOW() - INTERVAL '5 minutes';

-- Query latency by operation type
CREATE OR REPLACE VIEW v_query_latency_by_type AS
SELECT 
    CASE 
        WHEN query ILIKE '%game_sessions%INSERT%' THEN 'Game Creation'
        WHEN query ILIKE '%game_sessions%UPDATE%' THEN 'Game Updates'
        WHEN query ILIKE '%game_moves%INSERT%' THEN 'Card Plays'
        WHEN query ILIKE '%game_participants%' THEN 'Player Operations'
        WHEN query ILIKE '%SELECT%game_sessions%' THEN 'Game Queries'
        ELSE 'Other'
    END as operation_type,
    COUNT(*) as query_count,
    round(AVG(mean_exec_time)::numeric, 2) as avg_latency_ms,
    round(MAX(mean_exec_time)::numeric, 2) as max_latency_ms,
    round(SUM(total_exec_time)::numeric, 2) as total_time_ms
FROM pg_stat_statements
WHERE calls > 10
GROUP BY operation_type
ORDER BY avg_latency_ms DESC;
```

This comprehensive PostgreSQL performance optimization plan provides specific, actionable improvements for your Hokm game server. The next sections will cover vacuum automation and performance regression monitoring.
