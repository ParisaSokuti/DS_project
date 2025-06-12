# server.py

import asyncio
import sys
import websockets
import json
import uuid
import random
import time
from .network import NetworkManager
from .game_board import GameBoard
from .game_states import GameState
from .redis_manager import RedisManager

# Constants
ROOM_SIZE = 4    # Single game storage system

class GameServer:
    def __init__(self):
        self.redis_manager = RedisManager()
        self.network_manager = NetworkManager()
        self.active_games = {}  # Maps room_code -> GameBoard for active games only
        self.load_active_games_from_redis()  # Load active games on startup

    def load_active_games_from_redis(self):
        """Load all active games from Redis into self.active_games on server startup."""
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
                        print(f"[LOG] Recovered active game for room {room_code} with players: {players}")
                except Exception as e:
                    print(f"[ERROR] Failed to recover game for key {key}: {str(e)}")
        except Exception as e:
            print(f"[ERROR] Failed to scan Redis for active games: {str(e)}")

    async def handle_join(self, websocket, data):
        """Handle a new player joining with separated connection and state management"""
        try:
            room_code = data.get('room_code', '9999')
            
            # Validate room exists or can be created
            if not self.redis_manager.room_exists(room_code):
                try:
                    self.redis_manager.create_room(room_code)
                    print(f"[LOG] Room {room_code} created successfully")
                except Exception as e:
                    print(f"[ERROR] Failed to create room {room_code}: {str(e)}")
                    await self.network_manager.notify_error(websocket, "Failed to create game room")
                    return None

            # Check if game is cancelled due to not enough players (after a disconnect)
            game = self.active_games.get(room_code)
            if game:
                phase = getattr(game, 'game_phase', None)
                connected_players = [p for p in self.redis_manager.get_room_players(room_code) if p.get('connection_status') == 'active']
                if len(connected_players) < ROOM_SIZE and (
                    phase == GameState.TEAM_ASSIGNMENT.value or
                    (hasattr(GameState, 'WAITING_FOR_HOKM') and phase == GameState.WAITING_FOR_HOKM.value) or
                    (phase == 'waiting_for_hokm')
                ):
                    print(f"[LOG] Not enough players in room {room_code} during join (phase: {phase}). Cancelling game.")
                    await self.network_manager.notify_error(websocket, "Game was cancelled due to player disconnect.")
                    await self.network_manager.broadcast_to_room(
                        room_code,
                        'game_cancelled',
                        {'message': 'A player disconnected and not enough players remain. The game has been cancelled.'},
                        self.redis_manager
                    )
                    if room_code in self.active_games:
                        del self.active_games[room_code]
                    self.redis_manager.delete_game_state(room_code)
                    return None

            # Check if room is full
            room_players = self.redis_manager.get_room_players(room_code)
            if len(room_players) >= ROOM_SIZE:
                await self.network_manager.notify_error(websocket, "Room is full")
                return None

            # Create new player with unique ID and name
            player_id = str(uuid.uuid4())
            player_number = len(room_players) + 1
            username = f"Player {player_number}"

            # Save session data to Redis
            session_data = {
                'username': username,
                'room_code': room_code,
                'connected_at': str(int(time.time())),
                'expires_at': str(int(time.time()) + 3600),
                'player_number': player_number,
                'connection_status': 'active'
            }
            self.redis_manager.save_player_session(player_id, session_data)

            # Register live connection
            self.network_manager.register_connection(websocket, player_id, room_code)

            # Add to room
            room_data = {
                'player_id': player_id,
                'username': username,
                'player_number': player_number,
                'joined_at': str(int(time.time())),
                'connection_status': 'active'
            }
            self.redis_manager.add_player_to_room(room_code, room_data)

            # Send join confirmation
            print(f"[LOG] Room {room_code}: {username} joined [PHASE: {GameState.WAITING_FOR_PLAYERS.value}] - Players: {len(room_players) + 1}/4")
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
            if len(room_players) + 1 >= ROOM_SIZE:
                print(f"[LOG] Room {room_code} is full, ready to play! [PHASE: {GameState.TEAM_ASSIGNMENT.value}]")
                await self.handle_game_start(room_code)

            return True

        except Exception as e:
            print(f"[ERROR] Failed to handle join: {str(e)}")
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
            
            # Get all players in room
            players = [p['username'] for p in self.redis_manager.get_room_players(room_code)]
            
            # Create new game instance
            game = GameBoard(players, room_code)
            self.active_games[room_code] = game
            
            # Assign teams and get initial state
            team_result = game.assign_teams_and_hakem(self.redis_manager)
            
            # Save initial game state
            game_state = game.to_redis_dict()
            self.redis_manager.save_game_state(room_code, game_state)
            
            # Broadcast phase change to TEAM_ASSIGNMENT
            await self.network_manager.broadcast_to_room(
                room_code,
                'phase_change',
                {'new_phase': GameState.TEAM_ASSIGNMENT.value},
                self.redis_manager
            )
            
            # Broadcast team assignments
            await self.network_manager.broadcast_to_room(
                room_code,
                'team_assignment',
                team_result,
                self.redis_manager
            )
            
            # Deal initial cards
            initial_hands = game.initial_deal()
            
            # Transition to waiting for hokm phase
            game.game_phase = GameState.WAITING_FOR_HOKM.value
            game_state = game.to_redis_dict()
            self.redis_manager.save_game_state(room_code, game_state)
            
            # Broadcast phase change to WAITING_FOR_HOKM - CRITICAL for hokm selection
            print(f"[LOG] Broadcasting phase change to WAITING_FOR_HOKM in room {room_code}")
            await self.network_manager.broadcast_to_room(
                room_code,
                'phase_change',
                {'new_phase': GameState.WAITING_FOR_HOKM.value},
                self.redis_manager
            )
            
            # Send initial hands to players
            for player in self.redis_manager.get_room_players(room_code):
                ws = self.network_manager.get_live_connection(player['player_id'])
                if ws:
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
            room_code = self.network_manager.connection_metadata[websocket]['room_code']
            await self.network_manager.handle_player_disconnected(
                websocket,
                room_code,
                self.redis_manager
            )
            # Remove connection metadata for this websocket
            if websocket in self.network_manager.connection_metadata:
                del self.network_manager.connection_metadata[websocket]
            # Check if game is in TEAM_ASSIGNMENT or hokm selection phase and not enough live connections in this room
            game = self.active_games.get(room_code)
            if game:
                phase = getattr(game, 'game_phase', None)
                # Count live connections for this room
                active_conn_count = sum(
                    1 for meta in self.network_manager.connection_metadata.values()
                    if meta.get('room_code') == room_code
                )
                if active_conn_count < ROOM_SIZE and phase in (
                    GameState.TEAM_ASSIGNMENT.value,
                    GameState.WAITING_FOR_HOKM.value
                ):
                    print(f"[LOG] Not enough players ({active_conn_count}/{ROOM_SIZE}) during {phase} in room {room_code}. Cancelling game.")
                    await self.network_manager.broadcast_to_room(
                        room_code,
                        'game_cancelled',
                        {'message': 'A player disconnected and not enough players remain. The game has been cancelled.'},
                        self.redis_manager
                    )
                    # Clean up game
                    self.active_games.pop(room_code, None)
                    self.redis_manager.delete_game_state(room_code)
        except Exception as e:
            print(f"[ERROR] Error handling connection closure: {str(e)}")

    async def handle_message(self, websocket, message):
        """Handle incoming WebSocket messages"""
        try:
            if not isinstance(message, dict):
                await self.network_manager.notify_error(websocket, "Malformed message: not a JSON object.")
                return
            msg_type = message.get('type')
            if not msg_type:
                await self.network_manager.notify_error(websocket, "Malformed message: missing 'type' field.")
                return
            if msg_type == 'join':
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
                await self.network_manager.handle_player_reconnected(
                    websocket,
                    player_id,
                    self.redis_manager
                )
                # Find the player's room and username
                room_code = None
                username = None
                for code in self.active_games:
                    for p in self.redis_manager.get_room_players(code):
                        if p['player_id'] == player_id:
                            room_code = code
                            username = p['username']
                            break
                    if room_code:
                        break
                if room_code and username:
                    game = self.active_games.get(room_code)
                    if game:
                        # Send current hand, phase, and turn info
                        hand = game.hands.get(username, [])
                        is_hakem = (username == game.hakem)
                        await self.network_manager.send_message(
                            websocket,
                            'reconnect_success',
                            {
                                'hand': hand,
                                'is_hakem': is_hakem,
                                'hakem': game.hakem,
                                'hokm': getattr(game, 'hokm', None),
                                'phase': getattr(game, 'game_phase', None),
                                'current_turn': getattr(game, 'current_turn', None),
                                'your_turn': (game.players[game.current_turn] == username) if hasattr(game, 'current_turn') and hasattr(game, 'players') else False
                            }
                        )
                else:
                    await self.network_manager.notify_error(websocket, "Could not restore session: player not found in any active game.")
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
            else:
                print(f"[WARNING] Unknown message type: {msg_type}")
                await self.network_manager.notify_error(websocket, f"Unknown message type: {msg_type}")
        except Exception as e:
            print(f"[ERROR] Failed to handle message: {str(e)}")
            try:
                await self.network_manager.notify_error(websocket, f"Internal server error: {str(e)}")
            except Exception as notify_err:
                print(f"[ERROR] Failed to notify user of message error: {notify_err}")

    async def handle_hokm_selection(self, websocket, message):
        """Handle hokm selection by the Hakem, save state, broadcast, and deal remaining cards."""
        try:
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
            # Save state after hokm selection
            game_state = game.to_redis_dict()
            self.redis_manager.save_game_state(room_code, game_state)
            # Broadcast hokm selection
            await self.network_manager.broadcast_to_room(
                room_code,
                'hokm_selected',
                {'suit': game.hokm, 'hakem': game.hakem},
                self.redis_manager
            )
            # Phase change: FINAL_DEAL
            game.game_phase = GameState.FINAL_DEAL.value if hasattr(GameState, 'FINAL_DEAL') else 'final_deal'
            game_state = game.to_redis_dict()
            self.redis_manager.save_game_state(room_code, game_state)
            
            # Broadcast phase change - CRITICAL for game progression
            print(f"[LOG] Broadcasting phase change to FINAL_DEAL in room {room_code}")
            await self.network_manager.broadcast_to_room(
                room_code,
                'phase_change',
                {'new_phase': game.game_phase},
                self.redis_manager
            )
            # Deal remaining cards and save state
            final_hands = game.final_deal(self.redis_manager)
            for player in self.redis_manager.get_room_players(room_code):
                ws = self.network_manager.get_live_connection(player['player_id'])
                if ws:
                    await self.network_manager.send_message(
                        ws,
                        'final_deal',
                        {
                            'hand': final_hands[player['username']],
                            'hokm': game.hokm
                        }
                    )
            # Save state after final deal
            game_state = game.to_redis_dict()
            self.redis_manager.save_game_state(room_code, game_state)
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
            player, player_id = self.find_player_by_websocket(websocket, room_code)
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
            result = game.play_card(player, card, self.redis_manager)
            # Handle invalid play (e.g., suit-follow violation)
            if not result.get('valid', True):
                await self.network_manager.notify_error(websocket, result.get('message', 'Invalid move'))
                return
            # Save state after card play
            game_state = game.to_redis_dict()
            self.redis_manager.save_game_state(room_code, game_state)
            # Broadcast card play
            await self.network_manager.broadcast_to_room(
                room_code,
                'card_played',
                {'player': player, 'card': card, 'team': game.teams.get(player, 0) + 1, 'player_id': player_id},
                self.redis_manager
            )
            
            # Send turn_start for next player if trick is not complete
            if not result.get('trick_complete'):
                next_player = result.get('next_turn')
                if next_player:
                    for player_info in self.redis_manager.get_room_players(room_code):
                        ws = self.network_manager.get_live_connection(player_info['player_id'])
                        if ws:
                            await self.network_manager.send_message(
                                ws,
                                "turn_start",
                                {
                                    "current_player": next_player,
                                    "your_turn": player_info['username'] == next_player,
                                    "hand": game.hands[player_info['username']][:],
                                    "hokm": game.hokm
                                }
                            )
            
            # If trick complete, broadcast trick result and save state
            if result.get('trick_complete'):
                await self.network_manager.broadcast_to_room(
                    room_code,
                    'trick_result',
                    {
                        'winner': result.get('trick_winner'),
                        'team1_tricks': result.get('team_tricks', {}).get(0, 0),
                        'team2_tricks': result.get('team_tricks', {}).get(1, 0)
                    },
                    self.redis_manager
                )
                # Save state after trick
                game_state = game.to_redis_dict()
                self.redis_manager.save_game_state(room_code, game_state)
                
                # Send turn_start for trick winner to start next trick (unless hand is complete)
                if not result.get('hand_complete'):
                    trick_winner = result.get('trick_winner')
                    if trick_winner:
                        for player_info in self.redis_manager.get_room_players(room_code):
                            ws = self.network_manager.get_live_connection(player_info['player_id'])
                            if ws:
                                await self.network_manager.send_message(
                                    ws,
                                    "turn_start",
                                    {
                                        "current_player": trick_winner,
                                        "your_turn": player_info['username'] == trick_winner,
                                        "hand": game.hands[player_info['username']][:],
                                        "hokm": game.hokm
                                    }
                                )
                
                # If hand complete, broadcast hand and round completion and save state
                if result.get('hand_complete'):
                    # Fix the winning_team calculation to prevent negative values
                    round_winner = result.get('round_winner', 1)  # Default to team 1 if missing
                    winning_team = max(0, round_winner - 1) if round_winner > 0 else 0  # Ensure it's 0 or 1, never negative
                    
                    # Broadcast hand completion with proper data types
                    await self.network_manager.broadcast_to_room(
                        room_code,
                        'hand_complete',
                        {
                            'winning_team': winning_team,  # Always 0 or 1
                            'tricks': result.get('team_tricks', {0: 0, 1: 0}),
                            'round_winner': round_winner,  # Always 1 or 2
                            'round_scores': result.get('round_scores', {0: 0, 1: 0}),
                            'game_complete': result.get('game_complete', False)
                        },
                        self.redis_manager
                    )
                    # Save state after hand completion
                    game_state = game.to_redis_dict()
                    self.redis_manager.save_game_state(room_code, game_state)

                    # Broadcast game_over if game is complete
                    if result.get('game_complete'):
                        await self.network_manager.broadcast_to_room(
                            room_code,
                            'game_over',
                            {'winner_team': result.get('round_winner')},
                            self.redis_manager
                        )
        except Exception as e:
            print(f"[ERROR] Failed to handle play_card: {str(e)}")
            await self.network_manager.notify_error(websocket, f"Failed to handle play_card: {str(e)}")

    async def start_first_trick(self, room_code):
        """Initialize the first trick after hokm selection"""
        game = self.active_games[room_code]
        game.current_turn = 0  # Hakem leads first trick
        first_player = game.players[game.current_turn]
        
        print(f"\n=== Starting first trick in room {room_code} ===")
        print(f"{first_player} (Hakem) leads the first trick")
        
        # Update phase to gameplay
        game.game_phase = GameState.GAMEPLAY.value
        
        # Save updated game state after initiating first trick
        game_state = game.to_redis_dict()
        self.redis_manager.save_game_state(room_code, game_state)
        
        # Broadcast phase change to gameplay
        await self.network_manager.broadcast_to_room(
            room_code,
            'phase_change',
            {'new_phase': GameState.GAMEPLAY.value},
            self.redis_manager
        )
        
        # Notify all players whose turn it is
        for player in self.redis_manager.get_room_players(room_code):
            ws = self.network_manager.get_live_connection(player['player_id'])
            if ws:
                await self.network_manager.send_message(
                    ws,
                    "turn_start",
                    {
                        "current_player": first_player,
                        "your_turn": player['username'] == first_player,
                        "hand": game.hands[player['username']][:]
                    }
                )

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

    def find_player_by_websocket(self, websocket, room_code):
        """Enhanced player lookup with multiple fallback mechanisms"""
        room_players = self.redis_manager.get_room_players(room_code)
        
        # Method 1: Check connection metadata
        if websocket in self.network_manager.connection_metadata:
            conn_data = self.network_manager.connection_metadata[websocket]
            player_id = conn_data.get('player_id')
            if player_id:
                for p in room_players:
                    if p.get('player_id') == player_id:
                        return p.get('username'), player_id
        
        # Method 2: Check live connections
        if websocket in self.network_manager.live_connections:
            player_id = self.network_manager.live_connections[websocket]
            for p in room_players:
                if p.get('player_id') == player_id:
                    return p.get('username'), player_id
        
        # Method 3: Find by room code match in connection metadata
        for p in room_players:
            if p.get('connection_status') == 'active':
                # Try to find websocket for this player
                for ws, conn_data in self.network_manager.connection_metadata.items():
                    if (conn_data.get('room_code') == room_code and 
                        conn_data.get('player_id') == p.get('player_id')):
                        if ws == websocket:
                            return p.get('username'), p.get('player_id')
        
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
            self.network_manager.register_connection(websocket, new_player_id, room_code)
            
            print(f"[LOG] Repaired connection for {username} in room {room_code}")
            return new_player_id
            
        except Exception as e:
            print(f"[ERROR] Failed to repair connection for {username}: {str(e)}")
            return None

