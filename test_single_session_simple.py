#!/usr/bin/env python3
"""
Simple test to verify single-session enforcement
"""

import asyncio
import websockets
import json
import sys
import os

# Add current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def test_connection(connection_name, username, password):
    """Test a single connection"""
    print(f"\n🔗 Testing {connection_name}...")
    
    try:
        async with websockets.connect(
            "ws://localhost:8765",
            ping_interval=60,
            ping_timeout=300,
            close_timeout=300
        ) as ws:
            print(f"✅ {connection_name}: WebSocket connected")
            
            # Try to authenticate
            auth_message = {
                'type': 'auth_login',
                'username': username,
                'password': password
            }
            
            await ws.send(json.dumps(auth_message))
            
            # Wait for response
            response = await asyncio.wait_for(ws.recv(), timeout=5.0)
            response_data = json.loads(response)
            
            if response_data.get('type') == 'auth_response':
                if response_data.get('success'):
                    print(f"✅ {connection_name}: Authentication successful")
                    
                    # Keep connection alive for a bit
                    await asyncio.sleep(2)
                    return True
                else:
                    error_code = response_data.get('error_code')
                    message = response_data.get('message')
                    
                    if error_code == 'ALREADY_CONNECTED':
                        print(f"🚫 {connection_name}: Correctly rejected - {message}")
                        return 'rejected'
                    else:
                        print(f"❌ {connection_name}: Authentication failed - {message}")
                        return False
            else:
                print(f"❌ {connection_name}: Unexpected response - {response_data}")
                return False
                
    except Exception as e:
        print(f"❌ {connection_name}: Error - {e}")
        return False

async def main():
    print("🔍 Single-Session Enforcement Test")
    print("=" * 50)
    
    # Test first connection
    result1 = await test_connection("Connection 1", "kasra", "test")
    
    if result1 == True:
        print("\n⏳ First connection successful, testing second connection...")
        
        # Test second connection (should be rejected)
        result2 = await test_connection("Connection 2", "kasra", "test")
        
        if result2 == 'rejected':
            print("\n🎉 SUCCESS: Single-session enforcement is working correctly!")
            print("   - First connection allowed")
            print("   - Second connection properly rejected")
        else:
            print("\n❌ FAILED: Second connection should have been rejected")
    else:
        print(f"\n❌ FAILED: First connection failed: {result1}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Test interrupted")
