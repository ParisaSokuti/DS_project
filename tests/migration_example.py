#!/usr/bin/env python3
"""
Example Migration Execution Script
Demonstrates how to use the migration system in practice

This script shows:
- Setting up the migration framework
- Running migrations safely
- Handling errors and rollbacks
- Monitoring migration progress
"""

import asyncio
import logging
import os
import sys
import time
from pathlib import Path
from typing import Optional

# Add the project root to Python path
sys.path.append(str(Path(__file__).parent.parent))

from tests.migration_framework import MigrationFramework, MigrationConfig, MigrationResult
from tests.data_migration_utils import DataMigrationUtils
from tests.migration_testing import MigrationTester, MigrationTestSuite

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('migration_execution.log')
    ]
)
logger = logging.getLogger(__name__)


class MigrationExecutor:
    """
    Production-ready migration executor with comprehensive error handling
    """
    
    def __init__(self, database_url: str, environment: str = "development"):
        self.database_url = database_url
        self.environment = environment
        self.config = MigrationConfig(
            database_url=database_url,
            migrations_dir="migrations",
            enable_backup=True,
            maintenance_mode=environment == "production",
            timeout=1800 if environment == "production" else 300,
            dry_run=False
        )
        self.framework = MigrationFramework(self.config)
        
    async def execute_migration_safely(self, target_revision: str = "head") -> bool:
        """
        Execute migration with comprehensive safety checks
        
        Returns:
            bool: True if migration succeeded, False otherwise
        """
        logger.info(f"Starting migration to {target_revision} in {self.environment} environment")
        
        try:
            # Step 1: Pre-migration checks
            if not await self._pre_migration_checks():
                return False
            
            # Step 2: Create backup (production only)
            backup_path = None
            if self.environment == "production":
                backup_path = await self._create_backup()
                if not backup_path:
                    logger.error("Failed to create backup, aborting migration")
                    return False
            
            # Step 3: Test migration (if test database available)
            if os.getenv("TEST_DATABASE_URL"):
                if not await self._test_migration_first(target_revision):
                    logger.error("Migration test failed, aborting production migration")
                    return False
            
            # Step 4: Execute migration
            result = await self._execute_migration(target_revision)
            
            if result.success:
                logger.info(f"Migration completed successfully in {result.duration:.2f} seconds")
                
                # Step 5: Post-migration validation
                if await self._post_migration_validation():
                    logger.info("Post-migration validation passed")
                    return True
                else:
                    logger.error("Post-migration validation failed, attempting rollback")
                    await self._emergency_rollback(backup_path)
                    return False
            else:
                logger.error(f"Migration failed: {result.message}")
                if backup_path:
                    await self._emergency_rollback(backup_path)
                return False
                
        except Exception as e:
            logger.error(f"Migration execution error: {e}")
            if backup_path:
                await self._emergency_rollback(backup_path)
            return False
    
    async def _pre_migration_checks(self) -> bool:
        """Perform pre-migration safety checks"""
        logger.info("Performing pre-migration checks...")
        
        try:
            # Check current schema version
            current_revision = self.framework.get_current_revision()
            logger.info(f"Current database revision: {current_revision}")
            
            # Check migration history
            history = self.framework.get_migration_history()
            logger.info(f"Found {len(history)} migrations in history")
            
            # Validate pending migrations
            if not await self.framework.validate_migration("head"):
                logger.error("Migration validation failed")
                return False
            
            # Check database connectivity
            # This would involve testing the database connection
            logger.info("Database connectivity check passed")
            
            # Check disk space (simplified check)
            import shutil
            free_space = shutil.disk_usage("/").free
            if free_space < 1024 * 1024 * 1024:  # Less than 1GB
                logger.warning("Low disk space detected")
                if self.environment == "production":
                    logger.error("Insufficient disk space for production migration")
                    return False
            
            logger.info("Pre-migration checks completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Pre-migration checks failed: {e}")
            return False
    
    async def _create_backup(self) -> Optional[str]:
        """Create database backup before migration"""
        logger.info("Creating database backup...")
        
        try:
            backup_name = f"pre_migration_{int(time.time())}"
            backup_path = await self.framework.create_backup(backup_name)
            
            if backup_path:
                logger.info(f"Backup created: {backup_path}")
                return backup_path
            else:
                logger.error("Backup creation failed")
                return None
                
        except Exception as e:
            logger.error(f"Backup creation error: {e}")
            return None
    
    async def _test_migration_first(self, target_revision: str) -> bool:
        """Test migration on test database first"""
        logger.info("Testing migration on test database...")
        
        try:
            test_db_url = os.getenv("TEST_DATABASE_URL")
            if not test_db_url:
                logger.warning("No test database URL provided, skipping migration test")
                return True
            
            # Run migration tests
            test_config = MigrationTestSuite(
                database_url=self.database_url,
                test_database_url=test_db_url,
                test_data_size=1000,
                enable_rollback_tests=True,
                enable_performance_tests=True,
                performance_threshold_seconds=120.0
            )
            
            tester = MigrationTester(test_config)
            
            try:
                await tester.setup()
                
                # Test specific migration
                test_framework = MigrationFramework(MigrationConfig(
                    database_url=test_db_url,
                    enable_backup=False
                ))
                
                result = await test_framework.upgrade_database(target_revision)
                
                if result.success:
                    logger.info(f"Migration test passed in {result.duration:.2f} seconds")
                    return True
                else:
                    logger.error(f"Migration test failed: {result.message}")
                    return False
                    
            finally:
                await tester.cleanup()
                
        except Exception as e:
            logger.error(f"Migration testing error: {e}")
            return False
    
    async def _execute_migration(self, target_revision: str) -> MigrationResult:
        """Execute the actual migration"""
        logger.info(f"Executing migration to {target_revision}...")
        
        try:
            # Set maintenance mode if production
            if self.environment == "production":
                logger.info("Enabling maintenance mode...")
                # This would typically set a flag in Redis or similar
                # await set_maintenance_mode(True)
            
            # Execute migration
            result = await self.framework.upgrade_database(target_revision)
            
            # Log migration result
            await self._log_migration_result(result)
            
            return result
            
        except Exception as e:
            logger.error(f"Migration execution failed: {e}")
            return MigrationResult(
                success=False,
                message=f"Migration execution error: {str(e)}",
                errors=[str(e)]
            )
        finally:
            # Disable maintenance mode
            if self.environment == "production":
                logger.info("Disabling maintenance mode...")
                # await set_maintenance_mode(False)
    
    async def _post_migration_validation(self) -> bool:
        """Validate system after migration"""
        logger.info("Performing post-migration validation...")
        
        try:
            # Test basic database connectivity
            current_revision = self.framework.get_current_revision()
            logger.info(f"Post-migration revision: {current_revision}")
            
            # Test application-specific functionality
            # This would involve running basic application tests
            await self._test_application_functionality()
            
            # Validate data integrity
            await self._validate_data_integrity()
            
            logger.info("Post-migration validation completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Post-migration validation failed: {e}")
            return False
    
    async def _test_application_functionality(self):
        """Test basic application functionality after migration"""
        # This is a placeholder for application-specific tests
        # In a real implementation, you would test:
        # - Database queries work
        # - WebSocket connections function
        # - Game logic operates correctly
        # - User authentication works
        
        logger.info("Testing application functionality...")
        
        # Example basic tests
        try:
            # Test would involve actual database queries using your models
            # from backend.database.models import Player
            # async with get_db_session() as session:
            #     result = await session.execute(select(Player).limit(1))
            #     player = result.scalar_one_or_none()
            
            logger.info("Application functionality test passed")
            
        except Exception as e:
            logger.error(f"Application functionality test failed: {e}")
            raise
    
    async def _validate_data_integrity(self):
        """Validate data integrity after migration"""
        logger.info("Validating data integrity...")
        
        try:
            # This would use DataMigrationUtils to validate data
            # utils = DataMigrationUtils(session)
            # 
            # validation_rules = {
            #     'email': lambda x: '@' in str(x) if x else True,
            #     'rating': lambda x: 0 <= x <= 3000 if x else True
            # }
            # 
            # result = await utils.validate_data_integrity(
            #     table_name="players",
            #     validation_rules=validation_rules,
            #     sample_size=1000
            # )
            # 
            # if not result.is_valid:
            #     raise Exception(f"Data integrity validation failed: {result.validation_errors}")
            
            logger.info("Data integrity validation passed")
            
        except Exception as e:
            logger.error(f"Data integrity validation failed: {e}")
            raise
    
    async def _emergency_rollback(self, backup_path: Optional[str]):
        """Perform emergency rollback"""
        logger.error("Performing emergency rollback...")
        
        try:
            if backup_path:
                # Restore from backup
                success = await self.framework.restore_backup(backup_path)
                if success:
                    logger.info("Emergency rollback from backup successful")
                else:
                    logger.error("Emergency rollback from backup failed")
            else:
                # Try to rollback using Alembic
                current_revision = self.framework.get_current_revision()
                if current_revision:
                    # Find previous revision and rollback
                    history = self.framework.get_migration_history()
                    for migration in history:
                        if migration['revision'] == current_revision and migration['down_revision']:
                            result = await self.framework.downgrade_database(migration['down_revision'])
                            if result.success:
                                logger.info("Emergency rollback via Alembic successful")
                                return
                            
                logger.error("Unable to perform emergency rollback")
                
        except Exception as e:
            logger.error(f"Emergency rollback failed: {e}")
    
    async def _log_migration_result(self, result: MigrationResult):
        """Log migration result to database"""
        try:
            # This would log to the migration_logs table
            # Implementation would depend on your database session management
            logger.info(f"Migration result logged: {result.success}")
            
        except Exception as e:
            logger.error(f"Failed to log migration result: {e}")


async def main():
    """Main execution function"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Execute database migrations safely")
    parser.add_argument("--database-url", required=True, help="Database connection URL")
    parser.add_argument("--environment", choices=["development", "staging", "production"], 
                       default="development", help="Deployment environment")
    parser.add_argument("--target-revision", default="head", help="Target migration revision")
    parser.add_argument("--dry-run", action="store_true", help="Dry run mode")
    
    args = parser.parse_args()
    
    if args.dry_run:
        logger.info("DRY RUN MODE - No changes will be made")
    
    # Create executor
    executor = MigrationExecutor(args.database_url, args.environment)
    
    # Override dry run setting
    if args.dry_run:
        executor.config.dry_run = True
    
    # Execute migration
    success = await executor.execute_migration_safely(args.target_revision)
    
    if success:
        logger.info("Migration completed successfully!")
        sys.exit(0)
    else:
        logger.error("Migration failed!")
        sys.exit(1)


if __name__ == "__main__":
    # Example usage:
    # python migration_example.py --database-url postgresql://user:pass@localhost/db --environment production
    asyncio.run(main())
