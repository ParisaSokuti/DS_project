# Redis Async Migration Guide

## Overview
This guide provides step-by-step instructions for migrating from blocking Redis operations to async Redis operations in the distributed card game server.

## Current Problem
The existing server uses blocking Redis operations in async contexts, causing performance issues:

```python
# PROBLEMATIC PATTERN (current)
await asyncio.wait_for(
    loop.run_in_executor(executor, self.redis_manager.get_room_players, room_code),
    timeout=2.0
)
```

## Solution Components

### 1. AsyncRedisManager (`async_redis_manager.py`)
- Pure async implementation using `aioredis`
- Connection pooling for better performance
- Proper error handling and timeouts
- Compatible interface with existing RedisManager

### 2. HybridRedisManager (`redis_manager_hybrid.py`)
- Provides both sync and async interfaces
- Allows gradual migration without breaking existing code
- Automatic fallback to sync operations if async fails

### 3. Migration Example (`migrate_server_to_async_redis.py`)
- Complete example of migrated server
- Shows before/after patterns
- Demonstrates proper async/await usage

## Migration Steps

### Step 1: Install Dependencies
```bash
pip install aioredis>=2.0.0
```

### Step 2: Choose Migration Strategy

#### Option A: Gradual Migration (Recommended)
Use `HybridRedisManager` to migrate incrementally:

```python
# In server.py
from redis_manager_hybrid import HybridRedisManager

class GameServer:
    def __init__(self):
        self.redis_manager = HybridRedisManager()
        
    async def startup(self):
        # Enable async mode
        await self.redis_manager.connect_async()
```

#### Option B: Full Migration
Replace with `AsyncRedisManager` directly:

```python
# In server.py
from async_redis_manager import AsyncRedisManager

class GameServer:
    def __init__(self):
        self.redis_manager = AsyncRedisManager()
        
    async def startup(self):
        await self.redis_manager.connect()
```

### Step 3: Update Server Initialization

```python
# OLD VERSION
class GameServer:
    def __init__(self):
        self.redis_manager = RedisManager()
        # ... other initialization

# NEW VERSION  
class GameServer:
    def __init__(self):
        self.redis_manager = HybridRedisManager()  # or AsyncRedisManager
        
    async def startup(self):
        """Add proper startup sequence"""
        success = await self.redis_manager.connect_async()
        if not success:
            raise Exception("Failed to connect to Redis")
        return True
        
    async def shutdown(self):
        """Add proper shutdown sequence"""
        await self.redis_manager.disconnect_async()
```

### Step 4: Replace Blocking Redis Operations

#### Pattern 1: Basic Operations
```python
# OLD BLOCKING VERSION
await asyncio.wait_for(
    loop.run_in_executor(executor, self.redis_manager.create_room, room_code),
    timeout=2.0
)

# NEW ASYNC VERSION
await self.redis_manager.create_room_async(room_code)
```

#### Pattern 2: Data Retrieval
```python
# OLD BLOCKING VERSION
room_players_data = await asyncio.wait_for(
    loop.run_in_executor(executor, self.redis_manager.get_room_players, room_code),
    timeout=2.0
)

# NEW ASYNC VERSION
room_players_data = await self.redis_manager.get_room_players_async(room_code)
```

#### Pattern 3: State Management
```python
# OLD BLOCKING VERSION
await asyncio.wait_for(
    loop.run_in_executor(executor, self.redis_manager.save_game_state, room_code, game_state),
    timeout=2.0
)

# NEW ASYNC VERSION
await self.redis_manager.save_game_state_async(room_code, game_state)
```

### Step 5: Update Error Handling

```python
# OLD VERSION with timeout handling
try:
    await asyncio.wait_for(
        loop.run_in_executor(executor, self.redis_manager.operation),
        timeout=2.0
    )
except asyncio.TimeoutError:
    print("Redis timeout, continuing anyway")
    
# NEW VERSION with proper async error handling
try:
    await self.redis_manager.operation_async()
except Exception as e:
    logging.error(f"Redis operation failed: {e}")
    # Handle specific error types as needed
```

