#!/usr/bin/env python3
"""
Primary machine startup script
Starts both primary server and load balancer
"""
import subprocess
import time
import sys
import os

def start_component(name, command, delay=2):
    """Start a component in a new console window"""
    try:
        print(f"🚀 Starting {name}...")
        
        if sys.platform == "win32":
            # Windows: Start in new console window
            process = subprocess.Popen(
                command,
                creationflags=subprocess.CREATE_NEW_CONSOLE,
                cwd=os.getcwd()
            )
        else:
            # Linux/Mac: Start in background
            process = subprocess.Popen(command, cwd=os.getcwd())
        
        print(f"✅ {name} started (PID: {process.pid})")
        time.sleep(delay)
        return process
    
    except Exception as e:
        print(f"❌ Failed to start {name}: {e}")
        return None

def main():
    print("🎮 Starting Primary Machine Components")
    print("=" * 50)
    print("🖥️  Primary Server + Load Balancer Setup")
    print("🌐 Secondary Server: 192.168.1.92:8765")
    print("=" * 50)
    
    processes = []
    
    try:
        # Start primary server
        primary_cmd = [
            sys.executable, 
            "backend/server.py", 
            "--port", "8765", 
            "--instance-name", "primary"
        ]
        primary_process = start_component("Primary Server", primary_cmd, 3)
        if primary_process:
            processes.append(("Primary Server", primary_process))
        
        # Start load balancer
        lb_cmd = [sys.executable, "backend/load_balancer.py"]
        lb_process = start_component("Load Balancer", lb_cmd, 3)
        if lb_process:
            processes.append(("Load Balancer", lb_process))
        
        # Optional: Start Redis monitor
        monitor_cmd = [sys.executable, "backend/redis_monitor.py"]
        monitor_process = start_component("Redis Monitor", monitor_cmd, 1)
        if monitor_process:
            processes.append(("Redis Monitor", monitor_process))
        
        print("\n✅ All components started!")
        print("📋 Running components:")
        for name, process in processes:
            print(f"   - {name} (PID: {process.pid})")
        
        print("\n🎯 Next steps:")
        print("1. Make sure friend's secondary server is running")
        print("2. Test connectivity: python test_network_connectivity.py")
        print("3. Start clients: python backend/client.py")
        print("4. Test failover by stopping primary server")
        
        print("\n⚠️  Press Ctrl+C to stop all components")
        
        # Keep script running
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n🛑 Stopping all components...")
            
    except Exception as e:
        print(f"❌ Setup failed: {e}")
    
    finally:
        # Clean up processes
        for name, process in processes:
            try:
                print(f"🔪 Stopping {name}...")
                process.terminate()
                process.wait(timeout=5)
            except Exception as e:
                print(f"⚠️  Failed to stop {name}: {e}")
        
        print("✅ Cleanup complete")

if __name__ == "__main__":
    main()
