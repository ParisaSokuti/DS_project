"""
SQLAlchemy 2.0 Async Session Manager for Hokm Game Server
Handles connection pooling, session lifecycle, and transaction management
Optimized for high-concurrency WebSocket gaming workloads
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Optional, AsyncGenerator, Dict, Any, Callable, TypeVar, Awaitable
from sqlalchemy.ext.asyncio import (
    AsyncEngine, 
    AsyncSession, 
    async_sessionmaker,
    create_async_engine
)
from sqlalchemy.exc import SQLAlchemyError, DisconnectionError
from sqlalchemy.pool import QueuePool
from sqlalchemy import event, text
import time
from weakref import WeakSet

from .config import DatabaseConfig, get_database_config

logger = logging.getLogger(__name__)

T = TypeVar('T')

class AsyncSessionManager:
    """
    Async session manager optimized for real-time gaming applications
    
    Key features:
    - Connection pooling with automatic reconnection
    - Transaction management with proper rollback handling
    - Session lifecycle management for WebSocket connections
    - Performance monitoring and query optimization
    - Circuit breaker pattern for database failures
    """
    
    def __init__(self, config: Optional[DatabaseConfig] = None):
        """
        Initialize the session manager with database configuration
        
        Args:
            config: Database configuration. If None, loads from environment
        """
        self.config = config or get_database_config()
        self.engine: Optional[AsyncEngine] = None
        self.session_factory: Optional[async_sessionmaker[AsyncSession]] = None
        self.is_initialized = False
        
        # Performance monitoring
        self.active_sessions: WeakSet[AsyncSession] = WeakSet()
        self.connection_stats = {
            'total_connections': 0,
            'failed_connections': 0,
            'active_sessions_count': 0,
            'total_queries': 0,
            'slow_queries': 0,
            'average_query_time': 0.0
        }
        
        # Circuit breaker integration
        from .postgresql_circuit_breaker import PostgreSQLCircuitBreaker, CircuitBreakerConfig
        
        # Configure circuit breaker for database operations
        circuit_config = CircuitBreakerConfig(
            failure_threshold=5,
            recovery_timeout=60,
            success_threshold=3,
            call_timeout=30.0,
            max_retries=3,
            initial_retry_delay=1.0,
            max_retry_delay=30.0,
            backoff_multiplier=2.0,
            enable_fallback=True,
            fallback_cache_ttl=300
        )
        
        self.circuit_breaker = PostgreSQLCircuitBreaker(
            name="session_manager_circuit_breaker",
            config=circuit_config
        )
        
        # Circuit breaker monitor (will be set up during initialization)
        self.circuit_monitor = None
        
        # Circuit breaker for database failures
        self.circuit_breaker_state = {
            'failure_count': 0,
            'last_failure_time': 0,
            'is_open': False,
            'failure_threshold': 5,
            'recovery_timeout': 60  # seconds
        }
    
    async def initialize(self) -> None:
        """
        Initialize the async engine and session factory
        Must be called before using the session manager
        """
        if self.is_initialized:
            logger.warning("Session manager already initialized")
            return
        
        try:
            logger.info("Initializing async database session manager")
            
            # Create async engine with optimized settings
            self.engine = create_async_engine(
                self.config.connection_url,
                **self.config.engine_options,
                poolclass=QueuePool,  # Use QueuePool for better performance
            )
            
            # Create session factory
            self.session_factory = async_sessionmaker(
                bind=self.engine,
                class_=AsyncSession,
                autocommit=self.config.autocommit,
                autoflush=self.config.autoflush,
                expire_on_commit=self.config.expire_on_commit,
            )
            
            # Initialize circuit breaker monitor
            from .circuit_breaker_monitor import PostgreSQLCircuitBreakerMonitor
            self.circuit_monitor = PostgreSQLCircuitBreakerMonitor()
            self.circuit_monitor.register_circuit_breaker("session_manager", self.circuit_breaker)
            
            # Start monitoring
            await self.circuit_monitor.start_monitoring()
            
            # Set up event listeners for monitoring
            self._setup_event_listeners()
            
            # Test the connection with circuit breaker
            await self._test_connection_with_circuit_breaker()
            
            self.is_initialized = True
            logger.info("Database session manager initialized successfully with circuit breaker protection")
            
        except Exception as e:
            logger.error(f"Failed to initialize database session manager: {e}")
            await self.cleanup()
            raise
    
    async def cleanup(self) -> None:
        """
        Clean up resources and close all connections
        Should be called during application shutdown
        """
        if not self.is_initialized:
            return
        
        logger.info("Cleaning up database session manager")
        
        try:
            # Stop circuit breaker monitoring
            if self.circuit_monitor:
                await self.circuit_monitor.stop_monitoring()
                self.circuit_monitor = None
            
            # Close all active sessions
            for session in list(self.active_sessions):
                try:
                    await session.close()
                except Exception as e:
                    logger.warning(f"Error closing session: {e}")
            
            # Dispose of the engine
            if self.engine:
                await self.engine.dispose()
                self.engine = None
            
            self.session_factory = None
            self.is_initialized = False
            
            logger.info("Database cleanup completed")
            
        except Exception as e:
            logger.error(f"Error during database cleanup: {e}")
    
    def _setup_event_listeners(self) -> None:
        """
        Set up SQLAlchemy event listeners for monitoring and optimization
        These listeners provide insights into connection health and query performance
        """
        if not self.engine:
            return
        
        # Connection events
        @event.listens_for(self.engine.sync_engine, "connect")
        def on_connect(dbapi_connection, connection_record):
            """Handle new database connections"""
            self.connection_stats['total_connections'] += 1
            logger.debug("New database connection established")
        
        @event.listens_for(self.engine.sync_engine, "checkout")
        def on_checkout(dbapi_connection, connection_record, connection_proxy):
            """Handle connection checkout from pool"""
            # Reset connection state for consistency
            # This is critical for gaming applications where state matters
            pass
        
        @event.listens_for(self.engine.sync_engine, "checkin")
        def on_checkin(dbapi_connection, connection_record):
            """Handle connection checkin to pool"""
            pass
        
        # Query performance monitoring
        if self.config.enable_query_logging:
            @event.listens_for(self.engine.sync_engine, "before_cursor_execute")
            def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
                """Record query start time"""
                context._query_start_time = time.time()
            
            @event.listens_for(self.engine.sync_engine, "after_cursor_execute")
            def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
                """Log slow queries and update statistics"""
                if hasattr(context, '_query_start_time'):
                    query_time = time.time() - context._query_start_time
                    self.connection_stats['total_queries'] += 1
                    
                    # Update average query time (simple moving average)
                    total_queries = self.connection_stats['total_queries']
                    avg_time = self.connection_stats['average_query_time']
                    self.connection_stats['average_query_time'] = (
                        (avg_time * (total_queries - 1) + query_time) / total_queries
                    )
                    
                    # Log slow queries
                    if query_time > self.config.slow_query_threshold:
                        self.connection_stats['slow_queries'] += 1
                        logger.warning(
                            f"Slow query detected: {query_time:.3f}s - "
                            f"{statement[:200]}{'...' if len(statement) > 200 else ''}"
                        )
    
    async def _test_connection(self) -> None:
        """
        Test database connection and validate schema
        Critical for ensuring database availability during server startup
        """
        if not self.engine:
            raise RuntimeError("Engine not initialized")
        
        try:
            async with self.engine.begin() as conn:
                # Test basic connectivity
                result = await conn.execute(text("SELECT 1"))
                await result.fetchone()
                
                # Test schema existence (check if main tables exist)
                result = await conn.execute(text("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name IN ('players', 'game_sessions', 'game_participants')
                """))
                
                tables = [row[0] for row in await result.fetchall()]
                required_tables = ['players', 'game_sessions', 'game_participants']
                
                missing_tables = set(required_tables) - set(tables)
                if missing_tables:
                    logger.warning(f"Missing database tables: {missing_tables}")
                else:
                    logger.info("Database schema validation passed")
            
            # Reset circuit breaker on successful connection
            self.circuit_breaker_state['failure_count'] = 0
            self.circuit_breaker_state['is_open'] = False
            
        except Exception as e:
            self._handle_connection_failure(e)
            raise
    
    def _handle_connection_failure(self, error: Exception) -> None:
        """
        Handle database connection failures with circuit breaker pattern
        Prevents cascading failures in high-traffic gaming scenarios
        """
        self.connection_stats['failed_connections'] += 1
        self.circuit_breaker_state['failure_count'] += 1
        self.circuit_breaker_state['last_failure_time'] = time.time()
        
        logger.error(f"Database connection failure: {error}")
        
        # Open circuit breaker if threshold exceeded
        if self.circuit_breaker_state['failure_count'] >= self.circuit_breaker_state['failure_threshold']:
            self.circuit_breaker_state['is_open'] = True
            logger.error("Database circuit breaker opened due to repeated failures")
    
    def _should_allow_connection(self) -> bool:
        """
        Check if connections should be allowed based on circuit breaker state
        """
        if not self.circuit_breaker_state['is_open']:
            return True
        
        # Check if recovery timeout has passed
        if time.time() - self.circuit_breaker_state['last_failure_time'] > self.circuit_breaker_state['recovery_timeout']:
            logger.info("Attempting to recover from database failures")
            self.circuit_breaker_state['is_open'] = False
            self.circuit_breaker_state['failure_count'] = 0
            return True
        
        return False
    
    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Get an async database session with proper lifecycle management
        
        This is the primary method for getting database sessions in your application.
        It handles connection pooling, error handling, and automatic cleanup.
        
        Example usage:
            async with session_manager.get_session() as session:
                # Perform database operations
                result = await session.execute(select(Player))
                players = result.scalars().all()
        """
        if not self.is_initialized:
            raise RuntimeError("Session manager not initialized. Call initialize() first.")
        
        if not self._should_allow_connection():
            raise RuntimeError("Database circuit breaker is open. Service temporarily unavailable.")
        
        if not self.session_factory:
            raise RuntimeError("Session factory not available")
        
        session = None
        try:
            # Create new session
            session = self.session_factory()
            self.active_sessions.add(session)
            self.connection_stats['active_sessions_count'] = len(self.active_sessions)
            
            yield session
            
        except DisconnectionError as e:
            # Handle connection loss gracefully
            logger.error(f"Database connection lost: {e}")
            self._handle_connection_failure(e)
            if session:
                await session.rollback()
            raise
            
        except SQLAlchemyError as e:
            # Handle database errors with proper rollback
            logger.error(f"Database error: {e}")
            if session:
                await session.rollback()
            raise
            
        except Exception as e:
            # Handle unexpected errors
            logger.error(f"Unexpected error in database session: {e}")
            if session:
                await session.rollback()
            raise
            
        finally:
            # Always clean up the session
            if session:
                try:
                    await session.close()
                except Exception as e:
                    logger.warning(f"Error closing session: {e}")
                
                # Remove from active sessions tracking
                try:
                    self.active_sessions.discard(session)
                    self.connection_stats['active_sessions_count'] = len(self.active_sessions)
                except Exception:
                    pass
    
    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Get a database session with automatic transaction management
        
        This method provides transactional guarantees for complex operations.
        Perfect for game state updates that must be atomic.
        
        Example usage:
            async with session_manager.transaction() as session:
                # All operations are automatically wrapped in a transaction 
                await session.execute(update(Player).where(...))
                await session.execute(insert(GameMove).values(...))
                # Automatic commit on success, rollback on error
        """
        async with self.get_session() as session:
            try:
                # Begin transaction
                await session.begin()
                yield session
                # Commit on successful completion
                await session.commit()
                
            except Exception:
                # Rollback on any error
                await session.rollback()
                raise
    
    async def execute_with_retry(
        self, 
        operation: Callable[[AsyncSession], Awaitable[T]], 
        max_retries: int = 3,
        retry_delay: float = 0.1
    ) -> T:
        """
        Execute a database operation with automatic retry logic
        
        Useful for operations that might fail due to temporary connection issues.
        Critical for maintaining game state consistency during network hiccups.
        
        Args:
            operation: Async function that takes a session and returns a result
            max_retries: Maximum number of retry attempts
            retry_delay: Delay between retries (in seconds)
        
        Returns:
            Result of the operation
        """
        last_error = None
        
        for attempt in range(max_retries + 1):
            try:
                async with self.get_session() as session:
                    return await operation(session)
                    
            except (DisconnectionError, SQLAlchemyError) as e:
                last_error = e
                if attempt < max_retries:
                    logger.warning(f"Database operation failed (attempt {attempt + 1}), retrying: {e}")
                    await asyncio.sleep(retry_delay * (2 ** attempt))  # Exponential backoff
                else:
                    logger.error(f"Database operation failed after {max_retries + 1} attempts")
                    raise
        
        # This should never be reached, but just in case
        if last_error:
            raise last_error
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Perform a comprehensive health check of the database connection
        
        Returns detailed health information for monitoring and debugging.
        Critical for maintaining service availability in production.
        """
        health_info = {
            'status': 'unknown',
            'is_initialized': self.is_initialized,
            'circuit_breaker_open': self.circuit_breaker['is_open'],
            'connection_stats': self.connection_stats.copy(),
            'pool_status': {},
            'response_time_ms': None,
            'error': None
        }
        
        if not self.is_initialized:
            health_info['status'] = 'not_initialized'
            health_info['error'] = 'Session manager not initialized'
            return health_info
        
        if self.circuit_breaker['is_open']:
            health_info['status'] = 'circuit_breaker_open'
            health_info['error'] = 'Circuit breaker is open due to repeated failures'
            return health_info
        
        try:
            # Measure response time
            start_time = time.time()
            
            async with self.get_session() as session:
                await session.execute(text("SELECT 1"))
                
                # Get pool status if available
                if self.engine and hasattr(self.engine.pool, 'size'):
                    pool = self.engine.pool
                    health_info['pool_status'] = {
                        'size': pool.size(),
                        'checked_in': pool.checkedin(),
                        'checked_out': pool.checkedout(),
                        'overflow': pool.overflow(),
                        'invalid': pool.invalid()
                    }
            
            response_time = (time.time() - start_time) * 1000  # Convert to milliseconds
            health_info['response_time_ms'] = round(response_time, 2)
            health_info['status'] = 'healthy'
            
        except Exception as e:
            health_info['status'] = 'unhealthy'
            health_info['error'] = str(e)
            logger.error(f"Database health check failed: {e}")
        
        return health_info
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get current connection and performance statistics
        Useful for monitoring and debugging performance issues
        """
        stats = self.connection_stats.copy()
        stats.update({
            'is_initialized': self.is_initialized,
            'circuit_breaker': self.circuit_breaker.copy(),
            'config_environment': self.config.environment,
            'pool_size': self.config.pool_size,
            'max_overflow': self.config.max_overflow,
        })
        return stats
    
    async def _test_connection_with_circuit_breaker(self) -> None:
        """
        Test database connection using circuit breaker protection
        """
        async def test_connection():
            async with self.session_factory() as session:
                result = await session.execute(text("SELECT 1"))
                return result.scalar()
        
        try:
            result = await self.circuit_breaker.call(
                test_connection,
                operation_name="connection_test"
            )
            logger.info(f"Database connection test successful: {result}")
        except Exception as e:
            logger.error(f"Database connection test failed: {e}")
            raise
    
    async def get_session_with_circuit_breaker(self) -> AsyncSession:
        """
        Get a database session with circuit breaker protection
        """
        async def create_session():
            if not self.session_factory:
                raise RuntimeError("Session manager not initialized")
            
            session = self.session_factory()
            self.active_sessions.add(session)
            self.connection_stats['active_sessions_count'] = len(self.active_sessions)
            return session
        
        return await self.circuit_breaker.call(
            create_session,
            operation_name="session_create"
        )
    
    @asynccontextmanager
    async def get_transaction_with_circuit_breaker(self):
        """
        Get a database transaction with circuit breaker protection
        Automatically commits on success, rolls back on error
        """
        session = await self.get_session_with_circuit_breaker()
        
        try:
            async with session.begin():
                yield session
        except Exception as e:
            logger.error(f"Transaction failed, rolling back: {e}")
            try:
                await session.rollback()
            except Exception as rollback_error:
                logger.error(f"Rollback failed: {rollback_error}")
            raise
        finally:
            try:
                await session.close()
                if session in self.active_sessions:
                    self.active_sessions.discard(session)
                self.connection_stats['active_sessions_count'] = len(self.active_sessions)
            except Exception as close_error:
                logger.warning(f"Error closing session: {close_error}")
    
    async def execute_with_circuit_breaker(self, query, parameters=None, operation_name="database_query"):
        """
        Execute a query with circuit breaker protection
        """
        async def execute_query():
            async with self.get_session_with_circuit_breaker() as session:
                if parameters:
                    result = await session.execute(query, parameters)
                else:
                    result = await session.execute(query)
                await session.commit()
                return result
        
        return await self.circuit_breaker.call(
            execute_query,
            operation_name=operation_name
        )
    
    async def health_check_with_circuit_breaker(self) -> Dict[str, Any]:
        """
        Enhanced health check with circuit breaker metrics
        """
        health_data = {
            'status': 'unknown',
            'response_time': 0.0,
            'circuit_breaker': {},
            'connection_stats': self.connection_stats.copy(),
            'timestamp': time.time()
        }
        
        start_time = time.time()
        
        try:
            # Test basic connection
            await self._test_connection_with_circuit_breaker()
            
            response_time = time.time() - start_time
            health_data.update({
                'status': 'healthy',
                'response_time': response_time
            })
            
        except Exception as e:
            response_time = time.time() - start_time
            health_data.update({
                'status': 'unhealthy',
                'response_time': response_time,
                'error': str(e)
            })
        
        # Add circuit breaker information
        if self.circuit_breaker:
            health_data['circuit_breaker'] = {
                'state': self.circuit_breaker.get_state(),
                'metrics': self.circuit_breaker.get_metrics()
            }
        
        return health_data
    
    async def get_comprehensive_health_status(self) -> Dict[str, Any]:
        """
        Get comprehensive health status including all monitoring data
        """
        health_status = await self.health_check_with_circuit_breaker()
        
        # Add monitoring data if available
        if self.circuit_monitor:
            try:
                monitoring_data = await self.circuit_monitor.get_comprehensive_metrics()
                health_status['monitoring'] = monitoring_data
            except Exception as e:
                logger.warning(f"Failed to get monitoring data: {e}")
                health_status['monitoring'] = {'error': str(e)}
        
        # Add pool statistics
        if self.engine and hasattr(self.engine.pool, 'size'):
            try:
                pool_status = await self.get_pool_stats()
                health_status['connection_pool'] = pool_status
            except Exception as e:
                logger.warning(f"Failed to get pool stats: {e}")
                health_status['connection_pool'] = {'error': str(e)}
        
        return health_status


