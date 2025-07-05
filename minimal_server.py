#!/usr/bin/env python3
"""
Minimal Hokm Server for Testing
This version bypasses problematic Redis operations to get basic functionality working.
"""

import asyncio
import websockets
import json
import uuid
import time

class MinimalGameServer:
    def __init__(self):
        self.active_connections = {}  # websocket -> player_info
        self.rooms = {}  # room_code -> list of players
        
    async def handle_connection(self, websocket, path):
        print(f"[LOG] New connection from {websocket.remote_address}")
        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    await self.handle_message(websocket, data)
                except json.JSONDecodeError:
                    await self.send_error(websocket, "Invalid JSON message")
                except Exception as e:
                    print(f"[ERROR] Message handling error: {e}")
                    await self.send_error(websocket, f"Error: {str(e)}")
        except websockets.exceptions.ConnectionClosed:
            print(f"[LOG] Connection closed for {websocket.remote_address}")
        except Exception as e:
            print(f"[ERROR] Connection error: {e}")
        finally:
            await self.handle_disconnect(websocket)
    
    async def handle_message(self, websocket, data):
        print(f"[DEBUG] Received message: {data}")
        msg_type = data.get('type')
        
        if msg_type == 'join':
            await self.handle_join(websocket, data)
        elif msg_type == 'reconnect':
            await self.handle_reconnect(websocket, data)
        else:
            await self.send_error(websocket, f"Unknown message type: {msg_type}")
    
    async def handle_join(self, websocket, data):
        room_code = data.get('room_code', '9999')
        username = data.get('username', 'Player')
        
        # Create player info
        player_id = str(uuid.uuid4())
        player_number = len(self.rooms.get(room_code, [])) + 1
        player_name = f"Player {player_number}"
        
        # Store connection info
        self.active_connections[websocket] = {
            'player_id': player_id,
            'username': player_name,
            'room_code': room_code,
            'player_number': player_number
        }
        
        # Add to room
        if room_code not in self.rooms:
            self.rooms[room_code] = []
        
        self.rooms[room_code].append({
            'player_id': player_id,
            'username': player_name,
            'player_number': player_number,
            'websocket': websocket
        })
        
        # Send success response
        await self.send_message(websocket, 'join_success', {
            'username': player_name,
            'player_id': player_id,
            'room_code': room_code,
            'player_number': player_number
        })
        
        print(f"[LOG] {player_name} joined room {room_code} ({len(self.rooms[room_code])}/4 players)")
        
        # Start game if room is full
        if len(self.rooms[room_code]) >= 4:
            await self.start_game(room_code)
    
    async def handle_reconnect(self, websocket, data):
        player_id = data.get('player_id')
        await self.send_message(websocket, 'reconnect_failed', {
            'message': 'Reconnection not supported in minimal server'
        })
    
    async def start_game(self, room_code):
        print(f"[LOG] Starting game in room {room_code}")
        
        # Broadcast to all players in room
        message = {
            'type': 'game_started',
            'message': 'Game is starting! All 4 players connected.',
            'players': len(self.rooms[room_code])
        }
        
        for player in self.rooms[room_code]:
            try:
                await self.send_message(player['websocket'], 'game_started', message)
            except Exception as e:
                print(f"[ERROR] Failed to notify player: {e}")
    
    async def handle_disconnect(self, websocket):
        if websocket in self.active_connections:
            player_info = self.active_connections[websocket]
            room_code = player_info['room_code']
            username = player_info['username']
            
            # Remove from room
            if room_code in self.rooms:
                self.rooms[room_code] = [p for p in self.rooms[room_code] if p['websocket'] != websocket]
                if not self.rooms[room_code]:
                    del self.rooms[room_code]
            
            # Remove connection
            del self.active_connections[websocket]
            
            print(f"[LOG] {username} disconnected from room {room_code}")
    
    async def send_message(self, websocket, msg_type, data):
        message = {'type': msg_type, **data}
        try:
            await websocket.send(json.dumps(message))
        except Exception as e:
            print(f"[ERROR] Failed to send message: {e}")
    
    async def send_error(self, websocket, error_msg):
        await self.send_message(websocket, 'error', {'message': error_msg})

async def main():
    print("Starting Minimal Hokm WebSocket server on ws://0.0.0.0:8765")
    server = MinimalGameServer()
    
    async with websockets.serve(server.handle_connection, "0.0.0.0", 8765):
        print("INFO:server:server listening on 0.0.0.0:8765")
        await asyncio.Future()  # Run forever

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nMinimal server shutting down...")
    except Exception as e:
        print(f"[ERROR] Server error: {e}")
        import traceback
        traceback.print_exc()
