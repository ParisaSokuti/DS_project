#!/usr/bin/env python3
"""
Integration test for session persistence across client restarts
This test simulates real-world usage patterns
"""

import os
import sys
import asyncio
import websockets
import json
import subprocess
import time
import signal
import threading

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SERVER_URI = "ws://localhost:8765"


async def simulate_client_session(client_name, session_env=None):
    """Simulate a client session with optional environment"""
    
    if session_env:
        # Set environment variables for this session
        for key, value in session_env.items():
            os.environ[key] = value
    
    try:
        # Import client module with current environment
        import importlib
        import backend.client
        importlib.reload(backend.client)
        
        session_file = backend.client.SESSION_FILE
        
        print(f"\n🔍 {client_name}: Session file: {session_file}")
        
        # Check for existing session
        existing_player_id = None
        if os.path.exists(session_file):
            with open(session_file, 'r') as f:
                existing_player_id = f.read().strip()
            print(f"📋 {client_name}: Found existing session: {existing_player_id[:8]}...")
        else:
            print(f"📝 {client_name}: No existing session found")
        
        # Connect to server
        async with websockets.connect(SERVER_URI) as ws:
            if existing_player_id:
                # Try to reconnect
                message = {
                    "type": "reconnect",
                    "player_id": existing_player_id,
                    "room_code": "9999"
                }
                print(f"🔄 {client_name}: Attempting reconnection...")
            else:
                # Join as new player
                message = {
                    "type": "join", 
                    "username": client_name,
                    "room_code": "9999"
                }
                print(f"🆕 {client_name}: Joining as new player...")
            
            await ws.send(json.dumps(message))
            
            # Wait for response
            response_raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
            response = json.loads(response_raw)
            
            result = {'client_name': client_name, 'session_file': session_file}
            
            if response.get('type') == 'join_success':
                result.update({
                    'success': True,
                    'player_id': response.get('player_id'),
                    'username': response.get('username'),
                    'player_number': response.get('player_number'),
                    'reconnected': response.get('reconnected', False),
                    'action': 'joined'
                })
                
                # Save session for future reconnections
                with open(session_file, 'w') as f:
                    f.write(result['player_id'])
                
                print(f"✅ {client_name}: Joined as {result['username']} (Player {result['player_number']})")
                print(f"   Player ID: {result['player_id'][:8]}...")
                print(f"   Reconnected: {result['reconnected']}")
                
            elif response.get('type') == 'reconnect_success':
                result.update({
                    'success': True,
                    'player_id': response.get('player_id'),
                    'username': response.get('username'),
                    'reconnected': True,
                    'action': 'reconnected'
                })
                
                print(f"✅ {client_name}: Reconnected as {result['username']}")
                print(f"   Player ID: {result['player_id'][:8]}...")
                
            else:
                result.update({
                    'success': False,
                    'error': response,
                    'action': 'failed'
                })
                print(f"❌ {client_name}: Failed - {response}")
            
            return result
            
    except Exception as e:
        print(f"❌ {client_name}: Error - {e}")
        return {
            'client_name': client_name,
            'success': False,
            'error': str(e),
            'action': 'error'
        }


