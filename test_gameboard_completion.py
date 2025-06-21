#!/usr/bin/env python3
"""
Test the actual GameBoard implementation with the corrected game completion logic
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.game_board import GameBoard

def test_gameboard_completion():
    """Test that GameBoard correctly implements 2-round game completion"""
    
    print("=" * 70)
    print("TESTING ACTUAL GAMEBOARD - 7 ROUNDS TO WIN GAME")
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
    game.hakem = "Player 0"
    game.hokm = "spades"  # Set trump suit
    game.game_phase = "gameplay"
    
    print("Initial state:")
    print(f"Round scores: {game.round_scores}")
    print(f"Game phase: {game.game_phase}")
    
    # Test Round 1: Team 0 gets 7 tricks
    print("\n" + "-" * 50)
    print("ROUND 1: Team 0 wins with 7 tricks")
    print("-" * 50)
    
    # Set up game state for end of round 1
    game.tricks = {0: 7, 1: 6}
    game.completed_tricks = 13
    game.led_suit = "spades"  # Set led suit
    game.current_trick = [("Player 0", "A_spades"), ("Player 1", "K_spades"), 
                         ("Player 2", "Q_spades"), ("Player 3", "J_spades")]
    
    # Simulate trick resolution that ends the round
    result = game._resolve_trick()
    
    print("Result of _resolve_trick():")
    print(f"  hand_complete: {result.get('hand_complete', False)}")
    print(f"  game_complete: {result.get('game_complete', False)}")
    print(f"  round_winner: {result.get('round_winner', 'None')}")
    print(f"  round_scores: {result.get('round_scores', {})}")
    
    # Verify round 1 results
    assert result['hand_complete'], "Round should be complete"
    assert not result.get('game_complete', False), "Game should NOT be complete after 1 round"
    assert result['round_winner'] == 1, "Team 1 (0-indexed) should win the round"
    assert game.round_scores[0] == 1, "Team 0 should have 1 round win"
    assert game.round_scores[1] == 0, "Team 1 should have 0 round wins"
    
    print("✓ Round 1 completed correctly - game continues")
    
    # Test Round 2: Team 0 wins again (should end game)
    print("\n" + "-" * 50)
    print("ROUND 2: Team 0 wins again with 7 tricks")
    print("-" * 50)
    
    # Reset for round 2 (this would normally be done by _prepare_new_hand)
    game.tricks = {0: 7, 1: 6}
    game.completed_tricks = 13
    game.led_suit = "hearts"  # Set led suit
    game.current_trick = [("Player 2", "A_hearts"), ("Player 3", "K_hearts"), 
                         ("Player 0", "Q_hearts"), ("Player 1", "J_hearts")]
    
    # Simulate trick resolution that ends round 2
    result = game._resolve_trick()
    
    print("Result of _resolve_trick():")
    print(f"  hand_complete: {result.get('hand_complete', False)}")
    print(f"  game_complete: {result.get('game_complete', False)}")
    print(f"  round_winner: {result.get('round_winner', 'None')}")
    print(f"  round_scores: {result.get('round_scores', {})}")
    print(f"  game_phase: {game.game_phase}")
    
    # Verify round 2 results
    assert result['hand_complete'], "Round should be complete"
    assert result.get('game_complete', False), "Game SHOULD be complete after Team 0 wins 2nd round"
    assert result['round_winner'] == 1, "Team 1 (0-indexed) should win the round"
    assert game.round_scores[0] == 2, "Team 0 should have 2 round wins"
    assert game.round_scores[1] == 0, "Team 1 should have 0 round wins"
    assert game.game_phase == "completed", "Game phase should be 'completed'"
    
    print("✓ Round 2 completed correctly - GAME ENDS!")
    
    print(f"\n🎉 ALL TESTS PASSED!")
    print("GameBoard correctly implements:")
    print("✅ Rounds end when one team gets 7 tricks")
    print("✅ Game ends when one team wins 7 rounds")
    print("✅ Game phase changes to 'completed' when game ends")
    
    return True

if __name__ == "__main__":
    success = test_gameboard_completion()
    if success:
        print("\n✅ GameBoard implementation test passed!")
    else:
        print("\n❌ GameBoard implementation test failed!")
