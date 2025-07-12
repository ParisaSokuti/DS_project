-- Hokm Card Game Database Schema
-- Comprehensive schema with optimized indexes and constraints
-- Designed for PostgreSQL with SQLAlchemy compatibility

-- Enable necessary extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "pg_stat_statements";

-- Create main application schema
CREATE SCHEMA IF NOT EXISTS hokm_game;
SET search_path TO hokm_game, public;

-- =============================================
-- CORE TABLES
-- =============================================

-- Players table - Core user management
CREATE TABLE players (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE,
    password_hash VARCHAR(255), -- bcrypt hash
    
    -- Profile information
    display_name VARCHAR(100),
    avatar_url VARCHAR(500),
    country_code CHAR(2), -- ISO country code
    timezone VARCHAR(50), -- IANA timezone
    
    -- Authentication and security
    email_verified BOOLEAN DEFAULT FALSE,
    account_status VARCHAR(20) DEFAULT 'active' CHECK (account_status IN ('active', 'suspended', 'banned', 'deleted')),
    last_login TIMESTAMP WITH TIME ZONE,
    password_reset_token VARCHAR(255),
    password_reset_expires TIMESTAMP WITH TIME ZONE,
    email_verification_token VARCHAR(255),
    
    -- Game statistics (denormalized for performance)
    total_games INTEGER DEFAULT 0 CHECK (total_games >= 0),
    wins INTEGER DEFAULT 0 CHECK (wins >= 0),
    losses INTEGER DEFAULT 0 CHECK (losses >= 0),
    draws INTEGER DEFAULT 0 CHECK (draws >= 0),
    total_points INTEGER DEFAULT 0,
    rating INTEGER DEFAULT 1000 CHECK (rating >= 0 AND rating <= 3000),
    
    -- Tracking
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_seen TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE,
    
    -- Constraints
    CONSTRAINT valid_email CHECK (email IS NULL OR email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$'),
    CONSTRAINT valid_username CHECK (length(username) >= 3 AND username ~* '^[A-Za-z0-9_-]+$'),
    CONSTRAINT valid_stats CHECK (wins + losses + draws <= total_games)
);

-- Game sessions table - Active and completed games
CREATE TABLE game_sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    room_id VARCHAR(100) UNIQUE NOT NULL,
    session_key VARCHAR(255) UNIQUE NOT NULL,
    
    -- Game configuration
    game_type VARCHAR(20) DEFAULT 'standard' CHECK (game_type IN ('standard', 'tournament', 'friendly', 'ranked')),
    max_players INTEGER DEFAULT 4 CHECK (max_players BETWEEN 2 AND 4),
    current_players INTEGER DEFAULT 0 CHECK (current_players >= 0),
    rounds_to_win INTEGER DEFAULT 7 CHECK (rounds_to_win BETWEEN 1 AND 13),
    
    -- Game state
    status VARCHAR(20) DEFAULT 'waiting' CHECK (status IN ('waiting', 'starting', 'active', 'paused', 'completed', 'abandoned', 'cancelled')),
    phase VARCHAR(20) DEFAULT 'waiting' CHECK (phase IN ('waiting', 'dealing', 'trump_selection', 'playing', 'round_complete', 'game_complete')),
    current_round INTEGER DEFAULT 1 CHECK (current_round BETWEEN 1 AND 13),
    current_trick INTEGER DEFAULT 1 CHECK (current_trick BETWEEN 1 AND 13),
    current_player_position INTEGER CHECK (current_player_position BETWEEN 0 AND 3),
    
    -- Game participants
    hakem_id UUID REFERENCES players(id),
    hakem_position INTEGER CHECK (hakem_position BETWEEN 0 AND 3),
    trump_suit VARCHAR(10) CHECK (trump_suit IN ('hearts', 'diamonds', 'clubs', 'spades')),
    
    -- Game state storage (JSONB for flexibility)
    game_state JSONB DEFAULT '{}',
    player_hands JSONB DEFAULT '{}', -- Private hands per player
    played_cards JSONB DEFAULT '[]', -- Cards played in current trick
    completed_tricks JSONB DEFAULT '[]', -- All completed tricks
    scores JSONB DEFAULT '{"team1": 0, "team2": 0}', -- Current scores
    round_scores JSONB DEFAULT '[]', -- Score history per round
    team_assignments JSONB DEFAULT '{"team1": [], "team2": []}', -- Team memberships
    
    -- Settings and metadata
    settings JSONB DEFAULT '{}', -- Game-specific settings
    metadata JSONB DEFAULT '{}', -- Additional metadata
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Performance constraints
    CONSTRAINT valid_room_id CHECK (length(room_id) >= 3),
    CONSTRAINT valid_session_key CHECK (length(session_key) >= 10),
    CONSTRAINT valid_player_count CHECK (current_players <= max_players),
    CONSTRAINT valid_game_timing CHECK (started_at IS NULL OR started_at >= created_at),
    CONSTRAINT valid_completion_timing CHECK (completed_at IS NULL OR completed_at >= started_at)
);

