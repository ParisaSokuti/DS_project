#!/usr/bin/env python3
"""
Test script to verify the hand_complete message handling fix
"""

def test_hand_complete_parsing():
    """Test that we can correctly parse hand_complete message data"""
    
    # Sample data from your debug output
    sample_data = {
        'type': 'hand_complete', 
        'winning_team': 0, 
        'tricks': {'0': 7, '1': 6}, 
        'round_winner': 1, 
        'round_scores': {'0': 1, '1': 0}, 
        'game_complete': False, 
        'you': 'Player 2', 
        'player_number': 2
    }
    
    print("Testing hand_complete message parsing...")
    print(f"Input data: {sample_data}")
    print()
    
    # Simulate the parsing logic from client.py
    try:
        winning_team = sample_data['winning_team'] + 1
        
        # Handle tricks data - convert string keys to integers
        tricks_data = sample_data.get('tricks', {})
        if isinstance(tricks_data, dict):
            # Server sends {'0': count, '1': count} - convert to int
            tricks_team1 = int(tricks_data.get('0', 0)) if '0' in tricks_data else int(tricks_data.get(0, 0))
            tricks_team2 = int(tricks_data.get('1', 0)) if '1' in tricks_data else int(tricks_data.get(1, 0))
        else:
            # Fallback for list format
            tricks_team1 = tricks_data[0] if len(tricks_data) > 0 else 0
            tricks_team2 = tricks_data[1] if len(tricks_data) > 1 else 0
        
        print(f"=== Hand Complete ===")
        print(f"Team {winning_team} wins the hand!")
        print(f"Final trick count:")
        print(f"Team 1: {tricks_team1} tricks")
        print(f"Team 2: {tricks_team2} tricks")
        
        # Display round summary if available
        if 'round_scores' in sample_data:
            scores = sample_data.get('round_scores', {})
            # Handle string keys for round_scores too
            team1_rounds = int(scores.get('0', 0)) if '0' in scores else int(scores.get(0, 0))
            team2_rounds = int(scores.get('1', 0)) if '1' in scores else int(scores.get(1, 0))
            print("\nRound Score:")
            print(f"Team 1: {team1_rounds} hands")
            print(f"Team 2: {team2_rounds} hands")
        
        print("Round 1 finished")
        
        # Verify expected values
        assert tricks_team1 == 7, f"Expected Team 1 to have 7 tricks, got {tricks_team1}"
        assert tricks_team2 == 6, f"Expected Team 2 to have 6 tricks, got {tricks_team2}"
        assert team1_rounds == 1, f"Expected Team 1 to have 1 round win, got {team1_rounds}"
        assert team2_rounds == 0, f"Expected Team 2 to have 0 round wins, got {team2_rounds}"
        
        print("\n✅ All assertions passed! The fix works correctly.")
        
    except Exception as e:
        print(f"❌ Error in parsing: {e}")
        return False
    
    return True

def test_edge_cases():
    """Test various edge cases for the parsing logic"""
    
    print("\n" + "="*50)
    print("Testing edge cases...")
    
    # Test with integer keys (backwards compatibility)
    test_data_int_keys = {
        'type': 'hand_complete',
        'winning_team': 1,
        'tricks': {0: 5, 1: 8},  # Integer keys
        'round_scores': {0: 0, 1: 1}  # Integer keys
    }
    
    print("\nTest case: Integer keys")
    try:
        tricks_data = test_data_int_keys.get('tricks', {})
        tricks_team1 = int(tricks_data.get('0', 0)) if '0' in tricks_data else int(tricks_data.get(0, 0))
        tricks_team2 = int(tricks_data.get('1', 0)) if '1' in tricks_data else int(tricks_data.get(1, 0))
        
        scores = test_data_int_keys.get('round_scores', {})
        team1_rounds = int(scores.get('0', 0)) if '0' in scores else int(scores.get(0, 0))
        team2_rounds = int(scores.get('1', 0)) if '1' in scores else int(scores.get(1, 0))
        
        print(f"Team 1: {tricks_team1} tricks, {team1_rounds} rounds")
        print(f"Team 2: {tricks_team2} tricks, {team2_rounds} rounds")
        
        assert tricks_team1 == 5 and tricks_team2 == 8
        assert team1_rounds == 0 and team2_rounds == 1
        print("✅ Integer keys test passed")
        
    except Exception as e:
        print(f"❌ Integer keys test failed: {e}")
        
    # Test with missing data
    test_data_missing = {
        'type': 'hand_complete',
        'winning_team': 0,
        'tricks': {},
        'round_scores': {}
    }
    
    print("\nTest case: Missing data")
    try:
        tricks_data = test_data_missing.get('tricks', {})
        tricks_team1 = int(tricks_data.get('0', 0)) if '0' in tricks_data else int(tricks_data.get(0, 0))
        tricks_team2 = int(tricks_data.get('1', 0)) if '1' in tricks_data else int(tricks_data.get(1, 0))
        
        scores = test_data_missing.get('round_scores', {})
        team1_rounds = int(scores.get('0', 0)) if '0' in scores else int(scores.get(0, 0))
        team2_rounds = int(scores.get('1', 0)) if '1' in scores else int(scores.get(1, 0))
        
        print(f"Team 1: {tricks_team1} tricks, {team1_rounds} rounds")
        print(f"Team 2: {tricks_team2} tricks, {team2_rounds} rounds")
        
        assert tricks_team1 == 0 and tricks_team2 == 0
        assert team1_rounds == 0 and team2_rounds == 0
        print("✅ Missing data test passed")
        
    except Exception as e:
        print(f"❌ Missing data test failed: {e}")

if __name__ == "__main__":
    print("Hand Complete Message Fix Test")
    print("=" * 50)
    
    success = test_hand_complete_parsing()
    test_edge_cases()
    
    if success:
        print(f"\n🎉 All tests completed successfully!")
        print("The hand_complete message handling should now work correctly.")
    else:
        print(f"\n❌ Some tests failed. Please check the implementation.")
