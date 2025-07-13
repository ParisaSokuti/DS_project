"""
Data Migration Utilities for Hokm Game Server
Provides tools for safely migrating data during schema changes
"""

import asyncio
import logging
from typing import Dict, List, Any, Optional, Callable, AsyncGenerator
from datetime import datetime
from contextlib import asynccontextmanager
import json
from pathlib import Path

from sqlalchemy import text, inspect, Table, MetaData
from sqlalchemy.ext.asyncio import AsyncSession, AsyncEngine, create_async_engine
from sqlalchemy.orm import sessionmaker
import asyncpg

from migration_framework import MigrationFramework

logger = logging.getLogger(__name__)

class DataMigrationUtilities:
    """
    Utilities for data migration during schema changes
    Provides safe, efficient data transformation and migration capabilities
    """
    
    def __init__(self, database_url: str, batch_size: int = 1000):
        self.database_url = database_url
        self.batch_size = batch_size
        self.engine = None
        self.session_factory = None
        
    async def setup(self):
        """Setup database connections"""
        self.engine = create_async_engine(
            self.database_url,
            echo=False,
            pool_size=10,
            max_overflow=20
        )
        self.session_factory = sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False
        )
    
    async def cleanup(self):
        """Cleanup resources"""
        if self.engine:
            await self.engine.dispose()
    
    @asynccontextmanager
    async def get_session(self):
        """Get database session with automatic cleanup"""
        async with self.session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()
    
    async def migrate_table_data(
        self,
        source_table: str,
        target_table: str,
        transformation_func: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
        where_clause: Optional[str] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> Dict[str, Any]:
        """
        Migrate data from source table to target table with optional transformation
        
        Args:
            source_table: Source table name
            target_table: Target table name
            transformation_func: Optional function to transform each row
            where_clause: Optional WHERE clause to filter source data
            progress_callback: Optional callback for progress reporting
            
        Returns:
            Migration statistics
        """
        logger.info(f"Starting data migration from {source_table} to {target_table}")
        
        stats = {
            'total_rows': 0,
            'migrated_rows': 0,
            'failed_rows': 0,
            'start_time': datetime.now(),
            'end_time': None,
            'errors': []
        }
        
        try:
            async with self.get_session() as session:
                # Get total row count
                count_query = f"SELECT COUNT(*) FROM {source_table}"
                if where_clause:
                    count_query += f" WHERE {where_clause}"
                
                result = await session.execute(text(count_query))
                stats['total_rows'] = result.scalar()
                
                logger.info(f"Total rows to migrate: {stats['total_rows']}")
                
                # Migrate data in batches
                offset = 0
                while offset < stats['total_rows']:
                    batch_query = f"SELECT * FROM {source_table}"
                    if where_clause:
                        batch_query += f" WHERE {where_clause}"
                    batch_query += f" LIMIT {self.batch_size} OFFSET {offset}"
                    
                    result = await session.execute(text(batch_query))
                    rows = result.fetchall()
                    
                    if not rows:
                        break
                    
                    # Process batch
                    batch_stats = await self._process_migration_batch(
                        session, rows, target_table, transformation_func
                    )
                    
                    stats['migrated_rows'] += batch_stats['migrated']
                    stats['failed_rows'] += batch_stats['failed']
                    stats['errors'].extend(batch_stats['errors'])
                    
                    # Progress callback
                    if progress_callback:
                        progress_callback(stats['migrated_rows'], stats['total_rows'])
                    
                    offset += self.batch_size
                    
                    # Commit batch
                    await session.commit()
                    
                    logger.info(f"Migrated {stats['migrated_rows']}/{stats['total_rows']} rows")
                
                stats['end_time'] = datetime.now()
                duration = (stats['end_time'] - stats['start_time']).total_seconds()
                
                logger.info(f"Data migration completed in {duration:.2f} seconds")
                logger.info(f"Migrated: {stats['migrated_rows']}, Failed: {stats['failed_rows']}")
                
                return stats
                
        except Exception as e:
            logger.error(f"Data migration failed: {e}")
            stats['end_time'] = datetime.now()
            stats['errors'].append(str(e))
            raise
    
    async def _process_migration_batch(
        self,
        session: AsyncSession,
        rows: List[Any],
        target_table: str,
        transformation_func: Optional[Callable]
    ) -> Dict[str, Any]:
        """Process a batch of rows for migration"""
        batch_stats = {
            'migrated': 0,
            'failed': 0,
            'errors': []
        }
        
        for row in rows:
            try:
                # Convert row to dictionary
                row_dict = dict(row._mapping) if hasattr(row, '_mapping') else dict(row)
                
                # Apply transformation if provided
                if transformation_func:
                    transformed_row = transformation_func(row_dict)
                else:
                    transformed_row = row_dict
                
                # Insert into target table
                columns = ', '.join(transformed_row.keys())
                placeholders = ', '.join([f':{key}' for key in transformed_row.keys()])
                insert_query = f"INSERT INTO {target_table} ({columns}) VALUES ({placeholders})"
                
                await session.execute(text(insert_query), transformed_row)
                batch_stats['migrated'] += 1
                
            except Exception as e:
                batch_stats['failed'] += 1
                batch_stats['errors'].append({
                    'row': dict(row._mapping) if hasattr(row, '_mapping') else dict(row),
                    'error': str(e)
                })
                logger.warning(f"Failed to migrate row: {e}")
        
        return batch_stats
    
    async def validate_data_integrity(
        self,
        source_table: str,
        target_table: str,
        key_columns: List[str],
        validation_queries: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Validate data integrity after migration
        
        Args:
            source_table: Source table name
            target_table: Target table name
            key_columns: Columns to use for row matching
            validation_queries: Optional custom validation queries
            
        Returns:
            Validation results
        """
        logger.info(f"Validating data integrity between {source_table} and {target_table}")
        
        validation_results = {
            'row_count_match': False,
            'key_integrity': True,
            'data_consistency': True,
            'source_count': 0,
            'target_count': 0,
            'missing_keys': [],
            'extra_keys': [],
            'custom_validation_results': [],
            'errors': []
        }
        
        try:
            async with self.get_session() as session:
                # Compare row counts
                source_count_result = await session.execute(text(f"SELECT COUNT(*) FROM {source_table}"))
                target_count_result = await session.execute(text(f"SELECT COUNT(*) FROM {target_table}"))
                
                validation_results['source_count'] = source_count_result.scalar()
                validation_results['target_count'] = target_count_result.scalar()
                validation_results['row_count_match'] = (
                    validation_results['source_count'] == validation_results['target_count']
                )
                
                # Validate key integrity
                key_columns_str = ', '.join(key_columns)
                
                # Find missing keys (in source but not in target)
                missing_keys_query = f"""
                    SELECT {key_columns_str} FROM {source_table}
                    EXCEPT
                    SELECT {key_columns_str} FROM {target_table}
                """
                
                missing_result = await session.execute(text(missing_keys_query))
                validation_results['missing_keys'] = [dict(row._mapping) for row in missing_result.fetchall()]
                
                # Find extra keys (in target but not in source)
                extra_keys_query = f"""
                    SELECT {key_columns_str} FROM {target_table}
                    EXCEPT
                    SELECT {key_columns_str} FROM {source_table}
                """
                
                extra_result = await session.execute(text(extra_keys_query))
                validation_results['extra_keys'] = [dict(row._mapping) for row in extra_result.fetchall()]
                
                # Update integrity flags
                validation_results['key_integrity'] = (
                    len(validation_results['missing_keys']) == 0 and
                    len(validation_results['extra_keys']) == 0
                )
                
                # Run custom validation queries
                if validation_queries:
                    for i, query in enumerate(validation_queries):
                        try:
                            result = await session.execute(text(query))
                            rows = result.fetchall()
                            validation_results['custom_validation_results'].append({
                                'query_index': i,
                                'query': query,
                                'passed': len(rows) == 0,  # Assuming validation queries return issues
                                'issues': [dict(row._mapping) for row in rows]
                            })
                        except Exception as e:
                            validation_results['custom_validation_results'].append({
                                'query_index': i,
                                'query': query,
                                'passed': False,
                                'error': str(e)
                            })
                
                # Update overall data consistency
                validation_results['data_consistency'] = all([
                    validation_results['row_count_match'],
                    validation_results['key_integrity'],
                    all(vr.get('passed', False) for vr in validation_results['custom_validation_results'])
                ])
                
                logger.info(f"Validation completed. Data consistent: {validation_results['data_consistency']}")
                return validation_results
                
        except Exception as e:
            logger.error(f"Data validation failed: {e}")
            validation_results['errors'].append(str(e))
            validation_results['data_consistency'] = False
            return validation_results
    
    async def create_data_backup(
        self,
        tables: List[str],
        backup_name: Optional[str] = None
    ) -> str:
        """
        Create data backup for specified tables
        
        Args:
            tables: List of table names to backup
            backup_name: Optional backup name
            
        Returns:
            Backup file path
        """
        if not backup_name:
            backup_name = f"data_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        backup_file = f"backups/data_{backup_name}.sql"
        backup_dir = Path("backups")
        backup_dir.mkdir(exist_ok=True)
        
        try:
            # Parse database URL for pg_dump
            from urllib.parse import urlparse
            parsed = urlparse(self.database_url.replace("+asyncpg", ""))
            
            # Use pg_dump to create backup
            import subprocess
            cmd = [
                'pg_dump',
                '-h', parsed.hostname,
                '-p', str(parsed.port),
                '-U', parsed.username,
                '-d', parsed.path[1:],  # Remove leading slash
                '-f', backup_file,
                '--data-only',  # Only backup data, not schema
                '--verbose'
            ]
            
            # Add table filters
            for table in tables:
                cmd.extend(['-t', table])
            
            # Set password via environment variable
            import os
            env = os.environ.copy()
            env['PGPASSWORD'] = parsed.password
            
            logger.info(f"Creating data backup: {backup_file}")
            result = subprocess.run(cmd, env=env, capture_output=True, text=True)
            
            if result.returncode == 0:
                logger.info(f"Data backup created successfully: {backup_file}")
                return backup_file
            else:
                logger.error(f"Data backup failed: {result.stderr}")
                raise Exception(f"Data backup failed: {result.stderr}")
                
        except Exception as e:
            logger.error(f"Error creating data backup: {e}")
            raise
    
    async def restore_data_backup(self, backup_file: str) -> bool:
        """
        Restore data from backup file
        
        Args:
            backup_file: Path to backup file
            
        Returns:
            True if successful, False otherwise
        """
        try:
            from urllib.parse import urlparse
            parsed = urlparse(self.database_url.replace("+asyncpg", ""))
            
            import subprocess
            cmd = [
                'psql',
                '-h', parsed.hostname,
                '-p', str(parsed.port),
                '-U', parsed.username,
                '-d', parsed.path[1:],
                '-f', backup_file,
                '--quiet'
            ]
            
            import os
            env = os.environ.copy()
            env['PGPASSWORD'] = parsed.password
            
            logger.info(f"Restoring data from backup: {backup_file}")
            result = subprocess.run(cmd, env=env, capture_output=True, text=True)
            
            if result.returncode == 0:
                logger.info("Data restored successfully")
                return True
            else:
                logger.error(f"Data restore failed: {result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"Error restoring data: {e}")
            return False
    
    async def transform_json_data(
        self,
        table_name: str,
        column_name: str,
        transformation_func: Callable[[Dict[str, Any]], Dict[str, Any]],
        where_clause: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Transform JSON data in a column
        
        Args:
            table_name: Table containing the JSON column
            column_name: Name of the JSON column
            transformation_func: Function to transform JSON data
            where_clause: Optional WHERE clause to filter rows
            
        Returns:
            Transformation statistics
        """
        logger.info(f"Transforming JSON data in {table_name}.{column_name}")
        
        stats = {
            'total_rows': 0,
            'transformed_rows': 0,
            'failed_rows': 0,
            'errors': []
        }
        
        try:
            async with self.get_session() as session:
                # Get rows with JSON data
                base_query = f"SELECT id, {column_name} FROM {table_name} WHERE {column_name} IS NOT NULL"
                if where_clause:
                    base_query += f" AND {where_clause}"
                
                result = await session.execute(text(base_query))
                rows = result.fetchall()
                stats['total_rows'] = len(rows)
                
                for row in rows:
                    try:
                        row_id = row[0]
                        json_data = row[1]
                        
                        # Parse JSON if it's a string
                        if isinstance(json_data, str):
                            json_data = json.loads(json_data)
                        
                        # Apply transformation
                        transformed_data = transformation_func(json_data)
                        
                        # Update the row
                        update_query = f"UPDATE {table_name} SET {column_name} = :data WHERE id = :id"
                        await session.execute(
                            text(update_query),
                            {'data': json.dumps(transformed_data), 'id': row_id}
                        )
                        
                        stats['transformed_rows'] += 1
                        
                    except Exception as e:
                        stats['failed_rows'] += 1
                        stats['errors'].append({
                            'row_id': row[0],
                            'error': str(e)
                        })
                        logger.warning(f"Failed to transform JSON data for row {row[0]}: {e}")
                
                await session.commit()
                
                logger.info(f"JSON transformation completed. Transformed: {stats['transformed_rows']}, Failed: {stats['failed_rows']}")
                return stats
                
        except Exception as e:
            logger.error(f"JSON transformation failed: {e}")
            stats['errors'].append(str(e))
            raise
    
    async def analyze_table_structure(self, table_name: str) -> Dict[str, Any]:
        """
        Analyze table structure and provide migration insights
        
        Args:
            table_name: Name of the table to analyze
            
        Returns:
            Table analysis results
        """
        logger.info(f"Analyzing table structure: {table_name}")
        
        analysis = {
            'table_name': table_name,
            'exists': False,
            'row_count': 0,
            'columns': [],
            'indexes': [],
            'constraints': [],
            'size_mb': 0,
            'recommendations': []
        }
        
        try:
            async with self.get_session() as session:
                # Check if table exists
                table_exists_query = """
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_schema = 'public' 
                        AND table_name = :table_name
                    )
                """
                result = await session.execute(text(table_exists_query), {'table_name': table_name})
                analysis['exists'] = result.scalar()
                
                if not analysis['exists']:
                    analysis['recommendations'].append(f"Table {table_name} does not exist")
                    return analysis
                
                # Get row count
                count_result = await session.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
                analysis['row_count'] = count_result.scalar()
                
                # Get column information
                columns_query = """
                    SELECT column_name, data_type, is_nullable, column_default
                    FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = :table_name
                    ORDER BY ordinal_position
                """
                columns_result = await session.execute(text(columns_query), {'table_name': table_name})
                analysis['columns'] = [dict(row._mapping) for row in columns_result.fetchall()]
                
                # Get index information
                indexes_query = """
                    SELECT indexname, indexdef
                    FROM pg_indexes
                    WHERE schemaname = 'public' AND tablename = :table_name
                """
                indexes_result = await session.execute(text(indexes_query), {'table_name': table_name})
                analysis['indexes'] = [dict(row._mapping) for row in indexes_result.fetchall()]
                
                # Get table size
                size_query = """
                    SELECT pg_size_pretty(pg_total_relation_size(:table_name)) as size,
                           pg_total_relation_size(:table_name) / 1024 / 1024 as size_mb
                """
                size_result = await session.execute(text(size_query), {'table_name': table_name})
                size_row = size_result.fetchone()
                analysis['size_mb'] = float(size_row[1]) if size_row[1] else 0
                
                # Generate recommendations
                if analysis['row_count'] > 1000000:
                    analysis['recommendations'].append("Large table - consider chunked migration")
                
                if analysis['size_mb'] > 1000:
                    analysis['recommendations'].append("Large table size - ensure adequate backup space")
                
                if len(analysis['indexes']) > 10:
                    analysis['recommendations'].append("Many indexes - migration may be slow")
                
                logger.info(f"Table analysis completed for {table_name}")
                return analysis
                
        except Exception as e:
            logger.error(f"Table analysis failed: {e}")
            analysis['recommendations'].append(f"Analysis failed: {str(e)}")
            return analysis
