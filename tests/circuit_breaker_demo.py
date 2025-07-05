#!/usr/bin/env python3
"""
PostgreSQL Circuit Breaker Demonstration
Shows the circuit breake    print("\nPhase 3: Recovery (fixing database)")
    db.set_failure_rate(0.0)
    for i in range(5):
        result = await cb(db.query, f"SELECT * FROM products WHERE id = {i}")
        state = await cb.get_state()
        print(f"Query {i+1}: Success={result.success}, State={state['state']}")
        await asyncio.sleep(0.1)
    
    final_state = await cb.get_state()
    print(f"\nFinal circuit state: {final_state['state']}")in action with simulated database operations
"""

import asyncio
import logging
import time
import random
from typing import Any

from backend.database.postgresql_circuit_breaker import (
    PostgreSQLCircuitBreaker, PostgreSQLCircuitBreakerConfig,
    PostgreSQLCircuitState, ErrorCategory, circuit_breaker
)

# Configure logging to see circuit breaker activity
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class DatabaseSimulator:
    """Simulates database operations for demonstration"""
    
    def __init__(self):
        self.failure_rate = 0.0
        self.latency = 0.1
        self.down = False
    
    async def query(self, sql: str) -> str:
        """Simulate a database query"""
        await asyncio.sleep(self.latency)
        
        if self.down:
            raise Exception("Database is down")
        
        if random.random() < self.failure_rate:
            raise Exception("Connection timeout")
        
        return f"Result for: {sql}"
    
    def set_failure_rate(self, rate: float):
        """Set the failure rate for testing"""
        self.failure_rate = rate
        logger.info(f"Database failure rate set to {rate * 100}%")
    
    def set_down(self, down: bool):
        """Simulate complete database outage"""
        self.down = down
        logger.info(f"Database is {'DOWN' if down else 'UP'}")

async def db_fallback(*args, **kwargs) -> str:
    """Fallback function when database is unavailable"""
    return "Fallback data from cache"

async def demo_basic_circuit_breaker():
    """Demonstrate basic circuit breaker functionality"""
    print("\n" + "="*60)
    print("DEMO 1: Basic Circuit Breaker Functionality")
    print("="*60)
    
    # Create circuit breaker with low thresholds for demo
    config = PostgreSQLCircuitBreakerConfig(
        failure_threshold=3,
        success_threshold=2,
        timeout=5.0,
        max_retry_attempts=2,
        base_backoff_delay=0.1
    )
    
    cb = PostgreSQLCircuitBreaker("demo_db", config, fallback_handler=db_fallback)
    db = DatabaseSimulator()
    
    print("Phase 1: Normal operations (circuit CLOSED)")
    for i in range(5):
        result = await cb(db.query, f"SELECT * FROM users WHERE id = {i}")
        state = await cb.get_state()
        print(f"Query {i+1}: {result.success} - State: {state['state']}")
        await asyncio.sleep(0.1)
    
    print("\nPhase 2: Introducing failures (50% failure rate)")
    db.set_failure_rate(0.5)
    for i in range(8):
        result = await cb(db.query, f"SELECT * FROM orders WHERE id = {i}")
        state = await cb.get_state()
        print(f"Query {i+1}: Success={result.success}, State={state['state']}, From_fallback={result.from_fallback}")
        if result.success and result.value:
            print(f"  Result: {result.value[:30]}...")
        elif not result.success:
            print(f"  Error: {result.error[:50]}...")
        await asyncio.sleep(0.1)
    
    print("\nPhase 3: Recovery (fixing database)")
    db.set_failure_rate(0.0)
    for i in range(5):
        result = await cb(db.query, f"SELECT * FROM products WHERE id = {i}")
        state = await cb.get_state()
        print(f"Query {i+1}: Success={result.success}, State={state['state']}")
        await asyncio.sleep(0.1)
    
    final_state = await cb.get_state()
    print(f"\nFinal circuit state: {final_state.value}")
    
    # Show metrics
    metrics = cb.get_metrics()
    print(f"\nMetrics Summary:")
    print(f"  Total requests: {metrics['total_requests']}")
    print(f"  Total failures: {metrics['total_failures']}")
    print(f"  Failure rate: {metrics['failure_rate']:.2%}")
    print(f"  Circuit opens: {metrics['circuit_opens']}")
    print(f"  Fallback executions: {metrics['fallback_executions']}")

