#!/usr/bin/env python3
"""
Simple migration test script
"""
import subprocess
import time
import psutil

def kill_process_on_port(port):
    """Kill any process using the specified port"""
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            connections = proc.connections(kind='inet')
            for conn in connections:
                if conn.laddr.port == port:
                    print(f"🔥 Killing process {proc.pid} on port {port}")
                    proc.kill()
                    return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return False

def main():
    print("🧪 Simple Migration Test")
    print("=" * 40)
    
    print("📋 Manual Test Instructions:")
    print("1. Start primary server: python backend/server.py --port 8765 --instance-name primary")
    print("2. Start secondary server: python backend/server.py --port 8766 --instance-name secondary") 
    print("3. Start load balancer: python backend/load_balancer.py")
    print("4. Start clients: python backend/client.py")
    print("5. Join a room and start playing")
    print("6. Press Enter here to kill primary server...")
    
    input("Press Enter to kill primary server and test failover...")
    
    print("💥 Killing primary server on port 8765...")
    killed = kill_process_on_port(8765)
    
    if killed:
        print("✅ Primary server killed!")
        print("🔍 Check load balancer logs for migration activity")
        print("🎮 Check if clients continue playing on secondary server")
    else:
        print("❌ No process found on port 8765")
    
    print("\n📊 Migration test complete!")
    print("- Load balancer should detect failure within 2-4 seconds")
    print("- Clients should receive migration messages")
    print("- Game should continue on secondary server")

if __name__ == "__main__":
    main()
