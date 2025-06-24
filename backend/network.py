# network.py (Backend)
import asyncio
import json
import websockets
import time
import sys
import os
from typing import Optional, Dict, Any
try:
    from websockets.legacy.server import WebSocketServerProtocol
except ImportError:
    try:
        from websockets.server import WebSocketServerProtocol
    except ImportError:
        WebSocketServerProtocol = Any

# Add current directory to Python path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from redis_manager import RedisManager

class NetworkManager:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(NetworkManager, cls).__new__(cls)
            cls._instance.initialized = False
        return cls._instance
    
    def __init__(self):
        if not self.initialized:
            # Initialize Redis connection
            self.redis_manager = RedisManager()
            
            # Store only live WebSocket connections
            self.live_connections = {}  # Maps player_id -> websocket
            self.connection_metadata = {}  # Maps websocket -> {player_id, room_code}
            
            self.initialized = True
            
    def register_connection(self, websocket, player_id: str, room_code: str):
        """Register a new live WebSocket connection"""
        self.live_connections[player_id] = websocket
        self.connection_metadata[websocket] = {
            'player_id': player_id,
            'room_code': room_code,
            'connected_at': int(time.time())
        }
        
    def remove_connection(self, websocket):
        """Remove a WebSocket connection"""
        if websocket in self.connection_metadata:
            player_id = self.connection_metadata[websocket]['player_id']
            if player_id in self.live_connections:
                del self.live_connections[player_id]
            del self.connection_metadata[websocket]
            
    def get_live_connection(self, player_id: str):
        """Get a player's live WebSocket connection if it exists"""
        return self.live_connections.get(player_id)
    
    @staticmethod
    async def send_message(websocket, message_type: str, data: Optional[Dict[str, Any]] = None) -> bool:
        """Send a message to a websocket with proper error handling"""
        try:
            message = {"type": message_type}
            if data:
                message.update(data)
            await websocket.send(json.dumps(message))
            return True
        except websockets.ConnectionClosed:
            print("[ERROR] Connection closed while sending message")
            return False
        except Exception as e:
            print(f"[ERROR] Failed to send message: {str(e)}")
            return False
            
    async def broadcast_to_room(self, room_code: str, msg_type: str, data: Dict[str, Any], redis_manager: RedisManager):
        """
        Broadcast a message to all live connections in a room.
        Room membership is checked from Redis but messages are sent only to live connections.
        """
        try:
            # Get all players in room from Redis
            players = redis_manager.get_room_players(room_code)
            
            # Send message only to players with live connections
            for player in players:
                player_id = player.get('player_id')
                if not player_id:
                    continue
                    
                # Get live connection for player if it exists
                ws = self.get_live_connection(player_id)
                if ws:
                    try:
                        # Customize message for player if needed
                        player_data = data.copy()
                        player_data.update({
                            'you': player.get('username'),
                            'player_number': player.get('player_number', 0)
                        })
                        
                        success = await self.send_message(ws, msg_type, player_data)
                        if not success:
                            print(f"[WARNING] Failed to send message to {player.get('username')}")
                            # Remove failed connection
                            self.remove_connection(ws)
                    except Exception as e:
                        print(f"[ERROR] Failed to send message to player {player.get('username')}: {str(e)}")
                        # Remove failed connection
                        self.remove_connection(ws)
                else:
                    print(f"[INFO] Player {player.get('username')} has no live connection")
                    
            # Always persist broadcast in Redis for state recovery
            broadcast_key = f"broadcast:{room_code}:{int(time.time())}"
            redis_manager.redis.set(
                broadcast_key,
                json.dumps({
                    'type': msg_type,
                    'data': data,
                    'timestamp': time.time()
                }),
                ex=3600  # Expire after 1 hour
            )
                    
        except Exception as e:
            print(f"[ERROR] Failed to broadcast to room {room_code}: {str(e)}")
            
        # Log broadcast for debugging
        print(f"[DEBUG] Broadcast {msg_type} to room {room_code}")
        print(f"[DEBUG] Active connections: {len(self.live_connections)}")
            
    async def broadcast_game_state(self, room_code: str, game_state: Dict[str, Any], redis_manager: RedisManager):
        """Broadcast current game state to all live connections, persisting in Redis"""
        try:
            # 1. Save complete state to Redis first
            redis_manager.save_game_state(room_code, game_state)
            
            # 2. Send state updates to live connections
            players = redis_manager.get_room_players(room_code)
            teams = json.loads(game_state.get('teams', '{}'))
            
            for player in players:
                player_id = player.get('player_id')
                if not player_id:
                    continue
                
                # Only send to live connections
                ws = self.get_live_connection(player_id)
                if not ws:
                    continue
                    
                username = player.get('username')
                if not username:
                    continue
                    
                # Customize state for each player
                player_state = {
                    'type': 'game_state',
                    'phase': game_state.get('game_phase', 'unknown'),
                    'you': username,
                    'hand': json.loads(game_state.get(f'hand_{username}', '[]')),
                    'your_team': "1" if username in teams.get('1', []) else "2",
                    'hakem': game_state.get('hakem'),
                    'hokm': game_state.get('hokm'),
                    'current_turn': game_state.get('current_turn'),
                    'tricks': json.loads(game_state.get('tricks', '{}')),
                    'room_code': room_code,
                    'teams': teams
                }
                
                await self.send_message(ws, 'game_state', player_state)
                
            # Log successful broadcast
            print(f"[LOG] Game state broadcast to {len(self.live_connections)} live connection(s) in room {room_code}")
            
        except Exception as e:
            print(f"[ERROR] Failed to broadcast game state to room {room_code}: {str(e)}")
            # Log error details for debugging
            print(f"[DEBUG] Game state: {game_state}")
            
    @staticmethod
    async def notify_error(websocket, message: str):
        """Send an error message to a websocket"""
        await NetworkManager.send_message(
            websocket,
            'error',
            {'message': message}
        )

    @staticmethod
    async def notify_info(websocket, message: str):
        """Send an info message to a websocket"""
        await NetworkManager.send_message(
            websocket,
            'info',
            {'message': message}
        )

    async def handle_player_connected(self, websocket, room_code: str, player_data: Dict[str, Any], redis_manager: RedisManager):
        """Handle new player connection with improved session management"""
        try:
            player_id = player_data['player_id']
            username = player_data['username']
            
            # 1. Save session data in Redis
            session_data = {
                'username': username,
                'room_code': room_code,
                'connected_at': str(int(time.time())),
                'expires_at': str(int(time.time()) + 3600),
                'player_number': player_data.get('player_number', 0),
                'connection_status': 'active'
            }
            redis_manager.save_player_session(player_id, session_data)
            
            # 2. Register live connection
            self.register_connection(websocket, player_id, room_code)
            
            # 3. Add to room with all metadata
            room_data = {
                **player_data,
                'joined_at': str(int(time.time())),
                'connection_status': 'active'
            }
            redis_manager.add_player_to_room(room_code, room_data)
            
            # 4. Get existing game state if available
            game_state = redis_manager.get_game_state(room_code)
            join_response = {
                'username': username,
                'player_id': player_id,
                'room_code': room_code,
                'player_number': player_data.get('player_number', 0)
            }
            
            if game_state:
                join_response['game_state'] = game_state
            
            # 5. Send join confirmation
            await self.send_message(websocket, 'join_success', join_response)
            
            print(f"[LOG] Player {username} connected to room {room_code}")
            print(f"[DEBUG] Active connections: {len(self.live_connections)}")
            return True
            
        except Exception as e:
            print(f"[ERROR] Failed to handle player connection: {str(e)}")
            await self.notify_error(websocket, "Failed to join room")
            return False

    async def handle_player_disconnected(self, websocket, room_code: str, redis_manager: RedisManager):
        """Handle player disconnection with graceful connection cleanup"""
        try:
            # 1. Get player data from connection metadata
            if websocket not in self.connection_metadata:
                print("[ERROR] No metadata found for disconnected websocket")
                return False
                
            metadata = self.connection_metadata[websocket]
            player_id = metadata['player_id']
            
            print(f"[DEBUG] Starting disconnect handling for player_id: {player_id[:8]}... in room: {room_code}")
            
            # 2. Get player info from Redis
            session = redis_manager.get_player_session(player_id)
            if not session:
                print(f"[ERROR] No session found for player {player_id}")
                self.remove_connection(websocket)
                return False
                
            username = session.get('username')
            
            print(f"[DEBUG] Player {username} (ID: {player_id[:8]}...) disconnecting from room {room_code}")
            
            # DEBUG: Check room state before making any changes
            print(f"[DEBUG] Before disconnect processing:")
            redis_manager.debug_room_state(room_code)
            
            # 3. Update session in Redis
            disconnect_data = {
                'disconnected_at': str(int(time.time())),
                'room_code': room_code,
                'connection_status': 'disconnected',
                # Keep session alive for reconnection
                'expires_at': str(int(time.time()) + 3600)
            }
            redis_manager.save_player_session(player_id, disconnect_data)
            
            # 4. Update room player data to mark as disconnected
            room_players = redis_manager.get_room_players(room_code)
            print(f"[DEBUG] Room {room_code} currently has {len(room_players)} players:")
            for i, player in enumerate(room_players):
                print(f"[DEBUG]   Player {i+1}: {player.get('username', 'NO_NAME')} (ID: {player.get('player_id', 'NO_ID')[:8]}...) - Status: {player.get('connection_status', 'NO_STATUS')}")
            
            player_found = False
            for i, player in enumerate(room_players):
                if player.get('player_id') == player_id:
                    room_players[i]['connection_status'] = 'disconnected'
                    room_players[i]['disconnected_at'] = str(int(time.time()))
                    # Update the room player list
                    update_result = redis_manager.update_player_in_room(room_code, player_id, room_players[i])
                    print(f"[DEBUG] Updated player {username} status to disconnected. Update result: {update_result}")
                    player_found = True
                    break
            
            if not player_found:
                print(f"[ERROR] Player {player_id[:8]}... not found in room {room_code} players list!")
                
            # 5. Remove live connection
            self.remove_connection(websocket)
            
            # 6. Save game state if in active game
            game_state = redis_manager.get_game_state(room_code)
            if game_state:
                game_state['last_activity'] = str(int(time.time()))
                redis_manager.save_game_state(room_code, game_state)
                print(f"[DEBUG] Updated game state for room {room_code}")
            else:
                print(f"[DEBUG] No game state found for room {room_code}")
            
            print(f"[LOG] Player {username} disconnected from room {room_code}")
            print(f"[DEBUG] Remaining connections: {len(self.live_connections)}")
            
            # 7. Notify other players with remaining connection count
            await self.broadcast_to_room(
                room_code,
                'player_disconnected',
                {
                    'username': username,
                    'temporary': True,  # Allow reconnection
                    'active_players': len(self.live_connections)
                },
                redis_manager
            )
            
            # 8. Final verification - check if player is still in room
            updated_room_players = redis_manager.get_room_players(room_code)
            print(f"[DEBUG] After disconnect handling, room {room_code} has {len(updated_room_players)} players:")
            for i, player in enumerate(updated_room_players):
                print(f"[DEBUG]   Player {i+1}: {player.get('username', 'NO_NAME')} (ID: {player.get('player_id', 'NO_ID')[:8]}...) - Status: {player.get('connection_status', 'NO_STATUS')}")
            
            return True
        except Exception as e:
            print(f"[ERROR] Failed to handle player disconnection: {str(e)}")
            # Clean up connection anyway
            self.remove_connection(websocket)
            return False
    async def handle_player_reconnected(self, websocket, player_id: str, redis_manager: RedisManager):
        """Handle player reconnection with state recovery"""
        try:
            # 1. Validate and get session
            is_valid, session = redis_manager.attempt_reconnect(player_id, {
                'reconnected_at': str(int(time.time())),
                'connection_status': 'active'
            })
            
            if not is_valid:
                error_msg = session.get('error', 'Failed to reconnect')
                print(f"[DEBUG] Reconnection failed for {player_id[:8]}...: {error_msg}")
                await self.notify_error(websocket, error_msg)
                return False
                
            room_code = session.get('room_code')
            username = session.get('username')
            
            if not room_code or not username:
                await self.notify_error(websocket, "Invalid session data")
                return False
            
            # Additional validation: Check if player is actually in the room and disconnected
            room_players = redis_manager.get_room_players(room_code)
            player_in_room = None
            
            print(f"[DEBUG] Reconnection validation for player_id: {player_id}")
            
            # Debug room state
            redis_manager.debug_room_state(room_code)
            
            print(f"[DEBUG] Room {room_code} has {len(room_players)} players:")
            for i, player in enumerate(room_players):
                print(f"[DEBUG]   Player {i+1}: {player.get('player_id', 'NO_ID')[:8]}... ({player.get('username', 'NO_NAME')}) - {player.get('connection_status', 'NO_STATUS')}")
                if player.get('player_id') == player_id:
                    player_in_room = player
                    break
            
            if not player_in_room:
                print(f"[DEBUG] Player {player_id[:8]}... not found in room {room_code}")
                
                # Check if room exists at all
                if not redis_manager.room_exists(room_code):
                    await self.notify_error(websocket, "Game room no longer exists. The game may have ended or been cancelled.")
                    return False
                
                # Check if there's an active game but player is not in it
                game_state = redis_manager.get_game_state(room_code)
                if game_state:
                    await self.notify_error(websocket, "Game is active but your player slot is no longer available. The game may have been restarted.")
                else:
                    await self.notify_error(websocket, "No active game found. Please join a new game.")
                return False
            
            if player_in_room.get('connection_status') == 'active':
                await self.notify_error(websocket, "Player is already connected")
                return False
            
            # 2. Register new connection
            self.register_connection(websocket, player_id, room_code)
            
            # 3. Get current game state
            game_state = redis_manager.get_game_state(room_code)
            if not game_state:
                game_state = {}
            
            # 4. Send reconnection success with full state
            # Handle JSON parsing safely - data might already be parsed from Redis
            teams_data = game_state.get('teams', '{}')
            if isinstance(teams_data, str):
                teams = json.loads(teams_data)
            else:
                teams = teams_data
                
            hand_data = game_state.get(f'hand_{username}', '[]')
            if isinstance(hand_data, str):
                hand = json.loads(hand_data)
            else:
                hand = hand_data
                
            print(f"[DEBUG] Reconnection: Player {username} hand has {len(hand)} cards from Redis")
                
            tricks_data = game_state.get('tricks', '{}')
            if isinstance(tricks_data, str):
                tricks = json.loads(tricks_data)
            else:
                tricks = tricks_data
                
            restored_state = {
                'username': username,
                'room_code': room_code,
                'player_id': player_id,
                'game_state': {
                    'phase': game_state.get('phase', game_state.get('game_phase', 'waiting')),  # Try both 'phase' and 'game_phase'
                    'teams': teams,
                    'hakem': game_state.get('hakem'),
                    'hokm': game_state.get('hokm'),
                    'hand': hand,
                    'current_turn': int(game_state.get('current_turn', 0)),
                    'tricks': tricks,
                    'you': username,
                    'your_team': "1" if username in teams.get('1', []) else "2"
                }
            }
            
            await self.send_message(websocket, 'reconnect_success', restored_state)
            
            print(f"[LOG] Player {username} reconnected to room {room_code}")
            print(f"[DEBUG] Active connections: {len(self.live_connections)}")
            
            # 5. Check if reconnected player is hakem and needs to choose hokm
            current_phase = game_state.get('phase', game_state.get('game_phase', 'waiting'))
            current_hakem = game_state.get('hakem')
            current_hokm = game_state.get('hokm', '')
            
            if (current_phase == 'hokm_selection' and 
                current_hakem == username and 
                not current_hokm):
                print(f"[LOG] Reconnected hakem {username} needs to choose hokm")
                await self.send_message(websocket, 'hokm_request', {
                    'message': 'You are the Hakem. Choose hokm (hearts, diamonds, clubs, spades).',
                    'hand': hand
                })
            elif current_phase == 'gameplay':
                # Player reconnected during gameplay - send current turn info
                print(f"[LOG] Player {username} reconnected during gameplay")
                current_turn = int(game_state.get('current_turn', 0))
                players = json.loads(game_state.get('players', '[]')) if isinstance(game_state.get('players'), str) else game_state.get('players', [])
                
                if players and current_turn < len(players):
                    current_player = players[current_turn]
                    await self.send_message(websocket, 'turn_start', {
                        'current_player': current_player,
                        'your_turn': username == current_player,
                        'hand': hand,
                        'hokm': current_hokm,
                        'message': f'Game in progress. {current_player}\'s turn.'
                    })
            elif current_phase in ['final_deal']:
                # Player reconnected during final deal phase - send their full hand
                print(f"[LOG] Player {username} reconnected during final deal")
                await self.send_message(websocket, 'final_deal', {
                    'hand': hand,
                    'hokm': current_hokm,
                    'message': f'Final deal completed. You have {len(hand)} cards.'
                })
            
            # 6. Notify other players
            await self.broadcast_to_room(
                room_code,
                'player_reconnected',
                {
                    'username': username,
                    'active_players': len(self.live_connections)
                },
                redis_manager
            )
            
            return True
            
        except Exception as e:
            print(f"[ERROR] Failed to handle player reconnection: {str(e)}")
            await self.notify_error(websocket, "Failed to reconnect")
            return False

    @staticmethod
    async def receive_message(websocket) -> Optional[Dict[str, Any]]:
        """Receive and parse a JSON message from websocket"""
        try:
            message = await websocket.recv()
            return json.loads(message)
        except websockets.ConnectionClosed:
            print("[ERROR] Connection closed while receiving message")
            return None
        except json.JSONDecodeError:
            print("[ERROR] Invalid JSON received")
            return None
