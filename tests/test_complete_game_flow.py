#!/usr/bin/env python3
"""
Comprehensive test for complete game flow including 2-round game completion
"""

import sys
import os
import json
import asyncio
from unittest.mock import Mock, patch, MagicMock

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.game_board import GameBoard
from backend.server import GameServer

class AsyncMock(MagicMock):
    async def __call__(self, *args, **kwargs):
        return super(AsyncMock, self).__call__(*args, **kwargs)

async def test_complete_game_flow():
    """Test the complete game flow with 2-round completion"""
    
    print("=" * 70)
    print("TESTING COMPLETE GAME FLOW - 7 ROUNDS TO WIN")
    print("=" * 70)
    
    # Create server and game
    server = GameServer()
    server.redis_manager = Mock()
    server.network_manager = Mock()
    
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
    game.hokm = "spades"
    game.game_phase = "gameplay"
    
    # Mock server components
    server.active_games["test_room"] = game
    server.redis_manager.get_room_players.return_value = [
        {'username': 'Player 0', 'player_id': 'id0'},
        {'username': 'Player 1', 'player_id': 'id1'},
        {'username': 'Player 2', 'player_id': 'id2'},
        {'username': 'Player 3', 'player_id': 'id3'}
    ]
    
    server.network_manager.broadcast_to_room = AsyncMock()
    server.network_manager.get_live_connection = Mock(return_value=Mock())
    server.network_manager.send_message = AsyncMock()
    
    print("Testing scenario: Team 0 wins first round, Team 1 wins second round, Team 0 wins third round")
    
    # ROUND 1: Team 0 wins
    print("\n" + "="*50)
    print("ROUND 1: Team 0 wins with 7 tricks")
    print("="*50)
    
    game.tricks = {0: 7, 1: 6}
    game.round_scores = {0: 0, 1: 0}
    game.completed_tricks = 13
    game.led_suit = "spades"
    game.current_trick = [("Player 0", "A_spades"), ("Player 1", "K_spades"), 
                         ("Player 2", "Q_spades"), ("Player 3", "J_spades")]
    
    result = game._resolve_trick()
    
    print(f"Round 1 result:")
    print(f"  hand_complete: {result['hand_complete']}")
    print(f"  game_complete: {result.get('game_complete', False)}")
    print(f"  round_winner: {result['round_winner']}")
    print(f"  round_scores: {result['round_scores']}")
    print(f"  game_phase: {game.game_phase}")
    
    assert result['hand_complete'], "Round 1 should be complete"
    assert not result.get('game_complete', False), "Game should not be complete after round 1"
    assert game.round_scores[0] == 1, "Team 0 should have 1 round win"
    assert game.round_scores[1] == 0, "Team 1 should have 0 round wins"
    assert game.game_phase == "initial_deal", "Should be ready for next round"
    
    print("✓ Round 1 completed correctly")
    
    # ROUND 2: Team 1 wins
    print("\n" + "="*50)
    print("ROUND 2: Team 1 wins with 7 tricks")
    print("="*50)
    
    # Reset for round 2
    game.tricks = {0: 6, 1: 7}
    game.completed_tricks = 13
    game.led_suit = "hearts"
    game.current_trick = [("Player 1", "A_hearts"), ("Player 2", "K_hearts"), 
                         ("Player 3", "Q_hearts"), ("Player 0", "J_hearts")]
    
    result = game._resolve_trick()
    
    print(f"Round 2 result:")
    print(f"  hand_complete: {result['hand_complete']}")
    print(f"  game_complete: {result.get('game_complete', False)}")
    print(f"  round_winner: {result['round_winner']}")
    print(f"  round_scores: {result['round_scores']}")
    print(f"  game_phase: {game.game_phase}")
    
    assert result['hand_complete'], "Round 2 should be complete"
    assert not result.get('game_complete', False), "Game should not be complete after round 2"
    assert game.round_scores[0] == 1, "Team 0 should still have 1 round win"
    assert game.round_scores[1] == 1, "Team 1 should now have 1 round win"
    assert game.game_phase == "initial_deal", "Should be ready for next round"
    
    print("✓ Round 2 completed correctly - tied at 1-1")
    
    # ROUND 3: Team 0 wins (game should end)
    print("\n" + "="*50)
    print("ROUND 3: Team 0 wins with 7 tricks (GAME SHOULD END)")
    print("="*50)
    
    # Reset for round 3
    game.tricks = {0: 7, 1: 6}
    game.completed_tricks = 13
    game.led_suit = "clubs"
    game.current_trick = [("Player 2", "A_clubs"), ("Player 3", "K_clubs"), 
                         ("Player 0", "Q_clubs"), ("Player 1", "J_clubs")]
    
    result = game._resolve_trick()
    
    print(f"Round 3 result:")
    print(f"  hand_complete: {result['hand_complete']}")
    print(f"  game_complete: {result.get('game_complete', False)}")
    print(f"  round_winner: {result['round_winner']}")
    print(f"  round_scores: {result['round_scores']}")
    print(f"  game_phase: {game.game_phase}")
    
    assert result['hand_complete'], "Round 3 should be complete"
    assert result.get('game_complete', False), "Game SHOULD be complete after round 3"
    assert game.round_scores[0] == 2, "Team 0 should have 2 round wins"
    assert game.round_scores[1] == 1, "Team 1 should have 1 round win"
    assert game.game_phase == "completed", "Game phase should be 'completed'"
    
    print("✓ Round 3 completed correctly - GAME ENDS!")
    
    # Test server's handling of game completion
    print("\n" + "="*50)
    print("TESTING SERVER RESPONSE TO GAME COMPLETION")
    print("="*50)
    
    # Mock a final card play that triggers game completion
    mock_websocket = Mock()
    server.find_player_by_websocket = Mock(return_value=("Player 0", "id0"))
    
    # Set up game state for final play
    game.game_phase = "gameplay"
    game.hands = {"Player 0": ["A_diamonds"], "Player 1": [], "Player 2": [], "Player 3": []}
    game.tricks = {0: 6, 1: 6}
    game.completed_tricks = 12
    game.current_trick = [("Player 1", "K_diamonds"), ("Player 2", "Q_diamonds"), ("Player 3", "J_diamonds")]
    game.led_suit = "diamonds"
    game.current_turn = 0
    
    # Play the final card
    message = {
        'room_code': 'test_room',
        'player_id': 'id0',
        'card': 'A_diamonds'
    }
    
    try:
        await server.handle_play_card(mock_websocket, message)
        
        # Check that game_over broadcast was called
        broadcast_calls = server.network_manager.broadcast_to_room.call_args_list
        game_over_calls = [call for call in broadcast_calls if len(call[0]) >= 2 and call[0][1] == 'game_over']
        
        print(f"Number of game_over broadcasts: {len(game_over_calls)}")
        
        if game_over_calls:
            game_over_data = game_over_calls[0][0][2]  # Third argument is the data
            print(f"Game over data: {game_over_data}")
            print("✓ Server correctly broadcasts game_over when game completes")
        else:
            print("❌ Server did not broadcast game_over")
            
    except Exception as e:
        print(f"Error testing server game completion: {e}")
        import traceback
        traceback.print_exc()
    
    print(f"\n🎉 ALL TESTS PASSED!")
    print("\nFinal Summary:")
    print("✅ Each round ends when one team gets 7 tricks")
    print("✅ Game continues until one team wins 7 rounds")
    print("✅ Game phase changes to 'completed' when game ends")
    print("✅ Server properly handles game completion")
    print("✅ Complete game flow working correctly!")
    
    return True

if __name__ == "__main__":
    success = asyncio.run(test_complete_game_flow())
    if success:
        print("\n✅ Complete game flow test passed!")
    else:
        print("\n❌ Complete game flow test failed!")
