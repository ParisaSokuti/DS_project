#!/usr/bin/env python3
"""
Test to reproduce the server disconnect bug when a valid card is played
after multiple invalid suit-following attempts.
"""

import asyncio
import websockets
import json
import time
import pytest
import sys
import os

# Add backend directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from server import GameServer
from redis_manager import RedisManager

class TestServerDisconnectBug:
    
    def setup_method(self):
        """Set up test environment"""
        self.redis_manager = RedisManager()
        self.game_server = GameServer()
        self.server_task = None
        self.room_code = "TEST_DISCONNECT"
        
    def teardown_method(self):
        """Clean up test environment"""
        if self.server_task:
            self.server_task.cancel()
        # Clear test room
        self.redis_manager.clear_room(self.room_code)
    
    async def start_test_server(self):
        """Start test server"""
        async def handle_connection(websocket, path):
            try:
                print(f"[TEST] New connection from {websocket.remote_address}")
                async for message in websocket:
                    try:
                        data = json.loads(message)
                        await self.game_server.handle_message(websocket, data)
                    except json.JSONDecodeError:
                        await self.game_server.network_manager.notify_error(websocket, "Invalid message format")
                    except Exception as e:
                        print(f"[TEST ERROR] Failed to process message: {str(e)}")
                        import traceback
                        traceback.print_exc()
                        try:
                            await self.game_server.network_manager.notify_error(websocket, f"Internal server error: {str(e)}")
                        except Exception as notify_err:
                            print(f"[TEST ERROR] Failed to notify user of connection error: {notify_err}")
                            break  # This might be causing the disconnect!
            except websockets.ConnectionClosed:
                print("[TEST] Connection closed")
                await self.game_server.handle_connection_closed(websocket)
            except Exception as e:
                print(f"[TEST ERROR] Connection handler error: {str(e)}")
                import traceback
                traceback.print_exc()
        
        return await websockets.serve(handle_connection, "localhost", 8766)
    
    async def simulate_client(self, username, player_id):
        """Simulate a client connection"""
        uri = "ws://localhost:8766"
        try:
            async with websockets.connect(uri) as websocket:
                print(f"[CLIENT {username}] Connected to server")
                
                # Join room
                join_msg = {
                    "type": "join",
                    "username": username,
                    "room_code": self.room_code,
                    "player_id": player_id
                }
                await websocket.send(json.dumps(join_msg))
                
                # Listen for messages
                messages = []
                async for message in websocket:
                    data = json.loads(message)
                    messages.append(data)
                    print(f"[CLIENT {username}] Received: {data['type']}")
                    
                    # Auto-respond to certain messages
                    if data['type'] == 'hokm_selection_request' and username == 'hakem':
                        hokm_msg = {
                            "type": "hokm_selection",
                            "room_code": self.room_code,
                            "suit": "hearts"
                        }
                        await websocket.send(json.dumps(hokm_msg))
                    
                    elif data['type'] == 'turn_start' and data.get('your_turn'):
                        # This is where we'll test the bug
                        hand = data.get('hand', [])
                        if hand:
                            # Simulate the bug scenario:
                            # 1. Try to play invalid cards (suit-following violation)
                            # 2. Then play a valid card
                            
                            # First, try invalid cards
                            invalid_cards = [card for card in hand if not self.is_valid_follow_suit(card, hand)]
                            for invalid_card in invalid_cards[:2]:  # Try 2 invalid cards
                                play_msg = {
                                    "type": "play_card",
                                    "room_code": self.room_code,
                                    "player_id": player_id,
                                    "card": invalid_card
                                }
                                await websocket.send(json.dumps(play_msg))
                                await asyncio.sleep(0.1)  # Brief delay
                            
                            # Then play a valid card
                            valid_card = hand[0]  # Just pick the first card as valid
                            play_msg = {
                                "type": "play_card",
                                "room_code": self.room_code,
                                "player_id": player_id,
                                "card": valid_card
                            }
                            await websocket.send(json.dumps(play_msg))
                            print(f"[CLIENT {username}] Played valid card: {valid_card}")
                            
                            # Check if connection closes after this
                            try:
                                # Wait for server response
                                response = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                                response_data = json.loads(response)
                                print(f"[CLIENT {username}] Response to valid card: {response_data['type']}")
                                return True  # Connection stayed alive
                            except asyncio.TimeoutError:
                                print(f"[CLIENT {username}] No response from server - possible disconnect")
                                return False
                            except websockets.ConnectionClosed:
                                print(f"[CLIENT {username}] Connection closed after valid card!")
                                return False
                
                return messages
                
        except Exception as e:
            print(f"[CLIENT {username}] Connection error: {str(e)}")
            return False
    
    def is_valid_follow_suit(self, card, hand):
        """Simple suit-following check (simplified for testing)"""
        # This is a simplified version - in real game, it depends on led suit
        # For testing, we'll just assume some cards are invalid
        suit = card.split('_')[1] if '_' in card else ''
        return suit == 'hearts'  # Assume hearts is always valid for simplicity
    
    @pytest.mark.asyncio
    async def test_server_disconnect_bug(self):
        """Test that server doesn't disconnect after valid card following invalid attempts"""
        print("\n=== Testing Server Disconnect Bug ===")
        
        # Clear any existing room
        self.redis_manager.clear_room(self.room_code)
        
        # Start test server
        server = await self.start_test_server()
        
        try:
            # Create 4 players
            players = [
                ("player1", "p1"),
                ("player2", "p2"), 
                ("player3", "p3"),
                ("player4", "p4")
            ]
            
            # Set up game manually to get to gameplay phase quickly
            await self.setup_test_game()
            
            # Test the disconnect bug with one player
            username, player_id = players[0]
            connection_survived = await self.simulate_client(username, player_id)
            
            # Verify connection didn't close unexpectedly
            assert connection_survived, "Server closed connection after valid card play"
            
            print("✓ Server disconnect bug test passed")
            
        finally:
            server.close()
            await server.wait_closed()
    
    async def setup_test_game(self):
        """Set up a test game in gameplay phase"""
        # This would involve creating a game state where we can test card play
        # For now, this is a placeholder
        pass

if __name__ == "__main__":
    # Run the test
    async def run_test():
        test = TestServerDisconnectBug()
        test.setup_method()
        try:
            await test.test_server_disconnect_bug()
        finally:
            test.teardown_method()
    
    asyncio.run(run_test())
