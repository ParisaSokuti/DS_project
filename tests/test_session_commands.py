#!/usr/bin/env python3
"""
Test session management commands (exit vs clear_session)
This test verifies that 'exit' preserves sessions while 'clear_session' removes them
"""

import os
import sys
import asyncio
import json
import tempfile
import unittest
from unittest.mock import patch, MagicMock

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestSessionCommands(unittest.TestCase):
    """Test session management commands"""
    
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
    
    def test_clear_session_function(self):
        """Test the clear_session function"""
        from backend.client import clear_session, SESSION_FILE
        
        # Create a test session file
        test_player_id = "test-player-id-12345"
        with open(SESSION_FILE, 'w') as f:
            f.write(test_player_id)
        
        self.test_session_files.append(SESSION_FILE)
        
        # Verify file exists
        self.assertTrue(os.path.exists(SESSION_FILE), "Session file should exist before clear")
        
        # Clear session
        with patch('builtins.print') as mock_print:
            clear_session()
        
        # Verify file is removed
        self.assertFalse(os.path.exists(SESSION_FILE), "Session file should be removed after clear")
        
        # Verify correct message was printed
        mock_print.assert_called_with("🗑️ Session cleared")
    
    def test_preserve_session_function(self):
        """Test the preserve_session function"""
        from backend.client import preserve_session, SESSION_FILE
        
        # Create a test session file
        test_player_id = "test-player-id-67890"
        with open(SESSION_FILE, 'w') as f:
            f.write(test_player_id)
        
        self.test_session_files.append(SESSION_FILE)
        
        # Preserve session
        with patch('builtins.print') as mock_print:
            preserve_session()
        
        # Verify file still exists
        self.assertTrue(os.path.exists(SESSION_FILE), "Session file should still exist after preserve")
        
        # Verify file contents unchanged
        with open(SESSION_FILE, 'r') as f:
            content = f.read().strip()
        
        self.assertEqual(content, test_player_id, "Session file content should be unchanged")
        
        # Verify correct messages were printed
        expected_calls = [
            unittest.mock.call("💾 Session preserved for future reconnections"),
            unittest.mock.call(f"📁 Session file: {SESSION_FILE}")
        ]
        mock_print.assert_has_calls(expected_calls)
    
    def test_clear_session_no_file(self):
        """Test clear_session when no session file exists"""
        from backend.client import clear_session, SESSION_FILE
        
        # Ensure no session file exists
        if os.path.exists(SESSION_FILE):
            os.remove(SESSION_FILE)
        
        # Clear session
        with patch('builtins.print') as mock_print:
            clear_session()
        
        # Verify correct message was printed
        mock_print.assert_called_with("📝 No session file to clear")
    
    def test_session_file_naming_consistency(self):
        """Test that session file naming is consistent across calls"""
        from backend.client import SESSION_FILE, get_terminal_session_id
        
        # Get session file name multiple times
        session_1 = get_terminal_session_id()
        session_2 = get_terminal_session_id()
        
        # Should be the same
        self.assertEqual(session_1, session_2, "Session file name should be consistent")
        
        # Should match the module-level SESSION_FILE
        self.assertEqual(SESSION_FILE, session_1, "SESSION_FILE should match get_terminal_session_id()")
        
        print(f"✅ Consistent session file: {SESSION_FILE}")


class TestSessionFileOperations(unittest.TestCase):
    """Test file operations for session management"""
    
    def test_session_file_creation_and_deletion(self):
        """Test creating and deleting session files"""
        from backend.client import SESSION_FILE
        
        test_content = "test-player-id-abcdef"
        
        # Create session file
        with open(SESSION_FILE, 'w') as f:
            f.write(test_content)
        
        # Verify file exists and has correct content
        self.assertTrue(os.path.exists(SESSION_FILE))
        
        with open(SESSION_FILE, 'r') as f:
            content = f.read().strip()
        
        self.assertEqual(content, test_content)
        
        # Clean up
        os.remove(SESSION_FILE)
        self.assertFalse(os.path.exists(SESSION_FILE))
    
    def test_session_file_permissions(self):
        """Test that session files have appropriate permissions"""
        from backend.client import SESSION_FILE
        
        test_content = "test-player-id-permissions"
        
        # Create session file
        with open(SESSION_FILE, 'w') as f:
            f.write(test_content)
        
        try:
            # Check that file is readable and writable by owner
            stat = os.stat(SESSION_FILE)
            mode = stat.st_mode
            
            # File should be readable and writable by owner
            self.assertTrue(mode & 0o400, "File should be readable by owner")  # Read by owner
            self.assertTrue(mode & 0o200, "File should be writable by owner")  # Write by owner
            
            print(f"✅ Session file permissions: {oct(mode)}")
            
        finally:
            # Clean up
            if os.path.exists(SESSION_FILE):
                os.remove(SESSION_FILE)


