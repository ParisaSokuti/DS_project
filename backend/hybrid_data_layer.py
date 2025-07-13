"""
Hybrid Data Layer for Hokm Game Server
Implements Redis + PostgreSQL hybrid architecture with intelligent data routing,
synchronization, and error handling for optimal game performance.
"""

import asyncio
import json
import time
import logging
from typing import Dict, List, Any, Optional, Tuple, Union
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum
import uuid
from contextlib import asynccontextmanager

# Database imports
import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select, insert, update, delete
from sqlalchemy.orm import selectinload

# Circuit breaker imports
from backend.circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from backend.database.postgresql_circuit_breaker import PostgreSQLCircuitBreaker, PostgreSQLCircuitBreakerConfig
from backend.database.circuit_breaker_integration import CircuitBreakerIntegratedSessionManager

logger = logging.getLogger(__name__)

class DataLayer(Enum):
    """Data layer enumeration"""
    REDIS = "redis"
    POSTGRESQL = "postgresql"
    HYBRID = "hybrid"

class DataOperation(Enum):
    """Data operation types"""
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    UPDATE = "update"

@dataclass
class HybridDataConfig:
    """Configuration for hybrid data layer"""
    redis_url: str = "redis://localhost:6379"
    redis_prefix: str = "hokm:"
    redis_default_ttl: int = 3600  # 1 hour
    
    # Synchronization settings
    sync_enabled: bool = True
    sync_batch_size: int = 100
    sync_interval: float = 30.0  # seconds
    sync_retry_attempts: int = 3
    
    # Performance settings
    cache_enabled: bool = True
    cache_hit_logging: bool = False
    performance_logging: bool = True
    
    # Error handling
    redis_circuit_breaker_enabled: bool = True
    postgresql_circuit_breaker_enabled: bool = True
    fallback_enabled: bool = True

