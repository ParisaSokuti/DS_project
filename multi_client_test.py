#!/usr/bin/env python3
"""
Multi-Client Reconnection Test

This script runs multiple clients simultaneously to test reconnection during gameplay.
"""

import asyncio
import subprocess
import sys
import time
import os
import signal
import json

async def run_client(client_name, delay=0):
    """Run a client with optional delay"""
    if delay > 0:
        await asyncio.sleep(delay)
    
    print(f"🚀 Starting {client_name}...")
    
    # Start client process
    process = await asyncio.create_subprocess_exec(
        sys.executable, 
        "debug_client_reconnection.py", 
        client_name,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd="/Users/parisasokuti/Desktop/hokm_game_final"
    )
    
    # Wait for process to complete
    stdout, stderr = await process.communicate()
    
    result = {
        'name': client_name,
        'return_code': process.returncode,
        'stdout': stdout.decode('utf-8'),
        'stderr': stderr.decode('utf-8')
    }
    
    print(f"📋 {client_name} completed with code {process.returncode}")
    return result

async def run_multiple_clients():
    """Run multiple clients to test reconnection"""
    print("🎮 Starting Multi-Client Reconnection Test")
    print("=" * 50)
    
    # Start 4 clients with slight delays
    tasks = [
        run_client("Player1", 0),
        run_client("Player2", 2),
        run_client("Player3", 4),
        run_client("Player4", 6)
    ]
    
    # Wait for all clients to complete
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    print("\n" + "=" * 50)
    print("🔍 MULTI-CLIENT TEST RESULTS")
    print("=" * 50)
    
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            print(f"❌ Client {i+1} failed with exception: {result}")
        else:
            client_name = result['name']
            success = result['return_code'] == 0
            status = "✅ SUCCESS" if success else "❌ FAILED"
            print(f"{status} - {client_name}")
            
            if not success:
                print(f"  Error output: {result['stderr']}")
                # Show last few lines of stdout for debugging
                lines = result['stdout'].split('\n')
                for line in lines[-5:]:
                    if line.strip():
                        print(f"  {line}")
    
    # Save detailed results
    with open('multi_client_test_results.json', 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n💾 Detailed results saved to multi_client_test_results.json")

async def main():
    try:
        await run_multiple_clients()
    except KeyboardInterrupt:
        print("\n❌ Test interrupted by user")
        return 1
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n❌ Interrupted")
        sys.exit(1)
