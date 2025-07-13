#!/usr/bin/env python3
"""
Demo script to show session persistence in action
This script demonstrates the difference between old and new session behavior
"""

import os
import sys
import time

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def show_session_demo():
    """Demonstrate session persistence"""
    
    print("🎭 Session Persistence Demo")
    print("=" * 50)
    
    # Import the client module to show session handling
    from backend.client import SESSION_FILE, get_terminal_session_id, clear_session, preserve_session
    
    print(f"📁 Your terminal's session file: {SESSION_FILE}")
    print(f"🔍 Session ID function: {get_terminal_session_id()}")
    
    # Check if session exists
    if os.path.exists(SESSION_FILE):
        with open(SESSION_FILE, 'r') as f:
            existing_player_id = f.read().strip()
        
        print(f"\n📋 Existing session found!")
        print(f"   Player ID: {existing_player_id[:8]}...")
        print(f"   Session file: {SESSION_FILE}")
        
        print(f"\n💡 This means when you run the client, you'll reconnect as the same player!")
        
        # Offer to clear session
        choice = input(f"\nDo you want to clear this session? (y/N): ").strip().lower()
        
        if choice in ['y', 'yes']:
            clear_session()
            print(f"🗑️ Session cleared! Next client run will create a new player.")
        else:
            preserve_session()
            print(f"💾 Session preserved! Next client run will reconnect to existing player.")
    
    else:
        print(f"\n📝 No existing session found.")
        print(f"   Next client run will create a new player and save the session.")
        
        # Create a demo session
        demo_choice = input(f"\nCreate a demo session? (y/N): ").strip().lower()
        
        if demo_choice in ['y', 'yes']:
            demo_player_id = f"demo-player-{int(time.time())}"
            
            with open(SESSION_FILE, 'w') as f:
                f.write(demo_player_id)
            
            print(f"✅ Demo session created!")
            print(f"   Player ID: {demo_player_id[:8]}...")
            print(f"   Session file: {SESSION_FILE}")
            print(f"   Next client run will try to reconnect with this ID.")

def show_commands_demo():
    """Show the difference between exit commands"""
    
    print(f"\n🎮 Client Command Demo")
    print("=" * 30)
    
    print(f"In the game client, you now have two exit options:")
    print(f"")
    print(f"1. 'exit' - Exits client but preserves session")
    print(f"   ✅ Session file is kept")
    print(f"   ✅ Next restart will reconnect to same player")
    print(f"   ✅ Perfect for temporary disconnections")
    print(f"")
    print(f"2. 'clear_session' - Exits client and clears session")
    print(f"   🗑️ Session file is deleted")
    print(f"   🆕 Next restart will create a new player")
    print(f"   🔄 Perfect for starting completely fresh")
    print(f"")
    print(f"Old behavior: Always cleared session on exit")
    print(f"New behavior: Preserves session by default, clear only when requested")

def show_terminal_isolation_demo():
    """Show how different terminals get different sessions"""
    
    print(f"\n🖥️ Terminal Isolation Demo")
    print("=" * 35)
    
    from backend.client import get_terminal_session_id
    
    current_session = get_terminal_session_id()
    
    print(f"Your current terminal session: {current_session}")
    print(f"")
    print(f"How it works:")
    print(f"• Each terminal window gets a unique session file")
    print(f"• Based on terminal ID, SSH session, or hostname+username")
    print(f"• Different terminals = different players")
    print(f"• Same terminal = same player across restarts")
    print(f"")
    print(f"Examples:")
    print(f"• Terminal 1: .player_session_abc12345")
    print(f"• Terminal 2: .player_session_def67890")
    print(f"• SSH session: .player_session_ssh98765")
    print(f"")
    print(f"This ensures that:")
    print(f"✅ You can play from multiple terminals simultaneously")
    print(f"✅ Each terminal maintains its own game state")
    print(f"✅ Closing and reopening same terminal reconnects properly")

def main():
    """Main demo runner"""
    
    try:
        show_session_demo()
        show_commands_demo()
        show_terminal_isolation_demo()
        
        print(f"\n🎯 Summary")
        print("=" * 20)
        print(f"The session persistence fix ensures that:")
        print(f"✅ Same terminal = same player across restarts")
        print(f"✅ 'exit' preserves your session")
        print(f"✅ 'clear_session' lets you start fresh")
        print(f"✅ Multiple terminals = multiple players")
        print(f"")
        print(f"Try it out:")
        print(f"1. Run: python -m backend.client")
        print(f"2. Join a game, then type 'exit'")
        print(f"3. Run the client again - you'll reconnect!")
        print(f"4. Use 'clear_session' when you want a fresh start")
        
    except Exception as e:
        print(f"❌ Demo error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
