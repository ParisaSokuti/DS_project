"""
Stress Test Suite for Hokm Game Server

This comprehensive stress test simulates high-load scenarios including:
1. 100 concurrent players connecting
2. Rapid join/leave cycles
3. Multiple parallel games
4. Network interruptions during gameplay
5. Redis connection failures

Measures and reports on:
- Connection times and latency
- Memory usage patterns
- Server stability under load
- Error rates and recovery
- Performance bottlenecks

Usage:
    python test_stress.py
    python test_stress.py --quick    # Reduced load for faster testing
    python test_stress.py --report   # Generate detailed HTML report
"""

import asyncio
import websockets
import json
import time
import psutil
import random
import statistics
import threading
import subprocess
import sys
import argparse
from datetime import datetime, timedelta
from collections import defaultdict, deque
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional, Tuple
import concurrent.futures
import redis


@dataclass
class StressTestMetrics:
    """Container for all stress test metrics"""
    test_name: str
    start_time: float
    end_time: float
    duration: float
    
    # Connection metrics
    connection_attempts: int = 0
    successful_connections: int = 0
    failed_connections: int = 0
    connection_times: List[float] = None
    avg_connection_time: float = 0.0
    max_connection_time: float = 0.0
    min_connection_time: float = 0.0
    
    # Performance metrics
    memory_start: float = 0.0
    memory_peak: float = 0.0
    memory_end: float = 0.0
    memory_samples: List[float] = None
    cpu_samples: List[float] = None
    
    # Game metrics
    games_created: int = 0
    games_completed: int = 0
    messages_sent: int = 0
    messages_received: int = 0
    errors: List[str] = None
    
    # Latency metrics
    latency_samples: List[float] = None
    avg_latency: float = 0.0
    max_latency: float = 0.0
    p95_latency: float = 0.0
    p99_latency: float = 0.0
    
    # Success rates
    connection_success_rate: float = 0.0
    message_success_rate: float = 0.0
    overall_success_rate: float = 0.0
    
    def __post_init__(self):
        if self.connection_times is None:
            self.connection_times = []
        if self.memory_samples is None:
            self.memory_samples = []
        if self.cpu_samples is None:
            self.cpu_samples = []
        if self.errors is None:
            self.errors = []
        if self.latency_samples is None:
            self.latency_samples = []
    
    def calculate_derived_metrics(self):
        """Calculate derived metrics from raw data"""
        if self.connection_times:
            self.avg_connection_time = statistics.mean(self.connection_times)
            self.max_connection_time = max(self.connection_times)
            self.min_connection_time = min(self.connection_times)
        
        if self.latency_samples:
            self.avg_latency = statistics.mean(self.latency_samples)
            self.max_latency = max(self.latency_samples)
            if len(self.latency_samples) >= 20:  # Need sufficient samples for percentiles
                sorted_latencies = sorted(self.latency_samples)
                self.p95_latency = sorted_latencies[int(0.95 * len(sorted_latencies))]
                self.p99_latency = sorted_latencies[int(0.99 * len(sorted_latencies))]
        
        if self.connection_attempts > 0:
            self.connection_success_rate = (self.successful_connections / self.connection_attempts) * 100
        
        if self.messages_sent > 0:
            self.message_success_rate = (self.messages_received / self.messages_sent) * 100
        
        # Overall success rate combines connection and message success
        self.overall_success_rate = (self.connection_success_rate + self.message_success_rate) / 2


