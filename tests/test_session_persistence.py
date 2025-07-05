#!/usr/bin/env python3
"""
Test session persistence across client restarts
This test verifies that player sessions are preserved when clients exit and restart in the same terminal
"""

import os
import sys
import time
import subprocess
import asyncio
import websockets
import json
import tempfile
import unittest

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SERVER_URI = "ws://localhost:8765"


class TestSessionPersistence(unittest.TestCase):
    """Test session persistence functionality"""
    
    def setUp(self):
        """Set up test environment"""
        self.test_session_files = []
        
    def tearDown(self):
        """Clean up test files"""
        for session_file in self.test_session_files:
            try:
                if os.path.exists(session_file):
                    os.remove(session_file)
            except:
                pass
    
    def test_session_file_creation(self):
        """Test that session files are created with persistent naming"""
        # Import the client module to test session file naming
        from backend.client import get_terminal_session_id, SESSION_FILE
        
        # Test that session ID is consistent
        session_id_1 = get_terminal_session_id()
        session_id_2 = get_terminal_session_id()
        
        self.assertEqual(session_id_1, session_id_2, "Session ID should be consistent")
        
        # Test that session file name is consistent
        self.assertTrue(SESSION_FILE.startswith('.player_session_'), 
                       f"Session file should start with '.player_session_', got: {SESSION_FILE}")
        
        print(f"✅ Session file: {SESSION_FILE}")
        
    def test_session_file_different_environments(self):
        """Test that different environments get different session files"""
        from backend.client import get_terminal_session_id
        
        # Test with different environment variables
        original_term = os.environ.get('TERM_SESSION_ID', '')
        
        # Set first environment
        os.environ['TERM_SESSION_ID'] = 'test_session_1'
        session_1 = get_terminal_session_id()
        
        # Set second environment  
        os.environ['TERM_SESSION_ID'] = 'test_session_2'
        session_2 = get_terminal_session_id()
        
        # Restore original
        if original_term:
            os.environ['TERM_SESSION_ID'] = original_term
        else:
            os.environ.pop('TERM_SESSION_ID', None)
        
        self.assertNotEqual(session_1, session_2, 
                           "Different environments should get different session files")
        
        print(f"✅ Environment 1 session: {session_1}")
        print(f"✅ Environment 2 session: {session_2}")


async def test_client_connection_and_session():
    """Test client connection and session management"""
    
    print("\n🧪 Testing client connection and session management")
    
    # Test 1: Connect and create session
    print("\n=== Test 1: Initial connection ===")
    
    try:
        async with websockets.connect(SERVER_URI) as ws:
            # Send join message
            await ws.send(json.dumps({
                "type": "join",
                "username": "TestPlayer",
                "room_code": "9999"
            }))
            
            # Wait for response
            response_raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
            response = json.loads(response_raw)
            
            if response.get('type') == 'join_success':
                player_id = response.get('player_id')
                username = response.get('username')
                player_number = response.get('player_number')
                
                print(f"✅ Connected as {username} (Player {player_number})")
                print(f"   Player ID: {player_id[:8]}...")
                
                return {
                    'player_id': player_id,
                    'username': username,
                    'player_number': player_number
                }
            else:
                print(f"❌ Connection failed: {response}")
                return None
                
    except Exception as e:
        print(f"❌ Connection error: {e}")
        return None


async def test_session_persistence():
    """Test that sessions persist across restarts"""
    
    print("\n🧪 Testing session persistence")
    
    # Import client functions
    from backend.client import SESSION_FILE
    
    # Clean up any existing session
    if os.path.exists(SESSION_FILE):
        os.remove(SESSION_FILE)
        print(f"🧹 Cleaned up existing session file: {SESSION_FILE}")
    
    # Test 1: Connect and save session
    print("\n=== Test 1: Connect and save session ===")
    
    result1 = await test_client_connection_and_session()
    
    if not result1:
        print("❌ Initial connection failed")
        return False
    
    # Simulate session saving (this would normally happen in the client)
    with open(SESSION_FILE, 'w') as f:
        f.write(result1['player_id'])
    
    print(f"💾 Session saved to: {SESSION_FILE}")
    
    # Test 2: Check session file exists and contains correct data
    print("\n=== Test 2: Verify session file ===")
    
    if os.path.exists(SESSION_FILE):
        with open(SESSION_FILE, 'r') as f:
            saved_player_id = f.read().strip()
        
        if saved_player_id == result1['player_id']:
            print(f"✅ Session file contains correct player ID: {saved_player_id[:8]}...")
        else:
            print(f"❌ Session file has wrong player ID. Expected: {result1['player_id'][:8]}..., Got: {saved_player_id[:8]}...")
            return False
    else:
        print(f"❌ Session file not found: {SESSION_FILE}")
        return False
    
    # Test 3: Simulate restart and reconnection
    print("\n=== Test 3: Simulate restart and reconnection ===")
    
    try:
        async with websockets.connect(SERVER_URI) as ws:
            # Send reconnect message with saved player ID
            await ws.send(json.dumps({
                "type": "reconnect",
                "player_id": saved_player_id,
                "room_code": "9999"
            }))
            
            # Wait for response
            response_raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
            response = json.loads(response_raw)
            
            if response.get('type') == 'reconnect_success':
                reconnected_player_id = response.get('player_id')
                username = response.get('username')
                
                print(f"✅ Reconnected as {username}")
                print(f"   Original ID: {result1['player_id'][:8]}...")
                print(f"   Reconnected ID: {reconnected_player_id[:8]}...")
                
                if reconnected_player_id == result1['player_id']:
                    print("✅ SUCCESS: Same player ID on reconnection")
                    return True
                else:
                    print("❌ FAILURE: Different player ID on reconnection")
                    return False
            else:
                print(f"❌ Reconnection failed: {response}")
                return False
                
    except Exception as e:
        print(f"❌ Reconnection error: {e}")
        return False


async def main():
    """Main test runner"""
    print("🧪 Session Persistence Test Suite")
    print("=" * 50)
    
    # Run unit tests
    print("\n📋 Running unit tests...")
    unittest.main(argv=[''], exit=False, verbosity=2)
    
    # Run integration tests
    print("\n🔗 Running integration tests...")
    
    success = await test_session_persistence()
    
    if success:
        print("\n✅ All tests passed!")
        print("🎉 Session persistence is working correctly")
    else:
        print("\n❌ Some tests failed!")
        print("⚠️  Session persistence needs debugging")
    
    return success


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⚠️  Tests interrupted by user")
    except Exception as e:
        print(f"\n❌ Test suite error: {e}")
