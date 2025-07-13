"""
Debugging script specifically for the A_hearts connection issue.
This script will temporarily patch the server.py code to add extensive logging
and run a controlled test to identify where the connection is closing.
"""

import sys
import os
import asyncio
import json
import traceback
import websockets

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import server module for patching
from backend.server import GameServer
from backend.network import NetworkManager
from backend.redis_manager import RedisManager

# Original methods to restore after patching
original_handle_play_card = None
original_broadcast_to_room = None
original_send_message = None

def patch_server_functions():
    """Patch the server functions with debug versions"""
    global original_handle_play_card
    global original_broadcast_to_room
    global original_send_message
    
    # Store originals
    original_handle_play_card = GameServer.handle_play_card
    original_broadcast_to_room = NetworkManager.broadcast_to_room
    original_send_message = NetworkManager.send_message
    
    # Create debug versions with extensive logging
    async def debug_handle_play_card(self, websocket, message):
        """Debug version of handle_play_card with extensive logging"""
        try:
            print("\n==== PLAY CARD DEBUG ====")
            print(f"Received play_card message: {json.dumps(message, indent=2)}")
            
            room_code = message.get('room_code')
            card = message.get('card')
            print(f"Room: {room_code}, Card: {card}")
            
            # Call the game's play_card method and capture the result
            game = self.active_games.get(room_code)
            player, player_id = self.find_player_by_websocket(websocket, room_code)
            print(f"Player: {player}, Player ID: {player_id}")
            
            try:
                print("Calling game.play_card()...")
                result = game.play_card(player, card, self.redis_manager)
                print(f"play_card result: {json.dumps(result, indent=2, default=str)}")
            except Exception as e:
                print(f"ERROR in game.play_card(): {str(e)}")
                traceback.print_exc()
                return
            
            # Handle further processing based on result
            if result.get('trick_complete'):
                print("Trick is complete, preparing trick_result broadcast")
                
                # Debug the trick_result data
                trick_result_data = {
                    'winner': result.get('trick_winner'),
                    'team1_tricks': result.get('team_tricks', {}).get(0, 0),
                    'team2_tricks': result.get('team_tricks', {}).get(1, 0)
                }
                print(f"trick_result data: {json.dumps(trick_result_data, indent=2, default=str)}")
                
                # Check if hand is complete
                if result.get('hand_complete'):
                    print("Hand is complete, preparing hand_complete broadcast")
                    
                    # Debug the winning team calculation
                    round_winner = result.get('round_winner', 1)
                    print(f"round_winner (raw): {round_winner}, type: {type(round_winner)}")
                    
                    winning_team = max(0, round_winner - 1) if round_winner > 0 else 0
                    print(f"winning_team (calculated): {winning_team}")
                    
                    # Debug the hand_complete data
                    hand_complete_data = {
                        'winning_team': winning_team,
                        'tricks': result.get('team_tricks', {0: 0, 1: 0}),
                        'round_winner': round_winner,
                        'round_scores': result.get('round_scores', {0: 0, 1: 0}),
                        'game_complete': result.get('game_complete', False)
                    }
                    print(f"hand_complete data: {json.dumps(hand_complete_data, indent=2, default=str)}")
                    
                    # Verify each field is JSON serializable
                    try:
                        for key, value in hand_complete_data.items():
                            json.dumps(value)
                            print(f"Field '{key}' is JSON serializable")
                    except Exception as e:
                        print(f"Field serialization error: {str(e)}")
                        traceback.print_exc()
            
            # Call the original function and return its result
            return await original_handle_play_card(self, websocket, message)
            
        except Exception as e:
            print(f"Exception in debug_handle_play_card: {str(e)}")
            traceback.print_exc()
    
    # Debug version of broadcast_to_room
    async def debug_broadcast_to_room(self, room_code, message_type, data, redis_manager=None):
        try:
            print(f"\n==== BROADCAST DEBUG ====")
            print(f"Broadcasting '{message_type}' to room: {room_code}")
            print(f"Data to broadcast: {json.dumps(data, indent=2, default=str)}")
            
            # Test JSON serialization
            try:
                json_str = json.dumps(data)
                print("Data is JSON serializable")
            except Exception as e:
                print(f"ERROR: Data is NOT JSON serializable: {str(e)}")
                print("Fields that may be problematic:")
                for key, value in data.items():
                    try:
                        json.dumps(value)
                    except Exception as e:
                        print(f"  - {key}: {str(e)}")
            
            # Call original function
            return await original_broadcast_to_room(self, room_code, message_type, data, redis_manager)
        except Exception as e:
            print(f"Exception in debug_broadcast_to_room: {str(e)}")
            traceback.print_exc()
            raise
    
    # Debug version of send_message
    async def debug_send_message(self, websocket, message_type, data):
        try:
            print(f"\n==== SEND MESSAGE DEBUG ====")
            print(f"Sending '{message_type}' to client")
            print(f"Data to send: {json.dumps(data, indent=2, default=str)}")
            
            # Test JSON serialization
            try:
                msg = {"type": message_type, "data": data}
                json_str = json.dumps(msg)
                print("Message is JSON serializable")
            except Exception as e:
                print(f"ERROR: Message is NOT JSON serializable: {str(e)}")
                print("Fields that may be problematic:")
                for key, value in data.items():
                    try:
                        json.dumps(value)
                    except Exception as e:
                        print(f"  - {key}: {str(e)}")
            
            # Call original function
            return await original_send_message(self, websocket, message_type, data)
        except Exception as e:
            print(f"Exception in debug_send_message: {str(e)}")
            traceback.print_exc()
            raise
    
    # Apply patches
    GameServer.handle_play_card = debug_handle_play_card
    NetworkManager.broadcast_to_room = debug_broadcast_to_room
    NetworkManager.send_message = debug_send_message
    
    print("Server functions patched with debug versions")