-- Game participants table - Links players to game sessions
CREATE TABLE game_participants (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    game_session_id UUID NOT NULL REFERENCES game_sessions(id) ON DELETE CASCADE,
    player_id UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    
    -- Position and team
    position INTEGER NOT NULL CHECK (position BETWEEN 0 AND 3),
    team INTEGER NOT NULL CHECK (team IN (1, 2)),
    is_hakem BOOLEAN DEFAULT FALSE,
    
    -- Connection status
    is_connected BOOLEAN DEFAULT TRUE,
    connection_id VARCHAR(255),
    ip_address INET,
    user_agent TEXT,
    
    -- Participation tracking
    joined_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    left_at TIMESTAMP WITH TIME ZONE,
    last_action_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    disconnections INTEGER DEFAULT 0,
    
    -- Game performance
    cards_played INTEGER DEFAULT 0,
    tricks_won INTEGER DEFAULT 0,
    points_earned INTEGER DEFAULT 0,
    average_response_time INTERVAL,
    
    -- Constraints
    UNIQUE (game_session_id, position),
    UNIQUE (game_session_id, player_id),
    CONSTRAINT valid_connection_timing CHECK (left_at IS NULL OR left_at >= joined_at)
);

-- Game moves/actions table - Complete audit trail
CREATE TABLE game_moves (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    game_session_id UUID NOT NULL REFERENCES game_sessions(id) ON DELETE CASCADE,
    player_id UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    
    -- Move details
    move_type VARCHAR(30) NOT NULL CHECK (move_type IN (
        'join_game', 'leave_game', 'ready', 'not_ready',
        'choose_trump', 'play_card', 'pass_turn',
        'chat_message', 'reconnect', 'disconnect',
        'game_start', 'round_start', 'trick_complete', 'round_complete', 'game_complete'
    )),
    move_data JSONB NOT NULL DEFAULT '{}',
    
    -- Game context
    round_number INTEGER NOT NULL CHECK (round_number >= 1),
    trick_number INTEGER CHECK (trick_number >= 1),
    sequence_number INTEGER NOT NULL,
    
    -- Validation and processing
    is_valid BOOLEAN DEFAULT TRUE,
    validation_errors JSONB DEFAULT '[]',
    processed_at TIMESTAMP WITH TIME ZONE,
    
    -- Timing
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    response_time INTERVAL, -- Time taken to make the move
    
    -- Constraints
    UNIQUE (game_session_id, sequence_number),
    CONSTRAINT valid_trick_context CHECK (
        (move_type IN ('choose_trump', 'game_start', 'round_start') AND trick_number IS NULL) OR
        (move_type IN ('play_card', 'pass_turn') AND trick_number IS NOT NULL)
    )
);

-- WebSocket connections table - Real-time connection management
CREATE TABLE websocket_connections (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    connection_id VARCHAR(255) UNIQUE NOT NULL,
    
    -- Associated entities
    player_id UUID REFERENCES players(id) ON DELETE CASCADE,
    game_session_id UUID REFERENCES game_sessions(id) ON DELETE CASCADE,
    
    -- Connection details
    ip_address INET,
    user_agent TEXT,
    protocol_version VARCHAR(10) DEFAULT '1.0',
    
    -- Connection lifecycle
    connected_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_ping TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    disconnected_at TIMESTAMP WITH TIME ZONE,
    disconnect_reason VARCHAR(100),
    
    -- Status and metrics
    is_active BOOLEAN DEFAULT TRUE,
    message_count INTEGER DEFAULT 0,
    bytes_sent BIGINT DEFAULT 0,
    bytes_received BIGINT DEFAULT 0,
    
    -- Performance tracking
    average_latency INTERVAL,
    peak_latency INTERVAL,
    connection_quality DECIMAL(3,2) CHECK (connection_quality BETWEEN 0 AND 1),
    
    CONSTRAINT valid_connection_lifecycle CHECK (
        (is_active = TRUE AND disconnected_at IS NULL) OR
        (is_active = FALSE AND disconnected_at IS NOT NULL)
    )
);