async def simulate_client_exit_behavior():
    """Simulate different client exit behaviors"""
    
    print("\n🧪 Simulating client exit behaviors")
    
    from backend.client import SESSION_FILE, clear_session, preserve_session
    
    # Test scenario 1: Normal exit (should preserve session)
    print("\n=== Scenario 1: Normal exit (preserve session) ===")
    
    # Create a session
    test_player_id_1 = "player-normal-exit-123"
    with open(SESSION_FILE, 'w') as f:
        f.write(test_player_id_1)
    
    print(f"📝 Created session with ID: {test_player_id_1[:8]}...")
    
    # Simulate normal exit
    preserve_session()
    
    # Check that session still exists
    if os.path.exists(SESSION_FILE):
        with open(SESSION_FILE, 'r') as f:
            preserved_id = f.read().strip()
        
        if preserved_id == test_player_id_1:
            print("✅ SUCCESS: Session preserved after normal exit")
        else:
            print(f"❌ FAILURE: Session content changed. Expected: {test_player_id_1}, Got: {preserved_id}")
            return False
    else:
        print("❌ FAILURE: Session file was deleted on normal exit")
        return False
    
    # Test scenario 2: Clear session exit
    print("\n=== Scenario 2: Clear session exit ===")
    
    # Session file should still exist from previous test
    print(f"📝 Session file exists: {os.path.exists(SESSION_FILE)}")
    
    # Simulate clear session exit
    clear_session()
    
    # Check that session is gone
    if os.path.exists(SESSION_FILE):
        print("❌ FAILURE: Session file still exists after clear_session")
        return False
    else:
        print("✅ SUCCESS: Session cleared after clear_session exit")
    
    # Test scenario 3: Multiple sessions in different "terminals"
    print("\n=== Scenario 3: Multiple terminal sessions ===")
    
    # Simulate creating multiple session files
    terminal_sessions = [
        ('.player_session_term1', 'player-term1-456'),
        ('.player_session_term2', 'player-term2-789'),
        ('.player_session_term3', 'player-term3-abc')
    ]
    
    created_files = []
    
    for session_file, player_id in terminal_sessions:
        with open(session_file, 'w') as f:
            f.write(player_id)
        created_files.append(session_file)
        print(f"📝 Created {session_file} with ID: {player_id[:8]}...")
    
    # Verify all files exist
    all_exist = all(os.path.exists(f) for f, _ in terminal_sessions)
    
    if all_exist:
        print("✅ SUCCESS: Multiple terminal sessions created")
    else:
        print("❌ FAILURE: Not all terminal sessions were created")
    
    # Clean up
    for session_file in created_files:
        try:
            os.remove(session_file)
        except:
            pass
    
    return True


def main():
    """Main test runner"""
    print("🧪 Session Commands Test Suite")
    print("=" * 50)
    
    # Run unit tests
    print("\n📋 Running unit tests...")
    unittest.main(argv=[''], exit=False, verbosity=2)
    
    # Run simulation tests
    print("\n🎭 Running simulation tests...")
    
    try:
        success = asyncio.run(simulate_client_exit_behavior())
        
        if success:
            print("\n✅ All simulation tests passed!")
            print("🎉 Session command behavior is working correctly")
        else:
            print("\n❌ Some simulation tests failed!")
            print("⚠️  Session command behavior needs debugging")
    
    except Exception as e:
        print(f"\n❌ Simulation test error: {e}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⚠️  Tests interrupted by user")
    except Exception as e:
        print(f"\n❌ Test suite error: {e}")
