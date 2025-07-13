#!/usr/bin/env python3
"""
Quick Debug Test for Hokm Server

A simplified test to quickly identify connection and basic functionality issues.
Run this first if the main test is failing.

Usage: python test_debug.py
"""

import asyncio
import websockets
import json
import time

async def test_server_connection():
    """Test basic server connection"""
    print("🔗 Testing server connection...")
    
    try:
        websocket = await websockets.connect("ws://localhost:8765")
        print("✅ Connected to server successfully")
        
        # Test basic join
        join_message = {
            'type': 'join',
            'room_code': '9999'
        }
        
        await websocket.send(json.dumps(join_message))
        print(f"📤 Sent: {join_message}")
        
        # Wait for response
        response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
        response_data = json.loads(response)
        print(f"📥 Received: {response_data}")
        
        if response_data.get('type') == 'join_success':
            print("✅ Basic join functionality working")
        else:
            print(f"⚠️  Unexpected response: {response_data}")
            
        await websocket.close()
        return True
        
    except websockets.ConnectionRefusedError:
        print("❌ Cannot connect to server - is it running on localhost:8765?")
        return False
    except asyncio.TimeoutError:
        print("❌ Server connected but no response - check server logs")
        return False
    except Exception as e:
        print(f"❌ Connection test failed: {e}")
        return False

async def test_multiple_clients():
    """Test multiple client connections"""
    print("\n👥 Testing multiple client connections...")
    
    clients = []
    try:
        # Connect 4 clients
        for i in range(4):
            ws = await websockets.connect("ws://localhost:8765")
            clients.append(ws)
            print(f"✅ Client {i+1} connected")
            
        # All join the same room
        for i, ws in enumerate(clients):
            join_msg = {'type': 'join', 'room_code': '9999'}
            await ws.send(json.dumps(join_msg))
            
            # Quick response check
            try:
                response = await asyncio.wait_for(ws.recv(), timeout=3.0)
                data = json.loads(response)
                print(f"📥 Client {i+1}: {data.get('type', 'unknown')}")
            except asyncio.TimeoutError:
                print(f"⚠️  Client {i+1}: No response")
                
        print("✅ Multiple client test completed")
        return True
        
    except Exception as e:
        print(f"❌ Multiple client test failed: {e}")
        return False
    finally:
        # Cleanup
        for ws in clients:
            try:
                await ws.close()
            except:
                pass

async def test_redis_connection():
    """Test if Redis is accessible"""
    print("\n🗄️  Testing Redis connection...")
    
    try:
        import redis
        r = redis.Redis(host='localhost', port=6379, decode_responses=True)
        r.ping()
        print("✅ Redis connection successful")
        
        # Test basic set/get
        test_key = "hokm_test_key"
        r.set(test_key, "test_value", ex=60)
        value = r.get(test_key)
        
        if value == "test_value":
            print("✅ Redis read/write working")
            r.delete(test_key)
            return True
        else:
            print("⚠️  Redis read/write issue")
            return False
            
    except ImportError:
        print("⚠️  Redis module not installed (pip install redis)")
        return False
    except Exception as e:
        print(f"❌ Redis connection failed: {e}")
        print("   Make sure Redis server is running")
        return False

async def main():
    """Run debug tests"""
    print("🔍 HOKM SERVER DEBUG TEST")
    print("=" * 40)
    
    results = []
    
    # Test Redis first
    redis_ok = await test_redis_connection()
    results.append(("Redis", redis_ok))
    
    # Test basic connection
    connection_ok = await test_server_connection()
    results.append(("Server Connection", connection_ok))
    
    if connection_ok:
        # Test multiple clients
        multi_client_ok = await test_multiple_clients()
        results.append(("Multiple Clients", multi_client_ok))
    
    # Summary
    print("\n" + "=" * 40)
    print("🎯 DEBUG TEST SUMMARY")
    print("=" * 40)
    
    for test_name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {test_name}")
    
    failed_count = sum(1 for _, success in results if not success)
    
    if failed_count == 0:
        print("\n🎉 All debug tests passed!")
        print("   The server appears to be working correctly.")
        print("   You can now run: python test_basic_game.py")
    else:
        print(f"\n⚠️  {failed_count} test(s) failed.")
        print("   Fix these issues before running the full test:")
        print("")
        if not redis_ok:
            print("   🗄️  Start Redis server: redis-server")
        if not connection_ok:
            print("   🖥️  Start the game server: python backend/server.py")
            
    print("=" * 40)

if __name__ == "__main__":
    asyncio.run(main())
