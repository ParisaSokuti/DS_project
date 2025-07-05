#!/usr/bin/env python3
"""
Test to reproduce the exact server-side bug
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.game_board import GameBoard

def test_server_side_bug():
    """Test the exact server-side logic that's causing the bug"""
    print("=== Testing Server-Side Bug ===")
    
    # Create a game and set it up
    players = ["Alice", "Bob", "Charlie", "Diana"]
    game = GameBoard(players)
    game.assign_teams_and_hakem()
    game.initial_deal()
    game.set_hokm("hearts")
    game.final_deal()
    
    print(f"Initial state:")
    print(f"  tricks: {game.tricks}")
    print(f"  completed_tricks: {game.completed_tricks}")
    
    # Simulate playing cards until hand completion
    # Let's manually simulate the conditions that might trigger the bug
    
    # Simulate a scenario where hand is marked complete but tricks are 0
    # This might happen due to state corruption or incorrect logic
    
    # Let's test the _resolve_trick method directly
    print("\n=== Testing _resolve_trick Method ===")
    
    # Set up a trick
    game.current_trick = [
        ("Alice", "A_hearts"),  # Alice plays Ace of hearts
        ("Bob", "K_hearts"),    # Bob plays King of hearts
        ("Charlie", "Q_hearts"), # Charlie plays Queen of hearts  
        ("Diana", "J_hearts")   # Diana plays Jack of hearts
    ]
    game.led_suit = "hearts"
    
    print(f"Before _resolve_trick:")
    print(f"  tricks: {game.tricks}")
    print(f"  completed_tricks: {game.completed_tricks}")
    print(f"  current_trick: {game.current_trick}")
    
    # Call _resolve_trick
    result = game._resolve_trick()
    
    print(f"\nAfter _resolve_trick:")
    print(f"  tricks: {game.tricks}")
    print(f"  completed_tricks: {game.completed_tricks}")
    print(f"  result: {result}")
    
    # Test the server-side logic
    print(f"\n=== Testing Server-Side Logic ===")
    team_tricks = result.get('team_tricks') or {0: 0, 1: 0}
    print(f"result.get('team_tricks'): {result.get('team_tricks')}")
    print(f"team_tricks after server logic: {team_tricks}")
    
    # Check if result['team_tricks'] is falsy
    if not result.get('team_tricks'):
        print("🚨 BUG FOUND: result['team_tricks'] is falsy!")
        print(f"  Type: {type(result.get('team_tricks'))}")
        print(f"  Value: {result.get('team_tricks')}")
        print(f"  Evaluates to False: {not result.get('team_tricks')}")
    
    return result

def test_edge_cases():
    """Test edge cases that might cause team_tricks to be falsy"""
    print("\n=== Testing Edge Cases ===")
    
    # Test what happens with different dict values
    test_cases = [
        {},  # Empty dict
        {0: 0, 1: 0},  # Both teams have 0 tricks
        {0: 1, 1: 0},  # Team 0 has 1 trick
        None,  # None value
    ]
    
    for i, case in enumerate(test_cases):
        print(f"\nTest case {i+1}: {case}")
        result = case or {0: 0, 1: 0}
        print(f"  Result: {result}")
        print(f"  Original is falsy: {not case}")

if __name__ == "__main__":
    test_server_side_bug()
    test_edge_cases()
