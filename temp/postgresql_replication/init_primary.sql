-- PostgreSQL Primary Server Initialization
-- Creates replication user and game database

-- Create replication user
CREATE USER replicator WITH REPLICATION ENCRYPTED PASSWORD 'repl_password123';

-- Create replication slot
SELECT pg_create_physical_replication_slot('standby_slot_1');

-- Create game database
CREATE DATABASE hokm_game;

-- Connect to game database
\c hokm_game;

-- Create game user
CREATE USER game_user WITH ENCRYPTED PASSWORD 'game_password123';

-- Grant permissions
GRANT ALL PRIVILEGES ON DATABASE hokm_game TO game_user;

-- Create game tables for fault tolerance testing
CREATE TABLE IF NOT EXISTS game_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    room_code VARCHAR(10) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    game_state JSONB,
    active_players INTEGER DEFAULT 0,
    status VARCHAR(20) DEFAULT 'waiting'
);

CREATE TABLE IF NOT EXISTS players (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    games_played INTEGER DEFAULT 0,
    games_won INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS game_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID REFERENCES game_sessions(id),
    player_id UUID REFERENCES players(id),
    event_type VARCHAR(50) NOT NULL,
    event_data JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for performance
CREATE INDEX idx_game_sessions_room_code ON game_sessions(room_code);
CREATE INDEX idx_game_sessions_status ON game_sessions(status);
CREATE INDEX idx_players_username ON players(username);
CREATE INDEX idx_game_events_session_id ON game_events(session_id);
CREATE INDEX idx_game_events_created_at ON game_events(created_at);

-- Grant permissions to game user
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO game_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO game_user;

-- Insert test data for fault tolerance demonstration
INSERT INTO players (username, email) VALUES 
    ('Player1', 'player1@example.com'),
    ('Player2', 'player2@example.com'),
    ('Player3', 'player3@example.com'),
    ('Player4', 'player4@example.com')
ON CONFLICT (username) DO NOTHING;

-- Create a function to simulate game activity
CREATE OR REPLACE FUNCTION simulate_game_activity()
RETURNS VOID AS $$
BEGIN
    -- Insert random game session
    INSERT INTO game_sessions (room_code, active_players, status)
    VALUES ('TEST' || floor(random() * 1000), floor(random() * 4) + 1, 'active');
    
    -- Log the activity
    RAISE NOTICE 'Simulated game activity at %', NOW();
END;
$$ LANGUAGE plpgsql;

-- Show replication status
SELECT slot_name, active, restart_lsn FROM pg_replication_slots;

COMMIT;
