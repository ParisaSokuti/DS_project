#!/usr/bin/env python3
"""
Test reconnection after disconnect during gameplay.
This simulates the exact issue where arvin disconnected and could not reconnect.
"""

import asyncio
import json
import websockets
import sys
import os

async def test_arvin_reconnection():
    """Test arvin's reconnection issue"""
    
    print("🧪 Testing Parisa1's Reconnection Issue")
    print("=" * 50)
    
    # Try to connect as arvin
    try:
        print("🔌 Connecting as parisa1...")
        ws = await websockets.connect("ws://localhost:8765")
        
        # Authenticate using the proper auth_login format
        auth_message = {
            "type": "auth_login",
            "username": "parisa1",
            "password": "testpass"
        }
        
        print("🔐 Sending authentication...")
        await ws.send(json.dumps(auth_message))
        
        # Wait for auth response
        response = await ws.recv()
        auth_data = json.loads(response)
        
        print(f"📨 Auth response: {auth_data}")
        
        if auth_data.get("type") == "auth_response":
            if auth_data.get("success"):
                player_info = auth_data.get("player_info", {})
                player_id = player_info.get("player_id")
                username = player_info.get("username")
                
                print(f"✅ Authentication successful!")
                print(f"   Player: {username}")
                print(f"   Player ID: {player_id}")
                
                # Save player ID for reconnection test
                session_file = f"test_session_{username}"
                with open(session_file, 'w') as f:
                    f.write(player_id)
                print(f"💾 Saved session to {session_file}")
                
                # Try to join room 9999
                print("🏠 Joining room 9999...")
                join_message = {
                    "type": "join",
                    "room_code": "9999"
                }
                
                await ws.send(json.dumps(join_message))
                
                # Wait for join response
                response = await ws.recv()
                join_data = json.loads(response)
                
                print(f"📨 Join response: {join_data}")
                
                if join_data.get("type") == "join_success":
                    print(f"✅ Successfully joined room 9999")
                    
                    # Simulate disconnect
                    print(f"🔌 Simulating disconnect...")
                    await ws.close()
                    
                    # Wait a moment
                    await asyncio.sleep(2)
                    
                    # Test reconnection
                    print(f"🔄 Testing reconnection...")
                    
                    # Reconnect
                    ws2 = await websockets.connect("ws://localhost:8765")
                    
                    # Re-authenticate
                    print("🔐 Re-authenticating...")
                    await ws2.send(json.dumps(auth_message))
                    
                    auth_response2 = await ws2.recv()
                    auth_data2 = json.loads(auth_response2)
                    
                    if auth_data2.get("success"):
                        print("✅ Re-authentication successful")
                        
                        # Try to reconnect to game
                        print("🔄 Attempting game reconnection...")
                        
                        reconnect_message = {
                            "type": "reconnect",
                            "player_id": player_id,
                            "room_code": "9999"
                        }
                        
                        await ws2.send(json.dumps(reconnect_message))
                        
                        # Wait for reconnect response
                        try:
                            reconnect_response = await asyncio.wait_for(ws2.recv(), timeout=10)
                            reconnect_data = json.loads(reconnect_response)
                            
                            print(f"📨 Reconnect response: {reconnect_data}")
                            
                            if reconnect_data.get("type") == "reconnect_success":
                                print("✅ RECONNECTION SUCCESSFUL!")
                                game_state = reconnect_data.get("game_state", {})
                                print(f"📋 Restored game state: {game_state}")
                            elif reconnect_data.get("type") == "error":
                                print(f"❌ Reconnection failed: {reconnect_data.get('message')}")
                            else:
                                print(f"❓ Unexpected response: {reconnect_data}")
                                
                        except asyncio.TimeoutError:
                            print("❌ Reconnection timeout - no response from server")
                        except Exception as e:
                            print(f"❌ Reconnection error: {e}")
                    else:
                        print(f"❌ Re-authentication failed: {auth_data2.get('message')}")
                    
                    # Clean up
                    try:
                        await ws2.close()
                        os.remove(session_file)
                    except:
                        pass
                        
                else:
                    print(f"❌ Failed to join room: {join_data}")
                    
            else:
                print(f"❌ Authentication failed: {auth_data.get('message')}")
        else:
            print(f"❌ Unexpected auth response: {auth_data}")
            
    except Exception as e:
        print(f"❌ Test error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_arvin_reconnection())
