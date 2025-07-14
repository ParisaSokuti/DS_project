-- PostgreSQL Primary Server Initialization Script
-- This script sets up the primary server for streaming replication

-- Create replication user
CREATE USER replicator WITH REPLICATION LOGIN ENCRYPTED PASSWORD 'replicator_password';

-- Create replication slot
SELECT pg_create_physical_replication_slot('replica_slot_1');

-- Create hokm_db database if it doesn't exist
CREATE DATABASE hokm_db;

-- Connect to hokm_db
\c hokm_db;

-- Create basic tables for testing
CREATE TABLE IF NOT EXISTS replication_test (
    id SERIAL PRIMARY KEY,
    data TEXT NOT NULL,
    created TIMESTAMP DEFAULT NOW()
);

-- Insert test data
INSERT INTO replication_test (data) VALUES 
    ('Primary server initialized'),
    ('Replication test data'),
    ('Ready for standby connection');

-- Create a function to generate test data
CREATE OR REPLACE FUNCTION generate_test_data(count INTEGER DEFAULT 10)
RETURNS void AS $$
BEGIN
    FOR i IN 1..count LOOP
        INSERT INTO replication_test (data) VALUES ('Test data ' || i || ' at ' || NOW());
    END LOOP;
END;
$$ LANGUAGE plpgsql;

-- Create a view to monitor replication
CREATE OR REPLACE VIEW replication_status AS
SELECT 
    application_name,
    client_addr,
    state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    write_lag,
    flush_lag,
    replay_lag,
    sync_state
FROM pg_stat_replication;

-- Grant permissions
GRANT SELECT ON replication_test TO replicator;
GRANT SELECT ON replication_status TO replicator;

-- Display setup information
SELECT 'Primary server initialized successfully' AS status;
SELECT 'Replication slot created: replica_slot_1' AS replication_slot;
SELECT 'Test data inserted: ' || COUNT(*) || ' rows' AS test_data FROM replication_test;
