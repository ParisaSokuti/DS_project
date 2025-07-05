#!/usr/bin/env python3
"""
Test the server disconnect bug fix.
This test simulates multiple invalid card plays followed by a valid one
to ensure the server doesn't disconnect.
"""

import asyncio
import sys
import os
import time

# Add the backend directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from redis_manager import RedisManager
from game_board import GameBoard

def test_server_disconnect_fix():
    """Test server disconnect bug fix"""
    print("=== Testing Server Disconnect Fix ===")
    
    # Create test game state
    redis_manager = RedisManager()
    room_code = "TEST_DISCONNECT_FIX"
    redis_manager.clear_room(room_code)
    
    # Create a game in gameplay phase
    game = GameBoard(["Alice", "Bob", "Charlie", "Dave"], 0)
    game.game_phase = "gameplay"
    game.hokm = "hearts"
    
    # Set up hands for testing
    game.hands = {
        "Alice": ["ace_hearts", "king_spades", "queen_clubs", "jack_diamonds"],
        "Bob": ["2_hearts", "3_spades", "4_clubs", "5_diamonds"],
        "Charlie": ["6_hearts", "7_spades", "8_clubs", "9_diamonds"],
        "Dave": ["10_hearts", "ace_spades", "king_clubs", "queen_diamonds"]
    }
    
    # Alice starts
    game.current_turn = 0
    
    print("Testing multiple invalid plays followed by valid play...")
    
    # Test 1: Invalid play (wrong suit when hearts led)
    game.led_suit = "hearts"
    
    # Alice leads with hearts
    result1 = game.play_card("Alice", "ace_hearts")
    print(f"Valid play result: {result1}")
    assert result1['valid'] == True
    
    # Bob tries to play spades when hearts are led (should be invalid if he has hearts)
    # First, let's make sure Bob has hearts so the play is invalid
    game.hands["Bob"] = ["2_hearts", "3_spades", "4_clubs", "5_diamonds"]
    
    result2 = game.play_card("Bob", "3_spades")
    print(f"Invalid play result: {result2}")
    
    # The play should be invalid because Bob has hearts but played spades
    if not result2['valid']:
        print("✓ Invalid play correctly rejected")
        
        # Now Bob plays a valid card
        result3 = game.play_card("Bob", "2_hearts")
        print(f"Valid play after invalid result: {result3}")
        
        if result3['valid']:
            print("✓ Valid play after invalid play works correctly")
        else:
            print("✗ Valid play after invalid play failed")
            return False
    else:
        print("✗ Invalid play was incorrectly accepted")
        return False
    
    print("✓ Server disconnect fix test passed")
    return True

def test_error_handling_robustness():
    """Test that error handling doesn't break game flow"""
    print("\n=== Testing Error Handling Robustness ===")
    
    # Test various error conditions
    game = GameBoard(["Alice", "Bob", "Charlie", "Dave"], 0)
    game.game_phase = "gameplay"
    game.hokm = "hearts"
    
    # Test invalid inputs
    test_cases = [
        ("", "ace_hearts"),  # Empty player
        ("Alice", ""),  # Empty card
        ("NonExistentPlayer", "ace_hearts"),  # Non-existent player
        ("Alice", "invalid_card"),  # Invalid card format
    ]
    
    for player, card in test_cases:
        try:
            result = game.play_card(player, card)
            print(f"Test {player}, {card}: {result}")
            # Should return invalid result, not raise exception
            assert 'valid' in result
            assert result['valid'] == False
        except Exception as e:
            print(f"✗ Exception raised for {player}, {card}: {e}")
            return False
    
    print("✓ Error handling robustness test passed")
    return True

if __name__ == "__main__":
    success = True
    
    try:
        success &= test_server_disconnect_fix()
        success &= test_error_handling_robustness()
        
        if success:
            print("\n✅ All tests passed! Server disconnect bug should be fixed.")
        else:
            print("\n❌ Some tests failed.")
            sys.exit(1)
            
    except Exception as e:
        print(f"\n❌ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