-- =============================================
-- GAME HISTORY AND ANALYTICS TABLES
-- =============================================

-- Game history table - Completed games summary
CREATE TABLE game_history (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    game_session_id UUID NOT NULL REFERENCES game_sessions(id) ON DELETE CASCADE,
    
    -- Game summary
    game_type VARCHAR(20) NOT NULL,
    total_rounds INTEGER NOT NULL,
    total_tricks INTEGER NOT NULL,
    game_duration INTERVAL NOT NULL,
    
    -- Outcome
    winning_team INTEGER CHECK (winning_team IN (1, 2)),
    final_scores JSONB NOT NULL,
    is_draw BOOLEAN DEFAULT FALSE,
    completion_reason VARCHAR(50) DEFAULT 'normal' CHECK (completion_reason IN (
        'normal', 'forfeit', 'timeout', 'disconnect', 'admin_action'
    )),
    
    -- Metadata
    trump_suit VARCHAR(10),
    hakem_player_id UUID REFERENCES players(id),
    total_moves INTEGER DEFAULT 0,
    
    -- Timestamps
    started_at TIMESTAMP WITH TIME ZONE NOT NULL,
    completed_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    CONSTRAINT valid_game_duration CHECK (completed_at > started_at),
    CONSTRAINT valid_outcome CHECK (
        (winning_team IS NOT NULL AND is_draw = FALSE) OR
        (winning_team IS NULL AND is_draw = TRUE)
    )
);

-- Player game statistics - Detailed per-game stats
CREATE TABLE player_game_stats (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    game_history_id UUID NOT NULL REFERENCES game_history(id) ON DELETE CASCADE,
    player_id UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    
    -- Game context
    team INTEGER NOT NULL CHECK (team IN (1, 2)),
    position INTEGER NOT NULL CHECK (position BETWEEN 0 AND 3),
    was_hakem BOOLEAN DEFAULT FALSE,
    
    -- Performance metrics
    cards_played INTEGER DEFAULT 0,
    tricks_won INTEGER DEFAULT 0,
    points_earned INTEGER DEFAULT 0,
    trump_cards_played INTEGER DEFAULT 0,
    successful_trump_calls INTEGER DEFAULT 0,
    
    -- Timing metrics
    total_thinking_time INTERVAL DEFAULT '0 seconds',
    average_move_time INTERVAL DEFAULT '0 seconds',
    fastest_move_time INTERVAL,
    slowest_move_time INTERVAL,
    
    -- Connection metrics
    disconnections INTEGER DEFAULT 0,
    total_offline_time INTERVAL DEFAULT '0 seconds',
    
    -- Outcome
    is_winner BOOLEAN DEFAULT FALSE,
    rating_change INTEGER DEFAULT 0,
    points_change INTEGER DEFAULT 0,
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    UNIQUE (game_history_id, player_id)
);

-- Player achievements table - Badges and milestones
CREATE TABLE player_achievements (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    player_id UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    
    -- Achievement details
    achievement_type VARCHAR(50) NOT NULL,
    achievement_name VARCHAR(100) NOT NULL,
    achievement_description TEXT,
    achievement_tier VARCHAR(20) DEFAULT 'bronze' CHECK (achievement_tier IN ('bronze', 'silver', 'gold', 'platinum', 'diamond')),
    
    -- Progress tracking
    current_progress INTEGER DEFAULT 0,
    required_progress INTEGER DEFAULT 1,
    is_completed BOOLEAN DEFAULT FALSE,
    
    -- Associated data
    game_session_id UUID REFERENCES game_sessions(id),
    metadata JSONB DEFAULT '{}',
    
    -- Timestamps
    earned_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    UNIQUE (player_id, achievement_type, achievement_name),
    CONSTRAINT valid_progress CHECK (current_progress <= required_progress),
    CONSTRAINT valid_completion CHECK (
        (is_completed = TRUE AND earned_at IS NOT NULL AND current_progress = required_progress) OR
        (is_completed = FALSE)
    )
);

