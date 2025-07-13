#!/usr/bin/env python3
"""
Quick verification that the Hokm game system is working
"""

import asyncio
import websockets
import json
import sys

async def test_connection():
    """Test that we can connect to the server"""
    try:
        print("🔍 Testing connection to Hokm server...")
        
        async with websockets.connect("ws://localhost:8765") as ws:
            # Send join message
            await ws.send(json.dumps({
                "type": "join",
                "username": "TestPlayer",
                "room_code": "TEST"
            }))
            
            # Get response
            response = await asyncio.wait_for(ws.recv(), timeout=3.0)
            data = json.loads(response)
            
            if data.get('type') == 'join_success':
                print("✅ SUCCESS: Server is running and accepting connections!")
                print(f"   Player ID: {data.get('player_id', 'N/A')[:8]}...")
                print(f"   Username: {data.get('username', 'N/A')}")
                return True
            else:
                print(f"❌ FAILED: Unexpected response: {data}")
                return False
                
    except Exception as e:
        print(f"❌ FAILED: Connection error: {e}")
        return False

async def main():
    print("=" * 50)
    print("🎴 HOKM GAME SYSTEM VERIFICATION")
    print("=" * 50)
    
    success = await test_connection()
    
    print("\n" + "=" * 50)
    if success:
        print("🎉 SYSTEM STATUS: READY TO PLAY!")
        print()
        print("📋 TO PLAY THE GAME:")
        print("1. Keep the server running (it's already started)")
        print("2. Open 4 terminals and run: python -m backend.client")
        print("3. All players will auto-join room 9999")
        print("4. Game starts when 4 players connect!")
        print()
        print("🧪 TO RUN TESTS:")
        print("   python test_complete_flow.py")
        print("   python test_error_handling.py")
    else:
        print("❌ SYSTEM NOT READY - Please check server status")
    print("=" * 50)

if __name__ == "__main__":
    asyncio.run(main())
