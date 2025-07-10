#!/usr/bin/env python3
"""
Debug test for reconnection handling
"""
import asyncio
import websockets
import json
import sys
import os
import time

# Add current directory to Python path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.client_auth_manager import ClientAuthManager

SERVER_URI = "ws://localhost:8765"

async def test_reconnect():
    """Test reconnection with debug output"""
    
    # Get session file path
    session_file = ".player_session_324dd405"
    
    # Read session player ID
    if os.path.exists(session_file):
        with open(session_file, 'r') as f:
            player_id = f.read().strip()
        print(f"🔍 Found session file with player ID: {player_id}")
    else:
        print("❌ No session file found")
        return
    
    try:
        async with websockets.connect(SERVER_URI) as ws:
            print(f"🔗 Connected to server")
            
            # First authenticate
            auth_manager = ClientAuthManager()
            authenticated = await auth_manager.authenticate_with_server(ws)
            if not authenticated:
                print("❌ Authentication failed")
                return
                
            player_info = auth_manager.get_player_info()
            auth_player_id = player_info['player_id']
            username = player_info['username']
            
            print(f"✅ Authenticated as {username} (ID: {auth_player_id})")
            
            # Check if session player ID matches authenticated player ID
            if player_id != auth_player_id:
                print(f"⚠️  Session player ID mismatch!")
                print(f"   Session: {player_id}")
                print(f"   Authenticated: {auth_player_id}")
                return
            
            print(f"🔄 Attempting to reconnect...")
            
            # Send reconnection request
            await ws.send(json.dumps({
                "type": "reconnect",
                "player_id": player_id,
                "room_code": "9999"
            }))
            
            print("📤 Reconnection request sent, waiting for response...")
            
            # Wait for response with timeout
            try:
                response = await asyncio.wait_for(ws.recv(), timeout=10.0)
                print(f"📥 Received response: {response}")
                
                data = json.loads(response)
                msg_type = data.get('type')
                
                if msg_type == 'reconnect_success':
                    print("✅ Reconnection successful!")
                    print(f"📋 Response data: {json.dumps(data, indent=2)}")
                elif msg_type == 'error':
                    print(f"❌ Reconnection failed: {data.get('message')}")
                else:
                    print(f"🤔 Unexpected response type: {msg_type}")
                    
            except asyncio.TimeoutError:
                print("⏰ Timeout waiting for server response")
                print("   The server might not be responding to reconnection requests")
                
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_reconnect())
