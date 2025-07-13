#!/usr/bin/env python3
"""
Simple test to verify hokm reconnection works
"""

import asyncio
import websockets
import json

SERVER_URI = "ws://localhost:8765"

async def simple_reconnection_test():
    """Simple test for reconnection during hokm phase"""
    
    print("🧪 Simple Reconnection Test")
    
    # Connect one player
    print("1. Connecting player...")
    
    try:
        ws = await websockets.connect(SERVER_URI)
        await ws.send(json.dumps({
            "type": "join",
            "username": "TestPlayer",
            "room_code": "9999"
        }))
        
        response = await ws.recv()
        join_response = json.loads(response)
        
        if join_response.get('type') == 'join_success':
            player_id = join_response.get('player_id')
            username = join_response.get('username')
            print(f"✅ Connected as {username}")
            print(f"   Player ID: {player_id[:8]}...")
            
            # Wait for game state
            msg = await ws.recv()
            game_state = json.loads(msg)
            print(f"📋 Game state: {game_state.get('type')} - {game_state.get('data', {}).get('phase', 'unknown')}")
            
            # Close connection
            await ws.close()
            print("🔌 Disconnected")
            
            # Wait a moment
            await asyncio.sleep(2)
            
            # Reconnect
            print("2. Reconnecting...")
            ws2 = await websockets.connect(SERVER_URI)
            await ws2.send(json.dumps({
                "type": "reconnect",
                "player_id": player_id,
                "room_code": "9999"
            }))
            
            reconnect_response = await ws2.recv()
            reconnect_msg = json.loads(reconnect_response)
            
            print(f"📥 Reconnection: {reconnect_msg.get('type')}")
            
            if reconnect_msg.get('type') == 'reconnect_success':
                print("✅ Reconnection successful!")
                
                # Try to send a test hokm selection (should fail gracefully, not crash)
                await ws2.send(json.dumps({
                    "type": "hokm_selected",
                    "room_code": "9999", 
                    "suit": "hearts"
                }))
                
                test_response = await ws2.recv()
                test_msg = json.loads(test_response)
                
                print(f"📥 Hokm test: {test_msg.get('type')} - {test_msg.get('message', '')}")
                
                if 'Game not found' in test_msg.get('message', ''):
                    print("❌ BUG: Game was deleted during reconnection!")
                    return False
                else:
                    print("✅ Game state preserved during reconnection!")
                    return True
            else:
                print(f"❌ Reconnection failed: {reconnect_msg}")
                return False
                
            await ws2.close()
            
        else:
            print(f"❌ Connection failed: {join_response}")
            return False
            
    except Exception as e:
        print(f"❌ Test error: {e}")
        return False

async def main():
    try:
        success = await simple_reconnection_test()
        if success:
            print("\n✅ Test passed - reconnection fix working!")
        else:
            print("\n❌ Test failed - reconnection still has issues")
        return success
    except Exception as e:
        print(f"Test crashed: {e}")
        return False

if __name__ == "__main__":
    asyncio.run(main())
