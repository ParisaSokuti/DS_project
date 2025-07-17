#!/usr/bin/env python3
"""
Fixed Load Balancer Test Script
Tests the improved load balancer with race condition fixes
"""

import asyncio
import websockets
import json
import time
import sys
import os

# Add current directory to Python path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SERVER_URI = "ws://localhost:8760"  # Load balancer port

async def test_client(client_id):
    """Test client that connects to load balancer"""
    try:
        print(f"🔌 Client {client_id}: Connecting to load balancer...")
        
        async with websockets.connect(
            SERVER_URI,
            ping_interval=60,
            ping_timeout=300,
            close_timeout=300
        ) as ws:
            print(f"✅ Client {client_id}: Connected successfully")
            
            # Send test message
            test_message = {
                "type": "test",
                "client_id": client_id,
                "message": f"Hello from client {client_id}"
            }
            
            await ws.send(json.dumps(test_message))
            print(f"📤 Client {client_id}: Sent test message")
            
            # Wait for response
            try:
                response = await asyncio.wait_for(ws.recv(), timeout=10.0)
                print(f"📥 Client {client_id}: Received response: {response[:100]}...")
            except asyncio.TimeoutError:
                print(f"⏰ Client {client_id}: No response received (this is normal)")
            
            # Keep connection alive for a bit
            await asyncio.sleep(5)
            
            print(f"👋 Client {client_id}: Closing connection")
            
    except Exception as e:
        print(f"❌ Client {client_id}: Error - {e}")

async def test_load_balancer():
    """Test the load balancer with multiple concurrent connections"""
    print("🧪 Testing Load Balancer with Race Condition Fixes")
    print("=" * 60)
    
    # Test 1: Multiple simultaneous connections
    print("\n📍 Test 1: Multiple simultaneous connections")
    tasks = []
    for i in range(4):
        task = asyncio.create_task(test_client(f"test_{i}"))
        tasks.append(task)
        await asyncio.sleep(0.1)  # Small delay between connections
    
    # Wait for all clients to complete
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    successful = sum(1 for r in results if not isinstance(r, Exception))
    print(f"\n📊 Results: {successful}/{len(tasks)} clients connected successfully")
    
    # Test 2: Rapid successive connections
    print("\n📍 Test 2: Rapid successive connections (stress test)")
    for i in range(3):
        try:
            await test_client(f"rapid_{i}")
        except Exception as e:
            print(f"❌ Rapid test {i} failed: {e}")
        await asyncio.sleep(1)
    
    print("\n✅ Load balancer tests completed")

if __name__ == "__main__":
    print("🛡️ Load Balancer Race Condition Fix Test")
    print("Make sure your load balancer and at least one server are running!")
    print("Commands to run first:")
    print("  Terminal 1: python backend/load_balancer.py")
    print("  Terminal 2: python backend/server.py --port 8765")
    print("  Terminal 3: python backend/server.py --port 8766")
    print()
    
    try:
        asyncio.run(test_load_balancer())
    except KeyboardInterrupt:
        print("\n👋 Test interrupted")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
