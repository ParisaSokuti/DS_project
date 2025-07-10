# redis_manager.py
import redis
import json
import time
from typing import Dict, List, Optional, Any, Tuple

class RedisManager:
    def __init__(self):
        self.redis = redis.Redis(
            host='localhost', 
            port=6379, 
            db=0,
            socket_timeout=5.0,  # 5 second timeout for socket operations
            socket_connect_timeout=3.0,  # 3 second timeout for connection
            socket_keepalive=True,
            socket_keepalive_options={}
        )
        self.connection_timeout = 30  # Connection timeout in seconds
        self.heartbeat_interval = 10  # Heartbeat check interval
        self.metrics = {
            'operations': 0,
            'errors': 0,
            'latency_sum': 0
        }
        self.valid_phases = ['waiting_for_players', 'team_assignment', 'initial_deal', 'hokm_selection', 'final_deal', 'gameplay', 'hand_complete', 'game_over', 'completed']
    
    def _measure_latency(self, start_time: float) -> None:
        """Update performance metrics"""
        elapsed = time.time() - start_time
        self.metrics['latency_sum'] += elapsed
        self.metrics['operations'] += 1
        
    def get_performance_metrics(self) -> dict:
        """Get current performance metrics"""
        ops = self.metrics['operations']
        return {
            'total_operations': ops,
            'error_rate': self.metrics['errors'] / ops if ops > 0 else 0,
            'avg_latency': self.metrics['latency_sum'] / ops if ops > 0 else 0
        }
        
    def save_player_session(self, player_id: str, session_data: dict):
        """Save player session with enhanced monitoring"""
        try:
            key = f"session:{player_id}"
            # Update session data but preserve existing connection_status if not provided
            updated_data = {
                'last_heartbeat': str(int(time.time()))
            }
            # Only set connection_status to 'active' if not already specified in session_data
            if 'connection_status' not in session_data:
                updated_data['connection_status'] = 'active'
            
            updated_data.update(session_data)
            self.redis.hset(key, mapping=updated_data)
            self.redis.expire(key, 3600)  # Session expires in 1 hour
            return True
        except Exception as e:
            print(f"[ERROR] Failed to save session for {player_id}: {str(e)}")
            return False
    
    def get_player_session(self, player_id: str) -> dict:
        key = f"session:{player_id}"
        return {k.decode(): v.decode() for k, v in self.redis.hgetall(key).items()}
    
    def add_player_to_room(self, room_code: str, player_data: dict):
        key = f"room:{room_code}:players"
        try:
            print(f"[DEBUG] Adding player to room {room_code}: {player_data.get('username', 'NO_NAME')}")
            self.redis.rpush(key, json.dumps(player_data))
            # Refresh expiration whenever we modify the list
            self.redis.expire(key, 3600)
            print(f"[DEBUG] Player added and expiration refreshed for room {room_code}")
        except Exception as e:
            print(f"[ERROR] Failed to add player to room {room_code}: {str(e)}")
        
    def get_room_players(self, room_code: str) -> List[dict]:
        key = f"room:{room_code}:players"
        try:
            # Debug: check if key exists
            exists = self.redis.exists(key)
            print(f"[DEBUG] get_room_players for {room_code}: key exists = {exists}")
            
            if not exists:
                print(f"[DEBUG] Room players key does not exist: {key}")
                return []
                
            players = self.redis.lrange(key, 0, -1)
            print(f"[DEBUG] Raw players data from Redis: {len(players)} entries")
            for i, p in enumerate(players):
                print(f"[DEBUG]   Player {i+1}: {p[:100]}...")  # First 100 chars
                
            result = [json.loads(p.decode()) for p in players]
            print(f"[DEBUG] Parsed {len(result)} players from Redis")
            return result
        except Exception as e:
            print(f"[ERROR] Failed to get room players for {room_code}: {str(e)}")
            return []
    
    def save_game_state(self, room_code: str, game_state: dict) -> bool:
        """Save game state with proper encoding, validation, and transaction support"""
        start_time = time.time()
        try:
            # Add required fields if missing
            if 'created_at' not in game_state:
                game_state['created_at'] = str(int(time.time()))
            if 'last_activity' not in game_state:
                game_state['last_activity'] = str(int(time.time()))
                
            # Validate state before saving (now that required fields are added)
            is_valid, error = self.validate_game_state(game_state)
            if not is_valid:
                print(f"[WARNING] Game state validation failed for room {room_code}: {error}")
                print(f"[WARNING] Saving anyway to prevent data loss...")
                # Don't raise exception - just log warning and continue
                
            pipe = self.redis.pipeline()
            key = f"game:{room_code}:state"
            
            # Encode state
            encoded_state = {}
            for k, v in game_state.items():
                if isinstance(v, (dict, list)):
                    encoded_state[k] = json.dumps(v)
                else:
                    encoded_state[k] = str(v)
                    
            # Execute transaction
            pipe.hset(key, mapping=encoded_state)
            pipe.expire(key, 3600)
            pipe.execute()
            
            print(f"[DEBUG] Successfully saved game state for room {room_code} with phase: {game_state.get('phase', 'UNKNOWN')}")
            
            self._measure_latency(start_time)
            return True
            
        except Exception as e:
            self.metrics['errors'] += 1
            print(f"[ERROR] Save game state failed for room {room_code}: {str(e)}")
            return False

    def get_game_state(self, room_code: str) -> dict:
        """Get game state with proper decoding"""
        print(f"[DEBUG] get_game_state START for room {room_code}")
        import time
        import signal
        start_time = time.time()
        
        # Add timeout handler
        def timeout_handler(signum, frame):
            raise TimeoutError("Redis operation timed out")
        
        try:
            key = f"game:{room_code}:state"
            print(f"[DEBUG] Step 1: About to call hgetall on key: {key}")
            
            # Set a manual timeout of 10 seconds
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(10)  # 10 second timeout
            
            try:
                raw_state = self.redis.hgetall(key)
                signal.alarm(0)  # Cancel the timeout
                print(f"[DEBUG] Step 2: hgetall completed, raw_state type: {type(raw_state)}, items: {len(raw_state)}")
            except TimeoutError:
                signal.alarm(0)  # Cancel the timeout
                print(f"[ERROR] Redis hgetall timed out after 10 seconds")
                elapsed = time.time() - start_time
                print(f"[DEBUG] get_game_state END (timeout, {elapsed:.2f}s)")
                return {}
            
            if not raw_state:
                print(f"[WARNING] No state found for room {room_code}")
                elapsed = time.time() - start_time
                print(f"[DEBUG] get_game_state END (no state, {elapsed:.2f}s)")
                return {}
                
            print(f"[DEBUG] Step 3: Decoding bytes to string...")
            # Decode bytes to string
            state = {k.decode(): v.decode() for k, v in raw_state.items()}
            print(f"[DEBUG] Step 4: Decoded {len(state)} items")
            
            print(f"[DEBUG] Step 5: Processing JSON values...")
            # Try to decode JSON values
            for k, v in list(state.items()):  # Use list to allow dict modification
                try:
                    if k in ['teams', 'players', 'tricks', 'player_order'] or k.startswith('hand_'):
                        print(f"[DEBUG] Step 5.{k}: Parsing JSON for {k}")
                        state[k] = json.loads(v)
                        print(f"[DEBUG] Step 5.{k}: JSON parsing successful")
                except json.JSONDecodeError as e:
                    print(f"[WARNING] Failed to decode JSON for key {k}: {str(e)}")
                    pass  # Keep as string if not valid JSON
                except Exception as e:
                    print(f"[ERROR] Unexpected error processing key {k}: {str(e)}")
                    
            elapsed = time.time() - start_time
            print(f"[DEBUG] get_game_state END (success, {elapsed:.2f}s)")
            return state
        except Exception as e:
            elapsed = time.time() - start_time
            print(f"[ERROR] Failed to get game state for room {room_code}: {str(e)}")
            print(f"[DEBUG] get_game_state END (error, {elapsed:.2f}s)")
            import traceback
            traceback.print_exc()
            return {}
    
    def clear_room(self, room_code: str):
        """Clean up room data"""
        self.redis.delete(f"room:{room_code}:players")
        self.redis.delete(f"game:{room_code}:state")

    def room_exists(self, room_code: str) -> bool:
        """Check if a room exists and is valid"""
        try:
            players_key = f"room:{room_code}:players"
            state_key = f"game:{room_code}:state"
            
            # Check if game state exists (this is the primary indicator)
            state_exists = bool(self.redis.exists(state_key))
            
            # For players, check if the key exists OR if it's tracked in state
            # (empty lists don't exist in Redis, but the room can still be valid)
            players_key_exists = bool(self.redis.exists(players_key))
            
            # A room is valid if it has game state
            # Players list may be empty (and thus not exist) for new rooms
            return state_exists
        except Exception as e:
            print(f"[ERROR] Failed to check room {room_code} existence: {str(e)}")
            return False

    def create_room(self, room_code: str):
        """Create a new room with proper initialization"""
        try:
            # Create room keys
            players_key = f"room:{room_code}:players"
            state_key = f"game:{room_code}:state"
            
            # Clear any existing data
            self.redis.delete(players_key)
            self.redis.delete(state_key)
            
            # Initialize empty room state
            self.redis.hset(state_key, "phase", "waiting_for_players")
            self.redis.hset(state_key, "created_at", str(int(time.time())))
            
            # Initialize players list as empty but existing
            # Add a placeholder and remove it to create the list structure
            self.redis.rpush(players_key, json.dumps({"placeholder": True}))
            self.redis.lrem(players_key, 1, json.dumps({"placeholder": True}))
            
            # Ensure the list exists even if empty by setting expiration
            self.redis.expire(players_key, 3600)  # 1 hour expiration
            
            print(f"[LOG] Created room {room_code}")
            return True
        except Exception as e:
            print(f"[ERROR] Failed to create room {room_code}: {str(e)}")
            return False

    def delete_room(self, room_code: str):
        """Delete a room and all associated data"""
        self.clear_room(room_code)  # This cleans up game state and player list
        
        # Also clean up any other room-related keys
        for key in self.redis.scan_iter(f"*{room_code}*"):
            self.redis.delete(key)
            
    def delete_player_session(self, player_id: str):
        """Delete a player's session data"""
        try:
            key = f"session:{player_id}"
            self.redis.delete(key)
        except Exception as e:
            print(f"[ERROR] Failed to delete player session {player_id}: {str(e)}")
            
    def cleanup_expired_sessions(self):
        """Clean up expired player sessions"""
        try:
            current_time = int(time.time())
            for key in self.redis.scan_iter("session:*"):
                try:
                    session = self.redis.hgetall(key)
                    if not session:
                        continue
                        
                    expires_at = int(session.get(b'expires_at', b'0').decode())
                    if expires_at < current_time:
                        self.redis.delete(key)
                        print(f"[LOG] Cleaned up expired session: {key}")
                        
                except Exception as e:
                    print(f"[ERROR] Error processing session {key}: {str(e)}")
                    
        except Exception as e:
            print(f"[ERROR] Error in cleanup_expired_sessions: {str(e)}")
    
    def update_player_heartbeat(self, player_id: str) -> bool:
        """Update player's last heartbeat timestamp"""
        try:
            key = f"session:{player_id}"
            current_time = str(int(time.time()))
            self.redis.hset(key, 'last_heartbeat', current_time)
            return True
        except Exception as e:
            print(f"[ERROR] Failed to update heartbeat for {player_id}: {str(e)}")
            return False

    def check_player_connection(self, player_id: str) -> str:
        """Check if player connection is still active"""
        try:
            session = self.get_player_session(player_id)
            if not session:
                return 'disconnected'
                
            last_heartbeat = int(session.get('last_heartbeat', '0'))
            current_time = int(time.time())
            
            if current_time - last_heartbeat > self.connection_timeout:
                self.mark_player_disconnected(player_id)
                return 'disconnected'
            return 'active'
        except Exception as e:
            print(f"[ERROR] Failed to check connection for {player_id}: {str(e)}")
            return 'unknown'

    def mark_player_disconnected(self, player_id: str):
        """Mark a player as disconnected"""
        try:
            key = f"session:{player_id}"
            self.redis.hset(key, 'connection_status', 'disconnected')
            session = self.get_player_session(player_id)
            if 'room_code' in session:
                self.handle_player_disconnect_from_room(session['room_code'], player_id)
        except Exception as e:
            print(f"[ERROR] Failed to mark player {player_id} as disconnected: {str(e)}")

    def handle_player_disconnect_from_room(self, room_code: str, player_id: str):
        """Handle cleanup when a player disconnects from a room"""
        try:
            players = self.get_room_players(room_code)
            updated_players = [p for p in players if p.get('player_id') != player_id]
            
            # Clear and update player list
            key = f"room:{room_code}:players"
            self.redis.delete(key)
            for player in updated_players:
                self.redis.rpush(key, json.dumps(player))
                
            # Update game state if needed
            if not updated_players:
                self.clear_room(room_code)
        except Exception as e:
            print(f"[ERROR] Failed to handle disconnect for player {player_id}: {str(e)}")

    def validate_session(self, player_id: str) -> Tuple[bool, str]:
        """
        Validate a player session and attempt recovery if possible
        Returns: (is_valid: bool, message: str)
        """
        try:
            session = self.get_player_session(player_id)
            if not session:
                return False, "Session not found"
                
            current_time = int(time.time())
            last_heartbeat = int(session.get('last_heartbeat', '0'))
            
            # Check if session is still within valid timeframe
            if current_time - last_heartbeat > self.connection_timeout:
                # Try to recover session if it's not too old (within 2x timeout)
                if current_time - last_heartbeat <= (self.connection_timeout * 2):
                    self.update_player_heartbeat(player_id)
                    return True, "Session recovered"
                else:
                    self.delete_player_session(player_id)
                    return False, "Session expired"
                    
            return True, "Session valid"
            
        except Exception as e:
            print(f"[ERROR] Session validation failed for {player_id}: {str(e)}")
            return False, "Session validation error"
            
    def attempt_reconnect(self, player_id: str, connection_data: dict) -> Tuple[bool, dict]:
        """
        Attempt to reconnect a player to their previous session
        Returns: (success: bool, session_data: dict)
        """
        try:
            is_valid, message = self.validate_session(player_id)
            
            if not is_valid:
                return False, {"error": message}
                
            # Update session with new connection data
            session = self.get_player_session(player_id)
            session.update(connection_data)
            session['connection_status'] = 'active'
            
            if self.save_player_session(player_id, session):
                return True, session
            else:
                return False, {"error": "Failed to update session"}
                
        except Exception as e:
            print(f"[ERROR] Reconnection failed for {player_id}: {str(e)}")
            return False, {"error": "Reconnection error"}
    
    def validate_game_state(self, state: dict) -> Tuple[bool, str]:
        """Validate game state structure and data"""
        try:
            # Required fields
            required = ['phase', 'created_at', 'last_activity']
            for field in required:
                if field not in state:
                    return False, f"Missing required field: {field}"
                    
            # Phase validation
            if state['phase'] not in self.valid_phases:
                return False, f"Invalid game phase: {state['phase']}"
                
            # Team validation if in team_assignment or later
            if state['phase'] != 'waiting_for_players':
                if 'teams' not in state:
                    return False, f"Teams required for phase: {state['phase']}"
                teams = json.loads(state['teams']) if isinstance(state['teams'], str) else state['teams']
                if not isinstance(teams, dict) or len(teams) != 4:
                    return False, "Invalid team structure - expected 4 players with team assignments"
                # Validate that all team values are 0 or 1
                for player, team in teams.items():
                    if team not in [0, 1]:
                        return False, f"Invalid team assignment for player {player}: {team}"
                    
            return True, ""
        except Exception as e:
            return False, str(e)
    
    def get_active_rooms(self) -> List[str]:
        """Get all active room codes from Redis"""
        try:
            room_codes = []
            for key in self.redis.scan_iter("game:*:state"):
                # Extract room code from key format "game:ROOM_CODE:state"
                room_code = key.decode().split(':')[1]
                if self.room_exists(room_code):
                    room_codes.append(room_code)
            return room_codes
        except Exception as e:
            print(f"[ERROR] Failed to get active rooms: {str(e)}")
            return []
            
    def delete_game_state(self, room_code: str):
        """Delete game state for a room"""
        try:
            key = f"game:{room_code}:state"
            self.redis.delete(key)
            print(f"[LOG] Deleted game state for room {room_code}")
        except Exception as e:
            print(f"[ERROR] Failed to delete game state for room {room_code}: {str(e)}")

    def is_game_completed(self, room_code: str) -> bool:
        """Check if a game is completed"""
        try:
            state = self.get_game_state(room_code)
            return state.get('phase') in ['game_over', 'completed']
        except Exception as e:
            print(f"[ERROR] Failed to check game completion for room {room_code}: {str(e)}")
            return True  # Assume completed if we can't check

    def update_player_in_room(self, room_code: str, player_id: str, updated_data: dict):
        """Update a specific player's data in the room"""
        try:
            key = f"room:{room_code}:players"
            players = self.get_room_players(room_code)
            
            print(f"[DEBUG] update_player_in_room: room {room_code} has {len(players)} players before update")
            
            # Find and update the player
            updated = False
            for i, player in enumerate(players):
                if player.get('player_id') == player_id:
                    # Update the player data
                    players[i] = updated_data
                    updated = True
                    break
            
            if not updated:
                print(f"[ERROR] Player {player_id} not found in room {room_code} for update")
                return False
                    
            # Clear the list and repopulate it
            self.redis.delete(key)
            for player_data in players:
                self.redis.rpush(key, json.dumps(player_data))
            
            # Refresh expiration after update
            self.redis.expire(key, 3600)
            
            print(f"[DEBUG] Successfully updated player {player_id} in room {room_code}")
            return True
            
        except Exception as e:
            print(f"[ERROR] Failed to update player in room: {str(e)}")
            return False

    def debug_room_state(self, room_code: str):
        """Debug function to print current room state"""
        try:
            print(f"\n=== DEBUG: Room {room_code} State ===")
            
            # Check if room exists
            exists = self.room_exists(room_code)
            print(f"Room exists: {exists}")
            
            if not exists:
                print("Room does not exist in Redis")
                return
            
            # Get room players
            players = self.get_room_players(room_code)
            print(f"Players in room: {len(players)}")
            for i, player in enumerate(players):
                print(f"  Player {i+1}: {player.get('username', 'NO_NAME')} (ID: {player.get('player_id', 'NO_ID')[:8]}...) - Status: {player.get('connection_status', 'NO_STATUS')}")
            
            # Get game state
            game_state = self.get_game_state(room_code)
            if game_state:
                print(f"Game state exists - Phase: {game_state.get('phase', 'NO_PHASE')}")
                print(f"  Hakem: {game_state.get('hakem', 'NO_HAKEM')}")
                print(f"  Hokm: {game_state.get('hokm', 'NO_HOKM')}")
                print(f"  Current turn: {game_state.get('current_turn', 'NO_TURN')}")
            else:
                print("No game state found")
            
            print("=== END DEBUG ===\n")
            
        except Exception as e:
            print(f"[ERROR] Debug room state failed: {str(e)}")
