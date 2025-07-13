#!/usr/bin/env python3
"""
Database Seeding Scripts
Populate database with initial and test data for different environments

Features:
- Environment-specific seed data
- Initial game configurations
- Test user accounts
- Reference data loading
- Bulk data operations optimized for performance
"""

import asyncio
import logging
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional
from uuid import uuid4, UUID

import asyncpg
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

# Add project root to path
import sys
sys.path.append(str(Path(__file__).parent.parent))

from backend.database.models import Base
from backend.database.config import DatabaseConfig, get_database_config

logger = logging.getLogger(__name__)


class DatabaseSeeder:
    """
    Database seeding orchestration for different environments
    """
    
    def __init__(self, environment: str = "development"):
        self.environment = environment
        self.config = get_database_config(environment)
        self.engine = None
        self.session_factory = None
        
    async def initialize(self):
        """Initialize database connection"""
        try:
            database_url = (
                f"postgresql+asyncpg://{self.config.username}:{self.config.password}"
                f"@{self.config.host}:{self.config.port}/{self.config.database}"
            )
            
            self.engine = create_async_engine(
                database_url,
                pool_size=self.config.pool_size,
                max_overflow=self.config.max_overflow,
                pool_timeout=self.config.pool_timeout,
                pool_recycle=self.config.pool_recycle,
                pool_pre_ping=self.config.pool_pre_ping,
                echo=self.config.echo_sql
            )
            
            self.session_factory = sessionmaker(
                bind=self.engine,
                class_=AsyncSession,
                expire_on_commit=False
            )
            
            logger.info(f"Database seeder initialized for {self.environment}")
            
        except Exception as e:
            logger.error(f"Failed to initialize database seeder: {e}")
            raise
    
    async def seed_all(self) -> Dict[str, Any]:
        """
        Run all seeding operations for the current environment
        """
        if not self.engine:
            await self.initialize()
            
        results = {
            'environment': self.environment,
            'started_at': datetime.utcnow().isoformat(),
            'operations': []
        }
        
        try:
            # 1. Seed reference data (always needed)
            reference_result = await self.seed_reference_data()
            results['operations'].append({
                'name': 'reference_data',
                'status': 'success',
                'records': reference_result['records_created'],
                'duration': reference_result['duration']
            })
            
            # 2. Environment-specific seeding
            if self.environment == "development":
                dev_result = await self.seed_development_data()
                results['operations'].append({
                    'name': 'development_data',
                    'status': 'success',
                    'records': dev_result['records_created'],
                    'duration': dev_result['duration']
                })
                
            elif self.environment == "testing":
                test_result = await self.seed_test_data()
                results['operations'].append({
                    'name': 'test_data',
                    'status': 'success',
                    'records': test_result['records_created'],
                    'duration': test_result['duration']
                })
                
            elif self.environment == "staging":
                staging_result = await self.seed_staging_data()
                results['operations'].append({
                    'name': 'staging_data',
                    'status': 'success',
                    'records': staging_result['records_created'],
                    'duration': staging_result['duration']
                })
                
            # Production gets minimal seeding (only reference data)
            
            results['completed_at'] = datetime.utcnow().isoformat()
            results['total_duration'] = sum(op['duration'] for op in results['operations'])
            results['status'] = 'success'
            
            logger.info(f"Database seeding completed for {self.environment}")
            return results
            
        except Exception as e:
            logger.error(f"Database seeding failed: {e}")
            results['status'] = 'failed'
            results['error'] = str(e)
            results['completed_at'] = datetime.utcnow().isoformat()
            raise
        
        finally:
            if self.engine:
                await self.engine.dispose()
    
    async def seed_reference_data(self) -> Dict[str, Any]:
        """
        Seed reference data needed for game operations
        """
        start_time = datetime.utcnow()
        records_created = 0
        
        async with self.session_factory() as session:
            try:
                # Game configurations
                game_configs = [
                    {
                        'id': str(uuid4()),
                        'name': 'Standard Hokm',
                        'max_players': 4,
                        'min_players': 4,
                        'rounds_to_win': 7,
                        'card_deal_size': 13,
                        'allow_reconnection': True,
                        'reconnection_timeout': 300,
                        'turn_timeout': 60,
                        'is_active': True
                    },
                    {
                        'id': str(uuid4()),
                        'name': 'Quick Hokm',
                        'max_players': 4,
                        'min_players': 4,
                        'rounds_to_win': 3,
                        'card_deal_size': 13,
                        'allow_reconnection': True,
                        'reconnection_timeout': 180,
                        'turn_timeout': 30,
                        'is_active': True
                    }
                ]
                
                for config in game_configs:
                    await session.execute(
                        text("""
                        INSERT INTO game_configurations 
                        (id, name, max_players, min_players, rounds_to_win, 
                         card_deal_size, allow_reconnection, reconnection_timeout, 
                         turn_timeout, is_active, created_at, updated_at)
                        VALUES 
                        (:id, :name, :max_players, :min_players, :rounds_to_win,
                         :card_deal_size, :allow_reconnection, :reconnection_timeout,
                         :turn_timeout, :is_active, NOW(), NOW())
                        ON CONFLICT (name) DO NOTHING
                        """),
                        config
                    )
                    records_created += 1
                
                # Card definitions (standard 52-card deck)
                suits = ['hearts', 'diamonds', 'clubs', 'spades']
                ranks = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
                
                for suit in suits:
                    for i, rank in enumerate(ranks):
                        card_data = {
                            'id': str(uuid4()),
                            'suit': suit,
                            'rank': rank,
                            'value': i + 2,  # 2-14 (Ace high)
                            'is_active': True
                        }
                        
                        await session.execute(
                            text("""
                            INSERT INTO cards (id, suit, rank, value, is_active, created_at, updated_at)
                            VALUES (:id, :suit, :rank, :value, :is_active, NOW(), NOW())
                            ON CONFLICT (suit, rank) DO NOTHING
                            """),
                            card_data
                        )
                        records_created += 1
                
                # Game status definitions
                game_statuses = [
                    {'name': 'waiting', 'description': 'Waiting for players'},
                    {'name': 'starting', 'description': 'Game starting'},
                    {'name': 'hakem_selection', 'description': 'Selecting trump suit'},
                    {'name': 'playing', 'description': 'Game in progress'},
                    {'name': 'round_complete', 'description': 'Round completed'},
                    {'name': 'game_complete', 'description': 'Game completed'},
                    {'name': 'paused', 'description': 'Game paused'},
                    {'name': 'cancelled', 'description': 'Game cancelled'}
                ]
                
                for status in game_statuses:
                    status['id'] = str(uuid4())
                    status['is_active'] = True
                    
                    await session.execute(
                        text("""
                        INSERT INTO game_statuses (id, name, description, is_active, created_at, updated_at)
                        VALUES (:id, :name, :description, :is_active, NOW(), NOW())
                        ON CONFLICT (name) DO NOTHING
                        """),
                        status
                    )
                    records_created += 1
                
                await session.commit()
                
                duration = (datetime.utcnow() - start_time).total_seconds()
                logger.info(f"Reference data seeded: {records_created} records in {duration:.2f}s")
                
                return {
                    'records_created': records_created,
                    'duration': duration
                }
                
            except Exception as e:
                await session.rollback()
                logger.error(f"Failed to seed reference data: {e}")
                raise
    
    async def seed_development_data(self) -> Dict[str, Any]:
        """
        Seed development environment with test users and games
        """
        start_time = datetime.utcnow()
        records_created = 0
        
        async with self.session_factory() as session:
            try:
                # Create test users
                test_users = [
                    {
                        'id': str(uuid4()),
                        'username': 'dev_player_1',
                        'email': 'dev1@example.com',
                        'password_hash': '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/lewdBenoznpXLsFof',  # 'password123'
                        'is_active': True,
                        'is_verified': True,
                        'rating': 1200,
                        'games_played': 0,
                        'games_won': 0
                    },
                    {
                        'id': str(uuid4()),
                        'username': 'dev_player_2',
                        'email': 'dev2@example.com',
                        'password_hash': '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/lewdBenoznpXLsFof',
                        'is_active': True,
                        'is_verified': True,
                        'rating': 1150,
                        'games_played': 0,
                        'games_won': 0
                    },
                    {
                        'id': str(uuid4()),
                        'username': 'dev_player_3',
                        'email': 'dev3@example.com',
                        'password_hash': '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/lewdBenoznpXLsFof',
                        'is_active': True,
                        'is_verified': True,
                        'rating': 1300,
                        'games_played': 0,
                        'games_won': 0
                    },
                    {
                        'id': str(uuid4()),
                        'username': 'dev_player_4',
                        'email': 'dev4@example.com',
                        'password_hash': '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/lewdBenoznpXLsFof',
                        'is_active': True,
                        'is_verified': True,
                        'rating': 1250,
                        'games_played': 0,
                        'games_won': 0
                    }
                ]
                
                for user in test_users:
                    await session.execute(
                        text("""
                        INSERT INTO users 
                        (id, username, email, password_hash, is_active, is_verified, 
                         rating, games_played, games_won, created_at, updated_at)
                        VALUES 
                        (:id, :username, :email, :password_hash, :is_active, :is_verified,
                         :rating, :games_played, :games_won, NOW(), NOW())
                        ON CONFLICT (username) DO NOTHING
                        """),
                        user
                    )
                    records_created += 1
                
                await session.commit()
                
                duration = (datetime.utcnow() - start_time).total_seconds()
                logger.info(f"Development data seeded: {records_created} records in {duration:.2f}s")
                
                return {
                    'records_created': records_created,
                    'duration': duration
                }
                
            except Exception as e:
                await session.rollback()
                logger.error(f"Failed to seed development data: {e}")
                raise
    
    async def seed_test_data(self) -> Dict[str, Any]:
        """
        Seed test environment with comprehensive test scenarios
        """
        start_time = datetime.utcnow()
        records_created = 0
        
        async with self.session_factory() as session:
            try:
                # Create test users with various scenarios
                test_scenarios = [
                    # Standard test users
                    {
                        'id': str(uuid4()),
                        'username': 'test_user_1',
                        'email': 'test1@test.com',
                        'password_hash': '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/lewdBenoznpXLsFof',
                        'is_active': True,
                        'is_verified': True,
                        'rating': 1000,
                        'games_played': 10,
                        'games_won': 5
                    },
                    # High-rated player
                    {
                        'id': str(uuid4()),
                        'username': 'test_expert',
                        'email': 'expert@test.com',
                        'password_hash': '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/lewdBenoznpXLsFof',
                        'is_active': True,
                        'is_verified': True,
                        'rating': 2000,
                        'games_played': 100,
                        'games_won': 75
                    },
                    # New player
                    {
                        'id': str(uuid4()),
                        'username': 'test_newbie',
                        'email': 'newbie@test.com',
                        'password_hash': '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/lewdBenoznpXLsFof',
                        'is_active': True,
                        'is_verified': True,
                        'rating': 800,
                        'games_played': 2,
                        'games_won': 0
                    },
                    # Inactive user (for testing edge cases)
                    {
                        'id': str(uuid4()),
                        'username': 'test_inactive',
                        'email': 'inactive@test.com',
                        'password_hash': '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/lewdBenoznpXLsFof',
                        'is_active': False,
                        'is_verified': True,
                        'rating': 1200,
                        'games_played': 50,
                        'games_won': 25
                    }
                ]
                
                for user in test_scenarios:
                    await session.execute(
                        text("""
                        INSERT INTO users 
                        (id, username, email, password_hash, is_active, is_verified, 
                         rating, games_played, games_won, created_at, updated_at)
                        VALUES 
                        (:id, :username, :email, :password_hash, :is_active, :is_verified,
                         :rating, :games_played, :games_won, NOW(), NOW())
                        ON CONFLICT (username) DO NOTHING
                        """),
                        user
                    )
                    records_created += 1
                
                await session.commit()
                
                duration = (datetime.utcnow() - start_time).total_seconds()
                logger.info(f"Test data seeded: {records_created} records in {duration:.2f}s")
                
                return {
                    'records_created': records_created,
                    'duration': duration
                }
                
            except Exception as e:
                await session.rollback()
                logger.error(f"Failed to seed test data: {e}")
                raise
    
    async def seed_staging_data(self) -> Dict[str, Any]:
        """
        Seed staging environment with production-like data
        """
        start_time = datetime.utcnow()
        records_created = 0
        
        async with self.session_factory() as session:
            try:
                # Create staging admin user
                admin_user = {
                    'id': str(uuid4()),
                    'username': 'staging_admin',
                    'email': 'admin@staging.hokm.com',
                    'password_hash': '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/lewdBenoznpXLsFof',
                    'is_active': True,
                    'is_verified': True,
                    'is_admin': True,
                    'rating': 1500,
                    'games_played': 0,
                    'games_won': 0
                }
                
                await session.execute(
                    text("""
                    INSERT INTO users 
                    (id, username, email, password_hash, is_active, is_verified, 
                     is_admin, rating, games_played, games_won, created_at, updated_at)
                    VALUES 
                    (:id, :username, :email, :password_hash, :is_active, :is_verified,
                     :is_admin, :rating, :games_played, :games_won, NOW(), NOW())
                    ON CONFLICT (username) DO NOTHING
                    """),
                    admin_user
                )
                records_created += 1
                
                await session.commit()
                
                duration = (datetime.utcnow() - start_time).total_seconds()
                logger.info(f"Staging data seeded: {records_created} records in {duration:.2f}s")
                
                return {
                    'records_created': records_created,
                    'duration': duration
                }
                
            except Exception as e:
                await session.rollback()
                logger.error(f"Failed to seed staging data: {e}")
                raise
    
    async def clear_all_data(self) -> Dict[str, Any]:
        """
        Clear all data from database (use with caution!)
        Only allowed in development and testing environments
        """
        if self.environment in ['production', 'staging']:
            raise ValueError(f"Data clearing not allowed in {self.environment} environment")
        
        start_time = datetime.utcnow()
        tables_cleared = 0
        
        async with self.session_factory() as session:
            try:
                # Get all table names
                result = await session.execute(
                    text("""
                    SELECT tablename FROM pg_tables 
                    WHERE schemaname = 'public' 
                    AND tablename != 'alembic_version'
                    ORDER BY tablename
                    """)
                )
                tables = [row[0] for row in result.fetchall()]
                
                # Disable foreign key checks temporarily
                await session.execute(text("SET session_replication_role = replica;"))
                
                # Truncate all tables
                for table in tables:
                    await session.execute(text(f"TRUNCATE TABLE {table} RESTART IDENTITY CASCADE;"))
                    tables_cleared += 1
                
                # Re-enable foreign key checks
                await session.execute(text("SET session_replication_role = DEFAULT;"))
                
                await session.commit()
                
                duration = (datetime.utcnow() - start_time).total_seconds()
                logger.info(f"Database cleared: {tables_cleared} tables in {duration:.2f}s")
                
                return {
                    'tables_cleared': tables_cleared,
                    'duration': duration
                }
                
            except Exception as e:
                await session.rollback()
                logger.error(f"Failed to clear database: {e}")
                raise


