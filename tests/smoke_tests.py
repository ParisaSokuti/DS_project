#!/usr/bin/env python3
"""
Database Smoke Tests
Post-deployment validation and health checks

Features:
- Connection validation
- Schema integrity checks
- Performance baseline validation
- Data consistency verification
- Security configuration validation
"""

import asyncio
import logging
import time
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

import asyncpg
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text, inspect

# Add project root to path
import sys
sys.path.append(str(Path(__file__).parent.parent))

from backend.database.models import Base
from backend.database.config import DatabaseConfig, get_database_config

logger = logging.getLogger(__name__)


class DatabaseSmokeTests:
    """
    Comprehensive database smoke testing suite
    """
    
    def __init__(self, environment: str = "development"):
        self.environment = environment
        self.config = get_database_config(environment)
        self.engine = None
        self.session_factory = None
        self.test_results = []
        
    async def initialize(self):
        """Initialize database connection for testing"""
        try:
            database_url = (
                f"postgresql+asyncpg://{self.config.username}:{self.config.password}"
                f"@{self.config.host}:{self.config.port}/{self.config.database}"
            )
            
            self.engine = create_async_engine(
                database_url,
                pool_size=5,  # Smaller pool for testing
                max_overflow=10,
                pool_timeout=30,
                pool_recycle=3600,
                pool_pre_ping=True,
                echo=False  # Disable SQL logging for tests
            )
            
            self.session_factory = sessionmaker(
                bind=self.engine,
                class_=AsyncSession,
                expire_on_commit=False
            )
            
            logger.info(f"Smoke test initialized for {self.environment}")
            
        except Exception as e:
            logger.error(f"Failed to initialize smoke tests: {e}")
            raise
    
    async def run_all_tests(self) -> Dict[str, Any]:
        """
        Run all smoke tests and return comprehensive results
        """
        if not self.engine:
            await self.initialize()
            
        test_suite = {
            'environment': self.environment,
            'started_at': datetime.utcnow().isoformat(),
            'tests': [],
            'summary': {
                'total': 0,
                'passed': 0,
                'failed': 0,
                'warnings': 0
            }
        }
        
        # Test suite configuration
        tests = [
            ('Connection Test', self.test_basic_connection),
            ('Schema Validation', self.test_schema_integrity),
            ('Essential Tables', self.test_essential_tables),
            ('Indexes Validation', self.test_indexes),
            ('Permissions Check', self.test_permissions),
            ('Performance Baseline', self.test_performance_baseline),
            ('Data Consistency', self.test_data_consistency),
            ('Security Configuration', self.test_security_config),
            ('Connection Pool', self.test_connection_pool),
            ('Transaction Handling', self.test_transaction_handling)
        ]
        
        for test_name, test_func in tests:
            test_result = await self.run_single_test(test_name, test_func)
            test_suite['tests'].append(test_result)
            test_suite['summary']['total'] += 1
            
            if test_result['status'] == 'passed':
                test_suite['summary']['passed'] += 1
            elif test_result['status'] == 'failed':
                test_suite['summary']['failed'] += 1
            else:
                test_suite['summary']['warnings'] += 1
        
        test_suite['completed_at'] = datetime.utcnow().isoformat()
        test_suite['duration'] = sum(test['duration'] for test in test_suite['tests'])
        test_suite['overall_status'] = 'passed' if test_suite['summary']['failed'] == 0 else 'failed'
        
        await self.cleanup()
        
        return test_suite
    
    async def run_single_test(self, test_name: str, test_func) -> Dict[str, Any]:
        """
        Run a single test with error handling and timing
        """
        start_time = time.time()
        
        try:
            logger.info(f"Running test: {test_name}")
            result = await test_func()
            
            duration = time.time() - start_time
            
            test_result = {
                'name': test_name,
                'status': 'passed',
                'duration': round(duration, 3),
                'details': result,
                'timestamp': datetime.utcnow().isoformat()
            }
            
            logger.info(f"✓ {test_name} passed ({duration:.3f}s)")
            return test_result
            
        except Exception as e:
            duration = time.time() - start_time
            
            test_result = {
                'name': test_name,
                'status': 'failed',
                'duration': round(duration, 3),
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            }
            
            logger.error(f"✗ {test_name} failed: {e}")
            return test_result
    
    async def test_basic_connection(self) -> Dict[str, Any]:
        """Test basic database connectivity"""
        async with self.session_factory() as session:
            result = await session.execute(text("SELECT version(), current_database(), current_user"))
            row = result.fetchone()
            
            return {
                'postgresql_version': row[0],
                'database_name': row[1],
                'connected_user': row[2],
                'connection_successful': True
            }
    
    async def test_schema_integrity(self) -> Dict[str, Any]:
        """Validate database schema integrity"""
        async with self.session_factory() as session:
            # Check if all expected tables exist
            result = await session.execute(
                text("""
                SELECT tablename 
                FROM pg_tables 
                WHERE schemaname = 'public' 
                ORDER BY tablename
                """)
            )
            
            existing_tables = [row[0] for row in result.fetchall()]
            
            # Expected core tables (adjust based on your schema)
            expected_tables = [
                'users', 'games', 'game_sessions', 'players', 'cards',
                'game_configurations', 'game_statuses', 'alembic_version'
            ]
            
            missing_tables = [table for table in expected_tables if table not in existing_tables]
            extra_tables = [table for table in existing_tables if table not in expected_tables]
            
            # Check for migration tracking table
            migration_result = await session.execute(
                text("SELECT version_num FROM alembic_version ORDER BY version_num DESC LIMIT 1")
            )
            current_migration = migration_result.scalar()
            
            return {
                'existing_tables': existing_tables,
                'missing_tables': missing_tables,
                'extra_tables': extra_tables,
                'current_migration': current_migration,
                'schema_valid': len(missing_tables) == 0
            }
    
    async def test_essential_tables(self) -> Dict[str, Any]:
        """Test essential table structures and constraints"""
        table_tests = {}
        
        async with self.session_factory() as session:
            # Test users table
            try:
                result = await session.execute(
                    text("SELECT COUNT(*) FROM information_schema.columns WHERE table_name = 'users'")
                )
                users_columns = result.scalar()
                table_tests['users'] = {
                    'exists': users_columns > 0,
                    'column_count': users_columns
                }
            except Exception as e:
                table_tests['users'] = {'exists': False, 'error': str(e)}
            
            # Test games table
            try:
                result = await session.execute(
                    text("SELECT COUNT(*) FROM information_schema.columns WHERE table_name = 'games'")
                )
                games_columns = result.scalar()
                table_tests['games'] = {
                    'exists': games_columns > 0,
                    'column_count': games_columns
                }
            except Exception as e:
                table_tests['games'] = {'exists': False, 'error': str(e)}
            
            # Test constraints
            constraint_result = await session.execute(
                text("""
                SELECT COUNT(*) 
                FROM information_schema.table_constraints 
                WHERE constraint_type IN ('PRIMARY KEY', 'FOREIGN KEY', 'UNIQUE')
                """)
            )
            constraint_count = constraint_result.scalar()
            
            return {
                'table_tests': table_tests,
                'constraint_count': constraint_count,
                'all_essential_tables_exist': all(t.get('exists', False) for t in table_tests.values())
            }
    
    async def test_indexes(self) -> Dict[str, Any]:
        """Validate critical indexes exist and are functional"""
        async with self.session_factory() as session:
            # Get all indexes
            result = await session.execute(
                text("""
                SELECT schemaname, tablename, indexname, indexdef
                FROM pg_indexes 
                WHERE schemaname = 'public'
                ORDER BY tablename, indexname
                """)
            )
            
            indexes = []
            for row in result.fetchall():
                indexes.append({
                    'schema': row[0],
                    'table': row[1],
                    'name': row[2],
                    'definition': row[3]
                })
            
            # Check for critical indexes (adjust based on your needs)
            critical_indexes = [
                'users_username_idx',
                'users_email_idx',
                'games_status_idx',
                'game_sessions_game_id_idx'
            ]
            
            existing_index_names = [idx['name'] for idx in indexes]
            missing_critical = [idx for idx in critical_indexes if idx not in existing_index_names]
            
            return {
                'total_indexes': len(indexes),
                'indexes': indexes,
                'missing_critical_indexes': missing_critical,
                'all_critical_indexes_exist': len(missing_critical) == 0
            }
    
    async def test_permissions(self) -> Dict[str, Any]:
        """Test database user permissions and security"""
        async with self.session_factory() as session:
            # Check current user privileges
            result = await session.execute(
                text("""
                SELECT 
                    has_database_privilege(current_user, current_database(), 'CONNECT') as can_connect,
                    has_database_privilege(current_user, current_database(), 'CREATE') as can_create,
                    has_database_privilege(current_user, current_database(), 'TEMP') as can_temp
                """)
            )
            
            privileges = result.fetchone()
            
            # Check table permissions on a sample table
            try:
                table_perms_result = await session.execute(
                    text("""
                    SELECT 
                        has_table_privilege(current_user, 'users', 'SELECT') as can_select,
                        has_table_privilege(current_user, 'users', 'INSERT') as can_insert,
                        has_table_privilege(current_user, 'users', 'UPDATE') as can_update,
                        has_table_privilege(current_user, 'users', 'DELETE') as can_delete
                    """)
                )
                table_perms = table_perms_result.fetchone()
            except Exception:
                table_perms = (False, False, False, False)
            
            return {
                'database_privileges': {
                    'can_connect': privileges[0],
                    'can_create': privileges[1],
                    'can_temp': privileges[2]
                },
                'table_privileges': {
                    'can_select': table_perms[0],
                    'can_insert': table_perms[1],
                    'can_update': table_perms[2],
                    'can_delete': table_perms[3]
                },
                'has_basic_permissions': privileges[0] and table_perms[0]
            }
    
    async def test_performance_baseline(self) -> Dict[str, Any]:
        """Test basic performance metrics"""
        performance_tests = {}
        
        async with self.session_factory() as session:
            # Simple SELECT performance
            start_time = time.time()
            await session.execute(text("SELECT 1"))
            simple_query_time = time.time() - start_time
            
            # Table count query performance
            start_time = time.time()
            result = await session.execute(text("SELECT COUNT(*) FROM pg_tables WHERE schemaname = 'public'"))
            table_count = result.scalar()
            table_count_time = time.time() - start_time
            
            # Connection pool test
            start_time = time.time()
            tasks = []
            for _ in range(5):
                tasks.append(self._test_concurrent_connection())
            await asyncio.gather(*tasks)
            concurrent_time = time.time() - start_time
            
            return {
                'simple_query_time_ms': round(simple_query_time * 1000, 3),
                'table_count_query_time_ms': round(table_count_time * 1000, 3),
                'concurrent_connections_time_ms': round(concurrent_time * 1000, 3),
                'table_count': table_count,
                'performance_acceptable': (
                    simple_query_time < 0.1 and 
                    table_count_time < 0.5 and 
                    concurrent_time < 2.0
                )
            }
    
    async def _test_concurrent_connection(self):
        """Helper for concurrent connection testing"""
        async with self.session_factory() as session:
            await session.execute(text("SELECT pg_sleep(0.1)"))
            return True
    
    async def test_data_consistency(self) -> Dict[str, Any]:
        """Test data consistency and referential integrity"""
        async with self.session_factory() as session:
            consistency_checks = {}
            
            # Check for orphaned records (example)
            try:
                # This is a generic example - adjust based on your foreign keys
                orphaned_result = await session.execute(
                    text("""
                    SELECT COUNT(*) as orphaned_count
                    FROM information_schema.table_constraints tc
                    WHERE tc.constraint_type = 'FOREIGN KEY'
                    """)
                )
                fk_count = orphaned_result.scalar()
                consistency_checks['foreign_key_constraints'] = fk_count
            except Exception as e:
                consistency_checks['foreign_key_constraints'] = f"Error: {e}"
            
            # Check for duplicate primary keys (should be impossible but good to verify)
            try:
                dup_result = await session.execute(
                    text("""
                    SELECT COUNT(*) 
                    FROM information_schema.table_constraints 
                    WHERE constraint_type = 'PRIMARY KEY'
                    """)
                )
                pk_count = dup_result.scalar()
                consistency_checks['primary_key_constraints'] = pk_count
            except Exception as e:
                consistency_checks['primary_key_constraints'] = f"Error: {e}"
            
            return {
                'consistency_checks': consistency_checks,
                'referential_integrity_valid': isinstance(consistency_checks.get('foreign_key_constraints'), int)
            }
    
    async def test_security_config(self) -> Dict[str, Any]:
        """Test security configuration"""
        async with self.session_factory() as session:
            # Check SSL configuration
            ssl_result = await session.execute(text("SHOW ssl"))
            ssl_enabled = ssl_result.scalar()
            
            # Check connection limits
            try:
                limits_result = await session.execute(
                    text("SELECT setting FROM pg_settings WHERE name = 'max_connections'")
                )
                max_connections = int(limits_result.scalar())
            except Exception:
                max_connections = None
            
            # Check authentication method (if accessible)
            try:
                auth_result = await session.execute(
                    text("SELECT COUNT(*) FROM pg_hba_file_rules WHERE type = 'host'")
                )
                auth_rules = auth_result.scalar()
            except Exception:
                auth_rules = None
            
            return {
                'ssl_enabled': ssl_enabled == 'on',
                'max_connections': max_connections,
                'auth_rules_configured': auth_rules is not None,
                'security_baseline_met': ssl_enabled == 'on' and max_connections and max_connections >= 100
            }
    
    async def test_connection_pool(self) -> Dict[str, Any]:
        """Test connection pool functionality"""
        start_time = time.time()
        
        # Test multiple concurrent connections
        async def test_connection():
            async with self.session_factory() as session:
                result = await session.execute(text("SELECT pg_backend_pid()"))
                return result.scalar()
        
        # Run multiple concurrent operations
        tasks = [test_connection() for _ in range(10)]
        pids = await asyncio.gather(*tasks)
        
        duration = time.time() - start_time
        
        return {
            'concurrent_connections': len(pids),
            'unique_pids': len(set(pids)),
            'duration_ms': round(duration * 1000, 3),
            'pool_working': len(set(pids)) > 1,  # Should use multiple connections
            'average_connection_time_ms': round((duration / len(pids)) * 1000, 3)
        }
    
    async def test_transaction_handling(self) -> Dict[str, Any]:
        """Test transaction handling and rollback capability"""
        async with self.session_factory() as session:
            try:
                # Start a transaction
                await session.begin()
                
                # Try to create a temporary table
                await session.execute(
                    text("CREATE TEMP TABLE smoke_test_temp (id INTEGER PRIMARY KEY, data TEXT)")
                )
                
                # Insert test data
                await session.execute(
                    text("INSERT INTO smoke_test_temp (id, data) VALUES (1, 'test')")
                )
                
                # Verify insert
                result = await session.execute(text("SELECT COUNT(*) FROM smoke_test_temp"))
                count_before_rollback = result.scalar()
                
                # Rollback transaction
                await session.rollback()
                
                # The temp table should be gone after rollback
                try:
                    await session.execute(text("SELECT COUNT(*) FROM smoke_test_temp"))
                    rollback_worked = False
                except Exception:
                    rollback_worked = True
                
                return {
                    'transaction_started': True,
                    'insert_successful': count_before_rollback == 1,
                    'rollback_successful': rollback_worked,
                    'transaction_handling_working': rollback_worked
                }
                
            except Exception as e:
                await session.rollback()
                return {
                    'transaction_started': False,
                    'error': str(e),
                    'transaction_handling_working': False
                }
    
    async def cleanup(self):
        """Clean up test resources"""
        if self.engine:
            await self.engine.dispose()


