#!/usr/bin/env python3
"""
Comprehensive test to reproduce the exact server flow and identify the bug
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.game_board import GameBoard
import json

def simulate_server_flow():
    """Simulate the exact server flow that might cause the bug"""
    print("=== Simulating Complete Server Flow ===")
    
    # Step 1: Create and set up game
    players = ["Alice", "Bob", "Charlie", "Diana"]
    game = GameBoard(players)
    game.assign_teams_and_hakem()
    game.initial_deal()
    game.set_hokm("hearts")
    game.final_deal()
    
    print(f"Initial state:")
    print(f"  tricks: {game.tricks}")
    print(f"  completed_tricks: {game.completed_tricks}")
    print(f"  teams: {game.teams}")
    
    # Step 2: Simulate playing multiple tricks to get close to hand completion
    for trick_num in range(1, 8):  # Play 7 tricks
        print(f"\n--- Trick {trick_num} ---")
        
        # Set up a trick where Alice wins (team determined by game.teams)
        game.current_trick = [
            ("Alice", f"{14-trick_num}_hearts"),  # Alice plays high card
            ("Bob", f"{13-trick_num}_hearts"),
            ("Charlie", f"{12-trick_num}_hearts"),
            ("Diana", f"{11-trick_num}_hearts")
        ]
        game.led_suit = "hearts"
        
        print(f"Before trick {trick_num}:")
        print(f"  tricks: {game.tricks}")
        print(f"  completed_tricks: {game.completed_tricks}")
        
        # Resolve the trick
        result = game._resolve_trick()
        
        print(f"After trick {trick_num}:")
        print(f"  tricks: {game.tricks}")
        print(f"  completed_tricks: {game.completed_tricks}")
        print(f"  hand_complete: {result.get('hand_complete')}")
        print(f"  team_tricks in result: {result.get('team_tricks')}")
        
        # Check if hand is complete
        if result.get('hand_complete'):
            print(f"🎯 Hand completed after {trick_num} tricks!")
            
            # Simulate the server-side logic
            team_tricks = result.get('team_tricks') or {0: 0, 1: 0}
            print(f"Server would send: tricks = {team_tricks}")
            
            # Check if this would cause the bug
            if team_tricks == {0: 0, 1: 0}:
                print("🚨 BUG REPRODUCED: Hand complete with 0 tricks for both teams!")
                print(f"  result['team_tricks']: {result.get('team_tricks')}")
                print(f"  game.tricks at time of bug: {game.tricks}")
                print(f"  game.completed_tricks: {game.completed_tricks}")
            
            break
    
    return game

def test_state_corruption_scenarios():
    """Test scenarios where state might get corrupted"""
    print("\n=== Testing State Corruption Scenarios ===")
    
    # Scenario 1: What if _resolve_trick is called when current_trick is empty?
    print("\n--- Scenario 1: Empty current_trick ---")
    players = ["Alice", "Bob", "Charlie", "Diana"]
    game = GameBoard(players)
    game.assign_teams_and_hakem()
    game.initial_deal()
    game.set_hokm("hearts")
    game.final_deal()
    
    # Set completed_tricks to 13 but don't set up current_trick
    game.completed_tricks = 13
    game.current_trick = []  # Empty trick
    
    try:
        print(f"Before _resolve_trick with empty current_trick:")
        print(f"  tricks: {game.tricks}")
        print(f"  completed_tricks: {game.completed_tricks}")
        print(f"  current_trick: {game.current_trick}")
        
        # This should fail or produce unexpected results
        result = game._resolve_trick()
        print(f"Result: {result}")
        
    except Exception as e:
        print(f"Exception with empty trick: {e}")
    
    # Scenario 2: What if Redis state gets corrupted?
    print("\n--- Scenario 2: Redis State Corruption ---")
    game2 = GameBoard(players)
    game2.assign_teams_and_hakem()
    game2.initial_deal()
    game2.set_hokm("hearts")
    game2.final_deal()
    
    # Simulate corrupted Redis state
    redis_state = game2.to_redis_dict()
    print(f"Original Redis state tricks: {redis_state['tricks']}")
    print(f"Original Redis state completed_tricks: {redis_state['completed_tricks']}")
    
    # Corrupt the state
    redis_state['completed_tricks'] = '13'  # High value
    redis_state['tricks'] = json.dumps({0: 0, 1: 0})  # But 0 tricks
    
    print(f"Corrupted Redis state tricks: {redis_state['tricks']}")
    print(f"Corrupted Redis state completed_tricks: {redis_state['completed_tricks']}")
    
    # Restore from corrupted state
    try:
        corrupted_game = GameBoard.from_redis_dict(redis_state, players)
        print(f"Restored from corrupted state:")
        print(f"  tricks: {corrupted_game.tricks}")
        print(f"  completed_tricks: {corrupted_game.completed_tricks}")
        
        # Check hand completion condition
        hand_done = (corrupted_game.tricks[0] >= 7 or corrupted_game.tricks[1] >= 7 or corrupted_game.completed_tricks >= 13)
        print(f"  hand_done would be: {hand_done}")
        
        if hand_done and corrupted_game.tricks[0] == 0 and corrupted_game.tricks[1] == 0:
            print("🚨 BUG REPRODUCED: Corrupted Redis state causes hand completion with 0 tricks!")
            
    except Exception as e:
        print(f"Exception restoring corrupted state: {e}")

if __name__ == "__main__":
    simulate_server_flow()
    test_state_corruption_scenarios()