### Step 6: Update Main Server Loop

```python
# Add to main server startup
async def main():
    server = GameServer()
    
    # Initialize server
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
        
        print("Server started on ws://localhost:8765")
        await start_server
        await asyncio.Future()  # Run forever
        
    except KeyboardInterrupt:
        print("Server stopped by user")
    finally:
        await server.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
```

## Performance Benefits

### Before Migration
- Each Redis operation blocks the event loop
- Thread pool overhead for every operation
- Complex timeout and fallback logic
- Potential memory leaks from executor threads

### After Migration
- True async operations with connection pooling
- No thread pool overhead
- Simplified error handling
- Better resource management
- Improved scalability

## Testing the Migration

### Step 1: Test Async Redis Manager
```python
import asyncio
from async_redis_manager import AsyncRedisManager

async def test_async_redis():
    redis_manager = AsyncRedisManager()
    
    # Test connection
    connected = await redis_manager.connect()
    assert connected, "Failed to connect to Redis"
    
    # Test basic operations
    room_code = "TEST_ROOM"
    success = await redis_manager.create_room(room_code)
    assert success, "Failed to create room"
    
    exists = await redis_manager.room_exists(room_code)
    assert exists, "Room should exist"
    
    # Cleanup
    await redis_manager.clear_room(room_code)
    await redis_manager.disconnect()
    
    print("All tests passed!")

if __name__ == "__main__":
    asyncio.run(test_async_redis())
```

### Step 2: Test Hybrid Manager
```python
import asyncio
from redis_manager_hybrid import HybridRedisManager

async def test_hybrid_redis():
    redis_manager = HybridRedisManager()
    
    # Test async mode
    await redis_manager.connect_async()
    
    room_code = "TEST_ROOM"
    
    # Test async operations
    success = await redis_manager.create_room_async(room_code)
    assert success, "Failed to create room (async)"
    
    # Test sync operations (should work too)
    exists = redis_manager.room_exists(room_code)
    assert exists, "Room should exist (sync)"
    
    # Cleanup
    await redis_manager.clear_room_async(room_code)
    await redis_manager.disconnect_async()
    
    print("Hybrid tests passed!")

if __name__ == "__main__":
    asyncio.run(test_hybrid_redis())
```

## Troubleshooting

### Common Issues

1. **Connection Errors**
   - Ensure Redis server is running
   - Check Redis configuration (host, port, db)
   - Verify network connectivity

2. **Import Errors**
   - Install aioredis: `pip install aioredis>=2.0.0`
   - Check Python path for new modules

3. **Event Loop Issues**
   - Use `asyncio.run()` for main entry point
   - Ensure all Redis operations are awaited
   - Don't mix sync and async operations incorrectly

4. **Performance Issues**
   - Monitor connection pool size
   - Adjust operation timeouts
   - Check Redis server performance

### Debugging

Enable debug logging:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

Monitor Redis operations:
```python
# Check performance metrics
metrics = redis_manager.get_performance_metrics()
print(f"Operations: {metrics['total_operations']}")
print(f"Error rate: {metrics['error_rate']}")
print(f"Avg latency: {metrics['avg_latency']}")
```

## Rollback Plan

If issues occur, you can quickly rollback:

1. **Using HybridRedisManager**: Simply don't call `connect_async()` - it will use sync operations
2. **Using AsyncRedisManager**: Replace import with original `RedisManager`
3. **Revert server.py**: Use git to revert to previous version

## Next Steps

1. **Phase 1**: Deploy with HybridRedisManager
2. **Phase 2**: Test all functionality with async operations
3. **Phase 3**: Monitor performance improvements
4. **Phase 4**: Switch to pure AsyncRedisManager
5. **Phase 5**: Remove sync fallback code

## Additional Optimizations

After migration, consider these improvements:

1. **Connection Pooling**: Tune pool size based on load
2. **Caching**: Implement Redis-backed caching for frequently accessed data
3. **Monitoring**: Add Redis operation metrics and alerts
4. **Scaling**: Consider Redis clustering for horizontal scaling