class PerformanceMonitor:
    """Monitor system performance during stress tests"""
    
    def __init__(self):
        self.monitoring = False
        self.memory_samples = []
        self.cpu_samples = []
        self.start_time = 0
        self.monitor_thread = None
    
    def start_monitoring(self):
        """Start performance monitoring in background thread"""
        self.monitoring = True
        self.start_time = time.time()
        self.memory_samples = []
        self.cpu_samples = []
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
    
    def stop_monitoring(self):
        """Stop performance monitoring"""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=1.0)
    
    def _monitor_loop(self):
        """Main monitoring loop"""
        while self.monitoring:
            try:
                # Get current process
                process = psutil.Process()
                
                # Memory usage in MB
                memory_mb = process.memory_info().rss / 1024 / 1024
                self.memory_samples.append(memory_mb)
                
                # CPU usage percentage
                cpu_percent = process.cpu_percent()
                self.cpu_samples.append(cpu_percent)
                
                time.sleep(0.5)  # Sample every 500ms
            except Exception as e:
                print(f"[WARNING] Performance monitoring error: {e}")
                break
    
    def get_metrics(self) -> Dict:
        """Get current performance metrics"""
        return {
            'memory_samples': self.memory_samples.copy(),
            'cpu_samples': self.cpu_samples.copy(),
            'memory_start': self.memory_samples[0] if self.memory_samples else 0,
            'memory_peak': max(self.memory_samples) if self.memory_samples else 0,
            'memory_end': self.memory_samples[-1] if self.memory_samples else 0,
            'avg_cpu': statistics.mean(self.cpu_samples) if self.cpu_samples else 0,
            'peak_cpu': max(self.cpu_samples) if self.cpu_samples else 0
        }


class StressTestClient:
    """Individual client for stress testing"""
    
    def __init__(self, client_id: str, server_url: str = "ws://localhost:8765"):
        self.client_id = client_id
        self.server_url = server_url
        self.websocket = None
        self.connected = False
        self.messages_sent = 0
        self.messages_received = 0
        self.connection_time = 0
        self.latency_samples = []
        self.errors = []
    
    async def connect(self) -> Tuple[bool, float]:
        """Connect to server and measure connection time"""
        start_time = time.time()
        try:
            self.websocket = await websockets.connect(self.server_url, timeout=10)
            self.connected = True
            self.connection_time = time.time() - start_time
            return True, self.connection_time
        except Exception as e:
            self.errors.append(f"Connection failed: {str(e)}")
            self.connection_time = time.time() - start_time
            return False, self.connection_time
    
    async def disconnect(self):
        """Disconnect from server"""
        if self.websocket and not self.websocket.closed:
            await self.websocket.close()
        self.connected = False
    
    async def send_message(self, message: Dict) -> Tuple[bool, float]:
        """Send message and measure latency"""
        if not self.connected or not self.websocket:
            return False, 0
        
        start_time = time.time()
        try:
            await self.websocket.send(json.dumps(message))
            self.messages_sent += 1
            
            # Wait for response with timeout
            response = await asyncio.wait_for(self.websocket.recv(), timeout=5.0)
            latency = time.time() - start_time
            self.latency_samples.append(latency)
            self.messages_received += 1
            return True, latency
        except Exception as e:
            latency = time.time() - start_time
            self.errors.append(f"Message failed: {str(e)}")
            return False, latency
    
    async def join_game(self, room_code: str) -> bool:
        """Join a game room"""
        message = {
            'type': 'join',
            'room_code': room_code,
            'username': f'StressTest_{self.client_id}'
        }
        success, _ = await self.send_message(message)
        return success
    
    async def simulate_gameplay(self, room_code: str, duration: float = 10.0):
        """Simulate gameplay for specified duration"""
        end_time = time.time() + duration
        
        # Join the game
        if not await self.join_game(room_code):
            return
        
        # Send periodic messages to simulate gameplay
        while time.time() < end_time and self.connected:
            try:
                # Send keep-alive or status messages
                message = {
                    'type': 'status',
                    'room_code': room_code,
                    'timestamp': time.time()
                }
                await self.send_message(message)
                await asyncio.sleep(random.uniform(0.5, 2.0))
            except Exception as e:
                self.errors.append(f"Gameplay simulation error: {str(e)}")
                break


