#!/usr/bin/env python3

import asyncio
import websockets
import json
import time

async def test_with_valid_token():
    """Test with a valid token that we know works"""
    
    # Use nima's token that we know works
    token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJwbGF5ZXJfaWQiOiI3ZTFiMWVmOC1kNmMzLTQ1MzAtOWU0Mi1kMjEzYWFlN2ExMmQiLCJ1c2VybmFtZSI6Im5pbWEiLCJleHAiOjE3NTIyNjE3NDMsImlhdCI6MTc1MjE3NTM0M30.O_w5FbPJ9QEZG1OSiX6pS3uMfoTd-XANjOYfdG4e-0A"
    
    room_code = "9999"
    
    print("🧪 Testing with valid token...")
    print(f"📦 Room code: {room_code}")
    print(f"👤 Using nima's token")
    
    try:
        # Connect to server
        uri = "ws://localhost:8765"
        websocket = await websockets.connect(uri)
        
        # Authenticate with token
        auth_message = {
            "type": "auth_token",
            "token": token
        }
        
        await websocket.send(json.dumps(auth_message))
        print("🔐 Sent authentication...")
        
        # Wait for auth response
        try:
            auth_response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
            print(f"   Auth response: {auth_response}")
            
            auth_data = json.loads(auth_response)
            if not auth_data.get('success', False):
                print(f"   ❌ Authentication failed: {auth_data.get('message', 'Unknown error')}")
                return
                
        except asyncio.TimeoutError:
            print(f"   ⚠️  Auth timeout")
            return
        
        # Join room
        join_message = {
            "type": "join",
            "room_code": room_code
        }
        
        await websocket.send(json.dumps(join_message))
        print("🚪 Sent join request...")
        
        # Wait for join response
        try:
            join_response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
            print(f"   Join response: {join_response}")
        except asyncio.TimeoutError:
            print(f"   ⚠️  Join timeout")
        
        # Wait for any additional messages
        print("⏳ Waiting for additional messages...")
        for i in range(5):
            try:
                message = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                print(f"   Message {i+1}: {message}")
            except asyncio.TimeoutError:
                break
        
        # Close connection
        await websocket.close()
        print("✅ Connection closed")
        
    except Exception as e:
        print(f"❌ Error during test: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_with_valid_token())
