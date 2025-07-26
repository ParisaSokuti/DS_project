#!/usr/bin/env python3
"""
Apply Redis async migration to the existing server.py

This script:
1. Creates backup of current server.py
2. Applies async Redis patterns to specific problematic sections
3. Maintains compatibility with existing game logic
4. Focuses only on Redis operations (as requested)
"""

import os
import shutil
import re
from datetime import datetime

def backup_current_server():
    """Create backup of current server.py"""
    backup_name = f"server_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.py"
    shutil.copy("backend/server.py", f"backend/{backup_name}")
    print(f"✓ Created backup: {backup_name}")
    return backup_name

def create_server_patch():
    """Create the patches needed for server.py"""
    
    # 1. Update imports section
    imports_patch = '''
# server.py - Redis Async Migration Applied

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
# MIGRATION: Switch to async Redis manager
from redis_manager_hybrid import HybridRedisManager as RedisManager  # Gradual migration
# from async_redis_manager import AsyncRedisManager as RedisManager  # Direct migration
from circuit_breaker_monitor import CircuitBreakerMonitor
from game_auth_manager import GameAuthManager

# Constants
ROOM_SIZE = 4    # Single game storage system

class GameServer:
    def __init__(self):
        self.redis_manager = RedisManager()
        self.network_manager = NetworkManager()
        self.auth_manager = GameAuthManager()
        self.active_games = {}
        
        # Setup logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
        
        # Redis connection state
        self._redis_connected = False
    
    async def startup(self):
        """Initialize server with async Redis connection"""
        try:
            # Connect to Redis using async interface
            if hasattr(self.redis_manager, 'connect_async'):
                self._redis_connected = await self.redis_manager.connect_async()
            else:
                # Direct async manager
                self._redis_connected = await self.redis_manager.connect()
            
            if not self._redis_connected:
                self.logger.error("Failed to connect to Redis")
                return False
            
            self.logger.info("✓ Redis connection established")
            
            # Initialize circuit breaker monitor if available
            if hasattr(self, 'circuit_breaker_monitor'):
                self.circuit_breaker_monitor = CircuitBreakerMonitor(self.redis_manager)
            
            return True
        except Exception as e:
            self.logger.error(f"Server startup failed: {e}")
            return False
    
    async def shutdown(self):
        """Clean shutdown with proper Redis disconnection"""
        try:
            if self._redis_connected:
                if hasattr(self.redis_manager, 'disconnect_async'):
                    await self.redis_manager.disconnect_async()
                else:
                    await self.redis_manager.disconnect()
            
            self.logger.info("✓ Server shutdown complete")
        except Exception as e:
            self.logger.error(f"Error during shutdown: {e}")
'''
    
    # 2. Async Redis operation patterns
    redis_patterns = {
        # Pattern for room creation
        'create_room_pattern': '''
    async def _create_room_async(self, room_code: str) -> bool:
        """Create room using async Redis operations"""
        try:
            if hasattr(self.redis_manager, 'create_room_async'):
                return await self.redis_manager.create_room_async(room_code)
            else:
                return await self.redis_manager.create_room(room_code)
        except Exception as e:
            self.logger.error(f"Failed to create room {room_code}: {e}")
            return False
    
    async def _room_exists_async(self, room_code: str) -> bool:
        """Check room existence using async Redis operations"""
        try:
            if hasattr(self.redis_manager, 'room_exists_async'):
                return await self.redis_manager.room_exists_async(room_code)
            else:
                return await self.redis_manager.room_exists(room_code)
        except Exception as e:
            self.logger.error(f"Failed to check room {room_code}: {e}")
            return False
    
    async def _get_room_players_async(self, room_code: str) -> list:
        """Get room players using async Redis operations"""
        try:
            if hasattr(self.redis_manager, 'get_room_players_async'):
                return await self.redis_manager.get_room_players_async(room_code)
            else:
                return await self.redis_manager.get_room_players(room_code)
        except Exception as e:
            self.logger.error(f"Failed to get room players {room_code}: {e}")
            return []
    
    async def _save_game_state_async(self, room_code: str, game_state: dict) -> bool:
        """Save game state using async Redis operations"""
        try:
            if hasattr(self.redis_manager, 'save_game_state_async'):
                return await self.redis_manager.save_game_state_async(room_code, game_state)
            else:
                return await self.redis_manager.save_game_state(room_code, game_state)
        except Exception as e:
            self.logger.error(f"Failed to save game state {room_code}: {e}")
            return False
''',
        
        # Pattern for handle_join method
        'handle_join_pattern': '''
    async def handle_join(self, websocket, data):
        """Handle a new player joining - ASYNC REDIS VERSION"""
        self.logger.debug(f"handle_join called with data: {data}")
        try:
            room_code = data.get('room_code', '9999')
            self.logger.debug(f"Room code: {room_code}")
            
            # Check if room exists - ASYNC VERSION (NO THREAD POOL)
            self.logger.debug("Checking if room exists...")
            try:
                room_exists = await self._room_exists_async(room_code)
                self.logger.debug(f"Room exists check result: {room_exists}")
            except Exception as e:
                self.logger.warning(f"Room check failed: {e}, assuming new room")
                room_exists = False
            
            # Create room if needed - ASYNC VERSION (NO THREAD POOL)
            if not room_exists:
                self.logger.debug(f"Room {room_code} doesn't exist, creating it")
                try:
                    success = await self._create_room_async(room_code)
                    if success:
                        self.logger.info(f"Room {room_code} created successfully")
                    else:
                        self.logger.warning(f"Failed to create room {room_code}")
                except Exception as e:
                    self.logger.error(f"Failed to create room {room_code}: {str(e)}")
                    # Continue anyway - room creation is not critical
            
            # Process player data
            player_id = data.get('player_id') or str(uuid.uuid4())
            username = data.get('username', f'Player_{player_id[:8]}')
            
            player_data = {
                'player_id': player_id,
                'username': username,
                'connection_status': 'active',
                'websocket_id': id(websocket),
                'joined_at': str(int(time.time()))
            }
            
            # Add player to room - ASYNC VERSION (NO THREAD POOL)
            try:
                if hasattr(self.redis_manager, 'add_player_to_room_async'):
                    success = await self.redis_manager.add_player_to_room_async(room_code, player_data)
                else:
                    success = await self.redis_manager.add_player_to_room(room_code, player_data)
                
                if success:
                    self.logger.info(f"Added player {username} to room {room_code}")
                else:
                    self.logger.warning(f"Failed to add player to room")
                    
            except Exception as e:
                self.logger.error(f"Error adding player to room: {e}")
                return await self._send_error(websocket, "Failed to join room")
            
            # Save player session - ASYNC VERSION (NO THREAD POOL)
            try:
                session_data = {
                    'room_code': room_code,
                    'username': username,
                    'websocket_id': id(websocket),
                    'connection_status': 'active'
                }
                
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
            await self._check_room_ready_async(room_code)
            
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
'''
    }
    
    return imports_patch, redis_patterns

