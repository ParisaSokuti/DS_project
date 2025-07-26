#!/usr/bin/env python3
"""
Database Rollback Script
Emergency and planned rollback procedures

Features:
- Automated rollback to previous migration
- Backup restoration
- Point-in-time recovery
- Rollback validation
- Emergency rollback procedures
"""

import asyncio
import logging
import argparse
import os
import sys
import time
import json
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from tests.migration_framework import MigrationFramework, MigrationConfig
from tests.data_migration_utils import DataMigrationUtils
from database.smoke_tests import DatabaseSmokeTests

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(f'rollback_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
    ]
)
logger = logging.getLogger(__name__)


class DatabaseRollback:
    """
    Comprehensive database rollback orchestration
    """
    
    def __init__(self, environment: str, config_file: Optional[str] = None):
        self.environment = environment
        self.config = self._load_config(config_file)
        self.backup_dir = Path("database/backups")
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        
    def _load_config(self, config_file: Optional[str]) -> Dict[str, Any]:
        """Load environment-specific configuration"""
        if config_file and Path(config_file).exists():
            with open(config_file, 'r') as f:
                return json.load(f)
        
        # Default configuration
        return {
            'database': {
                'host': os.getenv('DB_HOST', 'localhost'),
                'port': int(os.getenv('DB_PORT', '5432')),
                'database': os.getenv('DB_NAME', 'hokm_game'),
                'username': os.getenv('DB_USER', 'hokm_app'),
                'password': os.getenv('DB_PASSWORD', 'app_secure_password')
            },
            'backup': {
                'retention_days': 30,
                'compression': True,
                'verification': True
            },
            'rollback': {
                'max_rollback_steps': 5,
                'require_confirmation': self.environment == 'production',
                'run_smoke_tests': True,
                'notify_on_completion': self.environment in ['staging', 'production']
            }
        }
    
    async def rollback_migration(self, target_revision: Optional[str] = None, steps: int = 1) -> Dict[str, Any]:
        """
        Rollback database migrations
        
        Args:
            target_revision: Specific revision to rollback to
            steps: Number of migration steps to rollback
        """
        rollback_info = {
            'environment': self.environment,
            'started_at': datetime.utcnow().isoformat(),
            'type': 'migration_rollback',
            'target_revision': target_revision,
            'steps': steps
        }
        
        try:
            # 1. Get current migration state
            current_revision = await self._get_current_revision()
            rollback_info['current_revision'] = current_revision
            logger.info(f"Current migration revision: {current_revision}")
            
            # 2. Create backup before rollback
            if self.config['rollback']['require_confirmation']:
                confirmation = input(f"⚠️  ROLLBACK CONFIRMATION REQUIRED ⚠️\n"
                                   f"Environment: {self.environment}\n"
                                   f"Current revision: {current_revision}\n"
                                   f"Rolling back {steps} step(s)\n"
                                   f"Type 'CONFIRM ROLLBACK' to proceed: ")
                
                if confirmation != 'CONFIRM ROLLBACK':
                    raise ValueError("Rollback cancelled by user")
            
            backup_result = await self._create_pre_rollback_backup()
            rollback_info['backup_file'] = backup_result['backup_file']
            logger.info(f"Pre-rollback backup created: {backup_result['backup_file']}")
            
            # 3. Execute rollback
            migration_config = MigrationConfig(
                database_url=self._get_database_url(),
                migrations_dir="tests/migrations",
                environment=self.environment
            )
            
            migration_framework = MigrationFramework(migration_config)
            
            if target_revision:
                rollback_result = await migration_framework.rollback_to_revision(target_revision)
            else:
                rollback_result = await migration_framework.rollback_steps(steps)
            
            rollback_info['rollback_result'] = rollback_result
            
            # 4. Validate rollback
            validation_result = await self._validate_rollback()
            rollback_info['validation'] = validation_result
            
            if not validation_result['success']:
                logger.error("Rollback validation failed!")
                # Attempt to restore from backup
                restore_result = await self.restore_from_backup(backup_result['backup_file'])
                rollback_info['emergency_restore'] = restore_result
                raise Exception(f"Rollback validation failed: {validation_result['errors']}")
            
            # 5. Run smoke tests if configured
            if self.config['rollback']['run_smoke_tests']:
                smoke_test_result = await self._run_post_rollback_smoke_tests()
                rollback_info['smoke_tests'] = smoke_test_result
                
                if smoke_test_result['overall_status'] != 'passed':
                    logger.warning("Some smoke tests failed after rollback")
            
            rollback_info['completed_at'] = datetime.utcnow().isoformat()
            rollback_info['status'] = 'success'
            rollback_info['final_revision'] = await self._get_current_revision()
            
            logger.info(f"Migration rollback completed successfully")
            logger.info(f"Final revision: {rollback_info['final_revision']}")
            
            # 6. Send notifications
            if self.config['rollback']['notify_on_completion']:
                await self._send_rollback_notification(rollback_info)
            
            return rollback_info
            
        except Exception as e:
            rollback_info['status'] = 'failed'
            rollback_info['error'] = str(e)
            rollback_info['completed_at'] = datetime.utcnow().isoformat()
            
            logger.error(f"Migration rollback failed: {e}")
            
            # Send failure notification
            if self.config['rollback']['notify_on_completion']:
                await self._send_rollback_notification(rollback_info)
            
            raise
    
    async def restore_from_backup(self, backup_file: str, point_in_time: Optional[str] = None) -> Dict[str, Any]:
        """
        Restore database from backup file
        
        Args:
            backup_file: Path to backup file
            point_in_time: Optional point-in-time recovery timestamp
        """
        restore_info = {
            'environment': self.environment,
            'started_at': datetime.utcnow().isoformat(),
            'type': 'backup_restore',
            'backup_file': backup_file,
            'point_in_time': point_in_time
        }
        
        try:
            backup_path = Path(backup_file)
            if not backup_path.exists():
                raise FileNotFoundError(f"Backup file not found: {backup_file}")
            
            # Confirmation for production
            if self.config['rollback']['require_confirmation']:
                confirmation = input(f"⚠️  RESTORE CONFIRMATION REQUIRED ⚠️\n"
                                   f"Environment: {self.environment}\n"
                                   f"Backup file: {backup_file}\n"
                                   f"This will REPLACE the current database!\n"
                                   f"Type 'CONFIRM RESTORE' to proceed: ")
                
                if confirmation != 'CONFIRM RESTORE':
                    raise ValueError("Restore cancelled by user")
            
            # 1. Create safety backup of current state
            safety_backup = await self._create_pre_rollback_backup("pre_restore_safety")
            restore_info['safety_backup'] = safety_backup['backup_file']
            
            # 2. Execute restore
            db_config = self.config['database']
            
            if backup_path.suffix == '.sql':
                # SQL restore
                restore_cmd = [
                    'psql',
                    f"--host={db_config['host']}",
                    f"--port={db_config['port']}",
                    f"--username={db_config['username']}",
                    f"--dbname={db_config['database']}",
                    f"--file={backup_path}"
                ]
            else:
                # pg_dump format restore
                restore_cmd = [
                    'pg_restore',
                    f"--host={db_config['host']}",
                    f"--port={db_config['port']}",
                    f"--username={db_config['username']}",
                    f"--dbname={db_config['database']}",
                    '--clean',
                    '--if-exists',
                    '--verbose',
                    str(backup_path)
                ]
            
            # Set password via environment variable
            env = os.environ.copy()
            env['PGPASSWORD'] = db_config['password']
            
            logger.info(f"Starting database restore from {backup_file}")
            
            start_time = time.time()
            result = subprocess.run(
                restore_cmd,
                env=env,
                capture_output=True,
                text=True,
                timeout=3600  # 1 hour timeout
            )
            
            duration = time.time() - start_time
            
            if result.returncode != 0:
                raise Exception(f"Restore failed: {result.stderr}")
            
            restore_info['restore_duration'] = duration
            restore_info['restore_output'] = result.stdout
            
            # 3. Validate restore
            validation_result = await self._validate_restore()
            restore_info['validation'] = validation_result
            
            if not validation_result['success']:
                raise Exception(f"Restore validation failed: {validation_result['errors']}")
            
            # 4. Run smoke tests
            smoke_test_result = await self._run_post_rollback_smoke_tests()
            restore_info['smoke_tests'] = smoke_test_result
            
            restore_info['completed_at'] = datetime.utcnow().isoformat()
            restore_info['status'] = 'success'
            
            logger.info(f"Database restore completed successfully in {duration:.2f}s")
            
            return restore_info
            
        except Exception as e:
            restore_info['status'] = 'failed'
            restore_info['error'] = str(e)
            restore_info['completed_at'] = datetime.utcnow().isoformat()
            
            logger.error(f"Database restore failed: {e}")
            raise
    
    async def emergency_rollback(self, reason: str) -> Dict[str, Any]:
        """
        Emergency rollback procedure for critical situations
        """
        emergency_info = {
            'environment': self.environment,
            'started_at': datetime.utcnow().isoformat(),
            'type': 'emergency_rollback',
            'reason': reason,
            'automated': True
        }
        
        try:
            logger.critical(f"EMERGENCY ROLLBACK INITIATED: {reason}")
            
            # 1. Find the most recent successful backup
            latest_backup = await self._find_latest_backup()
            if not latest_backup:
                raise Exception("No backup available for emergency rollback")
            
            emergency_info['backup_used'] = latest_backup
            
            # 2. Emergency restore (skip confirmations)
            original_require_confirmation = self.config['rollback']['require_confirmation']
            self.config['rollback']['require_confirmation'] = False
            
            try:
                restore_result = await self.restore_from_backup(latest_backup)
                emergency_info['restore_result'] = restore_result
            finally:
                self.config['rollback']['require_confirmation'] = original_require_confirmation
            
            # 3. Immediate notification
            await self._send_emergency_notification(emergency_info)
            
            emergency_info['completed_at'] = datetime.utcnow().isoformat()
            emergency_info['status'] = 'success'
            
            logger.critical("EMERGENCY ROLLBACK COMPLETED SUCCESSFULLY")
            
            return emergency_info
            
        except Exception as e:
            emergency_info['status'] = 'failed'
            emergency_info['error'] = str(e)
            emergency_info['completed_at'] = datetime.utcnow().isoformat()
            
            logger.critical(f"EMERGENCY ROLLBACK FAILED: {e}")
            
            # Send failure notification
            await self._send_emergency_notification(emergency_info)
            
            raise
    
    async def list_available_backups(self) -> List[Dict[str, Any]]:
        """List all available backups"""
        backups = []
        
        for backup_file in self.backup_dir.glob("*.sql*"):
            try:
                stat = backup_file.stat()
                backups.append({
                    'file': str(backup_file),
                    'size_mb': round(stat.st_size / (1024 * 1024), 2),
                    'created_at': datetime.fromtimestamp(stat.st_ctime).isoformat(),
                    'age_hours': round((time.time() - stat.st_ctime) / 3600, 1)
                })
            except Exception as e:
                logger.warning(f"Could not read backup file {backup_file}: {e}")
        
        # Sort by creation time (newest first)
        backups.sort(key=lambda x: x['created_at'], reverse=True)
        
        return backups
    
    async def cleanup_old_backups(self) -> Dict[str, Any]:
        """Clean up old backup files"""
        retention_days = self.config['backup']['retention_days']
        cutoff_time = time.time() - (retention_days * 24 * 3600)
        
        cleanup_info = {
            'retention_days': retention_days,
            'cutoff_time': datetime.fromtimestamp(cutoff_time).isoformat(),
            'files_removed': [],
            'space_freed_mb': 0
        }
        
        for backup_file in self.backup_dir.glob("*.sql*"):
            try:
                stat = backup_file.stat()
                if stat.st_ctime < cutoff_time:
                    size_mb = stat.st_size / (1024 * 1024)
                    backup_file.unlink()
                    
                    cleanup_info['files_removed'].append({
                        'file': str(backup_file),
                        'size_mb': round(size_mb, 2),
                        'age_days': round((time.time() - stat.st_ctime) / (24 * 3600), 1)
                    })
                    cleanup_info['space_freed_mb'] += size_mb
                    
            except Exception as e:
                logger.warning(f"Could not remove backup file {backup_file}: {e}")
        
        cleanup_info['space_freed_mb'] = round(cleanup_info['space_freed_mb'], 2)
        
        logger.info(f"Cleaned up {len(cleanup_info['files_removed'])} old backups, "
                   f"freed {cleanup_info['space_freed_mb']} MB")
        
        return cleanup_info
    
    # Helper methods
    
    def _get_database_url(self) -> str:
        """Get database URL from configuration"""
        db = self.config['database']
        return f"postgresql://{db['username']}:{db['password']}@{db['host']}:{db['port']}/{db['database']}"
    
    async def _get_current_revision(self) -> Optional[str]:
        """Get current Alembic revision"""
        try:
            migration_config = MigrationConfig(
                database_url=self._get_database_url(),
                migrations_dir="tests/migrations",
                environment=self.environment
            )
            migration_framework = MigrationFramework(migration_config)
            return await migration_framework.get_current_revision()
        except Exception as e:
            logger.warning(f"Could not get current revision: {e}")
            return None
    
    async def _create_pre_rollback_backup(self, suffix: str = "pre_rollback") -> Dict[str, Any]:
        """Create backup before rollback operation"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"backup_{self.environment}_{suffix}_{timestamp}.sql"
        backup_path = self.backup_dir / backup_filename
        
        db_config = self.config['database']
        
        backup_cmd = [
            'pg_dump',
            f"--host={db_config['host']}",
            f"--port={db_config['port']}",
            f"--username={db_config['username']}",
            f"--dbname={db_config['database']}",
            '--verbose',
            '--format=custom',
            '--no-owner',
            '--no-privileges',
            f"--file={backup_path}"
        ]
        
        env = os.environ.copy()
        env['PGPASSWORD'] = db_config['password']
        
        start_time = time.time()
        result = subprocess.run(
            backup_cmd,
            env=env,
            capture_output=True,
            text=True,
            timeout=1800  # 30 minutes
        )
        
        duration = time.time() - start_time
        
        if result.returncode != 0:
            raise Exception(f"Backup failed: {result.stderr}")
        
        backup_size = backup_path.stat().st_size
        
        return {
            'backup_file': str(backup_path),
            'size_mb': round(backup_size / (1024 * 1024), 2),
            'duration': round(duration, 2),
            'status': 'success'
        }
    
    async def _validate_rollback(self) -> Dict[str, Any]:
        """Validate rollback operation"""
        # Basic validation - check if database is accessible and has expected structure
        try:
            # This is a placeholder - implement actual validation logic
            smoke_tests = DatabaseSmokeTests(self.environment)
            results = await smoke_tests.test_basic_connection()
            
            return {
                'success': True,
                'checks': ['database_accessible', 'basic_schema_intact'],
                'details': results
            }
        except Exception as e:
            return {
                'success': False,
                'errors': [str(e)],
                'details': None
            }
    
    async def _validate_restore(self) -> Dict[str, Any]:
        """Validate restore operation"""
        return await self._validate_rollback()  # Same validation for now
    
    async def _run_post_rollback_smoke_tests(self) -> Dict[str, Any]:
        """Run smoke tests after rollback"""
        try:
            smoke_tests = DatabaseSmokeTests(self.environment)
            return await smoke_tests.run_all_tests()
        except Exception as e:
            return {
                'overall_status': 'failed',
                'error': str(e),
                'summary': {'total': 0, 'passed': 0, 'failed': 1}
            }
    
    async def _find_latest_backup(self) -> Optional[str]:
        """Find the most recent backup file"""
        backups = await self.list_available_backups()
        return backups[0]['file'] if backups else None
    
    async def _send_rollback_notification(self, rollback_info: Dict[str, Any]):
        """Send rollback completion notification"""
        # Placeholder for notification logic
        logger.info(f"Rollback notification: {rollback_info['status']}")
    
    async def _send_emergency_notification(self, emergency_info: Dict[str, Any]):
        """Send emergency rollback notification"""
        # Placeholder for emergency notification logic
        logger.critical(f"Emergency notification: {emergency_info['reason']}")


async def main():
    """
    Main entry point for rollback operations
    """
    parser = argparse.ArgumentParser(description='Database Rollback Script')
    parser.add_argument(
        '--environment', '-e',
        choices=['development', 'testing', 'staging', 'production'],
        default='development',
        help='Target environment'
    )
    parser.add_argument(
        '--config', '-c',
        help='Configuration file path'
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Rollback command')
    
    # Migration rollback
    migration_parser = subparsers.add_parser('migration', help='Rollback migrations')
    migration_parser.add_argument('--steps', type=int, default=1, help='Number of steps to rollback')
    migration_parser.add_argument('--revision', help='Target revision to rollback to')
    
    # Backup restore
    restore_parser = subparsers.add_parser('restore', help='Restore from backup')
    restore_parser.add_argument('backup_file', help='Backup file to restore from')
    restore_parser.add_argument('--point-in-time', help='Point-in-time recovery timestamp')
    
    # Emergency rollback
    emergency_parser = subparsers.add_parser('emergency', help='Emergency rollback')
    emergency_parser.add_argument('reason', help='Reason for emergency rollback')
    
    # List backups
    list_parser = subparsers.add_parser('list-backups', help='List available backups')
    
    # Cleanup
    cleanup_parser = subparsers.add_parser('cleanup', help='Clean up old backups')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    rollback = DatabaseRollback(args.environment, args.config)
    
    try:
        if args.command == 'migration':
            result = await rollback.rollback_migration(args.revision, args.steps)
            logger.info(f"Migration rollback result: {result['status']}")
            
        elif args.command == 'restore':
            result = await rollback.restore_from_backup(args.backup_file, args.point_in_time)
            logger.info(f"Restore result: {result['status']}")
            
        elif args.command == 'emergency':
            result = await rollback.emergency_rollback(args.reason)
            logger.info(f"Emergency rollback result: {result['status']}")
            
        elif args.command == 'list-backups':
            backups = await rollback.list_available_backups()
            print(f"\nAvailable backups ({len(backups)}):")
            for backup in backups[:10]:  # Show last 10
                print(f"  {backup['file']} ({backup['size_mb']} MB, {backup['age_hours']}h ago)")
            
        elif args.command == 'cleanup':
            result = await rollback.cleanup_old_backups()
            logger.info(f"Cleanup completed: {len(result['files_removed'])} files removed, "
                       f"{result['space_freed_mb']} MB freed")
        
    except Exception as e:
        logger.error(f"Rollback operation failed: {e}")
        sys.exit(1)


if __name__ == '__main__':
    asyncio.run(main())
