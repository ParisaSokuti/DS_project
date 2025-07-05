#!/usr/bin/env python3
"""
Comprehensive Load Testing Framework for Hokm Game Server
Simulates realistic game traffic with PostgreSQL integration and advanced metrics
"""

import asyncio
import aiohttp
import websockets
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
import psutil
import concurrent.futures
from pathlib import Path
import statistics
import asyncpg
import redis.asyncio as redis

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

@dataclass
class UserBehaviorProfile:
    """Defines realistic user behavior patterns"""
    session_duration_minutes: Tuple[int, int] = (15, 45)  # min, max
    games_per_session: Tuple[int, int] = (2, 8)
    think_time_seconds: Tuple[float, float] = (0.5, 3.0)
    disconnect_probability: float = 0.02  # 2% chance per action
    reconnect_probability: float = 0.9  # 90% chance to reconnect
    idle_time_between_games: Tuple[int, int] = (30, 120)  # seconds
    card_play_speed: Tuple[float, float] = (1.0, 5.0)  # seconds between cards
    patience_timeout: int = 180  # seconds before leaving if game doesn't start

@dataclass
class LoadTestMetrics:
    """Comprehensive metrics collection for load testing"""
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None
    
    # Connection metrics
    connection_attempts: int = 0
    successful_connections: int = 0
    failed_connections: int = 0
    disconnections: int = 0
    reconnections: int = 0
    
    # Response time metrics
    response_times: deque = field(default_factory=lambda: deque(maxlen=10000))
    db_query_times: deque = field(default_factory=lambda: deque(maxlen=10000))
    websocket_latencies: deque = field(default_factory=lambda: deque(maxlen=10000))
    
    # Game flow metrics
    games_started: int = 0
    games_completed: int = 0
    games_abandoned: int = 0
    player_joins: int = 0
    player_leaves: int = 0
    
    # Error tracking
    errors_by_type: Dict[str, int] = field(default_factory=dict)
    error_details: List[Dict[str, Any]] = field(default_factory=list)
    
    # Resource utilization
    cpu_usage_samples: deque = field(default_factory=lambda: deque(maxlen=1000))
    memory_usage_samples: deque = field(default_factory=lambda: deque(maxlen=1000))
    network_io_samples: deque = field(default_factory=lambda: deque(maxlen=1000))
    
    # Database metrics
    db_connections_active: deque = field(default_factory=lambda: deque(maxlen=1000))
    db_query_counts: Dict[str, int] = field(default_factory=dict)
    db_slow_queries: List[Dict[str, Any]] = field(default_factory=list)

@dataclass
class PerformanceThresholds:
    """Defines acceptable performance thresholds"""
    max_avg_response_time_ms: float = 500.0
    max_p95_response_time_ms: float = 1000.0
    max_p99_response_time_ms: float = 2000.0
    max_error_rate_percent: float = 1.0
    max_connection_failure_rate_percent: float = 2.0
    min_games_completion_rate_percent: float = 90.0
    max_cpu_usage_percent: float = 80.0
    max_memory_usage_percent: float = 85.0
    max_db_connection_pool_usage_percent: float = 90.0
    max_db_query_time_ms: float = 100.0

