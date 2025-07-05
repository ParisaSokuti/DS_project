# Database Migration System Documentation
# Hokm Game Server - Production-Ready Migration Framework

## Overview

This document provides comprehensive guidance for using the database migration system for the Hokm game server. The system is built on Alembic and SQLAlchemy 2.0, providing robust, version-controlled database schema evolution with zero-downtime deployment capabilities.

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Setup and Configuration](#setup-and-configuration)
3. [Creating Migrations](#creating-migrations)
4. [Executing Migrations](#executing-migrations)
5. [Rollback Procedures](#rollback-procedures)
6. [Zero-Downtime Strategies](#zero-downtime-strategies)
7. [Testing Migrations](#testing-migrations)
8. [Monitoring and Logging](#monitoring-and-logging)
9. [Best Practices](#best-practices)
10. [Troubleshooting](#troubleshooting)

## Architecture Overview

The migration system consists of several key components:

### Core Components

- **MigrationFramework**: Main orchestration class for migration operations
- **DataMigrationUtils**: Utilities for complex data transformations
- **MigrationTester**: Comprehensive testing framework for migrations
- **Alembic Integration**: Version control and script generation
- **Monitoring**: Real-time tracking via MigrationLog and SchemaVersion models

### Directory Structure

```
migrations/
├── alembic.ini              # Alembic configuration
├── env.py                   # Environment setup for migrations
├── script.py.mako          # Migration template
├── versions/               # Generated migration scripts
│   ├── 001_initial_schema.py
│   ├── 002_add_player_stats.py
│   └── ...
└── README.md               # Migration-specific documentation

tests/
├── migration_framework.py   # Core migration orchestration
├── data_migration_utils.py  # Data transformation utilities
├── migration_testing.py     # Comprehensive testing framework
└── migration_results/       # Test reports and logs

backups/
├── pre_migration_backups/   # Automatic database backups
└── data_backups/           # Table-specific backups
```

## Setup and Configuration

### Prerequisites

1. **Database Dependencies**:
   ```bash
   pip install sqlalchemy>=2.0.0 alembic>=1.9.0 asyncpg>=0.27.0
   ```

2. **Environment Variables**:
   ```bash
   # Primary database
   DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/hokm_game
   
   # Test database (for migration testing)
   TEST_DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/hokm_test
   
   # Migration settings
   MIGRATION_ENV=production  # or development, staging
   ENABLE_MIGRATION_BACKUPS=true
   MIGRATION_TIMEOUT=300
   ```

### Initial Setup

1. **Initialize Migration Environment**:
   ```python
   from tests.migration_framework import MigrationFramework, MigrationConfig
   
   config = MigrationConfig(
       database_url="postgresql+asyncpg://user:password@localhost:5432/hokm_game",
       migrations_dir="migrations",
       enable_backup=True,
       maintenance_mode=True  # For production deployments
   )
   
   framework = MigrationFramework(config)
   ```

2. **Generate Initial Migration**:
   ```bash
   # From project root
   python -m tests.migration_framework \
       --database-url $DATABASE_URL \
       --action generate \
       --message "Initial schema"
   ```

## Creating Migrations

### Automatic Migration Generation

For schema changes detected from model modifications:

```python
# Generate migration automatically
framework = MigrationFramework(config)
result = framework.generate_migration("Add player rating system", auto=True)

if result.success:
    print(f"Migration generated: {result.message}")
else:
    print(f"Failed to generate migration: {result.errors}")
```

### Manual Migration Scripts

For complex data transformations or custom operations:

```python
# Create empty migration template
result = framework.generate_migration("Complex data transformation", auto=False)

# Edit the generated file in migrations/versions/
# Add custom upgrade/downgrade logic
```

### Example Migration Script

```python
"""Add advanced player statistics

Revision ID: abc123def456
Revises: xyz789abc123
Create Date: 2024-01-15 10:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = 'abc123def456'
down_revision = 'xyz789abc123'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Schema changes
    op.add_column('players', 
        sa.Column('skill_rating', sa.Integer(), nullable=True, default=1000))
    op.add_column('players', 
        sa.Column('performance_metrics', postgresql.JSONB(), nullable=True))
    
    # Create index for performance
    op.create_index('idx_players_skill_rating', 'players', ['skill_rating'])
    
    # Data migration (if needed)
    # Use DataMigrationUtils for complex transformations
    connection = op.get_bind()
    connection.execute(sa.text("""
        UPDATE players 
        SET skill_rating = CASE 
            WHEN rating > 1500 THEN rating + 200
            ELSE rating
        END
        WHERE skill_rating IS NULL
    """))


def downgrade() -> None:
    # Remove in reverse order
    op.drop_index('idx_players_skill_rating')
    op.drop_column('players', 'performance_metrics')
    op.drop_column('players', 'skill_rating')
```

### Data Migration with Utilities

For complex data transformations:

```python
from tests.data_migration_utils import DataMigrationUtils

async def upgrade_with_data_migration():
    """Example of using data migration utilities"""
    async with get_db_session() as session:
        utils = DataMigrationUtils(session)
        
        # Backup existing data
        backup_path = await utils.backup_table_data(
            "players", 
            "players_pre_stats_migration", 
            format="json"
        )
        
        # Transform player statistics
        def transform_stats(old_record):
            return {
                **old_record,
                'skill_rating': calculate_skill_rating(old_record),
                'performance_metrics': generate_performance_metrics(old_record)
            }
        
        # Migrate data with transformation
        progress = await utils.migrate_table_data(
            source_table="players_backup",
            target_table="players",
            transformation_func=transform_stats,
            validation_func=validate_player_stats
        )
        
        print(f"Migrated {progress.successful_records} records")
```

## Executing Migrations

### Development Environment

```bash
# Quick upgrade to latest
python -m tests.migration_framework \
    --database-url $DATABASE_URL \
    --action upgrade

# Upgrade to specific revision
python -m tests.migration_framework \
    --database-url $DATABASE_URL \
    --action upgrade \
    --revision abc123def456

# Dry run (see what would happen)
python -m tests.migration_framework \
    --database-url $DATABASE_URL \
    --action upgrade \
    --dry-run
```

### Production Environment

```python
import asyncio
from tests.migration_framework import MigrationFramework, MigrationConfig

async def production_migration():
    """Production-safe migration execution"""
    config = MigrationConfig(
        database_url=os.getenv("DATABASE_URL"),
        enable_backup=True,
        maintenance_mode=True,  # Enable maintenance mode
        enable_rollback_test=True,
        timeout=1800  # 30 minutes for large migrations
    )
    
    framework = MigrationFramework(config)
    
    try:
        # Pre-migration validation
        current_revision = framework.get_current_revision()
        print(f"Current revision: {current_revision}")
        
        # Validate migration before applying
        is_valid = await framework.validate_migration("head")
        if not is_valid:
            raise Exception("Migration validation failed")
        
        # Execute migration
        result = await framework.upgrade_database("head")
        
        if result.success:
            print(f"Migration completed: {result.message}")
            print(f"Duration: {result.duration:.2f} seconds")
            print(f"Backup created: {result.backup_created}")
        else:
            print(f"Migration failed: {result.message}")
            for error in result.errors:
                print(f"Error: {error}")
                
    except Exception as e:
        print(f"Migration execution failed: {e}")
        # Emergency rollback procedures would go here

# Run the migration
asyncio.run(production_migration())
```

## Rollback Procedures

### Automatic Rollback

The system provides automatic rollback capabilities:

```python
# Rollback to previous revision
result = await framework.downgrade_database("previous_revision_id")

# Rollback using backup (if migration fails)
if backup_path and not result.success:
    success = await framework.restore_backup(backup_path)
    if success:
        print("Database restored from backup")
```

### Manual Rollback Process

For emergency situations:

1. **Immediate Rollback**:
   ```bash
   # Stop application servers
   sudo systemctl stop hokm-game-server
   
   # Rollback database
   python -m tests.migration_framework \
       --database-url $DATABASE_URL \
       --action downgrade \
       --revision previous_known_good_revision
   
   # Restart application
   sudo systemctl start hokm-game-server
   ```

2. **Backup Restoration**:
   ```bash
   # If rollback fails, restore from backup
   psql $DATABASE_URL < backups/pre_migration_backup_20240115_103000.sql
   ```

### Rollback Safety Testing

Before production deployment:

```python
from tests.migration_testing import MigrationTester, MigrationTestSuite

async def test_rollback_safety():
    """Test migration rollback safety"""
    config = MigrationTestSuite(
        database_url=TEST_DATABASE_URL,
        test_database_url=TEST_DATABASE_URL,
        enable_rollback_tests=True
    )
    
    tester = MigrationTester(config)
    await tester.setup()
    
    # Test rollback capability
    await tester.test_rollback_safety()
    
    results = tester.test_results
    for result in results:
        if result.test_name == "rollback_safety":
            print(f"Rollback test: {result.success}")
            print(f"Message: {result.message}")
```

## Zero-Downtime Strategies

### Blue-Green Deployment

For zero-downtime deployments with database changes:

```python
async def blue_green_migration():
    """Blue-green deployment strategy"""
    # This requires infrastructure setup for database replication
    result = await framework.blue_green_migration("head")
    
    # Process:
    # 1. Create green database (copy of blue)
    # 2. Apply migrations to green
    # 3. Test green database
    # 4. Switch application to green
    # 5. Decommission blue (after verification)
```

### Rolling Deployment

For gradual rollout:

```python
async def rolling_migration():
    """Rolling deployment with backward compatibility"""
    # Requires careful migration design
    result = await framework.rolling_migration("head")
    
    # Process:
    # 1. Deploy schema changes that are backward compatible
    # 2. Deploy new application version
    # 3. Apply data migrations
    # 4. Clean up deprecated schema elements
```

### Shadow Database Testing

Test migrations on a copy before production:

```python
async def shadow_migration_test():
    """Test migration on shadow database"""
    result = await framework.shadow_migration("head")
    
    # Process:
    # 1. Create shadow database from production backup
    # 2. Apply migrations to shadow
    # 3. Run comprehensive tests
    # 4. Apply to production if tests pass
```

## Testing Migrations

### Comprehensive Test Suite

```python
from tests.migration_testing import run_migration_tests

async def test_migrations():
    """Run comprehensive migration tests"""
    results = await run_migration_tests(
        database_url=DATABASE_URL,
        test_database_url=TEST_DATABASE_URL,
        test_data_size=10000,  # Test with realistic data size
        performance_threshold_seconds=120.0,
        enable_concurrency_tests=True
    )
    
    # Generate report
    passed = sum(1 for r in results if r.success)
    failed = len(results) - passed
    
    print(f"Migration tests completed: {passed} passed, {failed} failed")
    
    for result in results:
        if not result.success:
            print(f"FAILED: {result.test_name} - {result.message}")
```

### Performance Testing

Test migration performance with various data sizes:

```python
async def performance_test():
    """Test migration performance"""
    config = MigrationTestSuite(
        database_url=TEST_DATABASE_URL,
        test_database_url=TEST_DATABASE_URL,
        test_data_size=100000,  # Large dataset
        performance_threshold_seconds=300.0  # 5 minute threshold
    )
    
    tester = MigrationTester(config)
    await tester.setup()
    await tester.test_migration_performance()
    
    # Check results
    for result in tester.test_results:
        if result.test_name == "migration_performance":
            metrics = result.performance_metrics
            for size, data in metrics.items():
                print(f"Size {size}: {data['duration']:.2f}s ({data['records_per_second']:.0f} records/sec)")
```

### Concurrency Testing

Test migration behavior under load:

```python
async def concurrency_test():
    """Test migration under concurrent database access"""
    config = MigrationTestSuite(
        database_url=TEST_DATABASE_URL,
        test_database_url=TEST_DATABASE_URL,
        concurrency_level=10  # 10 concurrent connections
    )
    
    tester = MigrationTester(config)
    await tester.setup()
    await tester.test_concurrent_migrations()
```

## Monitoring and Logging

### Migration Logging

All migrations are automatically logged in the `migration_logs` table:

```sql
-- Check recent migrations
SELECT 
    revision,
    description,
    status,
    started_at,
    completed_at,
    execution_time_seconds,
    error_message
FROM migration_logs 
ORDER BY started_at DESC 
LIMIT 10;

-- Check for failed migrations
SELECT * FROM migration_logs 
WHERE status = 'failed' 
ORDER BY started_at DESC;
```

### Schema Version Tracking

Track current schema state:

```sql
-- Get current schema version
SELECT * FROM schema_versions 
WHERE is_current = TRUE;

-- View version history
SELECT 
    version,
    description,
    applied_at,
    is_rollback_safe
FROM schema_versions 
ORDER BY applied_at DESC;
```

### Performance Monitoring

Monitor migration performance:

```python
# Check migration performance metrics
async def check_migration_performance():
    async with get_db_session() as session:
        result = await session.execute(text("""
            SELECT 
                revision,
                execution_time_seconds,
                affected_rows,
                backup_size_bytes / 1024 / 1024 as backup_size_mb
            FROM migration_logs
            WHERE status = 'completed'
            ORDER BY started_at DESC
            LIMIT 10
        """))
        
        for row in result:
            print(f"Migration {row.revision}: {row.execution_time_seconds}s, {row.affected_rows} rows")
```

## Best Practices

### Migration Design

1. **Make Migrations Atomic**:
   - Each migration should be a single, atomic operation
   - Use transactions to ensure consistency
   - Include proper error handling and rollback logic

2. **Maintain Backward Compatibility**:
   - Add columns as nullable initially
   - Use multiple migrations for complex changes
   - Avoid breaking changes in production

3. **Test Thoroughly**:
   - Test on realistic data sizes
   - Test rollback procedures
   - Validate performance impact

### Data Migrations

1. **Use Batched Processing**:
   ```python
   # Process large datasets in batches
   await utils.migrate_table_data(
       source_table="large_table",
       target_table="new_table",
       batch_size=1000  # Process 1000 records at a time
   )
   ```

2. **Validate Data Integrity**:
   ```python
   # Always validate after data migration
   validation_result = await utils.validate_data_integrity(
       table_name="migrated_table",
       validation_rules={
           'email': validate_email_format,
           'rating': lambda x: 0 <= x <= 3000
       }
   )
   ```

3. **Create Backups**:
   ```python
   # Always backup before data migrations
   backup_path = await utils.backup_table_data(
       table_name="critical_data",
       format="json"
   )
   ```

### Production Deployment

1. **Use Maintenance Mode**:
   ```python
   config = MigrationConfig(
       database_url=DATABASE_URL,
       maintenance_mode=True,  # Prevents new connections
       enable_backup=True
   )
   ```

2. **Monitor During Migration**:
   - Watch database performance metrics
   - Monitor application error rates
   - Have rollback plan ready

3. **Staged Rollout**:
   - Test in staging environment first
   - Use blue-green or rolling deployments
   - Monitor post-migration performance

### Error Handling

1. **Comprehensive Error Logging**:
   ```python
   try:
       result = await framework.upgrade_database("head")
   except Exception as e:
       logger.error(f"Migration failed: {e}")
       # Log to migration_logs table
       # Send alerts to monitoring system
       # Execute rollback procedures
   ```

2. **Automatic Recovery**:
   ```python
   if not result.success and result.backup_created:
       # Attempt automatic rollback
       recovery_success = await framework.restore_backup(result.backup_path)
       if recovery_success:
           logger.info("Automatic recovery successful")
   ```

## Troubleshooting

### Common Issues

1. **Migration Hangs**:
   ```bash
   # Check for blocking queries
   SELECT 
       pid, 
       state, 
       query, 
       query_start 
   FROM pg_stat_activity 
   WHERE state != 'idle';
   
   # Kill blocking queries if necessary
   SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE pid = <blocking_pid>;
   ```

2. **Out of Disk Space**:
   ```bash
   # Check disk usage
   df -h
   
   # Clean up old backups
   python -c "
   from tests.data_migration_utils import DataMigrationUtils
   import asyncio
   utils = DataMigrationUtils(None)
   asyncio.run(utils.cleanup_old_backups(days_to_keep=7))
   "
   ```

3. **Performance Issues**:
   ```sql
   -- Check for missing indexes
   SELECT schemaname, tablename, attname, n_distinct, correlation 
   FROM pg_stats 
   WHERE tablename = 'your_table';
   
   -- Analyze query performance
   EXPLAIN (ANALYZE, BUFFERS) SELECT * FROM your_table WHERE condition;
   ```

### Recovery Procedures

1. **Failed Migration Recovery**:
   ```python
   # Manual recovery process
   async def emergency_recovery():
       # 1. Stop application
       # 2. Restore from backup
       success = await framework.restore_backup("path/to/backup.sql")
       
       # 3. Mark migration as failed
       async with get_db_session() as session:
           await session.execute(text("""
               UPDATE migration_logs 
               SET status = 'failed', error_message = :error
               WHERE revision = :revision
           """), {"error": "Manual recovery", "revision": "failed_revision"})
           
       # 4. Restart application
   ```

2. **Data Corruption Recovery**:
   ```python
   # Validate and repair data
   async def repair_data():
       utils = DataMigrationUtils(session)
       
       # Check data integrity
       result = await utils.validate_data_integrity(
           table_name="corrupted_table",
           validation_rules=validation_rules
       )
       
       if not result.is_valid:
           # Restore from backup
           await utils.restore_table_data(
               backup_path="backups/table_backup.json",
               table_name="corrupted_table",
               truncate_first=True
           )
   ```

### Performance Optimization

1. **Index Optimization**:
   ```sql
   -- Add indexes for migration queries
   CREATE INDEX CONCURRENTLY idx_migration_temp ON large_table(migration_column);
   
   -- Drop after migration
   DROP INDEX idx_migration_temp;
   ```

2. **Batch Size Tuning**:
   ```python
   # Adjust batch size based on performance
   optimal_batch_size = await utils.find_optimal_batch_size(
       table_name="large_table",
       test_sizes=[100, 500, 1000, 5000]
   )
   ```

## Conclusion

This migration system provides enterprise-grade database evolution capabilities for the Hokm game server. By following the practices outlined in this documentation, you can safely evolve your database schema while maintaining zero downtime and data integrity.

For additional support or questions, refer to the test files and examples provided in the `tests/` directory.

### Quick Reference Commands

```bash
# Generate migration
python -m tests.migration_framework --database-url $DB_URL --action generate --message "Description"

# Apply migrations
python -m tests.migration_framework --database-url $DB_URL --action upgrade

# Rollback
python -m tests.migration_framework --database-url $DB_URL --action downgrade --revision previous_id

# Test migrations
python -m tests.migration_testing --database-url $DB_URL --test-database-url $TEST_DB_URL

# Check current version
python -m tests.migration_framework --database-url $DB_URL --action current

# View history
python -m tests.migration_framework --database-url $DB_URL --action history
```
