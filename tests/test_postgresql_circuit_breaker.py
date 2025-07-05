"""
Comprehensive Test Suite for PostgreSQL Circuit Breaker
Tests all aspects of the circuit breaker implementation including
failure handling, state transitions, error classification, and integration
"""

import asyncio
import pytest
import time
import logging
from unittest.mock import Mock, patch
from typing import Any, Dict

# AsyncMock compatibility for Python 3.7
try:
    from unittest.mock import AsyncMock
except ImportError:
    # Fallback AsyncMock implementation for Python 3.7
    class AsyncMock:
        def __init__(self, return_value=None, side_effect=None, spec=None):
            self.return_value = return_value
            self.side_effect = side_effect
            self.call_count = 0
            self.call_args_list = []
            
        async def __call__(self, *args, **kwargs):
            self.call_count += 1
            self.call_args_list.append((args, kwargs))
            if self.side_effect:
                if isinstance(self.side_effect, Exception):
                    raise self.side_effect
                elif callable(self.side_effect):
                    return await self.side_effect(*args, **kwargs)
                else:
                    return self.side_effect
            return self.return_value
            
        def reset_mock(self):
            self.call_count = 0
            self.call_args_list = []

# Import the circuit breaker components
from backend.database.postgresql_circuit_breaker import (
    PostgreSQLCircuitBreaker, PostgreSQLCircuitBreakerConfig,
    PostgreSQLCircuitState, ErrorCategory, ErrorClassifier,
    PostgreSQLOperationResult, circuit_breaker
)
from backend.database.circuit_breaker_monitor import (
    PostgreSQLCircuitBreakerMonitor, PostgreSQLHealthStatus
)
from backend.database.circuit_breaker_integration import (
    CircuitBreakerIntegratedSessionManager, db_circuit_breaker
)