async def cleanup_task():
    """Periodic task to cleanup expired sessions, inactive rooms, and stale connections"""
    while True:
        try:
            # Get instances
            network_mgr = NetworkManager()
            redis_mgr = RedisManager()
            
            # Cleanup expired sessions from Redis
            redis_mgr.cleanup_expired_sessions()
            
            current_time = int(time.time())
            
            # Check and cleanup stale connections
            for ws, metadata in list(network_mgr.connection_metadata.items()):
                connected_at = metadata.get('connected_at', 0)
                if current_time - connected_at > 7200:  # 2 hours without reconnection
                    print(f"[LOG] Removing stale connection for player {metadata.get('player_id')}")
                    network_mgr.remove_connection(ws)
            
            # Check for inactive rooms in Redis by scanning for room keys
            for key in redis_mgr.redis.scan_iter("room:*:players"):
                try:
                    room_code = key.decode().split(':')[1]  # Extract room code from key
                    if redis_mgr.room_exists(room_code):
                        game_state = redis_mgr.get_game_state(room_code)
                        if game_state:
                            last_activity = int(game_state.get('last_activity', '0'))
                            if current_time - last_activity > 3600:  # 1 hour inactivity
                                print(f"[LOG] Cleaning up inactive room {room_code}")
                                redis_mgr.delete_room(room_code)
                                
                                # Remove from active games if exists
                                if room_code in GameServer().active_games:
                                    del GameServer().active_games[room_code]
                except Exception as e:
                    print(f"[ERROR] Error checking room {room_code}: {str(e)}")
                    
        except Exception as e:
            print(f"[ERROR] Error in cleanup task: {str(e)}")
            
        await asyncio.sleep(300)  # Run every 5 minutes