-- =============================================
-- SYSTEM AND MONITORING TABLES
-- =============================================

-- System performance metrics
CREATE TABLE performance_metrics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    -- Metric identification
    metric_type VARCHAR(50) NOT NULL,
    metric_name VARCHAR(100) NOT NULL,
    metric_category VARCHAR(50) DEFAULT 'general',
    
    -- Metric values
    metric_value DECIMAL(15,4),
    metric_count INTEGER,
    metric_text TEXT,
    
    -- Context and metadata
    server_instance VARCHAR(100),
    metadata JSONB DEFAULT '{}',
    tags JSONB DEFAULT '[]',
    
    -- Timestamps
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Indexes will be created separately for performance
    CONSTRAINT valid_metric_value CHECK (
        (metric_value IS NOT NULL) OR 
        (metric_count IS NOT NULL) OR 
        (metric_text IS NOT NULL)
    )
);

-- Audit log for sensitive operations
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    -- Actor and action
    player_id UUID REFERENCES players(id),
    admin_id UUID, -- Reference to admin users (separate system)
    action_type VARCHAR(50) NOT NULL,
    action_description TEXT NOT NULL,
    
    -- Context
    entity_type VARCHAR(50), -- 'player', 'game_session', etc.
    entity_id UUID,
    ip_address INET,
    user_agent TEXT,
    
    -- Data changes
    old_values JSONB DEFAULT '{}',
    new_values JSONB DEFAULT '{}',
    
    -- Result
    success BOOLEAN DEFAULT TRUE,
    error_message TEXT,
    
    -- Timestamps
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Retention policy (for cleanup)
    retention_until TIMESTAMP WITH TIME ZONE DEFAULT (NOW() + INTERVAL '2 years')
);

-- =============================================
-- INDEXES FOR PERFORMANCE
-- =============================================

-- Players table indexes
CREATE INDEX CONCURRENTLY idx_players_username ON players(username);
CREATE INDEX CONCURRENTLY idx_players_email ON players(email) WHERE email IS NOT NULL;
CREATE INDEX CONCURRENTLY idx_players_rating ON players(rating DESC, total_games DESC);
CREATE INDEX CONCURRENTLY idx_players_last_seen ON players(last_seen DESC) WHERE is_active = TRUE;
CREATE INDEX CONCURRENTLY idx_players_created_at ON players(created_at DESC);
CREATE INDEX CONCURRENTLY idx_players_stats ON players(total_games DESC, wins DESC, rating DESC);
CREATE INDEX CONCURRENTLY idx_players_active ON players(is_active, last_seen DESC) WHERE is_active = TRUE;

-- Game sessions table indexes
CREATE INDEX CONCURRENTLY idx_game_sessions_room_id ON game_sessions(room_id);
CREATE INDEX CONCURRENTLY idx_game_sessions_status ON game_sessions(status, created_at DESC);
CREATE INDEX CONCURRENTLY idx_game_sessions_active ON game_sessions(status, updated_at DESC) 
    WHERE status IN ('waiting', 'starting', 'active', 'paused');
CREATE INDEX CONCURRENTLY idx_game_sessions_hakem ON game_sessions(hakem_id) WHERE hakem_id IS NOT NULL;
CREATE INDEX CONCURRENTLY idx_game_sessions_created_at ON game_sessions(created_at DESC);
CREATE INDEX CONCURRENTLY idx_game_sessions_game_type ON game_sessions(game_type, status, created_at DESC);

-- JSONB indexes for game state queries
CREATE INDEX CONCURRENTLY idx_game_sessions_game_state ON game_sessions USING GIN(game_state);
CREATE INDEX CONCURRENTLY idx_game_sessions_scores ON game_sessions USING GIN(scores);
CREATE INDEX CONCURRENTLY idx_game_sessions_team_assignments ON game_sessions USING GIN(team_assignments);

-- Game participants table indexes
CREATE INDEX CONCURRENTLY idx_game_participants_session ON game_participants(game_session_id, position);
CREATE INDEX CONCURRENTLY idx_game_participants_player ON game_participants(player_id, joined_at DESC);
CREATE INDEX CONCURRENTLY idx_game_participants_connected ON game_participants(is_connected, last_action_at DESC) 
    WHERE is_connected = TRUE;

