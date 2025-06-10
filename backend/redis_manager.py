# redis_manager.py
import redis
import json
import time
from typing import Dict, List, Optional, Any

class RedisManager:
    def __init__(self):
        self.redis = redis.Redis(host='localhost', port=6379, db=0)
        
    def save_player_session(self, player_id: str, session_data: dict):
        key = f"session:{player_id}"
        self.redis.hset(key, mapping=session_data)
        self.redis.expire(key, 3600)  # Session expires in 1 hour
    
    def get_player_session(self, player_id: str) -> dict:
        key = f"session:{player_id}"
        return {k.decode(): v.decode() for k, v in self.redis.hgetall(key).items()}
    
    def add_player_to_room(self, room_code: str, player_data: dict):
        key = f"room:{room_code}:players"
        self.redis.rpush(key, json.dumps(player_data))
        
    def get_room_players(self, room_code: str) -> List[dict]:
        key = f"room:{room_code}:players"
        players = self.redis.lrange(key, 0, -1)
        return [json.loads(p.decode()) for p in players]
    
    def save_game_state(self, room_code: str, game_state: dict):
        key = f"game:{room_code}:state"
        self.redis.hset(key, mapping=game_state)
        
    def get_game_state(self, room_code: str) -> dict:
        key = f"game:{room_code}:state"
        return {k.decode(): v.decode() for k, v in self.redis.hgetall(key).items()}
    
    def clear_room(self, room_code: str):
        """Clean up room data"""
        self.redis.delete(f"room:{room_code}:players")
        self.redis.delete(f"game:{room_code}:state")

    def room_exists(self, room_code: str) -> bool:
        """Check if a room exists"""
        key = f"room:{room_code}:players"
        return bool(self.redis.exists(key))

    def create_room(self, room_code: str):
        """Create a new room"""
        if not self.room_exists(room_code):
            key = f"room:{room_code}:players"
            self.redis.delete(key)  # Clear any stale data
            self.redis.rpush(key, "")  # Initialize empty list
            self.redis.lrem(key, 1, "")  # Remove the empty placeholder

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