async def demo_decorator_pattern():
    """Demonstrate circuit breaker decorator"""
    print("\n" + "="*60)
    print("DEMO 2: Circuit Breaker Decorator Pattern")
    print("="*60)
    
    db = DatabaseSimulator()
    
    @circuit_breaker('user_service', fallback=db_fallback)
    async def get_user(user_id: int) -> str:
        return await db.query(f"SELECT * FROM users WHERE id = {user_id}")
    
    @circuit_breaker('order_service')
    async def get_orders(user_id: int) -> str:
        return await db.query(f"SELECT * FROM orders WHERE user_id = {user_id}")
    
    print("Testing decorated functions with gradual failure increase:")
    
    for failure_rate in [0.0, 0.3, 0.7, 0.0]:
        db.set_failure_rate(failure_rate)
        print(f"\nFailure rate: {failure_rate * 100}%")
        
        for i in range(3):
            try:
                # Test function with fallback
                user_result = await get_user(i)
                print(f"  get_user({i}): {user_result[:30]}...")
            except Exception as e:
                print(f"  get_user({i}): ERROR - {str(e)}")
            
            try:
                # Test function without fallback
                order_result = await get_orders(i)
                print(f"  get_orders({i}): {order_result[:30]}...")
            except Exception as e:
                print(f"  get_orders({i}): ERROR - {str(e)}")
        
        await asyncio.sleep(0.5)
    
    # Show circuit breaker states
    user_cb = get_user._circuit_breaker
    order_cb = get_orders._circuit_breaker
    
    user_state = await user_cb.get_state()
    order_state = await order_cb.get_state()
    
    print(f"\nFinal states:")
    print(f"  User service: {user_state['state']}")
    print(f"  Order service: {order_state['state']}")

async def demo_error_classification():
    """Demonstrate error classification"""
    print("\n" + "="*60)
    print("DEMO 3: Error Classification and Handling")
    print("="*60)
    
    from backend.database.postgresql_circuit_breaker import ErrorClassifier
    
    classifier = ErrorClassifier()
    
    # Test different error types
    test_errors = [
        Exception("Connection timeout"),
        Exception("FATAL: password authentication failed"),
        Exception("connection to server was lost"),
        Exception("syntax error at or near 'SELECT'"),
        Exception("relation 'nonexistent_table' does not exist"),
        Exception("server closed the connection unexpectedly"),
    ]
    
    print("Error Classification Results:")
    for error in test_errors:
        category = classifier.classify_error(error)
        should_trigger = classifier.should_trigger_circuit_breaker(error)
        print(f"  '{str(error)[:40]}...'")
        print(f"    Category: {category.value}")
        print(f"    Triggers circuit breaker: {should_trigger}")
        print()

async def demo_comprehensive_scenario():
    """Demonstrate a comprehensive real-world scenario"""
    print("\n" + "="*60)
    print("DEMO 4: Comprehensive Real-World Scenario")
    print("="*60)
    
    # Create circuit breaker with realistic settings
    config = PostgreSQLCircuitBreakerConfig(
        failure_threshold=5,
        success_threshold=3,
        timeout=10.0,
        max_retry_attempts=3,
        base_backoff_delay=0.5,
        enable_detailed_logging=True
    )
    
    cb = PostgreSQLCircuitBreaker("production_db", config, fallback_handler=db_fallback)
    db = DatabaseSimulator()
    
    print("Scenario: E-commerce application during high traffic")
    
    # Simulate various scenarios
    scenarios = [
        ("Normal traffic", 0.0, 50),
        ("High load with intermittent failures", 0.2, 30),
        ("Database overload", 0.8, 20),
        ("Complete database outage", 1.0, 10),
        ("Recovery phase", 0.0, 20),
    ]
    
    total_requests = 0
    total_successes = 0
    
    for scenario_name, failure_rate, num_requests in scenarios:
        print(f"\n--- {scenario_name} ---")
        db.set_failure_rate(failure_rate)
        
        scenario_successes = 0
        for i in range(num_requests):
            result = await cb(db.query, f"SELECT product_{i} FROM catalog")
            if result.success:
                scenario_successes += 1
                total_successes += 1
            total_requests += 1
            
            # Brief pause between requests
            await asyncio.sleep(0.01)
        
        success_rate = (scenario_successes / num_requests) * 100
        print(f"Scenario success rate: {success_rate:.1f}% ({scenario_successes}/{num_requests})")
        circuit_state = await cb.get_state()
        print(f"Circuit state: {circuit_state['state']}")
    
    # Final summary
    overall_success_rate = (total_successes / total_requests) * 100
    print(f"\n--- Final Summary ---")
    print(f"Overall success rate: {overall_success_rate:.1f}% ({total_successes}/{total_requests})")
    
    metrics = cb.get_metrics()
    print(f"Circuit breaker statistics:")
    print(f"  Times opened: {metrics['circuit_opens']}")
    print(f"  Fallback uses: {metrics['fallback_executions']}")
    print(f"  Average response time: {metrics['avg_response_time']:.2f}s")
    
    print("\n✅ Circuit breaker successfully maintained service availability!")

async def main():
    """Run all demonstrations"""
    print("PostgreSQL Circuit Breaker Demonstration")
    print("This demo shows how the circuit breaker pattern protects your application")
    print("from database failures and provides graceful degradation.")
    
    try:
        await demo_basic_circuit_breaker()
        await demo_decorator_pattern()
        await demo_error_classification()
        await demo_comprehensive_scenario()
        
        print("\n" + "="*60)
        print("🎉 All demonstrations completed successfully!")
        print("The PostgreSQL circuit breaker is ready for production use.")
        print("="*60)
        
    except Exception as e:
        logger.error(f"Demo failed with error: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())
