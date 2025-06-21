#!/usr/bin/env python3
"""
Emergency game reset utility for when players get "Player not found in room" errors
"""

import asyncio
import websockets
import json
import sys
import os

# Add the project root to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

async def clear_game_room(room_code="9999"):
    """Clear a game room to fix player synchronization issues"""
    try:
        print(f"🧹 Clearing room {room_code}...")
        
        async with websockets.connect("ws://localhost:8765") as ws:
            # Send clear room command
            await ws.send(json.dumps({
                "type": "clear_room",
                "room_code": room_code
            }))
            
            # Wait for confirmation
            response = await asyncio.wait_for(ws.recv(), timeout=3.0)
            data = json.loads(response)
            
            if "cleared" in data.get('message', '').lower():
                print(f"✅ Room {room_code} has been cleared!")
                return True
            else:
                print(f"⚠️ Unexpected response: {data}")
                return False
                
    except Exception as e:
        print(f"❌ Failed to clear room: {e}")
        return False

async def main():
    print("=" * 50)
    print("🚨 HOKM GAME EMERGENCY RESET")
    print("=" * 50)
    print()
    print("This utility fixes 'Player not found in room' errors")
    print("by clearing the game state and allowing fresh connections.")
    print()
    
    room_code = input("Enter room code to clear (default: 9999): ").strip() or "9999"
    
    print(f"\n🔄 Attempting to clear room {room_code}...")
    
    success = await clear_game_room(room_code)
    
    print("\n" + "=" * 50)
    if success:
        print("✅ RESET COMPLETE!")
        print()
        print("🎮 Now all players can rejoin:")
        print("   python -m backend.client")
        print()
        print("The game will start fresh when 4 players connect.")
    else:
        print("❌ RESET FAILED")
        print()
        print("🔧 Manual fix:")
        print("1. Stop the server (Ctrl+C)")
        print("2. Restart: python -m backend.server")
        print("3. All players rejoin: python -m backend.client")
    print("=" * 50)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Reset cancelled.")
    except Exception as e:
        print(f"❌ Fatal error: {str(e)}")
        sys.exit(1)
