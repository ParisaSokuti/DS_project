#!/usr/bin/env python3
"""
PostgreSQL-Focused Load Testing Framework for Hokm Game Server
Comprehensive testing of database performance, connection pooling, and query optimization
"""

import asyncio
import asyncpg
import aiohttp
import websockets
import json
import time
import logging
import random
import argparse
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple, Set
from dataclasses import dataclass, field
from collections import defaultdict, deque
import psutil
import concurrent.futures
from pathlib import Path
import statistics
import redis.asyncio as redis
from contextlib import asynccontextmanager
import uuid
import traceback

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

@dataclass
class PostgreSQLMetrics:
    """PostgreSQL-specific performance metrics"""
    # Connection pool metrics
    pool_size: int = 0
    active_connections: deque = field(default_factory=lambda: deque(maxlen=1000))
    idle_connections: deque = field(default_factory=lambda: deque(maxlen=1000))
    connection_waits: deque = field(default_factory=lambda: deque(maxlen=1000))
    connection_timeouts: int = 0
    
    # Query performance metrics
    query_times_by_type: Dict[str, deque] = field(default_factory=lambda: defaultdict(lambda: deque(maxlen=1000)))
    slow_queries: List[Dict[str, Any]] = field(default_factory=list)
    query_counts_by_type: Dict[str, int] = field(default_factory=dict)
    failed_queries: Dict[str, int] = field(default_factory=dict)
    
    # Transaction metrics
    transaction_times: deque = field(default_factory=lambda: deque(maxlen=1000))
    transaction_rollbacks: int = 0
    transaction_deadlocks: int = 0
    
    # Lock contention metrics
    lock_waits: deque = field(default_factory=lambda: deque(maxlen=1000))
    lock_timeouts: int = 0
    blocking_queries: List[Dict[str, Any]] = field(default_factory=list)
    
    # Index usage metrics
    index_hits: int = 0
    index_misses: int = 0
    sequential_scans: int = 0
    
    # Buffer cache metrics
    buffer_hits: deque = field(default_factory=lambda: deque(maxlen=1000))
    buffer_misses: deque = field(default_factory=lambda: deque(maxlen=1000))
    
    # Database size metrics
    database_size_mb: deque = field(default_factory=lambda: deque(maxlen=100))
    table_sizes: Dict[str, deque] = field(default_factory=lambda: defaultdict(lambda: deque(maxlen=100)))

@dataclass
class DatabaseLoadProfile:
    """Defines database load patterns for testing"""
    concurrent_connections: int = 50
    queries_per_second_target: int = 1000
    read_write_ratio: float = 0.7  # 70% reads, 30% writes
    transaction_size_range: Tuple[int, int] = (1, 5)  # queries per transaction
    batch_operation_probability: float = 0.1  # 10% chance of batch operations
    complex_query_probability: float = 0.05  # 5% chance of complex queries
    concurrent_user_actions: int = 100  # simultaneous user actions
    data_volume_multiplier: float = 1.0  # scale test data volume