class VirtualUser:
    """Simulates a realistic game user with behavior patterns"""
    
    def __init__(self, user_id: str, server_url: str, behavior_profile: UserBehaviorProfile, metrics: LoadTestMetrics):
        self.user_id = user_id
        self.server_url = server_url
        self.behavior = behavior_profile
        self.metrics = metrics
        self.websocket = None
        self.session_start_time = None
        self.current_game_id = None
        self.is_connected = False
        self.games_played = 0
        self.session_active = True
        
    async def run_session(self):
        """Run a complete user session"""
        session_duration = random.randint(*self.behavior.session_duration_minutes) * 60
        games_to_play = random.randint(*self.behavior.games_per_session)
        
        self.session_start_time = time.time()
        logger.debug(f"User {self.user_id} starting {games_to_play} games over {session_duration/60:.1f} minutes")
        
        try:
            await self.connect()
            
            while (self.session_active and 
                   self.games_played < games_to_play and 
                   time.time() - self.session_start_time < session_duration):
                
                if not self.is_connected:
                    if random.random() < self.behavior.reconnect_probability:
                        await self.reconnect()
                    else:
                        break
                
                await self.play_game()
                self.games_played += 1
                
                if self.games_played < games_to_play:
                    # Idle time between games
                    idle_time = random.randint(*self.behavior.idle_time_between_games)
                    logger.debug(f"User {self.user_id} idling for {idle_time}s between games")
                    await asyncio.sleep(idle_time)
                    
        except Exception as e:
            logger.error(f"User {self.user_id} session error: {e}")
            self.metrics.errors_by_type["session_error"] = self.metrics.errors_by_type.get("session_error", 0) + 1
        finally:
            await self.disconnect()
            
        logger.debug(f"User {self.user_id} completed session: {self.games_played} games played")
    
    async def connect(self):
        """Connect to the game server"""
        start_time = time.time()
        self.metrics.connection_attempts += 1
        
        try:
            self.websocket = await websockets.connect(
                f"{self.server_url.replace('http', 'ws')}/ws",
                timeout=10
            )
            self.is_connected = True
            self.metrics.successful_connections += 1
            
            # Send initial authentication/join message
            await self.send_message({
                "type": "join",
                "username": self.user_id,
                "room_id": f"load_test_room_{random.randint(1, 20)}"  # Distribute across rooms
            })
            
            response_time = (time.time() - start_time) * 1000
            self.metrics.response_times.append(response_time)
            
        except Exception as e:
            self.metrics.failed_connections += 1
            self.metrics.errors_by_type["connection_failed"] = self.metrics.errors_by_type.get("connection_failed", 0) + 1
            logger.error(f"User {self.user_id} connection failed: {e}")
            raise
    
    async def disconnect(self):
        """Disconnect from the server"""
        if self.websocket and not self.websocket.closed:
            await self.websocket.close()
            self.metrics.disconnections += 1
        self.is_connected = False
    
    async def reconnect(self):
        """Attempt to reconnect after disconnection"""
        logger.debug(f"User {self.user_id} attempting reconnection")
        try:
            await self.disconnect()
            await asyncio.sleep(random.uniform(1, 5))  # Brief delay before reconnect
            await self.connect()
            self.metrics.reconnections += 1
        except Exception as e:
            logger.error(f"User {self.user_id} reconnection failed: {e}")
    
    async def play_game(self):
        """Simulate playing a complete game"""
        game_start_time = time.time()
        
        try:
            # Join game queue or create game
            await self.send_message({
                "type": "join_game",
                "game_type": "hokm"
            })
            
            # Wait for game to start (with timeout)
            game_started = await self.wait_for_game_start()
            if not game_started:
                self.metrics.games_abandoned += 1
                return
            
            self.metrics.games_started += 1
            self.metrics.player_joins += 1
            
            # Simulate game phases
            await self.simulate_game_phases()
            
            # Game completion
            game_duration = time.time() - game_start_time
            if game_duration > 60:  # Minimum reasonable game duration
                self.metrics.games_completed += 1
            else:
                self.metrics.games_abandoned += 1
                
        except Exception as e:
            self.metrics.games_abandoned += 1
            self.metrics.errors_by_type["game_error"] = self.metrics.errors_by_type.get("game_error", 0) + 1
            logger.error(f"User {self.user_id} game error: {e}")
    
    async def wait_for_game_start(self) -> bool:
        """Wait for game to start with timeout"""
        timeout = self.behavior.patience_timeout
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                message = await asyncio.wait_for(self.websocket.recv(), timeout=5.0)
                data = json.loads(message)
                
                if data.get("type") == "game_started":
                    self.current_game_id = data.get("game_id")
                    return True
                elif data.get("type") == "game_phase":
                    # Game might have started
                    return True
                    
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"User {self.user_id} error waiting for game start: {e}")
                return False
        
        logger.debug(f"User {self.user_id} timed out waiting for game start")
        return False
    
    async def simulate_game_phases(self):
        """Simulate realistic game phase interactions"""
        game_phases = ["trump_selection", "card_dealing", "playing", "round_end"]
        
        for phase in game_phases:
            if not self.is_connected:
                break
                
            # Simulate thinking time
            think_time = random.uniform(*self.behavior.think_time_seconds)
            await asyncio.sleep(think_time)
            
            # Random disconnection during game
            if random.random() < self.behavior.disconnect_probability:
                logger.debug(f"User {self.user_id} randomly disconnecting during {phase}")
                await self.disconnect()
                self.is_connected = False
                break
            
            # Simulate phase-specific actions
            if phase == "trump_selection":
                await self.simulate_trump_selection()
            elif phase == "card_dealing":
                await self.simulate_card_dealing()
            elif phase == "playing":
                await self.simulate_card_playing()
            elif phase == "round_end":
                await self.simulate_round_end()
    
    async def simulate_trump_selection(self):
        """Simulate trump selection phase"""
        await self.send_message({
            "type": "trump_selection",
            "suit": random.choice(["hearts", "diamonds", "clubs", "spades"])
        })
    
    async def simulate_card_dealing(self):
        """Simulate card dealing phase"""
        # Just wait for cards to be dealt
        await asyncio.sleep(2)
    
    async def simulate_card_playing(self):
        """Simulate playing cards during game"""
        # Simulate playing 13 tricks (52 cards / 4 players)
        for trick in range(13):
            if not self.is_connected:
                break
                
            # Wait for turn
            await asyncio.sleep(random.uniform(*self.behavior.card_play_speed))
            
            # Play a card
            await self.send_message({
                "type": "play_card",
                "card": f"{random.choice(['A', 'K', 'Q', 'J', '10', '9', '8', '7', '6', '5', '4', '3', '2'])}{random.choice(['H', 'D', 'C', 'S'])}"
            })
            
            # Brief pause between tricks
            await asyncio.sleep(1)
    
    async def simulate_round_end(self):
        """Simulate round end phase"""
        await asyncio.sleep(2)  # Wait for round to complete
    
    async def send_message(self, message: Dict[str, Any]):
        """Send message to server and measure response time"""
        if not self.is_connected or not self.websocket:
            return
            
        start_time = time.time()
        
        try:
            await self.websocket.send(json.dumps(message))
            
            # Measure response time (if expecting a response)
            if message.get("type") in ["join", "join_game", "trump_selection", "play_card"]:
                response = await asyncio.wait_for(self.websocket.recv(), timeout=5.0)
                response_time = (time.time() - start_time) * 1000
                self.metrics.response_times.append(response_time)
                self.metrics.websocket_latencies.append(response_time)
                
        except asyncio.TimeoutError:
            self.metrics.errors_by_type["timeout"] = self.metrics.errors_by_type.get("timeout", 0) + 1
        except Exception as e:
            self.metrics.errors_by_type["send_error"] = self.metrics.errors_by_type.get("send_error", 0) + 1
            logger.error(f"User {self.user_id} send error: {e}")