async def test_session_persistence_workflow():
    """Test a complete session persistence workflow"""
    
    print("\n🧪 Testing Session Persistence Workflow")
    print("=" * 60)
    
    # Clear Redis to start fresh
    try:
        import redis
        r = redis.Redis(host='localhost', port=6379, decode_responses=True)
        r.flushall()
        print("🧹 Redis cleared")
    except:
        print("⚠️  Could not clear Redis (continuing anyway)")
    
    results = []
    
    # Step 1: First client connects
    print(f"\n=== Step 1: Client connects for first time ===")
    
    result1 = await simulate_client_session("Alice", {'TERM_SESSION_ID': 'alice_terminal_123'})
    results.append(result1)
    
    if not result1.get('success'):
        print("❌ Step 1 failed - aborting test")
        return False
    
    original_player_id = result1['player_id']
    original_username = result1['username']
    original_player_number = result1['player_number']
    
    # Step 2: Client "exits" (connection closes but session preserved)
    print(f"\n=== Step 2: Client exits (session preserved) ===")
    print(f"💾 Session file preserved: {result1['session_file']}")
    
    # Verify session file exists
    if os.path.exists(result1['session_file']):
        with open(result1['session_file'], 'r') as f:
            saved_id = f.read().strip()
        print(f"✅ Session file contains: {saved_id[:8]}...")
    else:
        print("❌ Session file missing after exit")
        return False
    
    # Step 3: Wait a moment (simulate time between restarts)
    print(f"\n=== Step 3: Wait between sessions ===")
    await asyncio.sleep(2)
    print("⏳ Waited 2 seconds...")
    
    # Step 4: Same client reconnects
    print(f"\n=== Step 4: Client reconnects ===")
    
    result2 = await simulate_client_session("Alice_Reconnect", {'TERM_SESSION_ID': 'alice_terminal_123'})
    results.append(result2)
    
    if not result2.get('success'):
        print("❌ Step 4 failed - reconnection unsuccessful")
        return False
    
    # Step 5: Verify reconnection worked correctly
    print(f"\n=== Step 5: Verify reconnection ===")
    
    verification_results = {
        'same_player_id': result2['player_id'] == original_player_id,
        'same_username': result2['username'] == original_username,
        'was_reconnection': result2.get('action') == 'reconnected',
        'same_session_file': result2['session_file'] == result1['session_file']
    }
    
    print(f"Original: {original_username} (Player {original_player_number}) - {original_player_id[:8]}...")
    print(f"Reconnected: {result2['username']} - {result2['player_id'][:8]}...")
    print(f"Same player ID: {verification_results['same_player_id']}")
    print(f"Same username: {verification_results['same_username']}")
    print(f"Was reconnection: {verification_results['was_reconnection']}")
    print(f"Same session file: {verification_results['same_session_file']}")
    
    # Step 6: Test different terminal gets different session
    print(f"\n=== Step 6: Different terminal gets different session ===")
    
    result3 = await simulate_client_session("Bob", {'TERM_SESSION_ID': 'bob_terminal_456'})
    results.append(result3)
    
    if result3.get('success'):
        different_session_file = result3['session_file'] != result1['session_file']
        different_player_id = result3['player_id'] != original_player_id
        
        print(f"Bob's session file: {result3['session_file']}")
        print(f"Alice's session file: {result1['session_file']}")
        print(f"Different session files: {different_session_file}")
        print(f"Different player IDs: {different_player_id}")
        
        verification_results.update({
            'different_terminals_different_sessions': different_session_file,
            'different_terminals_different_players': different_player_id
        })
    else:
        print("❌ Step 6 failed - Bob couldn't connect")
        verification_results.update({
            'different_terminals_different_sessions': False,
            'different_terminals_different_players': False
        })
    
    # Summary
    print(f"\n📊 Test Results Summary:")
    print("=" * 40)
    
    all_passed = all(verification_results.values())
    
    for check, passed in verification_results.items():
        status = "✅" if passed else "❌"
        print(f"{status} {check.replace('_', ' ').title()}: {passed}")
    
    if all_passed:
        print(f"\n🎉 ALL TESTS PASSED!")
        print("Session persistence is working correctly")
    else:
        print(f"\n⚠️  SOME TESTS FAILED!")
        print("Session persistence needs debugging")
    
    # Cleanup
    print(f"\n🧹 Cleaning up test session files...")
    for result in results:
        if 'session_file' in result:
            try:
                if os.path.exists(result['session_file']):
                    os.remove(result['session_file'])
                    print(f"   Removed: {result['session_file']}")
            except Exception as e:
                print(f"   Failed to remove {result['session_file']}: {e}")
    
    return all_passed


async def main():
    """Main test runner"""
    print("🧪 Session Persistence Integration Test")
    print("=" * 50)
    
    try:
        success = await test_session_persistence_workflow()
        
        if success:
            print(f"\n✅ Integration test completed successfully!")
            return 0
        else:
            print(f"\n❌ Integration test failed!")
            return 1
            
    except Exception as e:
        print(f"\n💥 Integration test crashed: {e}")
        import traceback
        traceback.print_exc()
        return 2


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n⚠️  Test interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ Test runner error: {e}")
        sys.exit(1)
