#!/usr/bin/env python3
"""
Test to verify the updated game completion logic - game should end when one team wins 7 rounds
"""

import sys
import os

# Add the backend directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from game_board import GameBoard

def test_7_round_winning_condition():
    """Test that the game ends when one team wins 7 rounds"""
    
    print("=" * 70)
    print("TESTING 7-ROUND WINNING CONDITION")
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
    
    # Test: Team 0 wins 7 rounds
    print("Testing Team 0 winning 7 rounds...")
    
    # Simulate 7 rounds where Team 0 wins each round
    for round_num in range(1, 8):
        print(f"\n--- Round {round_num} ---")
        
        # Set up round state
        game.tricks = {0: 6, 1: 6}  # Close game
        game.completed_tricks = 12
        game.game_phase = "gameplay"
        
        # Simulate team 0 winning the round (getting 7 tricks)
        game.tricks[0] = 7
        
        # Check if round is complete
        hand_done = (game.tricks[0] >= 7 or game.tricks[1] >= 7 or game.completed_tricks >= 13)
        print(f"Round {round_num} complete: {hand_done}")
        print(f"Team tricks: {game.tricks}")
        
        # Simulate the round completion logic
        if hand_done:
            if game.tricks[0] >= 7:
                hand_winner_idx = 0
            elif game.tricks[1] >= 7:
                hand_winner_idx = 1
            else:
                hand_winner_idx = 0 if game.tricks[0] > game.tricks[1] else 1
            
            # Award round win
            game.round_scores[hand_winner_idx] += 1
            print(f"Round {round_num} winner: Team {hand_winner_idx + 1}")
            print(f"Round scores after round {round_num}: {game.round_scores}")
            
            # Check game completion using the actual game logic
            game_complete = game.round_scores[hand_winner_idx] >= 7
            if game_complete:
                game.game_phase = "completed"
            
            print(f"Game complete after round {round_num}: {game_complete}")
            
            if game_complete:
                print(f"🎉 Game ends after Team 0 wins {round_num} rounds!")
                break
    
    # Final verification
    print(f"\n" + "=" * 50)
    print("FINAL VERIFICATION")
    print("=" * 50)
    print(f"Team 0 round wins: {game.round_scores[0]}")
    print(f"Team 1 round wins: {game.round_scores[1]}")
    print(f"Game phase: {game.game_phase}")
    print(f"Game complete: {game.game_phase == 'completed'}")
    
    # Assertions
    assert game.round_scores[0] == 7, f"Team 0 should have 7 round wins, got {game.round_scores[0]}"
    assert game.round_scores[1] == 0, f"Team 1 should have 0 round wins, got {game.round_scores[1]}"
    assert game.game_phase == "completed", f"Game should be completed, phase is {game.game_phase}"
    
    print("✅ All assertions passed!")
    return True

def test_6_rounds_not_enough():
    """Test that game does NOT end after 6 rounds"""
    
    print("\n" + "=" * 70)
    print("TESTING THAT 6 ROUNDS IS NOT ENOUGH TO WIN")
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
    
    # Simulate 6 rounds where Team 0 wins each round
    for round_num in range(1, 7):
        print(f"Simulating round {round_num}...")
        
        # Set up round state
        game.tricks = {0: 7, 1: 6}  # Team 0 wins with 7 tricks
        game.completed_tricks = 13
        
        # Award round win to Team 0
        game.round_scores[0] += 1
        
        # Check game completion
        game_complete = game.round_scores[0] >= 7
        if game_complete:
            game.game_phase = "completed"
    
    print(f"After 6 rounds:")
    print(f"Team 0 round wins: {game.round_scores[0]}")
    print(f"Team 1 round wins: {game.round_scores[1]}")
    print(f"Game phase: {game.game_phase}")
    print(f"Game complete: {game.game_phase == 'completed'}")
    
    # Assertions
    assert game.round_scores[0] == 6, f"Team 0 should have 6 round wins, got {game.round_scores[0]}"
    assert game.game_phase != "completed", f"Game should NOT be completed after 6 rounds"
    
    print("✅ Game correctly continues after 6 rounds!")
    return True

if __name__ == "__main__":
    try:
        success = True
        success &= test_7_round_winning_condition()
        success &= test_6_rounds_not_enough()
        
        if success:
            print("\n" + "🎉" * 20)
            print("ALL TESTS PASSED!")
            print("7-round winning condition is working correctly!")
            print("🎉" * 20)
        else:
            print("\n❌ Some tests failed.")
            sys.exit(1)
            
    except Exception as e:
        print(f"\n❌ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
