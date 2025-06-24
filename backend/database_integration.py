"""
Server Integration Module for PostgreSQL Circuit Breaker
Integrates the PostgreSQL circuit breaker with the existing Hokm game server
"""

import asyncio
import logging
from typing import Optional, Dict, Any
from datetime import datetime

from .database.database_wrapper import DatabaseWrapper
from .database.postgresql_circuit_breaker import CircuitBreakerConfig
from .database.models import Player, GameSession, GameMove, PlayerStats

logger = logging.getLogger(__name__)

class DatabaseIntegratedGameServer:
    """
    Enhanced GameServer with PostgreSQL circuit breaker integration
    Extends the existing server with database capabilities while maintaining Redis compatibility
    """
    
    def __init__(self, original_server):
        """
        Initialize database integration
        
        Args:
            original_server: The existing GameServer instance
        """
        self.server = original_server
        self.db_wrapper: Optional[DatabaseWrapper] = None
        self.database_enabled = False
        
        # Integration settings
        self.dual_storage_mode = True  # Use both Redis and PostgreSQL
        self.fallback_to_redis = True  # Fall back to Redis if DB fails
        
        logger.info("Database integrated server initialized")
    
    async def initialize_database(self):
        """Initialize the database wrapper with circuit breaker protection"""
        try:
            logger.info("Initializing PostgreSQL database with circuit breaker protection")
            
            # Create database wrapper with Redis manager integration
            self.db_wrapper = DatabaseWrapper(
                session_manager=None,  # Will be auto-created
                redis_manager=self.server.redis_manager
            )
            
            # Initialize the wrapper
            await self.db_wrapper.initialize()
            
            # Test database connectivity
            health = await self.db_wrapper.health_check()
            if health['database_wrapper']['status'] == 'healthy':
                self.database_enabled = True
                logger.info("✅ PostgreSQL circuit breaker initialized successfully")
                logger.info(f"Database health: {health['database_wrapper']['status']}")
            else:
                logger.warning("⚠️ Database not healthy, operating in Redis-only mode")
                logger.warning(f"Database status: {health}")
                
        except Exception as e:
            logger.error(f"❌ Failed to initialize database: {e}")
            logger.warning("Operating in Redis-only mode")
            self.database_enabled = False
    
    async def handle_player_join_with_database(self, websocket, data):
        """Enhanced player join with database integration"""
        username = data['username']
        room_code = data['room_code']
        
        # First handle the Redis-based join (existing functionality)
        redis_result = await self.server.handle_join(websocket, data)
        
        # If Redis join was successful and database is available, store in database
        if redis_result and self.database_enabled:
            try:
                await self._store_player_join_in_database(username, room_code, data)
            except Exception as e:
                logger.warning(f"Failed to store player join in database: {e}")
                # Continue with Redis-only operation
        
        return redis_result
    
    async def _store_player_join_in_database(self, username: str, room_code: str, join_data: dict):
        """Store player join event in database with circuit breaker protection"""
        try:
            # Create or update player record
            player_data = {
                'username': username,
                'email': join_data.get('email'),
                'last_seen': datetime.utcnow(),
                'total_games': 1,  # Will be updated if player exists
                'current_room': room_code
            }
            
            # Use circuit breaker protected operation
            player = await self.db_wrapper.create_or_update_record(
                Player,
                {'username': username},  # Filter criteria
                player_data,
                operation_name="player_join"
            )
            
            logger.debug(f"Player {username} stored/updated in database")
            
            # Create game session if not exists
            session_data = {
                'room_id': room_code,
                'created_at': datetime.utcnow(),
                'status': 'active',
                'player_count': len(self.server.redis_manager.get_room_players(room_code))
            }
            
            await self.db_wrapper.create_record(
                GameSession,
                session_data,
                operation_name="game_session_create"
            )
            
        except Exception as e:
            logger.error(f"Database storage failed for player join: {e}")
            raise
    
    async def handle_game_move_with_database(self, room_code: str, player: str, move_data: dict):
        """Store game move in both Redis and PostgreSQL with circuit breaker protection"""
        
        # Always store in Redis first (primary for real-time)
        await self.server.redis_manager.store_move(room_code, player, move_data)
        
        # Try to store in PostgreSQL (secondary for persistence)
        if self.database_enabled:
            try:
                move_record = await self.db_wrapper.create_record(
                    GameMove,
                    {
                        'room_id': room_code,
                        'player_username': player,
                        'move_data': move_data,
                        'timestamp': datetime.utcnow()
                    },
                    operation_name="store_game_move"
                )
                
                logger.debug(f"Game move stored in database: {move_record}")
                
            except Exception as e:
                logger.warning(f"Failed to store move in database: {e}")
                # Game continues with Redis-only storage
    
    async def get_player_stats_with_fallback(self, username: str) -> dict:
        """Get player stats with database circuit breaker and Redis cache fallback"""
        
        # Try Redis cache first (fastest)
        try:
            cached_stats = await self.server.redis_manager.get_player_stats(username)
            if cached_stats:
                return cached_stats
        except Exception as e:
            logger.debug(f"Redis cache miss for player stats: {e}")
        
        # Try database with circuit breaker protection
        if self.database_enabled:
            try:
                player = await self.db_wrapper.get_by_field(
                    Player,
                    'username',
                    username,
                    operation_name="get_player_stats"
                )
                
                if player:
                    stats = {
                        'username': player.username,
                        'total_games': player.total_games,
                        'wins': player.wins,
                        'losses': player.losses,
                        'rating': player.rating,
                        'last_seen': player.last_seen.isoformat() if player.last_seen else None
                    }
                    
                    # Cache in Redis for future requests
                    await self.server.redis_manager.cache_player_stats(username, stats, ttl=300)
                    return stats
                    
            except Exception as e:
                logger.warning(f"Database lookup failed for {username}: {e}")
        
        # Return minimal stats if both fail
        return {
            'username': username,
            'total_games': 0,
            'wins': 0,
            'losses': 0,
            'rating': 1000,
            'last_seen': None
        }
    
    async def background_sync_to_database(self):
        """Background task to sync Redis data to PostgreSQL"""
        
        if not self.database_enabled:
            return
        
        while True:
            try:
                # Get active games from Redis
                active_games = await self.server.redis_manager.get_all_active_games()
                
                for room_code, game_data in active_games.items():
                    try:
                        # Sync to database with circuit breaker protection
                        await self._sync_game_to_database(room_code, game_data)
                        
                    except Exception as e:
                        logger.warning(f"Failed to sync game {room_code}: {e}")
                        # Continue with other games
                
                # Wait before next sync
                await asyncio.sleep(60)  # Sync every minute
                
            except Exception as e:
                logger.error(f"Background sync error: {e}")
                await asyncio.sleep(300)  # Wait 5 minutes on error
    
    async def _sync_game_to_database(self, room_code: str, game_data: dict):
        """Sync individual game to database"""
        
        try:
            # Use transaction for consistency
            async with self.db_wrapper.transaction("game_sync") as session:
                # Create or update game session
                game_session = await self.db_wrapper.create_or_update_record(
                    GameSession,
                    {'room_id': room_code},
                    {
                        'room_id': room_code,
                        'game_data': game_data,
                        'last_sync': datetime.utcnow(),
                        'status': game_data.get('phase', 'unknown')
                    },
                    operation_name="sync_game_session"
                )
                
                logger.debug(f"Synced game {room_code} to database")
        
        except Exception as e:
            logger.warning(f"Failed to sync game {room_code}: {e}")
            raise
    
    async def get_comprehensive_health_status(self) -> dict:
        """Get comprehensive server health including database circuit breaker status"""
        
        health_status = {
            'timestamp': datetime.utcnow().isoformat(),
            'server': 'healthy',
            'components': {}
        }
        
        # Check Redis health (existing)
        try:
            redis_health = await self.server.redis_manager.health_check()
            health_status['components']['redis'] = redis_health
        except Exception as e:
            health_status['components']['redis'] = {'status': 'unhealthy', 'error': str(e)}
            health_status['server'] = 'degraded'
        
        # Check PostgreSQL health with circuit breaker status
        if self.database_enabled and self.db_wrapper:
            try:
                db_health = await self.db_wrapper.health_check()
                health_status['components']['postgresql'] = db_health
                
                # Check if any circuit breakers are open
                cb_status = db_health.get('circuit_breakers', {})
                open_circuits = [name for name, cb in cb_status.items() 
                               if cb.get('state', {}).get('state') == 'open']
                
                if open_circuits:
                    health_status['server'] = 'degraded'
                    health_status['warnings'] = f"Circuit breakers open: {open_circuits}"
            
            except Exception as e:
                health_status['components']['postgresql'] = {'status': 'unhealthy', 'error': str(e)}
                health_status['server'] = 'degraded'
        else:
            health_status['components']['postgresql'] = {'status': 'disabled', 'reason': 'Database not initialized'}
        
        return health_status
    
    async def handle_database_outage(self):
        """Handle database outage gracefully"""
        
        logger.warning("Database outage detected, switching to Redis-only mode")
        
        # Update server mode
        self.database_enabled = False
        
        # Notify active players (optional)
        message = {
            'type': 'server_notice',
            'message': 'Server running in limited mode, some features unavailable'
        }
        
        for connection in self.server.network_manager.connections.values():
            try:
                await connection.send(json.dumps(message))
            except:
                pass  # Ignore send failures
        
        # Set up recovery monitoring
        asyncio.create_task(self._monitor_database_recovery())
    
    async def _monitor_database_recovery(self):
        """Monitor for database recovery"""
        
        while not self.database_enabled:
            try:
                # Test database connectivity
                if self.db_wrapper:
                    health = await self.db_wrapper.health_check()
                    
                    if health['database_wrapper']['status'] == 'healthy':
                        logger.info("Database recovered, resuming normal operation")
                        self.database_enabled = True
                        
                        # Notify players
                        message = {
                            'type': 'server_notice', 
                            'message': 'Server fully operational'
                        }
                        
                        for connection in self.server.network_manager.connections.values():
                            try:
                                await connection.send(json.dumps(message))
                            except:
                                pass
                        break
            
            except Exception as e:
                logger.debug(f"Database still unavailable: {e}")
            
            await asyncio.sleep(30)  # Check every 30 seconds
    
    async def cleanup(self):
        """Cleanup database connections and resources"""
        if self.db_wrapper:
            await self.db_wrapper.cleanup()
        logger.info("Database integration cleaned up")
