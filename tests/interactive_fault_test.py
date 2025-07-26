#!/usr/bin/env python3
"""
Interactive Fault Tolerance Demo
Tests the actual game client with simulated inputs
"""

import subprocess
import sys
import time
import threading
import os
import signal
import psutil

PYTHON_PATH = "C:/Users/kasra/DS_project/.venv_new/Scripts/python.exe"
CLIENT_PATH = "backend/client.py"

class InteractiveFaultTolerance:
    def __init__(self):
        self.processes = []
        
    def run_client_with_input(self, inputs, client_name="TestClient"):
        """Run a client with predefined inputs"""
        print(f"🚀 Starting {client_name}...")
        
        try:
            # Start the client process
            process = subprocess.Popen(
                [PYTHON_PATH, CLIENT_PATH],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=os.getcwd(),
                bufsize=1
            )
            
            self.processes.append(process)
            
            # Send inputs
            for input_text in inputs:
                print(f"📤 {client_name} input: {input_text}")
                process.stdin.write(input_text + "\n")
                process.stdin.flush()
                time.sleep(1)  # Wait between inputs
                
            # Read some output
            time.sleep(2)
            try:
                stdout, stderr = process.communicate(timeout=5)
                print(f"📋 {client_name} output:")
                print(stdout[:500] + "..." if len(stdout) > 500 else stdout)
                if stderr:
                    print(f"📋 {client_name} errors:")
                    print(stderr[:200] + "..." if len(stderr) > 200 else stderr)
            except subprocess.TimeoutExpired:
                print(f"⏰ {client_name} process still running...")
                
        except Exception as e:
            print(f"❌ Error running {client_name}: {e}")
            
    def test_client_startup_and_auth(self):
        """Test client startup and authentication"""
        print("\n" + "="*60)
        print("🧪 TEST: Client Startup and Authentication")
        print("="*60)
        
        # Test registration
        print("🔐 Testing user registration...")
        registration_inputs = [
            "2",  # Register
            f"test_user_{int(time.time())}",  # Username
            "test123",  # Password
            "test@example.com"  # Email
        ]
        
        self.run_client_with_input(registration_inputs, "RegistrationClient")
        
    def test_multiple_clients(self):
        """Test multiple clients connecting"""
        print("\n" + "="*60)
        print("🧪 TEST: Multiple Client Connections")
        print("="*60)
        
        # Start multiple clients with different usernames
        for i in range(3):
            inputs = [
                "2",  # Register
                f"player_{i}_{int(time.time())}",  # Username
                "test123",  # Password  
                f"player{i}@example.com"  # Email
            ]
            
            # Start client in background thread
            threading.Thread(
                target=self.run_client_with_input,
                args=(inputs, f"Client{i+1}"),
                daemon=True
            ).start()
            
            time.sleep(2)  # Stagger client starts
            
        print("⏰ Waiting for clients to connect...")
        time.sleep(10)
        
    def test_client_interruption(self):
        """Test client connection interruption"""
        print("\n" + "="*60)
        print("🧪 TEST: Client Connection Interruption")
        print("="*60)
        
        print("🔌 Starting client that will be interrupted...")
        
        # Start a client
        process = subprocess.Popen(
            [PYTHON_PATH, CLIENT_PATH],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=os.getcwd()
        )
        
        try:
            # Send some inputs
            process.stdin.write("2\n")  # Register
            process.stdin.write(f"interrupt_test_{int(time.time())}\n")  # Username
            process.stdin.flush()
            
            time.sleep(3)  # Let it start
            
            print("💥 Simulating client interruption...")
            process.terminate()  # Interrupt the client
            
            time.sleep(2)
            
            print("🔄 Testing if server handled disconnection gracefully...")
            # Start another client to see if server is still responsive
            recovery_inputs = [
                "2",  # Register
                f"recovery_test_{int(time.time())}",  # Username
                "test123",  # Password
                "recovery@example.com"  # Email
            ]
            
            self.run_client_with_input(recovery_inputs, "RecoveryClient")
            
        except Exception as e:
            print(f"❌ Error in interruption test: {e}")
        finally:
            if process.poll() is None:
                process.kill()
                
    def test_server_stress(self):
        """Test server under stress"""
        print("\n" + "="*60)
        print("🧪 TEST: Server Stress Test")
        print("="*60)
        
        print("⚡ Starting rapid client connections...")
        
        # Start many clients rapidly
        threads = []
        for i in range(5):
            inputs = [
                "2",  # Register
                f"stress_user_{i}_{int(time.time())}",  # Username
                "test123",  # Password
                f"stress{i}@example.com"  # Email
            ]
            
            thread = threading.Thread(
                target=self.run_client_with_input,
                args=(inputs, f"StressClient{i}"),
                daemon=True
            )
            threads.append(thread)
            thread.start()
            
            time.sleep(0.5)  # Very short delay between clients
            
        print("⏰ Waiting for stress test to complete...")
        time.sleep(15)
        
        # Wait for all threads
        for thread in threads:
            thread.join(timeout=5)
            
    def cleanup_processes(self):
        """Clean up any running processes"""
        print("\n🧹 Cleaning up processes...")
        
        for process in self.processes:
            try:
                if process.poll() is None:
                    process.terminate()
                    time.sleep(1)
                    if process.poll() is None:
                        process.kill()
            except Exception as e:
                print(f"⚠️  Error cleaning up process: {e}")
                
        # Also clean up any remaining Python processes running the client
        try:
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    if 'client.py' in ' '.join(proc.info['cmdline'] or []):
                        print(f"🧹 Terminating client process {proc.info['pid']}")
                        proc.terminate()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        except Exception as e:
            print(f"⚠️  Error in process cleanup: {e}")
            
    def run_all_tests(self):
        """Run all interactive fault tolerance tests"""
        print("🚀 Starting Interactive Fault Tolerance Tests")
        print("="*60)
        
        tests = [
            ("Client Startup & Auth", self.test_client_startup_and_auth),
            ("Multiple Clients", self.test_multiple_clients),  
            ("Client Interruption", self.test_client_interruption),
            ("Server Stress", self.test_server_stress),
        ]
        
        try:
            for test_name, test_func in tests:
                print(f"\n🔍 Running: {test_name}")
                start_time = time.time()
                
                try:
                    test_func()
                    duration = time.time() - start_time
                    print(f"✅ {test_name} completed in {duration:.2f}s")
                except Exception as e:
                    duration = time.time() - start_time
                    print(f"❌ {test_name} failed after {duration:.2f}s: {e}")
                    
                print("⏸️  Pausing between tests...")
                time.sleep(3)
                
        finally:
            self.cleanup_processes()
            
        print("\n🎯 Interactive fault tolerance testing completed!")
        print("📊 Check the outputs above to assess server resilience")

def main():
    print("🎮 Interactive Fault Tolerance Testing for Hokm Game Server")
    print("This will test real client connections and failure scenarios")
    print("="*60)
    
    # Check if server is running
    try:
        import websockets
        import asyncio
        
        async def check_server():
            async with websockets.connect("ws://localhost:8765", open_timeout=3) as ws:
                return True
                
        result = asyncio.run(check_server())
        if result:
            print("✅ Server is running and accessible")
        else:
            print("❌ Server check failed")
            return
            
    except Exception as e:
        print(f"❌ Cannot connect to server: {e}")
        print("Make sure the server is running: python backend/server.py")
        return
        
    # Run tests
    tester = InteractiveFaultTolerance()
    
    try:
        tester.run_all_tests()
    except KeyboardInterrupt:
        print("\n🛑 Testing interrupted by user")
        tester.cleanup_processes()
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        tester.cleanup_processes()

if __name__ == "__main__":
    main()
