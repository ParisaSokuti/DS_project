#!/usr/bin/env python3
"""
Live Server Failover Demo
Shows server failover during an active game
"""

import subprocess
import sys
import time
import os
import signal

def live_server_failover_demo():
    """
    Step-by-step demonstration of server failover during gameplay
    """
    print("=" * 80)
    print("🎯 LIVE SERVER FAILOVER DURING GAME DEMONSTRATION")
    print("=" * 80)
    
    print("\n🎮 This demo shows how your game continues when a server fails!")
    print("📍 You'll need 8 terminal windows total")
    
    print("\n" + "="*60)
    print("📋 STEP-BY-STEP INSTRUCTIONS")
    print("="*60)
    
    # Phase 1: Infrastructure Setup
    print("\n🏗️  PHASE 1: Setup Infrastructure (3 terminals)")
    print("-" * 50)
    print("Terminal 1 - Load Balancer:")
    print("   cd c:\\Users\\kasra\\hokm_game")
    print("   python backend/load_balancer.py")
    print("   ⏳ Wait for: 'Load Balancer started on port 8760'")
    
    print("\nTerminal 2 - Primary Server:")
    print("   cd c:\\Users\\kasra\\hokm_game")
    print("   python backend/server.py")
    print("   ⏳ Wait for: 'Server running on localhost:8765'")
    
    print("\nTerminal 3 - Secondary Server:")
    print("   cd c:\\Users\\kasra\\hokm_game")
    print("   python backend/server.py --port 8766")
    print("   ⏳ Wait for: 'Server running on localhost:8766'")
    
    input("\n⏸️  Press Enter when all 3 servers are running...")
    
    # Phase 2: Game Setup
    print("\n🎲 PHASE 2: Start Game (4 client terminals)")
    print("-" * 50)
    print("Open 4 more terminals for players:")
    
    for i in range(1, 5):
        print(f"\nTerminal {3+i} - Player {i}:")
        print("   cd c:\\Users\\kasra\\hokm_game")
        print("   python backend/client.py")
        print("   📝 Complete authentication")
        print("   🏠 Join room 9999")
    
    print("\n🃏 Start the game:")
    print("   - Player 1 will be Hakem (select Hokm)")
    print("   - All players play cards normally")
    print("   - Get to at least Round 2 or 3")
    
    input("\n⏸️  Press Enter when the game is actively running with players taking turns...")
    
    # Phase 3: The Failover Test
    print("\n💥 PHASE 3: SIMULATE SERVER FAILURE")
    print("-" * 50)
    print("🚨 NOW FOR THE MAGIC MOMENT!")
    print("\n1. Go to Terminal 2 (Primary Server)")
    print("2. Press Ctrl+C to kill the primary server")
    print("3. Watch what happens:")
    print("   ✅ Load Balancer: Will detect server failure")
    print("   ✅ Clients: Will show 'Connection lost, reconnecting...'")
    print("   ✅ Clients: Will automatically reconnect to secondary server")
    print("   ✅ Game: Will continue exactly where it left off!")
    
    input("\n💀 Press Enter AFTER you've killed the primary server...")
    
    # Phase 4: Verification
    print("\n🔍 PHASE 4: Verify Failover Success")
    print("-" * 50)
    print("Check your client terminals. You should see:")
    print("✅ 'Reconnection successful' or similar messages")
    print("✅ Game continues with the same player hands")
    print("✅ Turn order preserved")
    print("✅ Score unchanged")
    print("✅ All players can continue playing")
    
    print("\n🎯 Test the game:")
    print("- Current player should still be able to play their turn")
    print("- Other players should receive updates")
    print("- Complete a few more rounds to verify everything works")
    
    input("\n⏸️  Press Enter after verifying the game continues normally...")
    
    # Phase 5: Recovery (Optional)
    print("\n🔄 PHASE 5: Server Recovery (Optional)")
    print("-" * 50)
    print("You can optionally restart the primary server:")
    print("\n1. Go to Terminal 2")
    print("2. Run: python backend/server.py")
    print("3. Load balancer will detect it's back online")
    print("4. Future new connections might use the primary server again")
    print("5. Existing game continues on secondary server")
    
    print("\n🎉 DEMONSTRATION COMPLETE!")
    print("="*60)
    print("🏆 You've successfully demonstrated:")
    print("✅ Zero-downtime server failover")
    print("✅ Automatic client reconnection")
    print("✅ Game state preservation")
    print("✅ Seamless user experience")
    print("✅ High availability architecture")
    
    print("\n💡 This works because:")
    print("- Game state is stored in Redis (shared between servers)")
    print("- Load balancer monitors server health")
    print("- Clients have automatic reconnection logic")
    print("- Session persistence maintains player identity")

def quick_start_demo():
    """
    Quick automated start for the demo infrastructure
    """
    print("\n🚀 Quick Start: Auto-launching servers...")
    
    try:
        # Start Load Balancer
        print("Starting Load Balancer...")
        lb_process = subprocess.Popen([
            sys.executable, "backend/load_balancer.py"
        ])
        time.sleep(2)
        
        # Start Primary Server
        print("Starting Primary Server...")
        primary_process = subprocess.Popen([
            sys.executable, "backend/server.py"
        ])
        time.sleep(2)
        
        # Start Secondary Server
        print("Starting Secondary Server...")
        secondary_process = subprocess.Popen([
            sys.executable, "backend/server.py", "--port", "8766"
        ])
        time.sleep(2)
        
        print("✅ All servers started!")
        print("📍 Load Balancer: http://localhost:8760")
        print("📍 Primary Server: http://localhost:8765")
        print("📍 Secondary Server: http://localhost:8766")
        
        print("\n🎮 Now run 4 clients in separate terminals:")
        print("   python backend/client.py")
        
        input("\nPress Enter to stop all servers...")
        
        # Cleanup
        print("Stopping servers...")
        for process in [lb_process, primary_process, secondary_process]:
            if process.poll() is None:
                process.terminate()
        
        print("✅ All servers stopped")
        
    except Exception as e:
        print(f"❌ Error: {e}")

def main():
    """Main menu"""
    while True:
        print("\n" + "="*60)
        print("🎯 SERVER FAILOVER DEMONSTRATION")
        print("="*60)
        print("1. Full Step-by-Step Guide")
        print("2. Quick Start (Auto-launch servers)")
        print("3. Manual Setup Instructions Only")
        print("0. Exit")
        
        choice = input("\nChoose option (0-3): ").strip()
        
        if choice == "1":
            live_server_failover_demo()
        elif choice == "2":
            quick_start_demo()
        elif choice == "3":
            show_manual_setup()
        elif choice == "0":
            print("👋 Goodbye!")
            break
        else:
            print("❌ Invalid choice")

def show_manual_setup():
    """Show manual setup instructions"""
    print("\n📋 MANUAL SETUP INSTRUCTIONS")
    print("="*50)
    
    print("\n🏗️  Infrastructure (3 terminals):")
    print("Terminal 1: python backend/load_balancer.py")
    print("Terminal 2: python backend/server.py")
    print("Terminal 3: python backend/server.py --port 8766")
    
    print("\n🎮 Game Clients (4 terminals):")
    print("Terminal 4-7: python backend/client.py")
    
    print("\n💥 Failover Test:")
    print("1. Start playing the game")
    print("2. Kill Terminal 2 (Ctrl+C)")
    print("3. Watch clients reconnect automatically")
    print("4. Game continues on secondary server!")

if __name__ == "__main__":
    if not os.path.exists("backend/client.py"):
        print("❌ Please run this from the hokm_game directory")
        sys.exit(1)
    
    main()
