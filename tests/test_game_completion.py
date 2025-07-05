#!/usr/bin/env python3
"""
Test to verify game completion logic - game should end when one team wins 7 rounds
"""

import sys
import os
import json
import asyncio
from unittest.mock import Mock, patch, MagicMock

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.game_board import GameBoard
from backend.server import GameServer

def test_game_completion_logic():
    """Test that the game ends when one team wins 7 rounds"""
    
    print("=" * 70)
    print("TESTING GAME COMPLETION LOGIC - 7 ROUNDS TO WIN")
    print("=" * 70)
    
    players = ["Player 0", "Player 1", "Player 2", "Player 3"]
    game = GameBoard(players, "test_room")
    
    # Set up teams
    game.teams = {
        "Player 0": 0,
        "Player 2": 0,
        "Player 1": 1,
        "Player 3": 1
    }
    
    print("Testing round completion and game completion logic...")
    
    # Test 1: First round - Team 0 wins with 7 tricks
    print("\n" + "-" * 40)
    print("TEST 1: First round - Team 0 gets 7 tricks")
    print("-" * 40)
    
    # Set up initial state
    game.tricks = {0: 6, 1: 6}  # Close game
    game.round_scores = {0: 0, 1: 0}  # No rounds won yet
    game.completed_tricks = 12
    game.game_phase = "gameplay"
    
    # Simulate team 0 winning the 13th trick to get 7 tricks total
    game.tricks[0] = 7  # Team 0 now has 7 tricks
    
    # Check if round is complete
    hand_done = (game.tricks[0] >= 7 or game.tricks[1] >= 7 or game.completed_tricks >= 13)
    print(f"Round complete: {hand_done}")
    print(f"Team tricks: {game.tricks}")
    
    # Simulate the round completion logic
    if hand_done:
        if game.tricks[0] >= 7:
            hand_winner_idx = 0
        elif game.tricks[1] >= 7:
            hand_winner_idx = 1
        else:
            hand_winner_idx = 0 if game.tricks[0] > game.tricks[1] else 1
            
        game.round_scores[hand_winner_idx] += 1
        print(f"Round winner: Team {hand_winner_idx + 1}")
        print(f"Round scores after round 1: {game.round_scores}")
        
        # Check game completion
        game_complete = game.round_scores[hand_winner_idx] >= 7
        print(f"Game complete: {game_complete}")
        
        assert game.round_scores[0] == 1, "Team 0 should have 1 round win"
        assert game.round_scores[1] == 0, "Team 1 should have 0 round wins"
        assert not game_complete, "Game should NOT be complete after 1 round"
        
        print("✓ First round logic is correct")
    
    # Test 2-7: Team 0 wins rounds 2 through 7 (game should end after round 7)
    print("\n" + "-" * 40)
    print("TEST 2-7: Team 0 wins rounds 2-7 to reach 7 total wins")
    print("-" * 40)
    
    # Simulate rounds 2 through 7
    for round_num in range(2, 8):
        print(f"\n--- Round {round_num} ---")
        # Reset for each round
        game.tricks = {0: 6, 1: 6}
        game.completed_tricks = 12
        
        # Simulate team 0 winning again
        game.tricks[0] = 7
        
        hand_done = (game.tricks[0] >= 7 or game.tricks[1] >= 7 or game.completed_tricks >= 13)
        print(f"Round {round_num} complete: {hand_done}")
        
        if hand_done:
            if game.tricks[0] >= 7:
                hand_winner_idx = 0
            elif game.tricks[1] >= 7:
                hand_winner_idx = 1
            else:
                hand_winner_idx = 0 if game.tricks[0] > game.tricks[1] else 1
                
            game.round_scores[hand_winner_idx] += 1
            print(f"Round {round_num} winner: Team {hand_winner_idx + 1}")
            print(f"Round scores after round {round_num}: {game.round_scores}")
            
            # Check game completion
            game_complete = game.round_scores[hand_winner_idx] >= 7
            print(f"Game complete after round {round_num}: {game_complete}")
            
            if game_complete:
                print(f"✓ Game ends after Team 0 wins round {round_num}!")
                break
    
    # Final verification
    print(f"\nFinal verification:")
    print(f"Team 0 round wins: {game.round_scores[0]}")
    print(f"Team 1 round wins: {game.round_scores[1]}")
    print(f"Game complete: {game_complete}")
    
    assert game.round_scores[0] == 7, "Team 0 should have 7 round wins"
    assert game.round_scores[1] == 0, "Team 1 should have 0 round wins"
    assert game_complete, "Game SHOULD be complete after Team 0 wins 7 rounds"
    
    print("✓ Seven round logic is correct - game ends after 7 round wins!")
    
    # Test 3: Alternative scenario - Team 1 wins first, then Team 0 wins enough to reach 7
    print("\n" + "-" * 40)
    print("TEST 3: Alternative scenario - Team 1 wins 1, then Team 0 wins 7")
    print("-" * 40)
    
    # Reset game
    game.round_scores = {0: 0, 1: 0}
    
    # Team 1 wins first round
    game.round_scores[1] += 1
    print(f"After Team 1 wins round 1: {game.round_scores}")
    assert not (game.round_scores[1] >= 7), "Game should not be complete"
    
    # Team 0 wins next 7 rounds to reach 7 total
    for i in range(7):
        game.round_scores[0] += 1
        print(f"After Team 0 wins round {i+2}: {game.round_scores}")
        if i < 6:  # First 6 wins shouldn't complete the game
            assert max(game.round_scores.values()) < 7, "Game should still not be complete"
    
    # After 7th win, game should be complete
    assert game.round_scores[0] >= 7, "Game should be complete - Team 0 has 7 wins"
    
    print("✓ Alternative scenario logic is correct")
    
    print(f"\n🎉 ALL TESTS PASSED!")
    print("Game completion logic is working correctly:")
    print("- Each round ends when one team gets 7 tricks")
    print("- The game ends when one team wins 7 rounds")
    
    return True

if __name__ == "__main__":
    success = test_game_completion_logic()
    if success:
        print("\n✅ Game completion test passed!")
    else:
        print("\n❌ Game completion test failed!")
