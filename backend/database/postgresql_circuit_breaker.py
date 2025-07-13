"""
PostgreSQL Async Circuit Breaker Implementation
Provides comprehensive fault tolerance and resilience for PostgreSQL database operations
Integrates with existing circuit breaker monitoring system
"""

import asyncio
import time
import logging
from enum import Enum
from typing import Dict, List, Optional, Any, Callable, Union, Tuple
from collections import deque, defaultdict
from dataclasses import dataclass, field
from functools import wraps
import random
import json
from datetime import datetime, timedelta

# SQLAlchemy imports for error handling (with fallback for missing imports)
try:
    from sqlalchemy.exc import (
        SQLAlchemyError, DisconnectionError, TimeoutError as SQLTimeoutError,
        OperationalError, InterfaceError, DatabaseError, StatementError,
        InvalidRequestError, NoResultFound, MultipleResultsFound
    )
    from sqlalchemy.pool import InvalidRequestError as PoolInvalidRequestError
except ImportError:
    # Fallback definitions for when SQLAlchemy is not available
    class SQLAlchemyError(Exception): pass
    class DisconnectionError(SQLAlchemyError): pass
    class SQLTimeoutError(SQLAlchemyError): pass
    class OperationalError(SQLAlchemyError): pass
    class InterfaceError(SQLAlchemyError): pass
    class DatabaseError(SQLAlchemyError): pass
    class StatementError(SQLAlchemyError): pass
    class InvalidRequestError(SQLAlchemyError): pass
    class NoResultFound(SQLAlchemyError): pass
    class MultipleResultsFound(SQLAlchemyError): pass
    class PoolInvalidRequestError(SQLAlchemyError): pass

logger = logging.getLogger(__name__)

class PostgreSQLCircuitState(Enum):
    """PostgreSQL Circuit breaker states"""
    CLOSED = "closed"       # Normal operation
    OPEN = "open"           # Circuit is open, failing fast
    HALF_OPEN = "half_open" # Testing if service has recovered

class ErrorCategory(Enum):
    """Categories of database errors for circuit breaker decision making"""
    TRANSIENT = "transient"     # Temporary issues that should trigger circuit breaker
    PERSISTENT = "persistent"   # Permanent issues that should trigger circuit breaker
    QUERY_ERROR = "query_error" # SQL/query issues that shouldn't trigger circuit breaker
    SYSTEM = "system"           # System-level errors
    TIMEOUT = "timeout"         # Timeout-related errors

@dataclass
class PostgreSQLCircuitBreakerConfig:
    """PostgreSQL Circuit breaker configuration optimized for database operations"""
    
    # Circuit breaker thresholds
    failure_threshold: int = 5          # Failures to open circuit
    success_threshold: int = 3          # Successes to close from half-open
    timeout: float = 60.0               # Seconds before trying half-open
    time_window: float = 300.0          # Time window for failure tracking (5 minutes)
    
    # Retry strategy
    max_retry_attempts: int = 3         # Max retries with exponential backoff
    base_backoff_delay: float = 1.0     # Base delay for exponential backoff
    max_backoff_delay: float = 30.0     # Maximum backoff delay
    backoff_multiplier: float = 2.0     # Exponential backoff multiplier
    jitter: bool = True                 # Add random jitter to backoff
    
    # Health check configuration
    health_check_interval: float = 30.0 # Health check interval in seconds
    health_check_timeout: float = 5.0   # Health check timeout
    health_check_query: str = "SELECT 1" # Simple health check query
    
    # Fallback configuration
    enable_fallback: bool = True        # Enable fallback mechanisms
    fallback_timeout: float = 10.0      # Timeout for fallback operations
    
    # Monitoring and logging
    enable_detailed_logging: bool = True
    log_successful_operations: bool = False
    metrics_collection_enabled: bool = True

@dataclass
class PostgreSQLOperationResult:
    """Result of a PostgreSQL circuit-protected operation"""
    success: bool
    value: Any = None
    error: str = ""
    error_category: ErrorCategory = ErrorCategory.SYSTEM
    from_fallback: bool = False
    execution_time: float = 0.0
    retry_count: int = 0
    circuit_state: PostgreSQLCircuitState = PostgreSQLCircuitState.CLOSED

