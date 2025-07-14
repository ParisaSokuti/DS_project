#!/usr/bin/env python3
"""
UI Status Panel Demo
Demonstrates the comprehensive status panel with turn tracking, hokm display, scores, and game info.
"""

import pygame
import time
import threading
import asyncio
from hokm_gui_client import HokmGameGUI

class StatusPanelDemo(HokmGameGUI):
    """Extended game class to demonstrate the status panel features."""
    
    def __init__(self):
        super().__init__()
        self.demo_phase = 0
        
    def start_status_panel_demo(self):
        """Start the status panel demonstration."""
        # Skip directly to playing state
        self.game_state = "playing"
        
        # Initialize game state for demo
        self.player_cards = [
            "A_of_hearts", "K_of_hearts", "Q_of_hearts", "J_of_hearts", "10_of_hearts",
            "9_of_spades", "8_of_spades", "7_of_spades", "6_of_spades", 
            "A_of_diamonds", "K_of_diamonds", "Q_of_clubs", "J_of_clubs"
        ]
        
        # Start with realistic game state
        self.hokm_suit = "hearts"
        self.current_turn_player = "You"
        self.my_turn = True
        self.game_phase = "playing"
        self.trick_number = 0
        self.round_number = 0
        self.scores = {"team1": 3, "team2": 1}
        self.current_message = "Status Panel Demo - Watch the enhanced UI!"
        
        # Start demonstration cycle
        demo_thread = threading.Thread(target=self.demo_status_cycle)
        demo_thread.daemon = True
        demo_thread.start()
        
    def demo_status_cycle(self):
        """Cycle through different game states to show status panel features."""
        time.sleep(3)
        
        # Phase 1: Show turn changes
        self.message_queue.put("DEMO: Demonstrating turn changes...")
        time.sleep(2)
        
        self.current_turn_player = "North Player"
        self.my_turn = False
        self.waiting_for = "North Player"
        self.message_queue.put("Waiting for North Player's move...")
        time.sleep(3)
        
        self.current_turn_player = "East Player"
        self.waiting_for = "East Player"
        self.message_queue.put("Now East Player's turn...")
        time.sleep(3)
        
        # Phase 2: Show hokm selection
        self.message_queue.put("DEMO: Simulating hokm selection...")
        self.game_phase = "hokm_selection"
        self.hokm_selector = "West Player"
        self.hokm_suit = ""
        self.waiting_for = "hokm selection"
        time.sleep(4)
        
        # Select different hokm suits to show icons
        for suit in ["spades", "diamonds", "clubs", "hearts"]:
            self.hokm_suit = suit
            self.message_queue.put(f"DEMO: Hokm changed to {suit.upper()}")
            time.sleep(2)
        
        # Phase 3: Show score updates
        self.message_queue.put("DEMO: Showing score updates...")
        self.game_phase = "playing"
        self.hokm_selector = ""
        self.waiting_for = ""
        
        for i in range(5):
            self.scores["team1"] += 1
            self.trick_number += 1
            self.message_queue.put(f"Team 1 scores! Trick {self.trick_number}")
            time.sleep(2)
            
            self.scores["team2"] += 1
            self.trick_number += 1
            self.message_queue.put(f"Team 2 scores! Trick {self.trick_number}")
            time.sleep(2)
        
        # Phase 4: Show game phases
        self.message_queue.put("DEMO: Showing different game phases...")
        
        phases = [
            ("dealing", "Cards being dealt..."),
            ("playing", "Game in progress"),
            ("trick_complete", "Trick completed"),
            ("waiting", "Waiting for players")
        ]
        
        for phase, msg in phases:
            self.game_phase = phase
            if phase == "trick_complete":
                self.trick_winner = "North Player"
            self.message_queue.put(f"DEMO: {msg}")
            time.sleep(3)
        
        # Phase 5: Show your turn with pulsing effect
        self.message_queue.put("DEMO: Your turn - notice the pulsing effect!")
        self.game_phase = "playing"
        self.current_turn_player = "You"
        self.my_turn = True
        self.waiting_for = ""
        time.sleep(5)
        
        # Restart the cycle
        time.sleep(2)
        self.demo_status_cycle()
    
    def run(self):
        """Override run method to start demo immediately."""
        print("Starting Status Panel Demo...")
        self.calculate_positions()
        self.start_status_panel_demo()
        
        running = True
        while running:
            running = self.handle_events()
            self.update()
            self.draw()
            self.clock.tick(self.fps)
        
        print("Status Panel Demo ended.")
        pygame.quit()

def main():
    """Run the status panel demo."""
    print("\n" + "="*70)
    print("🎮 HOKM GAME - COMPREHENSIVE STATUS PANEL DEMO")
    print("="*70)
    print()
    print("🎯 Features to observe:")
    print("   📍 Turn Status Section:")
    print("      • Current player's turn (with pulsing effect when it's your turn)")
    print("      • Game phase indicators (dealing, hokm selection, playing, etc.)")
    print("      • Waiting status messages")
    print()
    print("   🃏 Hokm (Trump) Section:")
    print("      • Large suit symbol with proper colors")
    print("      • Suit name display")
    print("      • Hearts/Diamonds in red, Clubs/Spades in black")
    print()
    print("   🏆 Team Scores Section:")
    print("      • Current team scores")
    print("      • Leading team highlighted in green")
    print("      • Real-time score updates")
    print()
    print("   📊 Game Info Section:")
    print("      • Current round number")
    print("      • Current trick number")
    print("      • Additional game statistics")
    print()
    print("✨ Visual Enhancements:")
    print("   • Semi-transparent panel background")
    print("   • Color-coded sections for different information types")
    print("   • Pulsing animations for important states")
    print("   • Professional layout with clear visual hierarchy")
    print()
    print("🎮 Demo Sequence:")
    print("   1. Turn changes between players")
    print("   2. Hokm selection demonstration")
    print("   3. Score updates and trick progression")
    print("   4. Different game phase displays")
    print("   5. Your turn highlighting")
    print()
    print("🚀 Starting demo in 3 seconds...")
    print("="*70)
    
    for i in range(3, 0, -1):
        print(f"   {i}...")
        time.sleep(1)
    
    # Run the demo
    demo = StatusPanelDemo()
    demo.run()

if __name__ == "__main__":
    main()
