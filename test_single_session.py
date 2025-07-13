#!/usr/bin/env python3
"""
Test script to verify single-session enforcement
This script simulates a second client trying to connect as the same user
"""

import asyncio
import websockets
import json
import sys
import os

# Add current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def test_duplicate_connection():
    """Test that a second connection with the same user is rejected"""
    print("🧪 Testing duplicate connection prevention...")
    
    try:
        # Connect to server
        async with websockets.connect(
            "ws://localhost:8765",
            ping_interval=60,
            ping_timeout=300,
            close_timeout=300,
            max_size=1024*1024,
            max_queue=100
        ) as ws:
            print("✅ WebSocket connection established")
            
            # Try to authenticate as kasra (who should already be connected)
            auth_message = {
                'type': 'auth_login',
                'username': 'kasra',
                'password': 'test'  # Assuming this is the password
            }
            
            print("🔐 Attempting to login as kasra (should be already connected)...")
            await ws.send(json.dumps(auth_message))
            
            # Wait for response
            response = await asyncio.wait_for(ws.recv(), timeout=10.0)
            response_data = json.loads(response)
            
            if response_data.get('type') == 'auth_response':
                if response_data.get('success'):
                    print("❌ ERROR: Second connection was allowed! This should not happen!")
                    print(f"   Response: {response_data}")
                    return False
                else:
                    error_code = response_data.get('error_code')
                    message = response_data.get('message')
                    
                    if error_code == 'ALREADY_CONNECTED':
                        print("✅ SUCCESS: Second connection was properly rejected!")
                        print(f"   Message: {message}")
                        return True
                    else:
                        print(f"⚠️  Connection rejected for different reason: {message}")
                        return False
            else:
                print(f"❌ Unexpected response type: {response_data}")
                return False
                
    except asyncio.TimeoutError:
        print("❌ Timeout waiting for authentication response")
        return False
    except Exception as e:
        print(f"❌ Error during test: {e}")
        return False

async def main():
    print("🔍 Single-Session Enforcement Test")
    print("=" * 50)
    
    success = await test_duplicate_connection()
    
    if success:
        print("\n🎉 Test PASSED! Single-session enforcement is working correctly.")
    else:
        print("\n❌ Test FAILED! Single-session enforcement needs debugging.")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