class SystemMonitor:
    """Monitors system resource utilization during load tests"""
    
    def __init__(self, metrics: LoadTestMetrics, postgres_url: str, redis_url: str):
        self.metrics = metrics
        self.postgres_url = postgres_url
        self.redis_url = redis_url
        self.monitoring = False
        self.postgres_pool = None
        self.redis_client = None
        
    async def start_monitoring(self):
        """Start system monitoring"""
        self.monitoring = True
        
        # Initialize database connections for monitoring
        try:
            self.postgres_pool = await asyncpg.create_pool(self.postgres_url, min_size=1, max_size=2)
            self.redis_client = redis.from_url(self.redis_url)
        except Exception as e:
            logger.error(f"Failed to initialize monitoring connections: {e}")
        
        # Start monitoring tasks
        asyncio.create_task(self.monitor_system_resources())
        asyncio.create_task(self.monitor_database_metrics())
        
    async def stop_monitoring(self):
        """Stop system monitoring"""
        self.monitoring = False
        
        if self.postgres_pool:
            await self.postgres_pool.close()
        if self.redis_client:
            await self.redis_client.close()
    
    async def monitor_system_resources(self):
        """Monitor CPU, memory, and network usage"""
        while self.monitoring:
            try:
                # CPU usage
                cpu_percent = psutil.cpu_percent(interval=1)
                self.metrics.cpu_usage_samples.append(cpu_percent)
                
                # Memory usage
                memory = psutil.virtual_memory()
                self.metrics.memory_usage_samples.append(memory.percent)
                
                # Network I/O
                network = psutil.net_io_counters()
                self.metrics.network_io_samples.append({
                    'bytes_sent': network.bytes_sent,
                    'bytes_recv': network.bytes_recv,
                    'timestamp': time.time()
                })
                
                await asyncio.sleep(5)  # Sample every 5 seconds
                
            except Exception as e:
                logger.error(f"System monitoring error: {e}")
                await asyncio.sleep(10)
    
    async def monitor_database_metrics(self):
        """Monitor database-specific metrics"""
        while self.monitoring:
            try:
                # PostgreSQL metrics
                if self.postgres_pool:
                    await self.collect_postgres_metrics()
                
                # Redis metrics
                if self.redis_client:
                    await self.collect_redis_metrics()
                
                await asyncio.sleep(10)  # Sample every 10 seconds
                
            except Exception as e:
                logger.error(f"Database monitoring error: {e}")
                await asyncio.sleep(15)
    
    async def collect_postgres_metrics(self):
        """Collect PostgreSQL performance metrics"""
        try:
            async with self.postgres_pool.acquire() as conn:
                # Active connections
                result = await conn.fetchval("SELECT count(*) FROM pg_stat_activity WHERE state = 'active'")
                self.metrics.db_connections_active.append(result)
                
                # Slow queries (queries taking > 1 second)
                slow_queries = await conn.fetch("""
                    SELECT query, query_start, now() - query_start as duration 
                    FROM pg_stat_activity 
                    WHERE state = 'active' AND now() - query_start > interval '1 second'
                    LIMIT 10
                """)
                
                for query in slow_queries:
                    self.metrics.db_slow_queries.append({
                        'query': query['query'][:200],  # Truncate long queries
                        'duration_seconds': query['duration'].total_seconds(),
                        'timestamp': time.time()
                    })
                
                # Database statistics
                stats = await conn.fetchrow("""
                    SELECT sum(numbackends) as connections,
                           sum(xact_commit) as commits,
                           sum(xact_rollback) as rollbacks,
                           sum(tup_returned) as tuples_read,
                           sum(tup_inserted) as tuples_inserted,
                           sum(tup_updated) as tuples_updated
                    FROM pg_stat_database
                """)
                
                self.metrics.db_query_counts.update({
                    'commits': stats['commits'],
                    'rollbacks': stats['rollbacks'],
                    'tuples_read': stats['tuples_read'],
                    'tuples_inserted': stats['tuples_inserted'],
                    'tuples_updated': stats['tuples_updated']
                })
                
        except Exception as e:
            logger.error(f"PostgreSQL metrics collection error: {e}")
    
    async def collect_redis_metrics(self):
        """Collect Redis performance metrics"""
        try:
            info = await self.redis_client.info()
            
            # Key metrics from Redis INFO
            redis_metrics = {
                'connected_clients': info.get('connected_clients', 0),
                'used_memory': info.get('used_memory', 0),
                'used_memory_percent': info.get('used_memory_rss', 0) / info.get('maxmemory', 1) * 100 if info.get('maxmemory') else 0,
                'keyspace_hits': info.get('keyspace_hits', 0),
                'keyspace_misses': info.get('keyspace_misses', 0),
                'total_commands_processed': info.get('total_commands_processed', 0)
            }
            
            # Store in metrics (could extend LoadTestMetrics to include Redis metrics)
            logger.debug(f"Redis metrics: {redis_metrics}")
            
        except Exception as e:
            logger.error(f"Redis metrics collection error: {e}")

