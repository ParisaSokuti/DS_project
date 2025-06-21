#!/usr/bin/env python3
"""
Test for the new round implementation in the Hokm game.
This tests the logic where after round one is finished, we start the next round
with the player from the winning team with the most tricks as the new hakem.
"""

import sys
import os
import json
from unittest.mock import Mock, patch
import asyncio

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.game_board import GameBoard
from backend.game_states import GameState

def create_test_game():
    """Create a test game with 4 players"""
    players = ["Player 0", "Player 1", "Player 2", "Player 3"]
    game = GameBoard(players)
    
    # Assign teams: 0,2 in team 0 and 1,3 in team 1
    game.teams = {
        "Player 0": 0,
        "Player 2": 0,
        "Player 1": 1,
        "Player 3": 1
    }
    
    # Set initial hakem
    game.hakem = "Player 0"
    game.game_phase = "initial_deal"
    
    return game

def test_new_hakem_selection():
    """Test that new hakem is selected correctly from winning team"""
    game = create_test_game()
    
    # Initial state
    print("Initial game state:")
    print(f"Hakem: {game.hakem}")
    print(f"Teams: {game.teams}")
    
    # Simulate round completion where Team 0 wins (players 0 and 2)
    # Player 2 has more tricks than Player 0
    game.tricks = {0: 8, 1: 5}  # Team 0 has 8 tricks, Team 1 has 5
    
    # Assign different trick counts to players (normally not tracked, adding for test)
    game.player_tricks = {
        "Player 0": 3,
        "Player 2": 5,  # Most tricks in team 0
        "Player 1": 2,
        "Player 3": 3
    }
    
    print("\nSimulating round completion...")
    print(f"Team 0 tricks: {game.tricks[0]}")
    print(f"Team 1 tricks: {game.tricks[1]}")
    print(f"Player tricks: {game.player_tricks}")
    
    # Test preparing for new hand (which should select a new hakem)
    game._prepare_new_hand()
    
    # Verify new hakem is Player 2 (most tricks in winning team)
    print("\nAfter new hakem selection:")
    print(f"New Hakem: {game.hakem}")
    assert game.hakem == "Player 2", f"Expected Player 2 to be the new hakem, got {game.hakem}"
    print("✓ New hakem correctly selected from winning team")
    
    # Verify game state is reset for new round
    assert game.game_phase == "initial_deal", "Game phase should be initial_deal"
    assert game.hokm is None, "Hokm should be reset"
    assert len(game.deck) == 52, "Deck should be reset to 52 cards"
    assert game.tricks == {0: 0, 1: 0}, "Trick counts should be reset"
    print("✓ Game state correctly reset for new round")

def test_multiple_rounds():
    """Test multiple rounds of hakem selection"""
    game = create_test_game()
    
    # Initial hakem
    assert game.hakem == "Player 0"
    
    # Round 1: Team 0 wins, Player 2 has most tricks
    game.tricks = {0: 7, 1: 6}
    game.player_tricks = {"Player 0": 3, "Player 2": 4, "Player 1": 3, "Player 3": 3}
    game._prepare_new_hand()
    assert game.hakem == "Player 2", "Round 1: Expected Player 2 to be new hakem"
    
    # Round 2: Team 1 wins, Player 3 has most tricks
    game.tricks = {0: 5, 1: 8}
    game.player_tricks = {"Player 0": 2, "Player 2": 3, "Player 1": 3, "Player 3": 5}
    game._prepare_new_hand()
    assert game.hakem == "Player 3", "Round 2: Expected Player 3 to be new hakem"
    
    # Round 3: Team 0 wins again, Player 0 has most tricks
    game.tricks = {0: 8, 1: 5}
    game.player_tricks = {"Player 0": 5, "Player 2": 3, "Player 1": 2, "Player 3": 3}
    game._prepare_new_hand()
    assert game.hakem == "Player 0", "Round 3: Expected Player 0 to be new hakem"
    
    print("✓ Multiple rounds of hakem selection passed")

if __name__ == "__main__":
    print("=" * 60)
    print("TESTING NEW ROUND IMPLEMENTATION")
    print("=" * 60)
    
    test_new_hakem_selection()
    test_multiple_rounds()
    
    print("\n✓ All tests passed!")
    print("The new round implementation with hakem selection works correctly.")
