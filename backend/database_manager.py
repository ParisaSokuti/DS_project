"""
PostgreSQL Database Manager for Hokm Game Server
Provides high-level database operations with connection pooling and error handling
"""
import asyncio
import logging
import json
import uuid
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

import asyncpg
import aioredis
from asyncpg.pool import Pool
from asyncpg.connection import Connection

from .circuit_breaker import CircuitBreaker


class DatabaseManager:
    """
    Manages PostgreSQL connections and provides high-level database operations
    for the Hokm game server with connection pooling, circuit breaker pattern,
    and Redis integration.
    """
    
    def __init__(self, 
                 primary_dsn: str,
                 replica_dsn: Optional[str] = None,
                 redis_url: Optional[str] = None,
                 min_connections: int = 10,
                 max_connections: int = 50,
                 max_inactive_connection_lifetime: float = 300.0):
        """
        Initialize the database manager.
        
        Args:
            primary_dsn: Primary database connection string
            replica_dsn: Read replica connection string (optional)
            redis_url: Redis connection string (optional)
            min_connections: Minimum connections in pool
            max_connections: Maximum connections in pool
            max_inactive_connection_lifetime: Max lifetime for inactive connections
        """
        self.primary_dsn = primary_dsn
        self.replica_dsn = replica_dsn
        self.redis_url = redis_url
        
        self.min_connections = min_connections
        self.max_connections = max_connections
        self.max_inactive_connection_lifetime = max_inactive_connection_lifetime
        
        self.primary_pool: Optional[Pool] = None
        self.replica_pool: Optional[Pool] = None
        self.redis_client: Optional[aioredis.Redis] = None
        
        self.logger = logging.getLogger(__name__)
        
        # Circuit breakers for resilience
        self.primary_circuit_breaker = CircuitBreaker(
            failure_threshold=5,
            recovery_timeout=60,
            expected_exception=Exception
        )
        
        self.replica_circuit_breaker = CircuitBreaker(
            failure_threshold=3,
            recovery_timeout=30,
            expected_exception=Exception
        )
        
        self._connection_lock = asyncio.Lock()
        self._health_check_task: Optional[asyncio.Task] = None
        
    async def initialize(self):
        """Initialize database connections and Redis client."""
        try:
            # Initialize primary database pool
            self.primary_pool = await asyncpg.create_pool(
                self.primary_dsn,
                min_size=self.min_connections,
                max_size=self.max_connections,
                max_inactive_connection_lifetime=self.max_inactive_connection_lifetime,
                command_timeout=30,
                server_settings={
                    'application_name': 'hokm_game_server',
                    'search_path': 'hokm_game,public'
                }
            )
            
            # Initialize replica pool if provided
            if self.replica_dsn:
                self.replica_pool = await asyncpg.create_pool(
                    self.replica_dsn,
                    min_size=max(2, self.min_connections // 2),
                    max_size=max(10, self.max_connections // 2),
                    max_inactive_connection_lifetime=self.max_inactive_connection_lifetime,
                    command_timeout=30,
                    server_settings={
                        'application_name': 'hokm_game_server_replica',
                        'search_path': 'hokm_game,public'
                    }
                )
            
            # Initialize Redis client if provided
            if self.redis_url:
                self.redis_client = await aioredis.from_url(
                    self.redis_url,
                    encoding='utf-8',
                    decode_responses=True,
                    socket_timeout=5,
                    socket_connect_timeout=5,
                    retry_on_timeout=True,
                    max_connections=20
                )
            
            # Start health check task
            self._health_check_task = asyncio.create_task(self._health_check_loop())
            
            self.logger.info("Database manager initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize database manager: {e}")
            raise
    
    async def close(self):
        """Close all database connections and Redis client."""
        try:
            # Cancel health check task
            if self._health_check_task:
                self._health_check_task.cancel()
                try:
                    await self._health_check_task
                except asyncio.CancelledError:
                    pass
            
            # Close database pools
            if self.primary_pool:
                await self.primary_pool.close()
                
            if self.replica_pool:
                await self.replica_pool.close()
                
            # Close Redis client
            if self.redis_client:
                await self.redis_client.close()
                
            self.logger.info("Database manager closed successfully")
            
        except Exception as e:
            self.logger.error(f"Error closing database manager: {e}")
    
    @asynccontextmanager
    async def get_connection(self, use_replica: bool = False):
        """
        Get a database connection from the pool.
        
        Args:
            use_replica: Whether to use read replica (if available)
            
        Yields:
            Database connection
        """
        pool = None
        circuit_breaker = None
        
        try:
            if use_replica and self.replica_pool:
                pool = self.replica_pool
                circuit_breaker = self.replica_circuit_breaker
            else:
                pool = self.primary_pool
                circuit_breaker = self.primary_circuit_breaker
            
            if not pool:
                raise RuntimeError("Database pool not initialized")
            
            async with circuit_breaker:
                async with pool.acquire() as connection:
                    yield connection
                    
        except Exception as e:
            self.logger.error(f"Error getting database connection: {e}")
            raise
    
    async def execute_query(self, query: str, *args, use_replica: bool = False) -> List[Dict]:
        """
        Execute a SELECT query and return results.
        
        Args:
            query: SQL query string
            *args: Query parameters
            use_replica: Whether to use read replica
            
        Returns:
            List of query results as dictionaries
        """
        try:
            async with self.get_connection(use_replica=use_replica) as conn:
                result = await conn.fetch(query, *args)
                return [dict(row) for row in result]
                
        except Exception as e:
            self.logger.error(f"Error executing query: {e}")
            raise
    
    async def execute_command(self, command: str, *args) -> str:
        """
        Execute a command (INSERT, UPDATE, DELETE) and return status.
        
        Args:
            command: SQL command string
            *args: Command parameters
            
        Returns:
            Command status string
        """
        try:
            async with self.get_connection() as conn:
                result = await conn.execute(command, *args)
                return result
                
        except Exception as e:
            self.logger.error(f"Error executing command: {e}")
            raise
    
    async def execute_in_transaction(self, operations: List[Tuple[str, tuple]]) -> List[Any]:
        """
        Execute multiple operations in a single transaction.
        
        Args:
            operations: List of (query/command, args) tuples
            
        Returns:
            List of operation results
        """
        try:
            async with self.get_connection() as conn:
                async with conn.transaction():
                    results = []
                    for query, args in operations:
                        if query.strip().upper().startswith('SELECT'):
                            result = await conn.fetch(query, *args)
                            results.append([dict(row) for row in result])
                        else:
                            result = await conn.execute(query, *args)
                            results.append(result)
                    return results
                    
        except Exception as e:
            self.logger.error(f"Error executing transaction: {e}")
            raise
    
    # Game-specific database operations
    
    async def create_player(self, username: str, email: Optional[str] = None, 
                          password_hash: Optional[str] = None) -> Dict:
        """Create a new player."""
        try:
            query = """
                INSERT INTO players (username, email, password_hash)
                VALUES ($1, $2, $3)
                RETURNING id, username, email, created_at, rating
            """
            result = await self.execute_query(query, username, email, password_hash)
            return result[0] if result else None
            
        except Exception as e:
            self.logger.error(f"Error creating player: {e}")
            raise
    
    async def get_player(self, player_id: Optional[str] = None, 
                        username: Optional[str] = None) -> Optional[Dict]:
        """Get player by ID or username."""
        try:
            if player_id:
                query = "SELECT * FROM players WHERE id = $1 AND is_active = true"
                result = await self.execute_query(query, uuid.UUID(player_id), use_replica=True)
            elif username:
                query = "SELECT * FROM players WHERE username = $1 AND is_active = true"
                result = await self.execute_query(query, username, use_replica=True)
            else:
                raise ValueError("Either player_id or username must be provided")
            
            return result[0] if result else None
            
        except Exception as e:
            self.logger.error(f"Error getting player: {e}")
            raise
    
    async def create_game_session(self, room_id: str, session_key: str, 
                                max_players: int = 4) -> Dict:
        """Create a new game session."""
        try:
            query = """
                INSERT INTO game_sessions (room_id, session_key, max_players)
                VALUES ($1, $2, $3)
                RETURNING id, room_id, session_key, status, created_at
            """
            result = await self.execute_query(query, room_id, session_key, max_players)
            return result[0] if result else None
            
        except Exception as e:
            self.logger.error(f"Error creating game session: {e}")
            raise
    
    async def get_game_session(self, room_id: Optional[str] = None, 
                             session_id: Optional[str] = None) -> Optional[Dict]:
        """Get game session by room ID or session ID."""
        try:
            if room_id:
                query = "SELECT * FROM game_sessions WHERE room_id = $1"
                result = await self.execute_query(query, room_id, use_replica=True)
            elif session_id:
                query = "SELECT * FROM game_sessions WHERE id = $1"
                result = await self.execute_query(query, uuid.UUID(session_id), use_replica=True)
            else:
                raise ValueError("Either room_id or session_id must be provided")
            
            return result[0] if result else None
            
        except Exception as e:
            self.logger.error(f"Error getting game session: {e}")
            raise
    
    async def add_player_to_game(self, game_session_id: str, player_id: str, 
                               position: int, team: int) -> bool:
        """Add a player to a game session."""
        try:
            operations = [
                ("""
                    INSERT INTO game_participants 
                    (game_session_id, player_id, position, team)
                    VALUES ($1, $2, $3, $4)
                """, (uuid.UUID(game_session_id), uuid.UUID(player_id), position, team)),
                ("""
                    UPDATE game_sessions 
                    SET current_players = current_players + 1
                    WHERE id = $1
                """, (uuid.UUID(game_session_id),))
            ]
            
            await self.execute_in_transaction(operations)
            return True
            
        except Exception as e:
            self.logger.error(f"Error adding player to game: {e}")
            return False
    
    async def update_game_state(self, game_session_id: str, game_state: Dict,
                              player_hands: Optional[Dict] = None,
                              scores: Optional[Dict] = None) -> bool:
        """Update game state using the stored function."""
        try:
            query = """
                SELECT update_game_state($1, $2, $3, $4)
            """
            result = await self.execute_query(
                query,
                uuid.UUID(game_session_id),
                json.dumps(game_state),
                json.dumps(player_hands) if player_hands else None,
                json.dumps(scores) if scores else None
            )
            return result[0]['update_game_state'] if result else False
            
        except Exception as e:
            self.logger.error(f"Error updating game state: {e}")
            return False
    
    async def record_game_move(self, game_session_id: str, player_id: str,
                             move_type: str, move_data: Dict,
                             round_number: int, trick_number: Optional[int] = None) -> Optional[str]:
        """Record a game move."""
        try:
            query = """
                SELECT record_game_move($1, $2, $3, $4, $5, $6)
            """
            result = await self.execute_query(
                query,
                uuid.UUID(game_session_id),
                uuid.UUID(player_id),
                move_type,
                json.dumps(move_data),
                round_number,
                trick_number
            )
            return str(result[0]['record_game_move']) if result else None
            
        except Exception as e:
            self.logger.error(f"Error recording game move: {e}")
            return None
    
    async def handle_player_reconnection(self, player_id: str, game_session_id: str,
                                       connection_id: str) -> Optional[Dict]:
        """Handle player reconnection using stored function."""
        try:
            query = """
                SELECT handle_player_reconnection($1, $2, $3)
            """
            result = await self.execute_query(
                query,
                uuid.UUID(player_id),
                uuid.UUID(game_session_id),
                connection_id
            )
            
            if result:
                return json.loads(result[0]['handle_player_reconnection'])
            return None
            
        except Exception as e:
            self.logger.error(f"Error handling player reconnection: {e}")
            return None
    
    async def get_active_games_stats(self) -> Dict:
        """Get active games statistics."""
        try:
            query = "SELECT * FROM get_active_game_stats()"
            result = await self.execute_query(query, use_replica=True)
            return result[0] if result else {}
            
        except Exception as e:
            self.logger.error(f"Error getting active games stats: {e}")
            return {}
    
    async def cleanup_old_connections(self) -> int:
        """Clean up old WebSocket connections."""
        try:
            query = "SELECT cleanup_old_connections()"
            result = await self.execute_query(query)
            return result[0]['cleanup_old_connections'] if result else 0
            
        except Exception as e:
            self.logger.error(f"Error cleaning up connections: {e}")
            return 0
    
    async def log_user_action(self, player_id: str, action_type: str,
                            action_data: Dict, ip_address: Optional[str] = None,
                            user_agent: Optional[str] = None) -> Optional[str]:
        """Log user action for audit purposes."""
        try:
            query = """
                SELECT audit.log_user_action($1, $2, $3, $4, $5)
            """
            result = await self.execute_query(
                query,
                uuid.UUID(player_id),
                action_type,
                json.dumps(action_data),
                ip_address,
                user_agent
            )
            return str(result[0]['log_user_action']) if result else None
            
        except Exception as e:
            self.logger.error(f"Error logging user action: {e}")
            return None
    
    # Cache operations with Redis
    
    async def cache_get(self, key: str) -> Optional[str]:
        """Get value from Redis cache."""
        if not self.redis_client:
            return None
        
        try:
            return await self.redis_client.get(key)
        except Exception as e:
            self.logger.error(f"Error getting from cache: {e}")
            return None
    
    async def cache_set(self, key: str, value: str, ttl: int = 3600) -> bool:
        """Set value in Redis cache."""
        if not self.redis_client:
            return False
        
        try:
            await self.redis_client.setex(key, ttl, value)
            return True
        except Exception as e:
            self.logger.error(f"Error setting cache: {e}")
            return False
    
    async def cache_delete(self, key: str) -> bool:
        """Delete value from Redis cache."""
        if not self.redis_client:
            return False
        
        try:
            await self.redis_client.delete(key)
            return True
        except Exception as e:
            self.logger.error(f"Error deleting from cache: {e}")
            return False
    
    # Health check and monitoring
    
    async def _health_check_loop(self):
        """Background task for health checks and maintenance."""
        while True:
            try:
                await asyncio.sleep(300)  # Check every 5 minutes
                
                # Check database health
                await self._check_database_health()
                
                # Clean up old connections
                cleaned = await self.cleanup_old_connections()
                if cleaned > 0:
                    self.logger.info(f"Cleaned up {cleaned} old connections")
                
                # Update circuit breaker metrics
                await self._update_circuit_breaker_metrics()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in health check loop: {e}")
    
    async def _check_database_health(self):
        """Check database connectivity and performance."""
        try:
            # Check primary database
            async with self.get_connection() as conn:
                await conn.fetchval("SELECT 1")
            
            # Check replica database if available
            if self.replica_pool:
                async with self.get_connection(use_replica=True) as conn:
                    await conn.fetchval("SELECT 1")
            
            # Check Redis if available
            if self.redis_client:
                await self.redis_client.ping()
                
        except Exception as e:
            self.logger.error(f"Database health check failed: {e}")
            raise
    
    async def _update_circuit_breaker_metrics(self):
        """Update circuit breaker metrics."""
        try:
            # Insert metrics into performance_metrics table
            operations = [
                ("""
                    INSERT INTO performance_metrics (metric_type, metric_name, metric_value, metadata)
                    VALUES ('circuit_breaker', 'primary_state', $1, $2)
                """, (
                    1 if self.primary_circuit_breaker.state == 'closed' else 0,
                    json.dumps({
                        'state': self.primary_circuit_breaker.state,
                        'failure_count': self.primary_circuit_breaker.failure_count,
                        'last_failure_time': self.primary_circuit_breaker.last_failure_time.isoformat() if self.primary_circuit_breaker.last_failure_time else None
                    })
                )),
                ("""
                    INSERT INTO performance_metrics (metric_type, metric_name, metric_value, metadata)
                    VALUES ('circuit_breaker', 'replica_state', $1, $2)
                """, (
                    1 if self.replica_circuit_breaker.state == 'closed' else 0,
                    json.dumps({
                        'state': self.replica_circuit_breaker.state,
                        'failure_count': self.replica_circuit_breaker.failure_count,
                        'last_failure_time': self.replica_circuit_breaker.last_failure_time.isoformat() if self.replica_circuit_breaker.last_failure_time else None
                    })
                ))
            ]
            
            await self.execute_in_transaction(operations)
            
        except Exception as e:
            self.logger.error(f"Error updating circuit breaker metrics: {e}")
    
    async def get_health_status(self) -> Dict:
        """Get overall health status of the database manager."""
        try:
            health_status = {
                'database_primary': 'unknown',
                'database_replica': 'unknown',
                'redis': 'unknown',
                'circuit_breaker_primary': self.primary_circuit_breaker.state,
                'circuit_breaker_replica': self.replica_circuit_breaker.state,
                'timestamp': datetime.utcnow().isoformat()
            }
            
            # Check primary database
            try:
                async with self.get_connection() as conn:
                    await conn.fetchval("SELECT 1")
                health_status['database_primary'] = 'healthy'
            except Exception:
                health_status['database_primary'] = 'unhealthy'
            
            # Check replica database
            if self.replica_pool:
                try:
                    async with self.get_connection(use_replica=True) as conn:
                        await conn.fetchval("SELECT 1")
                    health_status['database_replica'] = 'healthy'
                except Exception:
                    health_status['database_replica'] = 'unhealthy'
            else:
                health_status['database_replica'] = 'not_configured'
            
            # Check Redis
            if self.redis_client:
                try:
                    await self.redis_client.ping()
                    health_status['redis'] = 'healthy'
                except Exception:
                    health_status['redis'] = 'unhealthy'
            else:
                health_status['redis'] = 'not_configured'
            
            return health_status
            
        except Exception as e:
            self.logger.error(f"Error getting health status: {e}")
            return {'error': str(e), 'timestamp': datetime.utcnow().isoformat()}