class LoadTestRunner:
    """Main load testing orchestrator"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.metrics = LoadTestMetrics()
        self.thresholds = PerformanceThresholds(**config.get('thresholds', {}))
        self.behavior_profile = UserBehaviorProfile(**config.get('user_behavior', {}))
        self.monitor = SystemMonitor(
            self.metrics, 
            config.get('postgres_url', 'postgresql://localhost:5432/hokm_test'),
            config.get('redis_url', 'redis://localhost:6379')
        )
        
    async def run_load_test(self, concurrent_users: int, test_duration_minutes: int, ramp_up_minutes: int = 5):
        """Run comprehensive load test"""
        logger.info(f"🚀 Starting load test: {concurrent_users} users, {test_duration_minutes}m duration, {ramp_up_minutes}m ramp-up")
        
        # Start system monitoring
        await self.monitor.start_monitoring()
        
        try:
            # Create virtual users
            users = []
            for i in range(concurrent_users):
                user = VirtualUser(
                    user_id=f"load_user_{i:04d}",
                    server_url=self.config['server_url'],
                    behavior_profile=self.behavior_profile,
                    metrics=self.metrics
                )
                users.append(user)
            
            # Ramp up users gradually
            await self.ramp_up_users(users, ramp_up_minutes)
            
            # Let test run for specified duration
            logger.info(f"🔥 Full load running with {concurrent_users} concurrent users")
            await asyncio.sleep((test_duration_minutes - ramp_up_minutes) * 60)
            
            # Graceful shutdown
            logger.info("🛑 Gracefully shutting down load test")
            await self.shutdown_users(users)
            
        finally:
            # Stop monitoring
            await self.monitor.stop_monitoring()
            self.metrics.end_time = datetime.now()
            
        # Generate and return results
        return await self.generate_test_results()
    
    async def ramp_up_users(self, users: List[VirtualUser], ramp_up_minutes: int):
        """Gradually ramp up users to target load"""
        ramp_up_seconds = ramp_up_minutes * 60
        users_per_second = len(users) / ramp_up_seconds
        
        logger.info(f"📈 Ramping up {len(users)} users over {ramp_up_minutes} minutes ({users_per_second:.2f} users/sec)")
        
        tasks = []
        for i, user in enumerate(users):
            # Stagger user starts
            delay = i / users_per_second
            task = asyncio.create_task(self.start_user_with_delay(user, delay))
            tasks.append(task)
        
        # Wait for ramp-up to complete
        await asyncio.sleep(ramp_up_seconds)
        logger.info("📈 Ramp-up phase completed")
    
    async def start_user_with_delay(self, user: VirtualUser, delay: float):
        """Start a user after a specified delay"""
        await asyncio.sleep(delay)
        try:
            await user.run_session()
        except Exception as e:
            logger.error(f"User {user.user_id} session failed: {e}")
    
    async def shutdown_users(self, users: List[VirtualUser]):
        """Gracefully shutdown all users"""
        for user in users:
            user.session_active = False
            try:
                await user.disconnect()
            except:
                pass
    
    async def generate_test_results(self) -> Dict[str, Any]:
        """Generate comprehensive test results"""
        duration = (self.metrics.end_time - self.metrics.start_time).total_seconds()
        
        # Calculate response time statistics
        response_times = list(self.metrics.response_times)
        if response_times:
            avg_response_time = statistics.mean(response_times)
            p95_response_time = statistics.quantiles(response_times, n=20)[18]  # 95th percentile
            p99_response_time = statistics.quantiles(response_times, n=100)[98]  # 99th percentile
        else:
            avg_response_time = p95_response_time = p99_response_time = 0
        
        # Calculate error rates
        total_operations = (self.metrics.connection_attempts + self.metrics.games_started + 
                          self.metrics.player_joins + len(response_times))
        total_errors = sum(self.metrics.errors_by_type.values()) + self.metrics.failed_connections
        error_rate = (total_errors / total_operations * 100) if total_operations > 0 else 0
        
        # Calculate throughput
        throughput = total_operations / duration if duration > 0 else 0
        
        # System resource statistics
        cpu_usage = list(self.metrics.cpu_usage_samples)
        memory_usage = list(self.metrics.memory_usage_samples)
        
        results = {
            'test_summary': {
                'duration_seconds': duration,
                'total_operations': total_operations,
                'throughput_ops_per_sec': throughput,
                'error_rate_percent': error_rate
            },
            'performance_metrics': {
                'avg_response_time_ms': avg_response_time,
                'p95_response_time_ms': p95_response_time,
                'p99_response_time_ms': p99_response_time,
                'min_response_time_ms': min(response_times) if response_times else 0,
                'max_response_time_ms': max(response_times) if response_times else 0
            },
            'connection_metrics': {
                'connection_attempts': self.metrics.connection_attempts,
                'successful_connections': self.metrics.successful_connections,
                'failed_connections': self.metrics.failed_connections,
                'connection_success_rate_percent': (
                    self.metrics.successful_connections / self.metrics.connection_attempts * 100
                    if self.metrics.connection_attempts > 0 else 0
                ),
                'disconnections': self.metrics.disconnections,
                'reconnections': self.metrics.reconnections
            },
            'game_flow_metrics': {
                'games_started': self.metrics.games_started,
                'games_completed': self.metrics.games_completed,
                'games_abandoned': self.metrics.games_abandoned,
                'game_completion_rate_percent': (
                    self.metrics.games_completed / self.metrics.games_started * 100
                    if self.metrics.games_started > 0 else 0
                ),
                'player_joins': self.metrics.player_joins,
                'player_leaves': self.metrics.player_leaves
            },
            'resource_utilization': {
                'avg_cpu_percent': statistics.mean(cpu_usage) if cpu_usage else 0,
                'max_cpu_percent': max(cpu_usage) if cpu_usage else 0,
                'avg_memory_percent': statistics.mean(memory_usage) if memory_usage else 0,
                'max_memory_percent': max(memory_usage) if memory_usage else 0
            },
            'database_metrics': {
                'avg_active_connections': statistics.mean(list(self.metrics.db_connections_active)) if self.metrics.db_connections_active else 0,
                'max_active_connections': max(list(self.metrics.db_connections_active)) if self.metrics.db_connections_active else 0,
                'slow_queries_count': len(self.metrics.db_slow_queries),
                'query_statistics': dict(self.metrics.db_query_counts)
            },
            'error_analysis': {
                'errors_by_type': dict(self.metrics.errors_by_type),
                'error_details': self.metrics.error_details[:50]  # First 50 errors
            },
            'threshold_compliance': self.check_threshold_compliance(
                avg_response_time, p95_response_time, p99_response_time, error_rate,
                max(cpu_usage) if cpu_usage else 0,
                max(memory_usage) if memory_usage else 0
            )
        }
        
        return results
    
    def check_threshold_compliance(self, avg_response_time: float, p95_response_time: float, 
                                 p99_response_time: float, error_rate: float,
                                 max_cpu: float, max_memory: float) -> Dict[str, Any]:
        """Check if results meet performance thresholds"""
        compliance = {
            'overall_pass': True,
            'checks': {}
        }
        
        checks = [
            ('avg_response_time', avg_response_time, self.thresholds.max_avg_response_time_ms, 'ms'),
            ('p95_response_time', p95_response_time, self.thresholds.max_p95_response_time_ms, 'ms'),
            ('p99_response_time', p99_response_time, self.thresholds.max_p99_response_time_ms, 'ms'),
            ('error_rate', error_rate, self.thresholds.max_error_rate_percent, '%'),
            ('max_cpu_usage', max_cpu, self.thresholds.max_cpu_usage_percent, '%'),
            ('max_memory_usage', max_memory, self.thresholds.max_memory_usage_percent, '%')
        ]
        
        for check_name, actual_value, threshold_value, unit in checks:
            passed = actual_value <= threshold_value
            compliance['checks'][check_name] = {
                'passed': passed,
                'actual_value': actual_value,
                'threshold_value': threshold_value,
                'unit': unit
            }
            if not passed:
                compliance['overall_pass'] = False
        
        return compliance

class LoadTestReporter:
    """Generates comprehensive load test reports"""
    
    def __init__(self, results: Dict[str, Any], config: Dict[str, Any]):
        self.results = results
        self.config = config
    
    def generate_report(self, output_dir: str = "./load_test_reports") -> str:
        """Generate comprehensive load test report"""
        Path(output_dir).mkdir(exist_ok=True)
        
        # Generate different report formats
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # JSON report (detailed data)
        json_report_path = Path(output_dir) / f"load_test_results_{timestamp}.json"
        with open(json_report_path, 'w') as f:
            json.dump(self.results, f, indent=2, default=str)
        
        # Markdown report (human readable)
        md_report_path = Path(output_dir) / f"load_test_report_{timestamp}.md"
        with open(md_report_path, 'w') as f:
            f.write(self.generate_markdown_report())
        
        # HTML report (visual)
        html_report_path = Path(output_dir) / f"load_test_report_{timestamp}.html"
        with open(html_report_path, 'w') as f:
            f.write(self.generate_html_report())
        
        logger.info(f"📊 Load test reports generated:")
        logger.info(f"  - JSON: {json_report_path}")
        logger.info(f"  - Markdown: {md_report_path}")
        logger.info(f"  - HTML: {html_report_path}")
        
        return str(md_report_path)
    
    def generate_markdown_report(self) -> str:
        """Generate markdown report"""
        summary = self.results['test_summary']
        performance = self.results['performance_metrics']
        connections = self.results['connection_metrics']
        games = self.results['game_flow_metrics']
        resources = self.results['resource_utilization']
        database = self.results['database_metrics']
        compliance = self.results['threshold_compliance']
        
        status_emoji = "✅" if compliance['overall_pass'] else "❌"
        
        report = f"""# Load Test Report {status_emoji}

