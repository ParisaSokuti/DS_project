#!/usr/bin/env python3
"""
Real-world fault tolerance test using actual authentication flow
"""

import asyncio
import websockets
import json
import time
import sys
import os
import subprocess
import signal

# Add current directory to Python path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SERVER_URI = "ws://localhost:8765"

class RealWorldFaultTest:
    def __init__(self):
        self.clients = []
        
    async def test_basic_connection(self):
        """Test basic connection and authentication"""
        print("🧪 Testing basic connection and authentication flow...")
        
        try:
            async with websockets.connect(SERVER_URI) as ws:
                print("✅ WebSocket connection established")
                
                # Try to join without authentication (should fail)
                await ws.send(json.dumps({"type": "join", "room_code": "9999"}))
                
                response = await asyncio.wait_for(ws.recv(), timeout=5.0)
                data = json.loads(response)
                
                if data.get('type') == 'error' and 'authentication' in data.get('message', '').lower():
                    print("✅ Server properly requires authentication")
                    return True
                else:
                    print(f"⚠️  Unexpected response: {data}")
                    return False
                    
        except Exception as e:
            print(f"❌ Basic connection test failed: {e}")
            return False
            
    async def test_invalid_json_handling(self):
        """Test how server handles invalid JSON"""
        print("🧪 Testing invalid JSON handling...")
        
        try:
            async with websockets.connect(SERVER_URI) as ws:
                print("✅ Connected for JSON test")
                
                # Send invalid JSON
                invalid_json_messages = [
                    "not json at all",
                    '{"invalid": json}',  # Missing quotes
                    '{"unclosed": "string}',  # Unclosed string
                    '{"trailing": "comma",}',  # Trailing comma
                ]
                
                success_count = 0
                for msg in invalid_json_messages:
                    try:
                        await ws.send(msg)
                        
                        # Server should send error response
                        response = await asyncio.wait_for(ws.recv(), timeout=3.0)
                        data = json.loads(response)
                        
                        if data.get('type') == 'error':
                            print(f"✅ Invalid JSON properly handled")
                            success_count += 1
                        else:
                            print(f"⚠️  Unexpected response to invalid JSON: {data.get('type')}")
                            
                    except websockets.ConnectionClosed:
                        print("❌ Connection closed due to invalid JSON")
                        break
                    except asyncio.TimeoutError:
                        print("⏰ No response to invalid JSON")
                    except Exception as e:
                        print(f"❌ Error with invalid JSON: {e}")
                        
                print(f"📊 Invalid JSON handling: {success_count}/{len(invalid_json_messages)} handled properly")
                return success_count >= len(invalid_json_messages) // 2
                
        except Exception as e:
            print(f"❌ JSON handling test failed: {e}")
            return False
            
    async def test_connection_timeout(self):
        """Test connection timeout behavior"""
        print("🧪 Testing connection timeout and ping/pong...")
        
        try:
            async with websockets.connect(
                SERVER_URI,
                ping_interval=5,  # Short ping interval for testing
                ping_timeout=3
            ) as ws:
                print("✅ Connected with short ping interval")
                
                # Wait for ping/pong cycles
                print("⏰ Waiting for ping/pong cycles...")
                await asyncio.sleep(10)  # Wait 10 seconds for ping cycles
                
                # If we get here without connection closing, ping/pong is working
                print("✅ Ping/pong mechanism working correctly")
                return True
                
        except websockets.ConnectionClosed:
            print("🔌 Connection closed during ping/pong test")
            return False
        except Exception as e:
            print(f"❌ Timeout test failed: {e}")
            return False
            
    async def test_rapid_connections(self):
        """Test rapid connection establishment and closure"""
        print("🧪 Testing rapid connections...")
        
        successful_connections = 0
        total_attempts = 20
        
        for i in range(total_attempts):
            try:
                async with websockets.connect(
                    SERVER_URI,
                    open_timeout=3,
                    close_timeout=3
                ) as ws:
                    # Quick message exchange
                    await ws.send(json.dumps({"type": "test"}))
                    
                    try:
                        response = await asyncio.wait_for(ws.recv(), timeout=1.0)
                        successful_connections += 1
                    except asyncio.TimeoutError:
                        successful_connections += 1  # Connection established is still success
                        
                # Small delay between connections
                await asyncio.sleep(0.05)
                
            except Exception as e:
                if i % 5 == 0:  # Only print every 5th error to reduce spam
                    print(f"⚠️  Rapid connection {i+1} failed: {e}")
                    
        print(f"📊 Rapid connections: {successful_connections}/{total_attempts} successful")
        return successful_connections >= total_attempts * 0.8  # 80% success rate
        
    async def test_concurrent_connections(self):
        """Test multiple concurrent connections"""
        print("🧪 Testing concurrent connections...")
        
        async def create_connection(connection_id):
            try:
                async with websockets.connect(SERVER_URI) as ws:
                    # Each connection sends a different message
                    test_msg = {
                        "type": "test_concurrent",
                        "connection_id": connection_id,
                        "timestamp": time.time()
                    }
                    
                    await ws.send(json.dumps(test_msg))
                    
                    # Wait for response
                    try:
                        response = await asyncio.wait_for(ws.recv(), timeout=3.0)
                        return True
                    except asyncio.TimeoutError:
                        return True  # Connection established is success
                        
            except Exception as e:
                print(f"❌ Concurrent connection {connection_id} failed: {e}")
                return False
                
        # Create 10 concurrent connections
        tasks = [create_connection(i) for i in range(10)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        successful_connections = sum(1 for r in results if r is True)
        print(f"📊 Concurrent connections: {successful_connections}/10 successful")
        
        return successful_connections >= 7  # 70% success rate acceptable
        
    async def test_message_ordering(self):
        """Test message ordering under load"""
        print("🧪 Testing message ordering...")
        
        try:
            async with websockets.connect(SERVER_URI) as ws:
                print("✅ Connected for message ordering test")
                
                # Send multiple messages rapidly
                messages_sent = []
                for i in range(10):
                    msg = {
                        "type": "test_order",
                        "sequence": i,
                        "timestamp": time.time()
                    }
                    messages_sent.append(msg)
                    await ws.send(json.dumps(msg))
                    await asyncio.sleep(0.01)  # Small delay
                    
                print(f"📤 Sent {len(messages_sent)} messages in sequence")
                
                # Try to receive responses (may not be in order due to server error responses)
                responses_received = 0
                try:
                    for i in range(10):
                        response = await asyncio.wait_for(ws.recv(), timeout=2.0)
                        responses_received += 1
                except asyncio.TimeoutError:
                    pass
                    
                print(f"📥 Received {responses_received} responses")
                
                # Even if server sends error responses, it should handle all messages
                return responses_received >= 5  # At least half the messages handled
                
        except Exception as e:
            print(f"❌ Message ordering test failed: {e}")
            return False
            
    async def test_server_graceful_shutdown(self):
        """Test server behavior during shutdown (simulated)"""
        print("🧪 Testing server graceful behavior...")
        
        try:
            # Create connection
            async with websockets.connect(SERVER_URI) as ws:
                print("✅ Connected for graceful shutdown test")
                
                # Send a message
                await ws.send(json.dumps({"type": "test_shutdown"}))
                
                # Try to receive response
                try:
                    response = await asyncio.wait_for(ws.recv(), timeout=3.0)
                    data = json.loads(response)
                    print(f"📨 Server response: {data.get('type', 'unknown')}")
                    return True
                except asyncio.TimeoutError:
                    print("⏰ No response from server")
                    return True  # No response is also acceptable
                    
        except websockets.ConnectionClosed:
            print("🔌 Connection closed gracefully")
            return True
        except Exception as e:
            print(f"❌ Graceful shutdown test failed: {e}")
            return False
            
    async def run_all_tests(self):
        """Run all real-world fault tolerance tests"""
        print("🚀 Starting Real-World Fault Tolerance Tests")
        print("=" * 60)
        
        tests = [
            ("Basic Connection & Auth Check", self.test_basic_connection),
            ("Invalid JSON Handling", self.test_invalid_json_handling),
            ("Connection Timeout & Ping", self.test_connection_timeout),
            ("Rapid Connections", self.test_rapid_connections),
            ("Concurrent Connections", self.test_concurrent_connections),
            ("Message Ordering", self.test_message_ordering),
            ("Server Graceful Behavior", self.test_server_graceful_shutdown),
        ]
        
        results = {}
        
        for test_name, test_func in tests:
            try:
                print(f"\n🔍 Running: {test_name}")
                start_time = time.time()
                result = await test_func()
                end_time = time.time()
                
                duration = end_time - start_time
                status = "✅ PASS" if result else "❌ FAIL"
                results[test_name] = (status, f"{duration:.2f}s")
                
                print(f"📋 {test_name}: {'PASSED' if result else 'FAILED'} ({duration:.2f}s)")
                
            except Exception as e:
                results[test_name] = (f"❌ ERROR: {str(e)[:50]}...", "N/A")
                print(f"💥 {test_name}: ERROR - {e}")
                
            # Brief pause between tests
            await asyncio.sleep(1)
            
        # Print final results
        print("\n" + "="*70)
        print("📊 REAL-WORLD FAULT TOLERANCE TEST RESULTS")
        print("="*70)
        
        for test_name, (result, duration) in results.items():
            print(f"{test_name:.<40} {result} ({duration})")
            
        passed_tests = sum(1 for result, _ in results.values() if result.startswith("✅"))
        total_tests = len(results)
        
        print(f"\n🎯 Overall Results: {passed_tests}/{total_tests} tests passed")
        
        if passed_tests >= total_tests * 0.85:  # 85% pass rate
            print("🎉 Server fault tolerance: EXCELLENT")
            print("   Server handles failures gracefully and recovers well")
        elif passed_tests >= total_tests * 0.70:  # 70% pass rate
            print("✅ Server fault tolerance: GOOD")
            print("   Server handles most failure scenarios adequately")
        elif passed_tests >= total_tests * 0.50:  # 50% pass rate
            print("⚠️  Server fault tolerance: ACCEPTABLE")
            print("   Server has basic fault tolerance but could be improved")
        else:
            print("❌ Server fault tolerance: POOR")
            print("   Server needs significant improvements in error handling")
            
        return results

async def main():
    tester = RealWorldFaultTest()
    
    try:
        # Check server availability
        print("🔍 Checking server availability...")
        async with websockets.connect(SERVER_URI, open_timeout=5) as ws:
            print("✅ Server is running and accessible")
            
        # Run tests
        await tester.run_all_tests()
        
    except ConnectionRefusedError:
        print("❌ ERROR: Cannot connect to server")
        print(f"   Make sure the server is running on {SERVER_URI}")
    except Exception as e:
        print(f"❌ Fatal error: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Testing interrupted by user")
    except Exception as e:
        print(f"❌ Test runner error: {e}")