class RedisStressTester:
    """Test Redis performance under stress"""
    
    def __init__(self):
        self.redis_client = None
        self.original_redis_config = None
    
    async def test_redis_failures(self) -> StressTestMetrics:
        """Test server behavior when Redis fails"""
        metrics = StressTestMetrics("Redis Failure Test", time.time(), 0, 0)
        
        try:
            # Connect to Redis
            self.redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)
            
            # Test 1: Redis disconnect during game
            print("  Testing Redis disconnection during active games...")
            
            # Create some test clients
            clients = []
            for i in range(5):
                client = StressTestClient(f"redis_test_{i}")
                connected, conn_time = await client.connect()
                if connected:
                    clients.append(client)
                    metrics.successful_connections += 1
                    metrics.connection_times.append(conn_time)
                metrics.connection_attempts += 1
            
            # Join games
            room_code = "REDIS_STRESS_TEST"
            for client in clients:
                await client.join_game(room_code)
                metrics.messages_sent += client.messages_sent
                metrics.messages_received += client.messages_received
            
            # Stop Redis (simulate failure)
            print("  Simulating Redis failure...")
            subprocess.run(['redis-cli', 'shutdown', 'nosave'], 
                          capture_output=True, timeout=5)
            
            # Try to continue gameplay
            for client in clients:
                success, latency = await client.send_message({
                    'type': 'play_card',
                    'room_code': room_code,
                    'card': '2_hearts'
                })
                metrics.latency_samples.append(latency)
                if not success:
                    metrics.errors.extend(client.errors)
            
            # Restart Redis
            print("  Restarting Redis...")
            subprocess.run(['redis-server', '--daemonize', 'yes'], 
                          capture_output=True, timeout=10)
            time.sleep(2)  # Wait for Redis to start
            
            # Test recovery
            for client in clients:
                success, latency = await client.send_message({
                    'type': 'status',
                    'room_code': room_code
                })
                metrics.latency_samples.append(latency)
            
            # Cleanup
            for client in clients:
                await client.disconnect()
            
        except Exception as e:
            metrics.errors.append(f"Redis stress test error: {str(e)}")
        
        metrics.end_time = time.time()
        metrics.duration = metrics.end_time - metrics.start_time
        metrics.calculate_derived_metrics()
        return metrics


