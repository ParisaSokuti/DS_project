#!/usr/bin/env python3
"""
Simple Fault Tolerance Demonstration Script
Helps you manually test fault tolerance by starting multiple servers
"""

import subprocess
import sys
import time
import os

def print_banner():
    print("🎭 FAULT TOLERANCE DEMONSTRATION GUIDE")
    print("=" * 60)
    print("This guide will help you test fault tolerance manually.")
    print("Follow the steps to see automatic failover in action!")
    print("=" * 60)

def print_instructions():
    print("\n📋 STEP-BY-STEP INSTRUCTIONS:")
    print("\n1️⃣ START THE INFRASTRUCTURE")
    print("   Open 3 separate terminals and run these commands:")
    print("   Terminal 1: python server.py --port 8765 --instance-name primary")
    print("   Terminal 2: python server.py --port 8766 --instance-name secondary") 
    print("   Terminal 3: python load_balancer.py")
    
    print("\n2️⃣ START CLIENTS")
    print("   Open 2 more terminals for clients:")
    print("   Terminal 4: python client.py")
    print("   Terminal 5: python client.py")
    print("   (Clients will connect through load balancer on port 8760)")
    
    print("\n3️⃣ TEST FAULT TOLERANCE")
    print("   a) Let clients authenticate and try to join a game")
    print("   b) In primary server terminal, press Ctrl+C to kill it")
    print("   c) Watch load balancer automatically route to secondary server")
    print("   d) Clients should continue working without interruption!")
    
    print("\n4️⃣ TEST RECOVERY") 
    print("   a) Restart primary server: python server.py --port 8765 --instance-name primary")
    print("   b) Load balancer will detect it's healthy again")
    print("   c) New connections will use primary server")
    
    print("\n📊 MONITORING")
    print("   Watch the terminal outputs to see:")
    print("   - Load balancer health checks")
    print("   - Automatic failover messages")
    print("   - Client reconnection attempts")
    
    print("\n🔍 WHAT TO LOOK FOR:")
    print("   ✅ 'Server primary is now healthy'")
    print("   ❌ 'Server primary marked as unhealthy'") 
    print("   🔄 'Proxying new connection to secondary server'")
    print("   ✅ 'Failover to secondary successful'")

def start_server(port, instance_name):
    """Helper function to start a server"""
    cmd = [
        sys.executable, "server.py",
        "--port", str(port),
        "--instance-name", instance_name,
        "--host", "0.0.0.0"
    ]
    
    print(f"Starting {instance_name} server on port {port}...")
    print(f"Command: {' '.join(cmd)}")
    
    try:
        process = subprocess.Popen(cmd, cwd=".")
        print(f"✅ {instance_name} server started (PID: {process.pid})")
        return process
    except Exception as e:
        print(f"❌ Failed to start {instance_name} server: {e}")
        return None

def start_load_balancer():
    """Helper function to start the load balancer"""
    cmd = [sys.executable, "load_balancer.py"]
    
    print("Starting load balancer...")
    print(f"Command: {' '.join(cmd)}")
    
    try:
        process = subprocess.Popen(cmd, cwd=".")
        print(f"✅ Load balancer started (PID: {process.pid})")
        return process
    except Exception as e:
        print(f"❌ Failed to start load balancer: {e}")
        return None

def main():
    print_banner()
    
    print("\nChoose an option:")
    print("1. Show manual instructions (recommended)")
    print("2. Auto-start all components") 
    print("3. Start individual components")
    
    choice = input("\nEnter choice (1-3): ").strip()
    
    if choice == "1":
        print_instructions()
        print("\n💡 TIP: Copy and paste the commands into separate terminals")
        print("This gives you full control and visibility of the fault tolerance testing!")
        
    elif choice == "2":
        print("\n🚀 Auto-starting all components...")
        
        # Start servers
        primary = start_server(8765, "primary")
        time.sleep(2)
        
        secondary = start_server(8766, "secondary") 
        time.sleep(2)
        
        # Start load balancer
        lb = start_load_balancer()
        time.sleep(3)
        
        if primary and secondary and lb:
            print("\n✅ All components started successfully!")
            print("\nNow open terminals and run clients:")
            print("  python client.py")
            print("\nTo test failover:")
            print("  Kill primary server process (PID: {})".format(primary.pid))
            print("  Watch load balancer route to secondary server")
            
            input("\nPress Enter to stop all components...")
            
            # Cleanup
            print("Stopping components...")
            for proc, name in [(primary, "primary"), (secondary, "secondary"), (lb, "load balancer")]:
                if proc:
                    proc.terminate()
                    print(f"Stopped {name}")
        
    elif choice == "3":
        print("\n🔧 Individual component startup:")
        print("1. Start primary server")
        print("2. Start secondary server") 
        print("3. Start load balancer")
        print("4. Show status commands")
        
        sub_choice = input("Enter choice (1-4): ").strip()
        
        if sub_choice == "1":
            start_server(8765, "primary")
        elif sub_choice == "2":
            start_server(8766, "secondary")
        elif sub_choice == "3":
            start_load_balancer()
        elif sub_choice == "4":
            print("\n📊 Status commands:")
            print("Check processes: netstat -ano | findstr ':8765\\|:8766\\|:8760'")
            print("Check connections: netstat -ano | findstr 'ESTABLISHED'")
    
    else:
        print("Invalid choice")

if __name__ == "__main__":
    main()
