-- 03-create-functions.sql
-- Stored procedures and functions for Hokm Game

\echo 'Creating Hokm Game Functions and Triggers...'

SET search_path TO hokm_game, public;

-- Function to update the updated_at column
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Triggers for updated_at columns
CREATE TRIGGER update_players_updated_at 
    BEFORE UPDATE ON players 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_game_sessions_updated_at 
    BEFORE UPDATE ON game_sessions 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Function to automatically update player statistics
CREATE OR REPLACE FUNCTION update_player_stats()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.status = 'completed' AND OLD.status != 'completed' THEN
        -- Update total games for all participants
        UPDATE players 
        SET total_games = total_games + 1
        WHERE id IN (
            SELECT player_id FROM game_participants 
            WHERE game_session_id = NEW.id
        );
        
        -- Update wins/losses based on final scores
        -- This is a simplified version - you may want more complex logic
        WITH team_scores AS (
            SELECT 
                gp.team,
                COALESCE((NEW.scores->gp.team::text)::integer, 0) as score
            FROM game_participants gp 
            WHERE gp.game_session_id = NEW.id
            GROUP BY gp.team
        ),
        winning_team AS (
            SELECT team 
            FROM team_scores 
            ORDER BY score DESC 
            LIMIT 1
        )
        UPDATE players 
        SET wins = CASE 
            WHEN gp.team = (SELECT team FROM winning_team) THEN wins + 1
            ELSE wins
        END,
        losses = CASE 
            WHEN gp.team != (SELECT team FROM winning_team) THEN losses + 1
            ELSE losses
        END
        FROM game_participants gp
        WHERE players.id = gp.player_id 
        AND gp.game_session_id = NEW.id;
    END IF;
    
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Trigger for game completion
CREATE TRIGGER update_stats_on_game_complete 
    AFTER UPDATE ON game_sessions 
    FOR EACH ROW EXECUTE FUNCTION update_player_stats();

-- Function to clean up old disconnected WebSocket connections
CREATE OR REPLACE FUNCTION cleanup_old_connections()
RETURNS INTEGER AS $$
DECLARE
    cleaned_count INTEGER;
BEGIN
    UPDATE websocket_connections 
    SET is_active = false, disconnected_at = NOW()
    WHERE is_active = true 
    AND last_ping < NOW() - INTERVAL '5 minutes';
    
    GET DIAGNOSTICS cleaned_count = ROW_COUNT;
    
    -- Insert performance metric
    INSERT INTO performance_metrics (metric_type, metric_name, metric_value, metadata)
    VALUES ('cleanup', 'connections_cleaned', cleaned_count, 
            jsonb_build_object('timestamp', NOW()));
    
    RETURN cleaned_count;
END;
$$ language 'plpgsql';