## Executive Summary
- **Test Duration**: {summary['duration_seconds']:.1f} seconds
- **Total Operations**: {summary['total_operations']:,}
- **Throughput**: {summary['throughput_ops_per_sec']:.1f} ops/sec
- **Error Rate**: {summary['error_rate_percent']:.2f}%
- **Overall Status**: {'PASSED' if compliance['overall_pass'] else 'FAILED'}

## Performance Metrics
| Metric | Value | Threshold | Status |
|--------|-------|-----------|--------|
| Average Response Time | {performance['avg_response_time_ms']:.1f}ms | {compliance['checks']['avg_response_time']['threshold_value']:.1f}ms | {'✅' if compliance['checks']['avg_response_time']['passed'] else '❌'} |
| P95 Response Time | {performance['p95_response_time_ms']:.1f}ms | {compliance['checks']['p95_response_time']['threshold_value']:.1f}ms | {'✅' if compliance['checks']['p95_response_time']['passed'] else '❌'} |
| P99 Response Time | {performance['p99_response_time_ms']:.1f}ms | {compliance['checks']['p99_response_time']['threshold_value']:.1f}ms | {'✅' if compliance['checks']['p99_response_time']['passed'] else '❌'} |
| Min Response Time | {performance['min_response_time_ms']:.1f}ms | - | - |
| Max Response Time | {performance['max_response_time_ms']:.1f}ms | - | - |

