#!/usr/bin/env python3
"""
Migration Load Testing Framework
Tests database migration performance and reliability under various load conditions
"""

import asyncio
import asyncpg
import json
import time
import logging
import random
import argparse
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict, deque
import concurrent.futures
from pathlib import Path
import statistics
import redis.asyncio as redis
import uuid
import traceback
from enum import Enum

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

class MigrationPhase(Enum):
    PREPARATION = "preparation"
    DATA_MIGRATION = "data_migration"
    VALIDATION = "validation"
    CUTOVER = "cutover"
    ROLLBACK = "rollback"

@dataclass
class MigrationMetrics:
    """Metrics specific to migration load testing"""
    # Migration timing
    phase_start_times: Dict[str, datetime] = field(default_factory=dict)
    phase_end_times: Dict[str, datetime] = field(default_factory=dict)
    phase_durations: Dict[str, float] = field(default_factory=dict)
    
    # Data consistency
    records_migrated: int = 0
    migration_errors: int = 0
    data_validation_failures: int = 0
    consistency_check_results: List[Dict[str, Any]] = field(default_factory=list)
    
    # Performance during migration
    read_latency_during_migration: deque = field(default_factory=lambda: deque(maxlen=1000))
    write_latency_during_migration: deque = field(default_factory=lambda: deque(maxlen=1000))
    migration_throughput: deque = field(default_factory=lambda: deque(maxlen=1000))
    
    # System impact
    cpu_impact: deque = field(default_factory=lambda: deque(maxlen=1000))
    memory_impact: deque = field(default_factory=lambda: deque(maxlen=1000))
    connection_pool_impact: deque = field(default_factory=lambda: deque(maxlen=1000))
    
    # User experience impact
    user_request_failures: int = 0
    user_request_timeouts: int = 0
    user_experience_degradation: List[Dict[str, Any]] = field(default_factory=list)

