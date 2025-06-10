# network.py (Backend)
import asyncio
import json
import websockets
import time
from typing import Dict, Optional, Any, Union
from websockets.server import WebSocketServerProtocol
from websockets.client import WebSocketClientProtocol
from redis_manager import RedisManager

# Type alias for websocket connections
WebSocket = Union[WebSocketServerProtocol, WebSocketClientProtocol]

class NetworkManager:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(NetworkManager, cls).__new__(cls)
            cls._instance.initialized = False
        return cls._instance
    
    def __init__(self):
        if not self.initialized:
            self.redis_manager = RedisManager()
            self.initialized = True
    
    @staticmethod
    async def send_message(websocket: WebSocket, message_type: str, data: Optional[Dict[str, Any]] = None) -> bool:
        """Send a message to a websocket with proper error handling"""
        try:
            message = {"type": message_type}
            if data:
                message.update(data)
            await websocket.send(json.dumps(message))
            return True
        except websockets.ConnectionClosed:
            print("[ERROR] Connection closed while sending message")
            return False
        except Exception as e:
            print(f"[ERROR] Failed to send message: {str(e)}")
            return False
            
    @staticmethod
    async def broadcast_to_room(room_code: str, msg_type: str, data: Dict[str, Any], redis_manager: RedisManager):
        """Broadcast a message to all players in a room"""
        try:
            players = redis_manager.get_room_players(room_code)
            for player in players:
                if 'wsconnection' in player:
                    await NetworkManager.send_message(
                        player['wsconnection'],
                        msg_type,
                        data
                    )
        except Exception as e:
            print(f"[ERROR] Failed to broadcast to room {room_code}: {str(e)}")
            
    @staticmethod
    async def broadcast_game_state(room_code: str, game_state: Dict[str, Any], redis_manager: RedisManager):
        """Broadcast current game state to all players in a room"""
        try:
            players = redis_manager.get_room_players(room_code)
            for player in players:
                if 'wsconnection' in player and 'username' in player:
                    # Customize state data for each player
                    player_state = game_state.copy()
                    player_state.update({
                        'you': player['username'],
                        'hand': json.loads(game_state.get(f'hand_{player["username"]}', '[]')),
                        'your_team': "1" if player['username'] in json.loads(game_state['teams'])['1'] else "2"
                    })
                    await NetworkManager.send_message(
                        player['wsconnection'],
                        'game_state',
                        player_state
                    )
        except Exception as e:
            print(f"[ERROR] Failed to broadcast game state to room {room_code}: {str(e)}")
            
    @staticmethod
    async def notify_error(websocket, message: str):
        """Send an error message to a websocket"""
        await NetworkManager.send_message(
            websocket,
            'error',
            {'message': message}
        )

    @staticmethod
    async def handle_player_connected(websocket, room_code: str, player_data: Dict[str, Any], redis_manager: RedisManager):
        """Handle new player connection"""
        try:
            # Save session and room data
            redis_manager.save_player_session(
                player_data['player_id'],
                {
                    'username': player_data['username'],
                    'room_code': room_code,
                    'connected_at': str(int(time.time())),
                    'expires_at': str(int(time.time()) + 3600)
                }
            )

            # Add to room
            redis_manager.add_player_to_room(room_code, {
                **player_data,
                'joined_at': str(int(time.time()))
            })

            # Send confirmation
            await NetworkManager.send_message(
                websocket,
                'join_success',
                {
                    'username': player_data['username'],
                    'player_id': player_data['player_id'],
                    'room_code': room_code,
                    'player_number': player_data.get('player_number', 0)
                }
            )

            print(f"[LOG] Player {player_data['username']} connected to room {room_code}")
            return True

        except Exception as e:
            print(f"[ERROR] Failed to handle player connection: {str(e)}")
            await NetworkManager.notify_error(websocket, "Failed to join room")
            return False

    @staticmethod
    async def handle_player_disconnected(room_code: str, player_data: Dict[str, Any], redis_manager: RedisManager):
        """Handle player disconnection"""
        try:
            # Save disconnect time
            redis_manager.save_player_session(
                player_data['player_id'],
                {
                    'disconnected_at': str(int(time.time())),
                    'room_code': room_code
                }
            )

            print(f"[LOG] Player {player_data['username']} disconnected from room {room_code}")

            # Notify other players
            await NetworkManager.broadcast_to_room(
                room_code,
                'player_disconnected',
                {
                    'username': player_data['username'],
                    'temporary': True  # Allow reconnection
                },
                redis_manager
            )

        except Exception as e:
            print(f"[ERROR] Failed to handle player disconnection: {str(e)}")
            
    @staticmethod
    async def handle_player_reconnected(websocket, room_code: str, player_data: Dict[str, Any], redis_manager: RedisManager):
        """Handle player reconnection"""
        try:
            # Update session
            redis_manager.save_player_session(
                player_data['player_id'],
                {
                    'reconnected_at': str(int(time.time())),
                    'expires_at': str(int(time.time()) + 3600),
                    'room_code': room_code
                }
            )

            # Get current game state
            game_state = redis_manager.get_game_state(room_code)
            if game_state:
                await NetworkManager.broadcast_game_state(room_code, game_state, redis_manager)

            print(f"[LOG] Player {player_data['username']} reconnected to room {room_code}")

            # Notify other players
            await NetworkManager.broadcast_to_room(
                room_code,
                'player_reconnected',
                {'username': player_data['username']},
                redis_manager
            )

            return True

        except Exception as e:
            print(f"[ERROR] Failed to handle player reconnection: {str(e)}")
            await NetworkManager.notify_error(websocket, "Failed to reconnect")
            return False

    @staticmethod
    async def receive_message(websocket: WebSocket) -> Optional[Dict[str, Any]]:
        """Receive and parse a JSON message from websocket"""
        try:
            message = await websocket.recv()
            return json.loads(message)
        except websockets.ConnectionClosed:
            print("[ERROR] Connection closed while receiving message")
            return None
        except json.JSONDecodeError:
            print("[ERROR] Invalid JSON received")
            return None