-- Game moves table indexes
CREATE INDEX CONCURRENTLY idx_game_moves_session ON game_moves(game_session_id, sequence_number);
CREATE INDEX CONCURRENTLY idx_game_moves_player ON game_moves(player_id, timestamp DESC);
CREATE INDEX CONCURRENTLY idx_game_moves_type ON game_moves(move_type, timestamp DESC);
CREATE INDEX CONCURRENTLY idx_game_moves_timestamp ON game_moves(timestamp DESC);
CREATE INDEX CONCURRENTLY idx_game_moves_round_trick ON game_moves(game_session_id, round_number, trick_number, sequence_number);

-- JSONB index for move data
CREATE INDEX CONCURRENTLY idx_game_moves_data ON game_moves USING GIN(move_data);

-- WebSocket connections table indexes
CREATE INDEX CONCURRENTLY idx_websocket_connections_player ON websocket_connections(player_id, connected_at DESC);
CREATE INDEX CONCURRENTLY idx_websocket_connections_session ON websocket_connections(game_session_id, is_active);
CREATE INDEX CONCURRENTLY idx_websocket_connections_active ON websocket_connections(is_active, last_ping DESC) 
    WHERE is_active = TRUE;
CREATE INDEX CONCURRENTLY idx_websocket_connections_cleanup ON websocket_connections(last_ping) 
    WHERE is_active = TRUE;

-- Game history table indexes
CREATE INDEX CONCURRENTLY idx_game_history_session ON game_history(game_session_id);
CREATE INDEX CONCURRENTLY idx_game_history_completed_at ON game_history(completed_at DESC);
CREATE INDEX CONCURRENTLY idx_game_history_hakem ON game_history(hakem_player_id, completed_at DESC) 
    WHERE hakem_player_id IS NOT NULL;
CREATE INDEX CONCURRENTLY idx_game_history_game_type ON game_history(game_type, completed_at DESC);
CREATE INDEX CONCURRENTLY idx_game_history_duration ON game_history(game_duration, completed_at DESC);

-- Player game stats table indexes
CREATE INDEX CONCURRENTLY idx_player_game_stats_player ON player_game_stats(player_id, created_at DESC);
CREATE INDEX CONCURRENTLY idx_player_game_stats_game ON player_game_stats(game_history_id);
CREATE INDEX CONCURRENTLY idx_player_game_stats_performance ON player_game_stats(points_earned DESC, tricks_won DESC);

-- Player achievements table indexes
CREATE INDEX CONCURRENTLY idx_player_achievements_player ON player_achievements(player_id, earned_at DESC);
CREATE INDEX CONCURRENTLY idx_player_achievements_type ON player_achievements(achievement_type, is_completed, earned_at DESC);
CREATE INDEX CONCURRENTLY idx_player_achievements_completed ON player_achievements(is_completed, earned_at DESC) 
    WHERE is_completed = TRUE;

-- Performance metrics table indexes
CREATE INDEX CONCURRENTLY idx_performance_metrics_type_name ON performance_metrics(metric_type, metric_name, timestamp DESC);
CREATE INDEX CONCURRENTLY idx_performance_metrics_timestamp ON performance_metrics(timestamp DESC);
CREATE INDEX CONCURRENTLY idx_performance_metrics_server ON performance_metrics(server_instance, timestamp DESC) 
    WHERE server_instance IS NOT NULL;

-- Audit logs table indexes
CREATE INDEX CONCURRENTLY idx_audit_logs_player ON audit_logs(player_id, timestamp DESC) WHERE player_id IS NOT NULL;
CREATE INDEX CONCURRENTLY idx_audit_logs_action ON audit_logs(action_type, timestamp DESC);
CREATE INDEX CONCURRENTLY idx_audit_logs_entity ON audit_logs(entity_type, entity_id, timestamp DESC) 
    WHERE entity_type IS NOT NULL AND entity_id IS NOT NULL;
CREATE INDEX CONCURRENTLY idx_audit_logs_timestamp ON audit_logs(timestamp DESC);
CREATE INDEX CONCURRENTLY idx_audit_logs_retention ON audit_logs(retention_until) WHERE retention_until < NOW();

-- =============================================
-- TRIGGERS AND FUNCTIONS
-- =============================================

-- Function to update updated_at timestamp
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

-- Function to validate team assignments
CREATE OR REPLACE FUNCTION validate_team_assignments()
RETURNS TRIGGER AS $$
DECLARE
    team_count INTEGER;
