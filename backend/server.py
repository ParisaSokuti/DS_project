"""
Optimized Hokm Card Game Server
High-performance WebSocket server for multiplayer Persian card game
"""

import asyncio
import json
import time
import os
import concurrent.futures
from typing import Dict, Optional, Any

import websockets
import websockets.exceptions

# Local imports with fallback for both module and direct execution
try:
    from .network import NetworkManager
    from .game_board import GameBoard
    from .game_states import GameState
    from .redis_manager import RedisManager
    from .game_auth_manager import GameAuthManager
except ImportError:
    from network import NetworkManager
    from game_board import GameBoard
    from game_states import GameState
    from redis_manager import RedisManager
    from game_auth_manager import GameAuthManager

# Configuration constants
ROOM_SIZE = 4
REDIS_TIMEOUT = 2.0
BROADCAST_TIMEOUT = 3.0
PING_INTERVAL = 30
PONG_TIMEOUT = 10


class GameServer:
    """High-performance game server with optimized connection handling"""
    
    def __init__(self):
        self.redis_manager = RedisManager()
        self.network_manager = NetworkManager()
        self.auth_manager = GameAuthManager()
        self.active_games: Dict[str, GameBoard] = {}
        
        # Thread pool for CPU-intensive operations
        self.executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=10, 
            thread_name_prefix="GameServer"
        )

    async def execute_with_timeout(self, func, timeout: float = REDIS_TIMEOUT, *args, **kwargs) -> Optional[Any]:
        """Execute function with timeout and comprehensive error handling"""
        try:
            return await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(self.executor, func, *args, **kwargs),
                timeout=timeout
            )
        except (asyncio.TimeoutError, Exception) as e:
            error_type = "TIMEOUT" if isinstance(e, asyncio.TimeoutError) else "ERROR"
            print(f"[{error_type}] {func.__name__}: {e}")
            return None

    async def broadcast_with_fallback(self, room_code: str, message_type: str, data: Dict[str, Any]) -> None:
        """Broadcast message with timeout and direct fallback"""
        try:
            await asyncio.wait_for(
                self.network_manager.broadcast_to_room(room_code, message_type, data, self.redis_manager),
                timeout=BROADCAST_TIMEOUT
            )
        except (asyncio.TimeoutError, Exception) as e:
            print(f"[ERROR] Broadcasting {message_type}: {e}")
            # Direct fallback
            tasks = [self.network_manager.send_message(ws, message_type, data) 
                    for ws, meta in self.network_manager.connection_metadata.items() 
                    if meta.get('room_code') == room_code]
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

    def get_room_player_count(self, room_code: str) -> int:
        """Get current player count for a room from network manager"""
        return sum(1 for metadata in self.network_manager.connection_metadata.values() 
                  if metadata.get('room_code') == room_code)

    async def handle_join(self, websocket, data: Dict[str, Any]) -> Optional[bool]:
        """Handle player joining with optimized validation and processing"""
        try:
            room_code = data.get('room_code', '9999')
            
            # Quick capacity and auth checks
            if self.get_room_player_count(room_code) >= ROOM_SIZE:
                await self.network_manager.notify_error(websocket, "Room is full")
                return False

            player_info = self.auth_manager.get_authenticated_player(websocket)
            if not player_info:
                await self.network_manager.notify_error(websocket, "Authentication required")
                return False
            
            # Extract player data
            player_id, username = player_info['player_id'], player_info['username']
            player_number = self.get_room_player_count(room_code) + 1
            current_time = int(time.time())

            # Prepare session and room data
            session_data = {
                'username': username, 'display_name': player_info['display_name'],
                'player_id': player_id, 'room_code': room_code,
                'connected_at': str(current_time), 'expires_at': str(current_time + 3600),
                'player_number': player_number, 'connection_status': 'active',
                'rating': player_info.get('rating', 1000)
            }
            room_data = {
                'player_id': player_id, 'username': username, 'player_number': player_number,
                'joined_at': str(current_time), 'connection_status': 'active'
            }

            # Save data and register connection
            await asyncio.gather(
                self.execute_with_timeout(self.redis_manager.create_room, REDIS_TIMEOUT, room_code),
                self.execute_with_timeout(self.redis_manager.save_player_session, REDIS_TIMEOUT, player_id, session_data),
                self.execute_with_timeout(self.redis_manager.add_player_to_room, REDIS_TIMEOUT, room_code, room_data),
                return_exceptions=True
            )

            self.network_manager.register_connection(websocket, player_id, room_code, username)
            await self.network_manager.send_message(websocket, 'join_success', {
                'username': username, 'player_id': player_id, 
                'room_code': room_code, 'player_number': player_number
            })

            # Start game if room is full
            if self.get_room_player_count(room_code) >= ROOM_SIZE:
                print(f"[GAME] Room {room_code} full, starting game")
                await asyncio.sleep(0.5)  # Connection stabilization
                await self.handle_game_start(room_code)

            return True

        except Exception as e:
            print(f"[ERROR] Join failed: {e}")
            await self.network_manager.notify_error(websocket, "Failed to join room")
            return False

    async def handle_game_start(self, room_code: str):
        """Initialize and start a new game with optimized flow"""
        try:
            # Check if game already exists
            if room_code in self.active_games:
                existing_game = self.active_games[room_code]
                if existing_game.game_phase != GameState.WAITING_FOR_PLAYERS.value:
                    print(f"[LOG] Game already in progress in room {room_code}")
                    return

            # Get players from network manager (faster than Redis)
            players = [meta.get('username', f'Player{i+1}') 
                      for i, (ws, meta) in enumerate(self.network_manager.connection_metadata.items()) 
                      if meta.get('room_code') == room_code]

            if len(players) != ROOM_SIZE:
                print(f"[ERROR] Invalid player count: {len(players)}, expected {ROOM_SIZE}")
                return

            # Create and initialize game
            game = GameBoard(players, room_code)
            self.active_games[room_code] = game
            team_result = game.assign_teams_and_hakem(self.redis_manager)
            
            # Save initial game state and broadcast
            await asyncio.gather(
                self.execute_with_timeout(self.redis_manager.save_game_state, REDIS_TIMEOUT, room_code, game.to_redis_dict()),
                self.broadcast_with_fallback(room_code, 'phase_change', {'new_phase': GameState.TEAM_ASSIGNMENT.value}),
                self.broadcast_with_fallback(room_code, 'team_assignment', team_result),
                return_exceptions=True
            )
            
            # Deal initial cards and transition to hokm selection
            initial_hands = game.initial_deal()
            game.game_phase = GameState.WAITING_FOR_HOKM.value
            
            await asyncio.gather(
                self.execute_with_timeout(self.redis_manager.save_game_state, REDIS_TIMEOUT, room_code, game.to_redis_dict()),
                self.broadcast_with_fallback(room_code, 'phase_change', {'new_phase': GameState.WAITING_FOR_HOKM.value}),
                return_exceptions=True
            )
            
            # Send initial hands to players
            await self._send_initial_hands(room_code, initial_hands, game)
            print(f"[LOG] Game started in room {room_code}")
            
        except Exception as e:
            print(f"[ERROR] Failed to start game in room {room_code}: {str(e)}")
            await self.broadcast_with_fallback(room_code, 'error', {'message': f'Failed to start game: {str(e)}'})

    async def _send_initial_hands(self, room_code, initial_hands, game):
        """Send initial hands to players efficiently"""
        tasks = []
        for ws, metadata in self.network_manager.connection_metadata.items():
            if metadata.get('room_code') == room_code:
                username = metadata.get('username')
                if username in initial_hands:
                    is_hakem = (username == game.hakem)
                    message = "You are the Hakem. Choose hokm." if is_hakem else f"Waiting for {game.hakem} to choose hokm."
                    
                    tasks.append(self.network_manager.send_message(ws, 'initial_deal', {
                        'hand': initial_hands[username],
                        'is_hakem': is_hakem,
                        'hakem': game.hakem,
                        'message': message
                    }))
        
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    print(f"[DEBUG] Failed to send initial hand: {result}")

    async def handle_hokm_selection(self, websocket, message):
        """Handle hokm selection with optimized broadcasting"""
        try:
            room_code, suit = message.get('room_code'), message.get('suit')
            print(f"[DEBUG] Hokm selection received: room={room_code}, suit={suit}")
            
            if not room_code or not suit or room_code not in self.active_games:
                await self.network_manager.notify_error(websocket, "Invalid hokm selection request")
                return
                
            game = self.active_games[room_code]
            
            # Find player making selection
            player_username = next((meta.get('username') for ws, meta in self.network_manager.connection_metadata.items() 
                                  if ws == websocket and meta.get('room_code') == room_code), None)
            
            if not player_username:
                await self.network_manager.notify_error(websocket, "Player not found in room")
                return
            
            # Validate hakem and phase
            if player_username != game.hakem:
                await self.network_manager.notify_error(websocket, f"Only {game.hakem} (the Hakem) can choose hokm")
                return
            
            if game.game_phase != GameState.WAITING_FOR_HOKM.value:
                await self.network_manager.notify_error(websocket, f"Cannot choose hokm in current phase: {game.game_phase}")
                return
            
            print(f"[LOG] Hokm selection '{suit}' by {player_username} (hakem) in room {room_code}")
            
            # Set hokm and update phase
            if not game.set_hokm(suit, self.redis_manager, room_code):
                await self.network_manager.notify_error(websocket, "Invalid hokm selection")
                return

            # Update phase and deal final cards
            game.game_phase = GameState.FINAL_DEAL.value if hasattr(GameState, 'FINAL_DEAL') else 'final_deal'
            final_hands = game.final_deal(self.redis_manager)
            
            # Save state and broadcast updates
            await asyncio.gather(
                self.execute_with_timeout(self.redis_manager.save_game_state, REDIS_TIMEOUT, room_code, game.to_redis_dict()),
                self.broadcast_with_fallback(room_code, 'hokm_selected', {'suit': game.hokm, 'hakem': game.hakem}),
                self.broadcast_with_fallback(room_code, 'phase_change', {'new_phase': game.game_phase}),
                self.broadcast_with_fallback(room_code, 'final_deal', {'hokm': game.hokm, 'message': f'Hokm is {game.hokm}. Final deal completed.'}),
                return_exceptions=True
            )
            
            await self._send_final_hands(room_code, final_hands, game)
            await self.start_first_trick(room_code)
            
        except Exception as e:
            print(f"[ERROR] Failed to handle hokm selection: {str(e)}")
            await self.network_manager.notify_error(websocket, f"Failed to handle hokm selection: {str(e)}")

    async def _send_final_hands(self, room_code, final_hands, game):
        """Send final hands to players efficiently"""
        tasks = [self.network_manager.send_message(ws, 'final_deal', {'hand': final_hands[username], 'hokm': game.hokm})
                for ws, meta in self.network_manager.connection_metadata.items()
                if meta.get('room_code') == room_code and (username := meta.get('username')) in final_hands]
        
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    print(f"[DEBUG] Failed to send final hand: {result}")

    async def start_first_trick(self, room_code):
        """Start the first trick efficiently"""
        try:
            game = self.active_games[room_code]
            
            # Set hakem as first player
            hakem_index = game.players.index(game.hakem) if game.hakem in game.players else 0
            game.current_turn = hakem_index
            first_player = game.players[game.current_turn]
            game.game_phase = GameState.GAMEPLAY.value
            
            # Save state and broadcast
            await asyncio.gather(
                self.execute_with_timeout(self.redis_manager.save_game_state, REDIS_TIMEOUT, room_code, game.to_redis_dict()),
                self.broadcast_with_fallback(room_code, 'phase_change', {'new_phase': GameState.GAMEPLAY.value}),
                return_exceptions=True
            )
            
            await self._send_turn_start(room_code, first_player, game, f"{first_player} (Hakem) leads the first trick")
            print(f"[LOG] First trick started in room {room_code}, {first_player} leads")
                        
        except Exception as e:
            print(f"[ERROR] Failed to start first trick: {str(e)}")

    async def _send_turn_start(self, room_code, current_player, game, message):
        """Send turn start message to all players efficiently"""
        tasks = [self.network_manager.send_message(ws, "turn_start", {
                    "current_player": current_player,
                    "your_turn": username == current_player,
                    "hand": game.hands[username][:],
                    "hokm": game.hokm,
                    "message": message
                })
                for ws, meta in self.network_manager.connection_metadata.items()
                if meta.get('room_code') == room_code and (username := meta.get('username')) in game.hands]
        
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception):
                    print(f"[DEBUG] Failed to send turn_start: {result}")

    async def handle_play_card(self, websocket, message):
        """Handle card play with optimized processing"""
        try:
            room_code, player_id, card = message.get('room_code'), message.get('player_id'), message.get('card')
            
            if not all([room_code, player_id, card]) or room_code not in self.active_games:
                await self.network_manager.notify_error(websocket, "Invalid card play request")
                return
                
            game = self.active_games[room_code]
            
            # Find player efficiently
            player = next((meta.get('username') for ws, meta in self.network_manager.connection_metadata.items() 
                          if ws == websocket and meta.get('room_code') == room_code), None)
            
            if not player:
                await self.network_manager.notify_error(websocket, "Player not found in room")
                return
            
            # Validate turn and card
            if hasattr(game, 'current_turn') and game.players[game.current_turn] != player:
                expected_player = game.players[game.current_turn]
                await self.network_manager.notify_error(websocket, f"It is {expected_player}'s turn")
                return
            
            if player not in game.hands or card not in game.hands[player]:
                await self.network_manager.notify_error(websocket, "Invalid card play")
                return
            
            # Play card
            try:
                result = game.play_card(player, card, self.redis_manager)
            except (ValueError, Exception) as e:
                await self.network_manager.notify_error(websocket, f"Invalid game state: {str(e)}")
                return
                
            if not result.get('valid', True):
                await self.network_manager.notify_error(websocket, result.get('message', 'Invalid move'))
                return
            
            # Save state and broadcast card play
            await asyncio.gather(
                self.execute_with_timeout(self.redis_manager.save_game_state, REDIS_TIMEOUT, room_code, game.to_redis_dict()),
                self.broadcast_with_fallback(room_code, 'card_played', {
                    'player': player, 'card': card, 
                    'team': game.teams.get(player, 0) + 1, 'player_id': player_id
                }),
                return_exceptions=True
            )
            
            # Handle trick completion or next turn
            if result.get('trick_complete'):
                await self._handle_trick_completion(room_code, result, game)
            elif next_player := result.get('next_turn'):
                await self._send_turn_start(room_code, next_player, game, f"It's {next_player}'s turn")
            
        except Exception as e:
            print(f"[ERROR] Failed to handle play_card: {str(e)}")
            await self.network_manager.notify_error(websocket, "Failed to handle card play")

    async def _handle_trick_completion(self, room_code, result, game):
        """Handle trick completion efficiently"""
        try:
            # Broadcast trick result
            await self.broadcast_with_fallback(room_code, 'trick_result', {
                'winner': result.get('trick_winner'),
                'team1_tricks': (result.get('team_tricks') or {}).get(0, 0),
                'team2_tricks': (result.get('team_tricks') or {}).get(1, 0)
            })
            
            # Save state
            await self.execute_with_timeout(self.redis_manager.save_game_state, REDIS_TIMEOUT, room_code, game.to_redis_dict())
            
            if result.get('hand_complete'):
                await self._handle_hand_completion(room_code, result, game)
            else:
                # Start next trick with winner leading
                trick_winner = result.get('trick_winner')
                if trick_winner:
                    await self._send_turn_start(room_code, trick_winner, game, f"{trick_winner} won the trick and leads next")
                    
        except Exception as e:
            print(f"[ERROR] Failed to handle trick completion: {str(e)}")

    async def _handle_hand_completion(self, room_code, result, game):
        """Handle hand completion efficiently"""
        try:
            round_winner = result.get('round_winner', 1)
            winning_team = max(0, round_winner - 1) if round_winner > 0 else 0
            team_tricks = result.get('team_tricks') or {0: 0, 1: 0}
            round_scores = result.get('round_scores') or {0: 0, 1: 0}
            
            await self.broadcast_with_fallback(room_code, 'hand_complete', {
                'winning_team': winning_team,
                'tricks': team_tricks,
                'round_winner': round_winner,
                'round_scores': round_scores,
                'game_complete': bool(result.get('game_complete', False))
            })
            
            # Save state
            await self.execute_with_timeout(self.redis_manager.save_game_state, REDIS_TIMEOUT, room_code, game.to_redis_dict())

            if result.get('game_complete'):
                await self.broadcast_with_fallback(room_code, 'game_over', {'winner_team': result.get('round_winner')})
            else:
                # Start next round after delay
                print(f"[LOG] Scheduling next round for room {room_code}")
                asyncio.create_task(self._start_next_round_delayed(room_code, 3.0))
                
        except Exception as e:
            print(f"[ERROR] Failed to handle hand completion: {str(e)}")

    async def _start_next_round_delayed(self, room_code, delay_seconds):
        """Start next round after a delay"""
        await asyncio.sleep(delay_seconds)
        await self._start_next_round(room_code)

    async def _start_next_round(self, room_code):
        """Start the next round efficiently"""
        try:
            if room_code not in self.active_games:
                return

            game = self.active_games[room_code]
            if game.game_phase == "completed":
                return

            print(f"[LOG] Starting next round in room {room_code}")
            
            # Start new round
            initial_hands = game.start_new_round(self.redis_manager)
            if isinstance(initial_hands, dict) and "error" in initial_hands:
                print(f"[ERROR] Failed to start new round: {initial_hands['error']}")
                return

            # Get round info and broadcast
            round_info = game.get_new_round_info()
            
            await asyncio.gather(
                self.broadcast_with_fallback(room_code, 'phase_change', {'new_phase': GameState.WAITING_FOR_HOKM.value}),
                self.broadcast_with_fallback(room_code, 'new_round_start', round_info),
                return_exceptions=True
            )

            # Send initial hands
            await self._send_initial_hands(room_code, initial_hands, game)

            # Update game state
            await self.execute_with_timeout(self.redis_manager.save_game_state, REDIS_TIMEOUT, room_code, game.to_redis_dict())

            print(f"[LOG] Next round started successfully in room {room_code}")
            
        except Exception as e:
            print(f"[ERROR] Failed to start next round in room {room_code}: {str(e)}")

    async def handle_connection_closed(self, websocket):
        """Handle WebSocket connection closure efficiently"""
        try:
            # Clean up authentication
            self.auth_manager.disconnect_player(websocket)
            
            if websocket not in self.network_manager.connection_metadata:
                return
                
            metadata = self.network_manager.connection_metadata[websocket]
            room_code = metadata.get('room_code')
            player_id = metadata.get('player_id')
            
            if room_code:
                # Handle disconnection through network manager
                await self.network_manager.handle_player_disconnected(websocket, room_code, self.redis_manager)
                
                # Check if game should be cancelled
                game = self.active_games.get(room_code)
                if game:
                    active_count = self.get_room_player_count(room_code)
                    phase = getattr(game, 'game_phase', None)
                    
                    if (active_count < ROOM_SIZE and 
                        phase in (GameState.TEAM_ASSIGNMENT.value, GameState.WAITING_FOR_HOKM.value)):
                        
                        print(f"[LOG] Not enough players ({active_count}/{ROOM_SIZE}) in room {room_code}. Cancelling game.")
                        await self.broadcast_with_fallback(room_code, 'game_cancelled', {
                            'message': 'A player disconnected and not enough players remain. The game has been cancelled.'
                        })
                        self.active_games.pop(room_code, None)
                
        except Exception as e:
            print(f"[ERROR] Error handling connection closed: {str(e)}")
            # Clean up metadata
            try:
                if websocket in self.network_manager.connection_metadata:
                    del self.network_manager.connection_metadata[websocket]
            except Exception:
                pass

    async def handle_message(self, websocket, message):
        """Handle incoming WebSocket messages efficiently"""
        try:
            if not isinstance(message, dict) or 'type' not in message:
                await self.network_manager.notify_error(websocket, "Malformed message")
                return
            
            msg_type = message.get('type')
            
            # Handle authentication and reconnection messages first
            if msg_type in ['auth_login', 'auth_register', 'auth_token', 'reconnect']:
                if msg_type == 'reconnect':
                    await self._handle_reconnect(websocket, message)
                else:
                    await self.handle_authentication(websocket, message)
                return
            
            # Check authentication for all other messages
            if not self.auth_manager.is_authenticated(websocket):
                await self.network_manager.notify_error(websocket, "Authentication required")
                return
            
            # Route to appropriate handler
            handlers = {
                'join': self.handle_join,
                'hokm_selected': self.handle_hokm_selection,
                'play_card': self.handle_play_card,
                'health_check': self._handle_health_check
            }
            
            handler = handlers.get(msg_type)
            if handler:
                await handler(websocket, message)
            else:
                print(f"[WARNING] Unknown message type: {msg_type}")
                await self.network_manager.notify_error(websocket, f"Unknown message type: {msg_type}")
                
        except Exception as e:
            print(f"[ERROR] Failed to handle message: {str(e)}")
            await self.network_manager.notify_error(websocket, "Internal server error")

    async def handle_authentication(self, websocket, message):
        """Handle authentication messages efficiently"""
        try:
            msg_type = message.get('type')
            
            if msg_type == 'auth_login':
                username = message.get('username')
                password = message.get('password')
                
                if not username or not password:
                    await websocket.send(json.dumps({
                        'type': 'auth_response',
                        'success': False,
                        'message': 'Username and password are required'
                    }))
                    return
                
                auth_data = {'type': 'login', 'username': username, 'password': password}
                result = await self.auth_manager.authenticate_player(websocket, auth_data)
                
                response = {
                    'type': 'auth_response',
                    'success': result['success'],
                    'message': result['message']
                }
                
                if result['success']:
                    response['player_info'] = result['player_info']
                    print(f"[LOG] Player authenticated: {username}")
                
                await websocket.send(json.dumps(response))
                
            elif msg_type == 'auth_register':
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
                
                result = await asyncio.wait_for(
                    self.auth_manager.authenticate_player(websocket, auth_data),
                    timeout=30.0
                )
                
                response = {
                    'type': 'auth_response',
                    'success': result['success'],
                    'message': result['message']
                }
                
                if result['success']:
                    response['player_info'] = result['player_info']
                    print(f"[LOG] Player registered: {username}")
                
                await websocket.send(json.dumps(response))
                
        except (websockets.exceptions.ConnectionClosed, asyncio.TimeoutError) as e:
            print(f"[ERROR] Authentication error: {str(e)}")
        except Exception as e:
            print(f"[ERROR] Authentication error: {str(e)}")
            try:
                await websocket.send(json.dumps({
                    'type': 'auth_response',
                    'success': False,
                    'message': f'Authentication failed: {str(e)}'
                }))
            except Exception:
                pass

    async def _handle_reconnect(self, websocket, message):
        """Handle player reconnection efficiently"""
        player_id = message.get('player_id')
        if not player_id:
            await self.network_manager.notify_error(websocket, "Missing player_id for reconnection")
            return
            
        print(f"[LOG] Reconnection attempt for player_id: {player_id[:8]}...")
        success = await self.network_manager.handle_player_reconnected(websocket, player_id, self.redis_manager)
        
        if success:
            print(f"[LOG] Reconnection successful for player_id: {player_id[:8]}...")
        else:
            print(f"[LOG] Reconnection failed for player_id: {player_id[:8]}...")

    async def _handle_health_check(self, websocket, message):
        """Handle health check requests efficiently"""
        try:
            health_data = {
                'status': 'ok',
                'timestamp': time.time(),
                'server': {
                    'active_games': len(self.active_games),
                    'connected_clients': len(self.network_manager.connection_metadata)
                }
            }
            
            await websocket.send(json.dumps({
                'type': 'health_check_response',
                'data': health_data
            }))
            
        except Exception as e:
            print(f"[ERROR] Health check failed: {str(e)}")
            await self.network_manager.notify_error(websocket, f"Health check failed: {str(e)}")


