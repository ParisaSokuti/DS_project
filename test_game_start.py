#!/usr/bin/env python3
"""
Test script to simulate 4 players joining a game to test game start
"""

import asyncio
import websockets
import json
import time

async def create_player(username, password):
    """Create a player and join the game"""
    try:
        print(f"[{username}] Connecting to server...")
        async with websockets.connect("ws://localhost:8765") as websocket:
            # Register
            register_msg = {
                "type": "auth_register",
                "username": username,
                "password": password
            }
            await websocket.send(json.dumps(register_msg))
            response = await websocket.recv()
            auth_data = json.loads(response)
            
            if not auth_data.get("success", False):
                print(f"[{username}] Authentication failed: {auth_data}")
                return False
            
            print(f"[{username}] Authenticated successfully!")
            
            # Join room
            join_msg = {
                "type": "join",
                "room_code": "9999"
            }
            await websocket.send(json.dumps(join_msg))
            response = await websocket.recv()
            join_data = json.loads(response)
            
            if join_data.get("type") != "join_success":
                print(f"[{username}] Failed to join room: {join_data}")
                return False
            
            print(f"[{username}] Joined room successfully!")
            
            # Wait for game to start or other messages
            timeout = 10  # 10 second timeout
            start_time = time.time()
            
            while time.time() - start_time < timeout:
                try:
                    response = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                    message = json.loads(response)
                    msg_type = message.get("type")
                    
                    print(f"[{username}] Received: {msg_type}")
                    
                    if msg_type == "game_start":
                        print(f"[{username}] 🎮 Game started!")
                        return True
                    elif msg_type == "team_assignment":
                        print(f"[{username}] 👥 Team assigned!")
                        return True
                    elif msg_type == "initial_deal":
                        print(f"[{username}] 🎴 Cards dealt!")
                        return True
                        
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    print(f"[{username}] Error receiving message: {e}")
                    break
            
            print(f"[{username}] Timeout waiting for game start")
            return False
            
    except Exception as e:
        print(f"[{username}] Connection error: {e}")
        return False

async def test_game_start():
    """Test game start with 4 players"""
    print("=== Testing Game Start with 4 Players ===")
    
    # Use timestamp to ensure unique usernames
    timestamp = str(int(time.time()))
    players = [f"player{i+1}_{timestamp}" for i in range(4)]
    
    # Create tasks for all players
    tasks = []
    for i, username in enumerate(players):
        password = f"password{i+1}"  # Use longer passwords
        task = create_player(username, password)
        tasks.append(task)
        
        # Small delay between connections to avoid race conditions
        await asyncio.sleep(0.5)
    
    # Wait for all players to complete
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    print("\n=== Results ===")
    for i, result in enumerate(results):
        if isinstance(result, bool):
            status = "✅ Success" if result else "❌ Failed"
            print(f"Player {players[i]}: {status}")
        else:
            print(f"Player {players[i]}: ❌ Exception: {result}")
    
    success_count = sum(1 for r in results if r is True)
    print(f"\n{success_count}/{len(players)} players successfully joined and started game")
    
    return success_count == len(players)

if __name__ == "__main__":
    success = asyncio.run(test_game_start())
    if success:
        print("\n🎉 Game start test passed!")
    else:
        print("\n❌ Game start test failed!")