class PostgreSQLMonitor:
    """Monitors PostgreSQL performance metrics during load testing"""
    
    def __init__(self, db_config: Dict[str, Any]):
        self.db_config = db_config
        self.monitoring_pool = None
        self.metrics = PostgreSQLMetrics()
        self.monitoring_active = False
        
    async def start_monitoring(self):
        """Start monitoring PostgreSQL metrics"""
        self.monitoring_pool = await asyncpg.create_pool(
            **self.db_config,
            min_size=2,
            max_size=5,
            command_timeout=30
        )
        self.monitoring_active = True
        
        # Start monitoring tasks
        await asyncio.gather(
            self._monitor_connections(),
            self._monitor_queries(),
            self._monitor_locks(),
            self._monitor_buffer_cache(),
            self._monitor_database_size(),
            return_exceptions=True
        )
    
    async def stop_monitoring(self):
        """Stop monitoring and cleanup"""
        self.monitoring_active = False
        if self.monitoring_pool:
            await self.monitoring_pool.close()
    
    async def _monitor_connections(self):
        """Monitor connection pool statistics"""
        while self.monitoring_active:
            try:
                async with self.monitoring_pool.acquire() as conn:
                    # Get connection statistics
                    result = await conn.fetch("""
                        SELECT 
                            state,
                            COUNT(*) as count
                        FROM pg_stat_activity 
                        WHERE datname = $1
                        GROUP BY state
                    """, self.db_config['database'])
                    
                    active_count = 0
                    idle_count = 0
                    
                    for row in result:
                        if row['state'] == 'active':
                            active_count = row['count']
                        elif row['state'] == 'idle':
                            idle_count = row['count']
                    
                    self.metrics.active_connections.append(active_count)
                    self.metrics.idle_connections.append(idle_count)
                    
            except Exception as e:
                logger.warning(f"Connection monitoring error: {e}")
            
            await asyncio.sleep(1)
    
    async def _monitor_queries(self):
        """Monitor query performance and statistics"""
        while self.monitoring_active:
            try:
                async with self.monitoring_pool.acquire() as conn:
                    # Get slow queries
                    slow_queries = await conn.fetch("""
                        SELECT 
                            query,
                            calls,
                            total_time,
                            mean_time,
                            max_time,
                            stddev_time
                        FROM pg_stat_statements 
                        WHERE mean_time > 100
                        ORDER BY mean_time DESC 
                        LIMIT 10
                    """)
                    
                    for query in slow_queries:
                        self.metrics.slow_queries.append({
                            'timestamp': datetime.now(),
                            'query': query['query'][:200],  # Truncate for storage
                            'calls': query['calls'],
                            'total_time': query['total_time'],
                            'mean_time': query['mean_time'],
                            'max_time': query['max_time']
                        })
                    
                    # Get query type statistics
                    stats = await conn.fetch("""
                        SELECT 
                            CASE 
                                WHEN query ILIKE 'SELECT%' THEN 'SELECT'
                                WHEN query ILIKE 'INSERT%' THEN 'INSERT'
                                WHEN query ILIKE 'UPDATE%' THEN 'UPDATE'
                                WHEN query ILIKE 'DELETE%' THEN 'DELETE'
                                ELSE 'OTHER'
                            END as query_type,
                            SUM(calls) as total_calls,
                            AVG(mean_time) as avg_time
                        FROM pg_stat_statements 
                        GROUP BY 1
                    """)
                    
                    for stat in stats:
                        query_type = stat['query_type']
                        self.metrics.query_counts_by_type[query_type] = stat['total_calls']
                        if stat['avg_time']:
                            self.metrics.query_times_by_type[query_type].append(stat['avg_time'])
                    
            except Exception as e:
                logger.warning(f"Query monitoring error: {e}")
            
            await asyncio.sleep(5)
    
    async def _monitor_locks(self):
        """Monitor lock contention and blocking queries"""
        while self.monitoring_active:
            try:
                async with self.monitoring_pool.acquire() as conn:
                    # Get blocking queries
                    blocking = await conn.fetch("""
                        SELECT 
                            blocked_locks.pid AS blocked_pid,
                            blocked_activity.usename AS blocked_user,
                            blocking_locks.pid AS blocking_pid,
                            blocking_activity.usename AS blocking_user,
                            blocked_activity.query AS blocked_statement,
                            blocking_activity.query AS blocking_statement,
                            blocked_activity.application_name AS blocked_application
                        FROM pg_catalog.pg_locks blocked_locks
                        JOIN pg_catalog.pg_stat_activity blocked_activity 
                            ON blocked_activity.pid = blocked_locks.pid
                        JOIN pg_catalog.pg_locks blocking_locks 
                            ON blocking_locks.locktype = blocked_locks.locktype
                            AND blocking_locks.DATABASE IS NOT DISTINCT FROM blocked_locks.DATABASE
                            AND blocking_locks.relation IS NOT DISTINCT FROM blocked_locks.relation
                            AND blocking_locks.page IS NOT DISTINCT FROM blocked_locks.page
                            AND blocking_locks.tuple IS NOT DISTINCT FROM blocked_locks.tuple
                            AND blocking_locks.virtualxid IS NOT DISTINCT FROM blocked_locks.virtualxid
                            AND blocking_locks.transactionid IS NOT DISTINCT FROM blocked_locks.transactionid
                            AND blocking_locks.classid IS NOT DISTINCT FROM blocked_locks.classid
                            AND blocking_locks.objid IS NOT DISTINCT FROM blocked_locks.objid
                            AND blocking_locks.objsubid IS NOT DISTINCT FROM blocked_locks.objsubid
                            AND blocking_locks.pid != blocked_locks.pid
                        JOIN pg_catalog.pg_stat_activity blocking_activity 
                            ON blocking_activity.pid = blocking_locks.pid
                        WHERE NOT blocked_locks.GRANTED
                    """)
                    
                    for block in blocking:
                        self.metrics.blocking_queries.append({
                            'timestamp': datetime.now(),
                            'blocked_pid': block['blocked_pid'],
                            'blocking_pid': block['blocking_pid'],
                            'blocked_query': block['blocked_statement'][:200],
                            'blocking_query': block['blocking_statement'][:200]
                        })
                    
                    # Get lock wait statistics
                    lock_stats = await conn.fetchrow("""
                        SELECT 
                            SUM(blks_hit) as buffer_hits,
                            SUM(blks_read) as buffer_misses
                        FROM pg_stat_database 
                        WHERE datname = $1
                    """, self.db_config['database'])
                    
                    if lock_stats:
                        self.metrics.buffer_hits.append(lock_stats['buffer_hits'] or 0)
                        self.metrics.buffer_misses.append(lock_stats['buffer_misses'] or 0)
                    
            except Exception as e:
                logger.warning(f"Lock monitoring error: {e}")
            
            await asyncio.sleep(2)
    
    async def _monitor_buffer_cache(self):
        """Monitor buffer cache hit ratio and efficiency"""
        while self.monitoring_active:
            try:
                async with self.monitoring_pool.acquire() as conn:
                    result = await conn.fetchrow("""
                        SELECT 
                            SUM(heap_blks_hit) as heap_hit,
                            SUM(heap_blks_read) as heap_read,
                            SUM(idx_blks_hit) as idx_hit,
                            SUM(idx_blks_read) as idx_read
                        FROM pg_statio_user_tables
                    """)
                    
                    if result:
                        total_hit = (result['heap_hit'] or 0) + (result['idx_hit'] or 0)
                        total_read = (result['heap_read'] or 0) + (result['idx_read'] or 0)
                        
                        self.metrics.index_hits += result['idx_hit'] or 0
                        self.metrics.index_misses += result['idx_read'] or 0
                        
                        if total_hit + total_read > 0:
                            hit_ratio = total_hit / (total_hit + total_read)
                            self.metrics.buffer_hits.append(hit_ratio)
                    
            except Exception as e:
                logger.warning(f"Buffer cache monitoring error: {e}")
            
            await asyncio.sleep(10)
    
    async def _monitor_database_size(self):
        """Monitor database and table sizes"""
        while self.monitoring_active:
            try:
                async with self.monitoring_pool.acquire() as conn:
                    # Get database size
                    db_size = await conn.fetchrow("""
                        SELECT pg_database_size($1) / 1024 / 1024 as size_mb
                    """, self.db_config['database'])
                    
                    if db_size:
                        self.metrics.database_size_mb.append(db_size['size_mb'])
                    
                    # Get table sizes
                    table_sizes = await conn.fetch("""
                        SELECT 
                            schemaname,
                            tablename,
                            pg_total_relation_size(schemaname||'.'||tablename) / 1024 / 1024 as size_mb
                        FROM pg_tables 
                        WHERE schemaname = 'public'
                    """)
                    
                    for table in table_sizes:
                        table_name = table['tablename']
                        size_mb = table['size_mb']
                        self.metrics.table_sizes[table_name].append(size_mb)
                    
            except Exception as e:
                logger.warning(f"Database size monitoring error: {e}")
            
            await asyncio.sleep(30)

