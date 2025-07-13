#!/usr/bin/env python3
"""
Test Suite Runner for Hokm Game Server

Runs all available tests in the recommended order:
1. Debug test (quick diagnostics)
2. Basic functionality test (complete game flow)
3. Connection reliability test (stress testing)

Usage: python run_all_tests.py
"""

import asyncio
import subprocess
import sys
import time
import os
from typing import Tuple

def run_test(test_script: str, test_name: str) -> Tuple[bool, str]:
    """Run a test script and return success status and output"""
    print(f"\n{'='*60}")
    print(f"🧪 Running {test_name}")
    print(f"{'='*60}")
    
    try:
        start_time = time.time()
        
        # Handle different command types
        if test_script.startswith("pytest"):
            # For pytest commands, split the command
            cmd_parts = test_script.split()
            result = subprocess.run(
                cmd_parts,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout per test
            )
        else:
            # Regular Python script
            cmd_parts = test_script.split()
            if len(cmd_parts) == 1:
                # Single script file
                result = subprocess.run(
                    [sys.executable, test_script],
                    capture_output=True,
                    text=True,
                    timeout=300
                )
            else:
                # Script with arguments
                result = subprocess.run(
                    [sys.executable] + cmd_parts,
                    capture_output=True,
                    text=True,
                    timeout=300
                )
        
        duration = time.time() - start_time
        
        # Print the output
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
            
        success = result.returncode == 0
        
        print(f"\n{'✅ PASSED' if success else '❌ FAILED'} {test_name} ({duration:.1f}s)")
        
        return success, result.stdout + result.stderr
        
    except subprocess.TimeoutExpired:
        print(f"\n⏰ TIMEOUT {test_name} (exceeded 5 minutes)")
        return False, "Test timed out"
    except Exception as e:
        print(f"\n💥 ERROR running {test_name}: {e}")
        return False, str(e)

def check_server_running() -> bool:
    """Check if the server appears to be running"""
    try:
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(('localhost', 8765))
        sock.close()
        return result == 0
    except:
        return False

def main():
    """Run all tests in sequence"""
    print("🎮 HOKM GAME SERVER - COMPLETE TEST SUITE")
    print("="*60)
    print("This will run all available tests:")
    print("  1. Debug Test (Quick diagnostics)")
    print("  2. Natural Flow Test (Complete functionality)")
    print("  3. Connection Reliability Test (Stress testing)")
    print("  4. Redis Data Integrity Test (Data persistence)")
    print("  5. GameBoard Unit Tests (Core game logic)")
    print("  6. Stress Test (Optional - High load testing)")
    print("="*60)
    
    # Check if server is running
    if not check_server_running():
        print("⚠️  WARNING: Server doesn't appear to be running on localhost:8765")
        print("   Make sure to start your server with: python backend/server.py")
        print("   Press Ctrl+C to cancel, or Enter to continue anyway...")
        try:
            input()
        except KeyboardInterrupt:
            print("\nTest cancelled by user.")
            return 1
    
    # Ask about stress testing
    print("\n🤔 Do you want to include the comprehensive stress test?")
    print("   This test simulates 100 concurrent connections and high load.")
    print("   It may take 5-10 minutes and puts significant load on your server.")
    print("   Type 'yes' to include it, or just press Enter to skip:")
    
    try:
        include_stress = input().strip().lower() in ['yes', 'y']
    except KeyboardInterrupt:
        print("\nTest cancelled by user.")
        return 1
    
    # Test scripts to run
    tests = [
        ("test_debug.py", "Debug Test"),
        ("test_natural_flow.py", "Natural Flow Test"),
        ("test_connection_reliability.py", "Connection Reliability Test"),
        ("test_redis_integrity.py", "Redis Data Integrity Test")
    ]
    
    # Add GameBoard unit tests
    if os.path.exists("tests/test_game_board.py"):
        tests.append(("pytest tests/test_game_board.py -v", "GameBoard Unit Tests"))
    
    # Add stress test if requested
    if include_stress:
        if os.path.exists("test_stress.py"):
            tests.append(("test_stress.py --quick", "Stress Test (Quick Mode)"))
        else:
            print("⚠️  Stress test script not found, skipping...")
    
    results = []
    start_time = time.time()
    
    # Run each test
    for test_script, test_name in tests:
        if not os.path.exists(test_script):
            print(f"❌ Test script not found: {test_script}")
            results.append((test_name, False, "Script not found"))
            continue
            
        success, output = run_test(test_script, test_name)
        results.append((test_name, success, output))
        
        # Short pause between tests
        if test_script != tests[-1][0]:  # Not the last test
            print(f"\nPausing 3 seconds before next test...")
            time.sleep(3)
    
    total_duration = time.time() - start_time
    
    # Print final summary
    print("\n" + "="*70)
    print("📊 COMPLETE TEST SUITE SUMMARY")
    print("="*70)
    
    passed_tests = sum(1 for _, success, _ in results if success)
    total_tests = len(results)
    
    print(f"Total Tests Run: {total_tests}")
    print(f"✅ Passed: {passed_tests}")
    print(f"❌ Failed: {total_tests - passed_tests}")
    print(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%")
    print(f"Total Duration: {total_duration:.1f} seconds")
    
    print(f"\nIndividual Test Results:")
    print("-" * 40)
    
    for test_name, success, _ in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {test_name}")
    
    # Overall assessment
    print(f"\n{'='*70}")
    print("🎯 OVERALL SERVER ASSESSMENT")
    print("="*70)
    
    if passed_tests == total_tests:
        print("🎉 EXCELLENT: Your Hokm game server is working perfectly!")
        print("   All functionality and reliability tests passed.")
        print("   Your server is ready for production use.")
    elif passed_tests >= total_tests - 1:
        print("✅ VERY GOOD: Your server is working well with minor issues.")
        print("   Most functionality is working correctly.")
        print("   Address the failing test(s) for optimal performance.")
    elif passed_tests >= total_tests // 2:
        print("⚠️  MODERATE: Your server has partial functionality.")
        print("   Core features may be working but reliability issues exist.")
        print("   Significant improvements recommended before production.")
    else:
        print("❌ NEEDS WORK: Your server has major issues.")
        print("   Multiple core systems are not functioning properly.")
        print("   Extensive debugging and fixes required.")
    
    # Specific recommendations
    failed_tests = [name for name, success, _ in results if not success]
    
    if failed_tests:
        print(f"\nRecommended Actions:")
        if "Debug Test" in failed_tests:
            print("  🔧 Fix basic connectivity and Redis issues first")
        if "Basic Game Test" in failed_tests:
            print("  🔧 Debug core game logic and WebSocket message handling")
        if "Connection Reliability Test" in failed_tests:
            print("  🔧 Improve connection handling and resource management")
    else:
        print(f"\nNext Steps:")
        print("  🚀 Consider testing with real frontend clients")
        print("  🚀 Test with multiple concurrent games")
        print("  🚀 Add monitoring and logging for production")
    
    print("="*70)
    
    # Return appropriate exit code
    return 0 if passed_tests == total_tests else 1

if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\nTest suite interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\nFatal error running test suite: {e}")
        sys.exit(1)
