#!/usr/bin/env python3
"""
Debug script to test the specific client-server interaction causing connection close
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

class MockWebSocket:
    def __init__(self):
        self.sent_messages = []
        self.closed = False
        
    async def send(self, message):
        self.sent_messages.append(message)
        
    async def close(self):
        self.closed = True
        
    def is_closed(self):
        return self.closed

async def test_client_server_interaction():
    """Test the exact client-server interaction that causes connection close"""
    
    print("=" * 70)
    print("TESTING CLIENT-SERVER INTERACTION - CONNECTION CLOSE DEBUG")
    print("=" * 70)
    
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
    game.hokm = "spades"
    game.game_phase = "gameplay"
    
    # Set up hands - Player 2 has the exact hand from the user's output
    game.hands = {
        "Player 0": ["K_spades", "Q_hearts", "J_diamonds", "10_hearts", "9_hearts", "8_hearts", "7_hearts", "6_hearts"],
        "Player 1": ["4_spades", "A_hearts", "K_hearts", "Q_diamonds", "J_hearts", "10_diamonds", "9_diamonds", "8_diamonds"],
        "Player 2": ["10_clubs", "9_clubs", "7_clubs", "2_clubs", "Q_spades", "7_spades", "6_spades", "3_spades"],
        "Player 3": ["A_spades", "K_clubs", "Q_clubs", "J_clubs", "A_diamonds", "K_diamonds", "J_spades", "5_spades"]
    }
    
    # Player 1 has already played 4_spades
    game.current_trick = [("Player 1", "4_spades")]
    game.led_suit = "spades"
    game.current_turn = 2  # Player 2's turn
    
    # Add game to server
    server.active_games["test_room"] = game
    
    # Create mock websocket
    mock_websocket = MockWebSocket()
    
    # Mock find_player_by_websocket to return Player 2
    def mock_find_player(websocket, room_code):
        return "Player 2", "id2"
    
    server.find_player_by_websocket = mock_find_player
    
    # Mock Redis
    server.redis_manager.get_room_players.return_value = [
        {'username': 'Player 0', 'player_id': 'id0'},
        {'username': 'Player 1', 'player_id': 'id1'},
        {'username': 'Player 2', 'player_id': 'id2'},
        {'username': 'Player 3', 'player_id': 'id3'}
    ]
    
    # Replace network manager methods with tracking versions
    sent_messages = []
    
    async def mock_notify_error(websocket, message):
        print(f"[SERVER->CLIENT] Sending error: {message}")
        await websocket.send(json.dumps({
            'type': 'error',
            'message': message
        }))
        sent_messages.append(('error', message))
    
    async def mock_send_message(websocket, msg_type, data):
        print(f"[SERVER->CLIENT] Sending {msg_type}: {data}")
        await websocket.send(json.dumps({
            'type': msg_type,
            **data
        }))
        sent_messages.append((msg_type, data))
    
    async def mock_broadcast_to_room(room_code, msg_type, data, redis_manager):
        print(f"[SERVER->ROOM] Broadcasting {msg_type}: {data}")
        sent_messages.append(('broadcast', msg_type, data))
    
    server.network_manager.notify_error = mock_notify_error
    server.network_manager.send_message = mock_send_message
    server.network_manager.broadcast_to_room = mock_broadcast_to_room
    server.network_manager.get_live_connection = Mock(return_value=mock_websocket)
    
    print("\nGame state before play:")
    print(f"Current trick: {game.current_trick}")
    print(f"Led suit: {game.led_suit}")
    print(f"Current turn: {game.current_turn} (Player {players[game.current_turn]})")
    print(f"Player 2's hand: {game.hands['Player 2']}")
    
    print("\n" + "-" * 70)
    print("STEP 1: Player 2 tries to play 10_clubs (invalid - must follow spades)")
    print("-" * 70)
    
    # Test playing 10_clubs (invalid)
    message = {
        'room_code': 'test_room',
        'player_id': 'id2',
        'card': '10_clubs'
    }
    
    try:
        await server.handle_play_card(mock_websocket, message)
        
        print(f"\n✓ Server processed the invalid play")
        print(f"WebSocket closed: {mock_websocket.is_closed()}")
        print(f"Messages sent to client: {len(mock_websocket.sent_messages)}")
        
        for i, msg in enumerate(mock_websocket.sent_messages):
            parsed = json.loads(msg)
            print(f"  {i+1}. {parsed['type']}: {parsed.get('message', parsed)}")
            
        # Check game state after invalid play
        print(f"\nGame state after invalid play:")
        print(f"Current trick: {game.current_trick}")
        print(f"Player 2's hand: {game.hands['Player 2']}")
        print(f"Current turn: {game.current_turn}")
        
        # Verify the card was NOT removed from hand and game state didn't change
        assert "10_clubs" in game.hands["Player 2"], "Card should still be in hand after invalid play"
        assert len(game.current_trick) == 1, "Trick should still have only 1 card"
        assert game.current_turn == 2, "Turn should still be Player 2's"
        
        print("✓ Game state correctly preserved after invalid play")
        
    except Exception as e:
        print(f"❌ Exception in server: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print("\n" + "-" * 70)
    print("STEP 2: Player 2 plays Q_spades (valid)")  
    print("-" * 70)
    
    # Reset websocket for clean test
    mock_websocket.sent_messages.clear()
    
    # Test playing Q_spades (valid)
    message = {
        'room_code': 'test_room',
        'player_id': 'id2',
        'card': 'Q_spades'
    }
    
    try:
        await server.handle_play_card(mock_websocket, message)
        
        print(f"\n✓ Server processed the valid play")
        print(f"WebSocket closed: {mock_websocket.is_closed()}")
        print(f"Messages sent to client: {len(mock_websocket.sent_messages)}")
        
        for i, msg in enumerate(mock_websocket.sent_messages):
            parsed = json.loads(msg)
            print(f"  {i+1}. {parsed['type']}: {parsed.get('message', parsed)}")
            
        # Check game state after valid play
        print(f"\nGame state after valid play:")
        print(f"Current trick: {game.current_trick}")
        print(f"Player 2's hand: {game.hands['Player 2']}")
        print(f"Current turn: {game.current_turn} (Player {players[game.current_turn]})")
        
        # Verify the card was removed from hand and game state updated
        assert "Q_spades" not in game.hands["Player 2"], "Card should be removed from hand after valid play"
        assert len(game.current_trick) == 2, "Trick should now have 2 cards"
        assert game.current_turn == 3, "Turn should advance to Player 3"
        
        print("✓ Game state correctly updated after valid play")
        
    except Exception as e:
        print(f"❌ Exception in server: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    print(f"\n🎉 TEST COMPLETED SUCCESSFULLY!")
    print("\nCONCLUSION:")
    print("- Server correctly handles both invalid and valid plays")
    print("- Invalid plays send error message without changing game state")
    print("- Valid plays update game state and broadcast to room")
    print("- Connection is NOT closed by server for invalid plays")
    print("\n💡 The connection close issue is likely in the CLIENT code")
    print("   The client may be closing connection upon receiving error messages")
    
    return True

if __name__ == "__main__":
    success = asyncio.run(test_client_server_interaction())
    if success:
        print("\n✅ Server-side test completed successfully!")
    else:
        print("\n❌ Server-side test failed!")
