"""
Circuit Breaker Implementation for Redis Operations
Provides resilience and fault tolerance for Redis connectivity issues
"""

import time
import threading
import json
import logging
from enum import Enum
from typing import Dict, List, Optional, Any, Callable, Tuple
from collections import deque, defaultdict
from dataclasses import dataclass
from functools import wraps

class CircuitState(Enum):
    """Circuit breaker states"""
    CLOSED = "closed"       # Normal operation
    OPEN = "open"           # Circuit is open, failing fast
    HALF_OPEN = "half_open" # Testing if service has recovered

@dataclass
class CircuitBreakerConfig:
    """Circuit breaker configuration"""
    failure_threshold: int = 5          # Number of failures to open circuit
    success_threshold: int = 3          # Number of successes to close circuit from half-open
    timeout: float = 60.0               # Seconds to wait before trying half-open
    time_window: float = 300.0          # Time window for failure tracking (5 minutes)
    max_retry_attempts: int = 3         # Max retries with exponential backoff
    base_backoff_delay: float = 1.0     # Base delay for exponential backoff
    max_backoff_delay: float = 30.0     # Maximum backoff delay

@dataclass
class OperationResult:
    """Result of a circuit-protected operation"""
    success: bool
    value: Any = None
    error: str = ""
    from_cache: bool = False
    execution_time: float = 0.0

class CircuitBreakerMetrics:
    """Metrics collection for circuit breaker"""
    
    def __init__(self):
        self._lock = threading.Lock()
        self.reset()
    
    def reset(self):
        """Reset all metrics"""
        with self._lock:
            self.total_requests = 0
            self.total_failures = 0
            self.total_successes = 0
            self.circuit_opens = 0
            self.circuit_closes = 0
            self.fallback_executions = 0
            self.cache_hits = 0
            self.avg_response_time = 0.0
            self.response_times = deque(maxlen=1000)  # Keep last 1000 response times
            self.failure_reasons = defaultdict(int)
    
    def record_request(self, success: bool, response_time: float, error_type: str = ""):
        """Record a request result"""
        with self._lock:
            self.total_requests += 1
            self.response_times.append(response_time)
            
            if success:
                self.total_successes += 1
            else:
                self.total_failures += 1
                if error_type:
                    self.failure_reasons[error_type] += 1
            
            # Update average response time
            if self.response_times:
                self.avg_response_time = sum(self.response_times) / len(self.response_times)
    
    def record_circuit_open(self):
        """Record circuit opening"""
        with self._lock:
            self.circuit_opens += 1
    
    def record_circuit_close(self):
        """Record circuit closing"""
        with self._lock:
            self.circuit_closes += 1
    
    def record_fallback(self):
        """Record fallback execution"""
        with self._lock:
            self.fallback_executions += 1
    
    def record_cache_hit(self):
        """Record cache hit"""
        with self._lock:
            self.cache_hits += 1
    
    def get_failure_rate(self) -> float:
        """Get current failure rate"""
        with self._lock:
            if self.total_requests == 0:
                return 0.0
            return self.total_failures / self.total_requests
    
    def get_metrics_dict(self) -> Dict[str, Any]:
        """Get all metrics as dictionary"""
        with self._lock:
            return {
                'total_requests': self.total_requests,
                'total_failures': self.total_failures,
                'total_successes': self.total_successes,
                'failure_rate': self.get_failure_rate(),
                'circuit_opens': self.circuit_opens,
                'circuit_closes': self.circuit_closes,
                'fallback_executions': self.fallback_executions,
                'cache_hits': self.cache_hits,
                'avg_response_time': self.avg_response_time,
                'failure_reasons': dict(self.failure_reasons)
            }

class TimeWindow:
    """Sliding time window for tracking failures"""
    
    def __init__(self, window_size: float):
        self.window_size = window_size
        self.events = deque()
        self._lock = threading.Lock()
    
    def add_event(self, success: bool):
        """Add an event to the time window"""
        current_time = time.time()
        with self._lock:
            self.events.append((current_time, success))
            self._cleanup_old_events(current_time)
    
    def get_failure_count(self) -> int:
        """Get number of failures in current window"""
        current_time = time.time()
        with self._lock:
            self._cleanup_old_events(current_time)
            return sum(1 for _, success in self.events if not success)
    
    def get_total_count(self) -> int:
        """Get total number of events in current window"""
        current_time = time.time()
        with self._lock:
            self._cleanup_old_events(current_time)
            return len(self.events)
    
    def _cleanup_old_events(self, current_time: float):
        """Remove events older than window size"""
        cutoff_time = current_time - self.window_size
        while self.events and self.events[0][0] < cutoff_time:
            self.events.popleft()

