# server.py

import asyncio
import sys
import websockets
import json
import uuid
import random
import time
import os
import concurrent.futures
import traceback

# Add current directory to Python path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from network import NetworkManager
from game_board import GameBoard
from game_states import GameState
from redis_manager_resilient import ResilientRedisManager as RedisManager
from circuit_breaker_monitor import CircuitBreakerMonitor
from game_auth_manager import GameAuthManager

# Constants
ROOM_SIZE = 4    # Single game storage system

class GameServer:
    def __init__(self):
        self.redis_manager = RedisManager()
        self.circuit_breaker_monitor = CircuitBreakerMonitor(self.redis_manager)
        self.network_manager = NetworkManager()
        self.auth_manager = GameAuthManager()  # Add authentication manager
        self.active_games = {}  # Maps room_code -> GameBoard for active games only
        self.load_active_games_from_redis()  # Load active games on startup

    def load_active_games_from_redis(self):
        """Load all active games from Redis into self.active_games on server startup."""
        print("[LOG] Starting fresh - no Redis game loading for faster startup")
        return  # Bypass Redis loading to avoid startup hang

    async def handle_join(self, websocket, data):
        """Handle a new player joining with separated connection and state management"""
        print(f"[DEBUG] handle_join called with data: {data}")
        try:
            room_code = data.get('room_code', '9999')
            print(f"[DEBUG] Room code: {room_code}")
            
            print(f"[DEBUG] About to check if room exists...")
            # Check if room exists properly
            try:
                executor = concurrent.futures.ThreadPoolExecutor()
                loop = asyncio.get_event_loop()
                room_exists = await asyncio.wait_for(
                    loop.run_in_executor(executor, self.redis_manager.room_exists, room_code),
                    timeout=2.0
                )
                print(f"[DEBUG] Room exists check result: {room_exists}")
            except Exception as e:
                print(f"[DEBUG] Room check failed: {e}, assuming new room")
                room_exists = False
            print(f"[DEBUG] Room exists check result: {room_exists}")
            if not room_exists:
                print(f"[DEBUG] Room {room_code} doesn't exist, creating it")
                try:
                    # Add timeout to Redis operations
                    executor = concurrent.futures.ThreadPoolExecutor()
                    loop = asyncio.get_event_loop()
                    await asyncio.wait_for(
                        loop.run_in_executor(executor, self.redis_manager.create_room, room_code),
                        timeout=2.0
                    )
                    print(f"[LOG] Room {room_code} created successfully")
                except asyncio.TimeoutError:
                    print(f"[DEBUG] Redis timeout when creating room, continuing anyway")
                except Exception as e:
                    print(f"[ERROR] Failed to create room {room_code}: {str(e)}")
                    # Continue anyway - room creation is not critical for basic functionality
            else:
                print(f"[DEBUG] Room {room_code} already exists")

            # Check if game is cancelled due to not enough players (after a disconnect)
            # BUT: Don't cancel if this is a reconnection request - give it a chance to complete
            print(f"[DEBUG] Checking for existing game in room {room_code}")
            game = self.active_games.get(room_code)
            print(f"[DEBUG] Existing game found: {game is not None}")
            if game:
                print(f"[DEBUG] Getting game phase...")
                phase = getattr(game, 'game_phase', None)
                print(f"[DEBUG] Game phase: {phase}")
                print(f"[DEBUG] Getting room players...")
                # connected_players = [p for p in self.redis_manager.get_room_players(room_code) if p.get('connection_status') == 'active']
                # Temporarily bypass this Redis call that might be hanging
                connected_players = []
                print(f"[DEBUG] Connected players: {len(connected_players)}")
                
                # Only cancel if:
                # 1. Not enough active players AND
                # 2. This is a NEW join (not a reconnection attempt) AND  
                # 3. We're in a critical phase where we need all players
                is_critical_phase = (
                    phase == GameState.TEAM_ASSIGNMENT.value or
                    (hasattr(GameState, 'WAITING_FOR_HOKM') and phase == GameState.WAITING_FOR_HOKM.value) or
                    (phase == 'waiting_for_hokm')
                )
                
                if len(connected_players) < ROOM_SIZE and is_critical_phase:
                    # Check if this might be a reconnection by looking for disconnected players
                    disconnected_players = [p for p in self.redis_manager.get_room_players(room_code) if p.get('connection_status') != 'active']
                    
                    # If there are disconnected players, give them a chance to reconnect
                    # Only cancel if no disconnected players exist (meaning players truly left)
                    if not disconnected_players:
                        print(f"[LOG] Not enough players in room {room_code} during join (phase: {phase}). No disconnected players to reconnect. Cancelling game.")
                        await self.network_manager.notify_error(websocket, "Game was cancelled due to player disconnect.")
                        await self.network_manager.broadcast_to_room(
                            room_code,
                            'game_cancelled',
                            {'message': 'A player disconnected and not enough players remain. The game has been cancelled.'},
                            self.redis_manager
                        )
                        if room_code in self.active_games:
                            del self.active_games[room_code]
                        
                        # Delete game state with timeout to avoid hanging
                        try:
                            executor = concurrent.futures.ThreadPoolExecutor()
                            loop = asyncio.get_event_loop()
                            await asyncio.wait_for(
                                loop.run_in_executor(executor, self.redis_manager.delete_game_state, room_code),
                                timeout=2.0
                            )
                            print(f"[DEBUG] Deleted game state for room {room_code}")
                        except asyncio.TimeoutError:
                            print(f"[DEBUG] Redis timeout when deleting game state, continuing anyway")
                        except Exception as e:
                            print(f"[DEBUG] Could not delete game state: {e}, continuing anyway")
                        
                        return None
                    else:
                        print(f"[LOG] Room {room_code} has disconnected players who might reconnect. Not cancelling game yet.")

            # Check if room is full (count only active players for new joins)
            print(f"[DEBUG] Getting room players...")
            
            # SIMPLIFIED: Use only network manager connections for now to avoid Redis hangs
            room_players = []
            for ws, metadata in self.network_manager.connection_metadata.items():
                if metadata.get('room_code') == room_code:
                    room_players.append({
                        'player_id': metadata.get('player_id'),
                        'username': f"Player {len(room_players) + 1}",
                        'connection_status': 'active'
                    })
            print(f"[DEBUG] Room players from network manager: {len(room_players)}")
            active_players = [p for p in room_players if p.get('connection_status') == 'active']
            print(f"[DEBUG] Active players: {len(active_players)}")
            
            # For regular join requests, don't automatically reconnect to disconnected slots
            # Only allow reconnection through explicit "reconnect" messages
            
            # If room has space for new players, assign a new slot
            if len(room_players) < ROOM_SIZE:
                # Assign new player slot
                pass  # Continue to create new player below
            else:
                # Room is full - reject new join requests
                await self.network_manager.notify_error(websocket, "Room is full")
                return None

            # Get authenticated player info
            player_info = self.auth_manager.get_authenticated_player(websocket)
            if not player_info:
                await self.network_manager.notify_error(websocket, "Authentication required")
                return None
            
            # Use authenticated player information
            player_id = player_info['player_id']
            username = player_info['username']
            display_name = player_info['display_name']
            
            # Count current players in this room to assign correct player number
            current_room_count = 0
            for ws, metadata in self.network_manager.connection_metadata.items():
                if metadata.get('room_code') == room_code:
                    current_room_count += 1
            player_number = current_room_count + 1  # This player will be the next number

            # Save session data to Redis
            session_data = {
                'username': username,
                'display_name': display_name,
                'player_id': player_id,
                'room_code': room_code,
                'connected_at': str(int(time.time())),
                'expires_at': str(int(time.time()) + 3600),
                'player_number': player_number,
                'connection_status': 'active',
                'rating': player_info.get('rating', 1000)
            }
            try:
                executor = concurrent.futures.ThreadPoolExecutor()
                loop = asyncio.get_event_loop()
                await asyncio.wait_for(
                    loop.run_in_executor(executor, self.redis_manager.save_player_session, player_id, session_data),
                    timeout=2.0
                )
                print(f"[DEBUG] Saved session data for {username}")
            except asyncio.TimeoutError:
                print(f"[DEBUG] Redis timeout when saving session, continuing anyway")
            except Exception as e:
                print(f"[DEBUG] Could not save session data: {e}, continuing anyway")

            # Register live connection
            self.network_manager.register_connection(websocket, player_id, room_code, username)
            
            # Debug: check connection count immediately after registration
            debug_count = 0
            for ws, metadata in self.network_manager.connection_metadata.items():
                if metadata.get('room_code') == room_code:
                    debug_count += 1
            print(f"[DEBUG] Connections for room {room_code} after registration: {debug_count}")

            # Add to room
            room_data = {
                'player_id': player_id,
                'username': username,
                'player_number': player_number,
                'joined_at': str(int(time.time())),
                'connection_status': 'active'
            }
            try:
                executor = concurrent.futures.ThreadPoolExecutor()
                loop = asyncio.get_event_loop()
                await asyncio.wait_for(
                    loop.run_in_executor(executor, self.redis_manager.add_player_to_room, room_code, room_data),
                    timeout=2.0
                )
                print(f"[DEBUG] Added {username} to room {room_code}")
            except asyncio.TimeoutError:
                print(f"[DEBUG] Redis timeout when adding to room, continuing anyway")
            except Exception as e:
                print(f"[DEBUG] Could not add to room: {e}, continuing anyway")

            # Get updated player count after adding this player
            # Use simple counting based on network manager connections
            current_player_count = 0
            for ws, metadata in self.network_manager.connection_metadata.items():
                if metadata.get('room_code') == room_code:
                    current_player_count += 1
            
            print(f"[DEBUG] Updated player count: {current_player_count}")

            # Send join confirmation
            print(f"[LOG] Room {room_code}: {username} joined [PHASE: {GameState.WAITING_FOR_PLAYERS.value}] - Players: {current_player_count}/4")
            await self.network_manager.send_message(
                websocket,
                'join_success',
                {
                    'username': username,
                    'player_id': player_id,
                    'room_code': room_code,
                    'player_number': player_number
                }
            )

            # Start game if room is full
            if current_player_count >= ROOM_SIZE:
                print(f"[LOG] Room {room_code} is full, ready to play! [PHASE: {GameState.TEAM_ASSIGNMENT.value}]")
                # Add a small delay to ensure all connections are registered
                await asyncio.sleep(0.5)
                await self.handle_game_start(room_code)

            return True

        except Exception as e:
            print(f"[ERROR] Failed to handle join: {str(e)}")
            import traceback
            traceback.print_exc()
            await self.network_manager.notify_error(websocket, "Failed to join room")
            return False

    async def handle_game_start(self, room_code: str):
        """Initialize and start a new game"""
        try:
            # Check if game is already in progress to prevent duplicate initialization
            if room_code in self.active_games:
                existing_game = self.active_games[room_code]
                # Only restart if the game is in waiting_for_players phase
                if existing_game.game_phase != GameState.WAITING_FOR_PLAYERS.value:
                    print(f"[LOG] Game already in progress in room {room_code} (phase: {existing_game.game_phase}), skipping initialization")
                    return
            
            # Get all players in room with timeout and fallback
            print(f"[DEBUG] Getting players for room {room_code} to start game")
            executor = concurrent.futures.ThreadPoolExecutor()
            loop = asyncio.get_event_loop()
            
            try:
                room_players_data = await asyncio.wait_for(
                    loop.run_in_executor(executor, self.redis_manager.get_room_players, room_code),
                    timeout=2.0
                )
                players = [p['username'] for p in room_players_data]
                print(f"[DEBUG] Got players from Redis: {players}")
            except asyncio.TimeoutError:
                print(f"[DEBUG] Redis timeout when getting room players, using network manager fallback")
                # Fallback: get players from network manager connections
                players = []
                for ws, metadata in self.network_manager.connection_metadata.items():
                    if metadata.get('room_code') == room_code:
                        username = metadata.get('username', f'Player{len(players)+1}')
                        players.append(username)
                
                if len(players) >= ROOM_SIZE:
                    print(f"[DEBUG] Using fallback players from network manager: {players}")
                else:
                    print(f"[ERROR] Not enough connected players for fallback: {len(players)}")
                    return
            except Exception as e:
                print(f"[ERROR] Could not get room players: {e}")
                return
            
            # Ensure we have exactly 4 players
            if len(players) != 4:
                print(f"[ERROR] Invalid player count: {len(players)}, expected 4 players")
                return
            
            # Create new game instance
            game = GameBoard(players, room_code)
            self.active_games[room_code] = game
            
            # Assign teams and get initial state
            team_result = game.assign_teams_and_hakem(self.redis_manager)
            
            # Save initial game state with timeout
            try:
                game_state = game.to_redis_dict()
                await asyncio.wait_for(
                    loop.run_in_executor(executor, self.redis_manager.save_game_state, room_code, game_state),
                    timeout=2.0
                )
                print(f"[DEBUG] Saved initial game state to Redis")
            except asyncio.TimeoutError:
                print(f"[DEBUG] Redis timeout when saving initial game state, continuing anyway")
            except Exception as e:
                print(f"[DEBUG] Could not save initial game state: {e}, continuing anyway")
            
            # Broadcast phase change to TEAM_ASSIGNMENT with timeout protection
            print(f"[DEBUG] Broadcasting TEAM_ASSIGNMENT phase change...")
            try:
                await asyncio.wait_for(
                    self.network_manager.broadcast_to_room(
                        room_code,
                        'phase_change',
                        {'new_phase': GameState.TEAM_ASSIGNMENT.value},
                        self.redis_manager
                    ),
                    timeout=3.0
                )
                print(f"[DEBUG] TEAM_ASSIGNMENT phase change broadcasted")
            except asyncio.TimeoutError:
                print(f"[DEBUG] Timeout broadcasting TEAM_ASSIGNMENT phase change, trying direct network broadcast")
                # Fallback: broadcast directly to network connections
                for ws, metadata in self.network_manager.connection_metadata.items():
                    if metadata.get('room_code') == room_code:
                        try:
                            await self.network_manager.send_message(
                                ws,
                                'phase_change',
                                {'new_phase': GameState.TEAM_ASSIGNMENT.value}
                            )
                        except Exception as e:
                            print(f"[DEBUG] Failed to send phase change to individual connection: {e}")
            except Exception as e:
                print(f"[DEBUG] Error broadcasting TEAM_ASSIGNMENT phase change: {e}")
            
            # Broadcast team assignments with timeout protection
            print(f"[DEBUG] Broadcasting team assignments...")
            try:
                await asyncio.wait_for(
                    self.network_manager.broadcast_to_room(
                        room_code,
                        'team_assignment',
                        team_result,
                        self.redis_manager
                    ),
                    timeout=3.0
                )
                print(f"[DEBUG] Team assignments broadcasted")
            except asyncio.TimeoutError:
                print(f"[DEBUG] Timeout broadcasting team assignments, trying direct network broadcast")
                # Fallback: broadcast directly to network connections
                for ws, metadata in self.network_manager.connection_metadata.items():
                    if metadata.get('room_code') == room_code:
                        try:
                            await self.network_manager.send_message(
                                ws,
                                'team_assignment',
                                team_result
                            )
                        except Exception as e:
                            print(f"[DEBUG] Failed to send team assignment to individual connection: {e}")
            except Exception as e:
                print(f"[DEBUG] Error broadcasting team assignments: {e}")
            
            # Deal initial cards
            print(f"[DEBUG] Dealing initial cards...")
            initial_hands = game.initial_deal()
            print(f"[DEBUG] Initial cards dealt, hands: {len(initial_hands)}")
            
            # Transition to waiting for hokm phase
            game.game_phase = GameState.WAITING_FOR_HOKM.value
            print(f"[DEBUG] Game phase set to WAITING_FOR_HOKM")
            
            # Save game state with timeout
            try:
                game_state = game.to_redis_dict()
                await asyncio.wait_for(
                    loop.run_in_executor(executor, self.redis_manager.save_game_state, room_code, game_state),
                    timeout=2.0
                )
                print(f"[DEBUG] Saved WAITING_FOR_HOKM game state to Redis")
            except asyncio.TimeoutError:
                print(f"[DEBUG] Redis timeout when saving WAITING_FOR_HOKM state, continuing anyway")
            except Exception as e:
                print(f"[DEBUG] Could not save WAITING_FOR_HOKM state: {e}, continuing anyway")
            
            # Broadcast phase change to WAITING_FOR_HOKM - CRITICAL for hokm selection
            print(f"[LOG] Broadcasting phase change to WAITING_FOR_HOKM in room {room_code}")
            try:
                await asyncio.wait_for(
                    self.network_manager.broadcast_to_room(
                        room_code,
                        'phase_change',
                        {'new_phase': GameState.WAITING_FOR_HOKM.value},
                        self.redis_manager
                    ),
                    timeout=3.0
                )
                print(f"[DEBUG] WAITING_FOR_HOKM phase change broadcasted")
            except asyncio.TimeoutError:
                print(f"[DEBUG] Timeout broadcasting WAITING_FOR_HOKM phase change, trying direct network broadcast")
                # Fallback: broadcast directly to network connections
                for ws, metadata in self.network_manager.connection_metadata.items():
                    if metadata.get('room_code') == room_code:
                        try:
                            await self.network_manager.send_message(
                                ws,
                                'phase_change',
                                {'new_phase': GameState.WAITING_FOR_HOKM.value}
                            )
                        except Exception as e:
                            print(f"[DEBUG] Failed to send phase change to individual connection: {e}")
            except Exception as e:
                print(f"[DEBUG] Error broadcasting WAITING_FOR_HOKM phase change: {e}")
            
            # Send initial hands to players
            print(f"[DEBUG] About to send initial hands to players...")
            try:
                room_players_for_hands = await asyncio.wait_for(
                    loop.run_in_executor(executor, self.redis_manager.get_room_players, room_code),
                    timeout=2.0
                )
                print(f"[DEBUG] Got room players for sending hands: {len(room_players_for_hands)}")
            except asyncio.TimeoutError:
                print(f"[DEBUG] Redis timeout when getting room players for hands, using connected players")
                # Fallback: use network manager to get connections
                room_players_for_hands = []
                for ws, metadata in self.network_manager.connection_metadata.items():
                    if metadata.get('room_code') == room_code:
                        room_players_for_hands.append({
                            'username': metadata.get('username', f'Player{len(room_players_for_hands)+1}'),
                            'player_id': metadata.get('player_id')
                        })
                        if len(room_players_for_hands) >= len(players):
                            break
            except Exception as e:
                print(f"[DEBUG] Could not get room players for hands: {e}, using basic fallback")
                room_players_for_hands = [{'username': name, 'player_id': f'fallback_{i}'} for i, name in enumerate(players)]
            
            print(f"[DEBUG] Got room players for hands, starting to send messages...")
            for i, player in enumerate(room_players_for_hands):
                print(f"[DEBUG] Sending hand to player {i+1}: {player.get('username', 'unknown')}")
                ws = self.network_manager.get_live_connection(player['player_id'])
                if ws:
                    print(f"[DEBUG] Found live connection for player {player.get('username')}")
                    await self.network_manager.send_message(
                        ws,
                        'initial_deal',
                        {
                            'hand': initial_hands[player['username']],
                            'is_hakem': player['username'] == game.hakem,
                            'hakem': game.hakem,
                            'message': "You are the Hakem. Choose hokm." if player['username'] == game.hakem else f"Waiting for {game.hakem} to choose hokm."
                        }
                    )
                    print(f"[DEBUG] Sent initial hand to {player.get('username')}")
                else:
                    print(f"[DEBUG] No live connection found for player {player.get('username')}")
            
            print(f"[LOG] Game started in room {room_code}")
            
        except Exception as e:
            print(f"[ERROR] Failed to start game in room {room_code}: {str(e)}")
            # Notify all players in the room of the error
            try:
                await self.network_manager.broadcast_to_room(
                    room_code,
                    'error',
                    {'message': f'Failed to start game: {str(e)}'},
                    self.redis_manager
                )
            except Exception as notify_err:
                print(f"[ERROR] Failed to notify users of game start error: {notify_err}")

    async def handle_connection_closed(self, websocket):
        """Handle WebSocket connection closure"""
        try:
            # Clean up authentication
            self.auth_manager.disconnect_player(websocket)
            
            # Check if websocket exists in connection metadata
            if websocket not in self.network_manager.connection_metadata:
                print(f"[LOG] Connection closed but websocket not in metadata: {websocket.remote_address}")
                return
                
            metadata = self.network_manager.connection_metadata[websocket]
            room_code = metadata.get('room_code')
            player_id = metadata.get('player_id')
            
            print(f"[LOG] Handling connection closed for player {player_id} in room {room_code}")
            
            if room_code:
                # First, handle the disconnection properly through network manager
                await self.network_manager.handle_player_disconnected(
                    websocket,
                    room_code,
                    self.redis_manager
                )
                
                # Then, check if game should be cancelled (but only after disconnection is processed)
                # Give a small delay to ensure disconnection processing is complete
                await asyncio.sleep(0.1)
                
                # Check if game is in TEAM_ASSIGNMENT or hokm selection phase and not enough live connections in this room
                game = self.active_games.get(room_code)
                if game:
                    phase = getattr(game, 'game_phase', None)
                    
                    # Count ACTUAL room players who are still active (not just network connections)
                    room_players = self.redis_manager.get_room_players(room_code)
                    active_players = [p for p in room_players if p.get('connection_status') == 'active']
                    active_count = len(active_players)
                    
                    print(f"[LOG] Room {room_code} has {active_count} active players after disconnect (phase: {phase})")
                    
                    # Be more conservative about cancelling games during critical phases
                    # Give players time to reconnect before cancelling
                    if active_count < ROOM_SIZE and phase in (
                        GameState.TEAM_ASSIGNMENT.value,
                        GameState.WAITING_FOR_HOKM.value
                    ):
                        # Check if there are disconnected players who might reconnect
                        disconnected_players = [p for p in room_players if p.get('connection_status') != 'active']
                        
                        # Only cancel if there are no disconnected players (meaning players permanently left)
                        # If there are disconnected players, they might reconnect soon
                        if not disconnected_players:
                            print(f"[LOG] Not enough active players ({active_count}/{ROOM_SIZE}) during {phase} in room {room_code}. No disconnected players to reconnect. Cancelling game.")
                            await self.network_manager.broadcast_to_room(
                                room_code,
                                'game_cancelled',
                                {'message': 'A player disconnected and not enough players remain. The game has been cancelled.'},
                                self.redis_manager
                            )
                            # Clean up game
                            self.active_games.pop(room_code, None)
                        else:
                            print(f"[LOG] Not enough active players ({active_count}/{ROOM_SIZE}) in room {room_code}, but {len(disconnected_players)} disconnected players might reconnect. Keeping game alive.")
                
            # Note: connection metadata is already cleaned up by network manager
                
        except Exception as e:
            print(f"[ERROR] Error handling connection closed: {str(e)}")
            import traceback
            traceback.print_exc()
            # Try to clean up metadata anyway
            try:
                if websocket in self.network_manager.connection_metadata:
                    del self.network_manager.connection_metadata[websocket]
            except Exception:
                pass
        except Exception as e:
            print(f"[ERROR] Error handling connection closure: {str(e)}")

    async def handle_message(self, websocket, message):
        """Handle incoming WebSocket messages"""
        print(f"[DEBUG] Received message: {message}")
        try:
            if not isinstance(message, dict):
                print(f"[DEBUG] Message is not dict: {type(message)}")
                await self.network_manager.notify_error(websocket, "Malformed message: not a JSON object.")
                return
            msg_type = message.get('type')
            print(f"[DEBUG] Message type: {msg_type}")
            if not msg_type:
                await self.network_manager.notify_error(websocket, "Malformed message: missing 'type' field.")
                return
            
            # Handle authentication messages first (Phase 0)
            if msg_type in ['auth_login', 'auth_register', 'auth_token']:
                await self.handle_authentication(websocket, message)
                return
            
            # Check authentication for all other messages
            if not self.auth_manager.is_authenticated(websocket):
                await self.network_manager.notify_error(websocket, "Authentication required. Please authenticate first.")
                return
            
            if msg_type == 'join':
                print(f"[DEBUG] Handling join message")
                # Validate required fields for join
                if 'room_code' not in message:
                    await self.network_manager.notify_error(websocket, "Malformed join message: missing 'room_code'.")
                    return
                await self.handle_join(websocket, message)
            elif msg_type == 'reconnect':
                if 'player_id' not in message:
                    await self.network_manager.notify_error(websocket, "Malformed reconnect message: missing 'player_id'.")
                    return
                player_id = message.get('player_id')
                print(f"[LOG] Reconnection attempt for player_id: {player_id[:8]}...")
                # The network manager handles the full reconnection process
                success = await self.network_manager.handle_player_reconnected(
                    websocket,
                    player_id,
                    self.redis_manager
                )
                if not success:
                    print(f"[LOG] Reconnection failed for player_id: {player_id[:8]}..., falling back to join")
                else:
                    print(f"[LOG] Reconnection successful for player_id: {player_id[:8]}...")
            elif msg_type == 'hokm_selected':
                if 'room_code' not in message or 'suit' not in message:
                    await self.network_manager.notify_error(websocket, "Malformed hokm_selected message: missing 'room_code' or 'suit'.")
                    return
                await self.handle_hokm_selection(websocket, message)
            elif msg_type == 'play_card':
                if 'room_code' not in message or 'player_id' not in message or 'card' not in message:
                    await self.network_manager.notify_error(websocket, "Malformed play_card message: missing 'room_code', 'player_id', or 'card'.")
                    return
                await self.handle_play_card(websocket, message)
            elif msg_type == 'clear_room':
                await self.handle_clear_room(websocket, message)
                return
            elif msg_type == 'health_check':
                await self.handle_health_check(websocket, message)
                return
            else:
                print(f"[WARNING] Unknown message type: {msg_type}")
                await self.network_manager.notify_error(websocket, f"Unknown message type: {msg_type}")
        except Exception as e:
            print(f"[ERROR] Failed to handle message: {str(e)}")
            try:
                await self.network_manager.notify_error(websocket, f"Internal server error: {str(e)}")
            except Exception as notify_err:
                print(f"[ERROR] Failed to notify user of message error: {notify_err}")

    async def handle_authentication(self, websocket, message):
        """Handle authentication messages (Phase 0)"""
        print(f"[DEBUG] Handling authentication message: {message.get('type')}")
        
        try:
            msg_type = message.get('type')
            
            if msg_type == 'auth_login':
                # Handle username/password login
                username = message.get('username')
                password = message.get('password')
                
                if not username or not password:
                    await websocket.send(json.dumps({
                        'type': 'auth_response',
                        'success': False,
                        'message': 'Username and password are required'
                    }))
                    return
                
                auth_data = {
                    'type': 'login',
                    'username': username,
                    'password': password
                }
                
                result = await self.auth_manager.authenticate_player(websocket, auth_data)
                
                response = {
                    'type': 'auth_response',
                    'success': result['success'],
                    'message': result['message']
                }
                
                if result['success']:
                    response['player_info'] = result['player_info']
                    print(f"[LOG] Player authenticated: {username} (ID: {result['player_info']['player_id'][:8]}...)")
                
                await websocket.send(json.dumps(response))
                
            elif msg_type == 'auth_register':
                # Handle user registration
                username = message.get('username')
                password = message.get('password')
                email = message.get('email')
                display_name = message.get('display_name')
                
                if not username or not password:
                    await websocket.send(json.dumps({
                        'type': 'auth_response',
                        'success': False,
                        'message': 'Username and password are required'
                    }))
                    return
                
                auth_data = {
                    'type': 'register',
                    'username': username,
                    'password': password,
                    'email': email,
                    'display_name': display_name
                }
                
                result = await self.auth_manager.authenticate_player(websocket, auth_data)
                
                response = {
                    'type': 'auth_response',
                    'success': result['success'],
                    'message': result['message']
                }
                
                if result['success']:
                    response['player_info'] = result['player_info']
                    print(f"[LOG] Player registered and authenticated: {username} (ID: {result['player_info']['player_id'][:8]}...)")
                
                await websocket.send(json.dumps(response))
                
            elif msg_type == 'auth_token':
                # Handle JWT token authentication
                token = message.get('token')
                
                if not token:
                    await websocket.send(json.dumps({
                        'type': 'auth_response',
                        'success': False,
                        'message': 'Token is required'
                    }))
                    return
                
                auth_data = {
                    'type': 'token',
                    'token': token
                }
                
                result = await self.auth_manager.authenticate_player(websocket, auth_data)
                
                response = {
                    'type': 'auth_response',
                    'success': result['success'],
                    'message': result['message']
                }
                
                if result['success']:
                    response['player_info'] = result['player_info']
                    print(f"[LOG] Player authenticated via token: {result['player_info']['username']} (ID: {result['player_info']['player_id'][:8]}...)")
                
                await websocket.send(json.dumps(response))
                
        except Exception as e:
            print(f"[ERROR] Authentication error: {str(e)}")
            await websocket.send(json.dumps({
                'type': 'auth_response',
                'success': False,
                'message': f'Authentication failed: {str(e)}'
            }))

    async def handle_hokm_selection(self, websocket, message):
        """Handle hokm selection by the Hakem, save state, broadcast, and deal remaining cards."""
        try:
            # Create executor and loop for timeout operations
            executor = concurrent.futures.ThreadPoolExecutor()
            loop = asyncio.get_event_loop()
            
            room_code = message.get('room_code')
            suit = message.get('suit')
            if not room_code or not suit:
                await self.network_manager.notify_error(websocket, "Missing room_code or suit for hokm selection.")
                return
            if room_code not in self.active_games:
                await self.network_manager.notify_error(websocket, "Game not found for hokm selection.")
                return
                
            game = self.active_games[room_code]
            print(f"[LOG] Received hokm selection '{suit}' in room {room_code} [Current phase: {game.game_phase}]")
            
            # Set hokm and update phase
            if not game.set_hokm(suit, self.redis_manager, room_code):
                await self.network_manager.notify_error(websocket, "Invalid hokm selection or wrong phase.")
                return
            # Save state after hokm selection with timeout
            try:
                game_state = game.to_redis_dict()
                await asyncio.wait_for(
                    loop.run_in_executor(executor, self.redis_manager.save_game_state, room_code, game_state),
                    timeout=2.0
                )
                print(f"[DEBUG] Saved hokm state to Redis")
            except asyncio.TimeoutError:
                print(f"[DEBUG] Redis timeout when saving hokm state, continuing anyway")
            except Exception as e:
                print(f"[DEBUG] Could not save hokm state: {e}, continuing anyway")
                
            # Broadcast hokm selection with timeout protection
            try:
                await asyncio.wait_for(
                    self.network_manager.broadcast_to_room(
                        room_code,
                        'hokm_selected',
                        {'suit': game.hokm, 'hakem': game.hakem},
                        self.redis_manager
                    ),
                    timeout=3.0
                )
                print(f"[DEBUG] Hokm selection broadcasted")
            except asyncio.TimeoutError:
                print(f"[DEBUG] Timeout broadcasting hokm selection, trying direct network broadcast")
                # Fallback: broadcast directly to network connections
                for ws, metadata in self.network_manager.connection_metadata.items():
                    if metadata.get('room_code') == room_code:
                        try:
                            await self.network_manager.send_message(
                                ws,
                                'hokm_selected',
                                {'suit': game.hokm, 'hakem': game.hakem}
                            )
                        except Exception as e:
                            print(f"[DEBUG] Failed to send hokm selection to individual connection: {e}")
            except Exception as e:
                print(f"[DEBUG] Error broadcasting hokm selection: {e}")
                
            # Phase change: FINAL_DEAL
            game.game_phase = GameState.FINAL_DEAL.value if hasattr(GameState, 'FINAL_DEAL') else 'final_deal'
            
            # Save state after phase change with timeout
            try:
                game_state = game.to_redis_dict()
                await asyncio.wait_for(
                    loop.run_in_executor(executor, self.redis_manager.save_game_state, room_code, game_state),
                    timeout=2.0
                )
                print(f"[DEBUG] Saved FINAL_DEAL phase state to Redis")
            except asyncio.TimeoutError:
                print(f"[DEBUG] Redis timeout when saving FINAL_DEAL state, continuing anyway")
            except Exception as e:
                print(f"[DEBUG] Could not save FINAL_DEAL state: {e}, continuing anyway")
            
            # Broadcast phase change - CRITICAL for game progression
            print(f"[LOG] Broadcasting phase change to FINAL_DEAL in room {room_code}")
            try:
                await asyncio.wait_for(
                    self.network_manager.broadcast_to_room(
                        room_code,
                        'phase_change',
                        {'new_phase': game.game_phase},
                        self.redis_manager
                    ),
                    timeout=3.0
                )
                print(f"[DEBUG] FINAL_DEAL phase change broadcasted")
            except asyncio.TimeoutError:
                print(f"[DEBUG] Timeout broadcasting FINAL_DEAL phase change, trying direct network broadcast")
                # Fallback: broadcast directly to network connections
                for ws, metadata in self.network_manager.connection_metadata.items():
                    if metadata.get('room_code') == room_code:
                        try:
                            await self.network_manager.send_message(
                                ws,
                                'phase_change',
                                {'new_phase': game.game_phase}
                            )
                        except Exception as e:
                            print(f"[DEBUG] Failed to send phase change to individual connection: {e}")
            except Exception as e:
                print(f"[DEBUG] Error broadcasting FINAL_DEAL phase change: {e}")
            # Deal remaining cards and save state
            final_hands = game.final_deal(self.redis_manager)
            print(f"[DEBUG] Final deal completed, hands: {len(final_hands) if final_hands else 0}")
            
            # Use broadcast instead of individual sends to handle disconnected players
            try:
                await asyncio.wait_for(
                    self.network_manager.broadcast_to_room(
                        room_code,
                        'final_deal',
                        {
                            'hokm': game.hokm,
                            'message': f'Hokm is {game.hokm}. Final deal completed.'
                        },
                        self.redis_manager
                    ),
                    timeout=3.0
                )
                print(f"[DEBUG] Final deal message broadcasted")
            except asyncio.TimeoutError:
                print(f"[DEBUG] Timeout broadcasting final deal message, trying direct network broadcast")
                # Fallback: broadcast directly to network connections
                for ws, metadata in self.network_manager.connection_metadata.items():
                    if metadata.get('room_code') == room_code:
                        try:
                            await self.network_manager.send_message(
                                ws,
                                'final_deal',
                                {
                                    'hokm': game.hokm,
                                    'message': f'Hokm is {game.hokm}. Final deal completed.'
                                }
                            )
                        except Exception as e:
                            print(f"[DEBUG] Failed to send final deal message to individual connection: {e}")
            except Exception as e:
                print(f"[DEBUG] Error broadcasting final deal message: {e}")
            
            # Send individual hands to each player (this will store hands for disconnected players)
            try:
                room_players_for_final = await asyncio.wait_for(
                    loop.run_in_executor(executor, self.redis_manager.get_room_players, room_code),
                    timeout=2.0
                )
                print(f"[DEBUG] Got room players for final hands: {len(room_players_for_final)}")
            except asyncio.TimeoutError:
                print(f"[DEBUG] Redis timeout when getting room players for final hands, using connected players")
                # Fallback: use network manager to get connections
                room_players_for_final = []
                for ws, metadata in self.network_manager.connection_metadata.items():
                    if metadata.get('room_code') == room_code:
                        room_players_for_final.append({
                            'username': metadata.get('username', f'Player{len(room_players_for_final)+1}'),
                            'player_id': metadata.get('player_id')
                        })
            except Exception as e:
                print(f"[DEBUG] Could not get room players for final hands: {e}, using basic fallback")
                room_players_for_final = []
                
            for player in room_players_for_final:
                player_username = player['username']
                player_hand = final_hands.get(player_username, [])
                
                print(f"[DEBUG] Sending final hand to player {player_username}: {len(player_hand)} cards")
                ws = self.network_manager.get_live_connection(player['player_id'])
                if ws:
                    try:
                        await self.network_manager.send_message(
                            ws,
                            'final_deal',
                            {
                                'hand': player_hand,
                                'hokm': game.hokm
                            }
                        )
                        print(f"[DEBUG] Final hand sent to {player_username}")
                    except Exception as e:
                        print(f"[DEBUG] Failed to send final hand to {player_username}: {e}")
                else:
                    print(f"[DEBUG] Player {player_username} is disconnected, hand saved in Redis for later retrieval")
                    
            # Save state after final deal with timeout
            try:
                game_state = game.to_redis_dict()
                await asyncio.wait_for(
                    loop.run_in_executor(executor, self.redis_manager.save_game_state, room_code, game_state),
                    timeout=2.0
                )
                print(f"[DEBUG] Saved final deal state to Redis")
            except asyncio.TimeoutError:
                print(f"[DEBUG] Redis timeout when saving final deal state, continuing anyway")
            except Exception as e:
                print(f"[DEBUG] Could not save final deal state: {e}, continuing anyway")
                
            # Start first trick (which will send phase_change to GAMEPLAY)
            await self.start_first_trick(room_code)
        except Exception as e:
            print(f"[ERROR] Failed to handle hokm selection: {str(e)}")
            await self.network_manager.notify_error(websocket, f"Failed to handle hokm selection: {str(e)}")

    async def handle_play_card(self, websocket, message):
        """Handle a card play, update and save state, broadcast, and handle trick/hand completion."""
        try:
            room_code = message.get('room_code')
            player_id = message.get('player_id')
            card = message.get('card')
            if not room_code or not player_id or not card:
                await self.network_manager.notify_error(websocket, "Missing room_code, player_id, or card for play_card.")
                return
            if room_code not in self.active_games:
                await self.network_manager.notify_error(websocket, "Game not found for play_card.")
                return
            game = self.active_games[room_code]
            
            # Enhanced player lookup with debugging and fallback
            player, player_id = await self.find_player_by_websocket(websocket, room_code)
            if not player:
                error_msg = f"Player not found in room. player_id='{player_id}', room='{room_code}'"
                print(f"[ERROR] {error_msg}")
                await self.network_manager.notify_error(websocket, 
                    "Connection lost. Please exit and rejoin the game, or try reconnecting.")
                return
            
            # Out-of-turn check
            if hasattr(game, 'players') and hasattr(game, 'current_turn'):
                expected_player = game.players[game.current_turn]
                if player != expected_player:
                    await self.network_manager.notify_error(websocket, f"It is not your turn. It is {expected_player}'s turn.")
                    return
            # Card validity check
            if player not in game.hands or card not in game.hands[player]:
                await self.network_manager.notify_error(websocket, "Invalid card play: card not in your hand.")
                return
            # Play card and update state
            try:
                result = game.play_card(player, card, self.redis_manager)
                print(f"[DEBUG] play_card result: {result}")
                print(f"[DEBUG] trick_complete: {result.get('trick_complete')}")
                print(f"[DEBUG] next_turn: {result.get('next_turn')}")
                print(f"[DEBUG] current_turn after play: {getattr(game, 'current_turn', 'MISSING')}")
            except ValueError as ve:
                # This catches invalid game state errors (e.g., invalid trick resolution)
                error_msg = f"Invalid game state during card play: {str(ve)}"
                print(f"[ERROR] {error_msg}")
                await self.network_manager.notify_error(websocket, "Game state error. Please restart the game.")
                return
            except Exception as e:
                # Catch any other unexpected errors during card play
                error_msg = f"Unexpected error during card play: {str(e)}"
                print(f"[ERROR] {error_msg}")
                await self.network_manager.notify_error(websocket, "Unexpected error. Please try again.")
                return
                
            # Handle invalid play (e.g., suit-follow violation)
            if not result.get('valid', True):
                await self.network_manager.notify_error(websocket, result.get('message', 'Invalid move'))
                return
            # Save state after card play with timeout protection
            try:
                executor = concurrent.futures.ThreadPoolExecutor()
                loop = asyncio.get_event_loop()
                game_state = game.to_redis_dict()
                await asyncio.wait_for(
                    loop.run_in_executor(executor, self.redis_manager.save_game_state, room_code, game_state),
                    timeout=2.0
                )
                print(f"[DEBUG] Saved card play state to Redis")
            except asyncio.TimeoutError:
                print(f"[DEBUG] Redis timeout when saving card play state, continuing anyway")
            except Exception as e:
                print(f"[DEBUG] Could not save card play state: {e}, continuing anyway")
                
            # Broadcast card play with timeout protection
            try:
                await asyncio.wait_for(
                    self.network_manager.broadcast_to_room(
                        room_code,
                        'card_played',
                        {'player': player, 'card': card, 'team': game.teams.get(player, 0) + 1, 'player_id': player_id},
                        self.redis_manager
                    ),
                    timeout=3.0
                )
                print(f"[DEBUG] Card play broadcasted")
            except asyncio.TimeoutError:
                print(f"[DEBUG] Timeout broadcasting card play, trying direct network broadcast")
                # Fallback: broadcast directly to network connections
                for ws, metadata in self.network_manager.connection_metadata.items():
                    if metadata.get('room_code') == room_code:
                        try:
                            await self.network_manager.send_message(
                                ws,
                                'card_played',
                                {'player': player, 'card': card, 'team': game.teams.get(player, 0) + 1, 'player_id': player_id}
                            )
                        except Exception as e:
                            print(f"[DEBUG] Failed to send card play to individual connection: {e}")
            except Exception as e:
                print(f"[DEBUG] Error broadcasting card play: {e}")
            
            # Send turn_start for next player if trick is not complete
            if not result.get('trick_complete'):
                next_player = result.get('next_turn')
                print(f"[DEBUG] Trick not complete, next_player: {next_player}")
                if next_player:
                    print(f"[DEBUG] About to send turn_start to next player: {next_player}")
                    try:
                        room_players_for_turn = await asyncio.wait_for(
                            loop.run_in_executor(executor, self.redis_manager.get_room_players, room_code),
                            timeout=2.0
                        )
                        print(f"[DEBUG] Got room players for next turn: {len(room_players_for_turn)}")
                    except asyncio.TimeoutError:
                        print(f"[DEBUG] Redis timeout when getting room players for next turn, using connected players")
                        # Fallback: use network manager to get connections
                        room_players_for_turn = []
                        for ws, metadata in self.network_manager.connection_metadata.items():
                            if metadata.get('room_code') == room_code:
                                room_players_for_turn.append({
                                    'username': metadata.get('username', f'Player{len(room_players_for_turn)+1}'),
                                    'player_id': metadata.get('player_id')
                                })
                    except Exception as e:
                        print(f"[DEBUG] Could not get room players for next turn: {e}, using basic fallback")
                        room_players_for_turn = []
                    
                    print(f"[DEBUG] Sending turn_start to {len(room_players_for_turn)} players")
                    for player_info in room_players_for_turn:
                        ws = self.network_manager.get_live_connection(player_info['player_id'])
                        if ws and player_info['username'] in game.hands:
                            try:
                                await self.network_manager.send_message(
                                    ws,
                                    "turn_start",
                                    {
                                        "current_player": next_player,
                                        "your_turn": player_info['username'] == next_player,
                                        "hand": game.hands[player_info['username']][:],
                                        "hokm": game.hokm,
                                        "message": f"It's {next_player}'s turn"
                                    }
                                )
                                print(f"[DEBUG] Sent turn_start to {player_info['username']} for next player {next_player}")
                            except Exception as e:
                                print(f"[DEBUG] Failed to send turn_start to {player_info['username']}: {e}")
                        else:
                            if not ws:
                                print(f"[DEBUG] Player {player_info['username']} is disconnected during turn transition")
                            if player_info['username'] not in game.hands:
                                print(f"[DEBUG] Player {player_info['username']} has no hand data during turn transition")
                else:
                    print(f"[DEBUG] No next_player found in result!")
            else:
                print(f"[DEBUG] Trick is complete, not sending turn_start")
            
            # If trick complete, broadcast trick result and save state
            if result.get('trick_complete'):
                try:
                    await self.network_manager.broadcast_to_room(
                        room_code,
                        'trick_result',
                        {
                            'winner': result.get('trick_winner'),
                            'team1_tricks': (result.get('team_tricks') or {}).get(0, 0),
                            'team2_tricks': (result.get('team_tricks') or {}).get(1, 0)
                        },
                        self.redis_manager
                    )
                except Exception as e:
                    print(f"[ERROR] trick_result broadcast failed: {e}")
                # Save state after trick
                game_state = game.to_redis_dict()
                self.redis_manager.save_game_state(room_code, game_state)
                
                # Send turn_start for trick winner to start next trick (unless hand is complete)
                if not result.get('hand_complete'):
                    trick_winner = result.get('trick_winner')
                    if trick_winner:
                        try:
                            room_players_for_next_trick = await asyncio.wait_for(
                                loop.run_in_executor(executor, self.redis_manager.get_room_players, room_code),
                                timeout=2.0
                            )
                            print(f"[DEBUG] Got room players for next trick: {len(room_players_for_next_trick)}")
                        except asyncio.TimeoutError:
                            print(f"[DEBUG] Redis timeout when getting room players for next trick, using connected players")
                            # Fallback: use network manager to get connections
                            room_players_for_next_trick = []
                            for ws, metadata in self.network_manager.connection_metadata.items():
                                if metadata.get('room_code') == room_code:
                                    room_players_for_next_trick.append({
                                        'username': metadata.get('username', f'Player{len(room_players_for_next_trick)+1}'),
                                        'player_id': metadata.get('player_id')
                                    })
                        except Exception as e:
                            print(f"[DEBUG] Could not get room players for next trick: {e}, using basic fallback")
                            room_players_for_next_trick = []
                        
                        for player_info in room_players_for_next_trick:
                            ws = self.network_manager.get_live_connection(player_info['player_id'])
                            if ws and player_info['username'] in game.hands:
                                try:
                                    await self.network_manager.send_message(
                                        ws,
                                        "turn_start",
                                        {
                                            "current_player": trick_winner,
                                            "your_turn": player_info['username'] == trick_winner,
                                            "hand": game.hands[player_info['username']][:],
                                            "hokm": game.hokm,
                                            "message": f"{trick_winner} won the trick and leads next"
                                        }
                                    )
                                    print(f"[DEBUG] Sent turn_start to {player_info['username']} for trick winner {trick_winner}")
                                except Exception as e:
                                    print(f"[DEBUG] Failed to send turn_start to {player_info['username']}: {e}")
                            else:
                                if not ws:
                                    print(f"[DEBUG] Player {player_info['username']} is disconnected during trick transition")
                                if player_info['username'] not in game.hands:
                                    print(f"[DEBUG] Player {player_info['username']} has no hand data during trick transition")
                
                # If hand complete, broadcast hand and round completion and save state
                if result.get('hand_complete'):
                    # Fix the winning_team calculation to prevent negative values
                    round_winner = result.get('round_winner', 1)  # Default to team 1 if missing
                    winning_team = max(0, round_winner - 1) if round_winner > 0 else 0  # Ensure it's 0 or 1, never negative
                    # Coerce fields to safe JSON-serializable defaults
                    team_tricks = result.get('team_tricks') or {0: 0, 1: 0}
                    round_scores = result.get('round_scores') or {0: 0, 1: 0}
                    try:
                        await self.network_manager.broadcast_to_room(
                            room_code,
                            'hand_complete',
                            {
                                'winning_team': winning_team,
                                'tricks': team_tricks,
                                'round_winner': round_winner,
                                'round_scores': round_scores,
                                'game_complete': bool(result.get('game_complete', False))
                            },
                            self.redis_manager
                        )
                    except Exception as e:
                        print(f"[ERROR] hand_complete broadcast failed: {e}")
                    # Save state after hand completion
                    game_state = game.to_redis_dict()
                    self.redis_manager.save_game_state(room_code, game_state)

                    # Broadcast game_over if game is complete, otherwise start next round
                    if result.get('game_complete'):
                        await self.network_manager.broadcast_to_room(
                            room_code,
                            'game_over',
                            {'winner_team': result.get('round_winner')},
                            self.redis_manager
                        )
                    else:
                        # Start next round after 3 seconds delay
                        print(f"[LOG] Scheduling next round for room {room_code}")
                        asyncio.create_task(self.start_next_round_delayed(room_code, 3.0))
        except Exception as e:
            print(f"[ERROR] Failed to handle play_card: {str(e)}")
            import traceback
            traceback.print_exc()  # Print full stack trace for debugging
            try:
                await self.network_manager.notify_error(websocket, f"Failed to handle play_card: {str(e)}")
            except Exception as notify_err:
                print(f"[ERROR] Failed to notify play_card error: {notify_err}")
                # Don't re-raise - just log and continue

    async def start_first_trick(self, room_code):
        """Initialize the first trick after hokm selection"""
        try:
            executor = concurrent.futures.ThreadPoolExecutor()
            loop = asyncio.get_event_loop()
            
            game = self.active_games[room_code]
            
            # Find the hakem's index in the players list
            try:
                hakem_index = game.players.index(game.hakem)
            except ValueError:
                print(f"[ERROR] Hakem {game.hakem} not found in players list {game.players}")
                # Fallback: assume hakem is at index 0
                hakem_index = 0
                
            game.current_turn = hakem_index  # Hakem leads first trick
            first_player = game.players[game.current_turn]
            
            print(f"\n=== Starting first trick in room {room_code} ===")
            print(f"Hakem: {game.hakem}")
            print(f"Players order: {game.players}")
            print(f"Hakem index: {hakem_index}")
            print(f"{first_player} (Hakem) leads the first trick")
            print(f"Current turn set to: {game.current_turn}")
            
            # Verify that the first player is actually the hakem
            if first_player != game.hakem:
                print(f"[WARNING] First player {first_player} is not the hakem {game.hakem}!")
                # Force the hakem to be the current player
                game.current_turn = game.players.index(game.hakem)
                first_player = game.hakem
                print(f"[FIX] Corrected current_turn to {game.current_turn} for hakem {game.hakem}")
            
            # Update phase to gameplay
            game.game_phase = GameState.GAMEPLAY.value
            
            # Save updated game state after initiating first trick with timeout
            try:
                game_state = game.to_redis_dict()
                await asyncio.wait_for(
                    loop.run_in_executor(executor, self.redis_manager.save_game_state, room_code, game_state),
                    timeout=2.0
                )
                print(f"[DEBUG] Saved gameplay phase state to Redis")
            except asyncio.TimeoutError:
                print(f"[DEBUG] Redis timeout when saving gameplay state, continuing anyway")
            except Exception as e:
                print(f"[DEBUG] Could not save gameplay state: {e}, continuing anyway")
            
            # Broadcast phase change to gameplay with timeout protection
            try:
                await asyncio.wait_for(
                    self.network_manager.broadcast_to_room(
                        room_code,
                        'phase_change',
                        {'new_phase': GameState.GAMEPLAY.value},
                        self.redis_manager
                    ),
                    timeout=3.0
                )
                print(f"[DEBUG] GAMEPLAY phase change broadcasted")
            except asyncio.TimeoutError:
                print(f"[DEBUG] Timeout broadcasting GAMEPLAY phase change, trying direct network broadcast")
                # Fallback: broadcast directly to network connections
                for ws, metadata in self.network_manager.connection_metadata.items():
                    if metadata.get('room_code') == room_code:
                        try:
                            await self.network_manager.send_message(
                                ws,
                                'phase_change',
                                {'new_phase': GameState.GAMEPLAY.value}
                            )
                        except Exception as e:
                            print(f"[DEBUG] Failed to send phase change to individual connection: {e}")
            except Exception as e:
                print(f"[DEBUG] Error broadcasting GAMEPLAY phase change: {e}")
            
            # Get room players with timeout protection
            try:
                room_players = await asyncio.wait_for(
                    loop.run_in_executor(executor, self.redis_manager.get_room_players, room_code),
                    timeout=2.0
                )
                print(f"[DEBUG] Got room players for turn start: {len(room_players)}")
            except asyncio.TimeoutError:
                print(f"[DEBUG] Redis timeout when getting room players for turn start, using connected players")
                # Fallback: use network manager to get connections
                room_players = []
                for ws, metadata in self.network_manager.connection_metadata.items():
                    if metadata.get('room_code') == room_code:
                        room_players.append({
                            'username': metadata.get('username', f'Player{len(room_players)+1}'),
                            'player_id': metadata.get('player_id')
                        })
            except Exception as e:
                print(f"[DEBUG] Could not get room players for turn start: {e}, using basic fallback")
                room_players = []
            
            # Send individual turn info to each player with hand data
            for player in room_players:
                player_username = player['username']
                player_id = player['player_id']
                
                ws = self.network_manager.get_live_connection(player_id)
                if ws and player_username in game.hands:
                    try:
                        await self.network_manager.send_message(
                            ws,
                            "turn_start",
                            {
                                "current_player": first_player,
                                "your_turn": player_username == first_player,
                                "hand": game.hands[player_username][:],
                                "hokm": game.hokm,
                                "message": f"{first_player} (Hakem) leads the first trick"
                            }
                        )
                        print(f"[DEBUG] Sent turn_start with hand to {player_username}: {len(game.hands[player_username])} cards")
                    except Exception as e:
                        print(f"[DEBUG] Failed to send turn_start to {player_username}: {e}")
                else:
                    if not ws:
                        print(f"[DEBUG] Player {player_username} is disconnected during first trick start")
                    if player_username not in game.hands:
                        print(f"[DEBUG] Player {player_username} has no hand data")
                        
        except Exception as e:
            print(f"[ERROR] Failed to start first trick: {str(e)}")
            traceback.print_exc()

    async def handle_clear_room(self, websocket, message):
        # TEMPORARY: Admin/dev command to clear a room (for development/testing only)
        # TODO: Replace with proper admin interface/authorization
        room_code = message.get('room_code')
        if not room_code:
            await self.network_manager.notify_error(websocket, "Missing room_code for clear_room command.")
            return
        self.redis_manager.delete_room(room_code)
        if room_code in self.active_games:
            del self.active_games[room_code]
        await self.network_manager.notify_info(websocket, f"Room {room_code} has been cleared.")

    async def find_player_by_websocket(self, websocket, room_code):
        """Enhanced player lookup with multiple fallback mechanisms"""
        print(f"[DEBUG] find_player_by_websocket called for room {room_code}")
        print(f"[DEBUG] About to call redis_manager.get_room_players...")
        
        # Create executor and loop for timeout operations
        executor = concurrent.futures.ThreadPoolExecutor()
        loop = asyncio.get_event_loop()
        
        try:
            room_players = await asyncio.wait_for(
                loop.run_in_executor(executor, self.redis_manager.get_room_players, room_code),
                timeout=2.0
            )
            print(f"[DEBUG] get_room_players returned {len(room_players)} players")
        except asyncio.TimeoutError:
            print(f"[DEBUG] Redis timeout when getting room players, using fallback")
            # Fallback: use network manager to get connections
            room_players = []
            for ws, metadata in self.network_manager.connection_metadata.items():
                if metadata.get('room_code') == room_code:
                    room_players.append({
                        'username': metadata.get('username'),
                        'player_id': metadata.get('player_id'),
                        'connection_status': 'active'
                    })
            print(f"[DEBUG] Using {len(room_players)} fallback players")
        except Exception as e:
            print(f"[DEBUG] Error getting room players: {e}, using fallback")
            # Fallback: use network manager to get connections
            room_players = []
            for ws, metadata in self.network_manager.connection_metadata.items():
                if metadata.get('room_code') == room_code:
                    room_players.append({
                        'username': metadata.get('username'),
                        'player_id': metadata.get('player_id'),
                        'connection_status': 'active'
                    })
            print(f"[DEBUG] Using {len(room_players)} fallback players")
        
        # Method 1: Check connection metadata
        if websocket in self.network_manager.connection_metadata:
            conn_data = self.network_manager.connection_metadata[websocket]
            player_id = conn_data.get('player_id')
            print(f"[DEBUG] Found connection metadata with player_id: {player_id}")
            if player_id:
                for p in room_players:
                    print(f"[DEBUG] Checking room player: {p}")
                    if p.get('player_id') == player_id:
                        print(f"[DEBUG] Method 1 success: Found player {p.get('username')}")
                        return p.get('username'), player_id
        else:
            print(f"[DEBUG] Websocket not in connection_metadata")
        
        # Method 2: Check live connections
        if websocket in self.network_manager.live_connections:
            player_id = self.network_manager.live_connections[websocket]
            print(f"[DEBUG] Found in live_connections with player_id: {player_id}")
            for p in room_players:
                if p.get('player_id') == player_id:
                    print(f"[DEBUG] Method 2 success: Found player {p.get('username')}")
                    return p.get('username'), player_id
        else:
            print(f"[DEBUG] Websocket not in live_connections")
        
        # Method 3: Find by room code match in connection metadata
        print(f"[DEBUG] Trying method 3...")
        for p in room_players:
            if p.get('connection_status') == 'active':
                # Try to find websocket for this player
                for ws, conn_data in self.network_manager.connection_metadata.items():
                    if (conn_data.get('room_code') == room_code and 
                        conn_data.get('player_id') == p.get('player_id')):
                        if ws == websocket:
                            print(f"[DEBUG] Method 3 success: Found player {p.get('username')}")
                            return p.get('username'), p.get('player_id')
        
        print(f"[DEBUG] All methods failed - player not found!")
        return None, None

    def repair_player_connection(self, websocket, room_code, username):
        """Attempt to repair a broken player connection"""
        try:
            # Generate new player ID
            new_player_id = str(uuid.uuid4())
            
            # Update Redis with new connection info
            room_players = self.redis_manager.get_room_players(room_code)
            for i, p in enumerate(room_players):
                if p.get('username') == username:
                    # Update this player's ID
                    room_players[i]['player_id'] = new_player_id
                    room_players[i]['connection_status'] = 'active'
                    room_players[i]['reconnected_at'] = str(int(time.time()))
                    break
            
            # Save updated room data
            self.redis_manager.redis.delete(f"room:{room_code}:players")
            for p in room_players:
                self.redis_manager.add_player_to_room(room_code, p)
            
            # Update network manager
            self.network_manager.register_connection(websocket, new_player_id, room_code, username)
            
            print(f"[LOG] Repaired connection for {username} in room {room_code}")
            return new_player_id
            
        except Exception as e:
            print(f"[ERROR] Failed to repair connection for {username}: {str(e)}")
            return None

    async def start_next_round_delayed(self, room_code, delay_seconds):
        """Start next round after a delay"""
        await asyncio.sleep(delay_seconds)
        await self.start_next_round(room_code)

    async def start_next_round(self, room_code):
        """Start the next round with new hakem selection"""
        try:
            if room_code not in self.active_games:
                print(f"[ERROR] Room {room_code} not found for next round")
                return

            game = self.active_games[room_code]
            
            if game.game_phase == "completed":
                print(f"[LOG] Game in room {room_code} is already completed")
                return

            print(f"[LOG] Starting next round in room {room_code}")
            
            # Start new round (this handles hakem selection and initial deal)
            initial_hands = game.start_new_round(self.redis_manager)
            
            if isinstance(initial_hands, dict) and "error" in initial_hands:
                print(f"[ERROR] Failed to start new round: {initial_hands['error']}")
                return

            # Get round info for broadcast
            round_info = game.get_new_round_info()
            print(f"[LOG] Round info: {round_info}")
            
            # Broadcast phase change to hokm selection
            await self.network_manager.broadcast_to_room(
                room_code,
                'phase_change',
                {'new_phase': GameState.WAITING_FOR_HOKM.value},
                self.redis_manager
            )
            
            # Broadcast new round start to all players
            await self.network_manager.broadcast_to_room(
                room_code,
                'new_round_start',
                round_info,
                self.redis_manager
            )

            # Send individual initial hands to each player
            print(f"[LOG] Broadcasting initial hands: {list(initial_hands.keys())}")
            await self.broadcast_initial_hands(room_code, initial_hands)

            # Update game state in Redis
            game_state = game.to_redis_dict()
            self.redis_manager.save_game_state(room_code, game_state)

            print(f"[LOG] Next round started successfully in room {room_code}")
            
        except Exception as e:
            print(f"[ERROR] Failed to start next round in room {room_code}: {str(e)}")
            import traceback
            traceback.print_exc()

    async def broadcast_initial_hands(self, room_code, hands):
        """Broadcast initial hands (5 cards) to players for hokm selection"""
        try:
            game = self.active_games[room_code]
            
            for player_name, hand in hands.items():
                # Find the player info
                room_players = self.redis_manager.get_room_players(room_code)
                player_info = next((p for p in room_players if p['username'] == player_name), None)
                
                if player_info:
                    is_hakem = (player_name == game.hakem)
                    player_id = player_info['player_id']
                    
                    # Get the websocket connection for this player
                    ws = self.network_manager.get_live_connection(player_id)
                    if ws:
                        await self.network_manager.send_message(
                            ws,
                            'initial_deal',
                            {
                                'hand': hand,
                                'hakem': game.hakem,
                                'is_hakem': is_hakem,
                                'you': player_name,
                                'phase': 'hokm_selection'
                            }
                        )
                        print(f"[LOG] Sent initial hand to {player_name} (hakem: {is_hakem})")
                    else:
                        print(f"[ERROR] No websocket connection found for {player_name} (player_id: {player_id})")
                        
        except Exception as e:
            print(f"[ERROR] Failed to broadcast initial hands: {str(e)}")
            import traceback
            traceback.print_exc()

    async def handle_player_reconnection(self, websocket, room_code, disconnected_player):
        """Handle a player reconnecting to their previous slot"""
        try:
            player_id = disconnected_player['player_id']
            username = disconnected_player['username']
            player_number = disconnected_player['player_number']
            
            print(f"[LOG] Player reconnection: {username} rejoining room {room_code}")
            
            # Update player status to active
            updated_player_data = disconnected_player.copy()
            updated_player_data['connection_status'] = 'active'
            updated_player_data['reconnected_at'] = str(int(time.time()))
            
            # Update session data in Redis
            session_data = {
                'username': username,
                'room_code': room_code,
                'connected_at': updated_player_data.get('reconnected_at'),
                'expires_at': str(int(time.time()) + 3600),
                'player_number': player_number,
                'connection_status': 'active'
            }
            self.redis_manager.save_player_session(player_id, session_data)
            
            # Register live connection
            self.network_manager.register_connection(websocket, player_id, room_code, username)
            
            # Update room player data
            self.redis_manager.update_player_in_room(room_code, player_id, updated_player_data)
            
            # Send reconnection success message
            await self.network_manager.send_message(
                websocket,
                'join_success',
                {
                    'username': username,
                    'player_id': player_id,
                    'room_code': room_code,
                    'player_number': player_number,
                    'reconnected': True,
                    'message': f'Reconnected as {username}'
                }
            )
            
            # Send current game state if game is in progress
            game = self.active_games.get(room_code)
            if game:
                await self.send_game_state_to_reconnected_player(websocket, room_code, game, username)
            
            # Notify other players about reconnection
            await self.network_manager.broadcast_to_room(
                room_code,
                'player_reconnected',
                {
                    'username': username,
                    'player_number': player_number,
                    'message': f'{username} has reconnected'
                },
                self.redis_manager
            )
            
            print(f"[LOG] {username} successfully reconnected to room {room_code}")
            return True
            
        except Exception as e:
            print(f"[ERROR] Failed to handle player reconnection: {str(e)}")
            await self.network_manager.notify_error(websocket, f"Reconnection failed: {str(e)}")
            return False

    async def send_game_state_to_reconnected_player(self, websocket, room_code, game, username):
        """Send current game state to a reconnected player"""
        try:
            # Send current phase
            await self.network_manager.send_message(
                websocket,
                'phase_change',
                {
                    'old_phase': 'disconnected',
                    'new_phase': game.game_phase,
                    'message': f'Current game phase: {game.game_phase}'
                }
            )
            
            # Send team assignment if available
            if hasattr(game, 'teams') and game.teams:
                team_data = {}
                for player, team_id in game.teams.items():
                    if team_id not in team_data:
                        team_data[team_id] = []
                    team_data[team_id].append(player)
                
                await self.network_manager.send_message(
                    websocket,
                    'team_assignment',
                    {
                        'teams': team_data,
                        'hakem': getattr(game, 'hakem', None),
                        'you': username
                    }
                )
            
            # Send hand if in gameplay phase
            if game.game_phase in ['gameplay', 'final_deal', 'hokm_selection'] and hasattr(game, 'hands'):
                if username in game.hands:
                    await self.network_manager.send_message(
                        websocket,
                        'hand_update',
                        {
                            'hand': game.hands[username],
                            'hokm': getattr(game, 'hokm', None),
                            'phase': game.game_phase
                        }
                    )
            
            # Send current trick state if in gameplay
            if game.game_phase == 'gameplay' and hasattr(game, 'current_trick'):
                current_player_idx = getattr(game, 'current_turn', 0)
                your_turn = (game.players[current_player_idx] == username) if current_player_idx < len(game.players) else False
                
                await self.network_manager.send_message(
                    websocket,
                    'trick_state',
                    {
                        'current_trick': game.current_trick,
                        'current_player': current_player_idx,
                        'your_turn': your_turn,
                        'trick_count': getattr(game, 'completed_tricks', 0)
                    }
                )
            
            # Handle hokm selection phase for reconnected players
            elif game.game_phase in ['waiting_for_hokm', GameState.WAITING_FOR_HOKM.value] and hasattr(game, 'hakem'):
                if game.hakem == username:
                    # Send hokm selection prompt to the hakem
                    await self.network_manager.send_message(
                        websocket,
                        'hokm_selection_prompt',
                        {
                            'message': 'You are the Hakem. Please select the hokm suit.',
                            'hakem': game.hakem,
                            'you': username,
                            'phase': game.game_phase
                        }
                    )
                    print(f"[LOG] Sent hokm selection prompt to reconnected hakem: {username}")
                else:
                    # Send waiting message to non-hakem players
                    await self.network_manager.send_message(
                        websocket,
                        'waiting_for_hokm',
                        {
                            'message': f'Waiting for {game.hakem} to select hokm.',
                            'hakem': game.hakem,
                            'you': username,
                            'phase': game.game_phase
                        }
                    )
                    print(f"[LOG] Sent waiting for hokm message to reconnected player: {username}")
                
        except Exception as e:
            print(f"[ERROR] Failed to send game state to reconnected player: {str(e)}")

    async def handle_health_check(self, websocket, message):
        """Handle health check requests - returns circuit breaker and system status"""
        try:
            # Get comprehensive health status
            health_data = {
                'status': 'ok',
                'timestamp': time.time(),
                'server': {
                    'active_games': len(self.active_games),
                    'connected_clients': len(self.network_manager.connections) if hasattr(self.network_manager, 'connections') else 0
                },
                'circuit_breakers': self.circuit_breaker_monitor.get_circuit_breaker_status(),
                'redis_health': self.circuit_breaker_monitor.check_redis_health(),
                'performance_metrics': self.redis_manager.get_performance_metrics()
            }
            
            # Determine overall health status
            cb_status = health_data['circuit_breakers']
            redis_status = health_data['redis_health']
            
            if redis_status.get('status') == 'unhealthy' or any(
                cb.get('state') == 'open' for cb in cb_status.values()
            ):
                health_data['status'] = 'degraded'
            
            # Send health check response
            await websocket.send(json.dumps({
                'type': 'health_check_response',
                'data': health_data
            }))
            
        except Exception as e:
            print(f"[ERROR] Health check failed: {str(e)}")
            await self.network_manager.notify_error(websocket, f"Health check failed: {str(e)}")