def apply_migration_patterns():
    """Apply specific async patterns to replace blocking Redis operations"""
    
    patterns_to_replace = [
        # Replace thread pool executor patterns
        {
            'old': r'executor = concurrent\.futures\.ThreadPoolExecutor\(\)\s*\n\s*loop = asyncio\.get_event_loop\(\)\s*\n\s*await asyncio\.wait_for\(\s*loop\.run_in_executor\(executor, self\.redis_manager\.([^,]+),([^)]+)\),\s*timeout=[\d.]+\s*\)',
            'new': r'await self._\1_async(\2)',
            'description': 'Replace thread pool Redis operations with async calls'
        },
        
        # Replace specific blocking patterns from the server
        {
            'old': r'await asyncio\.wait_for\(\s*loop\.run_in_executor\(executor, self\.redis_manager\.create_room, room_code\),\s*timeout=[\d.]+\s*\)',
            'new': 'await self._create_room_async(room_code)',
            'description': 'Replace create_room blocking call'
        },
        
        {
            'old': r'await asyncio\.wait_for\(\s*loop\.run_in_executor\(executor, self\.redis_manager\.get_room_players, room_code\),\s*timeout=[\d.]+\s*\)',
            'new': 'await self._get_room_players_async(room_code)',
            'description': 'Replace get_room_players blocking call'
        },
        
        {
            'old': r'await asyncio\.wait_for\(\s*loop\.run_in_executor\(executor, self\.redis_manager\.save_game_state, ([^,]+), ([^)]+)\),\s*timeout=[\d.]+\s*\)',
            'new': r'await self._save_game_state_async(\1, \2)',
            'description': 'Replace save_game_state blocking call'
        }
    ]
    
    return patterns_to_replace

