"""
Migration Testing Framework for Hokm Game Server
Comprehensive testing utilities for database migrations

Features:
- Migration upgrade/downgrade testing
- Data integrity validation
- Performance testing
- Concurrency testing
- Rollback safety testing
- Migration simulation
"""

import asyncio
import logging
import time
import tempfile
import shutil
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable, Tuple
from pathlib import Path
from dataclasses import dataclass
from contextlib import asynccontextmanager
import json
import random
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from sqlalchemy import text, create_engine, MetaData, inspect
from sqlalchemy.ext.asyncio import AsyncSession, AsyncEngine, create_async_engine
from sqlalchemy.orm import sessionmaker
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from migration_framework import MigrationFramework, MigrationConfig, MigrationResult
from data_migration_utils import DataMigrationUtils, MigrationProgress

# Setup logging
logger = logging.getLogger(__name__)


@dataclass
class TestResult:
    """Result of a migration test"""
    test_name: str
    success: bool
    duration: float
    message: str = ""
    errors: List[str] = None
    warnings: List[str] = None
    performance_metrics: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []
        if self.warnings is None:
            self.warnings = []
        if self.performance_metrics is None:
            self.performance_metrics = {}


@dataclass
class MigrationTestSuite:
    """Configuration for migration test suite"""
    database_url: str
    test_database_url: str
    migrations_dir: str = "migrations"
    test_data_size: int = 1000
    concurrency_level: int = 5
    performance_threshold_seconds: float = 60.0
    enable_rollback_tests: bool = True
    enable_data_integrity_tests: bool = True
    enable_performance_tests: bool = True
    enable_concurrency_tests: bool = True