async def main():
    print("Starting Hokm WebSocket server on ws://0.0.0.0:8765")
    global game_server
    game_server = GameServer()
    game_server.load_active_games_from_redis()

    async def handle_connection(websocket, path):
        """Handle new WebSocket connections"""
        try:
            print(f"[LOG] New connection from {websocket.remote_address}")
            async for message in websocket:
                try:
                    data = json.loads(message)
                    await game_server.handle_message(websocket, data)
                except json.JSONDecodeError:
                    await game_server.network_manager.notify_error(websocket, "Invalid message format")
                except Exception as e:
                    print(f"[ERROR] Failed to process message: {str(e)}")
                    try:
                        await game_server.network_manager.notify_error(websocket, f"Internal server error: {str(e)}")
                    except Exception as notify_err:
                        print(f"[ERROR] Failed to notify user of connection error: {notify_err}")
        except websockets.ConnectionClosed:
            await game_server.handle_connection_closed(websocket)
        except Exception as e:
            print(f"[ERROR] Connection handler error: {str(e)}")
            try:
                await game_server.network_manager.notify_error(websocket, f"Connection handler error: {str(e)}")
            except Exception as notify_err:
                print(f"[ERROR] Failed to notify user of connection handler error: {notify_err}")
    
    # Start cleanup task
    cleanup_loop = asyncio.create_task(cleanup_task())
    
    try:
        async with websockets.serve(handle_connection, "0.0.0.0", 8765):
            await asyncio.Future()  # Run forever
    except Exception as e:
        print(f"[ERROR] Server error: {str(e)}")
    finally:
        cleanup_loop.cancel()
        try:
            await cleanup_loop
        except asyncio.CancelledError:
            pass

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServer shutting down...")
    except Exception as e:
        print(f"[ERROR] Fatal error: {str(e)}")
        sys.exit(1)
