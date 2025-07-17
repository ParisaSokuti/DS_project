#!/usr/bin/env python3
"""
Test complete server migration during active gameplay
"""
import asyncio
import subprocess
import time
import psutil
import signal
import os

class CompleteMigrationTest:
    def __init__(self):
        self.processes = []
        self.server_ports = [8765, 8766]
        self.load_balancer_port = 8760
        
    def cleanup_ports(self):
        """Kill any existing processes on our ports"""
        for port in [8760, 8765, 8766]:
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    connections = proc.connections(kind='inet')
                    for conn in connections:
                        if conn.laddr.port == port:
                            print(f"🔧 Killing process {proc.pid} using port {port}")
                            proc.kill()
                            break
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
    
    def start_servers(self):
        """Start primary and secondary servers"""
        print("🚀 Starting primary server on port 8765...")
        primary = subprocess.Popen([
            'python', 'backend/server.py', '--port', '8765', '--instance-name', 'primary'
        ], cwd='.', creationflags=subprocess.CREATE_NEW_CONSOLE)
        self.processes.append(('primary', primary))
        time.sleep(2)
        
        print("🚀 Starting secondary server on port 8766...")
        secondary = subprocess.Popen([
            'python', 'backend/server.py', '--port', '8766', '--instance-name', 'secondary'
        ], cwd='.', creationflags=subprocess.CREATE_NEW_CONSOLE)
        self.processes.append(('secondary', secondary))
        time.sleep(2)
    
    def start_load_balancer(self):
        """Start the load balancer"""
        print("⚖️ Starting load balancer on port 8760...")
        lb = subprocess.Popen([
            'python', 'backend/load_balancer.py'
        ], cwd='.', creationflags=subprocess.CREATE_NEW_CONSOLE)
        self.processes.append(('load_balancer', lb))
        time.sleep(3)
    
    def start_monitoring(self):
        """Start Redis monitoring"""
        print("📊 Starting Redis monitor...")
        monitor = subprocess.Popen([
            'python', 'backend/redis_monitor.py'
        ], cwd='.', creationflags=subprocess.CREATE_NEW_CONSOLE)
        self.processes.append(('monitor', monitor))
        time.sleep(1)
    
    def start_clients(self, num_clients=2):
        """Start test clients"""
        print(f"👥 Starting {num_clients} clients...")
        for i in range(num_clients):
            client = subprocess.Popen([
                'python', 'backend/client.py'
            ], cwd='.', creationflags=subprocess.CREATE_NEW_CONSOLE)
            self.processes.append((f'client_{i+1}', client))
            time.sleep(2)
    
    def kill_primary_server(self):
        """Kill the primary server to test failover"""
        print("\n💥 KILLING PRIMARY SERVER to test failover...")
        for name, proc in self.processes:
            if name == 'primary':
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                print("🔥 Primary server terminated!")
                break
    
    def wait_for_user_input(self):
        """Wait for user to press Enter"""
        input("\n⏳ Press Enter to kill the primary server and test migration...")
    
    def cleanup(self):
        """Clean up all processes"""
        print("\n🧹 Cleaning up processes...")
        for name, proc in self.processes:
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
            except Exception as e:
                print(f"Error cleaning up {name}: {e}")
    
    def run_test(self):
        """Run the complete test"""
        try:
            print("🔄 Starting Complete Migration Test")
            print("=" * 50)
            
            # Cleanup any existing processes
            self.cleanup_ports()
            time.sleep(2)
            
            # Start all components
            self.start_servers()
            self.start_load_balancer()
            self.start_monitoring()
            
            print("\n✅ All server components started!")
            print("📋 Test Instructions:")
            print("1. Start clients manually using: python backend/client.py")
            print("2. Join a room and start playing")
            print("3. When ready, press Enter here to kill primary server")
            print("4. Observe if the game continues on secondary server")
            
            # Wait for user to start game
            self.wait_for_user_input()
            
            # Kill primary server
            self.kill_primary_server()
            
            print("\n🔍 Observing system behavior...")
            print("- Check load balancer logs for migration activity")
            print("- Check Redis monitor for game state persistence")
            print("- Check if clients continue playing on secondary server")
            
            input("\nPress Enter to cleanup and exit...")
            
        except KeyboardInterrupt:
            print("\n⚠️ Test interrupted by user")
        except Exception as e:
            print(f"\n❌ Test failed: {e}")
        finally:
            self.cleanup()

if __name__ == "__main__":
    test = CompleteMigrationTest()
    test.run_test()