class PostgreSQLCircuitBreakerMetrics:
    """Comprehensive metrics collection for PostgreSQL circuit breaker"""
    
    def __init__(self):
        self._lock = asyncio.Lock()
        self.reset()
    
    def reset(self):
        """Reset all metrics"""
        # Request metrics
        self.total_requests = 0
        self.total_failures = 0
        self.total_successes = 0
        self.total_retries = 0
        
        # Circuit state metrics
        self.circuit_opens = 0
        self.circuit_closes = 0
        self.half_open_attempts = 0
        
        # Fallback metrics
        self.fallback_executions = 0
        self.fallback_successes = 0
        self.fallback_failures = 0
        
        # Performance metrics
        self.avg_response_time = 0.0
        self.response_times = deque(maxlen=1000)  # Keep last 1000 response times
        self.slow_queries = 0  # Queries taking > 1 second
        
        # Error categorization
        self.error_categories = defaultdict(int)
        self.error_details = defaultdict(int)
        
        # Health metrics
        self.last_health_check = None
        self.health_check_failures = 0
        self.consecutive_health_failures = 0
        
        # Time-based metrics
        self.start_time = time.time()
        self.last_reset_time = time.time()
    
    async def record_request(
        self, 
        success: bool, 
        response_time: float, 
        error_category: ErrorCategory = ErrorCategory.SYSTEM,
        error_details: str = "",
        retry_count: int = 0
    ):
        """Record a request result"""
        async with self._lock:
            self.total_requests += 1
            self.total_retries += retry_count
            self.response_times.append(response_time)
            
            if response_time > 1.0:  # Consider > 1s as slow
                self.slow_queries += 1
            
            if success:
                self.total_successes += 1
            else:
                self.total_failures += 1
                self.error_categories[error_category] += 1
                if error_details:
                    self.error_details[error_details] += 1
            
            # Update average response time
            if self.response_times:
                self.avg_response_time = sum(self.response_times) / len(self.response_times)
    
    async def record_circuit_state_change(self, new_state: PostgreSQLCircuitState):
        """Record circuit state changes"""
        async with self._lock:
            if new_state == PostgreSQLCircuitState.OPEN:
                self.circuit_opens += 1
            elif new_state == PostgreSQLCircuitState.CLOSED:
                self.circuit_closes += 1
            elif new_state == PostgreSQLCircuitState.HALF_OPEN:
                self.half_open_attempts += 1
    
    async def record_fallback(self, success: bool):
        """Record fallback execution"""
        async with self._lock:
            self.fallback_executions += 1
            if success:
                self.fallback_successes += 1
            else:
                self.fallback_failures += 1
    
    async def record_health_check(self, success: bool):
        """Record health check result"""
        async with self._lock:
            self.last_health_check = time.time()
            if success:
                self.consecutive_health_failures = 0
            else:
                self.health_check_failures += 1
                self.consecutive_health_failures += 1
    
    async def get_failure_rate(self) -> float:
        """Get current failure rate"""
        async with self._lock:
            if self.total_requests == 0:
                return 0.0
            return self.total_failures / self.total_requests
    
    async def get_summary(self) -> Dict[str, Any]:
        """Get comprehensive metrics summary"""
        async with self._lock:
            uptime = time.time() - self.start_time
            
            return {
                'uptime_seconds': uptime,
                'total_requests': self.total_requests,
                'success_rate': (self.total_successes / max(self.total_requests, 1)) * 100,
                'failure_rate': (self.total_failures / max(self.total_requests, 1)) * 100,
                'avg_response_time': self.avg_response_time,
                'slow_queries': self.slow_queries,
                'total_retries': self.total_retries,
                'circuit_opens': self.circuit_opens,
                'circuit_closes': self.circuit_closes,
                'fallback_executions': self.fallback_executions,
                'fallback_success_rate': (self.fallback_successes / max(self.fallback_executions, 1)) * 100,
                'error_categories': dict(self.error_categories),
                'error_details': dict(self.error_details),
                'health_check_failures': self.health_check_failures,
                'consecutive_health_failures': self.consecutive_health_failures
            }

