#!/usr/bin/env python3
"""
Test terminal-specific session isolation
This test verifies that different terminals get different sessions
"""

import os
import sys
import asyncio
import websockets
import json
import subprocess
import time
import unittest

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SERVER_URI = "ws://localhost:8765"


class TestTerminalIsolation(unittest.TestCase):
    """Test that different terminals get isolated sessions"""
    
    def setUp(self):
        """Set up test environment"""
        self.original_env = {}
        # Store original environment variables
        for var in ['TERM_SESSION_ID', 'WINDOWID', 'SSH_TTY']:
            self.original_env[var] = os.environ.get(var)
    
    def tearDown(self):
        """Restore original environment"""
        for var, value in self.original_env.items():
            if value is not None:
                os.environ[var] = value
            else:
                os.environ.pop(var, None)
    
    def test_different_term_sessions(self):
        """Test that different TERM_SESSION_ID values create different sessions"""
        from backend.client import get_terminal_session_id
        
        # Test terminal 1
        os.environ['TERM_SESSION_ID'] = 'terminal_1_abc123'
        session_1 = get_terminal_session_id()
        
        # Test terminal 2
        os.environ['TERM_SESSION_ID'] = 'terminal_2_def456'
        session_2 = get_terminal_session_id()
        
        # Test terminal 3 (same as terminal 1)
        os.environ['TERM_SESSION_ID'] = 'terminal_1_abc123'
        session_3 = get_terminal_session_id()
        
        # Assertions
        self.assertNotEqual(session_1, session_2, "Different terminals should have different sessions")
        self.assertEqual(session_1, session_3, "Same terminal should have same session")
        
        print(f"✅ Terminal 1 session: {session_1}")
        print(f"✅ Terminal 2 session: {session_2}")
        print(f"✅ Terminal 1 (repeat) session: {session_3}")
    
    def test_ssh_session_isolation(self):
        """Test that different SSH sessions create different sessions"""
        from backend.client import get_terminal_session_id
        
        # Clear other terminal identifiers
        for var in ['TERM_SESSION_ID', 'WINDOWID']:
            os.environ.pop(var, None)
        
        # Test SSH session 1
        os.environ['SSH_TTY'] = '/dev/pts/1'
        session_1 = get_terminal_session_id()
        
        # Test SSH session 2
        os.environ['SSH_TTY'] = '/dev/pts/2'
        session_2 = get_terminal_session_id()
        
        self.assertNotEqual(session_1, session_2, "Different SSH sessions should have different sessions")
        
        print(f"✅ SSH session 1: {session_1}")
        print(f"✅ SSH session 2: {session_2}")
    
    def test_fallback_session_consistency(self):
        """Test that fallback session (hostname+username) is consistent"""
        from backend.client import get_terminal_session_id
        
        # Clear all terminal identifiers to force fallback
        for var in ['TERM_SESSION_ID', 'WINDOWID', 'SSH_TTY']:
            os.environ.pop(var, None)
        
        session_1 = get_terminal_session_id()
        session_2 = get_terminal_session_id()
        
        self.assertEqual(session_1, session_2, "Fallback session should be consistent")
        
        print(f"✅ Fallback session: {session_1}")


async def test_multiple_terminals_different_players():
    """Test that multiple simulated terminals get different player slots"""
    
    print("\n🧪 Testing multiple terminal simulation")
    
    # Simulate 3 different terminals connecting
    terminals = [
        {'TERM_SESSION_ID': 'terminal_test_1'},
        {'TERM_SESSION_ID': 'terminal_test_2'},
        {'TERM_SESSION_ID': 'terminal_test_3'}
    ]
    
    connected_players = []
    
    for i, term_env in enumerate(terminals, 1):
        print(f"\n=== Terminal {i} connection ===")
        
        # Set environment for this terminal
        original_env = {}
        for key, value in term_env.items():
            original_env[key] = os.environ.get(key)
            os.environ[key] = value
        
        try:
            # Import with modified environment
            import importlib
            import backend.client
            importlib.reload(backend.client)
            
            session_file = backend.client.get_terminal_session_id()
            print(f"Terminal {i} session file: {session_file}")
            
            # Clean up any existing session for this terminal
            if os.path.exists(session_file):
                os.remove(session_file)
            
            # Connect to server
            async with websockets.connect(SERVER_URI) as ws:
                await ws.send(json.dumps({
                    "type": "join",
                    "username": f"Terminal{i}User",
                    "room_code": "9999"
                }))
                
                response_raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
                response = json.loads(response_raw)
                
                if response.get('type') == 'join_success':
                    player_info = {
                        'terminal': i,
                        'player_id': response.get('player_id'),
                        'username': response.get('username'),
                        'player_number': response.get('player_number'),
                        'session_file': session_file
                    }
                    connected_players.append(player_info)
                    
                    print(f"✅ Connected as {player_info['username']} (Player {player_info['player_number']})")
                    print(f"   Player ID: {player_info['player_id'][:8]}...")
                else:
                    print(f"❌ Connection failed: {response}")
        
        except Exception as e:
            print(f"❌ Terminal {i} error: {e}")
        
        finally:
            # Restore original environment
            for key, value in original_env.items():
                if value is not None:
                    os.environ[key] = value
                else:
                    os.environ.pop(key, None)
    
    # Analyze results
    print(f"\n📊 Results: {len(connected_players)} terminals connected")
    
    unique_player_ids = set(p['player_id'] for p in connected_players)
    unique_player_numbers = set(p['player_number'] for p in connected_players)
    unique_session_files = set(p['session_file'] for p in connected_players)
    
    print(f"Unique player IDs: {len(unique_player_ids)}")
    print(f"Unique player numbers: {len(unique_player_numbers)}")
    print(f"Unique session files: {len(unique_session_files)}")
    
    success = (
        len(unique_player_ids) == len(connected_players) and
        len(unique_player_numbers) == len(connected_players) and
        len(unique_session_files) == len(connected_players)
    )
    
    if success:
        print("✅ SUCCESS: All terminals got unique players and sessions")
    else:
        print("❌ FAILURE: Some terminals shared players or sessions")
        for player in connected_players:
            print(f"  Terminal {player['terminal']}: {player['username']} - {player['player_id'][:8]}... - {player['session_file']}")
    
    return success


async def main():
    """Main test runner"""
    print("🧪 Terminal Isolation Test Suite")
    print("=" * 50)
    
    # Run unit tests
    print("\n📋 Running unit tests...")
    unittest.main(argv=[''], exit=False, verbosity=2)
    
    # Run integration tests
    print("\n🔗 Running integration tests...")
    
    success = await test_multiple_terminals_different_players()
    
    if success:
        print("\n✅ All tests passed!")
        print("🎉 Terminal isolation is working correctly")
    else:
        print("\n❌ Some tests failed!")
        print("⚠️  Terminal isolation needs debugging")
    
    return success


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⚠️  Tests interrupted by user")
    except Exception as e:
        print(f"\n❌ Test suite error: {e}")