## Connection Metrics
- **Connection Attempts**: {connections['connection_attempts']:,}
- **Successful Connections**: {connections['successful_connections']:,}
- **Failed Connections**: {connections['failed_connections']:,}
- **Connection Success Rate**: {connections['connection_success_rate_percent']:.1f}%
- **Disconnections**: {connections['disconnections']:,}
- **Reconnections**: {connections['reconnections']:,}

## Game Flow Metrics
- **Games Started**: {games['games_started']:,}
- **Games Completed**: {games['games_completed']:,}
- **Games Abandoned**: {games['games_abandoned']:,}
- **Game Completion Rate**: {games['game_completion_rate_percent']:.1f}%
- **Player Joins**: {games['player_joins']:,}
- **Player Leaves**: {games['player_leaves']:,}

## Resource Utilization
| Resource | Average | Peak | Threshold | Status |
|----------|---------|------|-----------|--------|
| CPU Usage | {resources['avg_cpu_percent']:.1f}% | {resources['max_cpu_percent']:.1f}% | {compliance['checks']['max_cpu_usage']['threshold_value']:.1f}% | {'✅' if compliance['checks']['max_cpu_usage']['passed'] else '❌'} |
| Memory Usage | {resources['avg_memory_percent']:.1f}% | {resources['max_memory_percent']:.1f}% | {compliance['checks']['max_memory_usage']['threshold_value']:.1f}% | {'✅' if compliance['checks']['max_memory_usage']['passed'] else '❌'} |

