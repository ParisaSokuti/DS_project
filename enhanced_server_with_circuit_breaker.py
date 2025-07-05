"""
Enhanced Hokm Game Server with PostgreSQL Circuit Breaker Integration
Extends the existing server.py with comprehensive PostgreSQL circuit breaker protection
"""

import asyncio
import sys
import websockets
import json
import uuid
import random
import time
import os
import logging
from typing import Dict, Any, Optional

# Add current directory to Python path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import existing server components
from backend.network import NetworkManager
from backend.game_board import GameBoard
from backend.game_states import GameState
from backend.redis_manager_resilient import ResilientRedisManager as RedisManager
from backend.circuit_breaker_monitor import CircuitBreakerMonitor

# Import PostgreSQL circuit breaker components
from backend.database.circuit_breaker_integration import (
    get_circuit_breaker_session_manager,
    get_db_session_with_circuit_breaker,
    get_db_transaction_with_circuit_breaker,
    db_circuit_breaker
)
from backend.database.postgresql_circuit_breaker import PostgreSQLCircuitBreakerConfig
from backend.database import game_integration

logger = logging.getLogger(__name__)

# Constants
ROOM_SIZE = 4

class EnhancedGameServer:
    """
    Enhanced game server with PostgreSQL circuit breaker integration
    
    Features:
    - Dual storage: Redis for speed + PostgreSQL for persistence
    - Circuit breaker protection for all database operations
    - Automatic fallback mechanisms
    - Comprehensive monitoring and health checks
    - Transparent integration with existing game logic
    """
    
    def __init__(self):
        # Existing components
        self.redis_manager = RedisManager()
        self.circuit_breaker_monitor = CircuitBreakerMonitor(self.redis_manager)
        self.network_manager = NetworkManager()
        self.active_games = {}
        
        # PostgreSQL circuit breaker components
        self.db_session_manager = None
        self.db_circuit_breaker_enabled = True
        
        # Health and monitoring
        self.server_start_time = time.time()
        self.operation_stats = {
            'redis_operations': 0,
            'database_operations': 0,
            'fallback_operations': 0,
            'failed_operations': 0
        }
        
        logger.info("Enhanced Game Server with PostgreSQL Circuit Breaker initialized")
    
    async def initialize_database(self):
        """Initialize PostgreSQL connection with circuit breaker protection"""
        try:
            logger.info("Initializing PostgreSQL circuit breaker integration...")
            
            # Configure circuit breaker for gaming workloads
            config = PostgreSQLCircuitBreakerConfig(
                failure_threshold=5,        # Allow some failures before opening
                success_threshold=3,        # Quick recovery
                timeout=60.0,              # 1 minute timeout
                time_window=300.0,         # 5 minute failure window
                max_retry_attempts=3,      # Retry failed operations
                base_backoff_delay=1.0,    # Start with 1s delay
                max_backoff_delay=30.0,    # Max 30s delay
                enable_detailed_logging=True
            )
            
            # Get circuit breaker integrated session manager
            self.db_session_manager = await get_circuit_breaker_session_manager()
            
            # Test database connectivity
            health_status = await self.db_session_manager.health_check()
            
            if health_status.get('status') == 'healthy':
                logger.info("✅ PostgreSQL circuit breaker integration successful")
                self.db_circuit_breaker_enabled = True
            else:
                logger.warning("⚠️ PostgreSQL health check failed - running in Redis-only mode")
                logger.warning(f"Health status: {health_status}")
                self.db_circuit_breaker_enabled = False
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize PostgreSQL circuit breaker: {e}")
            logger.info("Falling back to Redis-only mode")
            self.db_circuit_breaker_enabled = False
    
    async def load_active_games_from_storage(self):
        """Load active games from both Redis and PostgreSQL with circuit breaker protection"""
        try:
            # First, try to load from Redis (faster)
            self.load_active_games_from_redis()
            
            # Then, sync with PostgreSQL if available
            if self.db_circuit_breaker_enabled:
                await self._sync_games_with_database()
            
        except Exception as e:
            logger.error(f"Error loading active games: {e}")
    
    def load_active_games_from_redis(self):
        """Load active games from Redis (existing implementation)"""
        try:
            for key in self.redis_manager.redis.scan_iter("room:*:game_state"):
                try:
                    room_code = key.decode().split(':')[1]
                    game_state = self.redis_manager.get_game_state(room_code)
                    if game_state:
                        # Reconstruct player list
                        players = []
                        if 'players' in game_state:
                            try:
                                players = json.loads(game_state['players'])
                            except Exception:
                                pass
                        if not players and 'player_order' in game_state:
                            try:
                                players = json.loads(game_state['player_order'])
                            except Exception:
                                pass
                        if not players:
                            players = [k[5:] for k in game_state if k.startswith('hand_')]
                        if not players:
                            continue
                        
                        game = GameBoard(players, room_code)
                        if 'teams' in game_state:
                            game.teams = json.loads(game_state['teams'])
                        if 'hakem' in game_state:
                            game.hakem = game_state['hakem']
                        if 'hokm' in game_state:
                            game.hokm = game_state['hokm']
                        if 'phase' in game_state:
                            game.game_phase = game_state['phase']
                        if 'current_turn' in game_state:
                            try:
                                game.current_turn = int(game_state['current_turn'])
                            except Exception:
                                pass
                        if 'tricks' in game_state:
                            try:
                                game.tricks = json.loads(game_state['tricks'])
                            except Exception:
                                pass
                        for p in players:
                            hand_key = f'hand_{p}'
                            if hand_key in game_state:
                                try:
                                    game.hands[p] = json.loads(game_state[hand_key])
                                except Exception:
                                    pass
                        
                        self.active_games[room_code] = game
                        logger.info(f"Recovered active game for room {room_code} with players: {players}")
                        
                except Exception as e:
                    logger.error(f"Failed to recover game for key {key}: {str(e)}")
        except Exception as e:
            logger.error(f"Failed to scan Redis for active games: {str(e)}")
    
    @db_circuit_breaker('read', fallback=lambda: None)
    async def _sync_games_with_database(self):
        """Sync active games with PostgreSQL database"""
        try:
            logger.info("Syncing active games with PostgreSQL...")
            
            # Get all active games from database
            active_db_games = await game_integration.get_joinable_games()
            
            for game_info in active_db_games:
                room_id = game_info['game']['room_id']
                
                # If game exists in Redis, ensure database is up to date
                if room_id in self.active_games:
                    await self._update_database_game_state(room_id)
                else:
                    # Game exists in database but not Redis - recover to Redis
                    await self._recover_game_from_database(room_id, game_info)
            
            self.operation_stats['database_operations'] += 1
            logger.info(f"Successfully synced {len(active_db_games)} games with database")
            
        except Exception as e:
            logger.error(f"Failed to sync games with database: {e}")
            self.operation_stats['failed_operations'] += 1
            # Don't raise - fallback to Redis-only operation
    
    @db_circuit_breaker('write')
    async def _update_database_game_state(self, room_code: str):
        """Update database with current Redis game state"""
        try:
            if room_code not in self.active_games:
                return
            
            game = self.active_games[room_code]
            redis_state = self.redis_manager.get_game_state(room_code)
            
            if redis_state and game:
                # Update game state in database
                await game_integration.update_game_state(
                    room_id=room_code,
                    game_phase=game.game_phase,
                    current_turn=getattr(game, 'current_turn', 0),
                    status='active' if game.game_phase != 'waiting' else 'waiting',
                    additional_data={
                        'teams': game.teams,
                        'hakem': getattr(game, 'hakem', None),
                        'hokm': getattr(game, 'hokm', None),
                        'tricks': getattr(game, 'tricks', []),
                        'redis_sync_time': time.time()
                    }
                )
                
                logger.debug(f"Updated database state for room {room_code}")
                
        except Exception as e:
            logger.error(f"Failed to update database state for room {room_code}: {e}")
            # Don't raise - continue with Redis operation
    
    async def _recover_game_from_database(self, room_id: str, game_info: Dict[str, Any]):
        """Recover game state from database to Redis"""
        try:
            logger.info(f"Recovering game {room_id} from database to Redis...")
            
            # Get full game state from database
            db_game_state = await game_integration.get_game_state(room_id)
            
            if db_game_state:
                # Reconstruct game in Redis and memory
                participants = db_game_state.get('participants', [])
                players = [p['player']['username'] for p in participants]
                
                if players:
                    # Create game instance
                    game = GameBoard(players, room_id)
                    
                    # Restore game state from database
                    game_data = db_game_state['game']
                    additional_data = game_data.get('game_metadata', {})
                    
                    if 'teams' in additional_data:
                        game.teams = additional_data['teams']
                    if 'hakem' in additional_data:
                        game.hakem = additional_data['hakem']
                    if 'hokm' in additional_data:
                        game.hokm = additional_data['hokm']
                    
                    game.game_phase = game_data.get('current_phase', 'waiting')
                    
                    # Store in active games and sync to Redis
                    self.active_games[room_id] = game
                    self._sync_game_to_redis(room_id, game)
                    
                    logger.info(f"Successfully recovered game {room_id} from database")
                
        except Exception as e:
            logger.error(f"Failed to recover game {room_id} from database: {e}")
    
    def _sync_game_to_redis(self, room_code: str, game: GameBoard):
        """Sync game state to Redis"""
        try:
            # Update Redis with current game state
            game_state = {
                'players': json.dumps(game.players),
                'teams': json.dumps(game.teams),
                'phase': game.game_phase,
                'hakem': getattr(game, 'hakem', ''),
                'hokm': getattr(game, 'hokm', ''),
                'current_turn': getattr(game, 'current_turn', 0),
                'tricks': json.dumps(getattr(game, 'tricks', [])),
                'last_sync': time.time()
            }
            
            # Add player hands
            for player in game.players:
                if player in game.hands:
                    game_state[f'hand_{player}'] = json.dumps(game.hands[player])
            
            # Save to Redis
            self.redis_manager.save_game_state(room_code, game_state)
            
            logger.debug(f"Synced game {room_code} to Redis")
            
        except Exception as e:
            logger.error(f"Failed to sync game {room_code} to Redis: {e}")
    
    async def handle_join_enhanced(self, websocket, data):
        """Enhanced join handler with database integration"""
        try:
            room_code = data.get('room_code', '9999')
            username = data.get('username', f'Player_{random.randint(1000, 9999)}')
            
            # Validate room exists or can be created
            if not self.redis_manager.room_exists(room_code):
                try:
                    self.redis_manager.create_room(room_code)
                    logger.info(f"Room {room_code} created successfully")
                    
                    # Also create in database if circuit breaker is enabled
                    if self.db_circuit_breaker_enabled:
                        await self._create_database_room(room_code, username)
                        
                except Exception as e:
                    logger.error(f"Failed to create room {room_code}: {str(e)}")
                    await websocket.send(json.dumps({
                        'type': 'error',
                        'message': f'Failed to create room: {str(e)}'
                    }))
                    return
            
            # Get connection info
            connection_id = f"ws_{id(websocket)}_{time.time()}"
            ip_address = websocket.remote_address[0] if websocket.remote_address else "unknown"
            user_agent = websocket.request_headers.get('User-Agent', 'Unknown')
            
            # Register WebSocket connection in database
            if self.db_circuit_breaker_enabled:
                await self._register_websocket_connection(
                    connection_id, username, room_code, ip_address, user_agent
                )
            
            # Continue with existing join logic...
            await self._process_player_join(websocket, room_code, username, connection_id)
            
        except Exception as e:
            logger.error(f"Error in enhanced join handler: {e}")
            await websocket.send(json.dumps({
                'type': 'error',
                'message': f'Join failed: {str(e)}'
            }))
    
    @db_circuit_breaker('write')
    async def _create_database_room(self, room_code: str, creator_username: str):
        """Create room in database with circuit breaker protection"""
        try:
            await game_integration.create_game_room(
                room_id=room_code,
                creator_username=creator_username,
                game_type='hokm',
                max_players=4
            )
            logger.info(f"Created room {room_code} in database")
            self.operation_stats['database_operations'] += 1
            
        except Exception as e:
            logger.warning(f"Failed to create room {room_code} in database: {e}")
            self.operation_stats['failed_operations'] += 1
            # Don't raise - continue with Redis-only operation
    
    @db_circuit_breaker('write')
    async def _register_websocket_connection(
        self, 
        connection_id: str, 
        username: str, 
        room_code: str, 
        ip_address: str, 
        user_agent: str
    ):
        """Register WebSocket connection in database"""
        try:
            await game_integration.register_websocket_connection(
                connection_id=connection_id,
                username=username,
                room_id=room_code,
                ip_address=ip_address,
                user_agent=user_agent
            )
            logger.debug(f"Registered WebSocket connection {connection_id}")
            self.operation_stats['database_operations'] += 1
            
        except Exception as e:
            logger.warning(f"Failed to register WebSocket connection: {e}")
            self.operation_stats['failed_operations'] += 1
    
    async def _process_player_join(self, websocket, room_code: str, username: str, connection_id: str):
        """Process player join with dual storage updates"""
        try:
            # Add player to Redis (existing logic)
            room_info = self.redis_manager.add_player_to_room(room_code, username)
            
            if room_info is None:
                await websocket.send(json.dumps({
                    'type': 'error',
                    'message': 'Failed to join room'
                }))
                return
            
            # Update database if enabled
            if self.db_circuit_breaker_enabled:
                await self._add_player_to_database_room(room_code, username, connection_id)
            
            # Continue with existing game logic...
            await self._handle_game_progression(websocket, room_code, username, room_info)
            
        except Exception as e:
            logger.error(f"Error processing player join: {e}")
            await websocket.send(json.dumps({
                'type': 'error',
                'message': f'Failed to process join: {str(e)}'
            }))
    
    @db_circuit_breaker('write')
    async def _add_player_to_database_room(self, room_code: str, username: str, connection_id: str):
        """Add player to database room"""
        try:
            await game_integration.join_game_room(
                room_id=room_code,
                username=username,
                connection_id=connection_id
            )
            logger.debug(f"Added player {username} to database room {room_code}")
            self.operation_stats['database_operations'] += 1
            
        except Exception as e:
            logger.warning(f"Failed to add player {username} to database room: {e}")
            self.operation_stats['failed_operations'] += 1
    
    async def _handle_game_progression(self, websocket, room_code: str, username: str, room_info: Dict[str, Any]):
        """Handle game progression with database sync"""
        try:
            players = room_info.get('players', [])
            
            # Send join success response
            await websocket.send(json.dumps({
                'type': 'join_success',
                'room_code': room_code,
                'username': username,
                'players': players,
                'player_count': len(players)
            }))
            
            # Check if room is full and start team assignment
            if len(players) == ROOM_SIZE:
                await self._start_team_assignment(room_code, players)
            
        except Exception as e:
            logger.error(f"Error handling game progression: {e}")
    
    async def _start_team_assignment(self, room_code: str, players: list):
        """Start team assignment with database sync"""
        try:
            # Create GameBoard instance
            game = GameBoard(players, room_code)
            game.assign_teams_and_hakem()
            
            # Store in active games
            self.active_games[room_code] = game
            
            # Update Redis
            game_state = {
                'players': json.dumps(players),
                'teams': json.dumps(game.teams),
                'hakem': game.hakem,
                'phase': 'team_assigned'
            }
            self.redis_manager.save_game_state(room_code, game_state)
            
            # Update database
            if self.db_circuit_breaker_enabled:
                await self._update_database_game_state(room_code)
            
            # Broadcast team assignment
            await self._broadcast_team_assignment(room_code, game)
            
        except Exception as e:
            logger.error(f"Error starting team assignment: {e}")
    
    async def _broadcast_team_assignment(self, room_code: str, game: GameBoard):
        """Broadcast team assignment to all players"""
        try:
            message = {
                'type': 'teams_assigned',
                'teams': game.teams,
                'hakem': game.hakem,
                'room_code': room_code
            }
            
            # Broadcast to all connected players (would need WebSocket connection tracking)
            # This would integrate with your existing connection management
            
            logger.info(f"Teams assigned for room {room_code}: {game.teams}, Hakem: {game.hakem}")
            
        except Exception as e:
            logger.error(f"Error broadcasting team assignment: {e}")
    
    async def get_comprehensive_health_status(self) -> Dict[str, Any]:
        """Get comprehensive health status including circuit breaker info"""
        try:
            status = {
                'timestamp': time.time(),
                'uptime_seconds': time.time() - self.server_start_time,
                'active_games': len(self.active_games),
                'operation_stats': self.operation_stats.copy(),
                'redis': {
                    'connected': True,  # Would check actual Redis connection
                    'circuit_breaker': await self._get_redis_circuit_breaker_status()
                },
                'postgresql': {
                    'enabled': self.db_circuit_breaker_enabled,
                    'circuit_breaker': await self._get_postgresql_circuit_breaker_status() if self.db_circuit_breaker_enabled else None
                }
            }
            
            # Calculate success rates
            total_ops = sum(self.operation_stats.values())
            if total_ops > 0:
                status['success_rate'] = (total_ops - self.operation_stats['failed_operations']) / total_ops * 100
            else:
                status['success_rate'] = 100.0
            
            return status
            
        except Exception as e:
            logger.error(f"Error getting health status: {e}")
            return {
                'error': str(e),
                'timestamp': time.time()
            }
    
    async def _get_redis_circuit_breaker_status(self) -> Dict[str, Any]:
        """Get Redis circuit breaker status"""
        try:
            # Would integrate with your existing Redis circuit breaker
            return {
                'status': 'healthy',
                'state': 'closed'
            }
        except Exception:
            return {
                'status': 'error',
                'state': 'unknown'
            }
    
    async def _get_postgresql_circuit_breaker_status(self) -> Dict[str, Any]:
        """Get PostgreSQL circuit breaker status"""
        try:
            if self.db_session_manager:
                return await self.db_session_manager.get_circuit_breaker_status()
            else:
                return {
                    'status': 'disabled',
                    'state': 'not_initialized'
                }
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e)
            }
    
    async def cleanup(self):
        """Cleanup server resources"""
        try:
            logger.info("Cleaning up Enhanced Game Server...")
            
            # Cleanup database session manager
            if self.db_session_manager:
                await self.db_session_manager.cleanup()
            
            # Cleanup existing components
            # (would cleanup Redis connections, WebSocket connections, etc.)
            
            logger.info("Enhanced Game Server cleanup completed")
            
        except Exception as e:
            logger.error(f"Error during server cleanup: {e}")

