#!/usr/bin/env python3
"""
Interactive test to verify reconnection behavior
"""

import subprocess
import sys
import time
import os
import signal

def run_client():
    """Run a single client"""
    process = subprocess.Popen(
        [sys.executable, "-m", "backend.client"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )
    return process

def main():
    print("🧪 Interactive Reconnection Test")
    print("This will help you manually verify the reconnection behavior")
    
    print("\n1. First, let's clean up any existing sessions:")
    os.system("rm -f .player_session*")
    print("✅ Session files cleaned")
    
    print("\n2. Starting Client 1...")
    client1 = run_client()
    time.sleep(3)  # Give time to connect
    
    # Check if client is still running
    if client1.poll() is None:
        print("✅ Client 1 is running")
        
        # Read output
        try:
            output, _ = client1.communicate(timeout=2)
            print(f"Client 1 output:\n{output}")
        except subprocess.TimeoutExpired:
            print("Client 1 is still running (no output yet)")
            client1.kill()
            output, _ = client1.communicate()
            print(f"Client 1 output:\n{output}")
    else:
        output, _ = client1.communicate()
        print(f"Client 1 output:\n{output}")
    
    print(f"\n3. Check session files:")
    os.system("ls -la .player_session*")
    
    print(f"\n4. Now start Client 2 (should get different player slot)...")
    client2 = run_client()
    time.sleep(3)
    
    if client2.poll() is None:
        print("✅ Client 2 is running")
        try:
            output, _ = client2.communicate(timeout=2)
            print(f"Client 2 output:\n{output}")
        except subprocess.TimeoutExpired:
            print("Client 2 is still running")
            client2.kill()
            output, _ = client2.communicate()
            print(f"Client 2 output:\n{output}")
    else:
        output, _ = client2.communicate()
        print(f"Client 2 output:\n{output}")
    
    print(f"\n5. Final session files:")
    os.system("ls -la .player_session*")
    
    print(f"\n6. Unique player IDs:")
    os.system("cat .player_session* | sort | uniq -c")

if __name__ == "__main__":
    main()
