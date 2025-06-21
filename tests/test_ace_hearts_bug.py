import sys
import os
import asyncio
import unittest
import json
import traceback
from unittest.mock import MagicMock, patch

# Add the parent directory to the path so we can import the backend modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.game_board import GameBoard
from backend.server import GameServer
from backend.network import NetworkManager
from backend.redis_manager import RedisManager

class MockWebSocket:
    """Mock WebSocket class for testing"""
    def __init__(self):
        self.sent_messages = []
        self.closed = False
        self.remote_address = ('127.0.0.1', 12345)
    
    async def send(self, message):
        self.sent_messages.append(message)
        
    async def close(self):
        self.closed = True

class TestAceHeartsBug(unittest.TestCase):
    """Test case to debug the issue with A_hearts card causing connection close"""
    
    async def async_setup(self):
        # Create mock objects
        self.redis_manager = MagicMock(spec=RedisManager)
        self.network_manager = MagicMock(spec=NetworkManager)
        
        # Setup mock behaviors
        self.player_ids = {f"Player {i+1}": f"player_id_{i}" for i in range(4)}
        self.room_code = "test_room"
        
        # Create mock websockets
        self.websockets = {player: MockWebSocket() for player in self.player_ids.keys()}
        
        # Setup mock connection metadata
        self.network_manager.connection_metadata = {
            ws: {"player_id": player_id, "room_code": self.room_code}
            for player, player_id in self.player_ids.items()
            for ws in [self.websockets[player]]
        }
        
        # Setup live connections
        self.network_manager.live_connections = {
            self.websockets[player]: self.player_ids[player] for player in self.player_ids
        }
        
        # Configure mock behaviors for network_manager
        def get_live_connection(player_id):
            for player, pid in self.player_ids.items():
                if pid == player_id:
                    return self.websockets[player]
            return None
        
        self.network_manager.get_live_connection.side_effect = get_live_connection
        
        # Create a capture for broadcast_to_room calls
        self.broadcast_calls = []
        
        async def mock_broadcast(room_code, message_type, data, redis_manager=None):
            # Save the broadcast attempt
            self.broadcast_calls.append((room_code, message_type, data))
            
            # Debug print
            print(f"[DEBUG] Broadcasting '{message_type}' to room: {room_code}")
            print(f"[DEBUG] Data: {json.dumps(data, indent=2)}")
            
            # Try to serialize the data to check for JSON issues
            try:
                json_str = json.dumps(data)
                return True
            except TypeError as e:
                print(f"[ERROR] JSON serialization failed: {str(e)}")
                print(f"[ERROR] Problem data: {data}")
                raise
        
        self.network_manager.broadcast_to_room.side_effect = mock_broadcast
        
        # Setup modified send_message to catch and log errors
        async def debug_send_message(websocket, message_type, data):
            try:
                print(f"[DEBUG] Sending {message_type} to client")
                print(f"[DEBUG] Message data: {json.dumps(data, indent=2)}")
                
                # Try to serialize the data
                json_msg = json.dumps({"type": message_type, "data": data})
                await websocket.send(json_msg)
                return True
            except Exception as e:
                print(f"[ERROR] Failed to send message: {str(e)}")
                traceback.print_exc()
                return False
                
        self.network_manager.send_message.side_effect = debug_send_message
        
        # Configure mock behaviors for redis_manager
        self.redis_manager.get_room_players.return_value = [
            {"username": player, "player_id": self.player_ids[player]}
            for player in self.player_ids
        ]
        
        # Create the game server with our mocked dependencies
        self.game_server = GameServer()
        self.game_server.redis_manager = self.redis_manager
        self.game_server.network_manager = self.network_manager
        
        # Create a game instance
        self.players = list(self.player_ids.keys())
        self.game = GameBoard(self.players, self.room_code)
        self.game_server.active_games[self.room_code] = self.game
        
        # Setup game state for testing
        self.game.teams = {self.players[i]: i % 2 for i in range(4)}  # Teams 0 and 1
        self.game.hakem = self.players[0]  # Player 1 is hakem
        self.game.hokm = "hearts"  # Hearts is hokm
        self.game.game_phase = "gameplay"
        self.game.current_turn = 3  # Player 4's turn
        
        # Setup hands
        self.game.hands = {
            "Player 1": ["K_hearts", "Q_diamonds", "5_diamonds", "3_diamonds", "A_clubs", "9_clubs", "8_clubs", "6_clubs", "A_spades", "K_spades", "9_spades", "8_spades", "2_spades"],
            "Player 2": ["10_hearts", "9_hearts", "8_hearts", "J_diamonds", "10_diamonds", "8_diamonds", "Q_clubs", "5_clubs", "4_clubs", "2_clubs", "Q_spades", "J_spades", "7_spades"],
            "Player 3": ["J_hearts", "7_hearts", "5_hearts", "4_hearts", "A_diamonds", "9_diamonds", "7_diamonds", "6_diamonds", "8_spades", "6_spades", "5_spades", "4_spades", "3_clubs"],
            "Player 4": ["A_hearts", "Q_hearts", "6_hearts", "K_diamonds", "4_diamonds", "2_diamonds", "K_clubs", "J_clubs", "10_clubs", "7_clubs", "5_clubs", "10_spades", "3_spades"]
        }
        
        # Initialize current trick
        self.game.current_trick = []
        
        # Save original methods before mocking
        self.original_play_card = self.game.play_card
        
        # Mock the to_redis_dict method to avoid errors
        self.game.to_redis_dict = MagicMock(return_value={})
    
    async def run_ace_hearts_test_scenario(self, scenario_name, play_card_result):
        """Run a test scenario with specific play_card results"""
        print(f"\n--- Test Scenario: {scenario_name} ---")
        
        # Set up the mock behavior for this scenario
        self.game.play_card = MagicMock(return_value=play_card_result)
        
        # Prepare the play card message
        message = {
            "room_code": self.room_code,
            "player_id": self.player_ids["Player 4"],
            "card": "A_hearts"
        }
        
        player_websocket = self.websockets["Player 4"]
        
        # Clear previous broadcast calls
        self.broadcast_calls = []
        
        # Wrap the handle_play_card method in try-except to catch and display any errors
        try:
            print(f"[INFO] Calling handle_play_card with card: A_hearts")
            await self.game_server.handle_play_card(player_websocket, message)
            print(f"[SUCCESS] {scenario_name} completed successfully")
            return True
        except Exception as e:
            print(f"[ERROR] Exception occurred: {str(e)}")
            traceback.print_exc()
            return False
    
    async def test_scenarios(self):
        """Test multiple scenarios to find the issue"""
        await self.async_setup()
        
        # Scenario 1: Normal card play
        await self.run_ace_hearts_test_scenario("Normal card play", {
            "valid": True,
            "trick_complete": False,
            "next_turn": "Player 1"
        })
        
        # Scenario 2: Trick complete but hand not complete
        await self.run_ace_hearts_test_scenario("Trick complete but hand not complete", {
            "valid": True,
            "trick_complete": True,
            "hand_complete": False,
            "trick_winner": "Player 2",
            "team_tricks": {0: 1, 1: 0}
        })
        
        # Scenario 3: Hand complete with team_tricks as dictionary
        await self.run_ace_hearts_test_scenario("Hand complete with proper data", {
            "valid": True,
            "trick_complete": True,
            "hand_complete": True,
            "trick_winner": "Player 2",
            "team_tricks": {0: 7, 1: 6},
            "round_winner": 1,  # Team 1 wins
            "round_scores": {0: 0, 1: 1},
            "game_complete": False
        })
        
        # Scenario 4: Missing round_winner (defaults should apply)
        await self.run_ace_hearts_test_scenario("Missing round_winner", {
            "valid": True,
            "trick_complete": True,
            "hand_complete": True,
            "trick_winner": "Player 2",
            "team_tricks": {0: 7, 1: 6},
            # round_winner is missing
            "round_scores": {0: 0, 1: 1},
            "game_complete": False
        })
        
        # Scenario 5: team_tricks as list instead of dictionary
        await self.run_ace_hearts_test_scenario("Invalid team_tricks format (list)", {
            "valid": True,
            "trick_complete": True,
            "hand_complete": True,
            "trick_winner": "Player 2",
            "team_tricks": [7, 6],  # Wrong format, should be dictionary
            "round_winner": 1,
            "round_scores": {0: 0, 1: 1},
            "game_complete": False
        })
        
        # Scenario 6: Negative round_winner value
        await self.run_ace_hearts_test_scenario("Negative round_winner", {
            "valid": True,
            "trick_complete": True,
            "hand_complete": True,
            "trick_winner": "Player 2",
            "team_tricks": {0: 7, 1: 6},
            "round_winner": -1,  # Invalid negative value
            "round_scores": {0: 0, 1: 1},
            "game_complete": False
        })
        
        # Scenario 7: Missing team_tricks
        await self.run_ace_hearts_test_scenario("Missing team_tricks", {
            "valid": True,
            "trick_complete": True,
            "hand_complete": True,
            "trick_winner": "Player 2",
            # team_tricks is missing
            "round_winner": 1,
            "round_scores": {0: 0, 1: 1},
            "game_complete": False
        })
        
        # Scenario 8: Non-serializable value
        class NonSerializable:
            pass
        
        await self.run_ace_hearts_test_scenario("Non-serializable value", {
            "valid": True,
            "trick_complete": True,
            "hand_complete": True,
            "trick_winner": "Player 2",
            "team_tricks": {0: 7, 1: 6},
            "round_winner": 1,
            "round_scores": {0: 0, 1: 1},
            "game_complete": False,
            "non_serializable": NonSerializable()  # This can't be serialized to JSON
        })
        
        # Scenario 9: Trick complete but no trick_winner provided
        await self.run_ace_hearts_test_scenario("Missing trick_winner", {
            "valid": True,
            "trick_complete": True,
            "hand_complete": False,
            # trick_winner is missing
            "team_tricks": {0: 1, 1: 0}
        })

def run_tests():
    """Run the tests asynchronously"""
    test = TestAceHeartsBug()
    loop = asyncio.get_event_loop()
    loop.run_until_complete(test.test_scenarios())
    
if __name__ == "__main__":
    run_tests()