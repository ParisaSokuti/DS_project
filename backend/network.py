# network.py (Backend)
import asyncio
import json
import uuid
import redis
import websockets
from websockets.server import serve, WebSocketServerProtocol
from typing import Dict, Optional

class NetworkManager:
    def __init__(self):
        self.redis = redis.Redis(host='localhost', port=6379, db=0)
        self.active_connections: Dict[str, WebSocketServerProtocol] = {}
        self.player_rooms: Dict[str, str] = {}

    async def handle_connection(self, websocket):
        """Main WebSocket connection handler"""
        player_id = str(uuid.uuid4())
        self.active_connections[player_id] = websocket
        
        try:
            async for message in websocket:
                await self.route_message(player_id, json.loads(message))
        except websockets.ConnectionClosed:
            await self.handle_disconnect(player_id)

    async def route_message(self, player_id: str, data: dict):
        """Route incoming messages to appropriate handlers"""
        msg_type = data.get('type')
        handler = {
            'authenticate': self.handle_auth,
            'join_queue': self.handle_queue,
            'play_card': self.handle_game_action,
            'keepalive': lambda pid, d: None
        }.get(msg_type)
        
        if handler:
            await handler(player_id, data)
        else:
            await self.send(player_id, {'type': 'error', 'message': 'Invalid message type'})

    async def handle_auth(self, player_id: str, data: dict):
        """Authentication handler"""
        # Implement your actual auth logic here
        success = True  # Replace with real auth check
        if success:
            await self.send(player_id, {
                'type': 'auth_success',
                'token': 'generated_jwt_token'
            })
        else:
            await self.send(player_id, {'type': 'auth_failed'})

    async def handle_queue(self, player_id: str, data: dict):
        """Matchmaking queue handler"""
        game_type = data.get('game_type', '4p')
        lobby_key = f'lobby:{game_type}'
        
        # Add to Redis queue
        self.redis.rpush(lobby_key, player_id)
        
        # Check if ready to start game
        queue_size = self.redis.llen(lobby_key)
        if queue_size >= (4 if game_type == '4p' else 2):
            players = [self.redis.lpop(lobby_key).decode() for _ in range(queue_size)]
            await self.create_game(players, game_type)

    async def create_game(self, player_ids: list, game_type: str):
        """Initialize new game room"""
        room_id = str(uuid.uuid4())[:8]
        game_state = {
            'players': player_ids,
            'status': 'starting',
            'trump_suit': None,
            'current_turn': 0
        }
        
        # Store in Redis
        self.redis.hset(f'game:{room_id}', mapping=game_state)
        
        # Notify players
        for pid in player_ids:
            self.player_rooms[pid] = room_id
            await self.send(pid, {
                'type': 'game_start',
                'room_id': room_id,
                'players': player_ids
            })

    async def handle_game_action(self, player_id: str, data: dict):
        """Handle in-game actions"""
        room_id = self.player_rooms.get(player_id)
        if not room_id:
            return
            
        # Validate game state
        game_state = self.redis.hgetall(f'game:{room_id}')
        if not game_state:
            return

        # Broadcast to other players
        for pid in json.loads(game_state[b'players']):
            if pid != player_id:
                await self.send(pid, {
                    'type': 'game_update'
                })

    @staticmethod
    async def send_message(
        websocket: WebSocketServerProtocol,
        message_type: str,
        data: dict = None
    ):
        """Send a JSON message over the websocket."""
        message = {"type": message_type}
        if data:
            message.update(data)
        try:
            await websocket.send(json.dumps(message))
        except websockets.ConnectionClosed:
            print("Connection closed while sending message")

    @staticmethod
    async def receive_message(websocket):
        try:
            message = await websocket.recv()
            return json.loads(message)
        except websockets.ConnectionClosed:
            print("Connection closed while receiving message")
            return None
        except json.JSONDecodeError:
            print("Invalid JSON received")
            return None
