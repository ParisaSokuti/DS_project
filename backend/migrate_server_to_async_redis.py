# migrate_server_to_async_redis.py
"""
Migration script for converting server.py to use async Redis operations

This script demonstrates:
1. How to replace blocking Redis operations with async versions
2. How to remove ThreadPoolExecutor workarounds
3. How to properly handle connection management
4. How to maintain backward compatibility during migration
"""

import asyncio
import sys
import websockets
import json
import uuid
import random
import time
import os
import traceback
import logging

# Add current directory to Python path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from network import NetworkManager
from game_board import GameBoard
from game_states import GameState
from async_redis_manager import AsyncRedisManager  # Direct async usage
from redis_manager_hybrid import HybridRedisManager  # Or hybrid for gradual migration
from circuit_breaker_monitor import CircuitBreakerMonitor
from game_auth_manager import GameAuthManager

# Constants
ROOM_SIZE = 4

class AsyncGameServer:
    """
    Async-first version of GameServer with proper Redis async operations
    
    Key improvements:
    - All Redis operations are truly async (no thread pool executors)
    - Proper connection management and error handling
    - Better performance with connection pooling
    - Cleaner code without timeout workarounds
    """
    
    def __init__(self, use_hybrid=False):
        if use_hybrid:
            # Option 1: Use hybrid manager for gradual migration
            self.redis_manager = HybridRedisManager()
        else:
            # Option 2: Use pure async manager for maximum performance
            self.redis_manager = AsyncRedisManager()
        
        self.network_manager = NetworkManager()
        self.auth_manager = GameAuthManager()
        self.active_games = {}  # Maps room_code -> GameBoard for active games only
        
        # Setup logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
    
    async def startup(self):
        """Initialize server and connect to Redis"""
        try:
            # Connect to Redis
            if hasattr(self.redis_manager, 'connect_async'):
                # Using hybrid manager
                success = await self.redis_manager.connect_async()
            else:
                # Using pure async manager
                success = await self.redis_manager.connect()
            
            if not success:
                self.logger.error("Failed to connect to Redis")
                return False
            
            self.logger.info("Redis connection established")
            
            # Initialize circuit breaker monitor if needed
            if hasattr(self, 'circuit_breaker_monitor'):
                self.circuit_breaker_monitor = CircuitBreakerMonitor(self.redis_manager)
            
            return True
        except Exception as e:
            self.logger.error(f"Server startup failed: {e}")
            return False
    
    async def shutdown(self):
        """Clean shutdown"""
        try:
            if hasattr(self.redis_manager, 'disconnect_async'):
                # Using hybrid manager
                await self.redis_manager.disconnect_async()
            else:
                # Using pure async manager
                await self.redis_manager.disconnect()
            
            self.logger.info("Server shutdown complete")
        except Exception as e:
            self.logger.error(f"Error during shutdown: {e}")
    
    async def handle_join(self, websocket, data):
        """
        Handle a new player joining - ASYNC VERSION
        
        This demonstrates how to replace the old blocking pattern:
        OLD:
            await asyncio.wait_for(
                loop.run_in_executor(executor, self.redis_manager.create_room, room_code),
                timeout=2.0
            )
        
        NEW:
            await self.redis_manager.create_room_async(room_code)
        """
        self.logger.debug(f"handle_join called with data: {data}")
        
        try:
            room_code = data.get('room_code', '9999')
            self.logger.debug(f"Room code: {room_code}")
            
            # Check if room exists - ASYNC VERSION
            self.logger.debug("Checking if room exists...")
            try:
                # OLD BLOCKING VERSION:
                # room_exists = await asyncio.wait_for(
                #     loop.run_in_executor(executor, self.redis_manager.room_exists, room_code),
                #     timeout=2.0
                # )
                
                # NEW ASYNC VERSION:
                if hasattr(self.redis_manager, 'room_exists_async'):
                    room_exists = await self.redis_manager.room_exists_async(room_code)
                else:
                    room_exists = await self.redis_manager.room_exists(room_code)
                
                self.logger.debug(f"Room exists check result: {room_exists}")
            except Exception as e:
                self.logger.warning(f"Room check failed: {e}, assuming new room")
                room_exists = False
            
            # Create room if it doesn't exist - ASYNC VERSION
            if not room_exists:
                self.logger.debug(f"Room {room_code} doesn't exist, creating it")
                try:
                    # OLD BLOCKING VERSION:
                    # await asyncio.wait_for(
                    #     loop.run_in_executor(executor, self.redis_manager.create_room, room_code),
                    #     timeout=2.0
                    # )
                    
                    # NEW ASYNC VERSION:
                    if hasattr(self.redis_manager, 'create_room_async'):
                        success = await self.redis_manager.create_room_async(room_code)
                    else:
                        success = await self.redis_manager.create_room(room_code)
                    
                    if success:
                        self.logger.info(f"Room {room_code} created successfully")
                    else:
                        self.logger.warning(f"Failed to create room {room_code}")
                        
                except Exception as e:
                    self.logger.error(f"Failed to create room {room_code}: {str(e)}")
                    # Continue anyway - room creation is not critical for basic functionality
            
            # Process player data and add to room
            player_id = data.get('player_id') or str(uuid.uuid4())
            username = data.get('username', f'Player_{player_id[:8]}')
            
            player_data = {
                'player_id': player_id,
                'username': username,
                'connection_status': 'active',
                'websocket_id': id(websocket),
                'joined_at': str(int(time.time()))
            }
            
            # Add player to room - ASYNC VERSION
            try:
                # OLD BLOCKING VERSION:
                # await asyncio.wait_for(
                #     loop.run_in_executor(executor, self.redis_manager.add_player_to_room, room_code, player_data),
                #     timeout=2.0
                # )
                
                # NEW ASYNC VERSION:
                if hasattr(self.redis_manager, 'add_player_to_room_async'):
                    success = await self.redis_manager.add_player_to_room_async(room_code, player_data)
                else:
                    success = await self.redis_manager.add_player_to_room(room_code, player_data)
                
                if success:
                    self.logger.info(f"Added player {username} to room {room_code}")
                else:
                    self.logger.warning(f"Failed to add player {username} to room {room_code}")
                    
            except Exception as e:
                self.logger.error(f"Error adding player to room: {e}")
                return await self._send_error(websocket, "Failed to join room")
            
            # Save player session - ASYNC VERSION
            try:
                session_data = {
                    'room_code': room_code,
                    'username': username,
                    'websocket_id': id(websocket),
                    'connection_status': 'active'
                }
                
                # OLD BLOCKING VERSION:
                # await asyncio.wait_for(
                #     loop.run_in_executor(executor, self.redis_manager.save_player_session, player_id, session_data),
                #     timeout=2.0
                # )
                
                # NEW ASYNC VERSION:
                if hasattr(self.redis_manager, 'save_player_session_async'):
                    await self.redis_manager.save_player_session_async(player_id, session_data)
                else:
                    await self.redis_manager.save_player_session(player_id, session_data)
                
            except Exception as e:
                self.logger.error(f"Error saving player session: {e}")
            
            # Register with network manager
            self.network_manager.register_connection(websocket, {
                'player_id': player_id,
                'username': username,
                'room_code': room_code
            })
            
            # Check if room is ready to start game
            await self._check_room_ready(room_code)
            
            # Send join confirmation
            await self._send_response(websocket, {
                'type': 'join_success',
                'player_id': player_id,
                'username': username,
                'room_code': room_code
            })
            
        except Exception as e:
            self.logger.error(f"Error in handle_join: {e}")
            await self._send_error(websocket, "Failed to join game")
    
    async def start_team_assignment(self, room_code: str):
        """
        Start team assignment phase - ASYNC VERSION
        """
        try:
            self.logger.debug(f"Getting players for room {room_code} to start game")
            
            # Get room players - ASYNC VERSION
            try:
                # OLD BLOCKING VERSION:
                # room_players_data = await asyncio.wait_for(
                #     loop.run_in_executor(executor, self.redis_manager.get_room_players, room_code),
                #     timeout=2.0
                # )
                
                # NEW ASYNC VERSION:
                if hasattr(self.redis_manager, 'get_room_players_async'):
                    room_players_data = await self.redis_manager.get_room_players_async(room_code)
                else:
                    room_players_data = await self.redis_manager.get_room_players(room_code)
                
                players = [p['username'] for p in room_players_data]
                self.logger.debug(f"Got players from Redis: {players}")
                
            except Exception as e:
                self.logger.warning(f"Failed to get room players: {e}")
                # Fallback: get players from network manager connections
                players = []
                for ws, metadata in self.network_manager.connection_metadata.items():
                    if metadata.get('room_code') == room_code:
                        players.append(metadata['username'])
            
            if len(players) >= ROOM_SIZE:
                # Initialize game
                game = GameBoard(players)
                self.active_games[room_code] = game
                
                # Save initial game state - ASYNC VERSION
                game_state = {
                    'phase': GameState.TEAM_ASSIGNMENT.value,
                    'players': players,
                    'created_at': str(int(time.time())),
                    'last_activity': str(int(time.time()))
                }
                
                # OLD BLOCKING VERSION:
                # await asyncio.wait_for(
                #     loop.run_in_executor(executor, self.redis_manager.save_game_state, room_code, game_state),
                #     timeout=2.0
                # )
                
                # NEW ASYNC VERSION:
                if hasattr(self.redis_manager, 'save_game_state_async'):
                    await self.redis_manager.save_game_state_async(room_code, game_state)
                else:
                    await self.redis_manager.save_game_state(room_code, game_state)
                
                # Notify players
                await self._broadcast_to_room(room_code, {
                    'type': 'team_assignment_start',
                    'players': players
                })
                
                self.logger.info(f"Started team assignment for room {room_code}")
            
        except Exception as e:
            self.logger.error(f"Error starting team assignment: {e}")
    
    async def _check_room_ready(self, room_code: str):
        """Check if room is ready to start and initiate game phases"""
        try:
            # Get current players - ASYNC VERSION
            if hasattr(self.redis_manager, 'get_room_players_async'):
                players = await self.redis_manager.get_room_players_async(room_code)
            else:
                players = await self.redis_manager.get_room_players(room_code)
            
            active_players = [p for p in players if p.get('connection_status') == 'active']
            
            if len(active_players) >= ROOM_SIZE:
                await self.start_team_assignment(room_code)
                
        except Exception as e:
            self.logger.error(f"Error checking room ready state: {e}")
    
    async def _broadcast_to_room(self, room_code: str, message: dict):
        """Broadcast message to all players in a room"""
        try:
            for websocket, metadata in self.network_manager.connection_metadata.items():
                if metadata.get('room_code') == room_code:
                    try:
                        await websocket.send(json.dumps(message))
                    except Exception as e:
                        self.logger.warning(f"Failed to send message to websocket: {e}")
        except Exception as e:
            self.logger.error(f"Error broadcasting to room {room_code}: {e}")
    
    async def _send_response(self, websocket, message: dict):
        """Send response to specific websocket"""
        try:
            await websocket.send(json.dumps(message))
        except Exception as e:
            self.logger.error(f"Failed to send response: {e}")
    
    async def _send_error(self, websocket, error_message: str):
        """Send error message to websocket"""
        try:
            await websocket.send(json.dumps({
                'type': 'error',
                'message': error_message
            }))
        except Exception as e:
            self.logger.error(f"Failed to send error message: {e}")
    
    async def handle_websocket(self, websocket, path):
        """Handle WebSocket connections"""
        try:
            self.logger.info(f"New WebSocket connection from {websocket.remote_address}")
            
            async for message in websocket:
                try:
                    data = json.loads(message)
                    message_type = data.get('type')
                    
                    if message_type == 'join':
                        await self.handle_join(websocket, data)
                    # Add other message handlers here
                    else:
                        await self._send_error(websocket, f"Unknown message type: {message_type}")
                        
                except json.JSONDecodeError:
                    await self._send_error(websocket, "Invalid JSON message")
                except Exception as e:
                    self.logger.error(f"Error handling message: {e}")
                    await self._send_error(websocket, "Internal server error")
                    
        except websockets.exceptions.ConnectionClosed:
            self.logger.info("WebSocket connection closed")
        except Exception as e:
            self.logger.error(f"WebSocket error: {e}")
        finally:
            # Clean up connection
            self.network_manager.unregister_connection(websocket)

async def main():
    """Main server entry point"""
    # Create server instance
    server = AsyncGameServer(use_hybrid=False)  # Set to True for gradual migration
    
    # Startup
    if not await server.startup():
        print("Failed to start server")
        return
    
    try:
        # Start WebSocket server
        start_server = websockets.serve(
            server.handle_websocket,
            "localhost",
            8765,
            ping_interval=20,
            ping_timeout=10
        )
        
        print("AsyncGameServer started on ws://localhost:8765")
        await start_server
        
        # Keep server running
        await asyncio.Future()  # Run forever
        
    except KeyboardInterrupt:
        print("Server stopped by user")
    finally:
        await server.shutdown()

if __name__ == "__main__":
    # Run the async server
    asyncio.run(main())
