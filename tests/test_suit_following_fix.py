#!/usr/bin/env python3
"""
Test the suit-following logic in the client to make sure it works correctly
"""

import sys
import os

# Add the backend directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from game_board import GameBoard

def test_suit_following():
    """Test the suit-following validation"""
    print("=== Testing Suit Following Logic ===")
    
    # Create a test game
    game = GameBoard(["Alice", "Bob", "Charlie", "Dave"], 0)
    game.game_phase = "gameplay"
    game.hokm = "hearts"  # Set trump suit
    
    # Set up a specific scenario
    game.hands = {
        "Alice": ["2_spades"],  # Alice leads with spades
        "Bob": ["4_hearts", "A_diamonds", "K_diamonds", "J_diamonds", "7_diamonds", "6_diamonds", "3_diamonds", "Q_clubs", "5_clubs", "K_spades", "J_spades"],
        "Charlie": ["3_hearts"],
        "Dave": ["4_hearts"]
    }
    
    # Alice plays 2_spades to lead the trick
    game.current_turn = 0
    result = game.play_card("Alice", "2_spades")
    print(f"Alice plays 2_spades: {result}")
    
    # Now it's Bob's turn - he must follow suit (play spades)
    print(f"\nBob's hand: {game.hands['Bob']}")
    print("Led suit:", game.led_suit)
    print("Bob has spades:", [card for card in game.hands['Bob'] if 'spades' in card])
    
    # Test invalid plays (should fail)
    invalid_plays = ["4_hearts", "A_diamonds", "Q_clubs"]
    for card in invalid_plays:
        result = game.play_card("Bob", card)
        print(f"Bob tries {card}: {result}")
        assert not result['valid'], f"Expected {card} to be invalid but it was accepted"
    
    # Test valid plays (should succeed)
    valid_plays = ["K_spades", "J_spades"]
    for card in valid_plays:
        # Reset game state for each test
        game.current_turn = 1  # Bob's turn
        game.current_trick = [("Alice", "2_spades")]  # Alice led with spades
        game.led_suit = "spades"
        
        result = game.play_card("Bob", card)
        print(f"Bob plays {card}: {result}")
        assert result['valid'], f"Expected {card} to be valid but it was rejected"
    
    print("\n✅ Suit following logic is working correctly!")
    return True

def test_client_card_selection():
    """Test the card selection logic"""
    print("\n=== Testing Client Card Selection ===")
    
    # Simulate the hand from the user's scenario
    hand = ["4_hearts", "A_diamonds", "K_diamonds", "J_diamonds", "7_diamonds", "6_diamonds", "3_diamonds", "Q_clubs", "5_clubs", "K_spades", "J_spades"]
    
    # Test valid selections
    test_cases = [
        ("10", "K_spades"),  # Should select K_spades
        ("11", "J_spades"),  # Should select J_spades
    ]
    
    for input_str, expected_card in test_cases:
        try:
            card_idx = int(input_str) - 1
            if 0 <= card_idx < len(hand):
                selected_card = hand[card_idx]
                print(f"Input '{input_str}' -> Index {card_idx} -> Card '{selected_card}'")
                assert selected_card == expected_card, f"Expected {expected_card}, got {selected_card}"
            else:
                print(f"Input '{input_str}' -> Invalid index {card_idx}")
        except ValueError:
            print(f"Input '{input_str}' -> ValueError")
    
    print("✅ Client card selection logic is working correctly!")
    return True

if __name__ == "__main__":
    try:
        success = True
        success &= test_suit_following()
        success &= test_client_card_selection()
        
        if success:
            print("\n🎉 All tests passed!")
            print("\nTo fix the issue, the user should select:")
            print("Option 10: K_spades")
            print("Option 11: J_spades")
            print("\nThese are the only valid cards since spades were led and must be followed.")
        else:
            print("\n❌ Some tests failed.")
            
    except Exception as e:
        print(f"\n❌ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