-- Function to get active game statistics
CREATE OR REPLACE FUNCTION get_active_game_stats()
RETURNS TABLE(
    total_active_games INTEGER,
    total_waiting_games INTEGER,
    total_connected_players INTEGER,
    average_game_duration INTERVAL
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        (SELECT COUNT(*)::INTEGER FROM game_sessions WHERE status = 'active'),
        (SELECT COUNT(*)::INTEGER FROM game_sessions WHERE status = 'waiting'),
        (SELECT COUNT(*)::INTEGER FROM websocket_connections WHERE is_active = true),
        (SELECT AVG(completed_at - started_at) 
         FROM game_sessions 
         WHERE status = 'completed' 
         AND completed_at > NOW() - INTERVAL '24 hours');
END;
$$ language 'plpgsql';

-- Function to update game state efficiently
CREATE OR REPLACE FUNCTION update_game_state(
    p_game_session_id UUID,
    p_game_state JSONB,
    p_player_hands JSONB DEFAULT NULL,
    p_scores JSONB DEFAULT NULL
)
RETURNS BOOLEAN AS $$
BEGIN
    UPDATE game_sessions 
    SET 
        game_state = COALESCE(p_game_state, game_state),
        player_hands = COALESCE(p_player_hands, player_hands),
        scores = COALESCE(p_scores, scores),
        updated_at = NOW()
    WHERE id = p_game_session_id;
    
    RETURN FOUND;
END;
$$ language 'plpgsql';

-- Function to record game move
CREATE OR REPLACE FUNCTION record_game_move(
    p_game_session_id UUID,
    p_player_id UUID,
    p_move_type VARCHAR(20),
    p_move_data JSONB,
    p_round_number INTEGER,
    p_trick_number INTEGER DEFAULT NULL
)
RETURNS UUID AS $$
DECLARE
    move_id UUID;
    next_sequence INTEGER;
BEGIN
    -- Get next sequence number
    SELECT COALESCE(MAX(sequence_number), 0) + 1 
    INTO next_sequence
    FROM game_moves 
    WHERE game_session_id = p_game_session_id;
    
    -- Insert move
    INSERT INTO game_moves (
        game_session_id, player_id, move_type, move_data,
        round_number, trick_number, sequence_number
    ) VALUES (
        p_game_session_id, p_player_id, p_move_type, p_move_data,
        p_round_number, p_trick_number, next_sequence
    ) RETURNING id INTO move_id;
    
    RETURN move_id;
END;
$$ language 'plpgsql';

-- Function to handle player reconnection
CREATE OR REPLACE FUNCTION handle_player_reconnection(
    p_player_id UUID,
    p_game_session_id UUID,
    p_connection_id VARCHAR(255)
)
RETURNS JSONB AS $$
DECLARE
    game_state JSONB;
    player_hand JSONB;
    result JSONB;
BEGIN
    -- Mark player as connected
    UPDATE game_participants 
    SET is_connected = true, reconnected_at = NOW()
    WHERE player_id = p_player_id AND game_session_id = p_game_session_id;
    
    -- Update connection
    INSERT INTO websocket_connections (player_id, game_session_id, connection_id)
    VALUES (p_player_id, p_game_session_id, p_connection_id)
    ON CONFLICT (connection_id) DO UPDATE SET
        last_ping = NOW(),
        is_active = true,
        disconnected_at = NULL;
    
    -- Get current game state and player hand
    SELECT gs.game_state, (gs.player_hands->p_player_id::text)
    INTO game_state, player_hand
    FROM game_sessions gs
    WHERE gs.id = p_game_session_id;
    
    -- Record reconnection move
    PERFORM record_game_move(
        p_game_session_id, p_player_id, 'reconnect', 
        jsonb_build_object('connection_id', p_connection_id),
        COALESCE((game_state->>'current_round')::integer, 1)
    );
    
    -- Return game state for reconnection
    result := jsonb_build_object(
        'game_state', game_state,
        'player_hand', player_hand,
        'reconnected_at', NOW()
    );
    
    RETURN result;
END;
$$ language 'plpgsql';

-- Create audit schema tables for sensitive operations
CREATE SCHEMA IF NOT EXISTS audit;

CREATE TABLE IF NOT EXISTS audit.user_actions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    player_id UUID,
    action_type VARCHAR(50) NOT NULL,
    action_data JSONB DEFAULT '{}',
    ip_address INET,
    user_agent TEXT,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Function to log user actions
CREATE OR REPLACE FUNCTION audit.log_user_action(
    p_player_id UUID,
    p_action_type VARCHAR(50),
    p_action_data JSONB DEFAULT '{}',
    p_ip_address INET DEFAULT NULL,
    p_user_agent TEXT DEFAULT NULL
)
RETURNS UUID AS $$
DECLARE
    log_id UUID;
BEGIN
    INSERT INTO audit.user_actions (player_id, action_type, action_data, ip_address, user_agent)
    VALUES (p_player_id, p_action_type, p_action_data, p_ip_address, p_user_agent)
    RETURNING id INTO log_id;
    
    RETURN log_id;
END;
$$ language 'plpgsql';

\echo 'Hokm Game Functions and Triggers created successfully!'
