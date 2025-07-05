"""
Database setup, migration, and schema tests for PostgreSQL integration.
Tests database initialization, migrations, and schema validation.
"""

import pytest
import asyncio
import os
from typing import Dict, List, Any
from pathlib import Path


@pytest.mark.asyncio
@pytest.mark.database
@pytest.mark.integration
class TestDatabaseSetup:
    """Test database setup, migrations, and schema validation."""
    
    async def test_database_connection_string_validation(self, db_manager):
        """Test database connection string validation."""
        # Test valid connection
        assert db_manager is not None
        
        # Test connection parameters
        connection_info = await db_manager.get_connection_info()
        
        required_params = ["host", "port", "database", "user"]
        for param in required_params:
            assert param in connection_info, f"Missing connection parameter: {param}"
    
    async def test_database_initialization(self, db_manager):
        """Test database initialization and table creation."""
        # Test if all required tables exist
        async with db_manager.get_session() as session:
            # Check for core tables
            tables_query = """
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_type = 'BASE TABLE'
            """
            result = await session.execute(tables_query)
            existing_tables = {row[0] for row in result.fetchall()}
            
            expected_tables = {
                "players",
                "game_sessions", 
                "game_moves",
                "player_stats",
                "game_session_players"
            }
            
            missing_tables = expected_tables - existing_tables
            assert len(missing_tables) == 0, f"Missing tables: {missing_tables}"
    
    async def test_table_schema_validation(self, db_manager):
        """Test that tables have correct schema structure."""
        async with db_manager.get_session() as session:
            # Test players table schema
            players_schema = await session.execute("""
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_name = 'players'
                ORDER BY ordinal_position
            """)
            
            players_cols = {row[0]: {"type": row[1], "nullable": row[2], "default": row[3]} 
                          for row in players_schema.fetchall()}
            
            # Verify required columns exist
            required_player_cols = ["id", "username", "email", "created_at", "is_active"]
            for col in required_player_cols:
                assert col in players_cols, f"Missing column in players table: {col}"
            
            # Test game_sessions table schema
            sessions_schema = await session.execute("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_name = 'game_sessions'
                ORDER BY ordinal_position
            """)
            
            sessions_cols = {row[0]: {"type": row[1], "nullable": row[2]} 
                           for row in sessions_schema.fetchall()}
            
            required_session_cols = ["id", "session_id", "creator_id", "game_phase", "created_at"]
            for col in required_session_cols:
                assert col in sessions_cols, f"Missing column in game_sessions table: {col}"
    
    async def test_database_indexes(self, db_manager):
        """Test that required indexes exist for performance."""
        async with db_manager.get_session() as session:
            indexes_query = """
                SELECT 
                    schemaname,
                    tablename,
                    indexname,
                    indexdef
                FROM pg_indexes
                WHERE schemaname = 'public'
                ORDER BY tablename, indexname
            """
            
            result = await session.execute(indexes_query)
            indexes = {f"{row[1]}.{row[2]}": row[3] for row in result.fetchall()}
            
            # Check for important performance indexes
            expected_indexes = [
                "players_username",
                "players_email", 
                "game_sessions_session_id",
                "game_moves_session_id",
                "player_stats_player_id"
            ]
            
            for expected_index in expected_indexes:
                matching_indexes = [idx for idx in indexes.keys() if expected_index in idx]
                assert len(matching_indexes) > 0, f"Missing index pattern: {expected_index}"
    
    async def test_database_constraints(self, db_manager):
        """Test that database constraints are properly defined."""
        async with db_manager.get_session() as session:
            # Check primary key constraints
            pk_query = """
                SELECT 
                    tc.table_name,
                    tc.constraint_name,
                    tc.constraint_type
                FROM information_schema.table_constraints tc
                WHERE tc.constraint_type = 'PRIMARY KEY'
                AND tc.table_schema = 'public'
            """
            
            result = await session.execute(pk_query)
            primary_keys = {row[0]: row[1] for row in result.fetchall()}
            
            required_pk_tables = ["players", "game_sessions", "game_moves", "player_stats"]
            for table in required_pk_tables:
                assert table in primary_keys, f"Missing primary key for table: {table}"
            
            # Check foreign key constraints
            fk_query = """
                SELECT 
                    tc.table_name,
                    tc.constraint_name,
                    kcu.column_name,
                    ccu.table_name AS foreign_table_name,
                    ccu.column_name AS foreign_column_name
                FROM information_schema.table_constraints AS tc
                JOIN information_schema.key_column_usage AS kcu
                    ON tc.constraint_name = kcu.constraint_name
                    AND tc.table_schema = kcu.table_schema
                JOIN information_schema.constraint_column_usage AS ccu
                    ON ccu.constraint_name = tc.constraint_name
                    AND ccu.table_schema = tc.table_schema
                WHERE tc.constraint_type = 'FOREIGN KEY'
                AND tc.table_schema = 'public'
            """
            
            result = await session.execute(fk_query)
            foreign_keys = result.fetchall()
            
            # Should have foreign keys for relationships
            fk_tables = {row[0] for row in foreign_keys}
            expected_fk_tables = ["game_sessions", "game_moves", "player_stats", "game_session_players"]
            
            for table in expected_fk_tables:
                assert table in fk_tables, f"Missing foreign key constraints for table: {table}"
    
    async def test_database_triggers_and_functions(self, db_manager):
        """Test that database triggers and functions are properly set up."""
        async with db_manager.get_session() as session:
            # Check for timestamp triggers (updated_at auto-update)
            triggers_query = """
                SELECT 
                    trigger_name,
                    event_object_table,
                    action_timing,
                    event_manipulation
                FROM information_schema.triggers
                WHERE trigger_schema = 'public'
            """
            
            result = await session.execute(triggers_query)
            triggers = result.fetchall()
            
            # Should have update timestamp triggers
            trigger_tables = {row[1] for row in triggers}
            expected_trigger_tables = ["players", "game_sessions", "player_stats"]
            
            for table in expected_trigger_tables:
                if f"{table}_updated_at" not in [t[0] for t in triggers]:
                    print(f"Warning: No updated_at trigger found for table: {table}")
    
    async def test_database_permissions(self, db_manager):
        """Test database user permissions."""
        async with db_manager.get_session() as session:
            # Test basic permissions
            try:
                # Should be able to SELECT
                await session.execute("SELECT 1")
                
                # Should be able to INSERT (in transaction)
                await session.execute("INSERT INTO players (username, email) VALUES ('test_perm', 'test@perm.com')")
                await session.rollback()  # Don't actually insert
                
                # Should be able to UPDATE (in transaction)
                await session.execute("UPDATE players SET last_login = NOW() WHERE username = 'nonexistent'")
                await session.rollback()
                
                # Should be able to DELETE (in transaction)
                await session.execute("DELETE FROM players WHERE username = 'nonexistent'")
                await session.rollback()
                
            except Exception as e:
                pytest.fail(f"Database permission test failed: {e}")
    
    async def test_database_connection_pooling(self, db_manager):
        """Test database connection pooling configuration."""
        # Test multiple concurrent connections
        sessions = []
        
        try:
            for i in range(5):
                session = db_manager.get_session()
                sessions.append(session)
            
            # All sessions should be created successfully
            assert len(sessions) == 5
            
            # Test that connections can execute queries
            for i, session in enumerate(sessions):
                async with session as s:
                    result = await s.execute(f"SELECT {i+1} as test_num")
                    row = result.fetchone()
                    assert row[0] == i + 1
                    
        finally:
            # Cleanup sessions
            for session in sessions:
                if hasattr(session, 'close'):
                    await session.close()


@pytest.mark.asyncio
@pytest.mark.database
@pytest.mark.migration
class TestDatabaseMigrations:
    """Test database migrations and version management."""
    
    async def test_migration_version_tracking(self, db_manager):
        """Test that migration versions are properly tracked."""
        async with db_manager.get_session() as session:
            # Check if alembic version table exists
            version_table_query = """
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_name = 'alembic_version'
                AND table_schema = 'public'
            """
            
            result = await session.execute(version_table_query)
            version_table = result.fetchone()
            
            if version_table:
                # Get current version
                current_version = await session.execute("SELECT version_num FROM alembic_version")
                version = current_version.fetchone()
                
                assert version is not None, "No migration version found"
                assert len(version[0]) > 0, "Migration version is empty"
            else:
                print("Warning: Alembic version table not found - migrations may not be set up")
    
    async def test_schema_migration_integrity(self, db_manager):
        """Test that schema changes maintain data integrity."""
        async with db_manager.get_session() as session:
            # Test that all tables can be accessed after migrations
            tables_query = """
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_type = 'BASE TABLE'
                AND table_name != 'alembic_version'
            """
            
            result = await session.execute(tables_query)
            tables = [row[0] for row in result.fetchall()]
            
            # Try to select from each table to ensure they're accessible
            for table in tables:
                try:
                    await session.execute(f"SELECT COUNT(*) FROM {table}")
                except Exception as e:
                    pytest.fail(f"Cannot access table {table} after migration: {e}")
    
    async def test_rollback_capability(self, db_manager):
        """Test that database can handle transaction rollbacks properly."""
        async with db_manager.get_session() as session:
            try:
                # Start transaction
                trans = await session.begin()
                
                # Make some changes
                await session.execute("INSERT INTO players (username, email) VALUES ('rollback_test', 'rollback@test.com')")
                
                # Verify change is visible in transaction
                result = await session.execute("SELECT COUNT(*) FROM players WHERE username = 'rollback_test'")
                count_in_transaction = result.scalar()
                assert count_in_transaction == 1, "Insert not visible in transaction"
                
                # Rollback
                await trans.rollback()
                
                # Verify change is not persisted
                result = await session.execute("SELECT COUNT(*) FROM players WHERE username = 'rollback_test'")
                count_after_rollback = result.scalar()
                assert count_after_rollback == 0, "Data persisted after rollback"
                
            except Exception as e:
                pytest.fail(f"Rollback test failed: {e}")


@pytest.mark.asyncio
@pytest.mark.database
@pytest.mark.backup
class TestDatabaseBackupAndRecovery:
    """Test database backup and recovery capabilities."""
    
    async def test_connection_recovery_after_failure(self, db_manager):
        """Test that connections can be recovered after database issues."""
        # This test would typically involve simulating database disconnection
        # For now, we test basic connection resilience
        
        async with db_manager.get_session() as session:
            # Test basic operation
            result = await session.execute("SELECT 1")
            assert result.fetchone()[0] == 1
        
        # Test that new connections work after the previous one
        async with db_manager.get_session() as session:
            result = await session.execute("SELECT 2")
            assert result.fetchone()[0] == 2
    
    async def test_data_consistency_checks(self, db_manager):
        """Test basic data consistency checks."""
        async with db_manager.get_session() as session:
            # Check for orphaned records (basic referential integrity)
            
            # Check for game moves without valid sessions
            orphaned_moves = await session.execute("""
                SELECT COUNT(*) 
                FROM game_moves gm 
                LEFT JOIN game_sessions gs ON gm.session_id = gs.session_id 
                WHERE gs.session_id IS NULL
            """)
            
            orphan_count = orphaned_moves.scalar()
            assert orphan_count == 0, f"Found {orphan_count} orphaned game moves"
            
            # Check for player stats without valid players
            orphaned_stats = await session.execute("""
                SELECT COUNT(*) 
                FROM player_stats ps 
                LEFT JOIN players p ON ps.player_id = p.id 
                WHERE p.id IS NULL
            """)
            
            orphan_stats_count = orphaned_stats.scalar()
            assert orphan_stats_count == 0, f"Found {orphan_stats_count} orphaned player stats"
    
    async def test_database_size_monitoring(self, db_manager):
        """Test database size monitoring capabilities."""
        async with db_manager.get_session() as session:
            # Get database size information
            size_query = """
                SELECT 
                    pg_size_pretty(pg_database_size(current_database())) as db_size,
                    pg_database_size(current_database()) as db_size_bytes
            """
            
            result = await session.execute(size_query)
            size_info = result.fetchone()
            
            assert size_info is not None, "Could not retrieve database size"
            assert size_info[1] > 0, "Database size should be greater than 0"
            
            # Get table sizes
            table_sizes_query = """
                SELECT 
                    schemaname,
                    tablename,
                    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size,
                    pg_total_relation_size(schemaname||'.'||tablename) as size_bytes
                FROM pg_tables 
                WHERE schemaname = 'public'
                ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
            """
            
            result = await session.execute(table_sizes_query)
            table_sizes = result.fetchall()
            
            assert len(table_sizes) > 0, "No table size information found"
            
            # Log table sizes for monitoring
            print("\nTable sizes:")
            for schema, table, size_pretty, size_bytes in table_sizes:
                print(f"  {table}: {size_pretty}")