class DatabaseLoadTester:
    """Generates realistic database load for testing"""
    
    def __init__(self, db_config: Dict[str, Any], load_profile: DatabaseLoadProfile):
        self.db_config = db_config
        self.load_profile = load_profile
        self.connection_pool = None
        self.test_data_ids = []
        
    async def setup(self):
        """Setup database connection pool and test data"""
        self.connection_pool = await asyncpg.create_pool(
            **self.db_config,
            min_size=self.load_profile.concurrent_connections // 2,
            max_size=self.load_profile.concurrent_connections,
            command_timeout=60
        )
        
        await self._create_test_data()
    
    async def cleanup(self):
        """Cleanup resources and test data"""
        await self._cleanup_test_data()
        if self.connection_pool:
            await self.connection_pool.close()
    
    async def _create_test_data(self):
        """Create test data for load testing"""
        try:
            async with self.connection_pool.acquire() as conn:
                # Create test games
                for i in range(int(100 * self.load_profile.data_volume_multiplier)):
                    game_id = f"load_test_game_{uuid.uuid4().hex[:8]}"
                    self.test_data_ids.append(game_id)
                    
                    await conn.execute("""
                        INSERT INTO games (game_id, created_at, status, current_phase)
                        VALUES ($1, NOW(), 'waiting', 'lobby')
                        ON CONFLICT (game_id) DO NOTHING
                    """, game_id)
                
                # Create test players
                for i in range(int(400 * self.load_profile.data_volume_multiplier)):
                    player_id = f"load_test_player_{uuid.uuid4().hex[:8]}"
                    
                    await conn.execute("""
                        INSERT INTO players (player_id, created_at, total_games, wins)
                        VALUES ($1, NOW(), $2, $3)
                        ON CONFLICT (player_id) DO NOTHING
                    """, player_id, random.randint(0, 100), random.randint(0, 50))
                
        except Exception as e:
            logger.error(f"Test data creation error: {e}")
    
    async def _cleanup_test_data(self):
        """Remove test data"""
        try:
            async with self.connection_pool.acquire() as conn:
                # Clean up test games
                for game_id in self.test_data_ids:
                    await conn.execute("DELETE FROM games WHERE game_id = $1", game_id)
                
                # Clean up test players
                await conn.execute("""
                    DELETE FROM players 
                    WHERE player_id LIKE 'load_test_player_%'
                """)
                
        except Exception as e:
            logger.error(f"Test data cleanup error: {e}")
    
    async def generate_load(self, duration_seconds: int) -> Dict[str, Any]:
        """Generate database load for specified duration"""
        start_time = time.time()
        end_time = start_time + duration_seconds
        
        tasks = []
        metrics = {
            'queries_executed': 0,
            'queries_failed': 0,
            'transactions_completed': 0,
            'transactions_failed': 0,
            'average_query_time': 0,
            'query_times': []
        }
        
        # Start load generation tasks
        for i in range(self.load_profile.concurrent_connections):
            task = asyncio.create_task(
                self._generate_user_load(end_time, metrics)
            )
            tasks.append(task)
        
        # Wait for all tasks to complete
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # Calculate final metrics
        if metrics['query_times']:
            metrics['average_query_time'] = statistics.mean(metrics['query_times'])
            metrics['p95_query_time'] = statistics.quantiles(metrics['query_times'], n=20)[18]  # 95th percentile
            metrics['p99_query_time'] = statistics.quantiles(metrics['query_times'], n=100)[98]  # 99th percentile
        
        return metrics
    
    async def _generate_user_load(self, end_time: float, metrics: Dict[str, Any]):
        """Generate load simulating a single user's database interactions"""
        while time.time() < end_time:
            try:
                async with self.connection_pool.acquire() as conn:
                    # Decide on operation type based on read/write ratio
                    if random.random() < self.load_profile.read_write_ratio:
                        await self._perform_read_operations(conn, metrics)
                    else:
                        await self._perform_write_operations(conn, metrics)
                    
                    # Occasionally perform complex operations
                    if random.random() < self.load_profile.complex_query_probability:
                        await self._perform_complex_operations(conn, metrics)
                    
                    # Batch operations
                    if random.random() < self.load_profile.batch_operation_probability:
                        await self._perform_batch_operations(conn, metrics)
                
                # Brief pause between operations
                await asyncio.sleep(random.uniform(0.01, 0.1))
                
            except Exception as e:
                metrics['queries_failed'] += 1
                logger.debug(f"Load generation error: {e}")
    
    async def _perform_read_operations(self, conn: asyncpg.Connection, metrics: Dict[str, Any]):
        """Perform typical read operations"""
        operations = [
            self._query_game_status,
            self._query_player_stats,
            self._query_game_history,
            self._query_leaderboard
        ]
        
        operation = random.choice(operations)
        start_time = time.time()
        
        try:
            await operation(conn)
            query_time = (time.time() - start_time) * 1000  # Convert to milliseconds
            metrics['queries_executed'] += 1
            metrics['query_times'].append(query_time)
        except Exception as e:
            metrics['queries_failed'] += 1
            raise
    
    async def _perform_write_operations(self, conn: asyncpg.Connection, metrics: Dict[str, Any]):
        """Perform typical write operations"""
        operations = [
            self._update_game_state,
            self._record_player_action,
            self._update_player_stats,
            self._create_game_event
        ]
        
        operation = random.choice(operations)
        start_time = time.time()
        
        try:
            async with conn.transaction():
                await operation(conn)
                transaction_time = (time.time() - start_time) * 1000
                metrics['transactions_completed'] += 1
                metrics['queries_executed'] += 1
                metrics['query_times'].append(transaction_time)
        except Exception as e:
            metrics['transactions_failed'] += 1
            metrics['queries_failed'] += 1
            raise
    
    async def _perform_complex_operations(self, conn: asyncpg.Connection, metrics: Dict[str, Any]):
        """Perform complex database operations"""
        start_time = time.time()
        
        try:
            # Complex aggregation query
            await conn.fetch("""
                SELECT 
                    p.player_id,
                    COUNT(g.game_id) as total_games,
                    AVG(CASE WHEN g.winner_id = p.player_id THEN 1 ELSE 0 END) as win_rate,
                    MAX(g.created_at) as last_game
                FROM players p
                LEFT JOIN games g ON g.winner_id = p.player_id OR 
                                   g.game_id IN (
                                       SELECT game_id FROM game_players 
                                       WHERE player_id = p.player_id
                                   )
                WHERE p.created_at > NOW() - INTERVAL '7 days'
                GROUP BY p.player_id
                HAVING COUNT(g.game_id) > 0
                ORDER BY win_rate DESC, total_games DESC
                LIMIT 50
            """)
            
            query_time = (time.time() - start_time) * 1000
            metrics['queries_executed'] += 1
            metrics['query_times'].append(query_time)
            
        except Exception as e:
            metrics['queries_failed'] += 1
            raise
    
    async def _perform_batch_operations(self, conn: asyncpg.Connection, metrics: Dict[str, Any]):
        """Perform batch database operations"""
        start_time = time.time()
        
        try:
            # Batch insert of game events
            events = []
            for i in range(random.randint(5, 20)):
                events.append((
                    random.choice(self.test_data_ids) if self.test_data_ids else f"game_{i}",
                    f"load_test_event_{uuid.uuid4().hex[:8]}",
                    json.dumps({"action": "test_action", "data": {"value": i}}),
                    datetime.now()
                ))
            
            await conn.executemany("""
                INSERT INTO game_events (game_id, event_type, event_data, created_at)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT DO NOTHING
            """, events)
            
            batch_time = (time.time() - start_time) * 1000
            metrics['queries_executed'] += len(events)
            metrics['query_times'].append(batch_time)
            
        except Exception as e:
            metrics['queries_failed'] += 1
            raise
    
    # Individual query methods
    async def _query_game_status(self, conn: asyncpg.Connection):
        """Query game status"""
        game_id = random.choice(self.test_data_ids) if self.test_data_ids else "default_game"
        await conn.fetchrow("""
            SELECT game_id, status, current_phase, created_at, updated_at
            FROM games 
            WHERE game_id = $1
        """, game_id)
    
    async def _query_player_stats(self, conn: asyncpg.Connection):
        """Query player statistics"""
        await conn.fetch("""
            SELECT player_id, total_games, wins, 
                   CASE WHEN total_games > 0 THEN wins::float / total_games ELSE 0 END as win_rate
            FROM players 
            WHERE total_games > $1
            ORDER BY win_rate DESC
            LIMIT $2
        """, random.randint(0, 10), random.randint(10, 50))
    
    async def _query_game_history(self, conn: asyncpg.Connection):
        """Query game history"""
        await conn.fetch("""
            SELECT g.game_id, g.status, g.created_at, 
                   COUNT(gp.player_id) as player_count
            FROM games g
            LEFT JOIN game_players gp ON g.game_id = gp.game_id
            WHERE g.created_at > NOW() - INTERVAL '1 hour'
            GROUP BY g.game_id, g.status, g.created_at
            ORDER BY g.created_at DESC
            LIMIT 100
        """)
    
    async def _query_leaderboard(self, conn: asyncpg.Connection):
        """Query leaderboard"""
        await conn.fetch("""
            SELECT player_id, total_games, wins,
                   RANK() OVER (ORDER BY wins DESC, total_games DESC) as rank
            FROM players
            WHERE total_games >= 10
            ORDER BY rank
            LIMIT 50
        """)
    
    async def _update_game_state(self, conn: asyncpg.Connection):
        """Update game state"""
        game_id = random.choice(self.test_data_ids) if self.test_data_ids else "default_game"
        new_status = random.choice(['waiting', 'playing', 'completed'])
        await conn.execute("""
            UPDATE games 
            SET status = $1, updated_at = NOW()
            WHERE game_id = $2
        """, new_status, game_id)
    
    async def _record_player_action(self, conn: asyncpg.Connection):
        """Record player action"""
        game_id = random.choice(self.test_data_ids) if self.test_data_ids else "default_game"
        await conn.execute("""
            INSERT INTO game_events (game_id, event_type, event_data, created_at)
            VALUES ($1, $2, $3, NOW())
            ON CONFLICT DO NOTHING
        """, game_id, "player_action", json.dumps({"action": "card_played", "card": "AS"}))
    
    async def _update_player_stats(self, conn: asyncpg.Connection):
        """Update player statistics"""
        await conn.execute("""
            UPDATE players 
            SET total_games = total_games + 1,
                wins = wins + $1,
                updated_at = NOW()
            WHERE player_id = $2
        """, random.randint(0, 1), f"load_test_player_{random.randint(1, 100)}")
    
    async def _create_game_event(self, conn: asyncpg.Connection):
        """Create game event"""
        game_id = random.choice(self.test_data_ids) if self.test_data_ids else "default_game"
        event_data = {
            "timestamp": datetime.now().isoformat(),
            "action": random.choice(["join", "leave", "play_card", "pass"]),
            "player": f"player_{random.randint(1, 4)}"
        }
        await conn.execute("""
            INSERT INTO game_events (game_id, event_type, event_data, created_at)
            VALUES ($1, $2, $3, NOW())
        """, game_id, "game_action", json.dumps(event_data))

