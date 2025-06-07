# server.py

import asyncio
import websockets
import json
import uuid
import random
from player import Player
from network import NetworkManager

ROOM_SIZE = 4

# In-memory structures for demo; use Redis for production
rooms = {}

def generate_room_code():
    return f"{random.randint(1000, 9999)}"

async def handle_connection(websocket, path):
    # Receive join/create message
    join_msg = await NetworkManager.receive_message(websocket)
    if not join_msg:
        return
    username = join_msg.get("username", "Anonymous")
    action = join_msg.get("type")
    room_code = join_msg.get("room_code")

    player_id = str(uuid.uuid4())
    player = Player(player_id=player_id, wsconnection=websocket, username=username)
    player.current_room = None

    # Room creation or joining
    if action == "create_room":
        room_code = generate_room_code()
        rooms[room_code] = []
        print(f"New room created: {room_code}")

    if action in ("join_room", "create_room"):
        if room_code not in rooms:
            await NetworkManager.send_message(websocket, "error", {
                "message": "Room does not exist. Please check the room code."
            })
            # Don't return, keep connection open for retry
        elif len(rooms[room_code]) >= ROOM_SIZE:
            await NetworkManager.send_message(websocket, "room_full", {
                "message": "Room is already full. Do you want to create a new room? (y/n)"
            })
            # Don't close connection yet; wait for client response!
        else:
            player.current_room = room_code
            rooms[room_code].append(player)
            player_number = len(rooms[room_code])
            print(f"Player {player_number}: {username} entered room [{room_code}]")

            # Broadcast updated room status to all players in the room
            await broadcast_room_status(room_code)

            await NetworkManager.send_message(websocket, "room_joined", {
                "room_id": room_code,
                "player_number": player_number,
                "total_players": player_number
            })

            # Notify all players if room is full
            if player_number == ROOM_SIZE:
                print(f"Room {room_code} is full, ready to play!")
                for p in rooms[room_code]:
                    await NetworkManager.send_message(
                        p.wsconnection,
                        "game_start",
                        {
                            "room_id": room_code,
                            "players": [pl.username for pl in rooms[room_code]]
                        }
                    )

    else:
        await NetworkManager.send_message(websocket, "error", {
            "message": "Invalid action."
        })

    # Keep connection open for future game logic
    try:
        while True:
            msg = await websocket.recv()
            data = json.loads(msg)
            
            # Handle new join attempts
            if data.get('type') in ('join_room', 'create_room'):
                room_code = data.get('room_code')
                if data.get('type') == 'create_room':
                    room_code = generate_room_code()
                    rooms[room_code] = []
                    print(f"New room created: {room_code}")
                
                if room_code not in rooms:
                    await NetworkManager.send_message(websocket, "error", {
                        "message": "Room does not exist. Please check the room code."
                    })
                elif len(rooms[room_code]) >= ROOM_SIZE:
                    await NetworkManager.send_message(websocket, "room_full", {
                        "message": "Room is already full. Do you want to create a new room? (y/n)"
                    })
                else:
                    player.current_room = room_code
                    rooms[room_code].append(player)
                    player_number = len(rooms[room_code])
                    print(f"Player {player_number}: {username} entered room [{room_code}]")
                    await broadcast_room_status(room_code)
                    await NetworkManager.send_message(websocket, "room_joined", {
                        "room_id": room_code,
                        "player_number": player_number,
                        "total_players": player_number
                    })
                    if player_number == ROOM_SIZE:
                        print(f"Room {room_code} is full, ready to play!")
                        for p in rooms[room_code]:
                            await NetworkManager.send_message(
                                p.wsconnection,
                                "game_start",
                                {
                                    "room_id": room_code,
                                    "players": [pl.username for pl in rooms[room_code]]
                                }
                            )
            elif data.get('type') == 'room_status':
                await broadcast_room_status(data.get('room_id'))
            elif data.get('type') == 'room_full':
                print(data.get('message'))
            elif data.get('type') == 'error':
                print("Error:", data.get('message'))
    except websockets.ConnectionClosed:
        print(f"Player {username} disconnected.")
        if player.current_room and player in rooms.get(player.current_room, []):
            rooms[player.current_room].remove(player)
            if not rooms[player.current_room]:
                del rooms[player.current_room]
            else:
                # Broadcast updated room status to remaining players
                await broadcast_room_status(player.current_room)

async def broadcast_room_status(room_code):
    players = rooms[room_code]
    for idx, p in enumerate(players):
        await NetworkManager.send_message(
            p.wsconnection,
            "room_status",
            {
                "room_id": room_code,
                "player_number": idx + 1,
                "total_players": len(players),
                "usernames": [pl.username for pl in players]
            }
        )

async def main():
    print("Starting Hokm WebSocket server on ws://0.0.0.0:8765")
    async with websockets.serve(handle_connection, "0.0.0.0", 8765):
        await asyncio.Future()  # Run forever

if __name__ == "__main__":
    asyncio.run(main())
