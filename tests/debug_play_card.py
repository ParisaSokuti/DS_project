#!/usr/bin/env python3
"""
Test to debug the connection closing issue by examining the play_card flow
"""

import sys
import os
import json
from unittest.mock import Mock, MagicMock, AsyncMock

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.game_board import GameBoard
from backend.server import GameServer

class AsyncMock(MagicMock):
    async def __call__(self, *args, **kwargs):
        return super(AsyncMock, self).__call__(*args, **kwargs)

async def test_play_card_validation():
    """Test the server's play_card validation and error handling"""
    
    print("=" * 60)
    print("TESTING PLAY CARD VALIDATION")
    print("=" * 60)
    
    # Create mock server
    server = GameServer()
    server.redis_manager = Mock()
    server.network_manager = Mock()
    
    # Create a test game in round 2 state
    players = ["Player 0", "Player 1", "Player 2", "Player 3"]
    game = GameBoard(players, "test_room")
    
    # Set up teams and game state
    game.teams = {
        "Player 0": 0,
        "Player 2": 0,
        "Player 1": 1,
        "Player 3": 1
    }
    
    game.hakem = "Player 2"  # Player 2 is now hakem (round 2)
    game.hokm = "hearts"
    game.game_phase = "gameplay"
    game.current_turn = 2  # Player 2's turn
    
    # Set up hands
    game.hands = {
        "Player 0": ["A_hearts", "K_hearts"],
        "Player 1": ["4_spades", "5_spades"],
        "Player 2": ["10_clubs", "9_clubs", "Q_spades", "7_spades"],
        "Player 3": ["A_spades", "K_spades"]
    }
    
    # Set up current trick - Player 1 already played
    game.current_trick = [("Player 1", "4_spades")]
    game.led_suit = "spades"
    game.current_turn = 2  # Now Player 2's turn
    
    # Add game to server
    server.active_games["test_room"] = game
    
    # Mock websocket and player lookup
    mock_websocket = Mock()
    
    # Mock the find_player_by_websocket method to return Player 2
    server.find_player_by_websocket = Mock(return_value=("Player 2", "player2_id"))
    
    # Mock network methods
    server.network_manager.notify_error = AsyncMock()
    server.network_manager.broadcast_to_room = AsyncMock()
    
    print("Initial state:")
    print(f"Current turn: Player {game.current_turn} ({game.players[game.current_turn]})")
    print(f"Current trick: {game.current_trick}")
    print(f"Led suit: {game.led_suit}")
    print(f"Player 2 hand: {game.hands['Player 2']}")
    
    print("\n" + "-" * 60)
    print("TEST 1: Player 2 tries to play 10_clubs (invalid - must follow suit)")
    print("-" * 60)
    
    # Create play_card message
    message = {
        'type': 'play_card',
        'room_code': 'test_room',
        'player_id': 'player2_id',
        'card': '10_clubs'
    }
    
    try:
        await server.handle_play_card(mock_websocket, message)
        
        # Check if notify_error was called
        server.network_manager.notify_error.assert_called_once()
        error_call = server.network_manager.notify_error.call_args
        error_message = error_call[0][1]  # Second argument is the message
        
        print(f"✓ Error notification sent: {error_message}")
        assert "follow suit" in error_message.lower(), f"Expected suit following error, got: {error_message}"
        
        # Check that broadcast was NOT called (invalid play shouldn't be broadcast)
        server.network_manager.broadcast_to_room.assert_not_called()
        print("✓ No broadcast sent for invalid play")
        
        # Check that Player 2 still has the card
        assert "10_clubs" in game.hands["Player 2"], "10_clubs should still be in Player 2's hand"
        print("✓ Card not removed from hand for invalid play")
        
        # Check that the turn didn't advance
        assert game.current_turn == 2, "Turn should not have advanced for invalid play"
        print("✓ Turn did not advance for invalid play")
        
    except Exception as e:
        print(f"❌ Exception during handle_play_card: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print("\n" + "-" * 60)
    print("TEST 2: Player 2 plays Q_spades (valid - follows suit)")
    print("-" * 60)
    
    # Reset mocks
    server.network_manager.notify_error.reset_mock()
    server.network_manager.broadcast_to_room.reset_mock()
    
    # Create valid play_card message
    message = {
        'type': 'play_card',
        'room_code': 'test_room',
        'player_id': 'player2_id',
        'card': 'Q_spades'
    }
    
    try:
        await server.handle_play_card(mock_websocket, message)
        
        # Check that no error was sent
        server.network_manager.notify_error.assert_not_called()
        print("✓ No error notification for valid play")
        
        # Check that broadcast was called (valid play should be broadcast)
        server.network_manager.broadcast_to_room.assert_called()
        print("✓ Broadcast sent for valid play")
        
        # Check that the card was removed from hand
        assert "Q_spades" not in game.hands["Player 2"], "Q_spades should be removed from Player 2's hand"
        print("✓ Card removed from hand for valid play")
        
        # Check that the turn advanced
        assert game.current_turn == 3, f"Turn should advance to 3, got {game.current_turn}"
        print("✓ Turn advanced for valid play")
        
    except Exception as e:
        print(f"❌ Exception during handle_play_card: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print(f"\n🎉 ALL TESTS PASSED!")
    print("The play_card validation logic is working correctly in isolation.")
    return True

if __name__ == "__main__":
    import asyncio
    success = asyncio.run(test_play_card_validation())
    if success:
        print("\n✅ Play card test completed successfully!")
        print("The issue might be with connection state or client-server communication.")
    else:
        print("\n❌ Play card test failed!")
        print("There's a bug in the server play_card handling.")
