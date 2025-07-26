
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
    """Initialize server with async Redis connection"""
    self._redis_connected = await self.redis_manager.connect_async()
    if not self._redis_connected:
        raise Exception("Failed to connect to Redis")
    return True

async def shutdown(self):
    """Clean shutdown with proper Redis disconnection"""
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