BEGIN
    -- Check that each team has exactly 2 players for a 4-player game
    SELECT COUNT(DISTINCT team) INTO team_count
    FROM game_participants 
    WHERE game_session_id = NEW.game_session_id;
    
    IF team_count > 2 THEN
        RAISE EXCEPTION 'Game cannot have more than 2 teams';
    END IF;
    
    -- Check team balance for 4-player games
    IF (SELECT max_players FROM game_sessions WHERE id = NEW.game_session_id) = 4 THEN
        IF (SELECT COUNT(*) FROM game_participants 
            WHERE game_session_id = NEW.game_session_id AND team = NEW.team) >= 2 THEN
            RAISE EXCEPTION 'Team % already has 2 players', NEW.team;
        END IF;
    END IF;
    
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Trigger for team validation
CREATE TRIGGER validate_team_assignments_trigger
    BEFORE INSERT ON game_participants
    FOR EACH ROW EXECUTE FUNCTION validate_team_assignments();

-- Function to update player statistics when game completes
CREATE OR REPLACE FUNCTION update_player_stats_on_game_complete()
RETURNS TRIGGER AS $$
BEGIN
    -- Only update stats when game status changes to completed
    IF NEW.status = 'completed' AND OLD.status != 'completed' THEN
        -- Update player statistics
        WITH game_results AS (
            SELECT 
                gp.player_id,
                gp.team,
                CASE 
                    WHEN (NEW.scores->('team' || gp.team::text))::integer > 
                         (NEW.scores->('team' || (CASE WHEN gp.team = 1 THEN 2 ELSE 1 END)::text))::integer 
                    THEN 'win'
                    WHEN (NEW.scores->('team' || gp.team::text))::integer < 
                         (NEW.scores->('team' || (CASE WHEN gp.team = 1 THEN 2 ELSE 1 END)::text))::integer 
                    THEN 'loss'
                    ELSE 'draw'
                END as result
            FROM game_participants gp
            WHERE gp.game_session_id = NEW.id
        )
        UPDATE players 
        SET 
            total_games = total_games + 1,
            wins = wins + CASE WHEN gr.result = 'win' THEN 1 ELSE 0 END,
            losses = losses + CASE WHEN gr.result = 'loss' THEN 1 ELSE 0 END,
            draws = draws + CASE WHEN gr.result = 'draw' THEN 1 ELSE 0 END,
            last_seen = NOW()
        FROM game_results gr
        WHERE players.id = gr.player_id;
        
        -- Create game history record
        INSERT INTO game_history (
            game_session_id, game_type, total_rounds, total_tricks,
            game_duration, winning_team, final_scores, trump_suit,
            hakem_player_id, started_at, completed_at
        ) VALUES (
            NEW.id, NEW.game_type, NEW.current_round, 
            (NEW.current_round * 13), -- Estimate total tricks
            NEW.completed_at - NEW.started_at,
            CASE 
                WHEN (NEW.scores->>'team1')::integer > (NEW.scores->>'team2')::integer THEN 1
                WHEN (NEW.scores->>'team1')::integer < (NEW.scores->>'team2')::integer THEN 2
                ELSE NULL
            END,
            NEW.scores, NEW.trump_suit, NEW.hakem_id,
            NEW.started_at, NEW.completed_at
        );
    END IF;
    
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Trigger for game completion
CREATE TRIGGER update_stats_on_game_complete 
    AFTER UPDATE ON game_sessions 
    FOR EACH ROW EXECUTE FUNCTION update_player_stats_on_game_complete();

-- =============================================
-- CONSTRAINTS AND CHECKS
-- =============================================

-- Additional check constraints for data integrity
ALTER TABLE game_sessions ADD CONSTRAINT check_current_player_valid 
    CHECK (current_player_position IS NULL OR 
           current_player_position IN (
               SELECT position FROM game_participants 
               WHERE game_session_id = game_sessions.id
           ));

-- Add constraint to ensure hakem is a participant
ALTER TABLE game_sessions ADD CONSTRAINT check_hakem_is_participant
    CHECK (hakem_id IS NULL OR 
           hakem_id IN (
               SELECT player_id FROM game_participants 
               WHERE game_session_id = game_sessions.id
           ));

-- =============================================
-- VIEWS FOR COMMON QUERIES
-- =============================================

