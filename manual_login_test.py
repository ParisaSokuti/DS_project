#!/usr/bin/env python3
"""
Manual test for single session - attempt login only
"""

import asyncio
import websockets
import json

async def attempt_login():
    try:
        print("🔗 Attempting to connect...")
        async with websockets.connect("ws://localhost:8765") as ws:
            print("✅ Connected to server")
            
            # Attempt login
            auth_message = {
                'type': 'auth_login',
                'username': 'kasra',
                'password': 'test'
            }
            
            print("🔐 Sending login request...")
            await ws.send(json.dumps(auth_message))
            
            # Wait for response
            print("⏳ Waiting for response...")
            response = await asyncio.wait_for(ws.recv(), timeout=10.0)
            response_data = json.loads(response)
            
            print(f"📨 Received response: {response_data}")
            
            if response_data.get('type') == 'auth_response':
                if response_data.get('success'):
                    print("✅ Login successful!")
                    print("⏳ Keeping connection alive for 30 seconds...")
                    await asyncio.sleep(30)
                else:
                    error_code = response_data.get('error_code')
                    message = response_data.get('message')
                    
                    if error_code == 'ALREADY_CONNECTED':
                        print(f"🚫 Connection rejected: {message}")
                    else:
                        print(f"❌ Login failed: {message}")
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(attempt_login())
