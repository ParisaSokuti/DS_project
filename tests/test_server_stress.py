#!/usr/bin/env python3
"""
Test to specifically reproduce and verify the fix for the server disconnect bug.
"""

import asyncio
import websockets
import json
import time

async def test_server_disconnect_bug():
    """Test the server disconnect bug scenario"""
    print("=== Testing Server Disconnect Bug Fix ===")
    
    uri = "ws://localhost:8765"
    
    try:
        async with websockets.connect(uri) as websocket:
            print("✓ Connected to server")
            
            # Join the game
            join_msg = {
                "type": "join",
                "room_code": "9999"
            }
            await websocket.send(json.dumps(join_msg))
            print("✓ Sent join message")
            
            # Wait for join confirmation
            response = await websocket.recv()
            data = json.loads(response)
            print(f"✓ Received response: {data['type']}")
            
            if data['type'] == 'join_success':
                player_id = data['player_id']
                print(f"✓ Successfully joined as {data['username']}")
                
                # Now simulate rapid invalid messages to stress test error handling
                print("\n--- Stress Testing Error Handling ---")
                
                # Send several malformed/invalid messages rapidly
                invalid_messages = [
                    {"type": "play_card"},  # Missing required fields
                    {"type": "play_card", "room_code": "9999"},  # Missing player_id and card
                    {"type": "play_card", "room_code": "9999", "player_id": "invalid"},  # Invalid player_id
                    {"type": "invalid_type", "data": "test"},  # Unknown message type
                    "invalid json",  # This will be caught as JSON decode error in the client, not sent
                    {"type": "play_card", "room_code": "9999", "player_id": player_id, "card": "invalid_card"}
                ]
                
                for i, msg in enumerate(invalid_messages[:-1]):  # Skip the invalid JSON one
                    try:
                        await websocket.send(json.dumps(msg))
                        print(f"✓ Sent invalid message {i+1}")
                        
                        # Try to receive error response
                        try:
                            error_response = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                            error_data = json.loads(error_response)
                            if error_data['type'] == 'error':
                                print(f"  ✓ Received error response: {error_data['message'][:50]}...")
                            else:
                                print(f"  ✓ Received response: {error_data['type']}")
                        except asyncio.TimeoutError:
                            print("  ✓ No response (expected for some invalid messages)")
                        
                        # Small delay between messages
                        await asyncio.sleep(0.1)
                        
                    except websockets.ConnectionClosed:
                        print(f"❌ Connection closed after invalid message {i+1}")
                        return False
                    except Exception as e:
                        print(f"❌ Error sending message {i+1}: {e}")
                        return False
                
                # Test that connection is still alive
                print("\n--- Testing Connection Still Alive ---")
                try:
                    # Send a valid message that should work
                    status_msg = {"type": "join", "room_code": "9999"}  # This should give us a "room full" error but connection should stay alive
                    await websocket.send(json.dumps(status_msg))
                    
                    final_response = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                    final_data = json.loads(final_response)
                    print(f"✓ Connection still alive! Received: {final_data['type']}")
                    return True
                    
                except asyncio.TimeoutError:
                    print("❌ No response from server - connection might be dead")
                    return False
                except websockets.ConnectionClosed:
                    print("❌ Connection closed unexpectedly!")
                    return False
                    
            else:
                print(f"❌ Failed to join: {data}")
                return False
                
    except Exception as e:
        print(f"❌ Test failed with exception: {e}")
        return False

async def test_rapid_message_handling():
    """Test rapid message sending to stress the connection handler"""
    print("\n=== Testing Rapid Message Handling ===")
    
    uri = "ws://localhost:8765"
    
    try:
        async with websockets.connect(uri) as websocket:
            print("✓ Connected to server")
            
            # Join the game
            join_msg = {
                "type": "join",
                "room_code": "9999"
            }
            await websocket.send(json.dumps(join_msg))
            
            # Wait for join response (might be error if room full)
            response = await websocket.recv()
            data = json.loads(response)
            print(f"✓ Join response: {data['type']}")
            
            # Send many rapid messages
            print("Sending 20 rapid messages...")
            for i in range(20):
                rapid_msg = {
                    "type": "play_card",
                    "room_code": "9999",
                    "player_id": "test_player",
                    "card": f"test_card_{i}"
                }
                await websocket.send(json.dumps(rapid_msg))
            
            print("✓ Sent all rapid messages")
            
            # Try to receive some responses
            responses_received = 0
            for i in range(10):  # Try to get up to 10 responses
                try:
                    response = await asyncio.wait_for(websocket.recv(), timeout=0.5)
                    responses_received += 1
                except asyncio.TimeoutError:
                    break
                except websockets.ConnectionClosed:
                    print("❌ Connection closed during rapid message test")
                    return False
            
            print(f"✓ Received {responses_received} responses")
            
            # Test final message to ensure connection is still alive
            final_msg = {"type": "join", "room_code": "9999"}
            await websocket.send(json.dumps(final_msg))
            
            final_response = await asyncio.wait_for(websocket.recv(), timeout=2.0)
            print("✓ Connection survived rapid message test!")
            return True
            
    except Exception as e:
        print(f"❌ Rapid message test failed: {e}")
        return False

async def main():
    """Run all tests"""
    print("Starting server disconnect bug fix tests...\n")
    
    test1_passed = await test_server_disconnect_bug()
    await asyncio.sleep(1)  # Brief pause between tests
    
    test2_passed = await test_rapid_message_handling()
    
    print(f"\n=== Test Results ===")
    print(f"Server Disconnect Bug Test: {'✅ PASSED' if test1_passed else '❌ FAILED'}")
    print(f"Rapid Message Handling Test: {'✅ PASSED' if test2_passed else '❌ FAILED'}")
    
    if test1_passed and test2_passed:
        print("\n🎉 All tests passed! Server disconnect bug appears to be fixed.")
    else:
        print("\n⚠️  Some tests failed. The bug may not be fully fixed.")

if __name__ == "__main__":
    asyncio.run(main())
