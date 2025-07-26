-- 04-create-permissions.sql
-- Set up database permissions for different user roles

\echo 'Setting up database permissions...'

-- Grant permissions to hokm_game_user (main application user)
GRANT CONNECT ON DATABASE hokm_game TO hokm_game_user;
GRANT USAGE ON SCHEMA hokm_game TO hokm_game_user;
GRANT USAGE ON SCHEMA audit TO hokm_game_user;

-- Table permissions for application user
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA hokm_game TO hokm_game_user;
GRANT INSERT ON audit.user_actions TO hokm_game_user;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA hokm_game TO hokm_game_user;

-- Function permissions
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA hokm_game TO hokm_game_user;
GRANT EXECUTE ON FUNCTION audit.log_user_action TO hokm_game_user;

-- Grant permissions to hokm_readonly (analytics user)
GRANT CONNECT ON DATABASE hokm_game TO hokm_readonly;
GRANT USAGE ON SCHEMA hokm_game TO hokm_readonly;
GRANT USAGE ON SCHEMA analytics TO hokm_readonly;
GRANT USAGE ON SCHEMA audit TO hokm_readonly;

-- Read-only permissions
GRANT SELECT ON ALL TABLES IN SCHEMA hokm_game TO hokm_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA audit TO hokm_readonly;

-- Ensure future tables inherit permissions
ALTER DEFAULT PRIVILEGES IN SCHEMA hokm_game GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO hokm_game_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA hokm_game GRANT USAGE, SELECT ON SEQUENCES TO hokm_game_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA hokm_game GRANT EXECUTE ON FUNCTIONS TO hokm_game_user;

ALTER DEFAULT PRIVILEGES IN SCHEMA hokm_game GRANT SELECT ON TABLES TO hokm_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA audit GRANT SELECT ON TABLES TO hokm_readonly;

-- Create analytics views
CREATE SCHEMA IF NOT EXISTS analytics;

-- Grant analytics schema permissions
GRANT USAGE ON SCHEMA analytics TO hokm_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA analytics TO hokm_readonly;

\echo 'Database permissions set successfully!'
