"""
PostgreSQL Circuit Breaker Integration
Integrates PostgreSQL circuit breaker with the async session manager
and provides transparent circuit breaking for database operations
"""

import asyncio
import logging
from typing import Optional, Dict, Any, Callable, TypeVar, Awaitable
from contextlib import asynccontextmanager
from functools import wraps

from .postgresql_circuit_breaker import (
    PostgreSQLCircuitBreaker, PostgreSQLCircuitBreakerConfig, 
    PostgreSQLOperationResult, circuit_breaker
)
from .circuit_breaker_monitor import PostgreSQLCircuitBreakerMonitor
from .session_manager import AsyncSessionManager

logger = logging.getLogger(__name__)

T = TypeVar('T')

class CircuitBreakerIntegratedSessionManager:
    """
    Enhanced AsyncSessionManager with circuit breaker integration
    
    Provides transparent circuit breaker protection for all database operations
    while maintaining the same interface as the original session manager
    """
    
    def __init__(
        self, 
        session_manager: AsyncSessionManager,
        enable_circuit_breaker: bool = True,
        circuit_breaker_config: Optional[PostgreSQLCircuitBreakerConfig] = None
    ):
        self.session_manager = session_manager
        self.enable_circuit_breaker = enable_circuit_breaker
        
        # Circuit breaker configuration
        self.cb_config = circuit_breaker_config or PostgreSQLCircuitBreakerConfig(
            failure_threshold=5,
            success_threshold=3,
            timeout=60.0,
            time_window=300.0,
            max_retry_attempts=3,
            base_backoff_delay=1.0,
            max_backoff_delay=30.0,
            enable_detailed_logging=True
        )
        
        # Circuit breaker instances
        self.circuit_breakers = {}
        self.monitor = PostgreSQLCircuitBreakerMonitor(session_manager)
        
        # Create default circuit breakers
        self._create_default_circuit_breakers()
        
        # Start monitoring
        if enable_circuit_breaker:
            asyncio.create_task(self.monitor.start_monitoring())
        
        logger.info("Circuit Breaker Integrated Session Manager initialized")
    
    def _create_default_circuit_breakers(self):
        """Create default circuit breakers for common operations"""
        
        # Main database operations
        self.circuit_breakers['database'] = self.monitor.create_circuit_breaker(
            'database_operations',
            config=self.cb_config,
            fallback_handler=self._database_fallback
        )
        
        # Read operations (can be more tolerant)
        read_config = PostgreSQLCircuitBreakerConfig(
            failure_threshold=8,
            success_threshold=3,
            timeout=30.0,
            max_retry_attempts=2
        )
        self.circuit_breakers['read'] = self.monitor.create_circuit_breaker(
            'read_operations',
            config=read_config,
            fallback_handler=self._read_fallback
        )
        
        # Write operations (less tolerant)
        write_config = PostgreSQLCircuitBreakerConfig(
            failure_threshold=3,
            success_threshold=2,
            timeout=120.0,
            max_retry_attempts=1
        )
        self.circuit_breakers['write'] = self.monitor.create_circuit_breaker(
            'write_operations',
            config=write_config
        )
        
        # Health check operations
        health_config = PostgreSQLCircuitBreakerConfig(
            failure_threshold=2,
            success_threshold=1,
            timeout=15.0,
            max_retry_attempts=1,
            health_check_timeout=3.0
        )
        self.circuit_breakers['health'] = self.monitor.create_circuit_breaker(
            'health_operations',
            config=health_config
        )
    
    async def _database_fallback(self) -> Any:
        """Fallback for general database operations"""
        logger.warning("Using database fallback - returning cached or default data")
        # Could integrate with Redis cache here
        return None
    
    async def _read_fallback(self) -> Any:
        """Fallback for read operations"""
        logger.warning("Using read fallback - returning cached data")
        # Could return cached data from Redis
        return None
    
    async def initialize(self):
        """Initialize the underlying session manager"""
        if self.enable_circuit_breaker:
            result = await self.circuit_breakers['database'](
                self.session_manager.initialize
            )
            if not result.success:
                if result.from_fallback:
                    logger.warning("Database initialization used fallback")
                else:
                    raise Exception(f"Database initialization failed: {result.error}")
        else:
            await self.session_manager.initialize()
    
    async def cleanup(self):
        """Cleanup resources"""
        try:
            await self.monitor.stop_monitoring()
        except Exception as e:
            logger.error(f"Error stopping circuit breaker monitoring: {e}")
        
        if self.enable_circuit_breaker:
            result = await self.circuit_breakers['database'](
                self.session_manager.cleanup
            )
            if not result.success:
                logger.error(f"Database cleanup failed: {result.error}")
        else:
            await self.session_manager.cleanup()
    
    @asynccontextmanager
    async def get_session(self):
        """Get database session with circuit breaker protection"""
        if not self.enable_circuit_breaker:
            async with self.session_manager.get_session() as session:
                yield session
            return
        
        cb = self.circuit_breakers['database']
        
        # Check if circuit is open
        if not await cb._can_execute():
            # Circuit is open - try fallback or fail
            if cb.fallback_handler:
                logger.warning("Database circuit is open - using fallback session")
                yield None  # Signal to use fallback
                return
            else:
                raise Exception("Database circuit breaker is OPEN and no fallback available")
        
        # Execute with circuit breaker protection
        try:
            async with self.session_manager.get_session() as session:
                yield CircuitBreakerProtectedSession(session, cb)
        except Exception as e:
            # Handle failure through circuit breaker
            await cb._handle_failure(e, 0)
            raise
    
    @asynccontextmanager
    async def get_transaction(self):
        """Get database transaction with circuit breaker protection"""
        if not self.enable_circuit_breaker:
            async with self.session_manager.get_transaction() as session:
                yield session
            return
        
        cb = self.circuit_breakers['write']  # Transactions are typically for writes
        
        # Check if circuit is open
        if not await cb._can_execute():
            if cb.fallback_handler:
                logger.warning("Write circuit is open - using fallback transaction")
                yield None  # Signal to use fallback
                return
            else:
                raise Exception("Write circuit breaker is OPEN and no fallback available")
        
        # Execute with circuit breaker protection
        try:
            async with self.session_manager.get_transaction() as session:
                yield CircuitBreakerProtectedSession(session, cb)
        except Exception as e:
            await cb._handle_failure(e, 0)
            raise
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check with circuit breaker protection"""
        if not self.enable_circuit_breaker:
            return await self.session_manager.health_check()
        
        cb = self.circuit_breakers['health']
        
        result = await cb(self.session_manager.health_check)
        
        if result.success:
            health_data = result.value
            # Add circuit breaker status to health check
            health_data['circuit_breaker'] = {
                'enabled': True,
                'status': await self.monitor.get_comprehensive_status()
            }
            return health_data
        else:
            return {
                'status': 'unhealthy',
                'error': result.error,
                'circuit_breaker': {
                    'enabled': True,
                    'state': result.circuit_state.value
                }
            }
    
    async def get_pool_stats(self) -> Dict[str, Any]:
        """Get connection pool statistics with circuit breaker info"""
        if not self.enable_circuit_breaker:
            return await self.session_manager.get_pool_stats()
        
        cb = self.circuit_breakers['database']
        
        result = await cb(self.session_manager.get_pool_stats)
        
        if result.success:
            pool_stats = result.value
            # Add circuit breaker metrics
            cb_state = await cb.get_state()
            pool_stats['circuit_breaker'] = {
                'state': cb_state['state'],
                'failure_count': cb_state['failure_count'],
                'metrics': cb_state['metrics']
            }
            return pool_stats
        else:
            return {
                'error': result.error,
                'circuit_breaker_state': result.circuit_state.value
            }
    
    async def execute_read_operation(self, operation: Callable[..., Awaitable[T]], *args, **kwargs) -> T:
        """Execute read operation with read circuit breaker"""
        if not self.enable_circuit_breaker:
            return await operation(*args, **kwargs)
        
        cb = self.circuit_breakers['read']
        result = await cb(operation, *args, **kwargs)
        
        if result.success:
            return result.value
        elif result.from_fallback:
            logger.warning("Read operation used fallback")
            return result.value
        else:
            raise Exception(f"Read operation failed: {result.error}")
    
    async def execute_write_operation(self, operation: Callable[..., Awaitable[T]], *args, **kwargs) -> T:
        """Execute write operation with write circuit breaker"""
        if not self.enable_circuit_breaker:
            return await operation(*args, **kwargs)
        
        cb = self.circuit_breakers['write']
        result = await cb(operation, *args, **kwargs)
        
        if result.success:
            return result.value
        else:
            raise Exception(f"Write operation failed: {result.error}")
    
    async def get_circuit_breaker_status(self) -> Dict[str, Any]:
        """Get comprehensive circuit breaker status"""
        if not self.enable_circuit_breaker:
            return {'enabled': False}
        
        return await self.monitor.get_comprehensive_status()
    
    async def reset_circuit_breakers(self):
        """Reset all circuit breakers"""
        if self.enable_circuit_breaker:
            await self.monitor.reset_all_circuit_breakers()

class CircuitBreakerProtectedSession:
    """
    Wrapper for database session that provides circuit breaker protection
    for individual session operations
    """
    
    def __init__(self, session, circuit_breaker: PostgreSQLCircuitBreaker):
        self.session = session
        self.circuit_breaker = circuit_breaker
    
    async def execute(self, statement, *args, **kwargs):
        """Execute statement with circuit breaker protection"""
        result = await self.circuit_breaker(
            self.session.execute, statement, *args, **kwargs
        )
        
        if result.success:
            return result.value
        else:
            raise Exception(f"Database execute failed: {result.error}")
    
    async def commit(self):
        """Commit transaction with circuit breaker protection"""
        result = await self.circuit_breaker(self.session.commit)
        
        if not result.success:
            raise Exception(f"Database commit failed: {result.error}")
    
    async def rollback(self):
        """Rollback transaction (typically doesn't need circuit breaker)"""
        await self.session.rollback()
    
    async def flush(self):
        """Flush session with circuit breaker protection"""
        result = await self.circuit_breaker(self.session.flush)
        
        if not result.success:
            raise Exception(f"Database flush failed: {result.error}")
    
    async def refresh(self, instance):
        """Refresh instance with circuit breaker protection"""
        result = await self.circuit_breaker(self.session.refresh, instance)
        
        if result.success:
            return result.value
        else:
            raise Exception(f"Database refresh failed: {result.error}")
    
    def add(self, instance):
        """Add instance to session (no circuit breaker needed)"""
        self.session.add(instance)
    
    def delete(self, instance):
        """Delete instance from session (no circuit breaker needed)"""
        self.session.delete(instance)
    
    def __getattr__(self, name):
        """Delegate other attributes to the underlying session"""
        return getattr(self.session, name)

# Decorator for protecting database functions
def db_circuit_breaker(
    operation_type: str = 'database',
    config: Optional[PostgreSQLCircuitBreakerConfig] = None,
    fallback: Optional[Callable] = None
):
    """
    Decorator for database operations with circuit breaker protection
    
    Args:
        operation_type: Type of operation ('read', 'write', 'database', 'health')
        config: Optional circuit breaker configuration
        fallback: Optional fallback function
    
    Usage:
        @db_circuit_breaker('read', fallback=get_from_cache)
        async def get_user_from_db(user_id):
            # Database operation
            pass
    """
    def decorator(func):
        # Create circuit breaker for this function
        cb_name = f"{func.__name__}_{operation_type}"
        cb = PostgreSQLCircuitBreaker(
            cb_name, 
            config or PostgreSQLCircuitBreakerConfig(),
            fallback
        )
        
        @wraps(func)
        async def wrapper(*args, **kwargs):
            result = await cb(func, *args, **kwargs)
            
            if result.success:
                return result.value
            elif result.from_fallback:
                logger.warning(f"Function {func.__name__} used fallback")
                return result.value
            else:
                raise Exception(f"Function {func.__name__} failed: {result.error}")
        
        # Attach circuit breaker for monitoring
        wrapper._circuit_breaker = cb
        return wrapper
    
    return decorator

# Global instance for easy access
_integrated_session_manager: Optional[CircuitBreakerIntegratedSessionManager] = None

async def get_circuit_breaker_session_manager() -> CircuitBreakerIntegratedSessionManager:
    """Get the global circuit breaker integrated session manager"""
    global _integrated_session_manager
    
    if _integrated_session_manager is None:
        from .session_manager import get_session_manager
        base_manager = await get_session_manager()
        _integrated_session_manager = CircuitBreakerIntegratedSessionManager(base_manager)
        await _integrated_session_manager.initialize()
    
    return _integrated_session_manager

# Context managers for easy use
@asynccontextmanager
async def get_db_session_with_circuit_breaker():
    """Get database session with circuit breaker protection"""
    manager = await get_circuit_breaker_session_manager()
    async with manager.get_session() as session:
        yield session

@asynccontextmanager
async def get_db_transaction_with_circuit_breaker():
    """Get database transaction with circuit breaker protection"""
    manager = await get_circuit_breaker_session_manager()
    async with manager.get_transaction() as session:
        yield session
