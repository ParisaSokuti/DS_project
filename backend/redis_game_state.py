"""
Redis Game State Manager for Hokm Game Server
Optimized for real-time game operations with low-latency access patterns
"""

import asyncio
import json
import time
import logging
from typing import Dict, List, Any, Optional, Set
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
import redis.asyncio as redis

logger = logging.getLogger(__name__)

class GamePhase(Enum):
    """Game phases for state management"""
    WAITING = "waiting"
    TEAM_ASSIGNMENT = "team_assignment"
    HOKM_SELECTION = "hokm_selection"
    CARD_DEALING = "card_dealing"
    PLAYING = "playing"
    ROUND_COMPLETE = "round_complete"
    GAME_COMPLETE = "game_complete"

@dataclass
class GameStateConfig:
    """Configuration for Redis game state management"""
    redis_prefix: str = "hokm:game:"
    default_ttl: int = 14400  # 4 hours
    heartbeat_interval: int = 30  # seconds
    player_timeout: int = 180  # 3 minutes
    turn_timeout: int = 60  # 1 minute
    
    # Performance settings
    pipeline_operations: bool = True
    use_lua_scripts: bool = True
    batch_updates: bool = True

class RedisGameStateManager:
    """
    Redis-based game state manager optimized for real-time Hokm gameplay.
    Implements efficient data structures and operations for low-latency gaming.
    """
    
    def __init__(self, redis_manager, config: GameStateConfig = None):
        self.redis = redis_manager
        self.config = config or GameStateConfig()
        
        # Lua scripts for atomic operations
        self.lua_scripts = {}
        self._initialize_lua_scripts()
        
        # Performance tracking
        self.operation_counts = {
            'game_creates': 0,
            'state_updates': 0,
            'player_actions': 0,
            'cache_operations': 0
        }
        
        logger.info("Redis Game State Manager initialized")
    
    def _initialize_lua_scripts(self):
        """Initialize Lua scripts for atomic operations"""
        
        # Script for atomic player join
        self.lua_scripts['player_join'] = """
        local game_key = KEYS[1]
        local player_id = ARGV[1]
        local player_data = ARGV[2]
        local max_players = tonumber(ARGV[3])
        
        local current_players = redis.call('HGET', game_key, 'player_count')
        current_players = tonumber(current_players) or 0
        
        if current_players >= max_players then
            return {false, 'game_full'}
        end
        
        local player_key = 'player:' .. player_id
        redis.call('HSET', game_key, player_key, player_data)
        redis.call('HSET', game_key, 'player_count', current_players + 1)
        redis.call('HSET', game_key, 'last_updated', ARGV[4])
        
        return {true, 'joined', current_players + 1}
        """
        
        # Script for atomic move validation and execution
        self.lua_scripts['execute_move'] = """
        local game_key = KEYS[1]
        local player_id = ARGV[1]
        local move_data = ARGV[2]
        local timestamp = ARGV[3]
        
        local current_turn = redis.call('HGET', game_key, 'current_turn')
        local game_phase = redis.call('HGET', game_key, 'phase')
        
        if current_turn ~= player_id then
            return {false, 'not_your_turn'}
        end
        
        if game_phase ~= 'playing' then
            return {false, 'invalid_phase'}
        end
        
        -- Execute the move
        redis.call('HSET', game_key, 'last_move', move_data)
        redis.call('HSET', game_key, 'last_move_time', timestamp)
        redis.call('HSET', game_key, 'last_updated', timestamp)
        
        -- Add to move history
        local history_key = game_key .. ':moves'
        redis.call('LPUSH', history_key, move_data)
        redis.call('EXPIRE', history_key, 3600)
        
        return {true, 'move_executed'}
        """
        
        # Script for updating scores atomically
        self.lua_scripts['update_scores'] = """
        local game_key = KEYS[1]
        local team1_score = ARGV[1]
        local team2_score = ARGV[2]
        local round_winner = ARGV[3]
        local timestamp = ARGV[4]
        
        redis.call('HSET', game_key, 'team1_score', team1_score)
        redis.call('HSET', game_key, 'team2_score', team2_score)
        redis.call('HSET', game_key, 'round_winner', round_winner)
        redis.call('HSET', game_key, 'last_updated', timestamp)
        
        -- Update round history
        local rounds_key = game_key .. ':rounds'
        local round_data = '{"team1":' .. team1_score .. ',"team2":' .. team2_score .. ',"winner":"' .. round_winner .. '","timestamp":"' .. timestamp .. '"}'
        redis.call('LPUSH', rounds_key, round_data)
        redis.call('EXPIRE', rounds_key, 7200)
        
        return {true, 'scores_updated'}
        """
    
    # Game Creation and Management
    async def create_game(self, room_id: str, creator_id: str, game_settings: Dict[str, Any] = None) -> bool:
        """Create a new game session in Redis"""
        try:
            game_key = f"{self.config.redis_prefix}{room_id}"
            
            # Default game settings
            default_settings = {
                'max_players': 4,
                'rounds_to_win': 7,
                'turn_timeout': self.config.turn_timeout,
                'auto_start': True
            }
            
            if game_settings:
                default_settings.update(game_settings)
            
            # Initial game state
            game_state = {
                'room_id': room_id,
                'creator_id': creator_id,
                'phase': GamePhase.WAITING.value,
                'player_count': 0,
                'max_players': default_settings['max_players'],
                'team1_score': 0,
                'team2_score': 0,
                'current_round': 0,
                'rounds_to_win': default_settings['rounds_to_win'],
                'created_at': datetime.utcnow().isoformat(),
                'last_updated': datetime.utcnow().isoformat(),
                'settings': json.dumps(default_settings),
                'status': 'active'
            }
            
            # Use pipeline for efficiency
            if self.config.pipeline_operations:
                pipe = self.redis.pipeline()
                pipe.hset(game_key, mapping=self._serialize_state(game_state))
                pipe.expire(game_key, self.config.default_ttl)
                
                # Create auxiliary data structures
                pipe.delete(f"{game_key}:players")  # Clear any existing players
                pipe.delete(f"{game_key}:moves")    # Clear move history
                pipe.delete(f"{game_key}:rounds")   # Clear round history
                
                await pipe.execute()
            else:
                await self.redis.hset(game_key, mapping=self._serialize_state(game_state))
                await self.redis.expire(game_key, self.config.default_ttl)
            
            self.operation_counts['game_creates'] += 1
            logger.info(f"Created game {room_id} with creator {creator_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create game {room_id}: {str(e)}")
            return False
    
    async def get_game_state(self, room_id: str) -> Optional[Dict[str, Any]]:
        """Get complete game state"""
        try:
            game_key = f"{self.config.redis_prefix}{room_id}"
            
            # Get main game state
            state_data = await self.redis.hgetall(game_key)
            if not state_data:
                return None
            
            game_state = self._deserialize_state(state_data)
            
            # Enrich with auxiliary data if needed
            if self.config.batch_updates:
                pipe = self.redis.pipeline()
                pipe.lrange(f"{game_key}:moves", 0, 9)  # Last 10 moves
                pipe.lrange(f"{game_key}:rounds", 0, -1)  # All rounds
                pipe.smembers(f"{game_key}:active_players")
                
                results = await pipe.execute()
                
                game_state['recent_moves'] = [json.loads(move) for move in results[0] if move]
                game_state['round_history'] = [json.loads(round_data) for round_data in results[1] if round_data]
                game_state['active_players'] = list(results[2])
            
            return game_state
            
        except Exception as e:
            logger.error(f"Failed to get game state for {room_id}: {str(e)}")
            return None
    
    async def update_game_phase(self, room_id: str, new_phase: GamePhase, additional_data: Dict[str, Any] = None) -> bool:
        """Update game phase with optional additional data"""
        try:
            game_key = f"{self.config.redis_prefix}{room_id}"
            
            update_data = {
                'phase': new_phase.value,
                'last_updated': datetime.utcnow().isoformat()
            }
            
            if additional_data:
                update_data.update(additional_data)
            
            await self.redis.hset(game_key, mapping=self._serialize_state(update_data))
            await self.redis.expire(game_key, self.config.default_ttl)
            
            self.operation_counts['state_updates'] += 1
            logger.debug(f"Updated game {room_id} phase to {new_phase.value}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update game phase for {room_id}: {str(e)}")
            return False
    
    # Player Management
    async def add_player_to_game(self, room_id: str, player_id: str, player_data: Dict[str, Any]) -> Dict[str, Any]:
        """Add player to game with atomic operation"""
        try:
            game_key = f"{self.config.redis_prefix}{room_id}"
            
            # Prepare player data
            player_info = {
                'player_id': player_id,
                'joined_at': datetime.utcnow().isoformat(),
                'status': 'active',
                **player_data
            }
            
            if self.config.use_lua_scripts:
                # Use Lua script for atomic operation
                result = await self.redis.eval(
                    self.lua_scripts['player_join'],
                    1,  # Number of keys
                    game_key,
                    player_id,
                    json.dumps(player_info),
                    "4",  # max_players
                    datetime.utcnow().isoformat()
                )
                
                success, message, player_count = result[0], result[1], result[2] if len(result) > 2 else 0
                
                if success:
                    # Add to active players set
                    await self.redis.sadd(f"{game_key}:active_players", player_id)
                    
                    return {
                        'success': True,
                        'message': message,
                        'player_count': player_count
                    }
                else:
                    return {
                        'success': False,
                        'message': message
                    }
            else:
                # Fallback to manual operation
                current_count = await self.redis.hget(game_key, 'player_count')
                current_count = int(current_count) if current_count else 0
                
                if current_count >= 4:
                    return {'success': False, 'message': 'game_full'}
                
                # Add player
                await self.redis.hset(game_key, f"player:{player_id}", json.dumps(player_info))
                await self.redis.hset(game_key, 'player_count', current_count + 1)
                await self.redis.sadd(f"{game_key}:active_players", player_id)
                
                return {
                    'success': True,
                    'message': 'joined',
                    'player_count': current_count + 1
                }
                
        except Exception as e:
            logger.error(f"Failed to add player {player_id} to game {room_id}: {str(e)}")
            return {'success': False, 'message': 'error', 'error': str(e)}
    
    async def remove_player_from_game(self, room_id: str, player_id: str) -> bool:
        """Remove player from game"""
        try:
            game_key = f"{self.config.redis_prefix}{room_id}"
            
            pipe = self.redis.pipeline()
            pipe.hdel(game_key, f"player:{player_id}")
            pipe.srem(f"{game_key}:active_players", player_id)
            
            # Update player count
            current_count = await self.redis.hget(game_key, 'player_count')
            if current_count:
                new_count = max(0, int(current_count) - 1)
                pipe.hset(game_key, 'player_count', new_count)
            
            pipe.hset(game_key, 'last_updated', datetime.utcnow().isoformat())
            await pipe.execute()
            
            logger.debug(f"Removed player {player_id} from game {room_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to remove player {player_id} from game {room_id}: {str(e)}")
            return False
    
    async def get_game_players(self, room_id: str) -> List[Dict[str, Any]]:
        """Get all players in a game"""
        try:
            game_key = f"{self.config.redis_prefix}{room_id}"
            
            # Get all player fields
            all_fields = await self.redis.hgetall(game_key)
            players = []
            
            for field, value in all_fields.items():
                if field.startswith('player:'):
                    player_data = json.loads(value)
                    players.append(player_data)
            
            return players
            
        except Exception as e:
            logger.error(f"Failed to get players for game {room_id}: {str(e)}")
            return []
    
    # Game Move Operations
    async def execute_player_move(self, room_id: str, player_id: str, move_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a player move with validation"""
        try:
            game_key = f"{self.config.redis_prefix}{room_id}"
            timestamp = datetime.utcnow().isoformat()
            
            # Prepare move data
            move_info = {
                'player_id': player_id,
                'move_data': move_data,
                'timestamp': timestamp,
                'move_id': f"{room_id}_{player_id}_{int(time.time() * 1000)}"
            }
            
            if self.config.use_lua_scripts:
                # Use Lua script for atomic move execution
                result = await self.redis.eval(
                    self.lua_scripts['execute_move'],
                    1,
                    game_key,
                    player_id,
                    json.dumps(move_info),
                    timestamp
                )
                
                success, message = result[0], result[1]
                
                if success:
                    self.operation_counts['player_actions'] += 1
                    return {'success': True, 'message': message, 'move_id': move_info['move_id']}
                else:
                    return {'success': False, 'message': message}
            else:
                # Manual validation and execution
                current_turn = await self.redis.hget(game_key, 'current_turn')
                if current_turn != player_id:
                    return {'success': False, 'message': 'not_your_turn'}
                
                # Execute move
                pipe = self.redis.pipeline()
                pipe.hset(game_key, 'last_move', json.dumps(move_info))
                pipe.hset(game_key, 'last_move_time', timestamp)
                pipe.hset(game_key, 'last_updated', timestamp)
                pipe.lpush(f"{game_key}:moves", json.dumps(move_info))
                pipe.expire(f"{game_key}:moves", 3600)
                await pipe.execute()
                
                self.operation_counts['player_actions'] += 1
                return {'success': True, 'message': 'move_executed', 'move_id': move_info['move_id']}
                
        except Exception as e:
            logger.error(f"Failed to execute move for player {player_id} in game {room_id}: {str(e)}")
            return {'success': False, 'message': 'error', 'error': str(e)}
    
    async def get_move_history(self, room_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get move history for a game"""
        try:
            moves_key = f"{self.config.redis_prefix}{room_id}:moves"
            moves = await self.redis.lrange(moves_key, 0, limit - 1)
            
            return [json.loads(move) for move in moves]
            
        except Exception as e:
            logger.error(f"Failed to get move history for game {room_id}: {str(e)}")
            return []
    
    # Score and Round Management
    async def update_game_scores(self, room_id: str, team1_score: int, team2_score: int, round_winner: str = None) -> bool:
        """Update game scores atomically"""
        try:
            game_key = f"{self.config.redis_prefix}{room_id}"
            timestamp = datetime.utcnow().isoformat()
            
            if self.config.use_lua_scripts:
                result = await self.redis.eval(
                    self.lua_scripts['update_scores'],
                    1,
                    game_key,
                    str(team1_score),
                    str(team2_score),
                    round_winner or '',
                    timestamp
                )
                
                return result[0]  # Success boolean
            else:
                # Manual score update
                pipe = self.redis.pipeline()
                pipe.hset(game_key, 'team1_score', team1_score)
                pipe.hset(game_key, 'team2_score', team2_score)
                if round_winner:
                    pipe.hset(game_key, 'round_winner', round_winner)
                pipe.hset(game_key, 'last_updated', timestamp)
                
                # Update round history
                round_data = {
                    'team1': team1_score,
                    'team2': team2_score,
                    'winner': round_winner,
                    'timestamp': timestamp
                }
                pipe.lpush(f"{game_key}:rounds", json.dumps(round_data))
                pipe.expire(f"{game_key}:rounds", 7200)
                
                await pipe.execute()
                return True
                
        except Exception as e:
            logger.error(f"Failed to update scores for game {room_id}: {str(e)}")
            return False
    
    async def advance_to_next_round(self, room_id: str) -> Dict[str, Any]:
        """Advance game to next round"""
        try:
            game_key = f"{self.config.redis_prefix}{room_id}"
            
            # Get current round
            current_round = await self.redis.hget(game_key, 'current_round')
            current_round = int(current_round) if current_round else 0
            
            new_round = current_round + 1
            
            # Update game state
            update_data = {
                'current_round': new_round,
                'phase': GamePhase.CARD_DEALING.value,
                'last_updated': datetime.utcnow().isoformat()
            }
            
            await self.redis.hset(game_key, mapping=self._serialize_state(update_data))
            
            return {
                'success': True,
                'current_round': new_round,
                'phase': GamePhase.CARD_DEALING.value
            }
            
        except Exception as e:
            logger.error(f"Failed to advance round for game {room_id}: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    # Card Management
    async def set_player_hand(self, room_id: str, player_id: str, cards: List[str], encrypted: bool = True) -> bool:
        """Set player's card hand (optionally encrypted)"""
        try:
            hand_key = f"{self.config.redis_prefix}{room_id}:hand:{player_id}"
            
            if encrypted:
                # In production, you'd use proper encryption here
                # For now, just base64 encode as a placeholder
                import base64
                cards_data = base64.b64encode(json.dumps(cards).encode()).decode()
            else:
                cards_data = json.dumps(cards)
            
            await self.redis.setex(hand_key, 7200, cards_data)  # 2 hour TTL
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to set hand for player {player_id} in game {room_id}: {str(e)}")
            return False
    
    async def get_player_hand(self, room_id: str, player_id: str, encrypted: bool = True) -> Optional[List[str]]:
        """Get player's card hand"""
        try:
            hand_key = f"{self.config.redis_prefix}{room_id}:hand:{player_id}"
            cards_data = await self.redis.get(hand_key)
            
            if not cards_data:
                return None
            
            if encrypted:
                import base64
                cards_json = base64.b64decode(cards_data.encode()).decode()
                return json.loads(cards_json)
            else:
                return json.loads(cards_data)
            
        except Exception as e:
            logger.error(f"Failed to get hand for player {player_id} in game {room_id}: {str(e)}")
            return None
    
    # Game Discovery and Listing
    async def get_active_games(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get list of active games"""
        try:
            pattern = f"{self.config.redis_prefix}*"
            games = []
            
            async for key in self.redis.scan_iter(match=pattern, count=100):
                if ':' not in key.split(self.config.redis_prefix, 1)[1]:  # Only main game keys
                    game_data = await self.redis.hgetall(key)
                    if game_data and game_data.get('status') == 'active':
                        games.append(self._deserialize_state(game_data))
                        
                        if len(games) >= limit:
                            break
            
            return games
            
        except Exception as e:
            logger.error(f"Failed to get active games: {str(e)}")
            return []
    
    async def cleanup_expired_games(self) -> int:
        """Cleanup expired or completed games"""
        try:
            pattern = f"{self.config.redis_prefix}*"
            cleaned = 0
            
            async for key in self.redis.scan_iter(match=pattern):
                if ':' not in key.split(self.config.redis_prefix, 1)[1]:  # Only main game keys
                    game_data = await self.redis.hgetall(key)
                    
                    if game_data:
                        status = game_data.get('status')
                        phase = game_data.get('phase')
                        last_updated = game_data.get('last_updated')
                        
                        # Check if game should be cleaned up
                        should_cleanup = False
                        
                        if status == 'completed':
                            should_cleanup = True
                        elif phase == GamePhase.GAME_COMPLETE.value:
                            should_cleanup = True
                        elif last_updated:
                            try:
                                last_update_time = datetime.fromisoformat(last_updated.replace('Z', '+00:00'))
                                if datetime.utcnow() - last_update_time > timedelta(hours=6):
                                    should_cleanup = True
                            except:
                                pass
                        
                        if should_cleanup:
                            room_id = key.split(self.config.redis_prefix, 1)[1]
                            await self._cleanup_game_data(room_id)
                            cleaned += 1
            
            logger.info(f"Cleaned up {cleaned} expired games")
            return cleaned
            
        except Exception as e:
            logger.error(f"Failed to cleanup expired games: {str(e)}")
            return 0
    
    async def _cleanup_game_data(self, room_id: str):
        """Cleanup all data for a specific game"""
        game_key = f"{self.config.redis_prefix}{room_id}"
        
        # Get all related keys
        keys_to_delete = [
            game_key,
            f"{game_key}:players",
            f"{game_key}:moves",
            f"{game_key}:rounds",
            f"{game_key}:active_players"
        ]
        
        # Add player hand keys
        players = await self.get_game_players(room_id)
        for player in players:
            player_id = player.get('player_id')
            if player_id:
                keys_to_delete.append(f"{game_key}:hand:{player_id}")
        
        # Delete all keys
        if keys_to_delete:
            await self.redis.delete(*keys_to_delete)
    
    # Utility Methods
    def _serialize_state(self, state: Dict[str, Any]) -> Dict[str, str]:
        """Serialize state data for Redis"""
        serialized = {}
        for key, value in state.items():
            if isinstance(value, (dict, list)):
                serialized[key] = json.dumps(value)
            else:
                serialized[key] = str(value)
        return serialized
    
    def _deserialize_state(self, state: Dict[str, str]) -> Dict[str, Any]:
        """Deserialize state data from Redis"""
        deserialized = {}
        for key, value in state.items():
            try:
                # Try to parse as JSON first
                deserialized[key] = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                # Try to parse as number
                try:
                    if '.' in value:
                        deserialized[key] = float(value)
                    else:
                        deserialized[key] = int(value)
                except ValueError:
                    # Keep as string
                    deserialized[key] = value
        return deserialized
    
    async def get_performance_metrics(self) -> Dict[str, Any]:
        """Get performance metrics"""
        return {
            **self.operation_counts,
            'lua_scripts_enabled': self.config.use_lua_scripts,
            'pipeline_operations_enabled': self.config.pipeline_operations,
            'batch_updates_enabled': self.config.batch_updates
        }