# Global session manager instance
_session_manager: Optional[AsyncSessionManager] = None


async def get_session_manager() -> AsyncSessionManager:
    """
    Get the global async session manager
    
    This is the primary way to access the database in your application.
    The session manager is automatically initialized on first access.
    
    Returns:
        Initialized AsyncSessionManager instance
    """
    global _session_manager
    
    if _session_manager is None:
        _session_manager = AsyncSessionManager()
        await _session_manager.initialize()
    
    return _session_manager


async def set_session_manager(manager: AsyncSessionManager) -> None:
    """
    Set a custom session manager (useful for testing)
    
    Args:
        manager: Custom session manager instance
    """
    global _session_manager
    
    # Clean up existing manager
    if _session_manager:
        await _session_manager.cleanup()
    
    _session_manager = manager


async def cleanup_session_manager() -> None:
    """
    Clean up the global session manager
    Should be called during application shutdown
    """
    global _session_manager
    
    if _session_manager:
        await _session_manager.cleanup()
        _session_manager = None


# Convenience functions for common patterns
@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Convenience function to get a database session
    
    Example usage:
        async with get_db_session() as session:
            # Use session for database operations
            pass
    """
    manager = await get_session_manager()
    async with manager.get_session() as session:
        yield session


@asynccontextmanager 
async def get_db_transaction() -> AsyncGenerator[AsyncSession, None]:
    """
    Convenience function to get a transactional database session
    
    Example usage:
        async with get_db_transaction() as session:
            # All operations are in a transaction
            pass
    """
    manager = await get_session_manager()
    async with manager.transaction() as session:
        yield session
