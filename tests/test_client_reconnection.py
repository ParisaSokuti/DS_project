#!/usr/bin/env python3
"""
Test client reconnection using the actual client code
"""

import asyncio
import subprocess
import time
import os
import signal

async def test_client_reconnection():
    print("=== Testing Client Reconnection ===")
    
    # Remove any existing session file
    session_file = '.player_session'
    if os.path.exists(session_file):
        os.remove(session_file)
        print("Removed existing session file")
    
    print("\n1. Starting first client...")
    
    # Start the client as a subprocess
    process1 = subprocess.Popen(
        ['python', '-m', 'backend.client'],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd='/Users/parisasokuti/my git repo/DS_project'
    )
    
    # Give it time to connect and join
    await asyncio.sleep(3)
    
    # Send 'exit' command to quit the client
    print("2. Sending exit command to first client...")
    process1.stdin.write('exit\n')
    process1.stdin.flush()
    
    # Wait for the process to exit
    stdout, stderr = process1.communicate(timeout=10)
    
    print("First client output:")
    print(stdout)
    if stderr:
        print("Errors:")
        print(stderr)
    
    # Check if session file was created
    if os.path.exists(session_file):
        with open(session_file, 'r') as f:
            session_data = f.read().strip()
        print(f"\n3. Session file created with player_id: {session_data}")
    else:
        print("\n❌ No session file created!")
        return False
    
    print("\n4. Waiting 2 seconds then starting second client (should reconnect)...")
    await asyncio.sleep(2)
    
    # Start second client (should use session file to reconnect)
    process2 = subprocess.Popen(
        ['python', '-m', 'backend.client'],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd='/Users/parisasokuti/my git repo/DS_project'
    )
    
    # Give it time to reconnect
    await asyncio.sleep(3)
    
    # Send 'exit' command
    print("5. Sending exit command to second client...")
    process2.stdin.write('exit\n')
    process2.stdin.flush()
    
    # Wait for the process to exit
    stdout2, stderr2 = process2.communicate(timeout=10)
    
    print("Second client output:")
    print(stdout2)
    if stderr2:
        print("Errors:")
        print(stderr2)
    
    # Check if reconnection was successful
    if "Successfully reconnected" in stdout2 or "Found existing session" in stdout2:
        print("\n✅ SUCCESS: Client reconnection is working!")
        return True
    else:
        print("\n❌ FAILED: Client did not reconnect properly")
        return False

async def main():
    try:
        result = await test_client_reconnection()
        exit(0 if result else 1)
    except Exception as e:
        print(f"Test error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)

if __name__ == "__main__":
    asyncio.run(main())
