#!/usr/bin/env python3
"""
Debug script to test the connection close issue when playing 10_clubs after 4_spades
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

async def test_connection_close_scenario():
    """Test the specific scenario where connection closes"""
    
    print("=" * 60)
    print("DEBUGGING CONNECTION CLOSE SCENARIO")
    print("=" * 60)
    
    # Create server and game
    server = GameServer()
    server.redis_manager = Mock()
    server.network_manager = Mock()
    
    players = ["Player 0", "Player 1", "Player 2", "Player 3"]
    game = GameBoard(players, "test_room")
    
    # Set up the exact scenario from the user's output
    game.teams = {
        "Player 0": 0,
        "Player 1": 1, 
        "Player 2": 0,
        "Player 3": 1
    }
    game.hakem = "Player 0"
    game.hokm = "spades"  # Assuming spades is trump
    game.game_phase = "gameplay"
    
    # Set up hands - Player 2 has 10_clubs and others
    game.hands = {
        "Player 0": ["K_spades", "Q_hearts", "J_diamonds", "10_hearts", "9_hearts", "8_hearts", "7_hearts", "6_hearts"],
        "Player 1": ["4_spades", "A_hearts", "K_hearts", "Q_diamonds", "J_hearts", "10_diamonds", "9_diamonds", "8_diamonds"],
        "Player 2": ["10_clubs", "9_clubs", "7_clubs", "2_clubs", "Q_spades", "7_spades", "6_spades", "3_spades"],
        "Player 3": ["A_spades", "K_clubs", "Q_clubs", "J_clubs", "A_diamonds", "K_diamonds", "J_spades", "5_spades"]
    }
    
    # Player 1 has already played 4_spades, so current trick should reflect this
    game.current_trick = [("Player 1", "4_spades")]
    game.led_suit = "spades"
    game.current_turn = 2  # Player 2's turn
    
    print("Game state:")
    print(f"Current trick: {game.current_trick}")
    print(f"Led suit: {game.led_suit}")
    print(f"Current turn: {game.current_turn} (Player {players[game.current_turn]})")
    print(f"Player 2's hand: {game.hands['Player 2']}")
    print(f"Hokm: {game.hokm}")
    
    # Add game to server
    server.active_games["test_room"] = game
    
    # Mock websocket and connection
    mock_websocket = Mock()
    server.network_manager.notify_error = AsyncMock()
    server.network_manager.send_message = AsyncMock()
    server.network_manager.broadcast_to_room = AsyncMock()
    server.network_manager.get_live_connection = Mock(return_value=mock_websocket)
    
    # Mock Redis
    server.redis_manager.get_room_players.return_value = [
        {'username': 'Player 0', 'player_id': 'id0'},
        {'username': 'Player 1', 'player_id': 'id1'},
        {'username': 'Player 2', 'player_id': 'id2'},
        {'username': 'Player 3', 'player_id': 'id3'}
    ]
    
    # Mock find_player_by_websocket to return Player 2
    def mock_find_player(websocket, room_code):
        return "Player 2", "id2"
    
    server.find_player_by_websocket = mock_find_player
    
    print("\n" + "-" * 60)
    print("TESTING CARD PLAY: Player 2 plays 10_clubs")
    print("-" * 60)
    
    # Test playing 10_clubs (which should be invalid - must follow spades)
    message = {
        'room_code': 'test_room',
        'player_id': 'id2',
        'card': '10_clubs'
    }
    
    try:
        await server.handle_play_card(mock_websocket, message)
        print("✓ handle_play_card completed without exceptions")
        
        # Check if error was sent
        error_calls = server.network_manager.notify_error.call_args_list
        if error_calls:
            print(f"❌ Error sent: {error_calls[0][0][1]}")
        else:
            print("❌ No error was sent - this might be the problem!")
            
        # Check the game state after the invalid play
        print(f"Current trick after play: {game.current_trick}")
        print(f"Player 2's hand after play: {game.hands['Player 2']}")
        print(f"Current turn after play: {game.current_turn}")
        
    except Exception as e:
        print(f"❌ Exception in handle_play_card: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "-" * 60)
    print("TESTING GAME BOARD VALIDATION DIRECTLY")
    print("-" * 60)
    
    # Test the game board validation directly
    valid, message = game.validate_play("Player 2", "10_clubs")
    print(f"Direct validation result: valid={valid}, message='{message}'")
    
    # Check if Player 2 has any spades
    player2_spades = [card for card in game.hands["Player 2"] if card.split('_')[1] == "spades"]
    print(f"Player 2's spades: {player2_spades}")
    
    if player2_spades:
        print("✓ Player 2 has spades, so playing 10_clubs should be invalid")
    else:
        print("✓ Player 2 has no spades, so playing 10_clubs should be valid")
        
    print("\n" + "-" * 60)
    print("TESTING VALID PLAY")
    print("-" * 60)
    
    # Test playing a valid spade card
    if player2_spades:
        valid_card = player2_spades[0]
        print(f"Testing valid play: {valid_card}")
        
        valid, message = game.validate_play("Player 2", valid_card)
        print(f"Valid play result: valid={valid}, message='{message}'")
        
        if valid:
            result = game.play_card("Player 2", valid_card)
            print(f"Play result: {result}")

if __name__ == "__main__":
    asyncio.run(test_connection_close_scenario())