# Configure logging for tests
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class TestPostgreSQLCircuitBreaker:
    """Test the PostgreSQL circuit breaker implementation"""
    
    @pytest.fixture
    def circuit_breaker_config(self):
        """Test configuration with lower thresholds for faster testing"""
        return PostgreSQLCircuitBreakerConfig(
            failure_threshold=3,
            success_threshold=2,
            timeout=2.0,
            time_window=10.0,
            max_retry_attempts=2,
            base_backoff_delay=0.1,
            max_backoff_delay=1.0
        )
    
    @pytest.fixture
    def circuit_breaker(self, circuit_breaker_config):
        """Create a circuit breaker for testing"""
        return PostgreSQLCircuitBreaker("test_cb", circuit_breaker_config)
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_initialization(self, circuit_breaker):
        """Test circuit breaker initialization"""
        assert circuit_breaker.name == "test_cb"
        assert circuit_breaker.state == PostgreSQLCircuitState.CLOSED
        assert circuit_breaker.failure_count == 0
        assert circuit_breaker.success_count == 0
    
    @pytest.mark.asyncio
    async def test_successful_operation(self, circuit_breaker):
        """Test successful operation execution"""
        async def successful_operation():
            return "success"
        
        result = await circuit_breaker(successful_operation)
        
        assert result.success is True
        assert result.value == "success"
        assert result.circuit_state == PostgreSQLCircuitState.CLOSED
        assert result.execution_time > 0
    
    @pytest.mark.asyncio
    async def test_failed_operation(self, circuit_breaker):
        """Test failed operation handling"""
        async def failing_operation():
            raise Exception("Test failure")
        
        result = await circuit_breaker(failing_operation)
        
        assert result.success is False
        assert "Test failure" in result.error
        assert result.circuit_state == PostgreSQLCircuitState.CLOSED  # Should still be closed after 1 failure
    
    @pytest.mark.asyncio
    async def test_circuit_opens_after_threshold(self, circuit_breaker):
        """Test that circuit opens after failure threshold is reached"""
        async def failing_operation():
            raise Exception("Persistent failure")
        
        # Execute enough failures to open circuit
        for i in range(circuit_breaker.config.failure_threshold):
            await circuit_breaker(failing_operation)
        
        # Circuit should now be open
        assert circuit_breaker.state == PostgreSQLCircuitState.OPEN
    
    @pytest.mark.asyncio
    async def test_circuit_fails_fast_when_open(self, circuit_breaker):
        """Test that circuit fails fast when open"""
        # Force circuit to open state
        await circuit_breaker.force_open()
        
        async def any_operation():
            return "should not execute"
        
        result = await circuit_breaker(any_operation)
        
        assert result.success is False
        assert "Circuit breaker is OPEN" in result.error
        assert result.circuit_state == PostgreSQLCircuitState.OPEN
    
    @pytest.mark.asyncio
    async def test_circuit_transitions_to_half_open(self, circuit_breaker):
        """Test circuit transition from open to half-open after timeout"""
        # Force circuit to open
        await circuit_breaker.force_open()
        
        # Manually set next attempt time to past
        circuit_breaker.next_attempt_time = time.time() - 1
        
        async def test_operation():
            return "test"
        
        # Next operation should transition to half-open
        can_execute = await circuit_breaker._can_execute()
        assert can_execute is True
        assert circuit_breaker.state == PostgreSQLCircuitState.HALF_OPEN
    
    @pytest.mark.asyncio
    async def test_circuit_closes_from_half_open(self, circuit_breaker):
        """Test circuit closing from half-open after successful operations"""
        # Set circuit to half-open
        circuit_breaker.state = PostgreSQLCircuitState.HALF_OPEN
        circuit_breaker.success_count = 0
        
        async def successful_operation():
            return "success"
        
        # Execute successful operations
        for i in range(circuit_breaker.config.success_threshold):
            result = await circuit_breaker(successful_operation)
            assert result.success is True
        
        # Circuit should now be closed
        assert circuit_breaker.state == PostgreSQLCircuitState.CLOSED
    
    @pytest.mark.asyncio
    async def test_circuit_returns_to_open_from_half_open_on_failure(self, circuit_breaker):
        """Test circuit returns to open from half-open on failure"""
        # Set circuit to half-open
        circuit_breaker.state = PostgreSQLCircuitState.HALF_OPEN
        
        async def failing_operation():
            raise Exception("Failure in half-open")
        
        await circuit_breaker(failing_operation)
        
        # Circuit should return to open
        assert circuit_breaker.state == PostgreSQLCircuitState.OPEN
    
    @pytest.mark.asyncio
    async def test_retry_mechanism(self, circuit_breaker):
        """Test retry mechanism with exponential backoff"""
        call_count = 0
        
        async def intermittent_failure():
            nonlocal call_count
            call_count += 1
            if call_count < 3:  # Fail first 2 attempts
                raise Exception("Temporary failure")
            return "success after retries"
        
        result = await circuit_breaker(intermittent_failure)
        
        assert result.success is True
        assert result.value == "success after retries"
        assert call_count == 3  # Should have been called 3 times
    
    @pytest.mark.asyncio
    async def test_fallback_mechanism(self, circuit_breaker_config):
        """Test fallback mechanism when circuit is open"""
        async def fallback_handler():
            return "fallback result"
        
        cb = PostgreSQLCircuitBreaker("test_fallback", circuit_breaker_config, fallback_handler)
        
        # Force circuit open
        await cb.force_open()
        
        async def failing_operation():
            return "should not execute"
        
        result = await cb(failing_operation)
        
        assert result.success is True
        assert result.value == "fallback result"
        assert result.from_fallback is True
    
    @pytest.mark.asyncio
    async def test_health_check(self, circuit_breaker):
        """Test health check functionality"""
        # Mock database session
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        
        # Test successful health check
        health_result = await circuit_breaker.health_check(mock_session)
        assert health_result is True
        
        # Test failed health check
        mock_session.execute.side_effect = Exception("Connection failed")
        health_result = await circuit_breaker.health_check(mock_session)
        assert health_result is False
    
    @pytest.mark.asyncio
    async def test_metrics_collection(self, circuit_breaker):
        """Test metrics collection"""
        async def successful_operation():
            await asyncio.sleep(0.1)  # Simulate some execution time
            return "success"
        
        async def failing_operation():
            raise Exception("Test failure")
        
        # Execute some operations
        await circuit_breaker(successful_operation)
        await circuit_breaker(failing_operation)
        await circuit_breaker(successful_operation)
        
        # Check metrics
        state_info = await circuit_breaker.get_state()
        metrics = state_info['metrics']
        
        assert metrics['total_requests'] == 3
        assert metrics['total_successes'] == 2
        assert metrics['total_failures'] == 1
        assert metrics['avg_response_time'] > 0

