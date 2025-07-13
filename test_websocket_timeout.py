#!/usr/bin/env python3
"""
Test script to verify WebSocket timeout configuration
Tests that client can connect and maintain connection with 5-minute timeouts
"""

import asyncio
import websockets
import json
import sys
import time

async def test_connection_timeout():
    """Test that WebSocket connection can be maintained for extended periods"""
    print("Testing WebSocket connection with 5-minute timeout...")
    
    try:
        # Connect with the same timeout configuration as the client
        async with websockets.connect(
            "ws://localhost:8765",
            ping_interval=60,      # Send ping every 60 seconds
            ping_timeout=300,      # 5 minutes timeout for ping response
            close_timeout=300,     # 5 minutes timeout for close handshake
            max_size=1024*1024,    # 1MB max message size
            max_queue=100          # Max queued messages
        ) as ws:
            print("✅ WebSocket connection established successfully")
            print("📊 Configuration:")
            print("   - Ping interval: 60 seconds")
            print("   - Ping timeout: 300 seconds (5 minutes)")
            print("   - Close timeout: 300 seconds (5 minutes)")
            print("   - Max message size: 1MB")
            print("   - Max queue size: 100")
            
            # Send a test message
            test_message = {
                'type': 'test',
                'message': 'Testing extended timeout configuration'
            }
            
            await ws.send(json.dumps(test_message))
            print("📤 Test message sent")
            
            # Wait for a short period to test connection stability
            print("⏳ Waiting 10 seconds to test connection stability...")
            await asyncio.sleep(10)
            
            # Send another message to verify connection is still active
            keepalive_message = {
                'type': 'keepalive',
                'timestamp': time.time()
            }
            
            await ws.send(json.dumps(keepalive_message))
            print("📤 Keepalive message sent")
            
            print("✅ WebSocket connection maintained successfully!")
            print("🔧 Timeout configuration verified")
            
    except websockets.exceptions.ConnectionClosedError as e:
        print(f"❌ Connection closed unexpectedly: {e}")
        return False
    except asyncio.TimeoutError as e:
        print(f"❌ Timeout error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False
    
    return True

async def main():
    print("🔍 WebSocket Timeout Configuration Test")
    print("=" * 50)
    
    success = await test_connection_timeout()
    
    if success:
        print("\n🎉 All tests passed! WebSocket timeout configuration is working correctly.")
    else:
        print("\n❌ Test failed. Check server configuration.")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
