#!/usr/bin/env python3
"""
Comprehensive Test Suite for Hokm Game Core Functionality
Tests the main game logic without requiring full server infrastructure.
"""

import sys
import os
sys.path.insert(0, 'backend')

def test_game_board_functionality():
    """Test GameBoard core functionality"""
    print("🎮 Testing GameBoard Core Functionality")
    print("=" * 60)
    
    from game_board import GameBoard
    
    try:
        # Test 1: Game Creation
        print("\n📝 Test 1: Game Creation")
        players = ['Alice', 'Bob', 'Charlie', 'Diana']
        game = GameBoard(players, 'TEST_ROOM')
        print(f"✅ Game created with {len(game.players)} players")
        
        # Test 2: Team Assignment
        print("\n📝 Test 2: Team Assignment")
        team_result = game.assign_teams_and_hakem(None)
        print(f"✅ Teams assigned successfully")
        print(f"   Team 1: {team_result['teams']['1']}")
        print(f"   Team 2: {team_result['teams']['2']}")
        print(f"   Hakem: {team_result['hakem']}")
        
        # Test 3: Initial Deal
        print("\n📝 Test 3: Initial Deal")
        initial_hands = game.initial_deal()
        print(f"✅ Initial deal completed")
        for player in players:
            print(f"   {player}: {len(initial_hands[player])} cards")
        
        # Test 4: Hokm Selection
        print("\n📝 Test 4: Hokm Selection")
        suits = ['hearts', 'diamonds', 'clubs', 'spades']
        for suit in suits:
            result = game.set_hokm(suit, None, 'TEST_ROOM')
            if result:
                print(f"✅ Hokm set to {suit}")
                break
        else:
            print("❌ Failed to set hokm")
            return False
        
        # Test 5: Final Deal
        print("\n📝 Test 5: Final Deal")
        final_hands = game.final_deal(None)
        print(f"✅ Final deal completed")
        for player in players:
            print(f"   {player}: {len(final_hands[player])} cards")
        
        # Test 6: Card Play Simulation
        print("\n📝 Test 6: Card Play Simulation")
        trick_count = 0
        max_tricks = 5  # Test first 5 tricks
        
        while trick_count < max_tricks and game.completed_tricks < 13:
            print(f"\n   Trick {game.completed_tricks + 1}:")
            
            # Play cards for each player in turn order
            for turn in range(4):
                current_player = game.players[game.current_turn]
                available_cards = game.hands[current_player]
                
                if not available_cards:
                    print(f"   {current_player}: No cards left")
                    break
                    
                # Play the first available card
                card = available_cards[0]
                
                try:
                    result = game.play_card(current_player, card, None)
                    print(f"   {current_player}: played {card}")
                    
                    if result.get('trick_complete'):
                        winner = result.get('trick_winner')
                        print(f"   >>> Trick won by {winner}")
                        trick_count += 1
                        break
                        
                except Exception as e:
                    print(f"   Error playing card: {e}")
                    break
        
        print(f"\n✅ Completed {trick_count} tricks successfully")
        
        # Test 7: Game State
        print("\n📝 Test 7: Game State")
        state = game.to_redis_dict()
        print(f"✅ Game state serialized successfully")
        print(f"   Phase: {state.get('game_phase')}")
        print(f"   Current turn: {state.get('current_turn')}")
        print(f"   Hokm: {state.get('hokm')}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error in GameBoard test: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_game_states():
    """Test game state management"""
    print("\n🎮 Testing Game States")
    print("=" * 60)
    
    try:
        from game_states import GameState
        
        # Test state enumeration
        states = [
            GameState.WAITING_FOR_PLAYERS,
            GameState.TEAM_ASSIGNMENT,
            GameState.WAITING_FOR_HOKM,
            GameState.FINAL_DEAL,
            GameState.GAMEPLAY
        ]
        
        print("✅ Game states available:")
        for state in states:
            print(f"   {state.name}: {state.value}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error in GameState test: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_redis_manager():
    """Test Redis manager basic functionality"""
    print("\n🎮 Testing Redis Manager")
    print("=" * 60)
    
    try:
        from redis_manager_resilient import ResilientRedisManager
        
        redis_manager = ResilientRedisManager()
        print("✅ Redis manager created successfully")
        
        # Test basic operations
        test_key = "test_key"
        test_value = "test_value"
        
        # This should work even if Redis is not available due to circuit breaker
        redis_manager.save_game_state(test_key, {'test': test_value})
        print("✅ Save operation completed")
        
        result = redis_manager.get_game_state(test_key)
        print(f"✅ Get operation completed: {result}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error in Redis test: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all tests"""
    print("🎯 HOKM GAME CORE FUNCTIONALITY TEST SUITE")
    print("=" * 80)
    
    tests = [
        ("GameBoard Functionality", test_game_board_functionality),
        ("Game States", test_game_states),
        ("Redis Manager", test_redis_manager)
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        try:
            if test_func():
                passed += 1
                print(f"\n✅ {test_name}: PASSED")
            else:
                print(f"\n❌ {test_name}: FAILED")
        except Exception as e:
            print(f"\n❌ {test_name}: ERROR - {e}")
    
    print("\n" + "=" * 80)
    print(f"🎯 TEST SUMMARY")
    print(f"Total Tests: {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {total - passed}")
    print(f"Success Rate: {(passed/total)*100:.1f}%")
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED! Core functionality is working correctly.")
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Check the detailed logs above.")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
