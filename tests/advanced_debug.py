#!/usr/bin/env python3
"""
Advanced debug script to test Redis state restoration and hand completion logic
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.game_board import GameBoard
import json

def test_redis_state_bug():
    """Test if the bug occurs during Redis state restoration"""
    print("=== Testing Redis State Restoration Bug ===")
    
    # Create a game and set it up normally
    players = ["Alice", "Bob", "Charlie", "Diana"]
    game = GameBoard(players)
    game.assign_teams_and_hakem()
    game.initial_deal()
    game.set_hokm("hearts")
    game.final_deal()
    
    print(f"Original game state:")
    print(f"  tricks: {game.tricks}")
    print(f"  completed_tricks: {game.completed_tricks}")
    print(f"  round_scores: {game.round_scores}")
    
    # Serialize to Redis format
    redis_state = game.to_redis_dict()
    print(f"\nSerialized state:")
    print(f"  tricks: {redis_state['tricks']}")
    print(f"  completed_tricks: {redis_state['completed_tricks']}")
    print(f"  round_scores: {redis_state['round_scores']}")
    
    # Test restoration
    restored_game = GameBoard.from_redis_dict(redis_state, players)
    print(f"\nRestored game state:")
    print(f"  tricks: {restored_game.tricks}")
    print(f"  completed_tricks: {restored_game.completed_tricks}")
    print(f"  round_scores: {restored_game.round_scores}")
    
    # Check if hand_done would be True with restored state
    hand_done = (restored_game.tricks[0] >= 7 or restored_game.tricks[1] >= 7 or restored_game.completed_tricks >= 13)
    print(f"\nWould hand_done be True with restored state? {hand_done}")
    
    # Now test what happens if Redis has corrupted data
    print("\n=== Testing Corrupted Redis Data ===")
    
    # Simulate corrupted state where completed_tricks is 13 but tricks are 0
    corrupted_state = redis_state.copy()
    corrupted_state['completed_tricks'] = '13'  # This should trigger hand completion
    corrupted_state['tricks'] = json.dumps({0: 0, 1: 0})  # But both teams have 0 tricks
    
    print(f"Corrupted state:")
    print(f"  tricks: {corrupted_state['tricks']}")
    print(f"  completed_tricks: {corrupted_state['completed_tricks']}")
    
    try:
        corrupted_game = GameBoard.from_redis_dict(corrupted_state, players)
        print(f"\nCorrupted game state after restoration:")
        print(f"  tricks: {corrupted_game.tricks}")
        print(f"  completed_tricks: {corrupted_game.completed_tricks}")
        
        # Check if this would trigger hand completion
        hand_done_corrupted = (corrupted_game.tricks[0] >= 7 or corrupted_game.tricks[1] >= 7 or corrupted_game.completed_tricks >= 13)
        print(f"\nWould hand_done be True with corrupted state? {hand_done_corrupted}")
        
        if hand_done_corrupted and corrupted_game.tricks[0] == 0 and corrupted_game.tricks[1] == 0:
            print("🚨 BUG REPRODUCED: Hand completion with 0 tricks!")
            print("This could happen if Redis state gets corrupted with completed_tricks >= 13")
            
            # Test what _resolve_trick would return
            if len(corrupted_game.current_trick) == 0:
                # Simulate a trick with 4 cards to trigger _resolve_trick
                corrupted_game.current_trick = [
                    ("Alice", "A_hearts"),
                    ("Bob", "K_hearts"),
                    ("Charlie", "Q_hearts"),
                    ("Diana", "J_hearts")
                ]
                corrupted_game.led_suit = "hearts"
                
                result = corrupted_game._resolve_trick()
                print(f"\n_resolve_trick result:")
                print(f"  hand_complete: {result.get('hand_complete')}")
                print(f"  team_tricks: {result.get('team_tricks')}")
                print(f"  round_winner: {result.get('round_winner')}")
        
    except Exception as e:
        print(f"Error with corrupted state: {e}")
    
    return True

def test_edge_case_scenarios():
    """Test various edge case scenarios that might cause the bug"""
    print("\n=== Testing Edge Case Scenarios ===")
    
    # Test 1: What happens when we manually set completed_tricks to 13
    players = ["Alice", "Bob", "Charlie", "Diana"]
    game = GameBoard(players)
    game.assign_teams_and_hakem()
    game.initial_deal()
    game.set_hokm("hearts")
    game.final_deal()
    
    # Manually set completed_tricks to 13 (this shouldn't happen in normal gameplay)
    game.completed_tricks = 13
    
    print(f"Test 1 - Manual completed_tricks = 13:")
    print(f"  tricks: {game.tricks}")
    print(f"  completed_tricks: {game.completed_tricks}")
    
    hand_done = (game.tricks[0] >= 7 or game.tricks[1] >= 7 or game.completed_tricks >= 13)
    print(f"  hand_done: {hand_done}")
    
    if hand_done and game.tricks[0] == 0 and game.tricks[1] == 0:
        print("  🚨 This would cause the bug!")

if __name__ == "__main__":
    test_redis_state_bug()
    test_edge_case_scenarios()
