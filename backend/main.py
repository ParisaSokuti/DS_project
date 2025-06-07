# main.py
import asyncio
import websockets
import json
from auth import register_user, authenticate_user
from lobby import assign_player_to_room, get_room_players

async def handler(websocket, path):
    # Step 1: Authentication
    msg = await websocket.recv()
    data = json.loads(msg)
    action = data.get('action')
    username = data.get('username')
    password = data.get('password')

    if action == 'register':
        if register_user(username, password):
            await websocket.send(json.dumps({'status': 'success', 'msg': 'Registered!'}))
        else:
            await websocket.send(json.dumps({'status': 'error', 'msg': 'Username exists'}))
        return

    if action == 'login':
        if authenticate_user(username, password):
            await websocket.send(json.dumps({'status': 'success', 'msg': 'Login successful'}))
        else:
            await websocket.send(json.dumps({'status': 'error', 'msg': 'Invalid credentials'}))
        return

    # Step 2: Lobby assignment (after login)
    if action == 'join_lobby':
        room_code, player_number = assign_player_to_room(username)
        await websocket.send(json.dumps({
            'status': 'joined',
            'room_code': room_code,
            'player_number': player_number,
            'msg': f"Player {player_number}: {username} entered the room [{room_code}]"
        }))
        if player_number == 4:
            players = get_room_players(room_code)
            print(f"Room {room_code} is full, ready to play... Players: {players}")

async def main():
    print("Starting Hokm WebSocket server on ws://0.0.0.0:8765")
    async with websockets.serve(handler, "0.0.0.0", 8765):
        await asyncio.Future()  # Run forever

if __name__ == "__main__":
    asyncio.run(main())