## Database Performance
- **Average Active Connections**: {database['avg_active_connections']:.1f}
- **Peak Active Connections**: {database['max_active_connections']}
- **Slow Queries Detected**: {database['slow_queries_count']}
- **Total Commits**: {database['query_statistics'].get('commits', 0):,}
- **Total Rollbacks**: {database['query_statistics'].get('rollbacks', 0):,}

## Error Analysis
"""
        
        errors = self.results['error_analysis']['errors_by_type']
        if errors:
            report += "| Error Type | Count |\n|------------|-------|\n"
            for error_type, count in errors.items():
                report += f"| {error_type} | {count:,} |\n"
        else:
            report += "No errors detected ✅\n"
        
        report += f"""
## Recommendations

"""
        
        # Add specific recommendations based on results
        recommendations = self.generate_recommendations()
        for rec in recommendations:
            report += f"- {rec}\n"
        
        return report
    
    def generate_html_report(self) -> str:
        """Generate HTML report with charts"""
        # Basic HTML report (could be enhanced with JavaScript charts)
        markdown_content = self.generate_markdown_report()
        
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Load Test Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; }}
        table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #f2f2f2; }}
        .passed {{ color: green; }}
        .failed {{ color: red; }}
        .summary {{ background-color: #f9f9f9; padding: 20px; border-radius: 5px; }}
    </style>
</head>
<body>
    <pre>{markdown_content}</pre>
</body>
</html>
"""
        return html
    
    def generate_recommendations(self) -> List[str]:
        """Generate actionable recommendations based on test results"""
        recommendations = []
        compliance = self.results['threshold_compliance']
        performance = self.results['performance_metrics']
        resources = self.results['resource_utilization']
        
        if not compliance['overall_pass']:
            recommendations.append("⚠️ Performance thresholds not met - system requires optimization")
        
        if not compliance['checks']['avg_response_time']['passed']:
            recommendations.append("🐌 Average response time too high - consider database query optimization or caching")
        
        if not compliance['checks']['max_cpu_usage']['passed']:
            recommendations.append("🔥 CPU usage too high - consider horizontal scaling or code optimization")
        
        if not compliance['checks']['max_memory_usage']['passed']:
            recommendations.append("💾 Memory usage too high - check for memory leaks or increase server memory")
        
        if resources['max_cpu_percent'] > 70:
            recommendations.append("📈 Consider implementing auto-scaling when CPU > 70%")
        
        if self.results['database_metrics']['slow_queries_count'] > 0:
            recommendations.append("🐢 Slow database queries detected - review and optimize query performance")
        
        if self.results['connection_metrics']['connection_success_rate_percent'] < 95:
            recommendations.append("🔗 Connection success rate low - investigate network or server issues")
        
        if self.results['game_flow_metrics']['game_completion_rate_percent'] < 90:
            recommendations.append("🎮 Game completion rate low - investigate user experience or timeout issues")
        
        if len(recommendations) == 0:
            recommendations.append("✅ System performance meets all requirements")
            recommendations.append("🚀 Ready for production load")
        
        return recommendations

