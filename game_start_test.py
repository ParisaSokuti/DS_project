#!/usr/bin/env python3
"""
Game Start Trigger Test

This script tests what happens when we have 4 players and tries to trigger the game start.
"""

import asyncio
import websockets
import json
import sys
import os
import time

# Add backend directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

try:
    from client_auth_manager import ClientAuthManager
except ImportError as e:
    print(f"❌ Import error: {e}")
    sys.exit(1)

SERVER_URI = "ws://192.168.1.26:8765"

async def trigger_game_start():
    """Connect as a player and try to trigger game start"""
    print("🎮 Testing Game Start Trigger")
    print("=" * 40)
    
    try:
        # Connect to server
        print("🔗 Connecting to server...")
        ws = await websockets.connect(SERVER_URI)
        
        # Authenticate
        auth_manager = ClientAuthManager()
        authenticated = await auth_manager.authenticate_with_server(ws)
        if not authenticated:
            print("❌ Authentication failed")
            return
        
        player_info = auth_manager.get_player_info()
        username = player_info['username']
        player_id = player_info['player_id']
        print(f"✅ Authenticated as {username}")
        
        # Join room
        await ws.send(json.dumps({
            "type": "join",
            "room_code": "9999"
        }))
        print("📤 Sent join request")
        
        # Listen for responses
        for i in range(10):  # Listen for up to 10 messages
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                data = json.loads(msg)
                msg_type = data.get('type')
                
                print(f"📥 {i+1}. Received: {msg_type}")
                
                if msg_type == 'join_success':
                    print("✅ Joined successfully")
                    
                elif msg_type == 'room_status':
                    players = data.get('usernames', [])
                    total_players = data.get('total_players', 0)
                    print(f"👥 Room status: {total_players}/4 players")
                    print(f"   Players: {', '.join(players)}")
                    
                    if total_players >= 4:
                        print("🚀 Room is full! Checking for game start...")
                        
                elif msg_type == 'team_assignment':
                    print("🎯 Game started! Team assignment received")
                    teams = data.get('teams', {})
                    hakem = data.get('hakem')
                    print(f"   Teams: {teams}")
                    print(f"   Hakem: {hakem}")
                    break
                    
                elif msg_type == 'waiting_for_players':
                    current_players = data.get('current_players', 0)
                    required_players = data.get('required_players', 4)
                    message = data.get('message', '')
                    print(f"⏳ {message}")
                    print(f"   Players: {current_players}/{required_players}")
                    
                elif msg_type == 'error':
                    error_msg = data.get('message', '')
                    print(f"❌ Error: {error_msg}")
                    
                else:
                    print(f"📋 Other message: {data}")
                    
            except asyncio.TimeoutError:
                print(f"⏰ Timeout waiting for message {i+1}")
                break
        
        # Try to trigger game start manually if room is full
        print("\n🔧 Trying to trigger game start manually...")
        await ws.send(json.dumps({
            "type": "start_game",
            "room_code": "9999"
        }))
        
        # Wait for response
        try:
            msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
            data = json.loads(msg)
            print(f"📥 Response to start_game: {data}")
        except asyncio.TimeoutError:
            print("⏰ No response to start_game trigger")
        
        await ws.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(trigger_game_start())
    except KeyboardInterrupt:
        print("\n❌ Interrupted")
    except Exception as e:
        print(f"❌ Failed: {e}")