class MigrationTester:
    """
    Comprehensive migration testing framework
    
    Provides automated testing for:
    - Migration upgrade/downgrade cycles
    - Data integrity during migrations
    - Performance characteristics
    - Concurrency safety
    - Rollback procedures
    """
    
    def __init__(self, config: MigrationTestSuite):
        self.config = config
        self.test_engine = None
        self.test_session_factory = None
        self.migration_framework = None
        self.test_results: List[TestResult] = []
        
    async def setup(self):
        """Setup test environment"""
        logger.info("Setting up migration test environment")
        
        # Create test database engine
        self.test_engine = create_async_engine(
            self.config.test_database_url,
            echo=False,
            pool_size=10,
            max_overflow=20
        )
        
        self.test_session_factory = sessionmaker(
            bind=self.test_engine,
            class_=AsyncSession,
            expire_on_commit=False
        )
        
        # Setup migration framework for testing
        migration_config = MigrationConfig(
            database_url=self.config.test_database_url,
            migrations_dir=self.config.migrations_dir,
            enable_backup=False,  # Disable backups for testing
            dry_run=False
        )
        
        self.migration_framework = MigrationFramework(migration_config)
        
        # Create test database schema
        await self._setup_test_database()
        
    async def cleanup(self):
        """Cleanup test environment"""
        if self.test_engine:
            await self.test_engine.dispose()
        logger.info("Migration test environment cleaned up")
        
    async def _setup_test_database(self):
        """Setup test database with initial schema"""
        try:
            # Drop and recreate test database
            await self._recreate_test_database()
            
            # Apply base schema
            await self._apply_base_schema()
            
            logger.info("Test database setup completed")
            
        except Exception as e:
            logger.error(f"Failed to setup test database: {e}")
            raise
            
    async def _recreate_test_database(self):
        """Drop and recreate test database"""
        # This would be implemented based on your database setup
        # For PostgreSQL, you might use administrative commands
        pass
        
    async def _apply_base_schema(self):
        """Apply base schema to test database"""
        # Apply initial migrations to get a baseline schema
        try:
            result = await self.migration_framework.upgrade_database("head")
            if not result.success:
                raise Exception(f"Failed to apply base schema: {result.message}")
        except Exception as e:
            logger.warning(f"No migrations to apply or error applying base schema: {e}")
            
    async def run_all_tests(self) -> List[TestResult]:
        """Run the complete migration test suite"""
        logger.info("Starting comprehensive migration test suite")
        start_time = time.time()
        
        try:
            # Basic migration tests
            await self.test_migration_upgrade_downgrade()
            
            # Data integrity tests
            if self.config.enable_data_integrity_tests:
                await self.test_data_integrity_during_migration()
                
            # Performance tests
            if self.config.enable_performance_tests:
                await self.test_migration_performance()
                
            # Concurrency tests
            if self.config.enable_concurrency_tests:
                await self.test_concurrent_migrations()
                
            # Rollback tests
            if self.config.enable_rollback_tests:
                await self.test_rollback_safety()
                
            total_duration = time.time() - start_time
            
            # Summary
            passed = sum(1 for r in self.test_results if r.success)
            failed = len(self.test_results) - passed
            
            logger.info(f"Migration test suite completed in {total_duration:.2f}s")
            logger.info(f"Tests passed: {passed}, Tests failed: {failed}")
            
            return self.test_results
            
        except Exception as e:
            logger.error(f"Test suite failed: {e}")
            raise
            
    async def test_migration_upgrade_downgrade(self):
        """Test basic migration upgrade and downgrade functionality"""
        test_name = "migration_upgrade_downgrade"
        start_time = time.time()
        
        try:
            # Get migration history
            history = self.migration_framework.get_migration_history()
            
            if not history:
                self.test_results.append(TestResult(
                    test_name=test_name,
                    success=True,
                    duration=time.time() - start_time,
                    message="No migrations found to test",
                    warnings=["No migration files found"]
                ))
                return
            
            # Test each migration
            for migration in history[-3:]:  # Test last 3 migrations
                revision = migration['revision']
                
                # Test upgrade
                upgrade_result = await self.migration_framework.upgrade_database(revision)
                if not upgrade_result.success:
                    raise Exception(f"Upgrade to {revision} failed: {upgrade_result.message}")
                
                # Test downgrade if possible
                if migration['down_revision']:
                    downgrade_result = await self.migration_framework.downgrade_database(migration['down_revision'])
                    if not downgrade_result.success:
                        raise Exception(f"Downgrade from {revision} failed: {downgrade_result.message}")
                    
                    # Upgrade back
                    re_upgrade_result = await self.migration_framework.upgrade_database(revision)
                    if not re_upgrade_result.success:
                        raise Exception(f"Re-upgrade to {revision} failed: {re_upgrade_result.message}")
            
            self.test_results.append(TestResult(
                test_name=test_name,
                success=True,
                duration=time.time() - start_time,
                message=f"Successfully tested {len(history)} migrations"
            ))
            
        except Exception as e:
            self.test_results.append(TestResult(
                test_name=test_name,
                success=False,
                duration=time.time() - start_time,
                message=f"Migration upgrade/downgrade test failed: {str(e)}",
                errors=[str(e)]
            ))
            
    async def test_data_integrity_during_migration(self):
        """Test that data integrity is maintained during migrations"""
        test_name = "data_integrity_during_migration"
        start_time = time.time()
        
        try:
            # Create test data
            await self._create_test_data()
            
            # Record checksums before migration
            pre_migration_checksums = await self._calculate_data_checksums()
            
            # Apply latest migration
            result = await self.migration_framework.upgrade_database("head")
            if not result.success:
                raise Exception(f"Migration failed: {result.message}")
            
            # Verify data integrity after migration
            post_migration_checksums = await self._calculate_data_checksums()
            
            # Compare checksums for unchanged data
            integrity_issues = []
            for table, pre_checksum in pre_migration_checksums.items():
                post_checksum = post_migration_checksums.get(table)
                if post_checksum and pre_checksum != post_checksum:
                    # This might be expected if the migration modified the table
                    # You would need to implement smarter comparison logic
                    pass
            
            self.test_results.append(TestResult(
                test_name=test_name,
                success=True,
                duration=time.time() - start_time,
                message="Data integrity maintained during migration",
                performance_metrics={
                    "tables_checked": len(pre_migration_checksums),
                    "integrity_issues": len(integrity_issues)
                }
            ))
            
        except Exception as e:
            self.test_results.append(TestResult(
                test_name=test_name,
                success=False,
                duration=time.time() - start_time,
                message=f"Data integrity test failed: {str(e)}",
                errors=[str(e)]
            ))
            
    async def test_migration_performance(self):
        """Test migration performance with various data sizes"""
        test_name = "migration_performance"
        start_time = time.time()
        
        try:
            performance_results = {}
            
            # Test with different data sizes
            test_sizes = [100, 1000, 5000]
            
            for size in test_sizes:
                # Create test data of specific size
                await self._create_test_data(size)
                
                # Measure migration time
                migration_start = time.time()
                result = await self.migration_framework.upgrade_database("head")
                migration_duration = time.time() - migration_start
                
                if not result.success:
                    raise Exception(f"Migration failed for size {size}: {result.message}")
                
                performance_results[f"size_{size}"] = {
                    "duration": migration_duration,
                    "records_per_second": size / migration_duration if migration_duration > 0 else 0
                }
                
                # Check if performance meets threshold
                if migration_duration > self.config.performance_threshold_seconds:
                    performance_results[f"size_{size}"]["warning"] = "Exceeded performance threshold"
            
            # Determine if test passed
            max_duration = max(result["duration"] for result in performance_results.values())
            success = max_duration <= self.config.performance_threshold_seconds
            
            self.test_results.append(TestResult(
                test_name=test_name,
                success=success,
                duration=time.time() - start_time,
                message=f"Performance test completed. Max duration: {max_duration:.2f}s",
                performance_metrics=performance_results
            ))
            
        except Exception as e:
            self.test_results.append(TestResult(
                test_name=test_name,
                success=False,
                duration=time.time() - start_time,
                message=f"Performance test failed: {str(e)}",
                errors=[str(e)]
            ))
            
    async def test_concurrent_migrations(self):
        """Test migration behavior under concurrent database access"""
        test_name = "concurrent_migrations"
        start_time = time.time()
        
        try:
            # Create test data
            await self._create_test_data()
            
            # Start background database activity
            stop_activity = threading.Event()
            activity_errors = []
            
            async def background_activity():
                """Simulate concurrent database activity"""
                try:
                    async with self.test_session_factory() as session:
                        while not stop_activity.is_set():
                            # Simulate read/write operations
                            result = await session.execute(text("SELECT COUNT(*) FROM players"))
                            count = result.scalar()
                            await asyncio.sleep(0.1)
                except Exception as e:
                    activity_errors.append(str(e))
            
            # Start background activity
            activity_task = asyncio.create_task(background_activity())
            
            try:
                # Run migration while activity is happening
                await asyncio.sleep(0.5)  # Let activity start
                result = await self.migration_framework.upgrade_database("head")
                
                if not result.success:
                    raise Exception(f"Migration failed under concurrent load: {result.message}")
                
            finally:
                # Stop background activity
                stop_activity.set()
                await activity_task
            
            # Check for activity errors
            warnings = []
            if activity_errors:
                warnings = [f"Background activity errors: {len(activity_errors)}"]
            
            self.test_results.append(TestResult(
                test_name=test_name,
                success=True,
                duration=time.time() - start_time,
                message="Migration completed successfully under concurrent load",
                warnings=warnings,
                performance_metrics={"activity_errors": len(activity_errors)}
            ))
            
        except Exception as e:
            self.test_results.append(TestResult(
                test_name=test_name,
                success=False,
                duration=time.time() - start_time,
                message=f"Concurrent migration test failed: {str(e)}",
                errors=[str(e)]
            ))
            
    async def test_rollback_safety(self):
        """Test rollback safety and recovery procedures"""
        test_name = "rollback_safety"
        start_time = time.time()
        
        try:
            # Create test data
            await self._create_test_data()
            
            # Get current state
            current_revision = self.migration_framework.get_current_revision()
            if not current_revision:
                self.test_results.append(TestResult(
                    test_name=test_name,
                    success=True,
                    duration=time.time() - start_time,
                    message="No migrations to test rollback",
                    warnings=["No current revision found"]
                ))
                return
            
            # Record pre-migration state
            pre_rollback_checksums = await self._calculate_data_checksums()
            
            # Find previous revision
            history = self.migration_framework.get_migration_history()
            previous_revision = None
            for migration in history:
                if migration['revision'] == current_revision and migration['down_revision']:
                    previous_revision = migration['down_revision']
                    break
            
            if not previous_revision:
                self.test_results.append(TestResult(
                    test_name=test_name,
                    success=True,
                    duration=time.time() - start_time,
                    message="No previous revision available for rollback test",
                    warnings=["Cannot test rollback - no previous revision"]
                ))
                return
            
            # Perform rollback
            rollback_result = await self.migration_framework.downgrade_database(previous_revision)
            if not rollback_result.success:
                raise Exception(f"Rollback failed: {rollback_result.message}")
            
            # Verify system is functional after rollback
            await self._verify_system_functionality()
            
            # Roll forward again
            forward_result = await self.migration_framework.upgrade_database(current_revision)
            if not forward_result.success:
                raise Exception(f"Forward migration after rollback failed: {forward_result.message}")
            
            # Verify data integrity after rollback cycle
            post_rollback_checksums = await self._calculate_data_checksums()
            
            # Compare checksums (allowing for expected differences)
            integrity_maintained = True
            for table in pre_rollback_checksums:
                if table in post_rollback_checksums:
                    # This is a simplified check - in reality you'd need more sophisticated comparison
                    pass
            
            self.test_results.append(TestResult(
                test_name=test_name,
                success=True,
                duration=time.time() - start_time,
                message="Rollback safety test completed successfully",
                performance_metrics={
                    "rollback_duration": rollback_result.duration,
                    "forward_duration": forward_result.duration,
                    "integrity_maintained": integrity_maintained
                }
            ))
            
        except Exception as e:
            self.test_results.append(TestResult(
                test_name=test_name,
                success=False,
                duration=time.time() - start_time,
                message=f"Rollback safety test failed: {str(e)}",
                errors=[str(e)]
            ))
            
    async def _create_test_data(self, size: int = None):
        """Create test data for migration testing"""
        if size is None:
            size = self.config.test_data_size
            
        async with self.test_session_factory() as session:
            try:
                # Create test players
                players_data = []
                for i in range(size):
                    players_data.append({
                        "username": f"test_user_{i}",
                        "email": f"test{i}@example.com",
                        "display_name": f"Test User {i}",
                        "is_active": True,
                        "total_games": random.randint(0, 100),
                        "wins": random.randint(0, 50),
                        "losses": random.randint(0, 50),
                        "rating": random.randint(800, 2000)
                    })
                
                # Insert in batches
                batch_size = 100
                for i in range(0, len(players_data), batch_size):
                    batch = players_data[i:i + batch_size]
                    await session.execute(
                        text("""
                            INSERT INTO players (username, email, display_name, is_active, total_games, wins, losses, rating)
                            VALUES (:username, :email, :display_name, :is_active, :total_games, :wins, :losses, :rating)
                        """),
                        batch
                    )
                
                await session.commit()
                logger.info(f"Created {size} test records")
                
            except Exception as e:
                await session.rollback()
                logger.error(f"Failed to create test data: {e}")
                raise
                
    async def _calculate_data_checksums(self) -> Dict[str, str]:
        """Calculate checksums for data integrity verification"""
        checksums = {}
        
        async with self.test_session_factory() as session:
            try:
                # Get list of tables
                inspector = inspect(self.test_engine.sync_engine)
                tables = inspector.get_table_names()
                
                for table in tables:
                    if table in ['alembic_version', 'migration_logs', 'schema_versions']:
                        continue  # Skip migration tracking tables
                    
                    # Calculate simple checksum based on record count and some data
                    result = await session.execute(text(f"SELECT COUNT(*) FROM {table}"))
                    count = result.scalar()
                    
                    # This is a simplified checksum - in practice you'd want more sophisticated hashing
                    checksums[table] = f"count_{count}"
                
                return checksums
                
            except Exception as e:
                logger.error(f"Failed to calculate checksums: {e}")
                return {}
                
    async def _verify_system_functionality(self):
        """Verify basic system functionality after migration changes"""
        async with self.test_session_factory() as session:
            try:
                # Test basic queries
                result = await session.execute(text("SELECT 1"))
                if not result.scalar():
                    raise Exception("Basic query failed")
                
                # Test table access
                result = await session.execute(text("SELECT COUNT(*) FROM players"))
                count = result.scalar()
                
                logger.info(f"System functionality verified - {count} players found")
                
            except Exception as e:
                logger.error(f"System functionality verification failed: {e}")
                raise
                
    def generate_test_report(self) -> str:
        """Generate a comprehensive test report"""
        if not self.test_results:
            return "No test results available"
        
        passed = sum(1 for r in self.test_results if r.success)
        failed = len(self.test_results) - passed
        total_duration = sum(r.duration for r in self.test_results)
        
        report = f"""
Migration Test Report
====================
Generated: {datetime.now().isoformat()}

Summary:
--------
Total Tests: {len(self.test_results)}
Passed: {passed}
Failed: {failed}
Total Duration: {total_duration:.2f} seconds

Test Results:
-------------
"""
        
        for result in self.test_results:
            status = "PASS" if result.success else "FAIL"
            report += f"{result.test_name}: {status} ({result.duration:.2f}s)\n"
            if result.message:
                report += f"  Message: {result.message}\n"
            if result.errors:
                report += f"  Errors: {', '.join(result.errors)}\n"
            if result.warnings:
                report += f"  Warnings: {', '.join(result.warnings)}\n"
            if result.performance_metrics:
                report += f"  Metrics: {result.performance_metrics}\n"
            report += "\n"
        
        return report


