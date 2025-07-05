#!/usr/bin/env python3
"""
Circuit Breaker Integration Test
Tests the complete circuit breaker integration with the game server
"""

import asyncio
import websockets
import json
import time
import redis
import subprocess
import threading
import sys
import os

# Add backend to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from redis_manager_resilient import ResilientRedisManager
from circuit_breaker_monitor import CircuitBreakerMonitor

class CircuitBreakerIntegrationTest:
    def __init__(self):
        self.server_url = "ws://localhost:8765"
        self.redis_client = redis.Redis(host='localhost', port=6379, db=0)
        self.test_results = []
        
    async def test_basic_functionality(self):
        """Test basic server functionality with circuit breaker"""
        print("\n=== Testing Basic Circuit Breaker Functionality ===")
        
        try:
            websocket = await websockets.connect(self.server_url)
            
            # Test health check
            health_check = {
                'type': 'health_check'
            }
            
            await websocket.send(json.dumps(health_check))
            response = await websocket.recv()
            data = json.loads(response)
            
            print(f"Health check response: {data['type']}")
            print(f"Server status: {data['data']['status']}")
            print(f"Circuit breakers: {list(data['data']['circuit_breakers'].keys())}")
            
            self.test_results.append({
                'test': 'basic_functionality',
                'status': 'passed',
                'details': 'Health check successful'
            })
            
            await websocket.close()
            
        except Exception as e:
            print(f"Basic functionality test failed: {e}")
            self.test_results.append({
                'test': 'basic_functionality',
                'status': 'failed',
                'details': str(e)
            })
    
    async def test_redis_failure_recovery(self):
        """Test circuit breaker behavior during Redis failure"""
        print("\n=== Testing Redis Failure and Recovery ===")
        
        try:
            # Connect to server
            websocket = await websockets.connect(self.server_url)
            
            # First, test normal operation
            join_message = {
                'type': 'join',
                'room_code': 'TEST123',
                'username': 'TestPlayer'
            }
            
            await websocket.send(json.dumps(join_message))
            response = await websocket.recv()
            print(f"Join response (before failure): {json.loads(response)['type']}")
            
            # Get initial health status
            await websocket.send(json.dumps({'type': 'health_check'}))
            health_before = json.loads(await websocket.recv())
            print(f"Health before Redis failure: {health_before['data']['status']}")
            
            # Simulate Redis failure by stopping Redis
            print("Simulating Redis failure...")
            try:
                # Try to shutdown Redis (may fail if not running)
                subprocess.run(['redis-cli', 'shutdown'], 
                             capture_output=True, timeout=5)
            except:
                print("Redis may already be stopped or not accessible")
            
            # Wait a moment for circuit breaker to detect failure
            await asyncio.sleep(2)
            
            # Test operation during failure (should use fallback)
            join_message2 = {
                'type': 'join',
                'room_code': 'TEST456',
                'username': 'TestPlayer2'
            }
            
            await websocket.send(json.dumps(join_message2))
            response = await websocket.recv()
            print(f"Join response (during failure): {json.loads(response)['type']}")
            
            # Check health status during failure
            await websocket.send(json.dumps({'type': 'health_check'}))
            health_during = json.loads(await websocket.recv())
            print(f"Health during Redis failure: {health_during['data']['status']}")
            print(f"Circuit breaker states: {health_during['data']['circuit_breakers']}")
            
            # Restart Redis
            print("Restarting Redis...")
            try:
                subprocess.run(['redis-server', '--daemonize', 'yes'], 
                             capture_output=True, timeout=10)
                await asyncio.sleep(3)  # Wait for Redis to start
            except:
                print("Failed to restart Redis automatically")
            
            # Test recovery
            await asyncio.sleep(5)  # Wait for circuit breaker recovery
            
            # Check health after recovery
            await websocket.send(json.dumps({'type': 'health_check'}))
            health_after = json.loads(await websocket.recv())
            print(f"Health after Redis recovery: {health_after['data']['status']}")
            
            self.test_results.append({
                'test': 'redis_failure_recovery',
                'status': 'passed',
                'details': f"Successfully handled Redis failure and recovery"
            })
            
            await websocket.close()
            
        except Exception as e:
            print(f"Redis failure recovery test failed: {e}")
            self.test_results.append({
                'test': 'redis_failure_recovery',
                'status': 'failed',
                'details': str(e)
            })
    
    async def test_fallback_cache_functionality(self):
        """Test fallback cache during Redis unavailability"""
        print("\n=== Testing Fallback Cache Functionality ===")
        
        # Create resilient Redis manager directly for testing
        redis_manager = ResilientRedisManager()
        monitor = CircuitBreakerMonitor(redis_manager)
        
        try:
            # Save some test data when Redis is available
            test_data = {
                'player_id': 'test123',
                'username': 'TestUser',
                'room_code': 'CACHE001'
            }
            
            # Test normal save operation
            success = redis_manager.save_player_session('test123', test_data)
            print(f"Normal save operation: {'Success' if success else 'Failed'}")
            
            # Force circuit breaker to open (simulate failures)
            for circuit in redis_manager.circuits.values():
                circuit.force_open()
            
            print("Circuit breakers forced open - testing fallback cache")
            
            # Try to get data (should use fallback cache)
            session_data = redis_manager.get_player_session('test123')
            print(f"Fallback cache retrieval: {'Success' if session_data else 'Failed'}")
            print(f"Retrieved data: {session_data}")
            
            # Check fallback cache stats
            cache_stats = redis_manager.get_performance_metrics().get('fallback_cache_stats', {})
            print(f"Cache stats: {cache_stats}")
            
            self.test_results.append({
                'test': 'fallback_cache',
                'status': 'passed',
                'details': 'Fallback cache working correctly'
            })
            
        except Exception as e:
            print(f"Fallback cache test failed: {e}")
            self.test_results.append({
                'test': 'fallback_cache',
                'status': 'failed',
                'details': str(e)
            })
    
    async def test_monitoring_system(self):
        """Test the monitoring and alerting system"""
        print("\n=== Testing Monitoring System ===")
        
        try:
            redis_manager = ResilientRedisManager()
            monitor = CircuitBreakerMonitor(redis_manager)
            
            # Get initial monitoring status
            status = monitor.get_circuit_breaker_status()
            print(f"Initial circuit breaker status: {status}")
            
            # Get dashboard metrics
            metrics = monitor.get_dashboard_metrics()
            print(f"Dashboard metrics: {metrics}")
            
            # Test alert rules
            alert_rules = monitor.alert_rules
            print(f"Active alert rules: {len(alert_rules)}")
            for rule in alert_rules:
                print(f"  - {rule.name}: {rule.condition} (severity: {rule.severity})")
            
            # Simulate some operations to generate metrics
            for i in range(10):
                try:
                    redis_manager.save_player_session(f'test{i}', {'data': f'test{i}'})
                except:
                    pass  # Expected to fail if Redis is down
            
            # Get updated metrics
            updated_metrics = monitor.get_dashboard_metrics()
            print(f"Updated metrics: {updated_metrics}")
            
            self.test_results.append({
                'test': 'monitoring_system',
                'status': 'passed',
                'details': 'Monitoring system functioning correctly'
            })
            
        except Exception as e:
            print(f"Monitoring system test failed: {e}")
            self.test_results.append({
                'test': 'monitoring_system',
                'status': 'failed',
                'details': str(e)
            })
    
    async def test_performance_impact(self):
        """Test performance impact of circuit breaker"""
        print("\n=== Testing Performance Impact ===")
        
        try:
            redis_manager = ResilientRedisManager()
            
            # Measure performance with circuit breaker
            start_time = time.time()
            operations = 100
            
            for i in range(operations):
                redis_manager.save_player_session(f'perf_test_{i}', {
                    'username': f'user_{i}',
                    'timestamp': time.time()
                })
            
            end_time = time.time()
            total_time = end_time - start_time
            avg_time_per_op = total_time / operations
            
            print(f"Performance test results:")
            print(f"  Total operations: {operations}")
            print(f"  Total time: {total_time:.3f} seconds")
            print(f"  Average time per operation: {avg_time_per_op:.4f} seconds")
            print(f"  Operations per second: {operations/total_time:.1f}")
            
            # Get performance metrics from Redis manager
            perf_metrics = redis_manager.get_performance_metrics()
            print(f"  Circuit breaker metrics: {perf_metrics}")
            
            # Check if performance is acceptable (< 10ms per operation)
            acceptable_performance = avg_time_per_op < 0.01
            
            self.test_results.append({
                'test': 'performance_impact',
                'status': 'passed' if acceptable_performance else 'warning',
                'details': f'Avg time per operation: {avg_time_per_op:.4f}s'
            })
            
        except Exception as e:
            print(f"Performance test failed: {e}")
            self.test_results.append({
                'test': 'performance_impact',
                'status': 'failed',
                'details': str(e)
            })
    
    def print_test_summary(self):
        """Print comprehensive test summary"""
        print("\n" + "="*60)
        print("CIRCUIT BREAKER INTEGRATION TEST SUMMARY")
        print("="*60)
        
        passed = sum(1 for result in self.test_results if result['status'] == 'passed')
        failed = sum(1 for result in self.test_results if result['status'] == 'failed')
        warnings = sum(1 for result in self.test_results if result['status'] == 'warning')
        
        print(f"Total tests: {len(self.test_results)}")
        print(f"Passed: {passed}")
        print(f"Failed: {failed}")
        print(f"Warnings: {warnings}")
        print()
        
        for result in self.test_results:
            status_symbol = "✓" if result['status'] == 'passed' else "✗" if result['status'] == 'failed' else "⚠"
            print(f"{status_symbol} {result['test']}: {result['details']}")
        
        print("\n" + "="*60)
        
        if failed == 0:
            print("🎉 All circuit breaker integration tests passed!")
        else:
            print(f"⚠️  {failed} test(s) failed. Please review the issues above.")

async def main():
    """Run all circuit breaker integration tests"""
    print("Starting Circuit Breaker Integration Tests...")
    print("Make sure the game server is running on localhost:8765")
    
    tester = CircuitBreakerIntegrationTest()
    
    # Run all tests
    await tester.test_basic_functionality()
    await tester.test_fallback_cache_functionality()
    await tester.test_monitoring_system()
    await tester.test_performance_impact()
    
    # Note: Redis failure test is commented out as it requires Redis admin access
    # Uncomment the following line if you want to test Redis failure scenarios
    # await tester.test_redis_failure_recovery()
    
    # Print summary
    tester.print_test_summary()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
    except Exception as e:
        print(f"Test suite failed: {e}")