class FallbackCache:
    """Simple in-memory cache for fallback operations"""
    
    def __init__(self, max_size: int = 1000, ttl: float = 300.0):
        self.max_size = max_size
        self.ttl = ttl
        self.cache = {}
        self._lock = threading.Lock()
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        with self._lock:
            if key in self.cache:
                value, timestamp = self.cache[key]
                if time.time() - timestamp < self.ttl:
                    return value
                else:
                    del self.cache[key]
            return None
    
    def set(self, key: str, value: Any):
        """Set value in cache"""
        with self._lock:
            # Clean up expired entries if cache is full
            if len(self.cache) >= self.max_size:
                self._cleanup_expired()
                
                # If still full, remove oldest entries
                if len(self.cache) >= self.max_size:
                    # Remove 10% of entries (oldest first)
                    items_to_remove = sorted(self.cache.items(), key=lambda x: x[1][1])
                    for i in range(len(items_to_remove) // 10):
                        del self.cache[items_to_remove[i][0]]
            
            self.cache[key] = (value, time.time())
    
    def _cleanup_expired(self):
        """Remove expired entries"""
        current_time = time.time()
        expired_keys = [
            key for key, (_, timestamp) in self.cache.items()
            if current_time - timestamp >= self.ttl
        ]
        for key in expired_keys:
            del self.cache[key]
    
    def clear(self):
        """Clear all cache entries"""
        with self._lock:
            self.cache.clear()

class CircuitBreaker:
    """Circuit breaker implementation for Redis operations"""
    
    def __init__(self, name: str, config: CircuitBreakerConfig = None):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self.state = CircuitState.CLOSED
        self.last_failure_time = 0.0
        self.consecutive_successes = 0
        self.time_window = TimeWindow(self.config.time_window)
        self.metrics = CircuitBreakerMetrics()
        self.cache = FallbackCache()
        self._lock = threading.RLock()
        
        # Set up logging
        self.logger = logging.getLogger(f"CircuitBreaker.{name}")
    
    def call(self, func: Callable, *args, fallback_func: Callable = None, cache_key: str = None, **kwargs) -> OperationResult:
        """Execute function with circuit breaker protection"""
        start_time = time.time()
        
        # Check circuit state
        if self._should_allow_request():
            try:
                # Try the main operation
                result = self._execute_with_retry(func, *args, **kwargs)
                execution_time = time.time() - start_time
                
                self._on_success()
                
                # Cache successful results if cache key provided
                if cache_key and result is not None:
                    self.cache.set(cache_key, result)
                
                self.metrics.record_request(True, execution_time)
                
                return OperationResult(
                    success=True,
                    value=result,
                    execution_time=execution_time
                )
                
            except Exception as e:
                execution_time = time.time() - start_time
                error_type = type(e).__name__
                
                self._on_failure()
                self.metrics.record_request(False, execution_time, error_type)
                
                # Try fallback mechanisms
                return self._try_fallback(fallback_func, cache_key, str(e), args, kwargs)
        else:
            # Circuit is open, try fallback immediately
            self.logger.warning(f"Circuit {self.name} is OPEN, using fallback")
            return self._try_fallback(fallback_func, cache_key, "Circuit breaker is OPEN", args, kwargs)
    
    def _should_allow_request(self) -> bool:
        """Check if request should be allowed based on circuit state"""
        with self._lock:
            if self.state == CircuitState.CLOSED:
                return True
            elif self.state == CircuitState.OPEN:
                # Check if timeout has passed
                if time.time() - self.last_failure_time >= self.config.timeout:
                    self.state = CircuitState.HALF_OPEN
                    self.consecutive_successes = 0
                    self.logger.info(f"Circuit {self.name} moving to HALF_OPEN state")
                    return True
                return False
            else:  # HALF_OPEN
                return True
    
    def _execute_with_retry(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with exponential backoff retry"""
        last_exception = None
        
        for attempt in range(self.config.max_retry_attempts):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_exception = e
                
                if attempt < self.config.max_retry_attempts - 1:
                    # Calculate backoff delay
                    delay = min(
                        self.config.base_backoff_delay * (2 ** attempt),
                        self.config.max_backoff_delay
                    )
                    
                    self.logger.warning(
                        f"Circuit {self.name} attempt {attempt + 1} failed: {str(e)}. "
                        f"Retrying in {delay:.2f}s"
                    )
                    time.sleep(delay)
        
        # All retries failed
        raise last_exception
    
    def _on_success(self):
        """Handle successful operation"""
        with self._lock:
            self.time_window.add_event(True)
            
            if self.state == CircuitState.HALF_OPEN:
                self.consecutive_successes += 1
                if self.consecutive_successes >= self.config.success_threshold:
                    self._close_circuit()
            elif self.state == CircuitState.OPEN:
                # This shouldn't happen, but handle gracefully
                self.state = CircuitState.HALF_OPEN
                self.consecutive_successes = 1
    
    def _on_failure(self):
        """Handle failed operation"""
        with self._lock:
            self.time_window.add_event(False)
            self.last_failure_time = time.time()
            self.consecutive_successes = 0
            
            # Check if we should open the circuit
            if self.state in [CircuitState.CLOSED, CircuitState.HALF_OPEN]:
                failure_count = self.time_window.get_failure_count()
                if failure_count >= self.config.failure_threshold:
                    self._open_circuit()
    
    def _open_circuit(self):
        """Open the circuit"""
        with self._lock:
            self.state = CircuitState.OPEN
            self.metrics.record_circuit_open()
            self.logger.error(f"Circuit {self.name} opened due to failures")
    
    def _close_circuit(self):
        """Close the circuit"""
        with self._lock:
            self.state = CircuitState.CLOSED
            self.consecutive_successes = 0
            self.metrics.record_circuit_close()
            self.logger.info(f"Circuit {self.name} closed - service recovered")
    
    def _try_fallback(self, fallback_func: Callable, cache_key: str, error: str, args: tuple, kwargs: dict) -> OperationResult:
        """Try fallback mechanisms"""
        # Try cache first
        if cache_key:
            cached_value = self.cache.get(cache_key)
            if cached_value is not None:
                self.metrics.record_cache_hit()
                self.logger.info(f"Circuit {self.name} using cached value for {cache_key}")
                return OperationResult(
                    success=True,
                    value=cached_value,
                    from_cache=True
                )
        
        # Try fallback function
        if fallback_func:
            try:
                self.metrics.record_fallback()
                result = fallback_func(*args, **kwargs)
                self.logger.info(f"Circuit {self.name} using fallback function")
                return OperationResult(
                    success=True,
                    value=result
                )
            except Exception as fallback_error:
                self.logger.error(f"Circuit {self.name} fallback failed: {str(fallback_error)}")
        
        # All fallbacks failed
        return OperationResult(
            success=False,
            error=error
        )
    
    def get_state(self) -> CircuitState:
        """Get current circuit state"""
        return self.state
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get circuit breaker metrics"""
        base_metrics = self.metrics.get_metrics_dict()
        base_metrics.update({
            'circuit_name': self.name,
            'circuit_state': self.state.value,
            'failure_count_in_window': self.time_window.get_failure_count(),
            'total_count_in_window': self.time_window.get_total_count(),
            'consecutive_successes': self.consecutive_successes,
            'cache_size': len(self.cache.cache)
        })
        return base_metrics
    
    def reset(self):
        """Reset circuit breaker to initial state"""
        with self._lock:
            self.state = CircuitState.CLOSED
            self.last_failure_time = 0.0
            self.consecutive_successes = 0
            self.time_window = TimeWindow(self.config.time_window)
            self.metrics.reset()
            self.cache.clear()
            self.logger.info(f"Circuit {self.name} reset to initial state")

def circuit_breaker(name: str, config: CircuitBreakerConfig = None, fallback: Callable = None, cache_key_func: Callable = None):
    """Decorator for applying circuit breaker to functions"""
    
    def decorator(func):
        cb = CircuitBreaker(name, config)
        
        @wraps(func)
        def wrapper(*args, **kwargs):
            cache_key = None
            if cache_key_func:
                cache_key = cache_key_func(*args, **kwargs)
            
            result = cb.call(func, *args, fallback_func=fallback, cache_key=cache_key, **kwargs)
            
            if result.success:
                return result.value
            else:
                raise Exception(result.error)
        
        # Attach circuit breaker to function for monitoring
        wrapper.circuit_breaker = cb
        return wrapper
    
    return decorator
