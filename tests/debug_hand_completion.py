#!/usr/bin/env python3
"""
Debug script to investigate the "Hand Complete with 0 tricks" issue
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.game_board import GameBoard

def test_hand_completion_bug():
    """Test to reproduce the hand completion with 0 tricks bug"""
    print("=== Testing Hand Completion Bug ===")
    
    # Create a game
    players = ["Alice", "Bob", "Charlie", "Diana"]
    game = GameBoard(players)
    
    # Set up initial state
    game.assign_teams_and_hakem()
    print(f"Teams: {game.teams}")
    print(f"Hakem: {game.hakem}")
    
    # Deal initial cards
    game.initial_deal()
    
    # Set hokm
    game.set_hokm("hearts")
    
    # Final deal
    game.final_deal()
    
    print(f"Initial tricks: {game.tricks}")
    print(f"Initial completed_tricks: {game.completed_tricks}")
    print(f"Game phase: {game.game_phase}")
    
    # Check if hand_done would be True with current state
    hand_done = (game.tricks[0] >= 7 or game.tricks[1] >= 7 or game.completed_tricks >= 13)
    print(f"Would hand_done be True? {hand_done}")
    
    # Try to simulate the issue by manually checking the condition
    print(f"game.tricks[0] >= 7: {game.tricks[0] >= 7}")
    print(f"game.tricks[1] >= 7: {game.tricks[1] >= 7}")
    print(f"game.completed_tricks >= 13: {game.completed_tricks >= 13}")
    
    # Let's check if there's any scenario where completed_tricks is >= 13 with 0 tricks
    if game.completed_tricks >= 13 and game.tricks[0] == 0 and game.tricks[1] == 0:
        print("🚨 BUG FOUND: completed_tricks >= 13 but both teams have 0 tricks!")
        print(f"completed_tricks: {game.completed_tricks}")
        print(f"tricks: {game.tricks}")
    
    return game

if __name__ == "__main__":
    test_hand_completion_bug()
