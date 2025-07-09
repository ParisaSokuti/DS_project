# redis_manager_with_circuit_breaker.py
import redis
import json
import time
import logging
from typing import Dict, List, Optional, Any, Tuple
from circuit_breaker import CircuitBreaker, CircuitBreakerConfig, OperationResult

class ResilientRedisManager:
    """
    Enhanced RedisManager with circuit breaker pattern for resilience
    
    Features:
    - Circuit breaker protection for all Redis operations
    - Automatic failover with fallback mechanisms
    - In-memory caching for critical operations
    - Comprehensive monitoring and metrics
    - Graceful degradation during Redis failures
    """
    
    def __init__(self, host='localhost', port=6379, db=0):
        # Redis connection
        self.redis = redis.Redis(host=host, port=port, db=db)
        self.connection_timeout = 30
        self.heartbeat_interval = 10
        
        # Circuit breaker configuration
        self.circuit_config = CircuitBreakerConfig(
            failure_threshold=3,        # Open circuit after 3 failures
            success_threshold=2,        # Close circuit after 2 successes
            timeout=30.0,              # Wait 30s before trying half-open
            time_window=120.0,         # 2-minute failure tracking window
            max_retry_attempts=2,      # Retry failed operations twice
            base_backoff_delay=0.5,    # Start with 500ms backoff
            max_backoff_delay=5.0      # Max 5s backoff
        )
        
        # Circuit breakers for different operation types
        self.circuits = {
            'read': CircuitBreaker('redis_read', self.circuit_config),
            'write': CircuitBreaker('redis_write', self.circuit_config),
            'delete': CircuitBreaker('redis_delete', self.circuit_config),
            'scan': CircuitBreaker('redis_scan', self.circuit_config)
        }
        
        # Fallback storage (in-memory cache for critical operations)
        self.fallback_cache = {
            'game_states': {},      # Room code -> game state
            'player_sessions': {},  # Player ID -> session data
            'room_players': {},     # Room code -> list of players
            'room_metadata': {}     # Room code -> metadata
        }
        
        # Legacy metrics (for compatibility)
        self.metrics = {
            'operations': 0,
            'errors': 0,
            'latency_sum': 0
        }
        
        self.valid_phases = [
            'waiting_for_players', 'team_assignment', 'initial_deal', 
            'hokm_selection', 'final_deal', 'gameplay', 'hand_complete', 
            'game_over', 'completed'
        ]
        
        # Set up logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
        
        self.logger.info("ResilientRedisManager initialized with circuit breaker protection")
    
    def _measure_latency(self, start_time: float) -> None:
        """Update performance metrics (legacy compatibility)"""
        elapsed = time.time() - start_time
        self.metrics['latency_sum'] += elapsed
        self.metrics['operations'] += 1
    
    def get_performance_metrics(self) -> dict:
        """Get performance metrics including circuit breaker stats"""
        # Legacy metrics
        ops = self.metrics['operations']
        base_metrics = {
            'total_operations': ops,
            'error_rate': self.metrics['errors'] / ops if ops > 0 else 0,
            'avg_latency': self.metrics['latency_sum'] / ops if ops > 0 else 0
        }
        
        # Circuit breaker metrics
        circuit_metrics = {}
        for name, circuit in self.circuits.items():
            circuit_metrics[f'{name}_circuit'] = circuit.get_metrics()
        
        base_metrics['circuit_breakers'] = circuit_metrics
        base_metrics['fallback_cache_stats'] = {
            'game_states_cached': len(self.fallback_cache['game_states']),
            'player_sessions_cached': len(self.fallback_cache['player_sessions']),
            'room_players_cached': len(self.fallback_cache['room_players'])
        }
        
        return base_metrics
    
    def _create_cache_key(self, operation: str, *args) -> str:
        """Create cache key for operations"""
        return f"{operation}:{':'.join(str(arg) for arg in args)}"
    
    def _fallback_get_game_state(self, room_code: str) -> dict:
        """Fallback for getting game state from memory"""
        return self.fallback_cache['game_states'].get(room_code, {})
    
    def _fallback_get_player_session(self, player_id: str) -> dict:
        """Fallback for getting player session from memory"""
        return self.fallback_cache['player_sessions'].get(player_id, {})
    
    def _fallback_get_room_players(self, room_code: str) -> List[dict]:
        """Fallback for getting room players from memory"""
        return self.fallback_cache['room_players'].get(room_code, [])
    
    def _fallback_room_exists(self, room_code: str) -> bool:
        """Fallback for checking room existence"""
        return (room_code in self.fallback_cache['game_states'] or 
                room_code in self.fallback_cache['room_players'])
    
    def save_player_session(self, player_id: str, session_data: dict) -> bool:
        """Save player session with circuit breaker protection"""
        def _redis_save():
            key = f"session:{player_id}"
            updated_data = {
                'last_heartbeat': str(int(time.time()))
            }
            if 'connection_status' not in session_data:
                updated_data['connection_status'] = 'active'
            
            updated_data.update(session_data)
            self.redis.hset(key, mapping=updated_data)
            self.redis.expire(key, 3600)
            return True
        
        def _fallback_save():
            # Store in memory as fallback
            self.fallback_cache['player_sessions'][player_id] = session_data.copy()
            self.logger.warning(f"Using fallback storage for player session {player_id}")
            return True
        
        cache_key = self._create_cache_key("session", player_id)
        result = self.circuits['write'].call(
            _redis_save,
            fallback_func=_fallback_save,
            cache_key=cache_key
        )
        
        if result.success:
            # Update fallback cache with successful write
            self.fallback_cache['player_sessions'][player_id] = session_data.copy()
            
        return result.success
    
    def get_player_session(self, player_id: str) -> dict:
        """Get player session with circuit breaker protection"""
        def _redis_get():
            key = f"session:{player_id}"
            raw_data = self.redis.hgetall(key)
            return {k.decode(): v.decode() for k, v in raw_data.items()}
        
        cache_key = self._create_cache_key("session", player_id)
        result = self.circuits['read'].call(
            _redis_get,
            fallback_func=lambda: self._fallback_get_player_session(player_id),
            cache_key=cache_key
        )
        
        return result.value if result.success else {}
    
    def add_player_to_room(self, room_code: str, player_data: dict):
        """Add player to room with circuit breaker protection"""
        def _redis_add():
            key = f"room:{room_code}:players"
            self.redis.rpush(key, json.dumps(player_data))
            self.redis.expire(key, 3600)
            return True
        
        def _fallback_add():
            if room_code not in self.fallback_cache['room_players']:
                self.fallback_cache['room_players'][room_code] = []
            self.fallback_cache['room_players'][room_code].append(player_data)
            self.logger.warning(f"Using fallback storage for adding player to room {room_code}")
            return True
        
        result = self.circuits['write'].call(
            _redis_add,
            fallback_func=_fallback_add
        )
        
        if result.success:
            # Update fallback cache
            if room_code not in self.fallback_cache['room_players']:
                self.fallback_cache['room_players'][room_code] = []
            self.fallback_cache['room_players'][room_code].append(player_data)
        
        if not result.success:
            self.logger.error(f"Failed to add player to room {room_code}: {result.error}")
    
    def get_room_players(self, room_code: str) -> List[dict]:
        """Get room players with circuit breaker protection"""
        def _redis_get():
            key = f"room:{room_code}:players"
            if not self.redis.exists(key):
                return []
            
            players = self.redis.lrange(key, 0, -1)
            return [json.loads(p.decode()) for p in players]
        
        cache_key = self._create_cache_key("room_players", room_code)
        result = self.circuits['read'].call(
            _redis_get,
            fallback_func=lambda: self._fallback_get_room_players(room_code),
            cache_key=cache_key
        )
        
        return result.value if result.success else []
    
    def save_game_state(self, room_code: str, game_state: dict) -> bool:
        """Save game state with circuit breaker protection"""
        start_time = time.time()
        
        def _redis_save():
            # Add required fields if missing
            if 'created_at' not in game_state:
                game_state['created_at'] = str(int(time.time()))
            if 'last_activity' not in game_state:
                game_state['last_activity'] = str(int(time.time()))
            
            # Validate state
            is_valid, error = self.validate_game_state(game_state)
            if not is_valid:
                self.logger.warning(f"Game state validation failed for room {room_code}: {error}")
            
            # Use pipeline for atomic operation
            pipe = self.redis.pipeline()
            key = f"game:{room_code}:state"
            
            # Encode state
            encoded_state = {}
            for k, v in game_state.items():
                if isinstance(v, (dict, list)):
                    encoded_state[k] = json.dumps(v)
                else:
                    encoded_state[k] = str(v)
            
            pipe.hset(key, mapping=encoded_state)
            pipe.expire(key, 3600)
            pipe.execute()
            
            return True
        
        def _fallback_save():
            # Store in fallback cache
            self.fallback_cache['game_states'][room_code] = game_state.copy()
            self.logger.warning(f"Using fallback storage for game state {room_code}")
            return True
        
        cache_key = self._create_cache_key("game_state", room_code)
        result = self.circuits['write'].call(
            _redis_save,
            fallback_func=_fallback_save,
            cache_key=cache_key
        )
        
        if result.success:
            # Update fallback cache with successful write
            self.fallback_cache['game_states'][room_code] = game_state.copy()
            self._measure_latency(start_time)
        else:
            self.metrics['errors'] += 1
        
        return result.success
    
    def get_game_state(self, room_code: str) -> dict:
        """Get game state with circuit breaker protection"""
        def _redis_get():
            key = f"game:{room_code}:state"
            raw_state = self.redis.hgetall(key)
            if not raw_state:
                return {}
            
            # Decode bytes to string
            state = {k.decode(): v.decode() for k, v in raw_state.items()}
            
            # Decode JSON values
            for k, v in list(state.items()):
                try:
                    if k in ['teams', 'players', 'tricks', 'player_order'] or k.startswith('hand_'):
                        state[k] = json.loads(v)
                except json.JSONDecodeError:
                    pass  # Keep as string if not valid JSON
            
            return state
        
        cache_key = self._create_cache_key("game_state", room_code)
        result = self.circuits['read'].call(
            _redis_get,
            fallback_func=lambda: self._fallback_get_game_state(room_code),
            cache_key=cache_key
        )
        
        return result.value if result.success else {}
    
    def room_exists(self, room_code: str) -> bool:
        """Check if room exists with circuit breaker protection"""
        def _redis_check():
            state_key = f"game:{room_code}:state"
            return bool(self.redis.exists(state_key))
        
        result = self.circuits['read'].call(
            _redis_check,
            fallback_func=lambda: self._fallback_room_exists(room_code)
        )
        
        return result.value if result.success else False
    
    def create_room(self, room_code: str) -> bool:
        """Create room with circuit breaker protection"""
        def _redis_create():
            players_key = f"room:{room_code}:players"
            state_key = f"game:{room_code}:state"
            
            # Clear any existing data
            self.redis.delete(players_key)
            self.redis.delete(state_key)
            
            # Initialize room state
            self.redis.hset(state_key, "phase", "waiting_for_players")
            self.redis.hset(state_key, "created_at", str(int(time.time())))
            
            # Initialize empty players list
            self.redis.rpush(players_key, json.dumps({"placeholder": True}))
            self.redis.lrem(players_key, 1, json.dumps({"placeholder": True}))
            self.redis.expire(players_key, 3600)
            
            return True
        
        def _fallback_create():
            # Initialize fallback storage
            self.fallback_cache['room_players'][room_code] = []
            self.fallback_cache['game_states'][room_code] = {
                'phase': 'waiting_for_players',
                'created_at': str(int(time.time()))
            }
            self.logger.warning(f"Using fallback storage for creating room {room_code}")
            return True
        
        result = self.circuits['write'].call(
            _redis_create,
            fallback_func=_fallback_create
        )
        
        if result.success:
            # Update fallback cache
            self.fallback_cache['room_players'][room_code] = []
            self.fallback_cache['game_states'][room_code] = {
                'phase': 'waiting_for_players',
                'created_at': str(int(time.time()))
            }
        
        return result.success
    
    def delete_room(self, room_code: str):
        """Delete room with circuit breaker protection"""
        def _redis_delete():
            # Delete all room-related keys
            for key in self.redis.scan_iter(f"*{room_code}*"):
                self.redis.delete(key)
            return True
        
        def _fallback_delete():
            # Remove from fallback cache
            self.fallback_cache['game_states'].pop(room_code, None)
            self.fallback_cache['room_players'].pop(room_code, None)
            self.fallback_cache['room_metadata'].pop(room_code, None)
            self.logger.warning(f"Using fallback deletion for room {room_code}")
            return True
        
        result = self.circuits['delete'].call(
            _redis_delete,
            fallback_func=_fallback_delete
        )
        
        if result.success or not result.success:  # Always clean up fallback cache
            # Clean up fallback cache regardless of Redis operation success
            self.fallback_cache['game_states'].pop(room_code, None)
            self.fallback_cache['room_players'].pop(room_code, None)
            self.fallback_cache['room_metadata'].pop(room_code, None)
    
    def get_active_rooms(self) -> List[str]:
        """Get active rooms with circuit breaker protection"""
        def _redis_scan():
            room_codes = []
            for key in self.redis.scan_iter("game:*:state"):
                room_code = key.decode().split(':')[1]
                if self.room_exists(room_code):
                    room_codes.append(room_code)
            return room_codes
        
        def _fallback_scan():
            # Return rooms from fallback cache
            room_codes = list(self.fallback_cache['game_states'].keys())
            self.logger.warning("Using fallback storage for active rooms scan")
            return room_codes
        
        result = self.circuits['scan'].call(
            _redis_scan,
            fallback_func=_fallback_scan
        )
        
        return result.value if result.success else []
    
    def get_circuit_breaker_status(self) -> Dict[str, Any]:
        """Get status of all circuit breakers"""
        status = {}
        for name, circuit in self.circuits.items():
            status[name] = {
                'state': circuit.get_state().value,
                'metrics': circuit.get_metrics()
            }
        return status
    
    def reset_circuit_breakers(self):
        """Reset all circuit breakers to closed state"""
        for circuit in self.circuits.values():
            circuit.reset()
        self.logger.info("All circuit breakers reset")
    
    def is_healthy(self) -> bool:
        """Check if Redis connection is healthy"""
        try:
            # Simple ping test with circuit breaker
            def _ping():
                return self.redis.ping()
            
            result = self.circuits['read'].call(_ping)
            return result.success and result.value
        except:
            return False
    
    # Legacy methods for backward compatibility
    def clear_room(self, room_code: str):
        """Legacy method - redirects to delete_room"""
        self.delete_room(room_code)
    
    def delete_player_session(self, player_id: str):
        """Delete player session with circuit breaker protection"""
        def _redis_delete():
            key = f"session:{player_id}"
            self.redis.delete(key)
            return True
        
        def _fallback_delete():
            self.fallback_cache['player_sessions'].pop(player_id, None)
            return True
        
        result = self.circuits['delete'].call(
            _redis_delete,
            fallback_func=_fallback_delete
        )
        
        # Always clean up fallback cache
        self.fallback_cache['player_sessions'].pop(player_id, None)
    
    def validate_game_state(self, state: dict) -> Tuple[bool, str]:
        """Validate game state structure"""
        try:
            required = ['phase', 'created_at', 'last_activity']
            for field in required:
                if field not in state:
                    return False, f"Missing required field: {field}"
            
            if state['phase'] not in self.valid_phases:
                return False, f"Invalid game phase: {state['phase']}"
            
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
    
    # Implement other legacy methods with circuit breaker protection
    def cleanup_expired_sessions(self):
        """Clean up expired sessions with circuit breaker protection"""
        def _redis_cleanup():
            current_time = int(time.time())
            expired_count = 0
            for key in self.redis.scan_iter("session:*"):
                try:
                    session = self.redis.hgetall(key)
                    if not session:
                        continue
                    
                    expires_at = int(session.get(b'expires_at', b'0').decode())
                    if expires_at < current_time:
                        self.redis.delete(key)
                        expired_count += 1
                except Exception as e:
                    self.logger.error(f"Error processing session {key}: {e}")
            
            return expired_count
        
        result = self.circuits['delete'].call(_redis_cleanup)
        
        if result.success:
            self.logger.info(f"Cleaned up {result.value} expired sessions")
        
        # Also clean up fallback cache
        current_time = int(time.time())
        expired_sessions = []
        for player_id, session in self.fallback_cache['player_sessions'].items():
            expires_at = int(session.get('expires_at', 0))
            if expires_at < current_time:
                expired_sessions.append(player_id)
        
        for player_id in expired_sessions:
            del self.fallback_cache['player_sessions'][player_id]


# Alias for backward compatibility
RedisManager = ResilientRedisManager
