#!/usr/bin/env python3
"""
Generate Initial Migration Script
Creates the first migration based on existing SQLAlchemy models

This script generates an Alembic migration that creates all the tables
defined in the backend.database.models module.
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

# Add the project root to Python path
sys.path.append(str(Path(__file__).parent.parent))

from tests.migration_framework import MigrationFramework, MigrationConfig

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)


async def generate_initial_migration():
    """Generate initial migration from existing models"""
    
    # Get database URL from environment or use default
    database_url = os.getenv(
        "DATABASE_URL", 
        "postgresql+asyncpg://postgres:password@localhost:5432/hokm_game"
    )
    
    logger.info(f"Generating initial migration for database: {database_url}")
    
    # Create migration configuration
    config = MigrationConfig(
        database_url=database_url,
        migrations_dir="migrations",
        enable_backup=False,  # No backup needed for initial migration
        dry_run=False
    )
    
    try:
        # Create migration framework
        framework = MigrationFramework(config)
        
        # Generate initial migration
        result = framework.generate_migration(
            message="Create initial schema with all game tables",
            auto=True  # Auto-generate based on models
        )
        
        if result.success:
            logger.info(f"Initial migration generated successfully: {result.message}")
            logger.info(f"Migration duration: {result.duration:.2f} seconds")
            
            # Show migration history
            history = framework.get_migration_history()
            if history:
                logger.info("Migration history:")
                for migration in history:
                    logger.info(f"  {migration['revision']}: {migration['message']}")
            
            return True
            
        else:
            logger.error(f"Failed to generate initial migration: {result.message}")
            for error in result.errors:
                logger.error(f"  Error: {error}")
            return False
            
    except Exception as e:
        logger.error(f"Error generating initial migration: {e}")
        return False


async def apply_initial_migration():
    """Apply the initial migration to create the database schema"""
    
    database_url = os.getenv(
        "DATABASE_URL", 
        "postgresql+asyncpg://postgres:password@localhost:5432/hokm_game"
    )
    
    logger.info(f"Applying initial migration to database: {database_url}")
    
    config = MigrationConfig(
        database_url=database_url,
        migrations_dir="migrations",
        enable_backup=False,  # No backup needed for initial schema
        dry_run=False
    )
    
    try:
        framework = MigrationFramework(config)
        
        # Check current revision
        current_revision = framework.get_current_revision()
        logger.info(f"Current database revision: {current_revision}")
        
        # Apply all migrations to head
        result = await framework.upgrade_database("head")
        
        if result.success:
            logger.info(f"Initial migration applied successfully: {result.message}")
            logger.info(f"Migration duration: {result.duration:.2f} seconds")
            
            # Verify the new revision
            new_revision = framework.get_current_revision()
            logger.info(f"New database revision: {new_revision}")
            
            return True
            
        else:
            logger.error(f"Failed to apply initial migration: {result.message}")
            for error in result.errors:
                logger.error(f"  Error: {error}")
            return False
            
    except Exception as e:
        logger.error(f"Error applying initial migration: {e}")
        return False


async def main():
    """Main function for generating and applying initial migration"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate and apply initial database migration")
    parser.add_argument("--action", choices=["generate", "apply", "both"], 
                       default="both", help="Action to perform")
    parser.add_argument("--database-url", help="Database connection URL")
    
    args = parser.parse_args()
    
    # Set database URL if provided
    if args.database_url:
        os.environ["DATABASE_URL"] = args.database_url
    
    success = True
    
    try:
        if args.action in ["generate", "both"]:
            logger.info("=== Generating Initial Migration ===")
            generate_success = await generate_initial_migration()
            if not generate_success:
                logger.error("Failed to generate initial migration")
                success = False
        
        if args.action in ["apply", "both"] and success:
            logger.info("=== Applying Initial Migration ===")
            apply_success = await apply_initial_migration()
            if not apply_success:
                logger.error("Failed to apply initial migration")
                success = False
        
        if success:
            logger.info("Initial migration setup completed successfully!")
            
            # Print next steps
            print("\n" + "="*60)
            print("INITIAL MIGRATION SETUP COMPLETE")
            print("="*60)
            print("\nNext steps:")
            print("1. Review the generated migration file in migrations/versions/")
            print("2. Test the migration on a development database")
            print("3. Create additional migrations as your schema evolves")
            print("\nUseful commands:")
            print("  # Generate new migration")
            print("  python -m tests.migration_framework --action generate --message 'Description'")
            print("\n  # Apply migrations")
            print("  python -m tests.migration_framework --action upgrade")
            print("\n  # Test migrations")
            print("  python tests/migration_example.py --environment development")
            print("="*60)
            
        else:
            logger.error("Initial migration setup failed!")
            sys.exit(1)
            
    except KeyboardInterrupt:
        logger.info("Operation cancelled by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