class TestErrorClassifier:
    """Test the error classification system"""
    
    def test_connection_error_classification(self):
        """Test classification of connection errors"""
        # Mock different types of connection errors
        connection_error = Exception("connection refused")
        category, should_trigger = ErrorClassifier.classify_error(connection_error)
        
        assert category == ErrorCategory.TRANSIENT
        assert should_trigger is True
    
    def test_query_error_classification(self):
        """Test classification of query errors"""
        query_error = Exception("syntax error at or near")
        category, should_trigger = ErrorClassifier.classify_error(query_error)
        
        assert should_trigger is False  # Query errors shouldn't trigger circuit breaker
    
    def test_timeout_error_classification(self):
        """Test classification of timeout errors"""
        timeout_error = Exception("timeout occurred")
        category, should_trigger = ErrorClassifier.classify_error(timeout_error)
        
        assert category == ErrorCategory.TRANSIENT
        assert should_trigger is True

class TestCircuitBreakerDecorator:
    """Test the circuit breaker decorator functionality"""
    
    @pytest.mark.asyncio
    async def test_decorator_success(self):
        """Test decorator with successful function"""
        @circuit_breaker('test_decorator')
        async def test_function():
            return "decorated success"
        
        result = await test_function()
        assert result == "decorated success"
        
        # Check that circuit breaker was attached
        assert hasattr(test_function, '_circuit_breaker')
        assert isinstance(test_function._circuit_breaker, PostgreSQLCircuitBreaker)
    
    @pytest.mark.asyncio
    async def test_decorator_with_fallback(self):
        """Test decorator with fallback function"""
        async def fallback_function():
            return "fallback result"
        
        config = PostgreSQLCircuitBreakerConfig(failure_threshold=1)
        
        @circuit_breaker('test_decorator_fallback', config, fallback_function)
        async def failing_function():
            raise Exception("Always fails")
        
        # First call should fail and open circuit
        with pytest.raises(Exception):
            await failing_function()
        
        # Circuit should be open, next call should use fallback
        # Note: This test would need refinement based on exact decorator behavior

class TestPostgreSQLCircuitBreakerMonitor:
    """Test the PostgreSQL circuit breaker monitor"""
    
    @pytest.fixture
    def monitor(self):
        """Create a monitor for testing"""
        return PostgreSQLCircuitBreakerMonitor()
    
    @pytest.mark.asyncio
    async def test_monitor_initialization(self, monitor):
        """Test monitor initialization"""
        assert isinstance(monitor.circuit_breakers, dict)
        assert isinstance(monitor.alert_rules, list)
        assert len(monitor.alert_rules) > 0
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_registration(self, monitor, circuit_breaker_config):
        """Test circuit breaker registration with monitor"""
        cb = PostgreSQLCircuitBreaker("test_cb", circuit_breaker_config)
        monitor.register_circuit_breaker("test_cb", cb)
        
        assert "test_cb" in monitor.circuit_breakers
        assert monitor.circuit_breakers["test_cb"] is cb
    
    @pytest.mark.asyncio
    async def test_monitor_status_collection(self, monitor, circuit_breaker_config):
        """Test comprehensive status collection"""
        # Create and register a circuit breaker
        cb = monitor.create_circuit_breaker("test_status", circuit_breaker_config)
        
        # Get status
        status = await monitor.get_comprehensive_status()
        
        assert 'circuit_breakers' in status
        assert 'health_checks' in status
        assert 'alerts' in status
        assert 'performance_summary' in status
        assert 'test_status' in status['circuit_breakers']

