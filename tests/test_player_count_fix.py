#!/usr/bin/env python3
"""
Quick test to verify that player count logging is now working correctly
"""

import asyncio
import websockets
import json
import time

async def test_player_count():
    """Test that player count is properly tracked and logged"""
    print("🧪 Testing Player Count Fix...")
    
    connections = []
    
    try:
        # Connect 4 players sequentially and check logs
        for i in range(4):
            print(f"\n📡 Connecting Player {i+1}...")
            
            try:
                websocket = await websockets.connect("ws://localhost:8765")
                connections.append(websocket)
                
                # Send join message
                join_message = {
                    "type": "join",
                    "room_code": "9999"
                }
                
                await websocket.send(json.dumps(join_message))
                
                # Wait for response
                response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                data = json.loads(response)
                
                print(f"✅ Player {i+1} joined successfully: {data.get('data', {}).get('username', 'Unknown')}")
                
                # Small delay between connections
                await asyncio.sleep(0.5)
                
            except Exception as e:
                print(f"❌ Player {i+1} failed to connect: {str(e)}")
                break
        
        print(f"\n📊 Final Status: {len(connections)} players connected")
        
        # Wait a moment to see if game starts
        print("⏱️  Waiting for game to start...")
        await asyncio.sleep(3)
        
    except Exception as e:
        print(f"❌ Test failed: {str(e)}")
    
    finally:
        # Close all connections
        print("\n🔌 Closing connections...")
        for i, conn in enumerate(connections):
            try:
                await conn.close()
                print(f"✅ Player {i+1} disconnected")
            except:
                pass

if __name__ == "__main__":
    print("🎮 Player Count Fix Test")
    print("=" * 50)
    print("This test will connect 4 players and check if the")
    print("server logs show the correct player count progression:")
    print("Player 1/4 → Player 2/4 → Player 3/4 → Player 4/4")
    print("\nMake sure your server is running first!")
    print("=" * 50)
    
    asyncio.run(test_player_count())
