# redis_manager_hybrid.py
import asyncio
import logging
from typing import Dict, List, Optional, Any, Tuple, Union
from concurrent.futures import ThreadPoolExecutor
import functools

from async_redis_manager import AsyncRedisManager
from redis_manager import RedisManager


class HybridRedisManager:
    """
    Hybrid Redis manager that provides both sync and async interfaces
    
    This allows for gradual migration from sync to async operations:
    - Existing sync code continues to work without changes
    - New code can use async methods for better performance
    - Provides migration path to full async implementation
    """
    
    def __init__(self, host='localhost', port=6379, db=0, pool_size=10):
        # Async manager (preferred)
        self.async_manager = AsyncRedisManager(host, port, db, pool_size)
        
        # Sync manager (fallback/compatibility)
        self.sync_manager = RedisManager()
        
        # Thread pool for running async operations in sync context
        self.thread_pool = ThreadPoolExecutor(max_workers=5, thread_name_prefix="redis_sync")
        
        # Connection state
        self._async_connected = False
    
    async def connect_async(self) -> bool:
        """Connect to Redis using async manager"""
        self._async_connected = await self.async_manager.connect()
        return self._async_connected
    
    async def disconnect_async(self):
        """Disconnect from Redis async manager"""
        await self.async_manager.disconnect()
        self._async_connected = False
    
    def _run_async_in_sync(self, coro):
        """Helper to run async coroutine in sync context"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If we're in an async context, run in thread pool
                future = asyncio.run_coroutine_threadsafe(coro, loop)
                return future.result(timeout=10.0)
            else:
                # If no loop is running, run directly
                return loop.run_until_complete(coro)
        except Exception:
            # Fallback: create new event loop
            new_loop = asyncio.new_event_loop()
            try:
                return new_loop.run_until_complete(coro)
            finally:
                new_loop.close()
    
    # ===== ASYNC METHODS (PREFERRED) =====
    
    async def save_player_session_async(self, player_id: str, session_data: dict) -> bool:
        """Async version of save_player_session"""
        return await self.async_manager.save_player_session(player_id, session_data)
    
    async def get_player_session_async(self, player_id: str) -> dict:
        """Async version of get_player_session"""
        return await self.async_manager.get_player_session(player_id)
    
    async def create_room_async(self, room_code: str) -> bool:
        """Async version of create_room"""
        return await self.async_manager.create_room(room_code)
    
    async def room_exists_async(self, room_code: str) -> bool:
        """Async version of room_exists"""
        return await self.async_manager.room_exists(room_code)
    
    async def add_player_to_room_async(self, room_code: str, player_data: dict) -> bool:
        """Async version of add_player_to_room"""
        return await self.async_manager.add_player_to_room(room_code, player_data)
    
    async def get_room_players_async(self, room_code: str) -> List[dict]:
        """Async version of get_room_players"""
        return await self.async_manager.get_room_players(room_code)
    
    async def save_game_state_async(self, room_code: str, game_state: dict) -> bool:
        """Async version of save_game_state"""
        return await self.async_manager.save_game_state(room_code, game_state)
    
    async def get_game_state_async(self, room_code: str) -> dict:
        """Async version of get_game_state"""
        return await self.async_manager.get_game_state(room_code)
    
    async def delete_game_state_async(self, room_code: str) -> bool:
        """Async version of delete_game_state"""
        return await self.async_manager.delete_game_state(room_code)
    
    async def clear_room_async(self, room_code: str) -> bool:
        """Async version of clear_room"""
        return await self.async_manager.clear_room(room_code)
    
    async def update_player_in_room_async(self, room_code: str, player_id: str, updated_data: dict) -> bool:
        """Async version of update_player_in_room"""
        return await self.async_manager.update_player_in_room(room_code, player_id, updated_data)
    
    async def update_player_heartbeat_async(self, player_id: str) -> bool:
        """Async version of update_player_heartbeat"""
        return await self.async_manager.update_player_heartbeat(player_id)
    
    async def check_player_connection_async(self, player_id: str) -> str:
        """Async version of check_player_connection"""
        return await self.async_manager.check_player_connection(player_id)
    
    async def get_active_rooms_async(self) -> List[str]:
        """Async version of get_active_rooms"""
        return await self.async_manager.get_active_rooms()
    
    async def cleanup_expired_sessions_async(self) -> int:
        """Async version of cleanup_expired_sessions"""
        return await self.async_manager.cleanup_expired_sessions()
    
    # ===== SYNC METHODS (COMPATIBILITY) =====
    
    def save_player_session(self, player_id: str, session_data: dict) -> bool:
        """Sync compatibility method"""
        if self._async_connected:
            try:
                return self._run_async_in_sync(
                    self.async_manager.save_player_session(player_id, session_data)
                )
            except Exception as e:
                logging.warning(f"Async operation failed, falling back to sync: {e}")
        
        return self.sync_manager.save_player_session(player_id, session_data)
    
    def get_player_session(self, player_id: str) -> dict:
        """Sync compatibility method"""
        if self._async_connected:
            try:
                return self._run_async_in_sync(
                    self.async_manager.get_player_session(player_id)
                )
            except Exception as e:
                logging.warning(f"Async operation failed, falling back to sync: {e}")
        
        return self.sync_manager.get_player_session(player_id)
    
    def create_room(self, room_code: str) -> bool:
        """Sync compatibility method"""
        if self._async_connected:
            try:
                return self._run_async_in_sync(
                    self.async_manager.create_room(room_code)
                )
            except Exception as e:
                logging.warning(f"Async operation failed, falling back to sync: {e}")
        
        return self.sync_manager.create_room(room_code)
    
    def room_exists(self, room_code: str) -> bool:
        """Sync compatibility method"""
        if self._async_connected:
            try:
                return self._run_async_in_sync(
                    self.async_manager.room_exists(room_code)
                )
            except Exception as e:
                logging.warning(f"Async operation failed, falling back to sync: {e}")
        
        return self.sync_manager.room_exists(room_code)
    
    def add_player_to_room(self, room_code: str, player_data: dict):
        """Sync compatibility method"""
        if self._async_connected:
            try:
                return self._run_async_in_sync(
                    self.async_manager.add_player_to_room(room_code, player_data)
                )
            except Exception as e:
                logging.warning(f"Async operation failed, falling back to sync: {e}")
        
        return self.sync_manager.add_player_to_room(room_code, player_data)
    
    def get_room_players(self, room_code: str) -> List[dict]:
        """Sync compatibility method"""
        if self._async_connected:
            try:
                return self._run_async_in_sync(
                    self.async_manager.get_room_players(room_code)
                )
            except Exception as e:
                logging.warning(f"Async operation failed, falling back to sync: {e}")
        
        return self.sync_manager.get_room_players(room_code)
    
    def save_game_state(self, room_code: str, game_state: dict) -> bool:
        """Sync compatibility method"""
        if self._async_connected:
            try:
                return self._run_async_in_sync(
                    self.async_manager.save_game_state(room_code, game_state)
                )
            except Exception as e:
                logging.warning(f"Async operation failed, falling back to sync: {e}")
        
        return self.sync_manager.save_game_state(room_code, game_state)
    
    def get_game_state(self, room_code: str) -> dict:
        """Sync compatibility method"""
        if self._async_connected:
            try:
                return self._run_async_in_sync(
                    self.async_manager.get_game_state(room_code)
                )
            except Exception as e:
                logging.warning(f"Async operation failed, falling back to sync: {e}")
        
        return self.sync_manager.get_game_state(room_code)
    
    def delete_game_state(self, room_code: str):
        """Sync compatibility method"""
        if self._async_connected:
            try:
                return self._run_async_in_sync(
                    self.async_manager.delete_game_state(room_code)
                )
            except Exception as e:
                logging.warning(f"Async operation failed, falling back to sync: {e}")
        
        return self.sync_manager.delete_game_state(room_code)
    
    def clear_room(self, room_code: str):
        """Sync compatibility method"""
        if self._async_connected:
            try:
                return self._run_async_in_sync(
                    self.async_manager.clear_room(room_code)
                )
            except Exception as e:
                logging.warning(f"Async operation failed, falling back to sync: {e}")
        
        return self.sync_manager.clear_room(room_code)
    
    def update_player_in_room(self, room_code: str, player_id: str, updated_data: dict):
        """Sync compatibility method"""
        if self._async_connected:
            try:
                return self._run_async_in_sync(
                    self.async_manager.update_player_in_room(room_code, player_id, updated_data)
                )
            except Exception as e:
                logging.warning(f"Async operation failed, falling back to sync: {e}")
        
        return self.sync_manager.update_player_in_room(room_code, player_id, updated_data)
    
    def update_player_heartbeat(self, player_id: str) -> bool:
        """Sync compatibility method"""
        if self._async_connected:
            try:
                return self._run_async_in_sync(
                    self.async_manager.update_player_heartbeat(player_id)
                )
            except Exception as e:
                logging.warning(f"Async operation failed, falling back to sync: {e}")
        
        return self.sync_manager.update_player_heartbeat(player_id)
    
    def check_player_connection(self, player_id: str) -> str:
        """Sync compatibility method"""
        if self._async_connected:
            try:
                return self._run_async_in_sync(
                    self.async_manager.check_player_connection(player_id)
                )
            except Exception as e:
                logging.warning(f"Async operation failed, falling back to sync: {e}")
        
        return self.sync_manager.check_player_connection(player_id)
    
    def get_active_rooms(self) -> List[str]:
        """Sync compatibility method"""
        if self._async_connected:
            try:
                return self._run_async_in_sync(
                    self.async_manager.get_active_rooms()
                )
            except Exception as e:
                logging.warning(f"Async operation failed, falling back to sync: {e}")
        
        return self.sync_manager.get_active_rooms()
    
    def cleanup_expired_sessions(self):
        """Sync compatibility method"""
        if self._async_connected:
            try:
                return self._run_async_in_sync(
                    self.async_manager.cleanup_expired_sessions()
                )
            except Exception as e:
                logging.warning(f"Async operation failed, falling back to sync: {e}")
        
        return self.sync_manager.cleanup_expired_sessions()
    
    # ===== ADDITIONAL COMPATIBILITY METHODS =====
    
    def delete_player_session(self, player_id: str):
        """Sync compatibility method"""
        if self._async_connected:
            try:
                return self._run_async_in_sync(
                    self.async_manager.delete_player_session(player_id)
                )
            except Exception as e:
                logging.warning(f"Async operation failed, falling back to sync: {e}")
        
        return self.sync_manager.delete_player_session(player_id)
    
    def delete_room(self, room_code: str):
        """Sync compatibility method"""
        if self._async_connected:
            try:
                return self._run_async_in_sync(
                    self.async_manager.delete_room(room_code)
                )
            except Exception as e:
                logging.warning(f"Async operation failed, falling back to sync: {e}")
        
        return self.sync_manager.delete_room(room_code)
    
    def mark_player_disconnected(self, player_id: str):
        """Sync compatibility method"""
        if self._async_connected:
            try:
                return self._run_async_in_sync(
                    self.async_manager.mark_player_disconnected(player_id)
                )
            except Exception as e:
                logging.warning(f"Async operation failed, falling back to sync: {e}")
        
        return self.sync_manager.mark_player_disconnected(player_id)
    
    def handle_player_disconnect_from_room(self, room_code: str, player_id: str):
        """Sync compatibility method"""
        if self._async_connected:
            try:
                return self._run_async_in_sync(
                    self.async_manager.handle_player_disconnect_from_room(room_code, player_id)
                )
            except Exception as e:
                logging.warning(f"Async operation failed, falling back to sync: {e}")
        
        return self.sync_manager.handle_player_disconnect_from_room(room_code, player_id)
    
    def validate_session(self, player_id: str) -> Tuple[bool, str]:
        """Sync compatibility method"""
        if self._async_connected:
            try:
                return self._run_async_in_sync(
                    self.async_manager.validate_session(player_id)
                )
            except Exception as e:
                logging.warning(f"Async operation failed, falling back to sync: {e}")
        
        return self.sync_manager.validate_session(player_id)
    
    def attempt_reconnect(self, player_id: str, connection_data: dict) -> Tuple[bool, dict]:
        """Sync compatibility method"""
        if self._async_connected:
            try:
                return self._run_async_in_sync(
                    self.async_manager.attempt_reconnect(player_id, connection_data)
                )
            except Exception as e:
                logging.warning(f"Async operation failed, falling back to sync: {e}")
        
        return self.sync_manager.attempt_reconnect(player_id, connection_data)
    
    def is_game_completed(self, room_code: str) -> bool:
        """Sync compatibility method"""
        if self._async_connected:
            try:
                return self._run_async_in_sync(
                    self.async_manager.is_game_completed(room_code)
                )
            except Exception as e:
                logging.warning(f"Async operation failed, falling back to sync: {e}")
        
        return self.sync_manager.is_game_completed(room_code)
    
    def debug_room_state(self, room_code: str):
        """Sync compatibility method"""
        if self._async_connected:
            try:
                return self._run_async_in_sync(
                    self.async_manager.debug_room_state(room_code)
                )
            except Exception as e:
                logging.warning(f"Async operation failed, falling back to sync: {e}")
        
        return self.sync_manager.debug_room_state(room_code)
    
    def validate_game_state(self, state: dict) -> Tuple[bool, str]:
        """Sync compatibility method"""
        if self._async_connected:
            return self.async_manager.validate_game_state(state)
        return self.sync_manager.validate_game_state(state)
    
    def get_performance_metrics(self) -> dict:
        """Get performance metrics from active manager"""
        if self._async_connected:
            return self.async_manager.get_performance_metrics()
        return self.sync_manager.get_performance_metrics()
    
    def __del__(self):
        """Cleanup thread pool on destruction"""
        self.thread_pool.shutdown(wait=False)
