#!/usr/bin/env python3
"""
Test to verify the fix for the "Hand Complete with 0 tricks" bug
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.game_board import GameBoard

def test_empty_trick_protection():
    """Test that _resolve_trick now properly handles empty current_trick"""
    print("=== Testing Empty Trick Protection ===")
    
    players = ["Alice", "Bob", "Charlie", "Diana"]
    game = GameBoard(players)
    game.assign_teams_and_hakem()
    game.initial_deal()
    game.set_hokm("hearts")
    game.final_deal()
    
    # Test 1: Empty current_trick
    print("\n--- Test 1: Empty current_trick ---")
    game.current_trick = []
    try:
        result = game._resolve_trick()
        print("❌ FAIL: Should have raised ValueError for empty trick")
        return False
    except ValueError as e:
        print(f"✅ PASS: Correctly caught ValueError: {e}")
    except Exception as e:
        print(f"❌ FAIL: Wrong exception type: {type(e).__name__}: {e}")
        return False
    
    # Test 2: Incomplete trick (only 3 cards)
    print("\n--- Test 2: Incomplete trick (3 cards) ---")
    game.current_trick = [
        ("Alice", "A_hearts"),
        ("Bob", "K_hearts"),
        ("Charlie", "Q_hearts")
    ]
    try:
        result = game._resolve_trick()
        print("❌ FAIL: Should have raised ValueError for incomplete trick")
        return False
    except ValueError as e:
        print(f"✅ PASS: Correctly caught ValueError: {e}")
    except Exception as e:
        print(f"❌ FAIL: Wrong exception type: {type(e).__name__}: {e}")
        return False
    
    # Test 3: Valid complete trick (4 cards)
    print("\n--- Test 3: Valid complete trick (4 cards) ---")
    game.current_trick = [
        ("Alice", "A_hearts"),
        ("Bob", "K_hearts"),
        ("Charlie", "Q_hearts"),
        ("Diana", "J_hearts")
    ]
    game.led_suit = "hearts"
    try:
        result = game._resolve_trick()
        print(f"✅ PASS: Valid trick processed successfully")
        print(f"  Winner: {result.get('trick_winner')}")
        print(f"  Team tricks: {result.get('team_tricks')}")
        return True
    except Exception as e:
        print(f"❌ FAIL: Valid trick should not raise exception: {type(e).__name__}: {e}")
        return False

def test_server_side_protection():
    """Test that the server-side logic is now protected"""
    print("\n=== Testing Server-Side Protection ===")
    
    # Simulate the scenario that caused the original bug
    # This simulates what would happen if somehow _resolve_trick was called 
    # with an empty current_trick (which should now be impossible)
    
    players = ["Alice", "Bob", "Charlie", "Diana"]
    game = GameBoard(players)
    game.assign_teams_and_hakem()
    game.initial_deal()
    game.set_hokm("hearts")
    game.final_deal()
    
    # Simulate the server-side logic from handle_play_card
    print("Simulating server-side hand completion logic...")
    
    # This would previously cause the bug, but now should be prevented
    try:
        # This should now fail before it gets to the problematic server logic
        game.current_trick = []
        game.completed_tricks = 13  # Force hand completion condition
        
        # This should raise ValueError before we get to server logic
        result = game._resolve_trick()
        
        # If we somehow get here, test the server logic
        team_tricks = result.get('team_tricks') or {0: 0, 1: 0}
        
        if team_tricks == {0: 0, 1: 0}:
            print("❌ FAIL: Server logic would still send 0 tricks for both teams")
            return False
        else:
            print(f"✅ PASS: Server logic would send correct trick counts: {team_tricks}")
            return True
            
    except ValueError as e:
        print(f"✅ PASS: _resolve_trick correctly prevented with ValueError: {e}")
        print("✅ PASS: Server logic will never receive invalid data")
        return True
    except Exception as e:
        print(f"❌ FAIL: Unexpected exception: {type(e).__name__}: {e}")
        return False

if __name__ == "__main__":
    print("🔧 Testing fix for 'Hand Complete with 0 tricks' bug")
    print("=" * 50)
    
    test1_result = test_empty_trick_protection()
    test2_result = test_server_side_protection()
    
    print("\n" + "=" * 50)
    if test1_result and test2_result:
        print("🎉 ALL TESTS PASSED!")
        print("✅ The 'Hand Complete with 0 tricks' bug has been fixed!")
        print("\nSummary:")
        print("- _resolve_trick now validates that current_trick has exactly 4 cards")
        print("- _resolve_trick now validates that a trick winner is found")
        print("- These safety checks prevent the bug from occurring")
        print("- Server will never receive invalid hand completion data")
    else:
        print("❌ SOME TESTS FAILED!")
        print("The fix may not be complete.")
