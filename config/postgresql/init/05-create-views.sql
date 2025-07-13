-- 05-create-views.sql
-- Analytics and reporting views

\echo 'Creating analytics views...'

SET search_path TO analytics, hokm_game, public;

-- Player performance view
CREATE OR REPLACE VIEW player_performance AS
SELECT 
    p.id,
    p.username,
    p.total_games,
    p.wins,
    p.losses,
    CASE 
        WHEN p.total_games > 0 THEN ROUND((p.wins::DECIMAL / p.total_games) * 100, 2)
        ELSE 0 
    END as win_percentage,
    p.rating,
    p.last_seen,
    COUNT(DISTINCT gs.id) FILTER (WHERE gs.created_at > NOW() - INTERVAL '7 days') as games_last_week,
    COUNT(DISTINCT gs.id) FILTER (WHERE gs.created_at > NOW() - INTERVAL '30 days') as games_last_month
FROM hokm_game.players p
LEFT JOIN hokm_game.game_participants gp ON p.id = gp.player_id
LEFT JOIN hokm_game.game_sessions gs ON gp.game_session_id = gs.id
GROUP BY p.id, p.username, p.total_games, p.wins, p.losses, p.rating, p.last_seen;

-- Game statistics view
CREATE OR REPLACE VIEW game_statistics_summary AS
SELECT 
    DATE(gs.created_at) as game_date,
    COUNT(*) as total_games,
    COUNT(*) FILTER (WHERE gs.status = 'completed') as completed_games,
    COUNT(*) FILTER (WHERE gs.status = 'abandoned') as abandoned_games,
    AVG(EXTRACT(EPOCH FROM (gs.completed_at - gs.started_at))) as avg_duration_seconds,
    COUNT(DISTINCT gp.player_id) as unique_players
FROM hokm_game.game_sessions gs
LEFT JOIN hokm_game.game_participants gp ON gs.id = gp.game_session_id
WHERE gs.created_at > NOW() - INTERVAL '30 days'
GROUP BY DATE(gs.created_at)
ORDER BY game_date DESC;

-- Active sessions view
CREATE OR REPLACE VIEW active_sessions AS
SELECT 
    gs.id,
    gs.room_id,
    gs.status,
    gs.current_players,
    gs.max_players,
    gs.current_round,
    gs.created_at,
    gs.started_at,
    EXTRACT(EPOCH FROM (NOW() - gs.started_at)) as duration_seconds,
    string_agg(p.username, ', ' ORDER BY gp.position) as players
FROM hokm_game.game_sessions gs
JOIN hokm_game.game_participants gp ON gs.id = gp.game_session_id
JOIN hokm_game.players p ON gp.player_id = p.id
WHERE gs.status IN ('waiting', 'active')
AND gp.is_connected = true
GROUP BY gs.id, gs.room_id, gs.status, gs.current_players, gs.max_players, 
         gs.current_round, gs.created_at, gs.started_at;

-- Connection statistics view
CREATE OR REPLACE VIEW connection_statistics AS
SELECT 
    DATE(wc.connected_at) as connection_date,
    COUNT(*) as total_connections,
    COUNT(DISTINCT wc.player_id) as unique_players,
    AVG(EXTRACT(EPOCH FROM (COALESCE(wc.disconnected_at, NOW()) - wc.connected_at))) as avg_session_duration,
    COUNT(*) FILTER (WHERE wc.disconnected_at IS NULL) as active_connections
FROM hokm_game.websocket_connections wc
WHERE wc.connected_at > NOW() - INTERVAL '7 days'
GROUP BY DATE(wc.connected_at)
ORDER BY connection_date DESC;

-- Performance metrics view
CREATE OR REPLACE VIEW performance_dashboard AS
SELECT 
    pm.metric_type,
    pm.metric_name,
    AVG(pm.metric_value) as avg_value,
    MIN(pm.metric_value) as min_value,
    MAX(pm.metric_value) as max_value,
    COUNT(*) as sample_count,
    MAX(pm.timestamp) as last_updated
FROM hokm_game.performance_metrics pm
WHERE pm.timestamp > NOW() - INTERVAL '1 hour'
GROUP BY pm.metric_type, pm.metric_name
ORDER BY pm.metric_type, pm.metric_name;

-- Player activity heatmap
CREATE OR REPLACE VIEW player_activity_heatmap AS
SELECT 
    EXTRACT(HOUR FROM gs.created_at) as hour_of_day,
    EXTRACT(DOW FROM gs.created_at) as day_of_week,
    COUNT(*) as game_count,
    COUNT(DISTINCT gp.player_id) as unique_players
FROM hokm_game.game_sessions gs
JOIN hokm_game.game_participants gp ON gs.id = gp.game_session_id
WHERE gs.created_at > NOW() - INTERVAL '30 days'
GROUP BY EXTRACT(HOUR FROM gs.created_at), EXTRACT(DOW FROM gs.created_at)
ORDER BY day_of_week, hour_of_day;

-- Top players leaderboard
CREATE OR REPLACE VIEW leaderboard AS
SELECT 
    p.id,
    p.username,
    p.rating,
    p.total_games,
    p.wins,
    p.losses,
    CASE 
        WHEN p.total_games > 0 THEN ROUND((p.wins::DECIMAL / p.total_games) * 100, 2)
        ELSE 0 
    END as win_percentage,
    ROW_NUMBER() OVER (ORDER BY p.rating DESC, p.wins DESC) as rank
FROM hokm_game.players p
WHERE p.total_games >= 10  -- Only players with at least 10 games
AND p.is_active = true
ORDER BY p.rating DESC, p.wins DESC
LIMIT 100;

-- Recent game moves for debugging
CREATE OR REPLACE VIEW recent_game_moves AS
SELECT 
    gm.id,
    gs.room_id,
    p.username,
    gm.move_type,
    gm.move_data,
    gm.round_number,
    gm.trick_number,
    gm.sequence_number,
    gm.timestamp
FROM hokm_game.game_moves gm
JOIN hokm_game.game_sessions gs ON gm.game_session_id = gs.id
JOIN hokm_game.players p ON gm.player_id = p.id
WHERE gm.timestamp > NOW() - INTERVAL '1 hour'
ORDER BY gm.timestamp DESC;

\echo 'Analytics views created successfully!'