async def cleanup_task(server_instance):
    """Periodic task to cleanup expired sessions, inactive rooms, and stale connections"""
    # Wait for server to fully start before beginning cleanup
    await asyncio.sleep(30)
    print("[LOG] Cleanup task starting periodic maintenance...")
    
    while True:
        try:
            # Use the passed server instance instead of global
            if not server_instance:
                await asyncio.sleep(300)
                continue
                
            # Check for dead connections by attempting to ping them
            dead_connections = []
            for ws, metadata in list(server_instance.network_manager.connection_metadata.items()):
                try:
                    # Try to ping the connection
                    pong_waiter = await ws.ping()
                    await asyncio.wait_for(pong_waiter, timeout=5)  # Short timeout for cleanup
                except (websockets.ConnectionClosed, asyncio.TimeoutError, Exception):
                    print(f"[LOG] Found dead connection for player {metadata.get('player_id')} in room {metadata.get('room_code')}")
                    dead_connections.append(ws)
            
            # Handle dead connections
            for ws in dead_connections:
                try:
                    await server_instance.handle_connection_closed(ws)
                except Exception as e:
                    print(f"[ERROR] Error handling dead connection: {str(e)}")
            
            # Cleanup expired sessions from Redis
            server_instance.redis_manager.cleanup_expired_sessions()
            
            current_time = int(time.time())
            
            # Check and cleanup stale connections (fallback)
            for ws, metadata in list(server_instance.network_manager.connection_metadata.items()):
                connected_at = metadata.get('connected_at', 0)
                if current_time - connected_at > 7200:  # 2 hours without activity
                    print(f"[LOG] Removing stale connection for player {metadata.get('player_id')}")
                    try:
                        await server_instance.handle_connection_closed(ws)
                    except Exception as e:
                        print(f"[ERROR] Error removing stale connection: {str(e)}")
            
            # Check for inactive rooms in Redis by scanning for room keys
            for key in server_instance.redis_manager.redis.scan_iter("room:*:players"):
                try:
                    room_code = key.decode().split(':')[1]  # Extract room code from key
                    if server_instance.redis_manager.room_exists(room_code):
                        game_state = server_instance.redis_manager.get_game_state(room_code)
                        if game_state:
                            last_activity = int(game_state.get('last_activity', '0'))
                            if current_time - last_activity > 3600:  # 1 hour inactivity
                                print(f"[LOG] Cleaning up inactive room {room_code}")
                                server_instance.redis_manager.delete_room(room_code)
                                
                                # Remove from active games if exists
                                if room_code in server_instance.active_games:
                                    del server_instance.active_games[room_code]
                except Exception as e:
                    print(f"[ERROR] Error checking room {room_code}: {str(e)}")
                    
        except Exception as e:
            print(f"[ERROR] Error in cleanup task: {str(e)}")
            import traceback
            traceback.print_exc()
            
        await asyncio.sleep(60)  # Run every minute for better responsiveness

