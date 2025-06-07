# lobby.py
import random
import redis
import json

redis_client = redis.Redis(host='localhost', port=6379, db=0)

def generate_room_code() -> str:
    # 4-digit room code, zero-padded
    return f"{random.randint(1000, 9999)}"

def assign_player_to_room(username: str) -> tuple[str, int]:
    # Find or create a room with <4 players
    room_code = redis_client.get('current_room_code')
    if not room_code:
        room_code = generate_room_code()
        redis_client.set('current_room_code', room_code)
        redis_client.delete(f'room:{room_code}:players')

    room_code = room_code.decode() if isinstance(room_code, bytes) else room_code
    players_key = f'room:{room_code}:players'
    players = redis_client.lrange(players_key, 0, -1)
    player_number = len(players) + 1

    redis_client.rpush(players_key, username)
    if player_number == 4:
        # Room is full, reset for next game
        redis_client.delete('current_room_code')
    return room_code, player_number

def get_room_players(room_code: str):
    players_key = f'room:{room_code}:players'
    return [p.decode() for p in redis_client.lrange(players_key, 0, -1)]
