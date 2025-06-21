#!/usr/bin/env python3
"""
Debug script to test the input validation logic that's causing issues
"""

def test_input_validation():
    """Test the input validation logic with edge cases"""
    
    # Simulate having 1 card in hand
    sorted_hand = ["A_hearts"]  # Single card
    
    print(f"Testing with {len(sorted_hand)} card(s): {sorted_hand}")
    
    # Test case 1: User enters "1" (should be valid)
    choice = "1"
    try:
        card_idx = int(choice) - 1  # This gives us 0
        print(f"User entered: '{choice}'")
        print(f"Calculated card_idx: {card_idx}")
        print(f"Hand length: {len(sorted_hand)}")
        print(f"Condition check: 0 <= {card_idx} < {len(sorted_hand)} = {0 <= card_idx < len(sorted_hand)}")
        
        if 0 <= card_idx < len(sorted_hand):
            card = sorted_hand[card_idx]
            print(f"✅ VALID: Selected card: {card}")
        else:
            print(f"❌ INVALID: Please enter a number between 1 and {len(sorted_hand)}")
            
    except ValueError as e:
        print(f"❌ ValueError: {e}")
    
    print("\n" + "="*50 + "\n")
    
    # Test case 2: User enters "0" (should be invalid)
    choice = "0"
    try:
        card_idx = int(choice) - 1  # This gives us -1
        print(f"User entered: '{choice}'")
        print(f"Calculated card_idx: {card_idx}")
        print(f"Hand length: {len(sorted_hand)}")
        print(f"Condition check: 0 <= {card_idx} < {len(sorted_hand)} = {0 <= card_idx < len(sorted_hand)}")
        
        if 0 <= card_idx < len(sorted_hand):
            card = sorted_hand[card_idx]
            print(f"✅ VALID: Selected card: {card}")
        else:
            print(f"❌ INVALID: Please enter a number between 1 and {len(sorted_hand)}")
            
    except ValueError as e:
        print(f"❌ ValueError: {e}")

    print("\n" + "="*50 + "\n")
    
    # Test case 3: User enters "2" with 1 card (should be invalid)
    choice = "2"
    try:
        card_idx = int(choice) - 1  # This gives us 1
        print(f"User entered: '{choice}'")
        print(f"Calculated card_idx: {card_idx}")
        print(f"Hand length: {len(sorted_hand)}")
        print(f"Condition check: 0 <= {card_idx} < {len(sorted_hand)} = {0 <= card_idx < len(sorted_hand)}")
        
        if 0 <= card_idx < len(sorted_hand):
            card = sorted_hand[card_idx]
            print(f"✅ VALID: Selected card: {card}")
        else:
            print(f"❌ INVALID: Please enter a number between 1 and {len(sorted_hand)}")
            
    except ValueError as e:
        print(f"❌ ValueError: {e}")

if __name__ == "__main__":
    test_input_validation()
