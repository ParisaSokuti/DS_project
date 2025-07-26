"""
Enhanced Hokm Game Server with SQLAlchemy 2.0 Async Integration
This integrates PostgreSQL database operations with your existing Redis-based server
"""

import asyncio
import json
import logging
from typing import Dict, Any, Optional, List
import websockets
from websockets.server import WebSocketServerProtocol
import sys
import os
import uuid
import time

# Add backend directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

# Import existing components
from backend.network import NetworkManager
from backend.game_board import GameBoard
from backend.game_states import GameState
from backend.redis_manager_resilient import ResilientRedisManager as RedisManager
from backend.circuit_breaker_monitor import CircuitBreakerMonitor

# Import new database integration
from backend.database import (
    get_session_manager, 
    game_integration,
    configure_logging,
    get_database_config,
    GameIntegrationLayer
)

logger = logging.getLogger(__name__)

class EnhancedHokmGameServer:
    """
    Enhanced Hokm game server with dual storage:
    - PostgreSQL for persistent game state, player data, and analytics
    - Redis for real-time session management and fast lookups
    
    This maintains compatibility with your existing server while adding
    comprehensive database features for production deployment.
    """
    
    def __init__(self):
        # Existing Redis components
        self.redis_manager = RedisManager()
        self.circuit_breaker_monitor = CircuitBreakerMonitor(self.redis_manager)
        self.network_manager = NetworkManager()
        self.active_games = {}  # Maps room_code -> GameBoard
        
        # New database components
        self.session_manager = None
        self.db_integration = GameIntegrationLayer()
        
        # Connection tracking
        self.active_connections: Dict[str, WebSocketServerProtocol] = {}
        self.connection_to_player: Dict[str, str] = {}
        self.connection_to_room: Dict[str, str] = {}
        self.player_to_connection: Dict[str, str] = {}
        
        # Performance monitoring
        self.stats = {
            'total_connections': 0,
            'active_games': 0,
            'database_operations': 0,
            'redis_operations': 0,
            'errors': 0
        }
    
    async def initialize(self):
        """
        Initialize the enhanced server with both Redis and PostgreSQL
        """
        try:
            # Configure logging
            config = get_database_config()
            configure_logging(config)
            
            # Initialize database session manager
            self.session_manager = await get_session_manager()
            
            # Test database connection
            health = await self.session_manager.health_check()
            if health['status'] != 'healthy':
                logger.error(f"Database health check failed: {health}")
                raise RuntimeError(f"Database initialization failed: {health}")
            
            # Load existing games from Redis (maintain compatibility)
            self.load_active_games_from_redis()
            
            # Sync Redis games with database
            await self.sync_redis_games_to_database()
            
            logger.info("Enhanced Hokm game server initialized successfully")
            logger.info(f"Database: {health}")
            logger.info(f"Redis circuit breaker: {self.circuit_breaker_monitor.get_status()}")
            
        except Exception as e:
            logger.error(f"Failed to initialize enhanced server: {e}")
            raise
    
    def load_active_games_from_redis(self):
        """Load active games from Redis (existing functionality)"""
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
                        # Restore game state from Redis
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
    
    async def sync_redis_games_to_database(self):
        """
        Synchronize Redis game state with PostgreSQL database
        This ensures data consistency between fast Redis cache and persistent database
        """
        try:
            for room_code, game in self.active_games.items():
                try:
                    # Create or update game session in database
                    db_game = await self.db_integration.create_game_room(
                        room_id=room_code,
                        creator_username=game.players[0] if game.players else 'unknown',
                        game_type='hokm',
                        max_players=4
                    )
                    
                    # Add all players to database
                    for i, player_name in enumerate(game.players):
                        await self.db_integration.join_game_room(
                            room_id=room_code,
                            username=player_name,
                            connection_id=f"sync_{player_name}_{int(time.time())}"
                        )
                    
                    # Update game state in database
                    await self.db_integration.update_game_state(
                        room_id=room_code,
                        game_phase=game.game_phase,
                        current_turn=game.current_turn,
                        additional_data={
                            'hakem': game.hakem,
                            'hokm': game.hokm,
                            'teams': game.teams,
                            'tricks': game.tricks
                        }
                    )
                    
                    logger.info(f"Synced game {room_code} to database")
                    
                except Exception as e:
                    logger.error(f"Failed to sync game {room_code} to database: {e}")
                    
        except Exception as e:
            logger.error(f"Failed to sync games to database: {e}")
    
    async def handle_connection(self, websocket: WebSocketServerProtocol, path: str):
        """
        Enhanced connection handler with database integration
        """
        connection_id = f"conn_{id(websocket)}_{int(time.time())}"
        self.stats['total_connections'] += 1
        
        try:
            # Register connection in database
            await self.db_integration.register_websocket_connection(
                connection_id=connection_id,
                ip_address=websocket.remote_address[0] if websocket.remote_address else None,
                user_agent=websocket.request_headers.get('User-Agent', 'Unknown')
            )
            
            # Track connection locally
            self.active_connections[connection_id] = websocket
            
            logger.info(f"New enhanced connection: {connection_id}")
            
            # Send welcome message with enhanced features
            await self.send_message(websocket, {
                'type': 'connection_established',
                'connection_id': connection_id,
                'features': ['database_persistence', 'analytics', 'reconnection_support'],
                'server_stats': self.get_server_stats()
            })
            
            # Handle messages
            await self.handle_messages(websocket, connection_id)
            
        except Exception as e:
            logger.error(f"Error handling enhanced connection {connection_id}: {e}")
            self.stats['errors'] += 1
        finally:
            await self.disconnect_client(connection_id)
    
    async def handle_messages(self, websocket: WebSocketServerProtocol, connection_id: str):
        """
        Enhanced message handler with database operations
        """
        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    message_type = data.get('type')
                    
                    # Route to appropriate handler
                    if message_type == 'join':
                        await self.handle_enhanced_join(websocket, connection_id, data)
                    elif message_type == 'play_card':
                        await self.handle_enhanced_play_card(websocket, connection_id, data)
                    elif message_type == 'reconnect':
                        await self.handle_reconnection(websocket, connection_id, data)
                    elif message_type == 'get_game_state':
                        await self.handle_get_game_state(websocket, connection_id, data)
                    elif message_type == 'get_player_stats':
                        await self.handle_get_player_stats(websocket, connection_id, data)
                    else:
                        # Fallback to existing handlers for compatibility
                        await self.handle_legacy_message(websocket, connection_id, data)
                        
                    self.stats['database_operations'] += 1
                    
                except json.JSONDecodeError:
                    await self.send_error(websocket, "Invalid JSON message")
                except Exception as e:
                    logger.error(f"Error handling message from {connection_id}: {e}")
                    await self.send_error(websocket, f"Message handling error: {str(e)}")
                    self.stats['errors'] += 1
                    
        except websockets.exceptions.ConnectionClosed:
            logger.info(f"Connection {connection_id} closed normally")
        except Exception as e:
            logger.error(f"Error in message loop for {connection_id}: {e}")
    
    async def handle_enhanced_join(self, websocket: WebSocketServerProtocol, connection_id: str, data: Dict[str, Any]):
        """
        Enhanced join handler with database integration
        """
        try:
            room_code = data.get('room_code', '9999')
            username = data.get('username', f'player_{int(time.time())}')
            
            # Create/update player in database
            player, is_new = await self.db_integration.create_player_if_not_exists(
                username=username,
                email=data.get('email'),
                display_name=data.get('display_name', username)
            )
            
            # Track connection to player mapping
            self.connection_to_player[connection_id] = username
            self.player_to_connection[username] = connection_id
            self.connection_to_room[connection_id] = room_code
            
            # Handle Redis room creation/joining (existing logic)
            if not self.redis_manager.room_exists(room_code):
                self.redis_manager.create_room(room_code)
                logger.info(f"Room {room_code} created for player {username}")
            
            # Add player to Redis room
            self.redis_manager.add_player_to_room(room_code, username)
            
            # Join or create game in database
            try:
                db_game, participant = await self.db_integration.join_game_room(
                    room_id=room_code,
                    username=username,
                    connection_id=connection_id,
                    ip_address=websocket.remote_address[0] if websocket.remote_address else None,
                    user_agent=websocket.request_headers.get('User-Agent', 'Unknown')
                )
                
                # Get current players from database
                players_in_game = await self.db_integration.get_game_participants(room_code)
                
                # Send enhanced join response
                await self.send_message(websocket, {
                    'type': 'join_success',
                    'room_code': room_code,
                    'username': username,
                    'player_id': str(player.id),
                    'position': participant.position,
                    'team': participant.team,
                    'is_new_player': is_new,
                    'players_in_game': [p.player.username for p in players_in_game],
                    'game_status': db_game.status,
                    'player_stats': {
                        'total_games': player.total_games,
                        'wins': player.wins,
                        'rating': player.rating
                    }
                })
                
                # Notify other players
                await self.broadcast_to_room(room_code, {
                    'type': 'player_joined',
                    'username': username,
                    'players_count': len(players_in_game),
                    'player_stats': {
                        'total_games': player.total_games,
                        'wins': player.wins,
                        'rating': player.rating
                    }
                }, exclude_connection=connection_id)
                
                # If game is full, start it
                if len(players_in_game) >= 4:
                    await self.start_enhanced_game(room_code)
                
                logger.info(f"Player {username} joined room {room_code} (position: {participant.position}, team: {participant.team})")
                
            except Exception as e:
                logger.error(f"Database join failed for {username} in room {room_code}: {e}")
                # Fallback to Redis-only mode
                await self.handle_legacy_join(websocket, connection_id, data)
                
        except Exception as e:
            logger.error(f"Enhanced join failed for connection {connection_id}: {e}")
            await self.send_error(websocket, f"Join failed: {str(e)}")
    
    async def handle_enhanced_play_card(self, websocket: WebSocketServerProtocol, connection_id: str, data: Dict[str, Any]):
        """
        Enhanced card play handler with move recording
        """
        try:
            username = self.connection_to_player.get(connection_id)
            room_code = self.connection_to_room.get(connection_id)
            
            if not username or not room_code:
                await self.send_error(websocket, "Player not in a game")
                return
            
            card = data.get('card')
            if not card:
                await self.send_error(websocket, "No card specified")
                return
            
            # Record move in database
            try:
                await self.db_integration.record_game_move(
                    room_id=room_code,
                    username=username,
                    move_type='play_card',
                    move_data={
                        'card': card,
                        'timestamp': time.time()
                    }
                )
            except Exception as e:
                logger.warning(f"Failed to record move in database: {e}")
            
            # Execute move using existing game logic
            game = self.active_games.get(room_code)
            if not game:
                await self.send_error(websocket, "Game not found")
                return
            
            # Validate and play card (existing logic)
            if username not in game.hands:
                await self.send_error(websocket, "Player not in game")
                return
            
            if card not in game.hands[username]:
                await self.send_error(websocket, "Card not in hand")
                return
            
            # Execute the card play
            result = game.play_card(username, card)
            
            if result['success']:
                # Update Redis state
                self.redis_manager.save_game_state(room_code, game)
                
                # Update database game state
                try:
                    await self.db_integration.update_game_state(
                        room_id=room_code,
                        current_turn=game.current_turn,
                        additional_data={
                            'last_move': {
                                'player': username,
                                'card': card,
                                'timestamp': time.time()
                            }
                        }
                    )
                except Exception as e:
                    logger.warning(f"Failed to update database game state: {e}")
                
                # Broadcast move to all players
                await self.broadcast_to_room(room_code, {
                    'type': 'card_played',
                    'player': username,
                    'card': card,
                    'game_state': game.get_public_state(),
                    'next_turn': game.get_current_player()
                })
                
                # Check for game completion
                if game.is_game_complete():
                    await self.handle_game_completion(room_code, game)
                
            else:
                await self.send_error(websocket, result['error'])
                
        except Exception as e:
            logger.error(f"Enhanced play card failed: {e}")
            await self.send_error(websocket, f"Play card failed: {str(e)}")
    
    async def handle_reconnection(self, websocket: WebSocketServerProtocol, connection_id: str, data: Dict[str, Any]):
        """
        Handle player reconnection with database state recovery
        """
        try:
            username = data.get('username')
            room_code = data.get('room_code')
            
            if not username or not room_code:
                await self.send_error(websocket, "Username and room_code required for reconnection")
                return
            
            # Verify player was in the game
            participants = await self.db_integration.get_game_participants(room_code)
            player_participant = None
            
            for participant in participants:
                if participant.player.username == username:
                    player_participant = participant
                    break
            
            if not player_participant:
                await self.send_error(websocket, "Player was not in this game")
                return
            
            # Update connection mappings
            old_connection = self.player_to_connection.get(username)
            if old_connection and old_connection in self.active_connections:
                # Close old connection
                try:
                    await self.active_connections[old_connection].close()
                    del self.active_connections[old_connection]
                except:
                    pass
            
            # Update mappings
            self.connection_to_player[connection_id] = username
            self.player_to_connection[username] = connection_id
            self.connection_to_room[connection_id] = room_code
            
            # Update database connection
            await self.db_integration.update_websocket_connection(
                connection_id=connection_id,
                player_username=username,
                status='reconnected'
            )
            
            # Get current game state
            game = self.active_games.get(room_code)
            if game:
                # Send reconnection success with full game state
                await self.send_message(websocket, {
                    'type': 'reconnection_success',
                    'room_code': room_code,
                    'username': username,
                    'position': player_participant.position,
                    'team': player_participant.team,
                    'game_state': game.get_player_state(username),
                    'hand': game.hands.get(username, []),
                    'current_turn': game.get_current_player(),
                    'phase': game.game_phase
                })
                
                # Notify other players
                await self.broadcast_to_room(room_code, {
                    'type': 'player_reconnected',
                    'username': username
                }, exclude_connection=connection_id)
                
                logger.info(f"Player {username} reconnected to room {room_code}")
            else:
                await self.send_error(websocket, "Game no longer active")
                
        except Exception as e:
            logger.error(f"Reconnection failed: {e}")
            await self.send_error(websocket, f"Reconnection failed: {str(e)}")
    
    async def handle_get_game_state(self, websocket: WebSocketServerProtocol, connection_id: str, data: Dict[str, Any]):
        """
        Get comprehensive game state from both Redis and database
        """
        try:
            username = self.connection_to_player.get(connection_id)
            room_code = self.connection_to_room.get(connection_id)
            
            if not username or not room_code:
                await self.send_error(websocket, "Player not in a game")
                return
            
            # Get Redis game state (fast)
            game = self.active_games.get(room_code)
            redis_state = game.get_player_state(username) if game else None
            
            # Get database game state (comprehensive)
            try:
                db_game_state = await self.db_integration.get_game_state(room_code)
                participants = await self.db_integration.get_game_participants(room_code)
                recent_moves = await self.db_integration.get_recent_moves(room_code, limit=10)
                
                await self.send_message(websocket, {
                    'type': 'game_state',
                    'room_code': room_code,
                    'redis_state': redis_state,
                    'database_state': {
                        'game_info': db_game_state,
                        'participants': [
                            {
                                'username': p.player.username,
                                'position': p.position,
                                'team': p.team,
                                'status': p.status
                            } for p in participants
                        ],
                        'recent_moves': [
                            {
                                'player': move.player.username,
                                'move_type': move.move_type,
                                'move_data': move.move_data,
                                'timestamp': move.created_at.isoformat()
                            } for move in recent_moves
                        ]
                    }
                })
                
            except Exception as e:
                logger.warning(f"Failed to get database state: {e}")
                # Fallback to Redis only
                await self.send_message(websocket, {
                    'type': 'game_state',
                    'room_code': room_code,
                    'redis_state': redis_state,
                    'database_state': None,
                    'error': 'Database state unavailable'
                })
                
        except Exception as e:
            logger.error(f"Get game state failed: {e}")
            await self.send_error(websocket, f"Failed to get game state: {str(e)}")
    
    async def handle_get_player_stats(self, websocket: WebSocketServerProtocol, connection_id: str, data: Dict[str, Any]):
        """
        Get comprehensive player statistics from database
        """
        try:
            username = self.connection_to_player.get(connection_id)
            target_username = data.get('target_username', username)
            
            if not username:
                await self.send_error(websocket, "Player not identified")
                return
            
            # Get player stats from database
            stats = await self.db_integration.get_player_statistics(target_username)
            
            await self.send_message(websocket, {
                'type': 'player_stats',
                'username': target_username,
                'stats': stats
            })
            
        except Exception as e:
            logger.error(f"Get player stats failed: {e}")
            await self.send_error(websocket, f"Failed to get player stats: {str(e)}")
    
    async def handle_legacy_message(self, websocket: WebSocketServerProtocol, connection_id: str, data: Dict[str, Any]):
        """
        Handle legacy messages using existing server logic
        This ensures backward compatibility
        """
        # Map connection_id back to websocket for legacy handlers
        message_type = data.get('type')
        
        # Use existing handlers but track in stats
        self.stats['redis_operations'] += 1
        
        # You can implement legacy handlers here or redirect to existing methods
        # For now, just log the legacy operation
        logger.info(f"Legacy message handled: {message_type} from {connection_id}")
    
    async def handle_legacy_join(self, websocket: WebSocketServerProtocol, connection_id: str, data: Dict[str, Any]):
        """
        Fallback join handler using existing Redis logic
        """
        try:
            room_code = data.get('room_code', '9999')
            username = data.get('username', f'player_{int(time.time())}')
            
            # Use existing Redis logic
            if not self.redis_manager.room_exists(room_code):
                self.redis_manager.create_room(room_code)
            
            self.redis_manager.add_player_to_room(room_code, username)
            
            # Update local mappings
            self.connection_to_player[connection_id] = username
            self.player_to_connection[username] = connection_id
            self.connection_to_room[connection_id] = room_code
            
            await self.send_message(websocket, {
                'type': 'join_success',
                'room_code': room_code,
                'username': username,
                'mode': 'redis_fallback'
            })
            
            logger.info(f"Player {username} joined room {room_code} (Redis fallback mode)")
            
        except Exception as e:
            logger.error(f"Legacy join failed: {e}")
            await self.send_error(websocket, f"Join failed: {str(e)}")
    
    async def start_enhanced_game(self, room_code: str):
        """
        Start a game with enhanced database tracking
        """
        try:
            # Get participants from database
            participants = await self.db_integration.get_game_participants(room_code)
            
            if len(participants) < 4:
                logger.warning(f"Not enough players to start game {room_code}")
                return
            
            # Create GameBoard if not exists
            if room_code not in self.active_games:
                player_names = [p.player.username for p in participants]
                game = GameBoard(player_names, room_code)
                self.active_games[room_code] = game
            
            game = self.active_games[room_code]
            
            # Update database game status
            await self.db_integration.update_game_state(
                room_id=room_code,
                status='in_progress',
                additional_data={
                    'started_at': time.time(),
                    'players': [p.player.username for p in participants]
                }
            )
            
            # Broadcast game start
            await self.broadcast_to_room(room_code, {
                'type': 'game_started',
                'room_code': room_code,
                'players': [p.player.username for p in participants],
                'your_hand': None  # Will be set per player
            })
            
            # Send individual hands
            for participant in participants:
                player_name = participant.player.username
                connection_id = self.player_to_connection.get(player_name)
                
                if connection_id and connection_id in self.active_connections:
                    await self.send_message(self.active_connections[connection_id], {
                        'type': 'your_hand',
                        'hand': game.hands.get(player_name, []),
                        'position': participant.position,
                        'team': participant.team
                    })
            
            self.stats['active_games'] += 1
            logger.info(f"Enhanced game started for room {room_code}")
            
        except Exception as e:
            logger.error(f"Failed to start enhanced game {room_code}: {e}")
    
    async def handle_game_completion(self, room_code: str, game: GameBoard):
        """
        Handle game completion with database recording
        """
        try:
            # Determine winners and update database
            winners = game.get_winners()  # Assuming this method exists
            
            # Record game completion
            await self.db_integration.complete_game(
                room_id=room_code,
                winner_data=winners,
                final_scores=game.get_final_scores(),  # Assuming this method exists
                game_duration=time.time() - game.start_time  # Assuming start_time exists
            )
            
            # Broadcast game completion
            await self.broadcast_to_room(room_code, {
                'type': 'game_completed',
                'room_code': room_code,
                'winners': winners,
                'final_scores': game.get_final_scores()
            })
            
            # Clean up
            if room_code in self.active_games:
                del self.active_games[room_code]
            
            self.stats['active_games'] -= 1
            logger.info(f"Game completed for room {room_code}")
            
        except Exception as e:
            logger.error(f"Failed to handle game completion {room_code}: {e}")
    
    async def disconnect_client(self, connection_id: str):
        """
        Enhanced client disconnection with database cleanup
        """
        try:
            username = self.connection_to_player.get(connection_id)
            room_code = self.connection_to_room.get(connection_id)
            
            # Update database connection status
            if username:
                await self.db_integration.update_websocket_connection(
                    connection_id=connection_id,
                    status='disconnected'
                )
            
            # Clean up local mappings
            if connection_id in self.active_connections:
                del self.active_connections[connection_id]
            
            if username:
                if self.player_to_connection.get(username) == connection_id:
                    del self.player_to_connection[username]
                
                # Notify room of disconnection
                if room_code:
                    await self.broadcast_to_room(room_code, {
                        'type': 'player_disconnected',
                        'username': username,
                        'connection_id': connection_id
                    }, exclude_connection=connection_id)
            
            if connection_id in self.connection_to_player:
                del self.connection_to_player[connection_id]
            
            if connection_id in self.connection_to_room:
                del self.connection_to_room[connection_id]
            
            logger.info(f"Client disconnected: {connection_id} (user: {username})")
            
        except Exception as e:
            logger.error(f"Error during client disconnect: {e}")
    
    async def broadcast_to_room(self, room_code: str, message: Dict[str, Any], exclude_connection: str = None):
        """
        Broadcast message to all players in a room
        """
        try:
            # Get all connections for this room
            room_connections = [
                conn_id for conn_id, room in self.connection_to_room.items()
                if room == room_code and conn_id != exclude_connection
            ]
            
            # Send message to all connections
            for connection_id in room_connections:
                if connection_id in self.active_connections:
                    try:
                        await self.send_message(self.active_connections[connection_id], message)
                    except Exception as e:
                        logger.warning(f"Failed to send message to {connection_id}: {e}")
                        
        except Exception as e:
            logger.error(f"Broadcast to room {room_code} failed: {e}")
    
    async def send_message(self, websocket: WebSocketServerProtocol, message: Dict[str, Any]):
        """
        Send JSON message to websocket
        """
        try:
            await websocket.send(json.dumps(message))
        except Exception as e:
            logger.warning(f"Failed to send message: {e}")
    
    async def send_error(self, websocket: WebSocketServerProtocol, error_message: str):
        """
        Send error message to websocket
        """
        await self.send_message(websocket, {
            'type': 'error',
            'message': error_message,
            'timestamp': time.time()
        })
    
    def get_server_stats(self) -> Dict[str, Any]:
        """
        Get current server statistics
        """
        return {
            **self.stats,
            'active_connections': len(self.active_connections),
            'active_games_count': len(self.active_games),
            'database_health': 'unknown',  # Will be updated by health checks
            'redis_health': self.circuit_breaker_monitor.get_status()
        }
    
    async def cleanup(self):
        """
        Cleanup server resources
        """
        try:
            # Close all active connections
            for connection in self.active_connections.values():
                try:
                    await connection.close()
                except:
                    pass
            
            # Cleanup database session manager
            if self.session_manager:
                await self.session_manager.cleanup()
            
            logger.info("Enhanced server cleanup completed")
            
        except Exception as e:
            logger.error(f"Error during server cleanup: {e}")

# Main server startup
async def main():
    """
    Start the enhanced Hokm game server
    """
    server = EnhancedHokmGameServer()
    
    try:
        # Initialize server
        await server.initialize()
        
        # Start WebSocket server
        logger.info("Starting enhanced Hokm game server on localhost:8765")
        
        async with websockets.serve(
            server.handle_connection, 
            "localhost", 
            8765,
            ping_interval=60,      # Send ping every 60 seconds
            ping_timeout=300,      # 5 minutes timeout for ping response
            close_timeout=300,     # 5 minutes timeout for close handshake
            max_size=1024*1024,    # 1MB max message size
            max_queue=100          # Max queued messages
        ):
            logger.info("Enhanced Hokm game server is running!")
            logger.info("Features: PostgreSQL persistence, Redis caching, reconnection support, analytics")
            
            # Keep server running
            await asyncio.Future()  # Run forever
            
    except KeyboardInterrupt:
        logger.info("Server shutdown requested")
    except Exception as e:
        logger.error(f"Server error: {e}")
    finally:
        await server.cleanup()

if __name__ == "__main__":
    # Run the enhanced server
    asyncio.run(main())
