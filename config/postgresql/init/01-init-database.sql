#!/bin/bash
# 01-init-database.sql
# Database initialization script for Hokm Game Server

\echo 'Creating Hokm Game Database Schema...'

-- Create extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_stat_statements";
CREATE EXTENSION IF NOT EXISTS "pg_buffercache";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Create database users
DO $$
BEGIN
    -- Create replication user
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'replicator') THEN
        CREATE ROLE replicator WITH REPLICATION PASSWORD 'repl_secure_2024!' LOGIN;
    END IF;
    
    -- Create application user with limited privileges
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'hokm_game_user') THEN
        CREATE ROLE hokm_game_user WITH PASSWORD 'game_user_secure_2024!' LOGIN;
    END IF;
    
    -- Create read-only user for analytics
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'hokm_readonly') THEN
        CREATE ROLE hokm_readonly WITH PASSWORD 'readonly_secure_2024!' LOGIN;
    END IF;
END
$$;

-- Create database schema
CREATE SCHEMA IF NOT EXISTS hokm_game;
CREATE SCHEMA IF NOT EXISTS analytics;
CREATE SCHEMA IF NOT EXISTS audit;

-- Set search path
ALTER DATABASE hokm_game SET search_path TO hokm_game, public;

\echo 'Database initialization completed successfully!'
