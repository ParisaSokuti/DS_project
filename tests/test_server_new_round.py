#!/usr/bin/env python3
"""
Test to debug the server issue with initial cards not being dealt in new rounds
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

async def test_server_new_round():
    """Test the server's new round functionality"""
    
    print("=" * 60)
    print("TESTING SERVER NEW ROUND FUNCTIONALITY")
    print("=" * 60)
    
    # Create mock server components
    server = GameServer()
    server.redis_manager = Mock()
    server.network_manager = Mock()
    
    # Create a test game
    players = ["Player 0", "Player 1", "Player 2", "Player 3"]
    game = GameBoard(players, "test_room")
    
    # Set up teams and initial state
    game.teams = {
        "Player 0": 0,
        "Player 2": 0,
        "Player 1": 1,
        "Player 3": 1
    }
    game.hakem = "Player 0"
    game.player_tricks = {"Player 0": 3, "Player 2": 5, "Player 1": 2, "Player 3": 3}
    game.tricks = {0: 8, 1: 5}  # Team 0 wins
    game.round_scores = {0: 1, 1: 0}  # Team 0 has won 1 round
    game.game_phase = "gameplay"
    
    # Add game to server's active games
    server.active_games["test_room"] = game
    
    print("Initial game state:")
    print(f"Hakem: {game.hakem}")
    print(f"Player tricks: {game.player_tricks}")
    print(f"Team tricks: {game.tricks}")
    print(f"Round scores: {game.round_scores}")
    
    # Mock Redis and Network methods
    server.redis_manager.get_room_players.return_value = [
        {'username': 'Player 0', 'player_id': 'id0'},
        {'username': 'Player 1', 'player_id': 'id1'},
        {'username': 'Player 2', 'player_id': 'id2'},
        {'username': 'Player 3', 'player_id': 'id3'}
    ]
    
    server.network_manager.broadcast_to_room = AsyncMock()
    server.network_manager.get_live_connection = Mock(return_value=Mock())  # Mock websocket
    server.network_manager.send_message = AsyncMock()
    
    print("\n" + "-" * 60)
    print("STARTING NEW ROUND TEST")
    print("-" * 60)
    
    # Test the new round functionality
    try:
        await server.start_next_round("test_room")
        
        print("\n✓ start_next_round completed without errors")
        
        # Check if the hakem was updated correctly
        print(f"New hakem: {game.hakem}")
        assert game.hakem == "Player 2", f"Expected Player 2 to be new hakem, got {game.hakem}"
        print("✓ Hakem correctly updated to Player 2")
        
        # Check if broadcast_to_room was called for new_round_start
        server.network_manager.broadcast_to_room.assert_called()
        calls = server.network_manager.broadcast_to_room.call_args_list
        
        # Find the new_round_start call
        new_round_call = None
        for call in calls:
            if len(call[0]) >= 2 and call[0][1] == 'new_round_start':
                new_round_call = call
                break
        
        assert new_round_call is not None, "new_round_start broadcast not found"
        print("✓ new_round_start broadcast was called")
        
        # Check the data sent in new_round_start
        broadcast_data = new_round_call[0][2]  # Third argument is the data
        print(f"Broadcast data: {broadcast_data}")
        
        assert broadcast_data['hakem'] == "Player 2", "Incorrect hakem in broadcast"
        assert broadcast_data['round_number'] == 2, "Incorrect round number"
        print("✓ Broadcast data is correct")
        
        # Check if send_message was called for initial_deal (should be called 4 times, once per player)
        send_calls = server.network_manager.send_message.call_args_list
        initial_deal_calls = [call for call in send_calls if len(call[0]) >= 2 and call[0][1] == 'initial_deal']
        
        print(f"Number of initial_deal calls: {len(initial_deal_calls)}")
        assert len(initial_deal_calls) == 4, f"Expected 4 initial_deal calls, got {len(initial_deal_calls)}"
        print("✓ initial_deal sent to all 4 players")
        
        # Check the content of one initial_deal call
        sample_call = initial_deal_calls[0]
        deal_data = sample_call[0][2]  # Third argument is the data
        print(f"Sample initial_deal data: {deal_data}")
        
        assert 'hand' in deal_data, "hand not in initial_deal data"
        assert 'hakem' in deal_data, "hakem not in initial_deal data"
        assert 'is_hakem' in deal_data, "is_hakem not in initial_deal data"
        assert len(deal_data['hand']) == 5, f"Expected 5 cards, got {len(deal_data['hand'])}"
        print("✓ initial_deal data structure is correct")
        
        print(f"\n🎉 ALL TESTS PASSED!")
        print("The server new round functionality is working correctly.")
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {str(e)}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

if __name__ == "__main__":
    success = asyncio.run(test_server_new_round())
    if success:
        print("\n✅ Server test completed successfully!")
    else:
        print("\n❌ Server test failed!")