class HokmStressTester:
    """Main stress testing class"""
    
    def __init__(self, server_url: str = "ws://localhost:8765", quick_mode: bool = False):
        self.server_url = server_url
        self.quick_mode = quick_mode
        self.performance_monitor = PerformanceMonitor()
        self.all_metrics = []
        
        # Adjust test parameters for quick mode
        if quick_mode:
            self.concurrent_players = 20
            self.rapid_cycles = 10
            self.parallel_games = 3
            self.test_duration = 30
        else:
            self.concurrent_players = 100
            self.rapid_cycles = 50
            self.parallel_games = 10
            self.test_duration = 120
    
    async def test_concurrent_connections(self) -> StressTestMetrics:
        """Test 1: 100 concurrent player connections"""
        print(f"🔗 Testing {self.concurrent_players} concurrent connections...")
        
        metrics = StressTestMetrics("Concurrent Connections", time.time(), 0, 0)
        self.performance_monitor.start_monitoring()
        
        # Create all clients
        clients = []
        connection_tasks = []
        
        for i in range(self.concurrent_players):
            client = StressTestClient(f"concurrent_{i}")
            clients.append(client)
            connection_tasks.append(client.connect())
        
        # Connect all clients simultaneously
        print(f"  Connecting {self.concurrent_players} clients simultaneously...")
        results = await asyncio.gather(*connection_tasks, return_exceptions=True)
        
        # Process results
        for i, (client, result) in enumerate(zip(clients, results)):
            metrics.connection_attempts += 1
            if isinstance(result, Exception):
                metrics.failed_connections += 1
                metrics.errors.append(f"Client {i}: {str(result)}")
            else:
                success, conn_time = result
                if success:
                    metrics.successful_connections += 1
                    metrics.connection_times.append(conn_time)
                else:
                    metrics.failed_connections += 1
                    metrics.errors.extend(client.errors)
        
        # Test messaging with all connected clients
        print("  Testing message broadcasting...")
        message_tasks = []
        for client in clients:
            if client.connected:
                message = {
                    'type': 'join',
                    'room_code': 'STRESS_TEST_ROOM',
                    'username': client.client_id
                }
                message_tasks.append(client.send_message(message))
        
        if message_tasks:
            message_results = await asyncio.gather(*message_tasks, return_exceptions=True)
            for client, result in zip(clients, message_results):
                if not isinstance(result, Exception):
                    success, latency = result
                    metrics.latency_samples.append(latency)
                    metrics.messages_sent += client.messages_sent
                    metrics.messages_received += client.messages_received
        
        # Cleanup
        disconnect_tasks = [client.disconnect() for client in clients if client.connected]
        if disconnect_tasks:
            await asyncio.gather(*disconnect_tasks, return_exceptions=True)
        
        self.performance_monitor.stop_monitoring()
        perf_metrics = self.performance_monitor.get_metrics()
        metrics.memory_samples = perf_metrics['memory_samples']
        metrics.cpu_samples = perf_metrics['cpu_samples']
        metrics.memory_start = perf_metrics['memory_start']
        metrics.memory_peak = perf_metrics['memory_peak']
        metrics.memory_end = perf_metrics['memory_end']
        
        metrics.end_time = time.time()
        metrics.duration = metrics.end_time - metrics.start_time
        metrics.calculate_derived_metrics()
        
        return metrics
    
    async def test_rapid_join_leave(self) -> StressTestMetrics:
        """Test 2: Rapid join/leave cycles"""
        print(f"🔄 Testing {self.rapid_cycles} rapid join/leave cycles...")
        
        metrics = StressTestMetrics("Rapid Join/Leave", time.time(), 0, 0)
        self.performance_monitor.start_monitoring()
        
        room_code = "RAPID_TEST_ROOM"
        
        for cycle in range(self.rapid_cycles):
            if cycle % 10 == 0:
                print(f"  Cycle {cycle + 1}/{self.rapid_cycles}")
            
            # Create client
            client = StressTestClient(f"rapid_{cycle}")
            
            # Connect
            metrics.connection_attempts += 1
            success, conn_time = await client.connect()
            if success:
                metrics.successful_connections += 1
                metrics.connection_times.append(conn_time)
                
                # Join game
                join_success, join_latency = await client.send_message({
                    'type': 'join',
                    'room_code': room_code,
                    'username': client.client_id
                })
                
                if join_success:
                    metrics.latency_samples.append(join_latency)
                    metrics.messages_sent += 1
                    metrics.messages_received += 1
                    
                    # Brief activity
                    await client.send_message({
                        'type': 'status',
                        'room_code': room_code
                    })
                    
                    # Leave (disconnect)
                    await client.disconnect()
                else:
                    metrics.errors.extend(client.errors)
            else:
                metrics.failed_connections += 1
                metrics.errors.extend(client.errors)
            
            # Small delay between cycles
            await asyncio.sleep(0.1)
        
        self.performance_monitor.stop_monitoring()
        perf_metrics = self.performance_monitor.get_metrics()
        metrics.memory_samples = perf_metrics['memory_samples']
        metrics.memory_start = perf_metrics['memory_start']
        metrics.memory_peak = perf_metrics['memory_peak']
        metrics.memory_end = perf_metrics['memory_end']
        
        metrics.end_time = time.time()
        metrics.duration = metrics.end_time - metrics.start_time
        metrics.calculate_derived_metrics()
        
        return metrics
    
    async def test_parallel_games(self) -> StressTestMetrics:
        """Test 3: Multiple parallel games"""
        print(f"🎮 Testing {self.parallel_games} parallel games...")
        
        metrics = StressTestMetrics("Parallel Games", time.time(), 0, 0)
        self.performance_monitor.start_monitoring()
        
        # Create game tasks
        game_tasks = []
        for game_id in range(self.parallel_games):
            room_code = f"PARALLEL_GAME_{game_id}"
            task = self._simulate_parallel_game(room_code, metrics)
            game_tasks.append(task)
        
        # Run all games in parallel
        results = await asyncio.gather(*game_tasks, return_exceptions=True)
        
        # Process results
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                metrics.errors.append(f"Parallel game {i} failed: {str(result)}")
            else:
                metrics.games_completed += 1
        
        self.performance_monitor.stop_monitoring()
        perf_metrics = self.performance_monitor.get_metrics()
        metrics.memory_samples = perf_metrics['memory_samples']
        metrics.memory_start = perf_metrics['memory_start']
        metrics.memory_peak = perf_metrics['memory_peak']
        metrics.memory_end = perf_metrics['memory_end']
        
        metrics.end_time = time.time()
        metrics.duration = metrics.end_time - metrics.start_time
        metrics.calculate_derived_metrics()
        
        return metrics
    
    async def _simulate_parallel_game(self, room_code: str, metrics: StressTestMetrics):
        """Simulate a single game with 4 players"""
        clients = []
        
        try:
            # Create 4 players
            for i in range(4):
                client = StressTestClient(f"{room_code}_player_{i}")
                
                # Connect
                metrics.connection_attempts += 1
                success, conn_time = await client.connect()
                if success:
                    clients.append(client)
                    metrics.successful_connections += 1
                    metrics.connection_times.append(conn_time)
                    
                    # Join game
                    await client.join_game(room_code)
                else:
                    metrics.failed_connections += 1
                    metrics.errors.extend(client.errors)
            
            # Simulate gameplay
            if len(clients) >= 2:  # Need at least 2 players
                metrics.games_created += 1
                
                # Parallel gameplay simulation
                gameplay_tasks = []
                for client in clients:
                    task = client.simulate_gameplay(room_code, self.test_duration / 4)
                    gameplay_tasks.append(task)
                
                await asyncio.gather(*gameplay_tasks, return_exceptions=True)
                
                # Collect metrics from clients
                for client in clients:
                    metrics.messages_sent += client.messages_sent
                    metrics.messages_received += client.messages_received
                    metrics.latency_samples.extend(client.latency_samples)
                    metrics.errors.extend(client.errors)
        
        finally:
            # Cleanup
            for client in clients:
                await client.disconnect()
    
    async def test_network_interruptions(self) -> StressTestMetrics:
        """Test 4: Network interruptions during gameplay"""
        print("📡 Testing network interruptions during gameplay...")
        
        metrics = StressTestMetrics("Network Interruptions", time.time(), 0, 0)
        self.performance_monitor.start_monitoring()
        
        room_code = "NETWORK_TEST_ROOM"
        clients = []
        
        try:
            # Setup clients
            for i in range(8):
                client = StressTestClient(f"network_test_{i}")
                metrics.connection_attempts += 1
                success, conn_time = await client.connect()
                
                if success:
                    clients.append(client)
                    metrics.successful_connections += 1
                    metrics.connection_times.append(conn_time)
                    await client.join_game(room_code)
                else:
                    metrics.failed_connections += 1
                    metrics.errors.extend(client.errors)
            
            if len(clients) < 4:
                metrics.errors.append("Insufficient clients for network test")
                return metrics
            
            # Start gameplay
            print("  Starting gameplay...")
            gameplay_tasks = []
            for client in clients:
                task = client.simulate_gameplay(room_code, 60)
                gameplay_tasks.append(task)
            
            # Run gameplay for a bit
            await asyncio.sleep(10)
            
            # Simulate network interruption by disconnecting random clients
            print("  Simulating network interruptions...")
            interruption_targets = random.sample(clients, len(clients) // 2)
            
            for client in interruption_targets:
                await client.disconnect()
                print(f"    Disconnected {client.client_id}")
            
            # Wait a bit
            await asyncio.sleep(5)
            
            # Attempt reconnections
            print("  Attempting reconnections...")
            for client in interruption_targets:
                success, conn_time = await client.connect()
                if success:
                    metrics.connection_times.append(conn_time)
                    await client.join_game(room_code)
                    print(f"    Reconnected {client.client_id}")
                else:
                    metrics.errors.extend(client.errors)
            
            # Continue gameplay
            await asyncio.sleep(10)
            
            # Collect final metrics
            for client in clients:
                metrics.messages_sent += client.messages_sent
                metrics.messages_received += client.messages_received
                metrics.latency_samples.extend(client.latency_samples)
                metrics.errors.extend(client.errors)
        
        finally:
            # Cleanup
            for client in clients:
                await client.disconnect()
        
        self.performance_monitor.stop_monitoring()
        perf_metrics = self.performance_monitor.get_metrics()
        metrics.memory_samples = perf_metrics['memory_samples']
        metrics.memory_start = perf_metrics['memory_start']
        metrics.memory_peak = perf_metrics['memory_peak']
        metrics.memory_end = perf_metrics['memory_end']
        
        metrics.end_time = time.time()
        metrics.duration = metrics.end_time - metrics.start_time
        metrics.calculate_derived_metrics()
        
        return metrics
    
    async def run_all_tests(self) -> List[StressTestMetrics]:
        """Run all stress tests"""
        print("🚀 Starting Comprehensive Stress Test Suite")
        print("=" * 60)
        
        if self.quick_mode:
            print("⚡ QUICK MODE: Reduced load for faster testing")
        else:
            print("🔥 FULL MODE: Maximum stress testing")
        
        print(f"Server: {self.server_url}")
        print(f"Concurrent Players: {self.concurrent_players}")
        print(f"Rapid Cycles: {self.rapid_cycles}")
        print(f"Parallel Games: {self.parallel_games}")
        print("=" * 60)
        
        all_metrics = []
        
        # Test 1: Concurrent Connections
        try:
            metrics1 = await self.test_concurrent_connections()
            all_metrics.append(metrics1)
            self._print_test_summary(metrics1)
        except Exception as e:
            print(f"❌ Concurrent connections test failed: {e}")
        
        print("\nPausing 3 seconds between tests...")
        await asyncio.sleep(3)
        
        # Test 2: Rapid Join/Leave
        try:
            metrics2 = await self.test_rapid_join_leave()
            all_metrics.append(metrics2)
            self._print_test_summary(metrics2)
        except Exception as e:
            print(f"❌ Rapid join/leave test failed: {e}")
        
        print("\nPausing 3 seconds between tests...")
        await asyncio.sleep(3)
        
        # Test 3: Parallel Games
        try:
            metrics3 = await self.test_parallel_games()
            all_metrics.append(metrics3)
            self._print_test_summary(metrics3)
        except Exception as e:
            print(f"❌ Parallel games test failed: {e}")
        
        print("\nPausing 3 seconds between tests...")
        await asyncio.sleep(3)
        
        # Test 4: Network Interruptions
        try:
            metrics4 = await self.test_network_interruptions()
            all_metrics.append(metrics4)
            self._print_test_summary(metrics4)
        except Exception as e:
            print(f"❌ Network interruptions test failed: {e}")
        
        print("\nPausing 3 seconds between tests...")
        await asyncio.sleep(3)
        
        # Test 5: Redis Failures
        try:
            redis_tester = RedisStressTester()
            metrics5 = await redis_tester.test_redis_failures()
            all_metrics.append(metrics5)
            self._print_test_summary(metrics5)
        except Exception as e:
            print(f"❌ Redis failure test failed: {e}")
        
        self.all_metrics = all_metrics
        return all_metrics
    
    def _print_test_summary(self, metrics: StressTestMetrics):
        """Print summary of individual test"""
        print(f"\n📊 {metrics.test_name} Results:")
        print(f"  Duration: {metrics.duration:.1f}s")
        print(f"  Connections: {metrics.successful_connections}/{metrics.connection_attempts} ({metrics.connection_success_rate:.1f}%)")
        
        if metrics.connection_times:
            print(f"  Avg Connection Time: {metrics.avg_connection_time:.3f}s")
            print(f"  Max Connection Time: {metrics.max_connection_time:.3f}s")
        
        if metrics.latency_samples:
            print(f"  Avg Latency: {metrics.avg_latency:.3f}s")
            print(f"  Max Latency: {metrics.max_latency:.3f}s")
            if metrics.p95_latency > 0:
                print(f"  P95 Latency: {metrics.p95_latency:.3f}s")
        
        if metrics.memory_samples:
            print(f"  Memory: {metrics.memory_start:.1f}MB → {metrics.memory_peak:.1f}MB → {metrics.memory_end:.1f}MB")
        
        print(f"  Messages: {metrics.messages_received}/{metrics.messages_sent} ({metrics.message_success_rate:.1f}%)")
        print(f"  Errors: {len(metrics.errors)}")
        
        if metrics.errors and len(metrics.errors) <= 5:
            for error in metrics.errors[:3]:
                print(f"    - {error}")
            if len(metrics.errors) > 3:
                print(f"    ... and {len(metrics.errors) - 3} more")
    
    def generate_report(self, filename: str = None):
        """Generate comprehensive HTML report"""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"stress_test_report_{timestamp}.html"
        
        html_content = self._generate_html_report()
        
        with open(filename, 'w') as f:
            f.write(html_content)
        
        print(f"📄 Detailed report generated: {filename}")
        return filename
    
    def _generate_html_report(self) -> str:
        """Generate HTML report content"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Hokm Server Stress Test Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; }}
        .header {{ background: #2c3e50; color: white; padding: 20px; border-radius: 5px; }}
        .summary {{ background: #ecf0f1; padding: 15px; margin: 20px 0; border-radius: 5px; }}
        .test-result {{ margin: 20px 0; padding: 15px; border: 1px solid #bdc3c7; border-radius: 5px; }}
        .pass {{ border-left: 5px solid #27ae60; }}
        .fail {{ border-left: 5px solid #e74c3c; }}
        .warning {{ border-left: 5px solid #f39c12; }}
        .metrics {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 10px; }}
        .metric {{ background: #f8f9fa; padding: 10px; border-radius: 3px; }}
        .errors {{ background: #ffebee; padding: 10px; margin: 10px 0; border-radius: 3px; }}
        table {{ width: 100%; border-collapse: collapse; margin: 10px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #f2f2f2; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🚀 Hokm Server Stress Test Report</h1>
        <p>Generated: {timestamp}</p>
        <p>Mode: {'Quick Mode' if self.quick_mode else 'Full Stress Mode'}</p>
    </div>
"""
        
        # Overall summary
        if self.all_metrics:
            total_connections = sum(m.connection_attempts for m in self.all_metrics)
            successful_connections = sum(m.successful_connections for m in self.all_metrics)
            total_errors = sum(len(m.errors) for m in self.all_metrics)
            total_duration = sum(m.duration for m in self.all_metrics)
            
            overall_success = (successful_connections / total_connections * 100) if total_connections > 0 else 0
            
            html += f"""
    <div class="summary">
        <h2>📊 Overall Summary</h2>
        <div class="metrics">
            <div class="metric">
                <strong>Total Tests:</strong> {len(self.all_metrics)}
            </div>
            <div class="metric">
                <strong>Total Duration:</strong> {total_duration:.1f}s
            </div>
            <div class="metric">
                <strong>Connection Success:</strong> {successful_connections}/{total_connections} ({overall_success:.1f}%)
            </div>
            <div class="metric">
                <strong>Total Errors:</strong> {total_errors}
            </div>
        </div>
    </div>
"""
            
            # Individual test results
            for i, metrics in enumerate(self.all_metrics):
                status_class = "pass" if metrics.overall_success_rate > 80 else "fail" if metrics.overall_success_rate < 50 else "warning"
                
                html += f"""
    <div class="test-result {status_class}">
        <h3>Test {i+1}: {metrics.test_name}</h3>
        <div class="metrics">
            <div class="metric">
                <strong>Duration:</strong> {metrics.duration:.1f}s
            </div>
            <div class="metric">
                <strong>Success Rate:</strong> {metrics.overall_success_rate:.1f}%
            </div>
            <div class="metric">
                <strong>Connections:</strong> {metrics.successful_connections}/{metrics.connection_attempts}
            </div>
            <div class="metric">
                <strong>Avg Connection Time:</strong> {metrics.avg_connection_time:.3f}s
            </div>
            <div class="metric">
                <strong>Avg Latency:</strong> {metrics.avg_latency:.3f}s
            </div>
            <div class="metric">
                <strong>Memory Peak:</strong> {metrics.memory_peak:.1f}MB
            </div>
        </div>
"""
                
                if metrics.errors:
                    html += f"""
        <div class="errors">
            <strong>Errors ({len(metrics.errors)}):</strong>
            <ul>
"""
                    for error in metrics.errors[:10]:  # Show first 10 errors
                        html += f"<li>{error}</li>"
                    if len(metrics.errors) > 10:
                        html += f"<li>... and {len(metrics.errors) - 10} more errors</li>"
                    html += "</ul></div>"
                
                html += "</div>"
        
        html += """
</body>
</html>
"""
        return html


async def main():
    """Main function"""
    parser = argparse.ArgumentParser(description='Hokm Server Stress Test')
    parser.add_argument('--quick', action='store_true', help='Run in quick mode (reduced load)')
    parser.add_argument('--report', action='store_true', help='Generate HTML report')
    parser.add_argument('--server', default='ws://localhost:8765', help='Server URL')
    
    args = parser.parse_args()
    
    # Check if server is running
    print("🔍 Checking server availability...")
    try:
        import websockets
        test_ws = await websockets.connect(args.server, timeout=5)
        await test_ws.close()
        print("✅ Server is reachable")
    except Exception as e:
        print(f"❌ Cannot connect to server: {e}")
        print("Please ensure the server is running on", args.server)
        return
    
    # Run stress tests
    tester = HokmStressTester(args.server, args.quick)
    metrics = await tester.run_all_tests()
    
    # Print final summary
    print("\n" + "=" * 60)
    print("🎯 FINAL STRESS TEST SUMMARY")
    print("=" * 60)
    
    if metrics:
        total_tests = len(metrics)
        passed_tests = sum(1 for m in metrics if m.overall_success_rate > 80)
        warning_tests = sum(1 for m in metrics if 50 <= m.overall_success_rate <= 80)
        failed_tests = sum(1 for m in metrics if m.overall_success_rate < 50)
        
        print(f"Tests Run: {total_tests}")
        print(f"✅ Passed: {passed_tests}")
        print(f"⚠️  Warnings: {warning_tests}")
        print(f"❌ Failed: {failed_tests}")
        
        overall_rating = "EXCELLENT" if failed_tests == 0 and warning_tests <= 1 else \
                        "GOOD" if failed_tests <= 1 else \
                        "MODERATE" if failed_tests <= 2 else "POOR"
        
        print(f"\n🏆 Overall Rating: {overall_rating}")
        
        if failed_tests > 0:
            print("\n🔧 Recommendations:")
            print("- Consider optimizing connection handling")
            print("- Implement better error recovery")
            print("- Add connection pooling or rate limiting")
            print("- Monitor memory usage patterns")
    
    # Generate report if requested
    if args.report and metrics:
        report_file = tester.generate_report()
        print(f"\n📊 Open {report_file} in your browser for detailed analysis")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⚠️ Test interrupted by user")
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
        sys.exit(1)