async def main():
    print("Starting Hokm WebSocket server on ws://0.0.0.0:8765")
    print("[DEBUG] Creating GameServer instance...")
    game_server = GameServer()
    print("[DEBUG] Loading games from Redis...")
    game_server.load_active_games_from_redis()
    print("[DEBUG] Server initialization complete")

    async def handle_connection(websocket, path):
        """Handle new WebSocket connections with ping/pong health checks"""
        ping_task = None
        try:
            print(f"[LOG] New connection from {websocket.remote_address}")
            
            # Start ping task to detect disconnections
            async def ping_client():
                try:
                    while True:
                        await asyncio.sleep(30)  # Ping every 30 seconds
                        try:
                            pong_waiter = await websocket.ping()
                            await asyncio.wait_for(pong_waiter, timeout=10)  # Wait up to 10 seconds for pong
                        except (websockets.ConnectionClosed, asyncio.TimeoutError):
                            print(f"[LOG] Ping failed - connection lost for {websocket.remote_address}")
                            break
                        except Exception as e:
                            print(f"[ERROR] Ping error: {str(e)}")
                            break
                except asyncio.CancelledError:
                    pass
            
            ping_task = asyncio.create_task(ping_client())
            
            async for message in websocket:
                try:
                    data = json.loads(message)
                    await game_server.handle_message(websocket, data)
                except json.JSONDecodeError:
                    try:
                        await game_server.network_manager.notify_error(websocket, "Invalid message format")
                    except Exception as notify_err:
                        print(f"[ERROR] Failed to notify JSON error: {notify_err}")
                        # Continue the loop even if notification fails
                except Exception as e:
                    print(f"[ERROR] Failed to process message: {str(e)}")
                    import traceback
                    traceback.print_exc()  # Print full stack trace for debugging
                    try:
                        await game_server.network_manager.notify_error(websocket, f"Internal server error: {str(e)}")
                    except Exception as notify_err:
                        print(f"[ERROR] Failed to notify user of connection error: {notify_err}")
                        # Continue the loop even if notification fails
                    # Don't break the loop - continue processing messages
        except websockets.ConnectionClosed:
            print(f"[LOG] Connection closed normally for {websocket.remote_address}")
            await game_server.handle_connection_closed(websocket)
        except Exception as e:
            print(f"[ERROR] Connection handler error: {str(e)}")
            import traceback
            traceback.print_exc()
            try:
                await game_server.network_manager.notify_error(websocket, f"Connection handler error: {str(e)}")
            except Exception as notify_err:
                print(f"[ERROR] Failed to notify user of connection handler error: {notify_err}")
        finally:
            # Always cancel ping task and handle disconnection
            if ping_task:
                ping_task.cancel()
                try:
                    await ping_task
                except asyncio.CancelledError:
                    pass
            
            # Handle disconnection regardless of how the connection ended
            await game_server.handle_connection_closed(websocket)
    
    # Start cleanup task with server instance (disabled for debugging)
    print("[DEBUG] Skipping cleanup task for now...")
    # cleanup_loop = asyncio.create_task(cleanup_task(game_server))
    # print("[DEBUG] Cleanup task started")
    
    try:
        print("[DEBUG] Starting WebSocket server...")
        server = await websockets.serve(
            handle_connection, 
            "0.0.0.0", 
            8765,
            ping_interval=60,      # Send ping every 60 seconds
            ping_timeout=300,      # 5 minutes timeout for ping response
            close_timeout=300,     # 5 minutes timeout for close handshake
            max_size=1024*1024,    # 1MB max message size
            max_queue=100          # Max queued messages
        )
        print("[LOG] WebSocket server is now listening on ws://0.0.0.0:8765")
        print("[LOG] WebSocket timeouts: ping_timeout=300s, close_timeout=300s")
        await server.wait_closed()  # Wait for server to be closed
    except Exception as e:
        print(f"[ERROR] Server error: {str(e)}")
    # finally:
    #     cleanup_loop.cancel()
    #     try:
    #         await cleanup_loop
    #     except asyncio.CancelledError:
    #         pass

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServer shutting down...")
    except Exception as e:
        print(f"[ERROR] Fatal error: {str(e)}")
        sys.exit(1)