# Command line interface
async def main():
    parser = argparse.ArgumentParser(description="Comprehensive Load Testing for Hokm Game Server")
    parser.add_argument("--users", type=int, default=100, help="Number of concurrent users")
    parser.add_argument("--duration", type=int, default=30, help="Test duration in minutes")
    parser.add_argument("--ramp-up", type=int, default=5, help="Ramp-up time in minutes")
    parser.add_argument("--server-url", default="http://localhost:8000", help="Server URL")
    parser.add_argument("--postgres-url", default="postgresql://localhost:5432/hokm_test", help="PostgreSQL URL")
    parser.add_argument("--redis-url", default="redis://localhost:6379", help="Redis URL")
    parser.add_argument("--output-dir", default="./load_test_reports", help="Output directory for reports")
    parser.add_argument("--config", help="Configuration file path (JSON)")
    
    args = parser.parse_args()
    
    # Load configuration
    config = {
        'server_url': args.server_url,
        'postgres_url': args.postgres_url,
        'redis_url': args.redis_url
    }
    
    if args.config and Path(args.config).exists():
        with open(args.config) as f:
            config.update(json.load(f))
    
    # Run load test
    runner = LoadTestRunner(config)
    
    try:
        logger.info("🚀 Starting comprehensive load test")
        results = await runner.run_load_test(args.users, args.duration, args.ramp_up)
        
        # Generate reports
        reporter = LoadTestReporter(results, config)
        report_path = reporter.generate_report(args.output_dir)
        
        # Print summary
        print(f"\n{'='*60}")
        print("LOAD TEST SUMMARY")
        print(f"{'='*60}")
        print(f"Duration: {results['test_summary']['duration_seconds']:.1f}s")
        print(f"Throughput: {results['test_summary']['throughput_ops_per_sec']:.1f} ops/sec")
        print(f"Error Rate: {results['test_summary']['error_rate_percent']:.2f}%")
        print(f"Avg Response Time: {results['performance_metrics']['avg_response_time_ms']:.1f}ms")
        print(f"P95 Response Time: {results['performance_metrics']['p95_response_time_ms']:.1f}ms")
        print(f"Status: {'PASSED' if results['threshold_compliance']['overall_pass'] else 'FAILED'}")
        print(f"Report: {report_path}")
        print(f"{'='*60}")
        
        # Exit with appropriate code
        sys.exit(0 if results['threshold_compliance']['overall_pass'] else 1)
        
    except KeyboardInterrupt:
        logger.info("🛑 Load test interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"💥 Load test failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
