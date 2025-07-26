-- 02-create-tables.sql
-- Hokm Game Database Schema

\echo 'Creating Hokm Game Tables...'

-- Set schema
SET search_path TO hokm_game, public;

-- Players table
CREATE TABLE IF NOT EXISTS players (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE,
    password_hash VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_seen TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT true,
    total_games INTEGER DEFAULT 0,
    wins INTEGER DEFAULT 0,
    losses INTEGER DEFAULT 0,
    rating INTEGER DEFAULT 1000,
    
    -- Constraints
    CONSTRAINT valid_email CHECK (email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$'),
    CONSTRAINT valid_username CHECK (length(username) >= 3 AND username ~* '^[A-Za-z0-9_-]+$'),
    CONSTRAINT valid_rating CHECK (rating >= 0 AND rating <= 3000)
);

-- Game sessions table
CREATE TABLE IF NOT EXISTS game_sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    room_id VARCHAR(100) UNIQUE NOT NULL,
    session_key VARCHAR(255) UNIQUE NOT NULL,
    status VARCHAR(20) DEFAULT 'waiting' CHECK (status IN ('waiting', 'active', 'completed', 'abandoned')),
    max_players INTEGER DEFAULT 4 CHECK (max_players BETWEEN 2 AND 4),
    current_players INTEGER DEFAULT 0,
    hakem_id UUID REFERENCES players(id),
    trump_suit VARCHAR(10),
    current_round INTEGER DEFAULT 1 CHECK (current_round BETWEEN 1 AND 7),
    
    -- Game state (stored as JSONB for flexibility)
    game_state JSONB DEFAULT '{}',
    player_hands JSONB DEFAULT '{}',
    played_cards JSONB DEFAULT '[]',
    scores JSONB DEFAULT '{}',
    
    -- Metadata
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Performance indexes
    CONSTRAINT valid_room_id CHECK (length(room_id) >= 3)
);

-- Game participants table (many-to-many relationship)
CREATE TABLE IF NOT EXISTS game_participants (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    game_session_id UUID NOT NULL REFERENCES game_sessions(id) ON DELETE CASCADE,
    player_id UUID NOT NULL REFERENCES players(id),
    position INTEGER CHECK (position BETWEEN 0 AND 3),
    team INTEGER CHECK (team IN (1, 2)),
    is_connected BOOLEAN DEFAULT true,
    joined_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    left_at TIMESTAMP WITH TIME ZONE,
    reconnected_at TIMESTAMP WITH TIME ZONE,
    
    -- Ensure unique position per game
    UNIQUE (game_session_id, position),
    UNIQUE (game_session_id, player_id)
);

-- Game moves/actions table (for audit and replay)
CREATE TABLE IF NOT EXISTS game_moves (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    game_session_id UUID NOT NULL REFERENCES game_sessions(id) ON DELETE CASCADE,
    player_id UUID NOT NULL REFERENCES players(id),
    move_type VARCHAR(20) NOT NULL CHECK (move_type IN ('play_card', 'choose_trump', 'pass', 'reconnect', 'disconnect')),
    move_data JSONB NOT NULL DEFAULT '{}',
    round_number INTEGER NOT NULL,
    trick_number INTEGER,
    sequence_number INTEGER NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Ensure moves are ordered
    UNIQUE (game_session_id, sequence_number)
);

-- WebSocket connections table (for session management)
CREATE TABLE IF NOT EXISTS websocket_connections (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    player_id UUID REFERENCES players(id),
    game_session_id UUID REFERENCES game_sessions(id),
    connection_id VARCHAR(255) UNIQUE NOT NULL,
    ip_address INET,
    user_agent TEXT,
    connected_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_ping TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    disconnected_at TIMESTAMP WITH TIME ZONE,
    is_active BOOLEAN DEFAULT true
);

-- Game statistics table (for analytics)
CREATE TABLE IF NOT EXISTS game_statistics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    game_session_id UUID NOT NULL REFERENCES game_sessions(id),
    player_id UUID NOT NULL REFERENCES players(id),
    team INTEGER NOT NULL,
    final_score INTEGER DEFAULT 0,
    rounds_won INTEGER DEFAULT 0,
    cards_played INTEGER DEFAULT 0,
    trump_choices INTEGER DEFAULT 0,
    average_response_time INTERVAL,
    disconnections INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Performance monitoring table
CREATE TABLE IF NOT EXISTS performance_metrics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    metric_type VARCHAR(50) NOT NULL,
    metric_name VARCHAR(100) NOT NULL,
    metric_value DECIMAL(10,4),
    metadata JSONB DEFAULT '{}',
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

\echo 'Creating indexes for optimal performance...'

-- Performance indexes
CREATE INDEX IF NOT EXISTS idx_players_username ON players(username);
CREATE INDEX IF NOT EXISTS idx_players_email ON players(email);
CREATE INDEX IF NOT EXISTS idx_players_rating ON players(rating DESC);
CREATE INDEX IF NOT EXISTS idx_players_last_seen ON players(last_seen DESC);

CREATE INDEX IF NOT EXISTS idx_game_sessions_room_id ON game_sessions(room_id);
CREATE INDEX IF NOT EXISTS idx_game_sessions_status ON game_sessions(status);
CREATE INDEX IF NOT EXISTS idx_game_sessions_created_at ON game_sessions(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_game_sessions_hakem_id ON game_sessions(hakem_id);

CREATE INDEX IF NOT EXISTS idx_game_participants_session ON game_participants(game_session_id);
CREATE INDEX IF NOT EXISTS idx_game_participants_player ON game_participants(player_id);
CREATE INDEX IF NOT EXISTS idx_game_participants_connected ON game_participants(is_connected) WHERE is_connected = true;

CREATE INDEX IF NOT EXISTS idx_game_moves_session ON game_moves(game_session_id);
CREATE INDEX IF NOT EXISTS idx_game_moves_player ON game_moves(player_id);
CREATE INDEX IF NOT EXISTS idx_game_moves_timestamp ON game_moves(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_game_moves_sequence ON game_moves(game_session_id, sequence_number);

CREATE INDEX IF NOT EXISTS idx_websocket_connections_player ON websocket_connections(player_id);
CREATE INDEX IF NOT EXISTS idx_websocket_connections_session ON websocket_connections(game_session_id);
CREATE INDEX IF NOT EXISTS idx_websocket_connections_active ON websocket_connections(is_active) WHERE is_active = true;

CREATE INDEX IF NOT EXISTS idx_game_statistics_session ON game_statistics(game_session_id);
CREATE INDEX IF NOT EXISTS idx_game_statistics_player ON game_statistics(player_id);

CREATE INDEX IF NOT EXISTS idx_performance_metrics_type ON performance_metrics(metric_type, metric_name);
CREATE INDEX IF NOT EXISTS idx_performance_metrics_timestamp ON performance_metrics(timestamp DESC);

-- JSONB indexes for game state queries
CREATE INDEX IF NOT EXISTS idx_game_sessions_game_state ON game_sessions USING GIN(game_state);
CREATE INDEX IF NOT EXISTS idx_game_sessions_scores ON game_sessions USING GIN(scores);

\echo 'Hokm Game Tables created successfully!'