class HybridDataLayer:
    """
    Hybrid data layer that intelligently routes data between Redis and PostgreSQL
    based on access patterns, data characteristics, and performance requirements.
    """
    
    def __init__(
        self,
        redis_manager,
        session_manager: CircuitBreakerIntegratedSessionManager,
        config: HybridDataConfig = None
    ):
        self.redis_manager = redis_manager
        self.session_manager = session_manager
        self.config = config or HybridDataConfig()
        
        # Circuit breakers
        self.redis_circuit_breaker = None
        self.postgresql_circuit_breaker = None
        
        # Synchronization
        self.sync_queue = asyncio.Queue()
        self.sync_task = None
        self.sync_running = False
        
        # Performance tracking
        self.performance_metrics = {
            'redis_operations': 0,
            'postgresql_operations': 0,
            'hybrid_operations': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'sync_operations': 0,
            'sync_failures': 0
        }
        
        # Data routing rules
        self.routing_rules = self._initialize_routing_rules()
        
        logger.info("Hybrid Data Layer initialized")
    
    async def initialize(self):
        """Initialize the hybrid data layer"""
        # Initialize circuit breakers
        if self.config.redis_circuit_breaker_enabled:
            redis_config = CircuitBreakerConfig(
                failure_threshold=5,
                timeout=30.0,
                time_window=300.0
            )
            self.redis_circuit_breaker = CircuitBreaker("redis_hybrid", redis_config)
        
        if self.config.postgresql_circuit_breaker_enabled:
            pg_config = PostgreSQLCircuitBreakerConfig(
                failure_threshold=3,
                timeout=60.0,
                max_retry_attempts=2
            )
            self.postgresql_circuit_breaker = PostgreSQLCircuitBreaker("postgresql_hybrid", pg_config)
        
        # Start synchronization task
        if self.config.sync_enabled:
            await self.start_synchronization()
        
        logger.info("Hybrid Data Layer fully initialized")
    
    def _initialize_routing_rules(self) -> Dict[str, Dict[str, Any]]:
        """Initialize data routing rules"""
        return {
            # Game state data - Redis primary
            'game_sessions': {
                'primary': DataLayer.REDIS,
                'secondary': DataLayer.POSTGRESQL,
                'ttl': 14400,  # 4 hours
                'sync_immediately': False,
                'sync_on_complete': True
            },
            'game_state': {
                'primary': DataLayer.REDIS,
                'secondary': DataLayer.POSTGRESQL,
                'ttl': 7200,  # 2 hours
                'sync_immediately': False,
                'sync_interval': 60  # 1 minute
            },
            'player_hands': {
                'primary': DataLayer.REDIS,
                'secondary': None,  # Never persist card hands
                'ttl': 7200,
                'encrypted': True
            },
            'game_moves': {
                'primary': DataLayer.REDIS,
                'secondary': DataLayer.POSTGRESQL,
                'ttl': 3600,  # 1 hour
                'sync_immediately': True  # Important for game integrity
            },
            
            # Player session data - Redis primary
            'player_sessions': {
                'primary': DataLayer.REDIS,
                'secondary': None,
                'ttl': 1800,  # 30 minutes
                'extend_on_activity': True
            },
            'websocket_connections': {
                'primary': DataLayer.REDIS,
                'secondary': None,
                'ttl': 1800
            },
            
            # Player data - PostgreSQL primary
            'players': {
                'primary': DataLayer.POSTGRESQL,
                'secondary': DataLayer.REDIS,
                'cache_ttl': 900,  # 15 minutes
                'cache_on_read': True
            },
            'player_statistics': {
                'primary': DataLayer.POSTGRESQL,
                'secondary': DataLayer.REDIS,
                'cache_ttl': 1800,  # 30 minutes
                'batch_updates': True
            },
            
            # System data - PostgreSQL primary
            'game_history': {
                'primary': DataLayer.POSTGRESQL,
                'secondary': None,
                'immutable': True
            },
            'audit_logs': {
                'primary': DataLayer.POSTGRESQL,
                'secondary': None,
                'append_only': True
            }
        }
    
    # Game State Operations
    async def create_game_session(self, room_id: str, game_data: Dict[str, Any]) -> bool:
        """Create a new game session"""
        start_time = time.time()
        
        try:
            # Store in Redis (primary)
            redis_key = f"{self.config.redis_prefix}game_session:{room_id}"
            game_data['created_at'] = datetime.utcnow().isoformat()
            game_data['last_updated'] = datetime.utcnow().isoformat()
            
            if self.redis_circuit_breaker:
                result = self.redis_circuit_breaker.call(
                    self.redis_manager.hset,
                    redis_key,
                    mapping=self._serialize_for_redis(game_data)
                )
                if not result.success:
                    raise Exception(f"Redis operation failed: {result.error}")
            else:
                await self.redis_manager.hset(redis_key, mapping=self._serialize_for_redis(game_data))
            
            # Set TTL
            rule = self.routing_rules['game_sessions']
            await self.redis_manager.expire(redis_key, rule['ttl'])
            
            # Queue for synchronization if needed
            if rule.get('sync_immediately'):
                await self._queue_sync_operation('game_sessions', 'create', room_id, game_data)
            
            self.performance_metrics['redis_operations'] += 1
            
            if self.config.performance_logging:
                logger.info(f"Created game session {room_id} in {time.time() - start_time:.3f}s")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to create game session {room_id}: {str(e)}")
            return False
    
    async def get_game_session(self, room_id: str) -> Optional[Dict[str, Any]]:
        """Get game session data"""
        start_time = time.time()
        
        try:
            # Try Redis first (primary)
            redis_key = f"{self.config.redis_prefix}game_session:{room_id}"
            
            if self.redis_circuit_breaker:
                result = self.redis_circuit_breaker.call(
                    self.redis_manager.hgetall,
                    redis_key
                )
                if result.success and result.value:
                    data = self._deserialize_from_redis(result.value)
                    self.performance_metrics['cache_hits'] += 1
                    if self.config.cache_hit_logging:
                        logger.debug(f"Cache hit for game session {room_id}")
                    return data
            else:
                data = await self.redis_manager.hgetall(redis_key)
                if data:
                    self.performance_metrics['cache_hits'] += 1
                    return self._deserialize_from_redis(data)
            
            # Fall back to PostgreSQL if enabled
            rule = self.routing_rules['game_sessions']
            if rule.get('secondary') == DataLayer.POSTGRESQL:
                return await self._get_from_postgresql('game_sessions', {'room_id': room_id})
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get game session {room_id}: {str(e)}")
            return None
        finally:
            if self.config.performance_logging:
                logger.debug(f"Got game session {room_id} in {time.time() - start_time:.3f}s")
    
    async def update_game_state(self, room_id: str, state_updates: Dict[str, Any]) -> bool:
        """Update game state with intelligent merging"""
        start_time = time.time()
        
        try:
            redis_key = f"{self.config.redis_prefix}game_state:{room_id}"
            
            # Add timestamp
            state_updates['last_updated'] = datetime.utcnow().isoformat()
            
            # Update in Redis
            if self.redis_circuit_breaker:
                result = self.redis_circuit_breaker.call(
                    self.redis_manager.hset,
                    redis_key,
                    mapping=self._serialize_for_redis(state_updates)
                )
                if not result.success:
                    raise Exception(f"Redis update failed: {result.error}")
            else:
                await self.redis_manager.hset(redis_key, mapping=self._serialize_for_redis(state_updates))
            
            # Update TTL
            rule = self.routing_rules['game_state']
            await self.redis_manager.expire(redis_key, rule['ttl'])
            
            # Queue for synchronization
            if rule.get('sync_interval'):
                await self._queue_sync_operation('game_state', 'update', room_id, state_updates)
            
            self.performance_metrics['redis_operations'] += 1
            return True
            
        except Exception as e:
            logger.error(f"Failed to update game state {room_id}: {str(e)}")
            return False
        finally:
            if self.config.performance_logging:
                logger.debug(f"Updated game state {room_id} in {time.time() - start_time:.3f}s")
    
    # Player Data Operations
    async def get_player_profile(self, player_id: str) -> Optional[Dict[str, Any]]:
        """Get player profile with intelligent caching"""
        start_time = time.time()
        
        try:
            # Check Redis cache first
            cache_key = f"{self.config.redis_prefix}player:{player_id}"
            
            if self.config.cache_enabled:
                cached_data = await self.redis_manager.hgetall(cache_key)
                if cached_data:
                    self.performance_metrics['cache_hits'] += 1
                    if self.config.cache_hit_logging:
                        logger.debug(f"Cache hit for player {player_id}")
                    return self._deserialize_from_redis(cached_data)
            
            # Get from PostgreSQL (primary)
            player_data = await self._get_from_postgresql('players', {'id': player_id})
            
            if player_data and self.config.cache_enabled:
                # Cache in Redis
                rule = self.routing_rules['players']
                await self.redis_manager.hset(cache_key, mapping=self._serialize_for_redis(player_data))
                await self.redis_manager.expire(cache_key, rule['cache_ttl'])
                
                self.performance_metrics['cache_misses'] += 1
            
            self.performance_metrics['postgresql_operations'] += 1
            return player_data
            
        except Exception as e:
            logger.error(f"Failed to get player profile {player_id}: {str(e)}")
            return None
        finally:
            if self.config.performance_logging:
                logger.debug(f"Got player profile {player_id} in {time.time() - start_time:.3f}s")
    
    async def update_player_statistics(self, player_id: str, stats_update: Dict[str, Any]) -> bool:
        """Update player statistics with batching support"""
        try:
            # For frequent updates, batch them
            rule = self.routing_rules['player_statistics']
            if rule.get('batch_updates'):
                return await self._queue_batch_update('player_statistics', player_id, stats_update)
            else:
                return await self._update_postgresql('player_statistics', {'id': player_id}, stats_update)
            
        except Exception as e:
            logger.error(f"Failed to update player statistics {player_id}: {str(e)}")
            return False
    
    # Session Management
    async def create_player_session(self, player_id: str, session_data: Dict[str, Any]) -> str:
        """Create player session in Redis"""
        try:
            session_id = str(uuid.uuid4())
            session_key = f"{self.config.redis_prefix}session:{session_id}"
            
            session_data.update({
                'player_id': player_id,
                'created_at': datetime.utcnow().isoformat(),
                'last_activity': datetime.utcnow().isoformat()
            })
            
            await self.redis_manager.hset(session_key, mapping=self._serialize_for_redis(session_data))
            
            rule = self.routing_rules['player_sessions']
            await self.redis_manager.expire(session_key, rule['ttl'])
            
            self.performance_metrics['redis_operations'] += 1
            return session_id
            
        except Exception as e:
            logger.error(f"Failed to create player session for {player_id}: {str(e)}")
            return None
    
    async def extend_session(self, session_id: str) -> bool:
        """Extend session TTL on activity"""
        try:
            session_key = f"{self.config.redis_prefix}session:{session_id}"
            
            # Update last activity
            await self.redis_manager.hset(session_key, 'last_activity', datetime.utcnow().isoformat())
            
            # Extend TTL
            rule = self.routing_rules['player_sessions']
            await self.redis_manager.expire(session_key, rule['ttl'])
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to extend session {session_id}: {str(e)}")
            return False
    
    # WebSocket Connection Management
    async def register_websocket_connection(self, connection_id: str, connection_data: Dict[str, Any]) -> bool:
        """Register WebSocket connection"""
        try:
            conn_key = f"{self.config.redis_prefix}connection:{connection_id}"
            
            connection_data.update({
                'connected_at': datetime.utcnow().isoformat(),
                'last_ping': datetime.utcnow().isoformat()
            })
            
            await self.redis_manager.hset(conn_key, mapping=self._serialize_for_redis(connection_data))
            
            rule = self.routing_rules['websocket_connections']
            await self.redis_manager.expire(conn_key, rule['ttl'])
            
            self.performance_metrics['redis_operations'] += 1
            return True
            
        except Exception as e:
            logger.error(f"Failed to register WebSocket connection {connection_id}: {str(e)}")
            return False
    
    async def get_active_connections(self, room_id: str) -> List[Dict[str, Any]]:
        """Get all active connections for a room"""
        try:
            pattern = f"{self.config.redis_prefix}connection:*"
            connections = []
            
            async for key in self.redis_manager.scan_iter(match=pattern):
                conn_data = await self.redis_manager.hgetall(key)
                if conn_data and conn_data.get('room_id') == room_id:
                    connections.append(self._deserialize_from_redis(conn_data))
            
            return connections
            
        except Exception as e:
            logger.error(f"Failed to get active connections for room {room_id}: {str(e)}")
            return []
    
    # Synchronization Methods
    async def start_synchronization(self):
        """Start the synchronization background task"""
        if self.sync_running:
            return
        
        self.sync_running = True
        self.sync_task = asyncio.create_task(self._synchronization_loop())
        logger.info("Data synchronization started")
    
    async def stop_synchronization(self):
        """Stop the synchronization background task"""
        if not self.sync_running:
            return
        
        self.sync_running = False
        if self.sync_task:
            self.sync_task.cancel()
            try:
                await self.sync_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Data synchronization stopped")
    
    async def _synchronization_loop(self):
        """Main synchronization loop"""
        while self.sync_running:
            try:
                await self._process_sync_queue()
                await asyncio.sleep(self.config.sync_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Synchronization error: {str(e)}")
                await asyncio.sleep(5)  # Brief pause on error
    
    async def _process_sync_queue(self):
        """Process synchronization queue"""
        operations = []
        
        # Collect batch of operations
        try:
            while len(operations) < self.config.sync_batch_size:
                operation = await asyncio.wait_for(self.sync_queue.get(), timeout=1.0)
                operations.append(operation)
        except asyncio.TimeoutError:
            pass  # No more operations, process what we have
        
        if not operations:
            return
        
        # Process operations
        for operation in operations:
            try:
                await self._execute_sync_operation(operation)
                self.performance_metrics['sync_operations'] += 1
            except Exception as e:
                logger.error(f"Sync operation failed: {str(e)}")
                self.performance_metrics['sync_failures'] += 1
                # Could implement retry logic here
    
    async def _queue_sync_operation(self, table: str, operation: str, key: str, data: Dict[str, Any]):
        """Queue a synchronization operation"""
        sync_op = {
            'table': table,
            'operation': operation,
            'key': key,
            'data': data,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        await self.sync_queue.put(sync_op)
    
    async def _execute_sync_operation(self, operation: Dict[str, Any]):
        """Execute a synchronization operation"""
        table = operation['table']
        op_type = operation['operation']
        key = operation['key']
        data = operation['data']
        
        if op_type == 'create':
            await self._create_in_postgresql(table, data)
        elif op_type == 'update':
            await self._update_postgresql(table, {'room_id': key}, data)
        elif op_type == 'delete':
            await self._delete_from_postgresql(table, {'room_id': key})
    
    # PostgreSQL Operations
    async def _get_from_postgresql(self, table: str, filters: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Get data from PostgreSQL"""
        if self.postgresql_circuit_breaker:
            result = await self.postgresql_circuit_breaker(self._pg_get_operation, table, filters)
            return result.value if result.success else None
        else:
            return await self._pg_get_operation(table, filters)
    
    async def _pg_get_operation(self, table: str, filters: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Execute PostgreSQL get operation"""
        async with self.session_manager.get_session() as session:
            # This is a simplified example - in practice, you'd use your ORM models
            where_clause = " AND ".join([f"{k} = :{k}" for k in filters.keys()])
            query = text(f"SELECT * FROM {table} WHERE {where_clause}")
            result = await session.execute(query, filters)
            row = result.fetchone()
            return dict(row) if row else None
    
    async def _create_in_postgresql(self, table: str, data: Dict[str, Any]) -> bool:
        """Create record in PostgreSQL"""
        if self.postgresql_circuit_breaker:
            result = await self.postgresql_circuit_breaker(self._pg_create_operation, table, data)
            return result.success
        else:
            return await self._pg_create_operation(table, data)
    
    async def _pg_create_operation(self, table: str, data: Dict[str, Any]) -> bool:
        """Execute PostgreSQL create operation"""
        async with self.session_manager.get_session() as session:
            columns = ", ".join(data.keys())
            placeholders = ", ".join([f":{k}" for k in data.keys()])
            query = text(f"INSERT INTO {table} ({columns}) VALUES ({placeholders})")
            await session.execute(query, data)
            await session.commit()
            return True
    
    async def _update_postgresql(self, table: str, filters: Dict[str, Any], updates: Dict[str, Any]) -> bool:
        """Update record in PostgreSQL"""
        if self.postgresql_circuit_breaker:
            result = await self.postgresql_circuit_breaker(self._pg_update_operation, table, filters, updates)
            return result.success
        else:
            return await self._pg_update_operation(table, filters, updates)
    
    async def _pg_update_operation(self, table: str, filters: Dict[str, Any], updates: Dict[str, Any]) -> bool:
        """Execute PostgreSQL update operation"""
        async with self.session_manager.get_session() as session:
            set_clause = ", ".join([f"{k} = :{k}" for k in updates.keys()])
            where_clause = " AND ".join([f"{k} = :filter_{k}" for k in filters.keys()])
            
            # Prepare parameters
            params = {**updates}
            for k, v in filters.items():
                params[f"filter_{k}"] = v
            
            query = text(f"UPDATE {table} SET {set_clause} WHERE {where_clause}")
            await session.execute(query, params)
            await session.commit()
            return True
    
    async def _delete_from_postgresql(self, table: str, filters: Dict[str, Any]) -> bool:
        """Delete record from PostgreSQL"""
        async with self.session_manager.get_session() as session:
            where_clause = " AND ".join([f"{k} = :{k}" for k in filters.keys()])
            query = text(f"DELETE FROM {table} WHERE {where_clause}")
            await session.execute(query, filters)
            await session.commit()
            return True
    
    # Utility Methods
    def _serialize_for_redis(self, data: Dict[str, Any]) -> Dict[str, str]:
        """Serialize data for Redis storage"""
        serialized = {}
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                serialized[key] = json.dumps(value)
            else:
                serialized[key] = str(value)
        return serialized
    
    def _deserialize_from_redis(self, data: Dict[str, str]) -> Dict[str, Any]:
        """Deserialize data from Redis"""
        deserialized = {}
        for key, value in data.items():
            try:
                # Try to parse as JSON first
                deserialized[key] = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                # If not JSON, keep as string
                deserialized[key] = value
        return deserialized
    
    async def _queue_batch_update(self, table: str, key: str, updates: Dict[str, Any]) -> bool:
        """Queue an update for batch processing"""
        # This would implement batching logic for performance
        # For now, just do immediate update
        return await self._update_postgresql(table, {'id': key}, updates)
    
    # Health and Monitoring
    async def get_health_status(self) -> Dict[str, Any]:
        """Get health status of the hybrid data layer"""
        status = {
            'redis_healthy': True,
            'postgresql_healthy': True,
            'synchronization_healthy': True,
            'performance_metrics': self.performance_metrics.copy()
        }
        
        # Check Redis health
        try:
            await self.redis_manager.ping()
        except Exception as e:
            status['redis_healthy'] = False
            status['redis_error'] = str(e)
        
        # Check PostgreSQL health
        try:
            async with self.session_manager.get_session() as session:
                await session.execute(text("SELECT 1"))
        except Exception as e:
            status['postgresql_healthy'] = False
            status['postgresql_error'] = str(e)
        
        # Check synchronization health
        status['sync_queue_size'] = self.sync_queue.qsize()
        status['sync_running'] = self.sync_running
        
        return status
    
    async def get_performance_metrics(self) -> Dict[str, Any]:
        """Get detailed performance metrics"""
        metrics = self.performance_metrics.copy()
        
        # Calculate derived metrics
        total_ops = metrics['redis_operations'] + metrics['postgresql_operations']
        if total_ops > 0:
            metrics['redis_percentage'] = (metrics['redis_operations'] / total_ops) * 100
            metrics['postgresql_percentage'] = (metrics['postgresql_operations'] / total_ops) * 100
        
        total_cache_ops = metrics['cache_hits'] + metrics['cache_misses']
        if total_cache_ops > 0:
            metrics['cache_hit_rate'] = (metrics['cache_hits'] / total_cache_ops) * 100
        
        if metrics['sync_operations'] > 0:
            metrics['sync_failure_rate'] = (metrics['sync_failures'] / metrics['sync_operations']) * 100
        
        return metrics
    
    async def cleanup(self):
        """Cleanup resources"""
        await self.stop_synchronization()
        
        if self.redis_circuit_breaker:
            self.redis_circuit_breaker.reset()
        
        if self.postgresql_circuit_breaker:
            await self.postgresql_circuit_breaker.reset()
        
        logger.info("Hybrid Data Layer cleaned up")

# Context manager for hybrid data operations
@asynccontextmanager
async def get_hybrid_data_layer(redis_manager, session_manager, config=None):
    """Context manager for hybrid data layer"""
    hybrid_layer = HybridDataLayer(redis_manager, session_manager, config)
    try:
        await hybrid_layer.initialize()
        yield hybrid_layer
    finally:
        await hybrid_layer.cleanup()
