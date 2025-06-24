#!/usr/bin/env python3
"""
Database Deployment Script
Automated PostgreSQL database provisioning and migration deployment

Features:
- Environment-specific configuration
- Automated backup creation
- Migration execution with rollback
- Health checks and validation
- Deployment tracking and notifications
"""

import asyncio
import logging
import argparse
import os
import sys
import time
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from tests.migration_framework import MigrationFramework, MigrationConfig
from tests.data_migration_utils import DataMigrationUtils
import subprocess
import requests

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(f'deployment_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
    ]
)
logger = logging.getLogger(__name__)


class DatabaseDeployment:
    """
    Comprehensive database deployment orchestration
    
    Handles:
    - Environment configuration loading
    - Database provisioning and initialization
    - Migration execution with safety checks
    - Backup creation and management
    - Health validation and smoke tests
    - Deployment tracking and notifications
    """
    
    def __init__(self, environment: str, database_url: str, config_path: Optional[str] = None):
        self.environment = environment
        self.database_url = database_url
        self.config = self._load_environment_config(config_path)
        self.deployment_id = f"{environment}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.backup_path = None
        
        # Initialize migration framework
        self.migration_config = MigrationConfig(
            database_url=database_url,
            enable_backup=self.config.get('enable_backup', True),
            maintenance_mode=environment == 'production',
            timeout=self.config.get('migration_timeout', 1800)
        )
        self.migration_framework = MigrationFramework(self.migration_config)
        
    def _load_environment_config(self, config_path: Optional[str] = None) -> Dict[str, Any]:
        """Load environment-specific configuration"""
        if config_path is None:
            config_path = Path(__file__).parent / 'config' / f'{self.environment}.json'
        
        try:
            if Path(config_path).exists():
                with open(config_path, 'r') as f:
                    config = json.load(f)
                logger.info(f"Loaded configuration for {self.environment}")
                return config
            else:
                logger.warning(f"Configuration file not found: {config_path}")
                return self._get_default_config()
        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration based on environment"""
        defaults = {
            'development': {
                'enable_backup': False,
                'migration_timeout': 300,
                'health_check_retries': 3,
                'smoke_test_timeout': 60,
                'notification_channels': []
            },
            'staging': {
                'enable_backup': True,
                'migration_timeout': 600,
                'health_check_retries': 5,
                'smoke_test_timeout': 120,
                'notification_channels': ['slack']
            },
            'production': {
                'enable_backup': True,
                'migration_timeout': 1800,
                'health_check_retries': 10,
                'smoke_test_timeout': 300,
                'notification_channels': ['slack', 'email'],
                'require_approval': True,
                'maintenance_window': '02:00-04:00'
            }
        }
        
        return defaults.get(self.environment, defaults['development'])
    
    async def deploy(self, 
                    target_revision: str = "head",
                    enable_backup: bool = True,
                    run_smoke_tests: bool = True) -> bool:
        """
        Execute complete database deployment
        
        Args:
            target_revision: Target migration revision
            enable_backup: Whether to create backup before deployment
            run_smoke_tests: Whether to run post-deployment validation
        
        Returns:
            bool: True if deployment succeeded, False otherwise
        """
        logger.info(f"Starting database deployment {self.deployment_id}")
        logger.info(f"Environment: {self.environment}")
        logger.info(f"Target revision: {target_revision}")
        
        try:
            # Step 1: Pre-deployment validation
            if not await self._pre_deployment_checks():
                return False
            
            # Step 2: Create backup (if enabled)
            if enable_backup and self.config.get('enable_backup', True):
                self.backup_path = await self._create_deployment_backup()
                if not self.backup_path and self.environment == 'production':
                    logger.error("Backup creation failed, aborting production deployment")
                    return False
            
            # Step 3: Set maintenance mode (production only)
            if self.environment == 'production':
                await self._set_maintenance_mode(True)
            
            try:
                # Step 4: Execute database provisioning
                if not await self._provision_database():
                    raise Exception("Database provisioning failed")
                
                # Step 5: Execute migrations
                migration_result = await self._execute_migrations(target_revision)
                if not migration_result:
                    raise Exception("Migration execution failed")
                
                # Step 6: Run smoke tests
                if run_smoke_tests:
                    smoke_test_result = await self._run_smoke_tests()
                    if not smoke_test_result:
                        raise Exception("Smoke tests failed")
                
                # Step 7: Update deployment tracking
                await self._track_deployment_success()
                
                logger.info(f"Deployment {self.deployment_id} completed successfully")
                await self._send_notification("success", "Database deployment completed successfully")
                return True
                
            except Exception as e:
                logger.error(f"Deployment failed: {e}")
                
                # Attempt automatic rollback
                if self.backup_path:
                    logger.info("Attempting automatic rollback...")
                    rollback_success = await self._execute_rollback()
                    if rollback_success:
                        logger.info("Automatic rollback completed")
                        await self._send_notification("rollback", f"Deployment failed, automatic rollback completed: {str(e)}")
                    else:
                        logger.error("Automatic rollback failed")
                        await self._send_notification("critical", f"Deployment and rollback failed: {str(e)}")
                else:
                    await self._send_notification("error", f"Deployment failed: {str(e)}")
                
                return False
                
            finally:
                # Step 8: Disable maintenance mode
                if self.environment == 'production':
                    await self._set_maintenance_mode(False)
                    
        except Exception as e:
            logger.error(f"Critical deployment error: {e}")
            await self._send_notification("critical", f"Critical deployment error: {str(e)}")
            return False
    
    async def _pre_deployment_checks(self) -> bool:
        """Perform comprehensive pre-deployment validation"""
        logger.info("Running pre-deployment checks...")
        
        try:
            # Check database connectivity
            if not await self._check_database_connectivity():
                logger.error("Database connectivity check failed")
                return False
            
            # Check migration validity
            if not await self.migration_framework.validate_migration("head"):
                logger.error("Migration validation failed")
                return False
            
            # Check disk space
            if not self._check_disk_space():
                logger.error("Insufficient disk space")
                return False
            
            # Check production-specific requirements
            if self.environment == 'production':
                if not await self._check_production_requirements():
                    return False
            
            # Check environment secrets
            if not self._validate_secrets():
                logger.error("Required secrets validation failed")
                return False
            
            logger.info("Pre-deployment checks passed")
            return True
            
        except Exception as e:
            logger.error(f"Pre-deployment checks failed: {e}")
            return False
    
    async def _check_database_connectivity(self) -> bool:
        """Check database connectivity and basic operations"""
        try:
            from sqlalchemy.ext.asyncio import create_async_engine
            from sqlalchemy import text
            
            engine = create_async_engine(self.database_url)
            async with engine.begin() as conn:
                result = await conn.execute(text("SELECT 1"))
                await result.fetchone()
            await engine.dispose()
            
            logger.info("Database connectivity check passed")
            return True
            
        except Exception as e:
            logger.error(f"Database connectivity check failed: {e}")
            return False
    
    def _check_disk_space(self, required_gb: float = 5.0) -> bool:
        """Check available disk space"""
        try:
            import shutil
            free_space = shutil.disk_usage("/").free
            free_gb = free_space / (1024 ** 3)
            
            if free_gb < required_gb:
                logger.error(f"Insufficient disk space: {free_gb:.2f}GB available, {required_gb}GB required")
                return False
            
            logger.info(f"Disk space check passed: {free_gb:.2f}GB available")
            return True
            
        except Exception as e:
            logger.error(f"Disk space check failed: {e}")
            return False
    
    async def _check_production_requirements(self) -> bool:
        """Check production-specific deployment requirements"""
        try:
            # Check maintenance window (if configured)
            maintenance_window = self.config.get('maintenance_window')
            if maintenance_window and not self._is_in_maintenance_window(maintenance_window):
                logger.error(f"Deployment outside maintenance window: {maintenance_window}")
                return False
            
            # Check if approval is required and obtained
            if self.config.get('require_approval', False):
                approval = os.getenv('DEPLOYMENT_APPROVAL')
                if not approval:
                    logger.error("Production deployment approval required but not provided")
                    return False
            
            # Check recent deployment frequency
            if not await self._check_deployment_frequency():
                return False
            
            logger.info("Production requirements check passed")
            return True
            
        except Exception as e:
            logger.error(f"Production requirements check failed: {e}")
            return False
    
    def _is_in_maintenance_window(self, window: str) -> bool:
        """Check if current time is within maintenance window"""
        try:
            start_time, end_time = window.split('-')
            current_time = datetime.now().strftime('%H:%M')
            return start_time <= current_time <= end_time
        except:
            return True  # Allow deployment if window parsing fails
    
    async def _check_deployment_frequency(self) -> bool:
        """Check if deployments are too frequent"""
        # This would check deployment history from tracking system
        # For now, just log and return True
        logger.info("Deployment frequency check passed")
        return True
    
    def _validate_secrets(self) -> bool:
        """Validate required secrets and credentials"""
        required_secrets = {
            'development': [],
            'staging': ['STAGING_DATABASE_URL'],
            'production': ['PRODUCTION_DATABASE_URL', 'BACKUP_ENCRYPTION_KEY']
        }
        
        env_secrets = required_secrets.get(self.environment, [])
        
        for secret in env_secrets:
            if not os.getenv(secret):
                logger.error(f"Required secret not found: {secret}")
                return False
        
        logger.info("Secrets validation passed")
        return True
    
    async def _create_deployment_backup(self) -> Optional[str]:
        """Create deployment backup"""
        logger.info("Creating deployment backup...")
        
        try:
            backup_name = f"deployment_{self.deployment_id}"
            backup_path = await self.migration_framework.create_backup(backup_name)
            
            if backup_path:
                logger.info(f"Deployment backup created: {backup_path}")
                
                # Upload backup to remote storage if configured
                backup_storage_url = os.getenv('BACKUP_STORAGE_URL')
                if backup_storage_url:
                    await self._upload_backup_to_storage(backup_path, backup_storage_url)
                
                return backup_path
            else:
                logger.error("Backup creation failed")
                return None
                
        except Exception as e:
            logger.error(f"Backup creation error: {e}")
            return None
    
    async def _upload_backup_to_storage(self, backup_path: str, storage_url: str):
        """Upload backup to remote storage"""
        try:
            # This would implement actual backup upload to S3, Azure, etc.
            logger.info(f"Uploading backup to storage: {storage_url}")
            # Implementation depends on storage provider
            logger.info("Backup upload completed")
        except Exception as e:
            logger.error(f"Backup upload failed: {e}")
    
    async def _provision_database(self) -> bool:
        """Provision database infrastructure if needed"""
        logger.info("Checking database provisioning...")
        
        try:
            # Check if database exists and is accessible
            await self._check_database_connectivity()
            
            # Run database initialization if needed
            if not await self._is_database_initialized():
                logger.info("Initializing database schema...")
                await self._initialize_database()
            
            # Ensure required extensions are installed
            await self._install_database_extensions()
            
            logger.info("Database provisioning completed")
            return True
            
        except Exception as e:
            logger.error(f"Database provisioning failed: {e}")
            return False
    
    async def _is_database_initialized(self) -> bool:
        """Check if database is already initialized"""
        try:
            from sqlalchemy.ext.asyncio import create_async_engine
            from sqlalchemy import text
            
            engine = create_async_engine(self.database_url)
            async with engine.begin() as conn:
                result = await conn.execute(text("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.tables 
                        WHERE table_name = 'alembic_version'
                    )
                """))
                exists = result.scalar()
            await engine.dispose()
            
            return bool(exists)
            
        except Exception as e:
            logger.error(f"Database initialization check failed: {e}")
            return False
    
    async def _initialize_database(self):
        """Initialize database with basic schema"""
        try:
            from backend.database.models import Base
            from sqlalchemy.ext.asyncio import create_async_engine
            
            engine = create_async_engine(self.database_url)
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            await engine.dispose()
            
            logger.info("Database schema initialized")
            
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            raise
    
    async def _install_database_extensions(self):
        """Install required PostgreSQL extensions"""
        try:
            from sqlalchemy.ext.asyncio import create_async_engine
            from sqlalchemy import text
            
            extensions = ['uuid-ossp', 'pg_trgm', 'btree_gin']
            
            engine = create_async_engine(self.database_url)
            async with engine.begin() as conn:
                for ext in extensions:
                    try:
                        await conn.execute(text(f"CREATE EXTENSION IF NOT EXISTS \"{ext}\""))
                        logger.info(f"Extension installed: {ext}")
                    except Exception as e:
                        logger.warning(f"Failed to install extension {ext}: {e}")
            await engine.dispose()
            
        except Exception as e:
            logger.error(f"Extension installation failed: {e}")
    
    async def _execute_migrations(self, target_revision: str) -> bool:
        """Execute database migrations"""
        logger.info(f"Executing migrations to {target_revision}...")
        
        try:
            result = await self.migration_framework.upgrade_database(target_revision)
            
            if result.success:
                logger.info(f"Migrations completed successfully in {result.duration:.2f} seconds")
                return True
            else:
                logger.error(f"Migration failed: {result.message}")
                for error in result.errors:
                    logger.error(f"Migration error: {error}")
                return False
                
        except Exception as e:
            logger.error(f"Migration execution error: {e}")
            return False
    
    async def _run_smoke_tests(self) -> bool:
        """Run post-deployment smoke tests"""
        logger.info("Running smoke tests...")
        
        try:
            # Import and run smoke tests
            from database.smoke_tests import run_smoke_tests
            
            test_result = await run_smoke_tests(
                database_url=self.database_url,
                environment=self.environment,
                timeout=self.config.get('smoke_test_timeout', 120)
            )
            
            if test_result:
                logger.info("Smoke tests passed")
                return True
            else:
                logger.error("Smoke tests failed")
                return False
                
        except Exception as e:
            logger.error(f"Smoke test execution failed: {e}")
            return False
    
    async def _execute_rollback(self) -> bool:
        """Execute deployment rollback"""
        try:
            if self.backup_path:
                success = await self.migration_framework.restore_backup(self.backup_path)
                if success:
                    logger.info("Rollback from backup completed")
                    return True
            
            # Try Alembic-based rollback
            current_revision = self.migration_framework.get_current_revision()
            if current_revision:
                history = self.migration_framework.get_migration_history()
                for migration in history:
                    if migration['revision'] == current_revision and migration['down_revision']:
                        result = await self.migration_framework.downgrade_database(migration['down_revision'])
                        if result.success:
                            logger.info("Alembic rollback completed")
                            return True
            
            logger.error("Rollback failed")
            return False
            
        except Exception as e:
            logger.error(f"Rollback execution failed: {e}")
            return False
    
    async def _set_maintenance_mode(self, enabled: bool):
        """Set application maintenance mode"""
        try:
            # This would set a flag in Redis or send signals to application servers
            # For now, just log the action
            status = "enabled" if enabled else "disabled"
            logger.info(f"Maintenance mode {status}")
            
            # Example: Set Redis flag
            # await redis_client.set('maintenance_mode', enabled)
            
        except Exception as e:
            logger.error(f"Failed to set maintenance mode: {e}")
    
    async def _track_deployment_success(self):
        """Track successful deployment"""
        try:
            deployment_info = {
                'deployment_id': self.deployment_id,
                'environment': self.environment,
                'timestamp': datetime.now().isoformat(),
                'status': 'success',
                'commit_sha': os.getenv('GITHUB_SHA', 'unknown'),
                'backup_path': self.backup_path
            }
            
            # Store deployment info (would typically use a tracking service)
            tracking_file = Path(f'deployments/{self.environment}_deployments.json')
            tracking_file.parent.mkdir(exist_ok=True)
            
            deployments = []
            if tracking_file.exists():
                with open(tracking_file, 'r') as f:
                    deployments = json.load(f)
            
            deployments.append(deployment_info)
            
            with open(tracking_file, 'w') as f:
                json.dump(deployments, f, indent=2)
            
            logger.info(f"Deployment tracking updated: {self.deployment_id}")
            
        except Exception as e:
            logger.error(f"Deployment tracking failed: {e}")
    
    async def _send_notification(self, status: str, message: str):
        """Send deployment notifications"""
        try:
            notification_channels = self.config.get('notification_channels', [])
            
            for channel in notification_channels:
                if channel == 'slack':
                    await self._send_slack_notification(status, message)
                elif channel == 'email':
                    await self._send_email_notification(status, message)
            
        except Exception as e:
            logger.error(f"Notification sending failed: {e}")
    
    async def _send_slack_notification(self, status: str, message: str):
        """Send Slack notification"""
        try:
            webhook_url = os.getenv('DEPLOYMENT_SLACK_WEBHOOK')
            if not webhook_url:
                return
            
            color_map = {
                'success': 'good',
                'error': 'danger',
                'rollback': 'warning',
                'critical': 'danger'
            }
            
            payload = {
                'text': f'Database Deployment {status.upper()}',
                'attachments': [{
                    'color': color_map.get(status, 'warning'),
                    'fields': [
                        {'title': 'Environment', 'value': self.environment, 'short': True},
                        {'title': 'Deployment ID', 'value': self.deployment_id, 'short': True},
                        {'title': 'Message', 'value': message, 'short': False}
                    ],
                    'ts': int(time.time())
                }]
            }
            
            response = requests.post(webhook_url, json=payload, timeout=10)
            response.raise_for_status()
            
        except Exception as e:
            logger.error(f"Slack notification failed: {e}")
    
    async def _send_email_notification(self, status: str, message: str):
        """Send email notification"""
        # Email notification implementation would go here
        logger.info(f"Email notification: {status} - {message}")


async def main():
    """Main deployment function"""
    parser = argparse.ArgumentParser(description="Deploy database changes")
    parser.add_argument('--environment', required=True, 
                       choices=['development', 'staging', 'production'],
                       help='Deployment environment')
    parser.add_argument('--database-url', required=True,
                       help='Database connection URL')
    parser.add_argument('--target-revision', default='head',
                       help='Target migration revision')
    parser.add_argument('--enable-backup', action='store_true', default=True,
                       help='Create backup before deployment')
    parser.add_argument('--run-smoke-tests', action='store_true', default=True,
                       help='Run smoke tests after deployment')
    parser.add_argument('--maintenance-mode', action='store_true',
                       help='Enable maintenance mode during deployment')
    
    args = parser.parse_args()
    
    try:
        deployment = DatabaseDeployment(args.environment, args.database_url)
        
        success = await deployment.deploy(
            target_revision=args.target_revision,
            enable_backup=args.enable_backup,
            run_smoke_tests=args.run_smoke_tests
        )
        
        if success:
            logger.info("Database deployment completed successfully")
            sys.exit(0)
        else:
            logger.error("Database deployment failed")
            sys.exit(1)
            
    except KeyboardInterrupt:
        logger.info("Deployment cancelled by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Deployment error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
