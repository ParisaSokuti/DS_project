#!/usr/bin/env python3
"""
Test to reproduce the specific suit-following issue
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.game_board import GameBoard

def test_suit_following_scenario():
    """Test the specific suit-following scenario that's causing connection issues"""
    
    print("=" * 60)
    print("TESTING SUIT FOLLOWING SCENARIO")
    print("=" * 60)
    
    # Create a test game
    players = ["Player 0", "Player 1", "Player 2", "Player 3"]
    game = GameBoard(players, "test_room")
    
    # Set up teams
    game.teams = {
        "Player 0": 0,
        "Player 2": 0,
        "Player 1": 1,
        "Player 3": 1
    }
    
    # Set up game state
    game.hakem = "Player 0"
    game.hokm = "hearts"  # Assume hearts is trump
    game.game_phase = "gameplay"
    
    # Set up hands - Player 2 has both spades and clubs
    game.hands = {
        "Player 0": ["A_hearts", "K_hearts", "Q_hearts"],
        "Player 1": ["4_spades", "5_spades", "6_spades"],
        "Player 2": ["10_clubs", "9_clubs", "7_clubs", "2_clubs", "Q_spades", "7_spades", "6_spades", "3_spades"],
        "Player 3": ["A_spades", "K_spades", "J_spades"]
    }
    
    # Set current turn to Player 1 (who will lead with spades)
    game.current_turn = 1
    
    print("Initial state:")
    print(f"Current turn: Player 1")
    print(f"Player 2 hand: {game.hands['Player 2']}")
    print(f"Hokm: {game.hokm}")
    
    print("\n" + "-" * 60)
    print("STEP 1: Player 1 plays 4_spades (leads)")
    print("-" * 60)
    
    # Player 1 plays 4_spades
    result1 = game.play_card("Player 1", "4_spades")
    print(f"Player 1 result: {result1}")
    
    if not result1.get('valid', True):
        print(f"❌ Player 1 play failed: {result1.get('message')}")
        return False
    
    print(f"Current trick: {game.current_trick}")
    print(f"Led suit: {game.led_suit}")
    print(f"Next turn: Player {game.current_turn} ({game.players[game.current_turn]})")
    
    print("\n" + "-" * 60)
    print("STEP 2: Player 2 tries to play 10_clubs (should fail - must follow suit)")
    print("-" * 60)
    
    # Player 2 tries to play 10_clubs (should fail because they have spades)
    result2 = game.play_card("Player 2", "10_clubs")
    print(f"Player 2 result: {result2}")
    
    if result2.get('valid', True):
        print("❌ ERROR: Play should have been rejected for suit-following violation")
        return False
    else:
        print(f"✓ Correctly rejected: {result2.get('message')}")
    
    print("\n" + "-" * 60)
    print("STEP 3: Player 2 plays Q_spades (should succeed)")
    print("-" * 60)
    
    # Player 2 plays Q_spades (should succeed)
    result3 = game.play_card("Player 2", "Q_spades")
    print(f"Player 2 result: {result3}")
    
    if not result3.get('valid', True):
        print(f"❌ Player 2 valid play failed: {result3.get('message')}")
        return False
    
    print(f"✓ Valid play succeeded")
    print(f"Current trick: {game.current_trick}")
    print(f"Next turn: Player {game.current_turn} ({game.players[game.current_turn]})")
    
    print("\n" + "-" * 60)
    print("STEP 4: Validate card removal from hand")
    print("-" * 60)
    
    print(f"Player 2 hand after play: {game.hands['Player 2']}")
    
    if "Q_spades" in game.hands["Player 2"]:
        print("❌ ERROR: Q_spades should have been removed from hand")
        return False
    
    if "10_clubs" not in game.hands["Player 2"]:
        print("❌ ERROR: 10_clubs should still be in hand")
        return False
        
    print("✓ Hand correctly updated")
    
    print(f"\n🎉 ALL TESTS PASSED!")
    print("The suit-following logic is working correctly.")
    return True

if __name__ == "__main__":
    success = test_suit_following_scenario()
    if success:
        print("\n✅ Suit following test completed successfully!")
        print("The issue may be elsewhere in the server code.")
    else:
        print("\n❌ Suit following test failed!")
        print("There's a bug in the game logic.")