class ErrorClassifier:
    """Classifies database errors to determine circuit breaker behavior"""
    
    # Error patterns that should trigger circuit breaker (transient/persistent)
    CIRCUIT_BREAKER_ERRORS = {
        # Connection issues
        DisconnectionError: ErrorCategory.TRANSIENT,
        OperationalError: ErrorCategory.PERSISTENT,  # Can be transient or persistent
        InterfaceError: ErrorCategory.PERSISTENT,
        
        # Timeout issues
        SQLTimeoutError: ErrorCategory.TIMEOUT,
        
        # System issues
        DatabaseError: ErrorCategory.SYSTEM,
    }
    
    # Error patterns that should NOT trigger circuit breaker
    NON_CIRCUIT_BREAKER_ERRORS = {
        StatementError: ErrorCategory.QUERY_ERROR,
        InvalidRequestError: ErrorCategory.QUERY_ERROR,
        NoResultFound: ErrorCategory.QUERY_ERROR,
        MultipleResultsFound: ErrorCategory.QUERY_ERROR,
        PoolInvalidRequestError: ErrorCategory.QUERY_ERROR,
    }
    
    @classmethod
    def classify_error(cls, error: Exception) -> Tuple[ErrorCategory, bool]:
        """
        Classify error and determine if it should trigger circuit breaker
        
        Returns:
            Tuple of (ErrorCategory, should_trigger_circuit_breaker)
        """
        error_type = type(error)
        error_message = str(error).lower()
        
        # Check specific error type mappings
        if error_type in cls.CIRCUIT_BREAKER_ERRORS:
            category = cls.CIRCUIT_BREAKER_ERRORS[error_type]
            
            # Special handling for OperationalError - can be transient or persistent
            if error_type == OperationalError:
                if any(keyword in error_message for keyword in [
                    'connection', 'network', 'timeout', 'temporary', 'busy'
                ]):
                    category = ErrorCategory.TRANSIENT
                else:
                    category = ErrorCategory.PERSISTENT
            
            return category, True
        
        if error_type in cls.NON_CIRCUIT_BREAKER_ERRORS:
            return cls.NON_CIRCUIT_BREAKER_ERRORS[error_type], False
        
        # Handle string-based error classification
        if any(keyword in error_message for keyword in [
            'connection refused', 'connection reset', 'connection lost',
            'network error', 'timeout', 'temporary failure', 'server unavailable'
        ]):
            return ErrorCategory.TRANSIENT, True
        
        if any(keyword in error_message for keyword in [
            'authentication failed', 'access denied', 'permission denied',
            'database does not exist', 'role does not exist'
        ]):
            return ErrorCategory.PERSISTENT, True
        
        if any(keyword in error_message for keyword in [
            'syntax error', 'column does not exist', 'table does not exist',
            'constraint violation', 'invalid input'
        ]):
            return ErrorCategory.QUERY_ERROR, False
        
        # Default: treat unknown errors as system errors that trigger circuit breaker
        return ErrorCategory.SYSTEM, True