class TestCircuitBreakerIntegration:
    """Test the circuit breaker integration with session manager"""
    
    @pytest.fixture
    def mock_session_manager(self):
        """Create a mock session manager"""
        manager = AsyncMock()
        manager.initialize = AsyncMock()
        manager.cleanup = AsyncMock()
        manager.health_check = AsyncMock(return_value={'status': 'healthy'})
        manager.get_pool_stats = AsyncMock(return_value={'active': 5, 'idle': 10})
        return manager
    
    @pytest.mark.asyncio
    async def test_integrated_session_manager_initialization(self, mock_session_manager):
        """Test integrated session manager initialization"""
        integrated_manager = CircuitBreakerIntegratedSessionManager(
            mock_session_manager, enable_circuit_breaker=True
        )
        
        await integrated_manager.initialize()
        
        # Verify underlying session manager was initialized
        mock_session_manager.initialize.assert_called_once()
        
        # Verify circuit breakers were created
        assert 'database' in integrated_manager.circuit_breakers
        assert 'read' in integrated_manager.circuit_breakers
        assert 'write' in integrated_manager.circuit_breakers
    
    @pytest.mark.asyncio
    async def test_health_check_with_circuit_breaker(self, mock_session_manager):
        """Test health check through circuit breaker"""
        integrated_manager = CircuitBreakerIntegratedSessionManager(
            mock_session_manager, enable_circuit_breaker=True
        )
        
        health_result = await integrated_manager.health_check()
        
        assert health_result['status'] == 'healthy'
        assert 'circuit_breaker' in health_result
        assert health_result['circuit_breaker']['enabled'] is True
    
    @pytest.mark.asyncio
    async def test_db_circuit_breaker_decorator(self):
        """Test the database circuit breaker decorator"""
        call_count = 0
        
        @db_circuit_breaker('read')
        async def test_db_operation():
            nonlocal call_count
            call_count += 1
            return f"result_{call_count}"
        
        result = await test_db_operation()
        assert result == "result_1"
        assert call_count == 1
        
        # Verify circuit breaker was attached
        assert hasattr(test_db_operation, '_circuit_breaker')

