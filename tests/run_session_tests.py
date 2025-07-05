#!/usr/bin/env python3
"""
Test runner for all session persistence tests
"""

import os
import sys
import subprocess
import asyncio
import time

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def run_test_file(test_file, description):
    """Run a single test file and return success status"""
    print(f"\n🧪 Running {description}")
    print("=" * 60)
    
    try:
        result = subprocess.run(
            [sys.executable, test_file],
            capture_output=True,
            text=True,
            timeout=60  # 60 second timeout
        )
        
        print(result.stdout)
        if result.stderr:
            print("STDERR:")
            print(result.stderr)
        
        success = result.returncode == 0
        
        if success:
            print(f"✅ {description} - PASSED")
        else:
            print(f"❌ {description} - FAILED (exit code: {result.returncode})")
        
        return success
        
    except subprocess.TimeoutExpired:
        print(f"⏰ {description} - TIMEOUT (60 seconds)")
        return False
    except Exception as e:
        print(f"💥 {description} - ERROR: {e}")
        return False

def check_server_running():
    """Check if the server is running"""
    try:
        result = subprocess.run(['ps', 'aux'], capture_output=True, text=True)
        return 'backend.server' in result.stdout
    except:
        return False

def start_server_if_needed():
    """Start server if it's not running"""
    if not check_server_running():
        print("🚀 Starting server...")
        
        # Start server in background
        server_process = subprocess.Popen(
            [sys.executable, '-m', 'backend.server'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # Wait a moment for server to start
        time.sleep(3)
        
        if server_process.poll() is None:
            print("✅ Server started successfully")
            return server_process
        else:
            print("❌ Failed to start server")
            return None
    else:
        print("✅ Server already running")
        return None

def main():
    """Main test runner"""
    print("🧪 Session Persistence Test Suite")
    print("=" * 60)
    print("This test suite verifies that player sessions persist correctly")
    print("across client restarts in the same terminal window.")
    print("=" * 60)
    
    # Check if we're in the right directory
    if not os.path.exists('backend/client.py'):
        print("❌ Error: Please run this script from the DS_project directory")
        print("   Current directory:", os.getcwd())
        return False
    
    # Start server if needed
    server_process = start_server_if_needed()
    
    # Test files to run
    tests = [
        ('tests/test_session_persistence.py', 'Session Persistence Unit Tests'),
        ('tests/test_terminal_isolation.py', 'Terminal Isolation Tests'),
        ('tests/test_session_commands.py', 'Session Commands Tests'),
        ('tests/test_session_integration.py', 'Session Integration Tests')
    ]
    
    results = []
    
    try:
        for test_file, description in tests:
            if os.path.exists(test_file):
                success = run_test_file(test_file, description)
                results.append((description, success))
            else:
                print(f"⚠️  Test file not found: {test_file}")
                results.append((description, False))
        
        # Print summary
        print(f"\n📊 TEST RESULTS SUMMARY")
        print("=" * 60)
        
        passed = sum(1 for _, success in results if success)
        total = len(results)
        
        for description, success in results:
            status = "✅ PASS" if success else "❌ FAIL"
            print(f"{status} {description}")
        
        print("-" * 60)
        print(f"Total: {passed}/{total} tests passed")
        
        if passed == total:
            print(f"\n🎉 ALL TESTS PASSED!")
            print("Session persistence is working correctly!")
            success_overall = True
        else:
            print(f"\n⚠️  {total - passed} TESTS FAILED!")
            print("Session persistence needs debugging.")
            success_overall = False
    
    finally:
        # Clean up server if we started it
        if server_process:
            print(f"\n🛑 Stopping server...")
            server_process.terminate()
            try:
                server_process.wait(timeout=5)
                print("✅ Server stopped")
            except subprocess.TimeoutExpired:
                server_process.kill()
                print("🔥 Server killed (force)")
    
    return success_overall

if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n⚠️  Tests interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ Test runner error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