class MigrationLoadTester:
    """Load testing specifically for database migration scenarios"""
    
    def __init__(self, redis_config: Dict[str, Any], postgres_config: Dict[str, Any]):
        self.redis_config = redis_config
        self.postgres_config = postgres_config
        self.redis_client = None
        self.postgres_pool = None
        self.metrics = MigrationMetrics()
        self.test_data_keys = []
        
    async def setup(self):
        """Setup connections and test environment"""
        # Setup Redis connection
        self.redis_client = redis.Redis(**self.redis_config)
        
        # Setup PostgreSQL connection pool
        self.postgres_pool = await asyncpg.create_pool(**self.postgres_config)
        
        # Create test data
        await self._create_test_data()
        
    async def cleanup(self):
        """Cleanup connections and test data"""
        await self._cleanup_test_data()
        
        if self.redis_client:
            await self.redis_client.close()
        
        if self.postgres_pool:
            await self.postgres_pool.close()
    
    async def _create_test_data(self):
        """Create test data in Redis for migration"""
        logger.info("Creating test data for migration load testing")
        
        # Create game data
        for i in range(1000):
            game_id = f"migration_test_game_{i}"
            self.test_data_keys.append(f"game:{game_id}")
            
            game_data = {
                'game_id': game_id,
                'status': random.choice(['waiting', 'playing', 'completed']),
                'created_at': datetime.now().isoformat(),
                'players': [f"player_{j}" for j in range(4)],
                'current_phase': random.choice(['lobby', 'dealing', 'playing', 'scoring']),
                'scores': {f"player_{j}": random.randint(0, 100) for j in range(4)},
                'hand_history': [
                    {'hand': h, 'winner': f"player_{random.randint(0, 3)}", 'cards': []}
                    for h in range(random.randint(1, 13))
                ]
            }
            
            await self.redis_client.hset(f"game:{game_id}", mapping={
                k: json.dumps(v) if isinstance(v, (dict, list)) else str(v)
                for k, v in game_data.items()
            })
        
        # Create player data
        for i in range(400):
            player_id = f"migration_test_player_{i}"
            self.test_data_keys.append(f"player:{player_id}")
            
            player_data = {
                'player_id': player_id,
                'username': f"user_{i}",
                'total_games': random.randint(0, 100),
                'wins': random.randint(0, 50),
                'created_at': datetime.now().isoformat(),
                'last_active': datetime.now().isoformat(),
                'preferences': json.dumps({
                    'theme': random.choice(['light', 'dark']),
                    'notifications': random.choice([True, False])
                })
            }
            
            await self.redis_client.hset(f"player:{player_id}", mapping=player_data)
        
        # Create active session data
        for i in range(100):
            session_id = f"migration_test_session_{i}"
            self.test_data_keys.append(f"session:{session_id}")
            
            session_data = {
                'session_id': session_id,
                'player_id': f"migration_test_player_{i % 400}",
                'game_id': f"migration_test_game_{i % 1000}",
                'created_at': datetime.now().isoformat(),
                'last_activity': datetime.now().isoformat(),
                'connection_state': random.choice(['connected', 'disconnected', 'reconnecting'])
            }
            
            await self.redis_client.hset(f"session:{session_id}", mapping=session_data)
            await self.redis_client.expire(f"session:{session_id}", 3600)  # 1 hour TTL
        
        logger.info(f"Created {len(self.test_data_keys)} test records")
    
    async def _cleanup_test_data(self):
        """Clean up test data"""
        if self.redis_client:
            # Clean Redis data
            if self.test_data_keys:
                await self.redis_client.delete(*self.test_data_keys)
        
        if self.postgres_pool:
            # Clean PostgreSQL data
            async with self.postgres_pool.acquire() as conn:
                await conn.execute("DELETE FROM games WHERE game_id LIKE 'migration_test_%'")
                await conn.execute("DELETE FROM players WHERE player_id LIKE 'migration_test_%'")
                await conn.execute("DELETE FROM sessions WHERE session_id LIKE 'migration_test_%'")
    
    async def test_migration_under_load(self, concurrent_users: int = 50, migration_duration_minutes: int = 10) -> Dict[str, Any]:
        """Test migration performance while system is under load"""
        logger.info(f"Starting migration load test with {concurrent_users} concurrent users for {migration_duration_minutes} minutes")
        
        # Start user load simulation
        user_tasks = []
        for i in range(concurrent_users):
            task = asyncio.create_task(self._simulate_user_activity(f"load_user_{i}", migration_duration_minutes * 60))
            user_tasks.append(task)
        
        # Wait a bit for user load to ramp up
        await asyncio.sleep(5)
        
        # Start migration phases
        migration_task = asyncio.create_task(self._simulate_migration_phases())
        
        # Wait for migration to complete
        await migration_task
        
        # Stop user load
        for task in user_tasks:
            task.cancel()
        
        await asyncio.gather(*user_tasks, return_exceptions=True)
        
        return self._generate_migration_report()
    
    async def _simulate_user_activity(self, user_id: str, duration_seconds: int):
        """Simulate user activity during migration"""
        start_time = time.time()
        end_time = start_time + duration_seconds
        
        while time.time() < end_time:
            try:
                # Simulate typical user operations
                operation = random.choice([
                    self._user_read_operation,
                    self._user_write_operation,
                    self._user_game_join_operation,
                    self._user_game_action_operation
                ])
                
                operation_start = time.time()
                await operation(user_id)
                operation_time = (time.time() - operation_start) * 1000
                
                # Track latency during migration
                if hasattr(self, '_migration_active') and self._migration_active:
                    if 'read' in operation.__name__:
                        self.metrics.read_latency_during_migration.append(operation_time)
                    else:
                        self.metrics.write_latency_during_migration.append(operation_time)
                
                # Brief pause between operations
                await asyncio.sleep(random.uniform(0.1, 1.0))
                
            except Exception as e:
                logger.debug(f"User {user_id} operation error: {e}")
                if hasattr(self, '_migration_active') and self._migration_active:
                    self.metrics.user_request_failures += 1
                    
                    # Check if this is due to migration impact
                    if 'timeout' in str(e).lower():
                        self.metrics.user_request_timeouts += 1
                    
                    self.metrics.user_experience_degradation.append({
                        'timestamp': datetime.now(),
                        'user_id': user_id,
                        'error': str(e),
                        'operation': operation.__name__
                    })
    
    async def _user_read_operation(self, user_id: str):
        """Simulate user read operation"""
        # Try both Redis and PostgreSQL (depending on migration phase)
        game_id = f"migration_test_game_{random.randint(0, 999)}"
        
        # Read from Redis first
        redis_data = await self.redis_client.hgetall(f"game:{game_id}")
        
        # If migration is in progress, also try PostgreSQL
        if hasattr(self, '_migration_active') and self._migration_active:
            try:
                async with self.postgres_pool.acquire() as conn:
                    pg_data = await conn.fetchrow("SELECT * FROM games WHERE game_id = $1", game_id)
            except Exception as e:
                logger.debug(f"PostgreSQL read error during migration: {e}")
    
    async def _user_write_operation(self, user_id: str):
        """Simulate user write operation"""
        game_id = f"migration_test_game_{random.randint(0, 999)}"
        
        # Update in Redis
        await self.redis_client.hset(f"game:{game_id}", 'last_updated', datetime.now().isoformat())
        
        # If migration is in progress, also update PostgreSQL
        if hasattr(self, '_migration_active') and self._migration_active:
            try:
                async with self.postgres_pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE games SET updated_at = NOW() WHERE game_id = $1", 
                        game_id
                    )
            except Exception as e:
                logger.debug(f"PostgreSQL write error during migration: {e}")
    
    async def _user_game_join_operation(self, user_id: str):
        """Simulate user joining a game"""
        player_id = f"migration_test_player_{random.randint(0, 399)}"
        
        # Check player data from both sources
        redis_player = await self.redis_client.hgetall(f"player:{player_id}")
        
        if hasattr(self, '_migration_active') and self._migration_active:
            try:
                async with self.postgres_pool.acquire() as conn:
                    pg_player = await conn.fetchrow("SELECT * FROM players WHERE player_id = $1", player_id)
            except Exception:
                pass
    
    async def _user_game_action_operation(self, user_id: str):
        """Simulate user game action"""
        session_id = f"migration_test_session_{random.randint(0, 99)}"
        
        # Update session activity
        await self.redis_client.hset(f"session:{session_id}", 'last_activity', datetime.now().isoformat())
    
    async def _simulate_migration_phases(self):
        """Simulate the actual migration process"""
        self._migration_active = True
        phases = [
            MigrationPhase.PREPARATION,
            MigrationPhase.DATA_MIGRATION,
            MigrationPhase.VALIDATION,
            MigrationPhase.CUTOVER
        ]
        
        try:
            for phase in phases:
                await self._execute_migration_phase(phase)
        except Exception as e:
            logger.error(f"Migration failed, executing rollback: {e}")
            await self._execute_migration_phase(MigrationPhase.ROLLBACK)
        finally:
            self._migration_active = False
    
    async def _execute_migration_phase(self, phase: MigrationPhase):
        """Execute a specific migration phase"""
        phase_name = phase.value
        logger.info(f"Starting migration phase: {phase_name}")
        
        start_time = datetime.now()
        self.metrics.phase_start_times[phase_name] = start_time
        
        try:
            if phase == MigrationPhase.PREPARATION:
                await self._migration_preparation()
            elif phase == MigrationPhase.DATA_MIGRATION:
                await self._migration_data_transfer()
            elif phase == MigrationPhase.VALIDATION:
                await self._migration_validation()
            elif phase == MigrationPhase.CUTOVER:
                await self._migration_cutover()
            elif phase == MigrationPhase.ROLLBACK:
                await self._migration_rollback()
                
        except Exception as e:
            logger.error(f"Migration phase {phase_name} failed: {e}")
            self.metrics.migration_errors += 1
            raise
        finally:
            end_time = datetime.now()
            self.metrics.phase_end_times[phase_name] = end_time
            duration = (end_time - start_time).total_seconds()
            self.metrics.phase_durations[phase_name] = duration
            
            logger.info(f"Migration phase {phase_name} completed in {duration:.2f} seconds")
    
    async def _migration_preparation(self):
        """Prepare for migration"""
        # Create PostgreSQL tables if they don't exist
        async with self.postgres_pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS games (
                    game_id VARCHAR(255) PRIMARY KEY,
                    status VARCHAR(50),
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW(),
                    current_phase VARCHAR(50),
                    player_count INTEGER DEFAULT 0,
                    game_data JSONB
                )
            """)
            
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS players (
                    player_id VARCHAR(255) PRIMARY KEY,
                    username VARCHAR(255),
                    total_games INTEGER DEFAULT 0,
                    wins INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW(),
                    player_data JSONB
                )
            """)
            
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id VARCHAR(255) PRIMARY KEY,
                    player_id VARCHAR(255),
                    game_id VARCHAR(255),
                    created_at TIMESTAMP DEFAULT NOW(),
                    last_activity TIMESTAMP DEFAULT NOW(),
                    connection_state VARCHAR(50),
                    session_data JSONB
                )
            """)
        
        # Brief delay to simulate preparation work
        await asyncio.sleep(2)
    
    async def _migration_data_transfer(self):
        """Transfer data from Redis to PostgreSQL"""
        batch_size = 50
        migrated_count = 0
        
        # Migrate games
        for i in range(0, 1000, batch_size):
            batch_data = []
            for j in range(i, min(i + batch_size, 1000)):
                game_id = f"migration_test_game_{j}"
                redis_data = await self.redis_client.hgetall(f"game:{game_id}")
                
                if redis_data:
                    batch_data.append((
                        game_id,
                        redis_data.get(b'status', b'').decode(),
                        redis_data.get(b'current_phase', b'').decode(),
                        len(json.loads(redis_data.get(b'players', b'[]').decode())),
                        json.dumps({k.decode(): v.decode() for k, v in redis_data.items()})
                    ))
            
            if batch_data:
                async with self.postgres_pool.acquire() as conn:
                    await conn.executemany("""
                        INSERT INTO games (game_id, status, current_phase, player_count, game_data)
                        VALUES ($1, $2, $3, $4, $5)
                        ON CONFLICT (game_id) DO UPDATE SET
                            status = EXCLUDED.status,
                            current_phase = EXCLUDED.current_phase,
                            player_count = EXCLUDED.player_count,
                            game_data = EXCLUDED.game_data,
                            updated_at = NOW()
                    """, batch_data)
                
                migrated_count += len(batch_data)
                self.metrics.records_migrated += len(batch_data)
                self.metrics.migration_throughput.append(len(batch_data))
            
            # Brief pause between batches
            await asyncio.sleep(0.1)
        
        # Migrate players
        for i in range(0, 400, batch_size):
            batch_data = []
            for j in range(i, min(i + batch_size, 400)):
                player_id = f"migration_test_player_{j}"
                redis_data = await self.redis_client.hgetall(f"player:{player_id}")
                
                if redis_data:
                    batch_data.append((
                        player_id,
                        redis_data.get(b'username', b'').decode(),
                        int(redis_data.get(b'total_games', b'0').decode() or 0),
                        int(redis_data.get(b'wins', b'0').decode() or 0),
                        json.dumps({k.decode(): v.decode() for k, v in redis_data.items()})
                    ))
            
            if batch_data:
                async with self.postgres_pool.acquire() as conn:
                    await conn.executemany("""
                        INSERT INTO players (player_id, username, total_games, wins, player_data)
                        VALUES ($1, $2, $3, $4, $5)
                        ON CONFLICT (player_id) DO UPDATE SET
                            username = EXCLUDED.username,
                            total_games = EXCLUDED.total_games,
                            wins = EXCLUDED.wins,
                            player_data = EXCLUDED.player_data,
                            updated_at = NOW()
                    """, batch_data)
                
                migrated_count += len(batch_data)
                self.metrics.records_migrated += len(batch_data)
            
            await asyncio.sleep(0.1)
        
        logger.info(f"Migrated {migrated_count} records to PostgreSQL")
    
    async def _migration_validation(self):
        """Validate migrated data"""
        validation_errors = 0
        
        # Sample validation of games
        for i in range(0, 100, 10):  # Sample every 10th game
            game_id = f"migration_test_game_{i}"
            
            # Get data from both sources
            redis_data = await self.redis_client.hgetall(f"game:{game_id}")
            
            async with self.postgres_pool.acquire() as conn:
                pg_data = await conn.fetchrow("SELECT * FROM games WHERE game_id = $1", game_id)
            
            # Compare key fields
            if redis_data and pg_data:
                redis_status = redis_data.get(b'status', b'').decode()
                pg_status = pg_data['status']
                
                if redis_status != pg_status:
                    validation_errors += 1
                    self.metrics.consistency_check_results.append({
                        'timestamp': datetime.now(),
                        'record_type': 'game',
                        'record_id': game_id,
                        'field': 'status',
                        'redis_value': redis_status,
                        'postgres_value': pg_status,
                        'consistent': False
                    })
                else:
                    self.metrics.consistency_check_results.append({
                        'timestamp': datetime.now(),
                        'record_type': 'game',
                        'record_id': game_id,
                        'consistent': True
                    })
        
        self.metrics.data_validation_failures = validation_errors
        
        if validation_errors > 0:
            logger.warning(f"Found {validation_errors} validation errors")
        else:
            logger.info("Data validation passed")
    
    async def _migration_cutover(self):
        """Perform migration cutover"""
        # Simulate switching read/write operations to PostgreSQL
        logger.info("Performing migration cutover")
        
        # Brief delay to simulate cutover process
        await asyncio.sleep(3)
        
        logger.info("Cutover completed - system now using PostgreSQL")
    
    async def _migration_rollback(self):
        """Perform migration rollback"""
        logger.info("Performing migration rollback")
        
        # Simulate rollback process
        async with self.postgres_pool.acquire() as conn:
            await conn.execute("DELETE FROM games WHERE game_id LIKE 'migration_test_%'")
            await conn.execute("DELETE FROM players WHERE player_id LIKE 'migration_test_%'")
            await conn.execute("DELETE FROM sessions WHERE session_id LIKE 'migration_test_%'")
        
        await asyncio.sleep(2)
        logger.info("Rollback completed - system reverted to Redis")
    
    def _generate_migration_report(self) -> Dict[str, Any]:
        """Generate comprehensive migration test report"""
        report = {
            'migration_summary': {
                'total_duration': sum(self.metrics.phase_durations.values()),
                'phase_durations': dict(self.metrics.phase_durations),
                'records_migrated': self.metrics.records_migrated,
                'migration_errors': self.metrics.migration_errors,
                'validation_failures': self.metrics.data_validation_failures
            },
            'performance_impact': {
                'avg_read_latency_during_migration': statistics.mean(self.metrics.read_latency_during_migration) if self.metrics.read_latency_during_migration else 0,
                'avg_write_latency_during_migration': statistics.mean(self.metrics.write_latency_during_migration) if self.metrics.write_latency_during_migration else 0,
                'p95_read_latency': statistics.quantiles(self.metrics.read_latency_during_migration, n=20)[18] if len(self.metrics.read_latency_during_migration) > 20 else 0,
                'p95_write_latency': statistics.quantiles(self.metrics.write_latency_during_migration, n=20)[18] if len(self.metrics.write_latency_during_migration) > 20 else 0,
                'migration_throughput_avg': statistics.mean(self.metrics.migration_throughput) if self.metrics.migration_throughput else 0
            },
            'user_experience_impact': {
                'request_failures': self.metrics.user_request_failures,
                'request_timeouts': self.metrics.user_request_timeouts,
                'degradation_events': len(self.metrics.user_experience_degradation),
                'failure_rate': self.metrics.user_request_failures / max(sum([len(self.metrics.read_latency_during_migration), len(self.metrics.write_latency_during_migration)]), 1)
            },
            'data_consistency': {
                'validation_checks': len(self.metrics.consistency_check_results),
                'consistent_records': len([r for r in self.metrics.consistency_check_results if r.get('consistent', False)]),
                'inconsistent_records': len([r for r in self.metrics.consistency_check_results if not r.get('consistent', True)]),
                'consistency_rate': len([r for r in self.metrics.consistency_check_results if r.get('consistent', False)]) / max(len(self.metrics.consistency_check_results), 1)
            },
            'recommendations': self._generate_migration_recommendations()
        }
        
        return report
    
    def _generate_migration_recommendations(self) -> List[Dict[str, str]]:
        """Generate migration-specific recommendations"""
        recommendations = []
        
        # Performance recommendations
        if self.metrics.read_latency_during_migration and statistics.mean(self.metrics.read_latency_during_migration) > 100:
            recommendations.append({
                'category': 'Performance',
                'priority': 'High',
                'recommendation': 'Consider implementing read replicas to reduce read latency during migration',
                'rationale': f'Average read latency during migration: {statistics.mean(self.metrics.read_latency_during_migration):.2f}ms'
            })
        
        # User experience recommendations
        failure_rate = self.metrics.user_request_failures / max(len(self.metrics.read_latency_during_migration) + len(self.metrics.write_latency_during_migration), 1)
        if failure_rate > 0.01:  # More than 1% failure rate
            recommendations.append({
                'category': 'User Experience',
                'priority': 'High',
                'recommendation': 'Implement circuit breakers and graceful degradation during migration',
                'rationale': f'Request failure rate during migration: {failure_rate:.2%}'
            })
        
        # Data consistency recommendations
        consistency_rate = len([r for r in self.metrics.consistency_check_results if r.get('consistent', False)]) / max(len(self.metrics.consistency_check_results), 1)
        if consistency_rate < 0.99:  # Less than 99% consistency
            recommendations.append({
                'category': 'Data Consistency',
                'priority': 'Critical',
                'recommendation': 'Implement more robust data validation and synchronization mechanisms',
                'rationale': f'Data consistency rate: {consistency_rate:.2%}'
            })
        
        # Migration timing recommendations
        total_duration = sum(self.metrics.phase_durations.values())
        if total_duration > 300:  # More than 5 minutes
            recommendations.append({
                'category': 'Migration Timing',
                'priority': 'Medium',
                'recommendation': 'Consider breaking migration into smaller, incremental steps',
                'rationale': f'Total migration duration: {total_duration:.1f} seconds'
            })
        
        # Throughput recommendations
        if self.metrics.migration_throughput and statistics.mean(self.metrics.migration_throughput) < 10:
            recommendations.append({
                'category': 'Migration Throughput',
                'priority': 'Medium',
                'recommendation': 'Increase batch size and parallel processing for data migration',
                'rationale': f'Average migration throughput: {statistics.mean(self.metrics.migration_throughput):.1f} records/batch'
            })
        
        return recommendations

async def main():
    """Main function for migration load testing"""
    parser = argparse.ArgumentParser(description='Migration Load Testing for Hokm Game Server')
    parser.add_argument('--redis-host', default='localhost', help='Redis host')
    parser.add_argument('--redis-port', type=int, default=6379, help='Redis port')
    parser.add_argument('--postgres-host', default='localhost', help='PostgreSQL host')
    parser.add_argument('--postgres-port', type=int, default=5432, help='PostgreSQL port')
    parser.add_argument('--postgres-db', default='hokm_game', help='PostgreSQL database')
    parser.add_argument('--postgres-user', default='postgres', help='PostgreSQL user')
    parser.add_argument('--postgres-password', default='password', help='PostgreSQL password')
    parser.add_argument('--concurrent-users', type=int, default=50, help='Number of concurrent users')
    parser.add_argument('--duration', type=int, default=10, help='Test duration in minutes')
    parser.add_argument('--output', default='migration_load_test_report.json', help='Output file')
    parser.add_argument('--verbose', action='store_true', help='Enable verbose logging')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    redis_config = {
        'host': args.redis_host,
        'port': args.redis_port,
        'decode_responses': False
    }
    
    postgres_config = {
        'host': args.postgres_host,
        'port': args.postgres_port,
        'database': args.postgres_db,
        'user': args.postgres_user,
        'password': args.postgres_password
    }
    
    tester = MigrationLoadTester(redis_config, postgres_config)
    
    try:
        await tester.setup()
        report = await tester.test_migration_under_load(args.concurrent_users, args.duration)
        
        # Save report
        with open(args.output, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        
        # Print summary
        print(f"\nMigration Load Test Complete!")
        print(f"Migration Duration: {report['migration_summary']['total_duration']:.2f} seconds")
        print(f"Records Migrated: {report['migration_summary']['records_migrated']}")
        print(f"Migration Errors: {report['migration_summary']['migration_errors']}")
        print(f"User Request Failures: {report['user_experience_impact']['request_failures']}")
        print(f"Data Consistency Rate: {report['data_consistency']['consistency_rate']:.2%}")
        print(f"Report saved to: {args.output}")
        
        # Print key recommendations
        if report['recommendations']:
            print("\nKey Recommendations:")
            for rec in report['recommendations'][:3]:
                print(f"- [{rec['priority']}] {rec['recommendation']}")
    
    except Exception as e:
        logger.error(f"Migration load test failed: {e}")
        logger.error(traceback.format_exc())
        sys.exit(1)
    finally:
        await tester.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