class PostgreSQLLoadTestRunner:
    """Main class for running PostgreSQL load tests"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.db_config = config['database']
        self.load_profile = DatabaseLoadProfile(**config.get('load_profile', {}))
        self.monitor = PostgreSQLMonitor(self.db_config)
        self.load_tester = DatabaseLoadTester(self.db_config, self.load_profile)
        
    async def run_comprehensive_test(self, duration_minutes: int = 10) -> Dict[str, Any]:
        """Run comprehensive PostgreSQL load test"""
        logger.info(f"Starting PostgreSQL load test for {duration_minutes} minutes")
        
        try:
            # Setup
            await self.load_tester.setup()
            await self.monitor.start_monitoring()
            
            # Run load test
            load_metrics = await self.load_tester.generate_load(duration_minutes * 60)
            
            # Stop monitoring
            await self.monitor.stop_monitoring()
            
            # Generate comprehensive report
            report = await self._generate_test_report(load_metrics)
            
            return report
            
        except Exception as e:
            logger.error(f"Load test error: {e}")
            logger.error(traceback.format_exc())
            raise
        finally:
            await self.load_tester.cleanup()
    
    async def _generate_test_report(self, load_metrics: Dict[str, Any]) -> Dict[str, Any]:
        """Generate comprehensive test report"""
        pg_metrics = self.monitor.metrics
        
        report = {
            'test_summary': {
                'duration_minutes': self.config.get('duration_minutes', 10),
                'concurrent_connections': self.load_profile.concurrent_connections,
                'target_qps': self.load_profile.queries_per_second_target,
                'read_write_ratio': self.load_profile.read_write_ratio
            },
            'load_metrics': load_metrics,
            'database_metrics': {
                'connection_stats': {
                    'avg_active_connections': statistics.mean(pg_metrics.active_connections) if pg_metrics.active_connections else 0,
                    'max_active_connections': max(pg_metrics.active_connections) if pg_metrics.active_connections else 0,
                    'avg_idle_connections': statistics.mean(pg_metrics.idle_connections) if pg_metrics.idle_connections else 0,
                    'connection_timeouts': pg_metrics.connection_timeouts
                },
                'query_performance': {
                    'query_counts_by_type': dict(pg_metrics.query_counts_by_type),
                    'avg_query_times_by_type': {
                        qtype: statistics.mean(times) if times else 0
                        for qtype, times in pg_metrics.query_times_by_type.items()
                    },
                    'slow_queries_count': len(pg_metrics.slow_queries),
                    'failed_queries': dict(pg_metrics.failed_queries)
                },
                'transaction_stats': {
                    'avg_transaction_time': statistics.mean(pg_metrics.transaction_times) if pg_metrics.transaction_times else 0,
                    'transaction_rollbacks': pg_metrics.transaction_rollbacks,
                    'transaction_deadlocks': pg_metrics.transaction_deadlocks
                },
                'lock_contention': {
                    'lock_timeouts': pg_metrics.lock_timeouts,
                    'blocking_queries_count': len(pg_metrics.blocking_queries)
                },
                'buffer_cache': {
                    'avg_hit_ratio': statistics.mean(pg_metrics.buffer_hits) if pg_metrics.buffer_hits else 0,
                    'index_hit_ratio': pg_metrics.index_hits / (pg_metrics.index_hits + pg_metrics.index_misses) if (pg_metrics.index_hits + pg_metrics.index_misses) > 0 else 0
                },
                'database_size': {
                    'current_size_mb': pg_metrics.database_size_mb[-1] if pg_metrics.database_size_mb else 0,
                    'table_sizes': {
                        table: sizes[-1] if sizes else 0
                        for table, sizes in pg_metrics.table_sizes.items()
                    }
                }
            },
            'performance_analysis': await self._analyze_performance(load_metrics, pg_metrics),
            'recommendations': await self._generate_recommendations(load_metrics, pg_metrics)
        }
        
        return report
    
    async def _analyze_performance(self, load_metrics: Dict[str, Any], pg_metrics: PostgreSQLMetrics) -> Dict[str, Any]:
        """Analyze performance and identify bottlenecks"""
        analysis = {
            'bottlenecks': [],
            'performance_issues': [],
            'strengths': []
        }
        
        # Check query performance
        if load_metrics.get('average_query_time', 0) > 100:  # 100ms threshold
            analysis['bottlenecks'].append({
                'type': 'slow_queries',
                'severity': 'high' if load_metrics.get('average_query_time', 0) > 500 else 'medium',
                'description': f"Average query time {load_metrics.get('average_query_time', 0):.2f}ms exceeds threshold",
                'impact': 'User experience degradation'
            })
        
        # Check connection pool utilization
        if pg_metrics.active_connections:
            max_active = max(pg_metrics.active_connections)
            if max_active > self.load_profile.concurrent_connections * 0.9:
                analysis['bottlenecks'].append({
                    'type': 'connection_pool_exhaustion',
                    'severity': 'high',
                    'description': f"Connection pool utilization peaked at {max_active}/{self.load_profile.concurrent_connections}",
                    'impact': 'Connection timeouts and request failures'
                })
        
        # Check lock contention
        if pg_metrics.lock_timeouts > 0 or len(pg_metrics.blocking_queries) > 10:
            analysis['bottlenecks'].append({
                'type': 'lock_contention',
                'severity': 'medium',
                'description': f"Lock timeouts: {pg_metrics.lock_timeouts}, Blocking queries: {len(pg_metrics.blocking_queries)}",
                'impact': 'Transaction delays and potential deadlocks'
            })
        
        # Check buffer cache efficiency
        if pg_metrics.buffer_hits:
            hit_ratio = statistics.mean(pg_metrics.buffer_hits)
            if hit_ratio < 0.95:  # 95% threshold
                analysis['performance_issues'].append({
                    'type': 'low_buffer_cache_hit_ratio',
                    'severity': 'medium',
                    'description': f"Buffer cache hit ratio {hit_ratio:.2%} below optimal",
                    'impact': 'Increased disk I/O and slower queries'
                })
        
        # Identify strengths
        if load_metrics.get('queries_failed', 0) == 0:
            analysis['strengths'].append("No query failures during load test")
        
        if pg_metrics.transaction_deadlocks == 0:
            analysis['strengths'].append("No transaction deadlocks detected")
        
        error_rate = load_metrics.get('queries_failed', 0) / max(load_metrics.get('queries_executed', 1), 1)
        if error_rate < 0.01:  # Less than 1% error rate
            analysis['strengths'].append(f"Low error rate: {error_rate:.2%}")
        
        return analysis
    
    async def _generate_recommendations(self, load_metrics: Dict[str, Any], pg_metrics: PostgreSQLMetrics) -> List[Dict[str, str]]:
        """Generate performance improvement recommendations"""
        recommendations = []
        
        # Connection pool recommendations
        if pg_metrics.active_connections:
            max_active = max(pg_metrics.active_connections)
            if max_active > self.load_profile.concurrent_connections * 0.8:
                recommendations.append({
                    'category': 'Connection Pool',
                    'priority': 'High',
                    'recommendation': f'Increase connection pool size from {self.load_profile.concurrent_connections} to {max_active + 10}',
                    'rationale': 'High connection pool utilization detected'
                })
        
        # Query optimization recommendations
        if pg_metrics.slow_queries:
            recommendations.append({
                'category': 'Query Optimization',
                'priority': 'High',
                'recommendation': 'Optimize slow queries identified in monitoring',
                'rationale': f'{len(pg_metrics.slow_queries)} slow queries detected during test'
            })
        
        # Index recommendations
        if pg_metrics.index_misses > pg_metrics.index_hits * 0.1:  # More than 10% misses
            recommendations.append({
                'category': 'Indexing',
                'priority': 'Medium',
                'recommendation': 'Review and add missing indexes for frequently queried columns',
                'rationale': 'High index miss ratio indicates potential missing indexes'
            })
        
        # Buffer cache recommendations
        if pg_metrics.buffer_hits:
            hit_ratio = statistics.mean(pg_metrics.buffer_hits)
            if hit_ratio < 0.95:
                recommendations.append({
                    'category': 'Memory Configuration',
                    'priority': 'Medium',
                    'recommendation': 'Increase shared_buffers and effective_cache_size parameters',
                    'rationale': f'Buffer cache hit ratio {hit_ratio:.2%} indicates need for more memory allocation'
                })
        
        # Lock contention recommendations
        if pg_metrics.lock_timeouts > 0:
            recommendations.append({
                'category': 'Concurrency',
                'priority': 'Medium',
                'recommendation': 'Review transaction isolation levels and query patterns to reduce lock contention',
                'rationale': f'{pg_metrics.lock_timeouts} lock timeouts detected'
            })
        
        # Scaling recommendations
        qps = load_metrics.get('queries_executed', 0) / (self.config.get('duration_minutes', 10) * 60)
        if qps < self.load_profile.queries_per_second_target * 0.8:
            recommendations.append({
                'category': 'Scaling',
                'priority': 'High',
                'recommendation': 'Consider horizontal scaling or read replicas',
                'rationale': f'Achieved QPS {qps:.0f} below target {self.load_profile.queries_per_second_target}'
            })
        
        return recommendations

def create_test_config() -> Dict[str, Any]:
    """Create default test configuration"""
    return {
        'database': {
            'host': 'localhost',
            'port': 5432,
            'database': 'hokm_game',
            'user': 'postgres',
            'password': 'password'
        },
        'load_profile': {
            'concurrent_connections': 50,
            'queries_per_second_target': 1000,
            'read_write_ratio': 0.7,
            'transaction_size_range': [1, 5],
            'batch_operation_probability': 0.1,
            'complex_query_probability': 0.05,
            'concurrent_user_actions': 100,
            'data_volume_multiplier': 1.0
        },
        'duration_minutes': 10,
        'output_format': 'json'
    }

async def main():
    """Main function for running PostgreSQL load tests"""
    parser = argparse.ArgumentParser(description='PostgreSQL Load Testing for Hokm Game Server')
    parser.add_argument('--config', type=str, help='Path to configuration file')
    parser.add_argument('--duration', type=int, default=10, help='Test duration in minutes')
    parser.add_argument('--connections', type=int, default=50, help='Concurrent database connections')
    parser.add_argument('--qps-target', type=int, default=1000, help='Target queries per second')
    parser.add_argument('--output', type=str, default='postgresql_load_test_report.json', help='Output file path')
    parser.add_argument('--verbose', action='store_true', help='Enable verbose logging')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Load configuration
    if args.config and Path(args.config).exists():
        with open(args.config, 'r') as f:
            config = json.load(f)
    else:
        config = create_test_config()
    
    # Override config with command line arguments
    config['duration_minutes'] = args.duration
    config['load_profile']['concurrent_connections'] = args.connections
    config['load_profile']['queries_per_second_target'] = args.qps_target
    
    # Run load test
    runner = PostgreSQLLoadTestRunner(config)
    
    try:
        report = await runner.run_comprehensive_test(args.duration)
        
        # Save report
        with open(args.output, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        
        # Print summary
        print(f"\nPostgreSQL Load Test Complete!")
        print(f"Duration: {args.duration} minutes")
        print(f"Queries executed: {report['load_metrics']['queries_executed']}")
        print(f"Queries failed: {report['load_metrics']['queries_failed']}")
        print(f"Average query time: {report['load_metrics']['average_query_time']:.2f}ms")
        print(f"Report saved to: {args.output}")
        
        # Print key recommendations
        if report['recommendations']:
            print("\nKey Recommendations:")
            for rec in report['recommendations'][:3]:  # Show top 3
                print(f"- [{rec['priority']}] {rec['recommendation']}")
        
    except Exception as e:
        logger.error(f"Load test failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
