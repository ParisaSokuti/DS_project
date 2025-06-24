"""
Database Integration Wrapper with Circuit Breaker Protection
Provides easy-to-use database operations with comprehensive error handling
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Optional, Any, Dict, Callable, TypeVar

from sqlalchemy import select, update, delete

from .session_manager import AsyncSessionManager
from .postgresql_circuit_breaker import PostgreSQLCircuitBreaker, CircuitBreakerConfig, CircuitBreakerOpen
from .circuit_breaker_monitor import PostgreSQLCircuitBreakerMonitor, MonitoringConfig

logger = logging.getLogger(__name__)

T = TypeVar('T')

class DatabaseWrapper:
    """
    High-level database wrapper with circuit breaker protection
    Provides convenient methods for database operations with automatic error handling
    """
    
    def __init__(self, 
                 session_manager: Optional[AsyncSessionManager] = None,
                 redis_manager=None):  # Your existing RedisManager
        """
        Initialize database wrapper
        
        Args:
            session_manager: AsyncSessionManager instance
            redis_manager: Existing RedisManager for fallback and monitoring integration
        """
        self.session_manager = session_manager
        self.redis_manager = redis_manager
        self.is_initialized = False
        
        # Circuit breakers for different operation types
        self.circuit_breakers = {}
        self.circuit_monitor = None
        
        # Operation categories for circuit breaker isolation
        self.operation_categories = {
            'read': 'database_read_operations',
            'write': 'database_write_operations', 
            'transaction': 'database_transactions',
            'admin': 'database_admin_operations'
        }
    
    async def initialize(self):
        """Initialize the database wrapper with circuit breaker protection"""
        if self.is_initialized:
            logger.warning("Database wrapper already initialized")
            return
        
        try:
            logger.info("Initializing database wrapper with circuit breaker protection")
            
            # Initialize session manager if not provided
            if not self.session_manager:
                from .config import get_database_config
                config = get_database_config()
                self.session_manager = AsyncSessionManager(config)
                await self.session_manager.initialize()
            
            # Create circuit breakers for different operation types
            await self._setup_circuit_breakers()
            
            # Initialize monitoring
            await self._setup_monitoring()
            
            self.is_initialized = True
            logger.info("Database wrapper initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize database wrapper: {e}")
            raise
    
    async def _setup_circuit_breakers(self):
        """Setup circuit breakers for different operation categories"""
        
        # Read operations circuit breaker (more tolerant)
        read_config = CircuitBreakerConfig(
            failure_threshold=10,      # Allow more failures for reads
            recovery_timeout=30,       # Faster recovery
            success_threshold=2,       # Fewer successes needed
            call_timeout=15.0,         # Shorter timeout for reads
            max_retries=2,
            enable_fallback=True,      # Enable fallback for read operations
            fallback_cache_ttl=600     # 10-minute cache for reads
        )
        
        self.circuit_breakers['read'] = PostgreSQLCircuitBreaker(
            name=self.operation_categories['read'],
            config=read_config
        )
        
        # Write operations circuit breaker (strict)
        write_config = CircuitBreakerConfig(
            failure_threshold=5,       # Less tolerance for write failures
            recovery_timeout=60,       # Longer recovery time
            success_threshold=3,       # More successes needed
            call_timeout=30.0,         # Longer timeout for writes
            max_retries=3,
            enable_fallback=False,     # No fallback for writes (data consistency)
            fallback_cache_ttl=0
        )
        
        self.circuit_breakers['write'] = PostgreSQLCircuitBreaker(
            name=self.operation_categories['write'],
            config=write_config
        )
        
        # Transaction operations circuit breaker (very strict)
        transaction_config = CircuitBreakerConfig(
            failure_threshold=3,       # Very low tolerance
            recovery_timeout=120,      # Long recovery time
            success_threshold=5,       # Many successes needed
            call_timeout=60.0,         # Long timeout for transactions
            max_retries=1,             # Minimal retries
            enable_fallback=False,     # No fallback for transactions
            fallback_cache_ttl=0
        )
        
        self.circuit_breakers['transaction'] = PostgreSQLCircuitBreaker(
            name=self.operation_categories['transaction'],
            config=transaction_config
        )
        
        # Admin operations circuit breaker (moderate)
        admin_config = CircuitBreakerConfig(
            failure_threshold=5,
            recovery_timeout=60,
            success_threshold=3,
            call_timeout=45.0,
            max_retries=2,
            enable_fallback=False,     # No fallback for admin ops
            fallback_cache_ttl=0
        )
        
        self.circuit_breakers['admin'] = PostgreSQLCircuitBreaker(
            name=self.operation_categories['admin'],
            config=admin_config
        )
        
        logger.info(f"Setup {len(self.circuit_breakers)} circuit breakers for database operations")
    
    async def _setup_monitoring(self):
        """Setup comprehensive monitoring for all circuit breakers"""
        
        # Configure monitoring
        monitoring_config = MonitoringConfig(
            health_check_interval=30,
            metrics_collection_interval=60,
            alert_threshold_failure_rate=5.0,    # Alert at 5% failure rate
            alert_threshold_response_time=2.0,   # Alert at 2s response time
            enable_auto_recovery=True,
            recovery_probe_interval=60,
            log_detailed_metrics=True,
            export_metrics_to_redis=bool(self.redis_manager)
        )
        
        self.circuit_monitor = PostgreSQLCircuitBreakerMonitor(
            redis_manager=self.redis_manager,
            config=monitoring_config
        )
        
        # Register all circuit breakers
        for category, circuit_breaker in self.circuit_breakers.items():
            self.circuit_monitor.register_circuit_breaker(category, circuit_breaker)
        
        # Start monitoring
        await self.circuit_monitor.start_monitoring()
        
        logger.info("Database monitoring started for all circuit breakers")
    
    async def cleanup(self):
        """Cleanup database wrapper resources"""
        if not self.is_initialized:
            return
        
        logger.info("Cleaning up database wrapper")
        
        try:
            # Stop monitoring
            if self.circuit_monitor:
                await self.circuit_monitor.stop_monitoring()
            
            # Cleanup session manager
            if self.session_manager:
                await self.session_manager.cleanup()
            
            self.is_initialized = False
            logger.info("Database wrapper cleanup completed")
            
        except Exception as e:
            logger.error(f"Error during database wrapper cleanup: {e}")
    
    # READ OPERATIONS
    
    async def read_query(self, query, parameters=None, operation_name="read_query") -> Any:
        """
        Execute a read query with circuit breaker protection
        Falls back to cached data if available
        """
        if not self.is_initialized:
            raise RuntimeError("Database wrapper not initialized")
        
        async def execute_read():
            async with self.session_manager.get_session_with_circuit_breaker() as session:
                if parameters:
                    result = await session.execute(query, parameters)
                else:
                    result = await session.execute(query)
                return result
        
        try:
            return await self.circuit_breakers['read'].call(
                execute_read,
                operation_name=f"read_{operation_name}"
            )
        except CircuitBreakerOpen as e:
            logger.warning(f"Read circuit breaker open for {operation_name}: {e}")
            # Could fallback to Redis here if data is available
            raise
    
    async def get_by_id(self, model_class, id_value, operation_name=None) -> Optional[Any]:
        """Get a record by ID with circuit breaker protection"""
        operation_name = operation_name or f"get_{model_class.__name__.lower()}_by_id"
        
        async def get_record():
            async with self.session_manager.get_session_with_circuit_breaker() as session:
                result = await session.execute(
                    select(model_class).where(model_class.id == id_value)
                )
                return result.scalar_one_or_none()
        
        return await self.circuit_breakers['read'].call(
            get_record,
            operation_name=operation_name
        )
    
    async def query_all(self, model_class, filters=None, limit=100, operation_name=None) -> list:
        """Query multiple records with circuit breaker protection"""
        operation_name = operation_name or f"query_{model_class.__name__.lower()}_all"
        
        async def query_records():
            async with self.session_manager.get_session_with_circuit_breaker() as session:
                query = select(model_class)
                
                if filters:
                    for key, value in filters.items():
                        if hasattr(model_class, key):
                            query = query.where(getattr(model_class, key) == value)
                
                query = query.limit(limit)
                result = await session.execute(query)
                return list(result.scalars().all())
        
        return await self.circuit_breakers['read'].call(
            query_records,
            operation_name=operation_name
        )
    
    # WRITE OPERATIONS
    
    async def create_record(self, model_class, data: Dict[str, Any], operation_name=None) -> Any:
        """Create a new record with circuit breaker protection"""
        operation_name = operation_name or f"create_{model_class.__name__.lower()}"
        
        async def create():
            async with self.session_manager.get_transaction_with_circuit_breaker() as session:
                record = model_class(**data)
                session.add(record)
                await session.flush()
                await session.refresh(record)
                return record
        
        return await self.circuit_breakers['write'].call(
            create,
            operation_name=operation_name
        )
    
    async def update_record(self, model_class, id_value, data: Dict[str, Any], operation_name=None) -> Optional[Any]:
        """Update a record with circuit breaker protection"""
        operation_name = operation_name or f"update_{model_class.__name__.lower()}"
        
        async def update():
            async with self.session_manager.get_transaction_with_circuit_breaker() as session:
                result = await session.execute(
                    update(model_class)
                    .where(model_class.id == id_value)
                    .values(**data)
                    .returning(model_class)
                )
                updated_record = result.scalar_one_or_none()
                if updated_record:
                    await session.refresh(updated_record)
                return updated_record
        
        return await self.circuit_breakers['write'].call(
            update,
            operation_name=operation_name
        )
    
    async def delete_record(self, model_class, id_value, operation_name=None) -> bool:
        """Delete a record with circuit breaker protection"""
        operation_name = operation_name or f"delete_{model_class.__name__.lower()}"
        
        async def delete():
            async with self.session_manager.get_transaction_with_circuit_breaker() as session:
                result = await session.execute(
                    delete(model_class).where(model_class.id == id_value)
                )
                return result.rowcount > 0
        
        return await self.circuit_breakers['write'].call(
            delete,
            operation_name=operation_name
        )
    
    # TRANSACTION OPERATIONS
    
    @asynccontextmanager
    async def transaction(self, operation_name="database_transaction"):
        """
        Database transaction context manager with circuit breaker protection
        
        Usage:
            async with db_wrapper.transaction("user_creation") as session:
                user = User(username="alice")
                session.add(user)
                # Transaction automatically committed or rolled back
        """
        async def get_transaction_session():
            return self.session_manager.get_transaction_with_circuit_breaker()
        
        transaction_context = await self.circuit_breakers['transaction'].call(
            get_transaction_session,
            operation_name=f"transaction_{operation_name}"
        )
        
        async with transaction_context as session:
            yield session
    
    async def execute_transaction(self, func: Callable, *args, operation_name="custom_transaction", **kwargs) -> T:
        """
        Execute a function within a transaction with circuit breaker protection
        
        Args:
            func: Async function that takes session as first argument
            *args: Additional arguments for the function
            operation_name: Name for monitoring
            **kwargs: Additional keyword arguments for the function
        """
        async def transaction_wrapper():
            async with self.transaction(operation_name) as session:
                return await func(session, *args, **kwargs)
        
        return await transaction_wrapper()
    
    # HEALTH AND MONITORING
    
    async def health_check(self) -> Dict[str, Any]:
        """Comprehensive health check for all database operations"""
        health_status = {
            'database_wrapper': {
                'status': 'healthy',
                'initialized': self.is_initialized,
                'timestamp': asyncio.get_event_loop().time()
            },
            'session_manager': {},
            'circuit_breakers': {},
            'monitoring': {}
        }
        
        try:
            # Session manager health
            if self.session_manager:
                health_status['session_manager'] = await self.session_manager.get_comprehensive_health_status()
            
            # Circuit breaker health
            for category, circuit_breaker in self.circuit_breakers.items():
                health_status['circuit_breakers'][category] = {
                    'state': circuit_breaker.get_state(),
                    'metrics': circuit_breaker.get_metrics()
                }
            
            # Monitoring health
            if self.circuit_monitor:
                health_status['monitoring'] = self.circuit_monitor.get_unified_health_status()
            
        except Exception as e:
            logger.error(f"Error in health check: {e}")
            health_status['database_wrapper']['status'] = 'unhealthy'
            health_status['database_wrapper']['error'] = str(e)
        
        return health_status
    
    async def get_metrics(self) -> Dict[str, Any]:
        """Get comprehensive metrics for all database operations"""
        if not self.circuit_monitor:
            return {'error': 'Monitoring not initialized'}
        
        return await self.circuit_monitor.get_comprehensive_metrics()
    
    async def reset_circuit_breakers(self):
        """Reset all circuit breakers"""
        logger.info("Resetting all database circuit breakers")
        
        for category, circuit_breaker in self.circuit_breakers.items():
            try:
                await circuit_breaker.reset()
                logger.info(f"Reset circuit breaker for {category}")
            except Exception as e:
                logger.error(f"Failed to reset circuit breaker for {category}: {e}")
    
    def get_dashboard_data(self) -> Dict[str, Any]:
        """Get data for monitoring dashboard"""
        if not self.circuit_monitor:
            return {'error': 'Monitoring not available'}
        
        return self.circuit_monitor.get_dashboard_data()

# Global instance for easy access
_database_wrapper: Optional[DatabaseWrapper] = None

async def get_database_wrapper(redis_manager=None) -> DatabaseWrapper:
    """Get the global database wrapper instance"""
    global _database_wrapper
    
    if _database_wrapper is None:
        _database_wrapper = DatabaseWrapper(redis_manager=redis_manager)
        await _database_wrapper.initialize()
    
    return _database_wrapper

async def cleanup_database_wrapper():
    """Cleanup the global database wrapper"""
    global _database_wrapper
    
    if _database_wrapper:
        await _database_wrapper.cleanup()
        _database_wrapper = None

# Convenience functions for common operations
async def safe_database_read(func: Callable, *args, operation_name="read_operation", **kwargs) -> Any:
    """Safely execute a database read operation with circuit breaker protection"""
    db_wrapper = await get_database_wrapper()
    
    async def read_operation():
        return await func(*args, **kwargs)
    
    return await db_wrapper.circuit_breakers['read'].call(
        read_operation,
        operation_name=operation_name
    )

async def safe_database_write(func: Callable, *args, operation_name="write_operation", **kwargs) -> Any:
    """Safely execute a database write operation with circuit breaker protection"""
    db_wrapper = await get_database_wrapper()
    
    async def write_operation():
        return await func(*args, **kwargs)
    
    return await db_wrapper.circuit_breakers['write'].call(
        write_operation,
        operation_name=operation_name
    )

# Decorators for easy circuit breaker application
def database_read_operation(operation_name: str = None):
    """Decorator for database read operations"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            return await safe_database_read(
                func, *args, 
                operation_name=operation_name or func.__name__, 
                **kwargs
            )
        return wrapper
    return decorator

def database_write_operation(operation_name: str = None):
    """Decorator for database write operations"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            return await safe_database_write(
                func, *args, 
                operation_name=operation_name or func.__name__, 
                **kwargs
            )
        return wrapper
    return decorator