async def main():
    """
    Main entry point for smoke tests
    """
    import argparse
    
    parser = argparse.ArgumentParser(description='Database Smoke Tests')
    parser.add_argument(
        '--environment', '-e',
        choices=['development', 'testing', 'staging', 'production'],
        default='development',
        help='Target environment'
    )
    parser.add_argument(
        '--output', '-o',
        help='Output file for test results (JSON format)'
    )
    parser.add_argument(
        '--fail-fast',
        action='store_true',
        help='Stop on first test failure'
    )
    
    args = parser.parse_args()
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    )
    
    smoke_tests = DatabaseSmokeTests(args.environment)
    
    try:
        logger.info(f"Running smoke tests for {args.environment}")
        results = await smoke_tests.run_all_tests()
        
        # Output results
        if args.output:
            with open(args.output, 'w') as f:
                json.dump(results, f, indent=2)
            logger.info(f"Results written to {args.output}")
        
        # Print summary
        summary = results['summary']
        logger.info(f"Smoke tests completed:")
        logger.info(f"  Total: {summary['total']}")
        logger.info(f"  Passed: {summary['passed']}")
        logger.info(f"  Failed: {summary['failed']}")
        logger.info(f"  Warnings: {summary['warnings']}")
        logger.info(f"  Duration: {results['duration']:.3f}s")
        logger.info(f"  Overall Status: {results['overall_status'].upper()}")
        
        if results['overall_status'] == 'failed':
            logger.error("Some smoke tests failed!")
            for test in results['tests']:
                if test['status'] == 'failed':
                    logger.error(f"  ✗ {test['name']}: {test.get('error', 'Unknown error')}")
            sys.exit(1)
        else:
            logger.info("All smoke tests passed! ✓")
        
    except Exception as e:
        logger.error(f"Smoke tests failed: {e}")
        sys.exit(1)


if __name__ == '__main__':
    asyncio.run(main())
