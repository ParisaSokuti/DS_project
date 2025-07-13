# async_redis_manager.py
import aioredis
import json
import time
import asyncio
import logging
from typing import Dict, List, Optional, Any, Tuple, Union

class AsyncRedisManager:
    """
    Async Redis manager using aioredis for non-blocking operations
    
    Features:
    - Full async/await support with aioredis
    - Connection pooling and automatic reconnection
    - Proper error handling and timeouts
    - Compatible interface with existing RedisManager
    - Performance monitoring and metrics
    """
    
    def __init__(self, host='localhost', port=6379, db=0, pool_size=10):
        self.host = host
        self.port = port
        self.db = db
        self.pool_size = pool_size
        self.pool: Optional[aioredis.ConnectionPool] = None
        self.redis: Optional[aioredis.Redis] = None
        
        # Configuration
        self.connection_timeout = 30
        self.heartbeat_interval = 10
        self.operation_timeout = 5.0  # Default timeout for Redis operations
        
        # Metrics
        self.metrics = {
            'operations': 0,
            'errors': 0,
            'latency_sum': 0
        }
        
        # Valid game phases
        self.valid_phases = [
            'waiting_for_players', 'team_assignment', 'initial_deal', 
            'hokm_selection', 'final_deal', 'gameplay', 'hand_complete', 
            'game_over', 'completed'
        ]
        
        # Connection state
        self._connected = False
        self._connecting = False
    
    async def connect(self) -> bool:
        """Establish Redis connection with pool"""
        if self._connected:
            return True
            
        if self._connecting:
            # Wait for ongoing connection attempt
            while self._connecting:
                await asyncio.sleep(0.1)
            return self._connected
            
        self._connecting = True
        
        try:
            # Create connection pool
            self.pool = aioredis.ConnectionPool(
                host=self.host,
                port=self.port,
                db=self.db,
                max_connections=self.pool_size,
                retry_on_timeout=True,
                socket_connect_timeout=5,
                socket_timeout=5
            )
            
            # Create Redis client
            self.redis = aioredis.Redis(connection_pool=self.pool, decode_responses=True)
            
            # Test connection
            await asyncio.wait_for(self.redis.ping(), timeout=2.0)
            
            self._connected = True
            self._connecting = False
            
            logging.info(f"[AsyncRedis] Connected to Redis at {self.host}:{self.port}")
            return True
            
        except Exception as e:
            self._connecting = False
            self._connected = False
            logging.error(f"[AsyncRedis] Connection failed: {str(e)}")
            return False
    
    async def disconnect(self):
        """Close Redis connection"""
        if self.redis:
            await self.redis.close()
        if self.pool:
            await self.pool.disconnect()
        self._connected = False
        logging.info("[AsyncRedis] Disconnected from Redis")
    
    async def ensure_connected(self) -> bool:
        """Ensure Redis connection is active"""
        if not self._connected:
            return await self.connect()
        
        try:
            await asyncio.wait_for(self.redis.ping(), timeout=1.0)
            return True
        except Exception:
            self._connected = False
            return await self.connect()
    
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
            'avg_latency': self.metrics['latency_sum'] / ops if ops > 0 else 0,
            'connected': self._connected
        }
    
    async def _safe_execute(self, operation, *args, **kwargs):
        """Execute Redis operation with error handling and metrics"""
        if not await self.ensure_connected():
            raise ConnectionError("Cannot connect to Redis")
            
        start_time = time.time()
        try:
            result = await asyncio.wait_for(
                operation(*args, **kwargs), 
                timeout=self.operation_timeout
            )
            self._measure_latency(start_time)
            return result
        except Exception as e:
            self.metrics['errors'] += 1
            logging.error(f"[AsyncRedis] Operation failed: {str(e)}")
            raise
    
    # ===== SESSION MANAGEMENT =====
    
    async def save_player_session(self, player_id: str, session_data: dict) -> bool:
        """Save player session with enhanced monitoring"""
        try:
            key = f"session:{player_id}"
            
            # Update session data but preserve existing connection_status if not provided
            updated_data = {
                'last_heartbeat': str(int(time.time()))
            }
            
            # Only set connection_status to 'active' if not already specified
            if 'connection_status' not in session_data:
                updated_data['connection_status'] = 'active'
            
            updated_data.update(session_data)
            
            # Convert values to strings for Redis hash
            redis_data = {k: str(v) for k, v in updated_data.items()}
            
            await self._safe_execute(self.redis.hset, key, mapping=redis_data)
            await self._safe_execute(self.redis.expire, key, 3600)  # 1 hour expiration
            
            return True
        except Exception as e:
            logging.error(f"[AsyncRedis] Failed to save session for {player_id}: {str(e)}")
            return False
    
    async def get_player_session(self, player_id: str) -> dict:
        """Get player session data"""
        try:
            key = f"session:{player_id}"
            session_data = await self._safe_execute(self.redis.hgetall, key)
            return session_data or {}
        except Exception as e:
            logging.error(f"[AsyncRedis] Failed to get session for {player_id}: {str(e)}")
            return {}
    
    async def delete_player_session(self, player_id: str) -> bool:
        """Delete a player's session data"""
        try:
            key = f"session:{player_id}"
            await self._safe_execute(self.redis.delete, key)
            return True
        except Exception as e:
            logging.error(f"[AsyncRedis] Failed to delete session for {player_id}: {str(e)}")
            return False
    
    # ===== ROOM MANAGEMENT =====
    
    async def create_room(self, room_code: str) -> bool:
        """Create a new room with proper initialization"""
        try:
            players_key = f"room:{room_code}:players"
            state_key = f"game:{room_code}:state"
            
            # Clear any existing data
            await self._safe_execute(self.redis.delete, players_key)
            await self._safe_execute(self.redis.delete, state_key)
            
            # Initialize room state
            await self._safe_execute(
                self.redis.hset, 
                state_key, 
                mapping={
                    "phase": "waiting_for_players",
                    "created_at": str(int(time.time()))
                }
            )
            
            # Initialize empty players list by setting expiration
            await self._safe_execute(self.redis.expire, players_key, 3600)
            
            logging.info(f"[AsyncRedis] Created room {room_code}")
            return True
        except Exception as e:
            logging.error(f"[AsyncRedis] Failed to create room {room_code}: {str(e)}")
            return False
    
    async def room_exists(self, room_code: str) -> bool:
        """Check if a room exists and is valid"""
        try:
            state_key = f"game:{room_code}:state"
            exists = await self._safe_execute(self.redis.exists, state_key)
            return bool(exists)
        except Exception as e:
            logging.error(f"[AsyncRedis] Failed to check room {room_code} existence: {str(e)}")
            return False
    
    async def clear_room(self, room_code: str) -> bool:
        """Clean up room data"""
        try:
            await self._safe_execute(self.redis.delete, f"room:{room_code}:players")
            await self._safe_execute(self.redis.delete, f"game:{room_code}:state")
            return True
        except Exception as e:
            logging.error(f"[AsyncRedis] Failed to clear room {room_code}: {str(e)}")
            return False
    
    async def delete_room(self, room_code: str) -> bool:
        """Delete a room and all associated data"""
        try:
            await self.clear_room(room_code)
            
            # Clean up any other room-related keys
            pattern = f"*{room_code}*"
            async for key in self.redis.scan_iter(match=pattern):
                await self._safe_execute(self.redis.delete, key)
            
            return True
        except Exception as e:
            logging.error(f"[AsyncRedis] Failed to delete room {room_code}: {str(e)}")
            return False
    
    # ===== PLAYER MANAGEMENT =====
    
    async def add_player_to_room(self, room_code: str, player_data: dict) -> bool:
        """Add player to room"""
        try:
            key = f"room:{room_code}:players"
            player_json = json.dumps(player_data)
            
            await self._safe_execute(self.redis.rpush, key, player_json)
            await self._safe_execute(self.redis.expire, key, 3600)  # Refresh expiration
            
            logging.debug(f"[AsyncRedis] Added player {player_data.get('username', 'NO_NAME')} to room {room_code}")
            return True
        except Exception as e:
            logging.error(f"[AsyncRedis] Failed to add player to room {room_code}: {str(e)}")
            return False
    
    async def get_room_players(self, room_code: str) -> List[dict]:
        """Get all players in a room"""
        try:
            key = f"room:{room_code}:players"
            
            # Check if key exists
            exists = await self._safe_execute(self.redis.exists, key)
            if not exists:
                return []
            
            players_data = await self._safe_execute(self.redis.lrange, key, 0, -1)
            players = [json.loads(p) for p in players_data]
            
            logging.debug(f"[AsyncRedis] Retrieved {len(players)} players from room {room_code}")
            return players
        except Exception as e:
            logging.error(f"[AsyncRedis] Failed to get room players for {room_code}: {str(e)}")
            return []
    
    async def update_player_in_room(self, room_code: str, player_id: str, updated_data: dict) -> bool:
        """Update a specific player's data in the room"""
        try:
            key = f"room:{room_code}:players"
            players = await self.get_room_players(room_code)
            
            # Find and update the player
            updated = False
            for i, player in enumerate(players):
                if player.get('player_id') == player_id:
                    players[i] = updated_data
                    updated = True
                    break
            
            if not updated:
                logging.error(f"[AsyncRedis] Player {player_id} not found in room {room_code}")
                return False
            
            # Clear the list and repopulate it
            await self._safe_execute(self.redis.delete, key)
            for player_data in players:
                await self._safe_execute(self.redis.rpush, key, json.dumps(player_data))
            
            # Refresh expiration
            await self._safe_execute(self.redis.expire, key, 3600)
            
            logging.debug(f"[AsyncRedis] Updated player {player_id} in room {room_code}")
            return True
        except Exception as e:
            logging.error(f"[AsyncRedis] Failed to update player in room: {str(e)}")
            return False
    
    # ===== GAME STATE MANAGEMENT =====
    
    async def save_game_state(self, room_code: str, game_state: dict) -> bool:
        """Save game state with proper encoding and validation"""
        try:
            # Add required fields if missing
            if 'created_at' not in game_state:
                game_state['created_at'] = str(int(time.time()))
            if 'last_activity' not in game_state:
                game_state['last_activity'] = str(int(time.time()))
            
            # Validate state
            is_valid, error = self.validate_game_state(game_state)
            if not is_valid:
                logging.warning(f"[AsyncRedis] Game state validation failed for room {room_code}: {error}")
                logging.warning(f"[AsyncRedis] Saving anyway to prevent data loss...")
            
            key = f"game:{room_code}:state"
            
            # Encode state for Redis
            encoded_state = {}
            for k, v in game_state.items():
                if isinstance(v, (dict, list)):
                    encoded_state[k] = json.dumps(v)
                else:
                    encoded_state[k] = str(v)
            
            # Use pipeline for atomicity
            pipe = self.redis.pipeline()
            pipe.hset(key, mapping=encoded_state)
            pipe.expire(key, 3600)
            await self._safe_execute(pipe.execute)
            
            logging.debug(f"[AsyncRedis] Saved game state for room {room_code} with phase: {game_state.get('phase', 'UNKNOWN')}")
            return True
        except Exception as e:
            logging.error(f"[AsyncRedis] Failed to save game state for room {room_code}: {str(e)}")
            return False
    
    async def get_game_state(self, room_code: str) -> dict:
        """Get game state with proper decoding"""
        try:
            key = f"game:{room_code}:state"
            raw_state = await self._safe_execute(self.redis.hgetall, key)
            
            if not raw_state:
                logging.warning(f"[AsyncRedis] No state found for room {room_code}")
                return {}
            
            # Decode JSON values
            state = dict(raw_state)  # aioredis with decode_responses=True returns strings
            for k, v in list(state.items()):
                try:
                    if k in ['teams', 'players', 'tricks', 'player_order'] or k.startswith('hand_'):
                        state[k] = json.loads(v)
                except json.JSONDecodeError:
                    pass  # Keep as string if not valid JSON
                except Exception as e:
                    logging.error(f"[AsyncRedis] Error processing key {k}: {str(e)}")
            
            return state
        except Exception as e:
            logging.error(f"[AsyncRedis] Failed to get game state for room {room_code}: {str(e)}")
            return {}
    
    async def delete_game_state(self, room_code: str) -> bool:
        """Delete game state for a room"""
        try:
            key = f"game:{room_code}:state"
            await self._safe_execute(self.redis.delete, key)
            logging.info(f"[AsyncRedis] Deleted game state for room {room_code}")
            return True
        except Exception as e:
            logging.error(f"[AsyncRedis] Failed to delete game state for room {room_code}: {str(e)}")
            return False
    
    # ===== CONNECTION MANAGEMENT =====
    
    async def update_player_heartbeat(self, player_id: str) -> bool:
        """Update player's last heartbeat timestamp"""
        try:
            key = f"session:{player_id}"
            current_time = str(int(time.time()))
            await self._safe_execute(self.redis.hset, key, 'last_heartbeat', current_time)
            return True
        except Exception as e:
            logging.error(f"[AsyncRedis] Failed to update heartbeat for {player_id}: {str(e)}")
            return False
    
    async def check_player_connection(self, player_id: str) -> str:
        """Check if player connection is still active"""
        try:
            session = await self.get_player_session(player_id)
            if not session:
                return 'disconnected'
            
            last_heartbeat = int(session.get('last_heartbeat', '0'))
            current_time = int(time.time())
            
            if current_time - last_heartbeat > self.connection_timeout:
                await self.mark_player_disconnected(player_id)
                return 'disconnected'
            return 'active'
        except Exception as e:
            logging.error(f"[AsyncRedis] Failed to check connection for {player_id}: {str(e)}")
            return 'unknown'
    
    async def mark_player_disconnected(self, player_id: str) -> bool:
        """Mark a player as disconnected"""
        try:
            key = f"session:{player_id}"
            await self._safe_execute(self.redis.hset, key, 'connection_status', 'disconnected')
            
            session = await self.get_player_session(player_id)
            if 'room_code' in session:
                await self.handle_player_disconnect_from_room(session['room_code'], player_id)
            return True
        except Exception as e:
            logging.error(f"[AsyncRedis] Failed to mark player {player_id} as disconnected: {str(e)}")
            return False
    
    async def handle_player_disconnect_from_room(self, room_code: str, player_id: str) -> bool:
        """Handle cleanup when a player disconnects from a room"""
        try:
            players = await self.get_room_players(room_code)
            updated_players = [p for p in players if p.get('player_id') != player_id]
            
            # Clear and update player list
            key = f"room:{room_code}:players"
            await self._safe_execute(self.redis.delete, key)
            for player in updated_players:
                await self._safe_execute(self.redis.rpush, key, json.dumps(player))
            
            # Update game state if needed
            if not updated_players:
                await self.clear_room(room_code)
            
            return True
        except Exception as e:
            logging.error(f"[AsyncRedis] Failed to handle disconnect for player {player_id}: {str(e)}")
            return False
    
    # ===== UTILITY METHODS =====
    
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
    
    async def get_active_rooms(self) -> List[str]:
        """Get all active room codes from Redis"""
        try:
            room_codes = []
            async for key in self.redis.scan_iter(match="game:*:state"):
                # Extract room code from key format "game:ROOM_CODE:state"
                room_code = key.split(':')[1]
                if await self.room_exists(room_code):
                    room_codes.append(room_code)
            return room_codes
        except Exception as e:
            logging.error(f"[AsyncRedis] Failed to get active rooms: {str(e)}")
            return []
    
    async def is_game_completed(self, room_code: str) -> bool:
        """Check if a game is completed"""
        try:
            state = await self.get_game_state(room_code)
            return state.get('phase') in ['game_over', 'completed']
        except Exception as e:
            logging.error(f"[AsyncRedis] Failed to check game completion for room {room_code}: {str(e)}")
            return True  # Assume completed if we can't check
    
    async def cleanup_expired_sessions(self) -> int:
        """Clean up expired player sessions"""
        cleaned_count = 0
        try:
            current_time = int(time.time())
            async for key in self.redis.scan_iter(match="session:*"):
                try:
                    session = await self._safe_execute(self.redis.hgetall, key)
                    if not session:
                        continue
                    
                    expires_at = int(session.get('expires_at', '0'))
                    if expires_at < current_time:
                        await self._safe_execute(self.redis.delete, key)
                        cleaned_count += 1
                        logging.info(f"[AsyncRedis] Cleaned up expired session: {key}")
                except Exception as e:
                    logging.error(f"[AsyncRedis] Error processing session {key}: {str(e)}")
            
            logging.info(f"[AsyncRedis] Cleaned up {cleaned_count} expired sessions")
            return cleaned_count
        except Exception as e:
            logging.error(f"[AsyncRedis] Error in cleanup_expired_sessions: {str(e)}")
            return cleaned_count
    
    # ===== VALIDATION AND RECOVERY =====
    
    async def validate_session(self, player_id: str) -> Tuple[bool, str]:
        """Validate a player session and attempt recovery if possible"""
        try:
            session = await self.get_player_session(player_id)
            if not session:
                return False, "Session not found"
            
            current_time = int(time.time())
            last_heartbeat = int(session.get('last_heartbeat', '0'))
            
            # Check if session is still within valid timeframe
            if current_time - last_heartbeat > self.connection_timeout:
                # Try to recover session if it's not too old (within 2x timeout)
                if current_time - last_heartbeat <= (self.connection_timeout * 2):
                    await self.update_player_heartbeat(player_id)
                    return True, "Session recovered"
                else:
                    await self.delete_player_session(player_id)
                    return False, "Session expired"
            
            return True, "Session valid"
        except Exception as e:
            logging.error(f"[AsyncRedis] Session validation failed for {player_id}: {str(e)}")
            return False, "Session validation error"
    
    async def attempt_reconnect(self, player_id: str, connection_data: dict) -> Tuple[bool, dict]:
        """Attempt to reconnect a player to their previous session"""
        try:
            is_valid, message = await self.validate_session(player_id)
            
            if not is_valid:
                return False, {"error": message}
            
            # Update session with new connection data
            session = await self.get_player_session(player_id)
            session.update(connection_data)
            session['connection_status'] = 'active'
            
            if await self.save_player_session(player_id, session):
                return True, session
            else:
                return False, {"error": "Failed to update session"}
        except Exception as e:
            logging.error(f"[AsyncRedis] Reconnection failed for {player_id}: {str(e)}")
            return False, {"error": "Reconnection error"}
    
    # ===== DEBUG UTILITIES =====
    
    async def debug_room_state(self, room_code: str):
        """Debug function to print current room state"""
        try:
            print(f"\n=== DEBUG: Room {room_code} State ===")
            
            # Check if room exists
            exists = await self.room_exists(room_code)
            print(f"Room exists: {exists}")
            
            if not exists:
                print("Room does not exist in Redis")
                return
            
            # Get room players
            players = await self.get_room_players(room_code)
            print(f"Players in room: {len(players)}")
            for i, player in enumerate(players):
                print(f"  Player {i+1}: {player.get('username', 'NO_NAME')} "
                      f"(ID: {player.get('player_id', 'NO_ID')[:8]}...) - "
                      f"Status: {player.get('connection_status', 'NO_STATUS')}")
            
            # Get game state
            game_state = await self.get_game_state(room_code)
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