async def main():
    """
    Main entry point for database seeding
    """
    import argparse
    
    parser = argparse.ArgumentParser(description='Database Seeding Script')
    parser.add_argument(
        '--environment', '-e',
        choices=['development', 'testing', 'staging', 'production'],
        default='development',
        help='Target environment'
    )
    parser.add_argument(
        '--clear',
        action='store_true',
        help='Clear all data before seeding (dev/test only)'
    )
    parser.add_argument(
        '--reference-only',
        action='store_true',
        help='Only seed reference data'
    )
    
    args = parser.parse_args()
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    )
    
    seeder = DatabaseSeeder(args.environment)
    
    try:
        # Clear data if requested
        if args.clear:
            logger.info(f"Clearing database for {args.environment}")
            clear_result = await seeder.clear_all_data()
            logger.info(f"Database cleared: {clear_result}")
        
        # Seed data
        if args.reference_only:
            logger.info("Seeding reference data only")
            await seeder.initialize()
            result = await seeder.seed_reference_data()
        else:
            logger.info(f"Seeding database for {args.environment}")
            result = await seeder.seed_all()
        
        logger.info(f"Seeding completed successfully: {result}")
        
    except Exception as e:
        logger.error(f"Seeding failed: {e}")
        sys.exit(1)


if __name__ == '__main__':
    asyncio.run(main())
