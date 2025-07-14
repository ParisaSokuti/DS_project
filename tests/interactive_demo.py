#!/usr/bin/env python3
"""
Interactive Demo: Card Interaction Features
Demonstrates all the enhanced mouse and drag-and-drop features.
"""

import pygame
import time
import threading
from hokm_gui_client import HokmGameGUI

class InteractiveDemo(HokmGameGUI):
    """Extended game class for demonstrating interaction features."""
    
    def __init__(self):
        super().__init__()
        self.demo_phase = 0
        self.demo_start_time = 0
        
    def start_interactive_demo(self):
        """Start the interactive demonstration."""
        # Skip directly to playing state
        self.game_state = "playing"
        
        # Give player some cards to interact with
        self.player_cards = [
            "A_of_hearts", "K_of_hearts", "Q_of_hearts", "J_of_hearts", "10_of_hearts",
            "9_of_spades", "8_of_spades", "7_of_spades", "6_of_spades", 
            "A_of_diamonds", "K_of_diamonds", "Q_of_clubs", "J_of_clubs"
        ]
        
        self.hokm_suit = "hearts"
        self.my_turn = True
        self.current_message = "Try the new interaction features! Hover, click, and drag cards!"
        
        # Start demonstration thread
        demo_thread = threading.Thread(target=self.demo_guidance)
        demo_thread.daemon = True
        demo_thread.start()
        
    def demo_guidance(self):
        """Provide guided demonstration."""
        time.sleep(3)
        self.message_queue.put("DEMO: Try hovering your mouse over the cards...")
        
        time.sleep(5)
        self.message_queue.put("DEMO: Click on a card to select it (see the pulsing highlight)")
        
        time.sleep(5)  
        self.message_queue.put("DEMO: Now try dragging a card to the center table!")
        
        time.sleep(5)
        self.message_queue.put("DEMO: Use ESC to cancel drag, arrow keys to navigate!")
        
        time.sleep(5)
        self.message_queue.put("DEMO: Drop cards on the center table to play them!")
        
        # Repeat the cycle
        time.sleep(10)
        self.demo_guidance()
    
    def run(self):
        """Override run method to start demo immediately."""
        print("Starting Interactive Card Demo...")
        self.calculate_positions()
        self.start_interactive_demo()
        
        running = True
        while running:
            running = self.handle_events()
            self.update()
            self.draw()
            self.clock.tick(self.fps)
        
        print("Demo ended.")
        pygame.quit()

def main():
    """Run the interactive demo."""
    print("\n" + "="*60)
    print("🎮 INTERACTIVE CARD GAME DEMO")
    print("="*60)
    print()
    print("🎯 Features to try:")
    print("   • Hover effects - Move mouse over cards")
    print("   • Card selection - Click to select cards") 
    print("   • Drag and drop - Drag cards to center table")
    print("   • Visual feedback - Watch for highlights and animations")
    print("   • Keyboard controls - Arrow keys + SPACE")
    print("   • ESC to cancel drags")
    print()
    print("✨ What to look for:")
    print("   • Cards rise when hovered")
    print("   • Selected cards pulse with yellow highlight")
    print("   • Dragged cards show shadows and transparency")
    print("   • Drop zones glow green when dragging")
    print("   • Ghost outlines show original card positions")
    print()
    print("🚀 Starting demo in 3 seconds...")
    print("="*60)
    
    for i in range(3, 0, -1):
        print(f"   {i}...")
        time.sleep(1)
    
    # Run the demo
    demo = InteractiveDemo()
    demo.run()

if __name__ == "__main__":
    main()
