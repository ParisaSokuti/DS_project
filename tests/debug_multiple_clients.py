#!/usr/bin/env python3
"""
Debug script to test multiple client connections and see reconnection behavior
"""

import subprocess
import time
import os
import signal
import sys

def cleanup_sessions():
    """Remove all existing session files"""
    os.system("rm -f .player_session*")
    print("🧹 Cleaned up all session files")

def start_client(client_id):
    """Start a client process"""
    print(f"🚀 Starting client {client_id}")
    
    # Start client process
    process = subprocess.Popen(
        [sys.executable, "-m", "backend.client"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True
    )
    
    return process

def main():
    print("🔍 Testing multiple client connections")
    
    # Clean up first
    cleanup_sessions()
    
    # Start 4 clients with a small delay between each
    clients = []
    for i in range(4):
        print(f"\n--- Starting Client {i+1} ---")
        client = start_client(i+1)
        clients.append(client)
        time.sleep(2)  # Wait 2 seconds between client starts
        
        # Read initial output from client
        try:
            # Use a timeout to avoid blocking forever
            client.wait(timeout=5)  # Wait up to 5 seconds for client to finish initial connection
        except subprocess.TimeoutExpired:
            # Client is still running, that's expected
            pass
        
        # Check if there's any output
        if client.poll() is None:  # Process is still running
            print(f"✅ Client {i+1} started successfully")
        else:
            print(f"❌ Client {i+1} exited early")
            if client.stdout:
                output = client.stdout.read()
                print(f"Output: {output}")
    
    print(f"\n📊 Started {len(clients)} clients")
    print("📁 Checking session files...")
    
    # List session files
    os.system("ls -la .player_session* 2>/dev/null || echo 'No session files found'")
    
    # Wait a bit more for clients to complete their connection process
    print("\n⏳ Waiting for clients to complete connections...")
    time.sleep(10)
    
    # Terminate all clients
    print("\n🛑 Terminating all clients...")
    for i, client in enumerate(clients):
        try:
            client.terminate()
            client.wait(timeout=3)
            print(f"✅ Client {i+1} terminated")
        except subprocess.TimeoutExpired:
            client.kill()
            print(f"🔥 Client {i+1} killed (force)")
        except Exception as e:
            print(f"❌ Error terminating client {i+1}: {e}")
    
    print("\n📁 Final session files check:")
    os.system("ls -la .player_session* 2>/dev/null || echo 'No session files found'")
    
    # Show unique player IDs
    print("\n🔍 Unique player IDs in session files:")
    os.system("cat .player_session* 2>/dev/null | sort | uniq || echo 'No session files to check'")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⚠️  Interrupted by user")
        # Clean up any remaining processes
        os.system("pkill -f 'python.*backend.client'")
        sys.exit(1)
