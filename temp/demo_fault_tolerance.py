#!/usr/bin/env python3
"""
Fault Tolerance Demonstration Script
Shows how to test various fault tolerance scenarios with the Hokm game client
"""

import subprocess
import sys
import time
import os
import signal
import threading

def demo_session_persistence():
    """
    Demonstrates session persistence and reconnection
    """
    print("\n" + "="*60)
    print("🔄 DEMO: Session Persistence and Reconnection")
    print("="*60)
    
    print("1. Start client.py normally and join a game")
    print("2. Note your player ID and session file")
    print("3. Force close the client (Ctrl+C)")
    print("4. Restart client.py - it should reconnect to the same game")
    print("\nTo test this:")
    print("- Run: python backend/client.py")
    print("- After authentication, note the session file path")
    print("- Press Ctrl+C to disconnect")
    print("- Run: python backend/client.py again")
    print("- Observe automatic reconnection attempt")

def demo_authentication_fallback():
    """
    Demonstrates authentication fallback mechanisms
    """
    print("\n" + "="*60)
    print("🔐 DEMO: Authentication Fallback")
    print("="*60)
    
    print("1. The system automatically falls back to simple auth if database fails")
    print("2. Re-authentication happens automatically when tokens expire")
    print("\nTo test this:")
    print("- Stop the database service temporarily")
    print("- Run: python backend/client.py")
    print("- Observe fallback to simple authentication")
    print("- Restart database service")
    print("- Try connecting again - should use database auth")

def demo_server_resilience():
    """
    Demonstrates server-side resilience features
    """
    print("\n" + "="*60)
    print("🛡️ DEMO: Server Resilience")
    print("="*60)
    
    print("1. Multiple client disconnection handling")
    print("2. Game state preservation during temporary issues")
    print("3. Redis circuit breaker activation")
    print("\nTo test this:")
    print("- Start 4 clients and begin a game")
    print("- Disconnect 2 clients (Ctrl+C)")
    print("- Observe server keeps game alive for reconnection")
    print("- Reconnect the clients within timeout period")
    print("- Game should resume normally")

def demo_data_sync_resilience():
    """
    Demonstrates data synchronization fault tolerance
    """
    print("\n" + "="*60)
    print("💾 DEMO: Data Synchronization Resilience")
    print("="*60)
    
    print("1. Game moves are queued with retry mechanisms")
    print("2. Failed operations go to dead letter queue")
    print("3. Multiple priority levels ensure critical data is synced first")
    print("\nTo test this:")
    print("- Play a complete game while monitoring logs")
    print("- Temporarily stop Redis/PostgreSQL")
    print("- Continue playing - moves should be queued")
    print("- Restart services - queued operations should process")

def demo_server_failover():
    """
    Demonstrates server failover during an active game
    """
    print("\n" + "="*80)
    print("🔄 DEMO: Live Server Failover During Game")
    print("="*80)
    
    print("This demonstration shows how the game continues when the primary server fails!")
    print("\n📋 STEP-BY-STEP GUIDE:")
    print("="*50)
    
    print("\n🚀 PHASE 1: Setup High Availability Infrastructure")
    print("1. Open 4 terminal windows")
    print("2. Terminal 1: Start Enhanced Load Balancer")
    print("   Command: python backend/enhanced_load_balancer.py")
    print("3. Terminal 2: Start Primary Server")
    print("   Command: python backend/server.py --port 8765 --instance-name primary")
    print("4. Terminal 3: Start Secondary Server")
    print("   Command: python backend/server.py --port 8766 --instance-name secondary")
    print("5. Terminal 4: Keep this for monitoring")
    
    print("\n🎮 PHASE 2: Start Game Session")
    print("6. Open 4 more terminals for game clients")
    print("7. In each client terminal, run:")
    print("   Command: python backend/client.py")
    print("8. All clients should connect through load balancer (port 8760)")
    print("9. Complete authentication and join room 9999")
    print("10. Start playing the game (select Hokm, play cards)")
    
    print("\n💥 PHASE 3: Simulate Server Failure (During Game!)")
    print("11. While players are actively playing...")
    print("12. Go to Primary Server terminal (Terminal 2)")
    print("13. Press Ctrl+C to kill the primary server")
    print("14. Watch the magic happen:")
    print("    - Load balancer detects failure")
    print("    - Clients automatically reconnect to secondary server")
    print("    - Game state is preserved via Redis")
    print("    - Game continues seamlessly!")
    
    print("\n🔄 PHASE 4: Observe Recovery")
    print("15. Check client terminals - should show reconnection messages")
    print("16. Game should continue on secondary server")
    print("17. Optionally restart primary server:")
    print("    Command: python backend/server.py --port 8765")
    print("18. Load balancer will detect it's back online")
    
    print("\n🎯 What You'll See:")
    print("✅ Clients: 'Reconnecting...', 'Connection restored'")
    print("✅ Load Balancer: 'Server primary unhealthy', 'Routing to secondary'")
    print("✅ Secondary Server: 'New connections accepted'")
    print("✅ Game: Continues without losing state!")
    
    choice = input("\n🚀 Ready to start the demo? (y/N): ").strip().lower()
    if choice == 'y':
        start_server_failover_demo()
    else:
        print("💡 Tip: You can run each step manually following the guide above!")