def restore_server_functions():
    """Restore original functions"""
    GameServer.handle_play_card = original_handle_play_card
    NetworkManager.broadcast_to_room = original_broadcast_to_room
    NetworkManager.send_message = original_send_message
    print("Original server functions restored")

async def simulate_client():
    """Simulate a client connecting and playing A_hearts"""
    try:
        uri = "ws://localhost:8765"
        print(f"Connecting to server at {uri}...")
        
        async with websockets.connect(uri) as websocket:
            print("Connected to server")
            
            # Join a game room
            room_code = "debug_room"
            join_message = {
                "type": "join",
                "room_code": room_code
            }
            await websocket.send(json.dumps(join_message))
            response = await websocket.recv()
            print(f"Server response: {response}")
            
            # Parse player_id from the response
            response_data = json.loads(response)
            player_id = response_data.get('data', {}).get('player_id')
            
            if not player_id:
                print("Error: Could not get player_id from server response")
                return
            
            # If we're allowed to play (would require 4 players in real game)
            # For testing we'd need to automatically fill the room or modify the server for test mode
            
            # Play A_hearts
            play_card_message = {
                "type": "play_card",
                "room_code": room_code,
                "player_id": player_id,
                "card": "A_hearts"
            }
            
            print(f"Sending play_card message: {json.dumps(play_card_message, indent=2)}")
            await websocket.send(json.dumps(play_card_message))
            
            # Try to receive a response - this will timeout if the server closes the connection
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                print(f"Server response after play_card: {response}")
            except asyncio.TimeoutError:
                print("Timeout waiting for server response - connection may have closed")
            
    except websockets.exceptions.ConnectionClosedError as e:
        print(f"Connection closed with error: {e}")
    except Exception as e:
        print(f"Client simulation error: {str(e)}")
        traceback.print_exc()

def print_instructions():
    """Print instructions for using this debug script"""
    print("""
=== ACE OF HEARTS BUG DEBUGGING HELPER ===

This script provides two ways to debug the issue:

1. Run your server normally, then execute this script with:
   python tests/debug_ace_hearts.py client
   
   This will simulate a client connecting and playing A_hearts.

2. Patch your server code with extensive logging by adding this to server.py:
   
   from tests.debug_ace_hearts import patch_server_functions
   # At the top of main() function:
   patch_server_functions()
   
   Then run your server normally and play the game until the bug occurs.

The issue might be related to:
- Data in `result` dictionary from play_card() method
- JSON serialization errors when broadcasting
- An exception when processing hand completion
""")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "client":
        asyncio.run(simulate_client())
    else:
        print_instructions()