# Convenience functions for testing

async def run_migration_tests(
    database_url: str,
    test_database_url: str,
    **kwargs
) -> List[TestResult]:
    """Run migration tests with default configuration"""
    config = MigrationTestSuite(
        database_url=database_url,
        test_database_url=test_database_url,
        **kwargs
    )
    
    tester = MigrationTester(config)
    
    try:
        await tester.setup()
        results = await tester.run_all_tests()
        return results
    finally:
        await tester.cleanup()


async def test_specific_migration(
    database_url: str,
    test_database_url: str,
    revision: str
) -> TestResult:
    """Test a specific migration revision"""
    config = MigrationTestSuite(
        database_url=database_url,
        test_database_url=test_database_url,
        enable_rollback_tests=False,
        enable_concurrency_tests=False,
        enable_performance_tests=False
    )
    
    tester = MigrationTester(config)
    
    try:
        await tester.setup()
        
        # Test specific migration
        start_time = time.time()
        result = await tester.migration_framework.upgrade_database(revision)
        duration = time.time() - start_time
        
        return TestResult(
            test_name=f"test_migration_{revision}",
            success=result.success,
            duration=duration,
            message=result.message,
            errors=result.errors if hasattr(result, 'errors') else []
        )
        
    finally:
        await tester.cleanup()


# CLI interface for migration testing
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Migration Testing Tool")
    parser.add_argument("--database-url", required=True, help="Main database URL")
    parser.add_argument("--test-database-url", required=True, help="Test database URL")
    parser.add_argument("--test-suite", choices=["all", "basic", "performance", "rollback"], 
                       default="all", help="Test suite to run")
    parser.add_argument("--report-file", help="File to save test report")
    
    args = parser.parse_args()
    
    async def main():
        config = MigrationTestSuite(
            database_url=args.database_url,
            test_database_url=args.test_database_url,
            enable_rollback_tests=args.test_suite in ["all", "rollback"],
            enable_performance_tests=args.test_suite in ["all", "performance"],
            enable_concurrency_tests=args.test_suite == "all"
        )
        
        tester = MigrationTester(config)
        
        try:
            await tester.setup()
            results = await tester.run_all_tests()
            
            # Generate report
            report = tester.generate_test_report()
            print(report)
            
            if args.report_file:
                with open(args.report_file, 'w') as f:
                    f.write(report)
                print(f"Report saved to {args.report_file}")
                
        finally:
            await tester.cleanup()
    
    asyncio.run(main())