async def main():
    """Main server function with optimized connection handling"""
    print("Starting Optimized Hokm WebSocket server on ws://0.0.0.0:8765")
    game_server = GameServer()

    async def handle_connection(websocket, path):
        """Handle new WebSocket connections with efficient ping/pong"""
        ping_task = None
        try:
            print(f"[LOG] New connection from {websocket.remote_address}")
            
            # Start ping task for connection health
            async def ping_client():
                try:
                    while True:
                        await asyncio.sleep(30)
                        pong_waiter = await websocket.ping()
                        await asyncio.wait_for(pong_waiter, timeout=10)
                except (asyncio.CancelledError, websockets.ConnectionClosed, asyncio.TimeoutError):
                    return
            
            ping_task = asyncio.create_task(ping_client())
            
            # Message handling loop
            async for message in websocket:
                try:
                    data = json.loads(message)
                    await game_server.handle_message(websocket, data)
                except json.JSONDecodeError:
                    await game_server.network_manager.notify_error(websocket, "Invalid message format")
                except Exception as e:
                    print(f"[ERROR] Failed to process message: {str(e)}")
                    await game_server.network_manager.notify_error(websocket, "Internal server error")
                    
        except websockets.ConnectionClosed:
            print(f"[LOG] Connection closed for {websocket.remote_address}")
        except Exception as e:
            print(f"[ERROR] Connection handler error: {str(e)}")
        finally:
            if ping_task:
                ping_task.cancel()
            await game_server.handle_connection_closed(websocket)
    
    # Start server
    print("[DEBUG] Starting WebSocket server...")
    async with websockets.serve(
        handle_connection, 
        "0.0.0.0", 
        8765,
        ping_timeout=300,
        close_timeout=300
    ):
        print("[LOG] WebSocket server is now listening on ws://0.0.0.0:8765")
        await asyncio.Future()  # Run forever

if __name__ == "__main__":
    asyncio.run(main())
