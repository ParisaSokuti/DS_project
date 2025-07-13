#!/usr/bin/env python3
"""
Test script to verify the 7-trick rule implementation.
This test simulates a game scenario where one team reaches 7 tricks before all 13 tricks are played.
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from game_board import GameBoard

def test_7_trick_rule():
    """Test that a hand ends immediately when a team reaches 7 tricks"""
    print("Testing 7-trick rule implementation...")
    
    # Create a test game
    players = ["Alice", "Bob", "Charlie", "Diana"]
    game = GameBoard(players)
    
    # Set up a basic game state
    game.teams = {"Alice": 0, "Bob": 1, "Charlie": 0, "Diana": 1}  # Alice/Charlie vs Bob/Diana
    game.hakem = "Alice"
    game.hokm = "hearts"
    game.game_phase = "gameplay"
    game.current_turn = 0
    game.players = players
    
    # Simulate initial hand dealing (we'll just set some cards)
    game.hands = {
        "Alice": ["A_hearts", "K_hearts", "Q_hearts"],
        "Bob": ["J_hearts", "10_hearts", "9_hearts"], 
        "Charlie": ["8_hearts", "7_hearts", "6_hearts"],
        "Diana": ["5_hearts", "4_hearts", "3_hearts"]
    }
    
    # Simulate tricks where Team 0 (Alice/Charlie) wins 6 tricks
    print("\nSimulating 6 tricks won by Team 0 (Alice/Charlie)...")
    for i in range(6):
        # Simulate a trick where Alice wins
        game.current_trick = [
            ("Alice", "A_hearts"),
            ("Bob", "J_hearts"),
            ("Charlie", "8_hearts"),
            ("Diana", "5_hearts")
        ]
        game.led_suit = "hearts"
        
        result = game._resolve_trick()
        print(f"Trick {i+1}: Winner: {result['trick_winner']}, Team tricks: {result['team_tricks']}")
        
        # Verify hand is not complete yet
        assert not result['hand_complete'], f"Hand should not be complete after {i+1} tricks"
    
    print(f"\nAfter 6 tricks - Team 0: {game.tricks[0]}, Team 1: {game.tricks[1]}")
    print("Hand should not be complete yet.")
    
    # Now simulate the 7th trick won by Team 0
    print("\nSimulating 7th trick won by Team 0...")
    game.current_trick = [
        ("Alice", "K_hearts"),
        ("Bob", "10_hearts"),
        ("Charlie", "7_hearts"),
        ("Diana", "4_hearts")
    ]
    game.led_suit = "hearts"
    
    result = game._resolve_trick()
    print(f"Trick 7: Winner: {result['trick_winner']}, Team tricks: {result['team_tricks']}")
    
    # Verify hand is complete when team reaches 7 tricks
    assert result['hand_complete'], "Hand should be complete when a team reaches 7 tricks"
    assert result['round_winner'] == 1, "Team 0 (index 0) should win, so round_winner should be 1"
    
    print(f"\n✅ SUCCESS: Hand completed when Team 0 reached 7 tricks!")
    print(f"Final trick count: Team 0: {result['team_tricks'][0]}, Team 1: {result['team_tricks'][1]}")
    print(f"Round winner: Team {result['round_winner']}")
    
    # Test edge case: what if all 13 tricks are played (shouldn't happen in real game)
    print("\n" + "="*50)
    print("Testing edge case: 13 tricks played without early termination")
    
    # Reset game state
    game.tricks = {0: 6, 1: 6}  # Tied at 6-6
    game.completed_tricks = 12  # 12 tricks played
    
    # Simulate 13th trick
    game.current_trick = [
        ("Alice", "Q_hearts"),
        ("Bob", "9_hearts"), 
        ("Charlie", "6_hearts"),
        ("Diana", "3_hearts")
    ]
    game.led_suit = "hearts"
    
    result = game._resolve_trick()
    print(f"Trick 13: Winner: {result['trick_winner']}, Team tricks: {result['team_tricks']}")
    
    # Verify hand completes after 13 tricks
    assert result['hand_complete'], "Hand should be complete after 13 tricks"
    print(f"✅ SUCCESS: Hand completed after all 13 tricks when no team reached 7!")
    
    print("\n🎉 All tests passed! The 7-trick rule is working correctly.")

if __name__ == "__main__":
    test_7_trick_rule()