-- Active games view
CREATE VIEW active_games AS
SELECT 
    gs.id,
    gs.room_id,
    gs.status,
    gs.phase,
    gs.current_players,
    gs.max_players,
    gs.game_type,
    gs.created_at,
    gs.started_at,
    EXTRACT(EPOCH FROM (NOW() - gs.started_at)) as duration_seconds,
    p.username as hakem_username,
    string_agg(pl.username, ', ' ORDER BY gp.position) as players
FROM game_sessions gs
LEFT JOIN players p ON gs.hakem_id = p.id
JOIN game_participants gp ON gs.id = gp.game_session_id
JOIN players pl ON gp.player_id = pl.id
WHERE gs.status IN ('waiting', 'starting', 'active', 'paused')
GROUP BY gs.id, gs.room_id, gs.status, gs.phase, gs.current_players, 
         gs.max_players, gs.game_type, gs.created_at, gs.started_at, p.username;

-- Player leaderboard view
CREATE VIEW player_leaderboard AS
SELECT 
    p.id,
    p.username,
    p.display_name,
    p.rating,
    p.total_games,
    p.wins,
    p.losses,
    p.draws,
    CASE 
        WHEN p.total_games > 0 THEN ROUND((p.wins::DECIMAL / p.total_games) * 100, 2)
        ELSE 0 
    END as win_percentage,
    ROW_NUMBER() OVER (ORDER BY p.rating DESC, p.wins DESC) as rank,
    p.last_seen
FROM players p
WHERE p.is_active = TRUE
  AND p.total_games >= 5  -- Only players with at least 5 games
ORDER BY p.rating DESC, p.wins DESC;

-- Recent games view
CREATE VIEW recent_games AS
SELECT 
    gh.id,
    gs.room_id,
    gh.game_type,
    gh.game_duration,
    gh.winning_team,
    gh.final_scores,
    ph.username as hakem_username,
    gh.completed_at,
    string_agg(p.username, ', ' ORDER BY pgs.position) as players
FROM game_history gh
JOIN game_sessions gs ON gh.game_session_id = gs.id
LEFT JOIN players ph ON gh.hakem_player_id = ph.id
JOIN player_game_stats pgs ON gh.id = pgs.game_history_id
JOIN players p ON pgs.player_id = p.id
WHERE gh.completed_at > NOW() - INTERVAL '24 hours'
GROUP BY gh.id, gs.room_id, gh.game_type, gh.game_duration, 
         gh.winning_team, gh.final_scores, ph.username, gh.completed_at
ORDER BY gh.completed_at DESC;

-- =============================================
-- GRANTS AND PERMISSIONS
-- =============================================

-- Create application roles
DO $$
BEGIN
    -- Application user (main game server)
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'hokm_app') THEN
        CREATE ROLE hokm_app WITH LOGIN PASSWORD 'app_secure_password_change_this';
    END IF;
    
    -- Read-only user (analytics, reporting)
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'hokm_readonly') THEN
        CREATE ROLE hokm_readonly WITH LOGIN PASSWORD 'readonly_secure_password_change_this';
    END IF;
    
    -- Admin user (full access)
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'hokm_admin') THEN
        CREATE ROLE hokm_admin WITH LOGIN PASSWORD 'admin_secure_password_change_this' CREATEDB;
    END IF;
END
$$;

-- Grant permissions
GRANT CONNECT ON DATABASE hokm_game TO hokm_app, hokm_readonly, hokm_admin;
GRANT USAGE ON SCHEMA hokm_game TO hokm_app, hokm_readonly, hokm_admin;

-- Application user permissions
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA hokm_game TO hokm_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA hokm_game TO hokm_app;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA hokm_game TO hokm_app;

-- Read-only user permissions
GRANT SELECT ON ALL TABLES IN SCHEMA hokm_game TO hokm_readonly;

-- Admin user permissions (full access)
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA hokm_game TO hokm_admin;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA hokm_game TO hokm_admin;
GRANT ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA hokm_game TO hokm_admin;

-- Set default privileges for future objects
ALTER DEFAULT PRIVILEGES IN SCHEMA hokm_game GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO hokm_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA hokm_game GRANT USAGE, SELECT ON SEQUENCES TO hokm_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA hokm_game GRANT EXECUTE ON FUNCTIONS TO hokm_app;

ALTER DEFAULT PRIVILEGES IN SCHEMA hokm_game GRANT SELECT ON TABLES TO hokm_readonly;