def start_server_failover_demo():
    """
    Automatically start the server failover demonstration
    """
    print("\n🚀 Starting automated server failover demo...")
    
    servers = {}
    
    try:
        # Start Load Balancer
        print("\n1️⃣ Starting Enhanced Load Balancer on port 8760...")
        servers['load_balancer'] = subprocess.Popen([
            sys.executable, "backend/enhanced_load_balancer.py"
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        time.sleep(3)
        print("✅ Load Balancer started")
        
        # Start Primary Server
        print("\n2️⃣ Starting Primary Server on port 8765...")
        servers['primary'] = subprocess.Popen([
            sys.executable, "backend/server.py", "--port", "8765"
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        time.sleep(3)
        print("✅ Primary Server started")
        
        # Start Secondary Server
        print("\n3️⃣ Starting Secondary Server on port 8766...")
        servers['secondary'] = subprocess.Popen([
            sys.executable, "backend/server.py", "--port", "8766"
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        time.sleep(3)
        print("✅ Secondary Server started")
        
        print("\n🎮 Infrastructure is ready!")
        print("📍 Load Balancer: ws://localhost:8760")
        print("📍 Primary Server: ws://localhost:8765")
        print("📍 Secondary Server: ws://localhost:8766")
        
        print("\n🎯 Now open multiple terminals and run:")
        print("   python backend/client.py")
        print("   (Clients will connect through load balancer)")
        
        input("\n⏸️  Press Enter when you have players connected and playing...")
        
        # Simulate primary server failure
        print("\n💥 SIMULATING PRIMARY SERVER FAILURE...")
        servers['primary'].terminate()
        print("🔥 Primary server terminated!")
        
        print("\n👀 Watch your client terminals - they should:")
        print("   1. Detect disconnection")
        print("   2. Automatically reconnect via load balancer")
        print("   3. Continue game on secondary server")
        
        time.sleep(10)
        
        print("\n🔄 Optionally restarting primary server...")
        servers['primary'] = subprocess.Popen([
            sys.executable, "backend/server.py", "--port", "8765"
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print("✅ Primary server restarted - load balancer will detect it")
        
        input("\n⏸️  Press Enter to shut down demo servers...")
        
    except Exception as e:
        print(f"❌ Demo failed: {e}")
    finally:
        # Cleanup
        print("\n🧹 Cleaning up servers...")
        for name, process in servers.items():
            if process and process.poll() is None:
                process.terminate()
                print(f"   Stopped {name}")
        print("✅ Cleanup complete")

def run_automated_fault_test():
    """
    Run an automated fault tolerance test
    """
    print("\n" + "="*60)
    print("🤖 AUTOMATED FAULT TOLERANCE TEST")
    print("="*60)
    
    try:
        # Run the enhanced fault tolerance test
        print("Starting automated fault tolerance test...")
        result = subprocess.run([
            sys.executable, "enhanced_fault_tolerance_test.py"
        ], capture_output=True, text=True, timeout=120)
        
        print("Test Output:")
        print(result.stdout)
        if result.stderr:
            print("Test Errors:")
            print(result.stderr)
            
    except subprocess.TimeoutExpired:
        print("⏰ Test timed out - this may indicate server issues")
    except FileNotFoundError:
        print("❌ Test file not found. Running basic connection test instead...")
        basic_connection_test()
    except Exception as e:
        print(f"❌ Test failed: {e}")

def basic_connection_test():
    """
    Basic connection test when advanced tests aren't available
    """
    print("Running basic connection test...")
    
    # Start a simple client connection test
    try:
        result = subprocess.run([
            sys.executable, "backend/client.py"
        ], input="exit\n", capture_output=True, text=True, timeout=30)
        
        if "Connected to server" in result.stdout or "Authentication" in result.stdout:
            print("✅ Basic connection test passed")
        else:
            print("⚠️ Connection test completed but may have issues")
            
    except Exception as e:
        print(f"❌ Basic connection test failed: {e}")

def interactive_demo_menu():
    """
    Interactive menu for fault tolerance demonstrations
    """
    print("\n" + "="*80)
    print("🎯 HOKM GAME FAULT TOLERANCE DEMONSTRATION")
    print("="*80)
    
    while True:
        print("\nSelect a fault tolerance scenario to demonstrate:")
        print("1. Session Persistence and Reconnection")
        print("2. Authentication Fallback Mechanisms")
        print("3. Server Resilience Features")
        print("4. Data Synchronization Resilience")
        print("5. Live Server Failover During Game")
        print("6. Run Automated Fault Test")
        print("7. Start Normal Game Client")
        print("0. Exit")
        
        choice = input("\nEnter your choice (0-7): ").strip()
        
        if choice == "1":
            demo_session_persistence()
        elif choice == "2":
            demo_authentication_fallback()
        elif choice == "3":
            demo_server_resilience()
        elif choice == "4":
            demo_data_sync_resilience()
        elif choice == "5":
            demo_server_failover()
        elif choice == "6":
            run_automated_fault_test()
        elif choice == "7":
            print("\n🎮 Starting normal game client...")
            print("Run: python backend/client.py")
            break
        elif choice == "0":
            print("👋 Goodbye!")
            break
        else:
            print("❌ Invalid choice. Please enter 0-7.")

def show_fault_tolerance_tips():
    """
    Show tips for observing fault tolerance in action
    """
    print("\n" + "="*60)
    print("💡 TIPS FOR OBSERVING FAULT TOLERANCE")
    print("="*60)
    
    tips = [
        "Monitor terminal output for reconnection messages",
        "Check session files in the game directory",
        "Observe circuit breaker state changes in logs",
        "Watch for retry attempts and exponential backoff",
        "Notice graceful degradation when services are unavailable",
        "See data synchronization queues handling failures",
        "Test multiple simultaneous disconnections and reconnections"
    ]
    
    for i, tip in enumerate(tips, 1):
        print(f"{i}. {tip}")

if __name__ == "__main__":
    print("🛡️ Hokm Game Fault Tolerance Demonstration")
    
    # Check if game files exist
    if not os.path.exists("backend/client.py"):
        print("❌ client.py not found. Please run this from the game root directory.")
        sys.exit(1)
    
    show_fault_tolerance_tips()
    interactive_demo_menu()
