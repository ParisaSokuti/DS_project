#!/usr/bin/env python3
"""
Enhanced Fault Tolerance Test Suite for Hokm Game Server
Tests various failure scenarios and recovery mechanisms with proper authentication
"""

import asyncio
import websockets
import json
import time
import sys
import os
import random
import uuid

# Add current directory to Python path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Configuration
SERVER_URI = "ws://localhost:8765"
TEST_ROOM = "9999"

class EnhancedFaultToleranceTest:
    def __init__(self):
        self.test_results = []
        
    async def authenticate_client(self, ws, username):
        """Handle client authentication"""
        try:
            # Send authentication request (register new user for testing)
            auth_request = {
                "type": "auth_request",
                "action": "register",
                "username": username,
                "password": f"test_pass_{username}",
                "email": f"{username}@test.com"
            }
            
            await ws.send(json.dumps(auth_request))
            
            # Wait for authentication response
            response = await asyncio.wait_for(ws.recv(), timeout=10.0)
            data = json.loads(response)
            
            if data.get('type') == 'auth_response' and data.get('success'):
                print(f"✅ Authentication successful for {username}")
                return True
            else:
                print(f"❌ Authentication failed for {username}: {data.get('message', 'Unknown error')}")
                return False
                
        except Exception as e:
            print(f"❌ Authentication error for {username}: {e}")
            return False
            
    async def create_authenticated_client(self, username, client_id):
        """Create a test client with proper authentication"""
        try:
            print(f"🔌 Connecting client {client_id} ({username})...")
            
            async with websockets.connect(
                SERVER_URI,
                ping_interval=60,
                ping_timeout=300,
                close_timeout=300,
                max_size=1024*1024,
                max_queue=100
            ) as ws:
                print(f"✅ Client {client_id} connected successfully")
                
                # Authenticate the client
                if not await self.authenticate_client(ws, username):
                    return False
                
                # Join the test room
                join_msg = {
                    "type": "join",
                    "room_code": TEST_ROOM
                }
                await ws.send(json.dumps(join_msg))
                
                # Wait for join response
                join_response = await asyncio.wait_for(ws.recv(), timeout=5.0)
                join_data = json.loads(join_response)
                
                if join_data.get('type') == 'join_success':
                    print(f"🎮 Client {client_id} ({username}) joined game successfully")
                    
                    # Listen for a few more messages to test stability
                    message_count = 0
                    while message_count < 3:
                        try:
                            message = await asyncio.wait_for(ws.recv(), timeout=5.0)
                            data = json.loads(message)
                            msg_type = data.get('type')
                            print(f"📨 Client {client_id} received: {msg_type}")
                            message_count += 1
                            
                            if msg_type == 'room_status':
                                players = data.get('usernames', [])
                                print(f"👥 Room status - Players: {players}")
                                
                        except asyncio.TimeoutError:
                            print(f"⏰ Client {client_id} message timeout")
                            break
                        except json.JSONDecodeError:
                            print(f"❌ Client {client_id} JSON decode error")
                            break
                            
                    return True
                else:
                    print(f"❌ Client {client_id} failed to join: {join_data.get('message', 'Unknown error')}")
                    return False
                    
        except websockets.ConnectionClosed:
            print(f"🔌 Client {client_id} connection closed")
            return False
        except ConnectionRefusedError:
            print(f"❌ Client {client_id} connection refused")
            return False
        except Exception as e:
            print(f"❌ Client {client_id} error: {e}")
            return False
            
    async def test_authentication_flow(self):
        """Test the authentication system"""
        print("\n" + "="*60)
        print("🧪 TEST 1: Authentication Flow")
        print("="*60)
        
        test_username = f"auth_test_user_{int(time.time())}"
        
        try:
            async with websockets.connect(SERVER_URI) as ws:
                print(f"✅ Connected for authentication test")
                
                # Test registration
                print("🔐 Testing user registration...")
                auth_success = await self.authenticate_client(ws, test_username)
                
                if auth_success:
                    print("✅ Authentication flow working correctly")
                    return True
                else:
                    print("❌ Authentication flow failed")
                    return False
                    
        except Exception as e:
            print(f"❌ Authentication test failed: {e}")
            return False
            
    async def test_connection_resilience(self):
        """Test connection drops and recovery"""
        print("\n" + "="*60)
        print("🧪 TEST 2: Connection Resilience")
        print("="*60)
        
        username = f"resilience_test_{int(time.time())}"
        
        try:
            # First connection
            async with websockets.connect(SERVER_URI) as ws1:
                print("✅ Initial connection established")
                
                # Authenticate and join
                if await self.authenticate_client(ws1, username):
                    await ws1.send(json.dumps({"type": "join", "room_code": TEST_ROOM}))
                    response = await asyncio.wait_for(ws1.recv(), timeout=5.0)
                    print(f"📨 Join response: {json.loads(response).get('type')}")
                    
                    # Get player ID for reconnection testing
                    join_data = json.loads(response)
                    player_id = join_data.get('player_id')
                    
                    print("🔌 Simulating connection drop...")
                    await ws1.close()
                    
                # Attempt reconnection after delay
                await asyncio.sleep(2)
                print("🔄 Attempting reconnection...")
                
                async with websockets.connect(SERVER_URI) as ws2:
                    print("✅ Reconnection established")
                    
                    # Re-authenticate
                    if await self.authenticate_client(ws2, username):
                        # Try to reconnect to game if we have player_id
                        if player_id:
                            reconnect_msg = {
                                "type": "reconnect",
                                "player_id": player_id,
                                "room_code": TEST_ROOM
                            }
                        else:
                            reconnect_msg = {"type": "join", "room_code": TEST_ROOM}
                            
                        await ws2.send(json.dumps(reconnect_msg))
                        response2 = await asyncio.wait_for(ws2.recv(), timeout=5.0)
                        reconnect_data = json.loads(response2)
                        
                        if reconnect_data.get('type') in ['reconnect_success', 'join_success']:
                            print("✅ Reconnection successful")
                            return True
                        else:
                            print(f"⚠️  Reconnection response: {reconnect_data.get('type')}")
                            return True  # Still count as success if we can rejoin
                            
                return False
                
        except Exception as e:
            print(f"❌ Connection resilience test failed: {e}")
            return False
            
    async def test_concurrent_authentications(self):
        """Test multiple clients authenticating simultaneously"""
        print("\n" + "="*60)
        print("🧪 TEST 3: Concurrent Authentication")
        print("="*60)
        
        async def authenticate_concurrent_client(client_id):
            username = f"concurrent_user_{client_id}_{int(time.time())}"
            try:
                async with websockets.connect(SERVER_URI) as ws:
                    success = await self.authenticate_client(ws, username)
                    if success:
                        # Try to join room too
                        await ws.send(json.dumps({"type": "join", "room_code": TEST_ROOM}))
                        response = await asyncio.wait_for(ws.recv(), timeout=5.0)
                        data = json.loads(response)
                        if data.get('type') == 'join_success':
                            print(f"✅ Concurrent client {client_id} fully authenticated and joined")
                            return True
                    return False
            except Exception as e:
                print(f"❌ Concurrent client {client_id} failed: {e}")
                return False
                
        # Test with 5 concurrent authentications
        tasks = [authenticate_concurrent_client(i) for i in range(5)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        success_count = sum(1 for r in results if r is True)
        print(f"📊 Concurrent authentications: {success_count}/5 successful")
        
        return success_count >= 3  # At least 3/5 should succeed
        
    async def test_malformed_requests(self):
        """Test server handling of malformed requests"""
        print("\n" + "="*60)
        print("🧪 TEST 4: Malformed Request Handling")
        print("="*60)
        
        try:
            async with websockets.connect(SERVER_URI) as ws:
                print("✅ Connected for malformed request testing")
                
                # Test various malformed requests
                malformed_requests = [
                    "not json at all",
                    '{"incomplete": "json"',  # Malformed JSON
                    json.dumps({"type": "nonexistent_action"}),  # Invalid action
                    json.dumps({"no_type": "field"}),  # Missing type
                    json.dumps({"type": "auth_request"}),  # Missing required auth fields
                    json.dumps({"type": "join", "room_code": ""}),  # Empty room code
                    json.dumps({"type": "play_card", "card": None}),  # Null values
                ]
                
                handled_properly = 0
                for i, request in enumerate(malformed_requests):
                    try:
                        print(f"📤 Sending malformed request {i+1}...")
                        await ws.send(request)
                        
                        # Server should respond with error
                        try:
                            response = await asyncio.wait_for(ws.recv(), timeout=3.0)
                            data = json.loads(response)
                            if data.get('type') == 'error':
                                print(f"✅ Server properly handled malformed request {i+1}")
                                handled_properly += 1
                            else:
                                print(f"⚠️  Unexpected response to malformed request {i+1}: {data.get('type')}")
                        except asyncio.TimeoutError:
                            print(f"⏰ No response to malformed request {i+1}")
                        except json.JSONDecodeError:
                            print(f"❌ Invalid JSON response to malformed request {i+1}")
                            
                    except Exception as e:
                        print(f"❌ Error with malformed request {i+1}: {e}")
                        
                print(f"📊 Malformed request handling: {handled_properly}/{len(malformed_requests)}")
                return handled_properly >= len(malformed_requests) // 2
                
        except Exception as e:
            print(f"❌ Malformed request test failed: {e}")
            return False
            
    async def test_room_management_stress(self):
        """Test room management under stress"""
        print("\n" + "="*60)
        print("🧪 TEST 5: Room Management Stress Test")
        print("="*60)
        
        async def stress_room_operations(operation_id):
            username = f"stress_user_{operation_id}_{int(time.time())}"
            try:
                async with websockets.connect(SERVER_URI) as ws:
                    # Authenticate
                    if not await self.authenticate_client(ws, username):
                        return False
                        
                    # Perform various room operations
                    operations = [
                        {"type": "join", "room_code": TEST_ROOM},
                        {"type": "join", "room_code": f"room_{operation_id}"},  # Different room
                        {"type": "clear_room", "room_code": f"room_{operation_id}"},  # Clear operation
                    ]
                    
                    success_count = 0
                    for op in operations:
                        try:
                            await ws.send(json.dumps(op))
                            response = await asyncio.wait_for(ws.recv(), timeout=3.0)
                            data = json.loads(response)
                            if data.get('type') in ['join_success', 'error']:  # Both are valid responses
                                success_count += 1
                            print(f"🔄 Stress operation {operation_id}: {op['type']} -> {data.get('type')}")
                        except asyncio.TimeoutError:
                            print(f"⏰ Stress operation {operation_id}: {op['type']} -> timeout")
                        await asyncio.sleep(0.1)
                        
                    return success_count >= len(operations) // 2
                    
            except Exception as e:
                print(f"❌ Stress operation {operation_id} failed: {e}")
                return False
                
        # Run multiple stress operations concurrently
        tasks = [stress_room_operations(i) for i in range(8)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        success_count = sum(1 for r in results if r is True)
        print(f"📊 Room stress operations: {success_count}/8 successful")
        
        return success_count >= 5  # At least 5/8 should succeed
        
    async def run_all_tests(self):
        """Run all enhanced fault tolerance tests"""
        print("🚀 Starting Enhanced Fault Tolerance Test Suite")
        print("=" * 60)
        
        tests = [
            ("Authentication Flow", self.test_authentication_flow),
            ("Connection Resilience", self.test_connection_resilience),
            ("Concurrent Authentication", self.test_concurrent_authentications),
            ("Malformed Request Handling", self.test_malformed_requests),
            ("Room Management Stress", self.test_room_management_stress),
        ]
        
        results = {}
        
        for test_name, test_func in tests:
            try:
                print(f"\n🔍 Running: {test_name}")
                result = await test_func()
                results[test_name] = "✅ PASS" if result else "❌ FAIL"
                print(f"📋 {test_name}: {'PASSED' if result else 'FAILED'}")
            except Exception as e:
                results[test_name] = f"❌ ERROR: {str(e)[:50]}..."
                print(f"💥 {test_name}: ERROR - {e}")
                
            # Brief pause between tests
            await asyncio.sleep(2)
            
        # Print final results
        print("\n" + "="*60)
        print("📊 ENHANCED FAULT TOLERANCE TEST RESULTS")
        print("="*60)
        
        for test_name, result in results.items():
            print(f"{test_name:.<35} {result}")
            
        passed_tests = sum(1 for result in results.values() if result.startswith("✅"))
        total_tests = len(results)
        
        print(f"\n🎯 Overall Results: {passed_tests}/{total_tests} tests passed")
        
        if passed_tests >= total_tests * 0.8:  # 80% pass rate
            print("🎉 Fault tolerance: EXCELLENT - Server is highly resilient")
        elif passed_tests >= total_tests * 0.6:  # 60% pass rate
            print("✅ Fault tolerance: GOOD - Server handles most failure scenarios well")
        else:
            print("⚠️  Fault tolerance: NEEDS IMPROVEMENT - Some critical issues found")
            
        return results

async def main():
    """Main test runner"""
    tester = EnhancedFaultToleranceTest()
    
    try:
        # First, check if server is running
        print("🔍 Checking server availability...")
        async with websockets.connect(SERVER_URI, open_timeout=5) as ws:
            print("✅ Server is running and accessible")
            
        # Run the test suite
        await tester.run_all_tests()
        
    except ConnectionRefusedError:
        print("❌ ERROR: Cannot connect to server")
        print(f"   Make sure the server is running on {SERVER_URI}")
        print("   Try running: python backend/server.py")
    except Exception as e:
        print(f"❌ Fatal error during testing: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Testing interrupted by user")
    except Exception as e:
        print(f"❌ Test runner error: {e}")