class PostgreSQLCircuitBreaker:
    """
    Comprehensive async circuit breaker for PostgreSQL operations
    
    Features:
    - Async/await support for database operations
    - Intelligent error classification
    - Exponential backoff with jitter
    - Health checking and monitoring
    - Fallback mechanism support
    - Comprehensive metrics collection
    - Integration with existing monitoring system
    """
    
    def __init__(
        self,
        name: str,
        config: Optional[PostgreSQLCircuitBreakerConfig] = None,
        fallback_handler: Optional[Callable] = None
    ):
        self.name = name
        self.config = config or PostgreSQLCircuitBreakerConfig()
        self.fallback_handler = fallback_handler
        
        # Circuit state
        self.state = PostgreSQLCircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = 0
        self.next_attempt_time = 0
        
        # Failure tracking with time window
        self.recent_failures = deque()
        
        # Metrics and monitoring
        self.metrics = PostgreSQLCircuitBreakerMetrics()
        
        # Locks for thread safety
        self._state_lock = asyncio.Lock()
        
        # Health checking
        self._health_check_task = None
        self._stop_health_check = False
        
        logger.info(f"PostgreSQL Circuit Breaker '{name}' initialized with config: {self.config}")
    
    async def __call__(self, func: Callable, *args, **kwargs) -> PostgreSQLOperationResult:
        """
        Execute function with circuit breaker protection
        
        This is the main entry point for circuit-protected database operations
        """
        start_time = time.time()
        
        try:
            # Check circuit state before execution
            if not await self._can_execute():
                return await self._handle_circuit_open(start_time)
            
            # Execute with retry logic
            result = await self._execute_with_retry(func, *args, **kwargs)
            
            # Handle successful execution
            await self._handle_success(result, time.time() - start_time)
            
            return PostgreSQLOperationResult(
                success=True,
                value=result,
                execution_time=time.time() - start_time,
                circuit_state=self.state
            )
            
        except Exception as error:
            # Handle execution failure
            return await self._handle_failure(error, start_time)
    
    async def _can_execute(self) -> bool:
        """Check if operation can be executed based on circuit state"""
        async with self._state_lock:
            current_time = time.time()
            
            if self.state == PostgreSQLCircuitState.CLOSED:
                return True
            
            elif self.state == PostgreSQLCircuitState.OPEN:
                if current_time >= self.next_attempt_time:
                    # Transition to half-open
                    self.state = PostgreSQLCircuitState.HALF_OPEN
                    self.success_count = 0
                    await self.metrics.record_circuit_state_change(self.state)
                    logger.info(f"Circuit breaker '{self.name}' transitioning to HALF_OPEN")
                    return True
                return False
            
            elif self.state == PostgreSQLCircuitState.HALF_OPEN:
                return True
            
            return False
    
    async def _execute_with_retry(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with exponential backoff retry logic"""
        last_exception = None
        
        for attempt in range(self.config.max_retry_attempts + 1):
            try:
                if attempt > 0:
                    # Calculate backoff delay
                    delay = min(
                        self.config.base_backoff_delay * (self.config.backoff_multiplier ** (attempt - 1)),
                        self.config.max_backoff_delay
                    )
                    
                    # Add jitter if enabled
                    if self.config.jitter:
                        delay *= (0.5 + random.random() * 0.5)  # 50% to 100% of calculated delay
                    
                    logger.debug(f"Retrying database operation (attempt {attempt + 1}) after {delay:.2f}s delay")
                    await asyncio.sleep(delay)
                
                # Execute the actual database operation
                if asyncio.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    result = func(*args, **kwargs)
                
                if attempt > 0:
                    logger.info(f"Database operation succeeded on retry attempt {attempt + 1}")
                
                return result
                
            except Exception as e:
                last_exception = e
                error_category, should_trigger_cb = ErrorClassifier.classify_error(e)
                
                # Don't retry for certain error types
                if error_category == ErrorCategory.QUERY_ERROR:
                    logger.debug(f"Not retrying query error: {e}")
                    raise e
                
                if attempt < self.config.max_retry_attempts:
                    logger.warning(f"Database operation failed (attempt {attempt + 1}): {e}")
                else:
                    logger.error(f"Database operation failed after {attempt + 1} attempts: {e}")
        
        # All retry attempts exhausted
        raise last_exception
    
    async def _handle_success(self, result: Any, execution_time: float):
        """Handle successful operation execution"""
        async with self._state_lock:
            current_time = time.time()
            
            # Record metrics
            await self.metrics.record_request(
                success=True,
                response_time=execution_time
            )
            
            if self.config.log_successful_operations:
                logger.debug(f"PostgreSQL operation succeeded in {execution_time:.3f}s")
            
            # Update circuit state
            if self.state == PostgreSQLCircuitState.HALF_OPEN:
                self.success_count += 1
                if self.success_count >= self.config.success_threshold:
                    # Close the circuit
                    self.state = PostgreSQLCircuitState.CLOSED
                    self.failure_count = 0
                    self.recent_failures.clear()
                    await self.metrics.record_circuit_state_change(self.state)
                    logger.info(f"Circuit breaker '{self.name}' CLOSED after {self.success_count} successes")
            
            elif self.state == PostgreSQLCircuitState.CLOSED:
                # Clean up old failures outside time window
                self._cleanup_old_failures(current_time)
    
    async def _handle_failure(self, error: Exception, start_time: float) -> PostgreSQLOperationResult:
        """Handle operation failure"""
        execution_time = time.time() - start_time
        error_category, should_trigger_cb = ErrorClassifier.classify_error(error)
        error_message = str(error)
        
        # Record metrics
        await self.metrics.record_request(
            success=False,
            response_time=execution_time,
            error_category=error_category,
            error_details=type(error).__name__
        )
        
        # Log the error
        if self.config.enable_detailed_logging:
            logger.error(
                f"PostgreSQL operation failed in {execution_time:.3f}s: "
                f"{error_category.value} - {error_message}"
            )
        
        # Update circuit state if error should trigger circuit breaker
        if should_trigger_cb:
            await self._update_failure_state()
        
        # Try fallback if available and appropriate
        if self.fallback_handler and error_category in [ErrorCategory.TRANSIENT, ErrorCategory.TIMEOUT]:
            try:
                fallback_result = await self._execute_fallback()
                return PostgreSQLOperationResult(
                    success=True,
                    value=fallback_result,
                    error="Used fallback due to: " + error_message,
                    error_category=error_category,
                    from_fallback=True,
                    execution_time=execution_time,
                    circuit_state=self.state
                )
            except Exception as fallback_error:
                logger.error(f"Fallback also failed: {fallback_error}")
                await self.metrics.record_fallback(success=False)
        
        return PostgreSQLOperationResult(
            success=False,
            error=error_message,
            error_category=error_category,
            execution_time=execution_time,
            circuit_state=self.state
        )
    
    async def _update_failure_state(self):
        """Update circuit state after a failure"""
        async with self._state_lock:
            current_time = time.time()
            
            # Add failure to recent failures
            self.recent_failures.append(current_time)
            self._cleanup_old_failures(current_time)
            
            # Check if we should open the circuit
            if self.state == PostgreSQLCircuitState.CLOSED:
                if len(self.recent_failures) >= self.config.failure_threshold:
                    # Open the circuit
                    self.state = PostgreSQLCircuitState.OPEN
                    self.next_attempt_time = current_time + self.config.timeout
                    await self.metrics.record_circuit_state_change(self.state)
                    logger.warning(
                        f"Circuit breaker '{self.name}' OPENED after {len(self.recent_failures)} failures "
                        f"in {self.config.time_window}s window"
                    )
            
            elif self.state == PostgreSQLCircuitState.HALF_OPEN:
                # Failure in half-open state - go back to open
                self.state = PostgreSQLCircuitState.OPEN
                self.next_attempt_time = current_time + self.config.timeout
                self.success_count = 0
                await self.metrics.record_circuit_state_change(self.state)
                logger.warning(f"Circuit breaker '{self.name}' returned to OPEN from HALF_OPEN")
    
    def _cleanup_old_failures(self, current_time: float):
        """Remove failures outside the time window"""
        cutoff_time = current_time - self.config.time_window
        while self.recent_failures and self.recent_failures[0] < cutoff_time:
            self.recent_failures.popleft()
    
    async def _handle_circuit_open(self, start_time: float) -> PostgreSQLOperationResult:
        """Handle execution when circuit is open"""
        execution_time = time.time() - start_time
        
        logger.debug(f"Circuit breaker '{self.name}' is OPEN - failing fast")
        
        # Try fallback if available
        if self.fallback_handler:
            try:
                fallback_result = await self._execute_fallback()
                return PostgreSQLOperationResult(
                    success=True,
                    value=fallback_result,
                    error="Circuit open - used fallback",
                    from_fallback=True,
                    execution_time=execution_time,
                    circuit_state=self.state
                )
            except Exception as fallback_error:
                logger.error(f"Fallback failed while circuit open: {fallback_error}")
                await self.metrics.record_fallback(success=False)
        
        return PostgreSQLOperationResult(
            success=False,
            error="Circuit breaker is OPEN - failing fast",
            execution_time=execution_time,
            circuit_state=self.state
        )
    
    async def _execute_fallback(self) -> Any:
        """Execute fallback handler"""
        logger.info(f"Executing fallback for circuit breaker '{self.name}'")
        
        if asyncio.iscoroutinefunction(self.fallback_handler):
            result = await asyncio.wait_for(
                self.fallback_handler(),
                timeout=self.config.fallback_timeout
            )
        else:
            result = self.fallback_handler()
        
        await self.metrics.record_fallback(success=True)
        return result
    
    async def health_check(self, db_session) -> bool:
        """Perform health check on database connection"""
        try:
            start_time = time.time()
            
            # Execute simple health check query
            if hasattr(db_session, 'execute'):
                await asyncio.wait_for(
                    db_session.execute(self.config.health_check_query),
                    timeout=self.config.health_check_timeout
                )
            else:
                # For non-async sessions
                db_session.execute(self.config.health_check_query)
            
            execution_time = time.time() - start_time
            await self.metrics.record_health_check(success=True)
            
            logger.debug(f"Health check passed in {execution_time:.3f}s")
            return True
            
        except Exception as e:
            await self.metrics.record_health_check(success=False)
            logger.warning(f"Health check failed: {e}")
            return False
    
    async def get_state(self) -> Dict[str, Any]:
        """Get current circuit breaker state and metrics"""
        async with self._state_lock:
            metrics_summary = await self.metrics.get_summary()
            
            return {
                'name': self.name,
                'state': self.state.value,
                'failure_count': len(self.recent_failures),
                'success_count': self.success_count,
                'next_attempt_time': self.next_attempt_time if self.state == PostgreSQLCircuitState.OPEN else None,
                'time_until_retry': max(0, self.next_attempt_time - time.time()) if self.state == PostgreSQLCircuitState.OPEN else 0,
                'config': {
                    'failure_threshold': self.config.failure_threshold,
                    'success_threshold': self.config.success_threshold,
                    'timeout': self.config.timeout,
                    'time_window': self.config.time_window
                },
                'metrics': metrics_summary
            }
    
    async def reset(self):
        """Reset circuit breaker state and metrics"""
        async with self._state_lock:
            self.state = PostgreSQLCircuitState.CLOSED
            self.failure_count = 0
            self.success_count = 0
            self.last_failure_time = 0
            self.next_attempt_time = 0
            self.recent_failures.clear()
            self.metrics.reset()
            
            logger.info(f"Circuit breaker '{self.name}' has been reset")
    
    async def force_open(self):
        """Force circuit breaker to open state (for testing)"""
        async with self._state_lock:
            self.state = PostgreSQLCircuitState.OPEN
            self.next_attempt_time = time.time() + self.config.timeout
            await self.metrics.record_circuit_state_change(self.state)
            
            logger.warning(f"Circuit breaker '{self.name}' FORCED OPEN")
    
    async def force_close(self):
        """Force circuit breaker to close state (for testing)"""
        async with self._state_lock:
            self.state = PostgreSQLCircuitState.CLOSED
            self.failure_count = 0
            self.recent_failures.clear()
            await self.metrics.record_circuit_state_change(self.state)
            
            logger.info(f"Circuit breaker '{self.name}' FORCED CLOSED")

def circuit_breaker(
    name: str,
    config: Optional[PostgreSQLCircuitBreakerConfig] = None,
    fallback: Optional[Callable] = None
):
    """
    Decorator for applying circuit breaker protection to async database functions
    
    Usage:
        @circuit_breaker('user_queries', fallback=get_user_from_cache)
        async def get_user_from_db(user_id):
            # Database operation here
            pass
    """
    cb = PostgreSQLCircuitBreaker(name, config, fallback)
    
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            result = await cb(func, *args, **kwargs)
            if not result.success:
                if result.from_fallback:
                    return result.value
                else:
                    # Re-raise the original exception
                    raise Exception(result.error)
            return result.value
        
        # Attach circuit breaker instance to function for monitoring
        wrapper._circuit_breaker = cb
        return wrapper
    
    return decorator