-- =============================================
-- SAMPLE DATA FOR TESTING
-- =============================================

-- Insert sample data (uncomment for testing)
/*
INSERT INTO players (username, email, display_name) VALUES
('player1', 'player1@example.com', 'Player One'),
('player2', 'player2@example.com', 'Player Two'),
('player3', 'player3@example.com', 'Player Three'),
('player4', 'player4@example.com', 'Player Four');
*/

-- =============================================
-- MAINTENANCE AND CLEANUP
-- =============================================

-- Function to clean up old audit logs
CREATE OR REPLACE FUNCTION cleanup_old_audit_logs()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM audit_logs WHERE retention_until < NOW();
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    
    INSERT INTO performance_metrics (metric_type, metric_name, metric_count)
    VALUES ('cleanup', 'audit_logs_deleted', deleted_count);
    
    RETURN deleted_count;
END;
$$ language 'plpgsql';

-- Function to clean up old performance metrics (keep last 30 days)
CREATE OR REPLACE FUNCTION cleanup_old_performance_metrics()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM performance_metrics 
    WHERE timestamp < NOW() - INTERVAL '30 days'
      AND metric_type != 'cleanup'; -- Keep cleanup metrics longer
    
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    
    INSERT INTO performance_metrics (metric_type, metric_name, metric_count)
    VALUES ('cleanup', 'performance_metrics_deleted', deleted_count);
    
    RETURN deleted_count;
END;
$$ language 'plpgsql';

-- Function to update player ratings (placeholder for ELO system)
CREATE OR REPLACE FUNCTION update_player_ratings()
RETURNS VOID AS $$
BEGIN
    -- Placeholder for rating calculation algorithm
    -- This would implement ELO rating or similar system
    -- based on game outcomes and opponent ratings
    
    INSERT INTO performance_metrics (metric_type, metric_name, metric_count)
    VALUES ('maintenance', 'rating_update_completed', 1);
END;
$$ language 'plpgsql';

-- =============================================
-- SCHEMA VALIDATION
-- =============================================

-- Function to validate schema integrity
CREATE OR REPLACE FUNCTION validate_schema_integrity()
RETURNS TABLE(check_name TEXT, status TEXT, details TEXT) AS $$
BEGIN
    -- Check for orphaned records
    RETURN QUERY
    SELECT 
        'orphaned_game_participants'::TEXT,
        CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END::TEXT,
        ('Found ' || COUNT(*) || ' orphaned game participants')::TEXT
    FROM game_participants gp
    LEFT JOIN game_sessions gs ON gp.game_session_id = gs.id
    WHERE gs.id IS NULL;
    
    RETURN QUERY
    SELECT 
        'orphaned_game_moves'::TEXT,
        CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END::TEXT,
        ('Found ' || COUNT(*) || ' orphaned game moves')::TEXT
    FROM game_moves gm
    LEFT JOIN game_sessions gs ON gm.game_session_id = gs.id
    WHERE gs.id IS NULL;
    
    -- Check constraint violations
    RETURN QUERY
    SELECT 
        'invalid_player_stats'::TEXT,
        CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END::TEXT,
        ('Found ' || COUNT(*) || ' players with invalid stats')::TEXT
    FROM players
    WHERE wins + losses + draws > total_games;
    
    -- Check index health
    RETURN QUERY
    SELECT 
        'index_health'::TEXT,
        'INFO'::TEXT,
        ('Total indexes: ' || COUNT(*))::TEXT
    FROM pg_indexes
    WHERE schemaname = 'hokm_game';
END;
$$ language 'plpgsql';

-- Create a summary comment
COMMENT ON SCHEMA hokm_game IS 'Hokm Card Game Database Schema - Optimized for PostgreSQL with comprehensive indexing and constraints';

-- Schema version tracking
CREATE TABLE schema_versions (
    version VARCHAR(20) PRIMARY KEY,
    description TEXT,
    applied_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

INSERT INTO schema_versions (version, description) 
VALUES ('1.0.0', 'Initial comprehensive schema with all core tables, indexes, and constraints');

-- Final message
DO $$
BEGIN
    RAISE NOTICE 'Hokm Game Database Schema v1.0.0 created successfully!';
    RAISE NOTICE 'Schema includes: % tables, comprehensive indexes, triggers, views, and functions', 
        (SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'hokm_game');
END
$$;
