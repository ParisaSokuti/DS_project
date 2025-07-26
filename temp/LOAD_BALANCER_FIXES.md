# Load Balancer Race Condition Fixes

## Problem Analysis
The error "cannot call recv while another coroutine is already waiting for the next message" was occurring because:

1. **Race Condition**: Multiple coroutines were trying to read from the same WebSocket connection simultaneously
2. **Async Iterator Issue**: Using `async for message in websocket` can cause conflicts when multiple tasks access the same connection
3. **Reconnection Loops**: Multiple failover attempts were being triggered simultaneously
4. **No Connection State Tracking**: No mechanism to prevent duplicate connection handling

## Fixes Applied

### 1. Fixed WebSocket Message Handling
**Before:**
```python
async def client_to_server():
    async for message in client_websocket:  # Race condition prone
        await server_websocket.send(message)
```

**After:**
```python
async def client_to_server():
    try:
        while True:
            try:
                message = await client_websocket.recv()  # Explicit recv()
                await server_websocket.send(message)
            except websockets.exceptions.ConnectionClosed:
                break
    except Exception as e:
        logger.warning(f"⚠️ Proxy task failed: {e}")
```

### 2. Added Connection State Tracking
```python
self.connection_states = {}  # websocket -> state (connecting, connected, disconnected)
```

This prevents multiple handlers from processing the same connection.

### 3. Improved Task Management
```python
# Run both directions concurrently with proper cancellation
client_task = asyncio.create_task(client_to_server())
server_task = asyncio.create_task(server_to_client())

try:
    # Wait for either task to complete (indicating connection closed)
    done, pending = await asyncio.wait(
        [client_task, server_task],
        return_when=asyncio.FIRST_COMPLETED
    )
    
    # Cancel remaining tasks
    for task in pending:
        task.cancel()
```

### 4. Added Rate Limiting for Reconnections
```python
self.reconnect_attempts = {}  # websocket -> (count, last_attempt_time)

# Check reconnection rate limiting
current_time = time.time()
reconnect_info = self.reconnect_attempts.get(client_websocket, (0, 0))
attempts, last_attempt = reconnect_info

# Reset counter if enough time has passed
if current_time - last_attempt > 60:  # Reset after 1 minute
    attempts = 0

# Only try failover if we haven't exceeded limits
if (attempts < 3 and 
    current_time - last_attempt > 5):  # Min 5 seconds between attempts
```

### 5. Enhanced Cleanup
```python
finally:
    # Clean up connection tracking
    if client_websocket in self.active_connections:
        server_name = self.active_connections[client_websocket]
        del self.active_connections[client_websocket]
        if server_name in self.servers:
            self.servers[server_name].connection_count = max(0, self.servers[server_name].connection_count - 1)
    
    # Clean up connection state and reconnection tracking
    if client_websocket in self.connection_states:
        del self.connection_states[client_websocket]
    if client_websocket in self.reconnect_attempts:
        del self.reconnect_attempts[client_websocket]
```

## Testing the Fixes

Run the test script to verify the fixes:
```bash
python test_load_balancer_fix.py
```

## Expected Behavior After Fixes

1. **No More Race Conditions**: Each WebSocket connection is handled by exactly one coroutine
2. **Controlled Reconnections**: Maximum 3 reconnection attempts with 5-second intervals
3. **Clean Failover**: When primary server fails, clients are smoothly transferred to secondary
4. **Proper Cleanup**: All connection tracking is cleaned up when connections close
5. **No Duplicate Handling**: Connection state tracking prevents duplicate processing

## Demonstration Steps

1. **Start Infrastructure:**
   ```bash
   # Terminal 1: Load Balancer
   python backend/load_balancer.py
   
   # Terminal 2: Primary Server
   python backend/server.py --port 8765 --instance-name primary
   
   # Terminal 3: Secondary Server
   python backend/server.py --port 8766 --instance-name secondary
   ```

2. **Start Game Clients:**
   ```bash
   # Terminals 4-7: Game clients
   python backend/client.py
   ```

3. **Test Failover:**
   - Let all 4 clients connect and start playing
   - Kill primary server (Ctrl+C in Terminal 2)
   - Observe smooth transition to secondary server
   - No race condition errors should appear in load balancer logs

## Key Improvements

- ✅ Eliminated race conditions in WebSocket message handling
- ✅ Added connection state tracking to prevent duplicate handling
- ✅ Implemented rate limiting for reconnection attempts
- ✅ Improved task cancellation and cleanup
- ✅ Enhanced error handling and logging
- ✅ Maintains game state during server transitions
