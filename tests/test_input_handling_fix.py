#!/usr/bin/env python3
"""
Test script to reproduce and verify the fix for the 
"Player not found in room" input handling issue.
"""

import os
import sys
import subprocess
import time
import signal

def cleanup_session_files():
    """Remove any existing session files"""
    for file in os.listdir('.'):
        if file.startswith('.player_session_'):
            try:
                os.remove(file)
                print(f"Removed session file: {file}")
            except:
                pass

def test_connection_error_handling():
    """Test that the connection error input handling works correctly"""
    print("=== Testing Connection Error Input Handling ===")
    
    # Cleanup any existing session files
    cleanup_session_files()
    
    # Create a fake session file to trigger reconnection attempt
    session_file = ".player_session_test123"
    with open(session_file, 'w') as f:
        f.write("fake-player-id-12345")
    
    print(f"Created fake session file: {session_file}")
    print("This should trigger a 'Player not found in room' error when client tries to reconnect")
    print("The client should then properly prompt for user input")
    print("\nStarting client...")
    print("When you see the connection error options, you should be able to type a response.")
    print("Try typing 'clear_session' to test the input handling.")
    
    # Start the client
    try:
        result = subprocess.run([
            sys.executable, "-m", "backend.client"
        ], cwd=".", timeout=30)
    except subprocess.TimeoutExpired:
        print("Client ran for 30 seconds - test completed")
    except KeyboardInterrupt:
        print("Test interrupted by user")
    
    # Cleanup
    try:
        os.remove(session_file)
        print(f"Cleaned up session file: {session_file}")
    except:
        pass

if __name__ == "__main__":
    test_connection_error_handling()