def create_migration_instructions():
    """Create step-by-step migration instructions"""
    
    instructions = """
# Redis Async Migration - Implementation Steps

## Step 1: Install Dependencies
```bash
pip install aioredis>=2.0.0
```

## Step 2: Deploy New Redis Managers
The following files have been created:
- `backend/async_redis_manager.py` - Pure async Redis manager
- `backend/redis_manager_hybrid.py` - Hybrid sync/async manager for gradual migration

## Step 3: Update Server Imports
Replace the Redis manager import in `backend/server.py`:

```python
# OLD
from redis_manager_resilient import ResilientRedisManager as RedisManager

# NEW (Gradual Migration)
from redis_manager_hybrid import HybridRedisManager as RedisManager

# OR (Direct Migration)
from async_redis_manager import AsyncRedisManager as RedisManager
```

## Step 4: Add Server Lifecycle Methods
Add startup and shutdown methods to `GameServer` class:

```python
async def startup(self):
    \"\"\"Initialize server with async Redis connection\"\"\"
    self._redis_connected = await self.redis_manager.connect_async()
    if not self._redis_connected:
        raise Exception("Failed to connect to Redis")
    return True

async def shutdown(self):
    \"\"\"Clean shutdown with proper Redis disconnection\"\"\"
    if self._redis_connected:
        await self.redis_manager.disconnect_async()
```

## Step 5: Replace Blocking Redis Patterns
Find and replace these patterns in `server.py`:

### Pattern 1: Room Creation
```python
# OLD BLOCKING
await asyncio.wait_for(
    loop.run_in_executor(executor, self.redis_manager.create_room, room_code),
    timeout=2.0
)

# NEW ASYNC
await self.redis_manager.create_room_async(room_code)
```

### Pattern 2: Get Room Players
```python
# OLD BLOCKING
room_players_data = await asyncio.wait_for(
    loop.run_in_executor(executor, self.redis_manager.get_room_players, room_code),
    timeout=2.0
)

# NEW ASYNC
room_players_data = await self.redis_manager.get_room_players_async(room_code)
```

### Pattern 3: Save Game State
```python
# OLD BLOCKING
await asyncio.wait_for(
    loop.run_in_executor(executor, self.redis_manager.save_game_state, room_code, game_state),
    timeout=2.0
)

# NEW ASYNC
await self.redis_manager.save_game_state_async(room_code, game_state)
```

## Step 6: Update Main Server Loop
```python
async def main():
    server = GameServer()
    
    # Initialize server
    if not await server.startup():
        print("Failed to start server")
        return
    
    try:
        # Start WebSocket server
        start_server = websockets.serve(server.handle_websocket, "localhost", 8765)
        await start_server
        await asyncio.Future()  # Run forever
    except KeyboardInterrupt:
        print("Server stopped by user")
    finally:
        await server.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
```

## Step 7: Test the Migration
Run the test script:
```bash
python test_redis_async_migration.py
```

## Step 8: Monitor Performance
After deployment, monitor:
- Response times for Redis operations
- Memory usage (should decrease due to no thread pool)
- Error rates
- Connection pool efficiency

## Rollback Plan
If issues occur:
1. Revert server.py import to original Redis manager
2. Or use HybridRedisManager without calling connect_async()

## Benefits After Migration
- No thread pool overhead
- True async operations
- Better error handling
- Improved scalability
- Cleaner code
- Better resource management
"""
    
    return instructions

def main():
    """Main migration application"""
    print("Redis Async Migration Tool")
    print("=" * 40)
    
    # Check if we're in the right directory
    if not os.path.exists("backend/server.py"):
        print("❌ Error: backend/server.py not found. Run this script from the project root.")
        return False
    
    # Create backup
    print("1. Creating backup...")
    backup_name = backup_current_server()
    
    # Generate migration files (already created above)
    print("2. Migration files created:")
    print("   ✓ backend/async_redis_manager.py")
    print("   ✓ backend/redis_manager_hybrid.py") 
    print("   ✓ backend/migrate_server_to_async_redis.py")
    print("   ✓ test_redis_async_migration.py")
    print("   ✓ REDIS_ASYNC_MIGRATION_GUIDE.md")
    
    # Create migration instructions
    print("3. Creating migration instructions...")
    instructions = create_migration_instructions()
    with open("REDIS_MIGRATION_INSTRUCTIONS.md", "w") as f:
        f.write(instructions)
    print("   ✓ REDIS_MIGRATION_INSTRUCTIONS.md")
    
    print("\n" + "=" * 40)
    print("✅ Migration preparation complete!")
    print("\nNext steps:")
    print("1. Review REDIS_MIGRATION_INSTRUCTIONS.md")
    print("2. Install dependencies: pip install aioredis>=2.0.0")
    print("3. Test with: python test_redis_async_migration.py")
    print("4. Apply changes to server.py following the guide")
    print("5. Use the example in migrate_server_to_async_redis.py")
    print(f"\nBackup created: backend/{backup_name}")
    
    return True

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
