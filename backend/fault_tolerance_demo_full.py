#!/usr/bin/env python3
"""
Fault Tolerance Demonstration
Shows automatic failover between multiple game servers
"""

import asyncio
import subprocess
import time
import psutil
import signal
import sys
import os
from typing import Dict, List, Optional

class FaultToleranceDemo:
    """
    Demonstrates fault tolerance by:
    1. Starting multiple game servers (primary and secondary)
    2. Starting a load balancer that routes to healthy servers
    3. Simulating server failures to show automatic failover
    4. Starting client connections to show uninterrupted service
    """
    
    def __init__(self):
        self.processes = {}  # name -> subprocess.Popen
        self.server_ports = {
            'primary': 8765,
            'secondary': 8766,
            'load_balancer': 8760
        }
        self.demo_running = True
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
    
    def signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        print(f"\n🛑 Received signal {signum}, shutting down demo...")
        self.demo_running = False
        asyncio.create_task(self.cleanup())
    
    def start_server(self, name: str, port: int) -> bool:
        """Start a game server instance"""
        try:
            print(f"🚀 Starting {name} server on port {port}...")
            
            # Start server process
            cmd = [
                sys.executable, "server.py",
                "--port", str(port),
                "--instance-name", name,
                "--host", "0.0.0.0"
            ]
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=os.path.dirname(os.path.abspath(__file__)),
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            self.processes[name] = process
            
            # Wait a moment to check if process started successfully
            time.sleep(2)
            
            if process.poll() is None:
                print(f"✅ {name.capitalize()} server started successfully (PID: {process.pid})")
                return True
            else:
                print(f"❌ {name.capitalize()} server failed to start")
                return False
                
        except Exception as e:
            print(f"❌ Failed to start {name} server: {e}")
            return False
    
    def start_load_balancer(self) -> bool:
        """Start the load balancer"""
        try:
            print(f"🔧 Starting load balancer on port {self.server_ports['load_balancer']}...")
            
            cmd = [sys.executable, "load_balancer.py"]
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=os.path.dirname(os.path.abspath(__file__)),
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            self.processes['load_balancer'] = process
            
            # Wait a moment to check if process started successfully
            time.sleep(3)
            
            if process.poll() is None:
                print(f"✅ Load balancer started successfully (PID: {process.pid})")
                return True
            else:
                print(f"❌ Load balancer failed to start")
                return False
                
        except Exception as e:
            print(f"❌ Failed to start load balancer: {e}")
            return False
    
    def start_client(self, client_name: str) -> bool:
        """Start a client connection"""
        try:
            print(f"👤 Starting {client_name}...")
            
            cmd = [sys.executable, "client.py"]
            
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=os.path.dirname(os.path.abspath(__file__)),
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            self.processes[client_name] = process
            
            # Wait a moment
            time.sleep(1)
            
            if process.poll() is None:
                print(f"✅ {client_name} started successfully (PID: {process.pid})")
                return True
            else:
                print(f"❌ {client_name} failed to start")
                return False
                
        except Exception as e:
            print(f"❌ Failed to start {client_name}: {e}")
            return False
    
    def kill_server(self, server_name: str):
        """Simulate server failure by killing the process"""
        if server_name in self.processes:
            process = self.processes[server_name]
            if process.poll() is None:  # Process is still running
                print(f"💥 SIMULATING FAILURE: Killing {server_name} server (PID: {process.pid})")
                try:
                    # Force kill the process
                    if sys.platform == "win32":
                        subprocess.call(["taskkill", "/F", "/T", "/PID", str(process.pid)], 
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    else:
                        process.kill()
                    
                    print(f"❌ {server_name.capitalize()} server killed")
                    
                    # Remove from processes
                    del self.processes[server_name]
                    
                except Exception as e:
                    print(f"⚠️ Error killing {server_name}: {e}")
            else:
                print(f"⚠️ {server_name} server is already stopped")
    
    def restart_server(self, server_name: str) -> bool:
        """Restart a failed server"""
        if server_name in ['primary', 'secondary']:
            port = self.server_ports[server_name]
            print(f"🔄 Restarting {server_name} server...")
            return self.start_server(server_name, port)
        return False
    
    def check_process_status(self):
        """Check status of all processes"""
        print("\n📊 Process Status:")
        print("-" * 50)
        
        for name, process in list(self.processes.items()):
            if process.poll() is None:
                print(f"🟢 {name}: Running (PID: {process.pid})")
            else:
                print(f"🔴 {name}: Stopped")
                # Remove dead processes
                del self.processes[name]
        
        print("-" * 50)
    
    def show_connections(self):
        """Show active network connections to our ports"""
        print("\n🌐 Network Connections:")
        print("-" * 50)
        
        try:
            for name, port in self.server_ports.items():
                connections = []
                for conn in psutil.net_connections():
                    if conn.laddr.port == port and conn.status == 'LISTEN':
                        connections.append(f"Listening on {conn.laddr.ip}:{conn.laddr.port}")
                    elif conn.raddr and conn.raddr.port == port:
                        connections.append(f"Client: {conn.laddr.ip}:{conn.laddr.port} -> {conn.raddr.ip}:{conn.raddr.port}")
                
                if connections:
                    print(f"{name} (:{port}):")
                    for conn in connections[:3]:  # Show first 3 connections
                        print(f"  {conn}")
                    if len(connections) > 3:
                        print(f"  ... and {len(connections) - 3} more")
                else:
                    print(f"{name} (:{port}): No connections")
        except Exception as e:
            print(f"Could not check connections: {e}")
        
        print("-" * 50)
    
    async def cleanup(self):
        """Clean up all processes"""
        print("🧹 Cleaning up processes...")
        
        for name, process in list(self.processes.items()):
            try:
                if process.poll() is None:
                    print(f"Stopping {name}...")
                    if sys.platform == "win32":
                        subprocess.call(["taskkill", "/F", "/T", "/PID", str(process.pid)], 
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    else:
                        process.terminate()
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            process.kill()
            except Exception as e:
                print(f"Error stopping {name}: {e}")
        
        self.processes.clear()
        print("✅ Cleanup complete")
    
    async def run_demo(self):
        """Run the complete fault tolerance demonstration"""
        print("🎭 FAULT TOLERANCE DEMONSTRATION")
        print("=" * 60)
        print("This demo will show:")
        print("1. Two game servers running simultaneously")
        print("2. A load balancer routing traffic to healthy servers")
        print("3. Automatic failover when a server fails")
        print("4. Uninterrupted client connections during failover")
        print("=" * 60)
        
        # Step 1: Start servers
        print("\n🚀 STEP 1: Starting backend infrastructure...")
        
        # Start primary server
        if not self.start_server('primary', self.server_ports['primary']):
            print("❌ Failed to start primary server. Aborting demo.")
            return
        
        # Start secondary server
        if not self.start_server('secondary', self.server_ports['secondary']):
            print("⚠️ Secondary server failed to start, continuing with primary only")
        
        # Start load balancer
        if not self.start_load_balancer():
            print("❌ Failed to start load balancer. Aborting demo.")
            await self.cleanup()
            return
        
        print("✅ Infrastructure started successfully!")
        
        # Step 2: Show initial status
        print("\n📊 STEP 2: Initial system status")
        self.check_process_status()
        self.show_connections()
        
        # Step 3: Start clients
        print("\n👥 STEP 3: Starting client connections...")
        self.start_client('client_1')
        time.sleep(2)
        self.start_client('client_2')
        
        print("\n⏰ Waiting 10 seconds for clients to connect...")
        await asyncio.sleep(10)
        
        # Step 4: Show system with clients
        print("\n📊 STEP 4: System status with clients")
        self.check_process_status()
        self.show_connections()
        
        # Step 5: Simulate primary server failure
        print("\n💥 STEP 5: FAULT TOLERANCE TEST - Simulating primary server failure...")
        print("This will demonstrate automatic failover to the secondary server")
        
        input("Press Enter to kill the primary server and test failover...")
        
        self.kill_server('primary')
        
        print("⏰ Waiting 15 seconds for automatic failover...")
        await asyncio.sleep(15)
        
        # Step 6: Show system after failover
        print("\n📊 STEP 6: System status after failover")
        self.check_process_status()
        self.show_connections()
        
        # Step 7: Restart failed server
        print("\n🔄 STEP 7: RECOVERY TEST - Restarting failed primary server...")
        
        input("Press Enter to restart the primary server...")
        
        if self.restart_server('primary'):
            print("⏰ Waiting 10 seconds for server to stabilize...")
            await asyncio.sleep(10)
            
            print("\n📊 System status after recovery:")
            self.check_process_status()
            self.show_connections()
        
        # Step 8: Interactive mode
        print("\n🎮 STEP 8: INTERACTIVE MODE")
        print("Commands available:")
        print("  'fail primary' - Kill primary server")
        print("  'fail secondary' - Kill secondary server")
        print("  'restart primary' - Restart primary server")
        print("  'restart secondary' - Restart secondary server")
        print("  'status' - Show process status")
        print("  'connections' - Show network connections")
        print("  'quit' - Exit demo")
        
        while self.demo_running:
            try:
                command = input("\nEnter command (or 'quit'): ").strip().lower()
                
                if command == 'quit':
                    break
                elif command == 'fail primary':
                    self.kill_server('primary')
                elif command == 'fail secondary':
                    self.kill_server('secondary')
                elif command == 'restart primary':
                    self.restart_server('primary')
                elif command == 'restart secondary':
                    self.restart_server('secondary')
                elif command == 'status':
                    self.check_process_status()
                elif command == 'connections':
                    self.show_connections()
                else:
                    print("Unknown command. Available: fail primary/secondary, restart primary/secondary, status, connections, quit")
                
            except (EOFError, KeyboardInterrupt):
                break
        
        # Cleanup
        await self.cleanup()
        print("\n🎉 Fault tolerance demonstration complete!")

async def main():
    """Main function"""
    demo = FaultToleranceDemo()
    
    try:
        await demo.run_demo()
    except KeyboardInterrupt:
        print("\nDemo interrupted")
    finally:
        await demo.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
