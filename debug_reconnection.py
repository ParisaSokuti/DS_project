#!/usr/bin/env python3
"""
Debug script to trace reconnection message flow
"""

def analyze_reconnection_debug_logs():
    """Analyze the debug logs provided by the user"""
    
    print("=== Analyzing Reconnection Debug Output ===\n")
    
    debug_lines = [
        "[DEBUG] attempt_reconnect: Session retrieved: True",
        "[DEBUG] attempt_reconnect: Checking required fields...",
        "[DEBUG] attempt_reconnect: Checking if room 9999 exists...",
        "[DEBUG] room_exists: Checking if room 9999 exists...",
        "[DEBUG] room_exists: Room 9999 - state:True, players:True, exists:True",
        "[DEBUG] attempt_reconnect: Room exists, updating session...",
        "[DEBUG] attempt_reconnect: Saving updated session...",
        "[DEBUG] attempt_reconnect: Session saved successfully",
        "INFO:redis_manager_resilient:Player 7e1b1ef8... successfully reconnected to room 9999",
        "[DEBUG] Session validation result: True",
        "[DEBUG] Session data: room_code=9999, username=nima",
        "[DEBUG] Step 2: Getting room players...",
        "[DEBUG] get_room_players: Getting players for room 9999...",
        "[DEBUG] get_room_players: Found 4 valid players in room 9999",
        "[DEBUG] Got 4 players from room",
        "[DEBUG] Reconnection validation for player_id: 7e1b1ef8-d6c3-4530-9e42-d213aae7a12d",
        "[DEBUG] Room 9999 has 4 players:",
        "[DEBUG]   Player 1: 7e1b1ef8... (nima) - active",
        "[DEBUG] Player nima reconnection allowed - live_connection: False, status: active"
    ]
    
    print("1. Redis Manager Level:")
    print("   ✅ Session retrieved successfully")
    print("   ✅ Room existence validated")
    print("   ✅ Session updated and saved")
    print("   ✅ Player successfully reconnected (Redis level)")
    print()
    
    print("2. Network Manager Level:")
    print("   ✅ Session validation passed")
    print("   ✅ Room and player data retrieved")
    print("   ✅ Player found in room with active status")
    print("   ✅ Reconnection allowed (no live connection conflict)")
    print()
    
    print("3. Missing from Debug Output:")
    print("   ❌ No 'register_connection' debug message")
    print("   ❌ No 'get_game_state' debug message")
    print("   ❌ No 'reconnect_success' message send debug")
    print("   ❌ No client-side message received debug")
    print()
    
    print("=== Suspected Issues ===")
    print()
    print("1. 🔍 MOST LIKELY: Network manager stops after validation")
    print("   - The flow stops at 'reconnection allowed' message")
    print("   - Missing subsequent steps: register_connection, get_game_state, send_message")
    print()
    print("2. 🔍 POSSIBLE: Game state retrieval fails")
    print("   - get_game_state() might be failing silently")
    print("   - This would prevent reconnect_success message from being sent")
    print()
    print("3. 🔍 POSSIBLE: WebSocket connection issue")
    print("   - Connection might be closed before message is sent")
    print("   - Client timeout (10s) might not be enough")
    print()
    
    print("=== Debugging Steps ===")
    print()
    print("1. Add debug prints in network.py after line ~465:")
    print("   print(f'[DEBUG] Step 3: Registering connection...')")
    print("   print(f'[DEBUG] Step 4: Getting game state...')")
    print("   print(f'[DEBUG] Step 5: Sending reconnect_success...')")
    print()
    print("2. Check if game_state retrieval is working:")
    print("   game_state = redis_manager.get_game_state(room_code)")
    print("   print(f'[DEBUG] Game state keys: {list(game_state.keys()) if game_state else None}')")
    print()
    print("3. Add exception handling around message sending:")
    print("   try:")
    print("       await self.send_message(websocket, 'reconnect_success', restored_state)")
    print("       print(f'[DEBUG] reconnect_success message sent')")
    print("   except Exception as e:")
    print("       print(f'[ERROR] Failed to send reconnect_success: {e}')")
    print()
    print("4. Check client timeout:")
    print("   - Current timeout is 10 seconds")
    print("   - Consider increasing to 30 seconds for debugging")

def suggest_fixes():
    """Suggest immediate fixes for the reconnection issue"""
    print("\n=== Immediate Fixes to Try ===\n")
    
    print("1. 🔧 Add debug prints to network.py:")
    print("   Add after line ~465 in handle_player_reconnected:")
    print("   ```python")
    print("   print(f'[DEBUG] Step 3: Registering connection for {username}...')")
    print("   self.register_connection(websocket, player_id, room_code, username)")
    print("   print(f'[DEBUG] Connection registered successfully')")
    print("   ```")
    print()
    
    print("2. 🔧 Add debug around game state:")
    print("   ```python") 
    print("   print(f'[DEBUG] Step 4: Getting game state for room {room_code}...')")
    print("   game_state = redis_manager.get_game_state(room_code)")
    print("   print(f'[DEBUG] Game state retrieved: {bool(game_state)}')")
    print("   if game_state:")
    print("       print(f'[DEBUG] Game state has {len(game_state)} keys')")
    print("   ```")
    print()
    
    print("3. 🔧 Add debug around message sending:")
    print("   ```python")
    print("   print(f'[DEBUG] Step 5: Sending reconnect_success to {username}...')")
    print("   success = await self.send_message(websocket, 'reconnect_success', restored_state)")
    print("   print(f'[DEBUG] Message send result: {success}')")
    print("   ```")
    print()
    
    print("4. 🔧 Increase client timeout:")
    print("   In client.py, change:")
    print("   ```python")
    print("   response = await asyncio.wait_for(ws.recv(), timeout=30.0)  # Increased from 10.0")
    print("   ```")
    print()
    
    print("5. 🔧 Add exception handling in network.py:")
    print("   Wrap the entire reconnection logic in try/except to catch any silent failures")

if __name__ == "__main__":
    analyze_reconnection_debug_logs()
    suggest_fixes()