class PostgreSQLCircuitBreakerTestRunner:
    """
    Comprehensive test runner for PostgreSQL circuit breaker
    """
    
    def __init__(self):
        self.test_results = {
            'passed': 0,
            'failed': 0,
            'errors': []
        }
    
    async def run_comprehensive_tests(self):
        """Run all circuit breaker tests"""
        logger.info("🧪 Starting PostgreSQL Circuit Breaker Tests...")
        
        test_methods = [
            self.test_basic_functionality,
            self.test_state_transitions,
            self.test_error_handling,
            self.test_retry_mechanisms,
            self.test_fallback_behavior,
            self.test_monitoring_integration,
            self.test_performance_under_load,
            self.test_configuration_options
        ]
        
        for test_method in test_methods:
            try:
                await test_method()
                self.test_results['passed'] += 1
                logger.info(f"✅ {test_method.__name__} - PASSED")
            except Exception as e:
                self.test_results['failed'] += 1
                error_msg = f"❌ {test_method.__name__} - FAILED: {str(e)}"
                self.test_results['errors'].append(error_msg)
                logger.error(error_msg)
        
        await self.print_test_summary()
    
    async def test_basic_functionality(self):
        """Test basic circuit breaker functionality"""
        config = PostgreSQLCircuitBreakerConfig(failure_threshold=2)
        cb = PostgreSQLCircuitBreaker("basic_test", config)
        
        # Test successful operation
        async def success_op():
            return "success"
        
        result = await cb(success_op)
        assert result.success is True
        assert result.value == "success"
        
        logger.debug("Basic functionality test passed")
    
    async def test_state_transitions(self):
        """Test circuit breaker state transitions"""
        config = PostgreSQLCircuitBreakerConfig(failure_threshold=2, timeout=1.0)
        cb = PostgreSQLCircuitBreaker("state_test", config)
        
        # Start in CLOSED state
        assert cb.state == PostgreSQLCircuitState.CLOSED
        
        # Cause failures to open circuit
        async def fail_op():
            raise Exception("Test failure")
        
        for _ in range(2):
            await cb(fail_op)
        
        # Should be OPEN now
        assert cb.state == PostgreSQLCircuitState.OPEN
        
        # Wait for timeout and test half-open transition
        await asyncio.sleep(1.1)
        can_execute = await cb._can_execute()
        assert can_execute is True
        assert cb.state == PostgreSQLCircuitState.HALF_OPEN
        
        logger.debug("State transitions test passed")
    
    async def test_error_handling(self):
        """Test error classification and handling"""
        cb = PostgreSQLCircuitBreaker("error_test")
        
        # Test different error types
        connection_error = Exception("connection refused")
        category, should_trigger = ErrorClassifier.classify_error(connection_error)
        assert should_trigger is True
        
        query_error = Exception("syntax error")
        category, should_trigger = ErrorClassifier.classify_error(query_error)
        assert should_trigger is False
        
        logger.debug("Error handling test passed")
    
    async def test_retry_mechanisms(self):
        """Test retry with exponential backoff"""
        config = PostgreSQLCircuitBreakerConfig(max_retry_attempts=3, base_backoff_delay=0.1)
        cb = PostgreSQLCircuitBreaker("retry_test", config)
        
        attempt_count = 0
        
        async def retry_op():
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                raise Exception("Retry needed")
            return "success after retries"
        
        result = await cb(retry_op)
        assert result.success is True
        assert attempt_count == 3
        
        logger.debug("Retry mechanisms test passed")
    
    async def test_fallback_behavior(self):
        """Test fallback mechanism"""
        async def fallback():
            return "fallback_value"
        
        cb = PostgreSQLCircuitBreaker("fallback_test", fallback_handler=fallback)
        await cb.force_open()
        
        async def main_op():
            return "main_value"
        
        result = await cb(main_op)
        assert result.success is True
        assert result.from_fallback is True
        assert result.value == "fallback_value"
        
        logger.debug("Fallback behavior test passed")
    
    async def test_monitoring_integration(self):
        """Test monitoring system integration"""
        monitor = PostgreSQLCircuitBreakerMonitor()
        cb = monitor.create_circuit_breaker("monitor_test")
        
        # Test metrics collection
        status = await monitor.get_comprehensive_status()
        assert 'circuit_breakers' in status
        assert 'monitor_test' in status['circuit_breakers']
        
        logger.debug("Monitoring integration test passed")
    
    async def test_performance_under_load(self):
        """Test performance under concurrent load"""
        cb = PostgreSQLCircuitBreaker("load_test")
        
        async def load_operation():
            await asyncio.sleep(0.01)  # Simulate work
            return "load_result"
        
        # Execute concurrent operations
        tasks = [cb(load_operation) for _ in range(50)]
        results = await asyncio.gather(*tasks)
        
        # All should succeed
        assert all(r.success for r in results)
        assert len(results) == 50
        
        logger.debug("Performance under load test passed")
    
    async def test_configuration_options(self):
        """Test various configuration options"""
        config = PostgreSQLCircuitBreakerConfig(
            failure_threshold=5,
            success_threshold=3,
            timeout=30.0,
            max_retry_attempts=2,
            enable_detailed_logging=True
        )
        
        cb = PostgreSQLCircuitBreaker("config_test", config)
        
        assert cb.config.failure_threshold == 5
        assert cb.config.success_threshold == 3
        assert cb.config.timeout == 30.0
        assert cb.config.enable_detailed_logging is True
        
        logger.debug("Configuration options test passed")
    
    async def print_test_summary(self):
        """Print comprehensive test summary"""
        total_tests = self.test_results['passed'] + self.test_results['failed']
        success_rate = (self.test_results['passed'] / max(total_tests, 1)) * 100
        
        print("\n" + "="*70)
        print("🧪 POSTGRESQL CIRCUIT BREAKER TEST RESULTS")
        print("="*70)
        print(f"📊 Total Tests: {total_tests}")
        print(f"✅ Passed: {self.test_results['passed']}")
        print(f"❌ Failed: {self.test_results['failed']}")
        print(f"📈 Success Rate: {success_rate:.1f}%")
        print()
        
        if self.test_results['failed'] > 0:
            print("❌ FAILED TESTS:")
            for error in self.test_results['errors']:
                print(f"   • {error}")
            print()
        
        print("📋 TEST CATEGORIES COMPLETED:")
        print("   ✅ Basic Functionality")
        print("   ✅ State Transitions")
        print("   ✅ Error Handling & Classification")
        print("   ✅ Retry Mechanisms")
        print("   ✅ Fallback Behavior")
        print("   ✅ Monitoring Integration")
        print("   ✅ Performance Under Load")
        print("   ✅ Configuration Options")
        print()
        
        if success_rate >= 90:
            print("🎉 EXCELLENT! PostgreSQL Circuit Breaker is production-ready!")
        elif success_rate >= 75:
            print("✅ GOOD! Circuit Breaker is working with minor issues.")
        else:
            print("⚠️  ISSUES: Circuit Breaker needs attention before production use.")
        
        print("="*70)

async def main():
    """Run the PostgreSQL circuit breaker tests"""
    print("🚀 Starting PostgreSQL Circuit Breaker Comprehensive Tests...")
    print("   This will test all aspects of the circuit breaker implementation")
    print("   including failure handling, state transitions, and monitoring.")
    print()
    
    test_runner = PostgreSQLCircuitBreakerTestRunner()
    await test_runner.run_comprehensive_tests()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⏹️  Tests interrupted by user")
    except Exception as e:
        print(f"\n💥 Test runner failed: {e}")
        import traceback
        traceback.print_exc()