async def main():
    """
    Main function to run the enhanced server
    """
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create and initialize enhanced server
    server = EnhancedGameServer()
    
    try:
        # Initialize database circuit breaker
        await server.initialize_database()
        
        # Load active games from storage
        await server.load_active_games_from_storage()
        
        logger.info("🚀 Enhanced Hokm Game Server with PostgreSQL Circuit Breaker started!")
        logger.info(f"   - Redis Circuit Breaker: ✅ Enabled")
        logger.info(f"   - PostgreSQL Circuit Breaker: {'✅ Enabled' if server.db_circuit_breaker_enabled else '❌ Disabled (fallback mode)'}")
        logger.info(f"   - Active Games Loaded: {len(server.active_games)}")
        
        # Start WebSocket server (would integrate with your existing WebSocket handler)
        # async with websockets.serve(server.handle_connection, "localhost", 8765):
        #     await asyncio.Future()  # Run forever
        
        # For now, just demonstrate health check
        health_status = await server.get_comprehensive_health_status()
        logger.info(f"Server Health Status: {json.dumps(health_status, indent=2)}")
        
        # Keep server running for demonstration
        logger.info("Server running... Press Ctrl+C to stop")
        await asyncio.sleep(3600)  # Run for 1 hour
        
    except KeyboardInterrupt:
        logger.info("Server shutdown requested by user")
    except Exception as e:
        logger.error(f"Server error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await server.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
