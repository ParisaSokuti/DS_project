# server.py

import asyncio
import websockets
import json
import uuid
import random
from player import Player
from network import NetworkManager
from game_board import GameBoard

ROOM_SIZE = 4

# Single game storage system
rooms = {}  # room_code -> [Player objects]
games = {}  # room_code -> GameBoard instance
player_rooms = {}  # websocket -> room_code
player_objects = {}  # websocket -> Player object

# --- Force all users into a single room for testing (delete this block later) ---
SINGLE_TEST_ROOM = "9999"  # delete this line later
rooms[SINGLE_TEST_ROOM] = []  # delete this line later
# -------------------------------------------------------------------------------

def generate_room_code():
    return f"{random.randint(1000, 9999)}"

async def start_first_trick(room_code):
    """Initialize the first trick after trump selection"""
    game = games[room_code]
    game.current_turn = 0  # Hakem leads first trick
    first_player = game.players[game.current_turn]
    
    print(f"\n=== Starting first trick in room {room_code} ===")
    print(f"{first_player} (Hakem) leads the first trick")
    
    # Notify all players whose turn it is
    for p in rooms[room_code]:
        await NetworkManager.send_message(
            p.wsconnection,
            "turn_start",
            {
                "current_player": first_player,
                "your_turn": p.username == first_player,
                "hand": game.hands[p.username][:]
            }
        )

async def handle_game_start(room_code):
    """Initialize and start a new game for a full room"""
    player_objects = rooms[room_code]
    players = [p.username for p in player_objects]
    
    # Create new game instance
    game = GameBoard(players)
    games[room_code] = game
    
    # Assign teams and determine Hakem
    team_info = game.assign_teams_and_hakem()
    
    # Notify players about team assignments
    for p in rooms[room_code]:
        await NetworkManager.send_message(
            p.wsconnection,
            "team_assignment",
            {
                "teams": team_info["teams"],
                "hakem": team_info["hakem"],
                "you": p.username
            }
        )
    
    # Deal initial cards
    game.initial_deal()
    
    # Send initial hands and trump selection prompt
    for player in player_objects:
        if player.username == game.hakem:
            await NetworkManager.send_message(
                player.wsconnection,
                "initial_deal",
                {
                    "hand": game.hands[player.username][:],
                    "is_hakem": True,
                    "message": "You are the Hakem. Choose a trump suit based on your 5 cards."
                }
            )
        else:
            await NetworkManager.send_message(
                player.wsconnection,
                "initial_deal",
                {
                    "hand": game.hands[player.username][:],
                    "is_hakem": False,
                    "message": f"Waiting for {game.hakem} to choose trump suit."
                }
            )

async def handle_connection(websocket, path):
    # Receive join/create message
    join_msg = await NetworkManager.receive_message(websocket)
    if not join_msg:
        return

    username = join_msg.get("username", f"player{random.randint(100, 999)}")
    action = join_msg.get("type")
    # room_code = join_msg.get("room_code")  # delete this line later

    player_id = str(uuid.uuid4())
    player = Player(player_id=player_id, wsconnection=websocket, username=username)

    # Store player mapping
    player_objects[websocket] = player

    # --- Force all users into a single room for testing (delete this block later) ---
    room_code = SINGLE_TEST_ROOM  # delete this line later
    # -------------------------------------------------------------------------------

    # Room creation or joining
    if action == "create_room":
        # room_code = generate_room_code()  # delete this line later
        # rooms[room_code] = []  # delete this line later
        print(f"New room created: {room_code}")

    if action in ("join_room", "create_room"):
        if room_code not in rooms:
            await NetworkManager.send_message(websocket, "error", {
                "message": "Room does not exist. Please check the room code."
            })
            return
        elif len(rooms[room_code]) >= ROOM_SIZE:
            await NetworkManager.send_message(websocket, "room_full", {
                "message": "Room is already full. Do you want to create a new room? (y/n)"
            })
            return
        else:
            player.current_room = room_code
            player_rooms[websocket] = room_code
            rooms[room_code].append(player)
            player_number = len(rooms[room_code])
            print(f"Player {player_number}: {username} entered room [{room_code}]")

            # Broadcast updated room status to all players in the room
            await broadcast_room_status(room_code)

            # Start game if room is full
            if player_number == ROOM_SIZE:
                print(f"Room {room_code} is full, ready to play!")
                await handle_game_start(room_code)

    # Keep connection open for game messages
    try:
        while True:
            msg = await websocket.recv()
            data = json.loads(msg)
            room_code = player_rooms.get(websocket)
            
            # Handle room full response
            if data.get('type') == 'create_room' and data.get('response') == 'y':
                new_room_code = generate_room_code()
                rooms[new_room_code] = []
                player.current_room = new_room_code
                player_rooms[websocket] = new_room_code
                rooms[new_room_code].append(player)
                print(f"Player 1: {username} entered room [{new_room_code}]")
                await broadcast_room_status(new_room_code)
            
            # Handle trump selection
            elif data.get('type') == 'trump_selected':
                suit = data.get('suit')
                valid_suits = {'hearts', 'diamonds', 'clubs', 'spades'}
                
                if suit not in valid_suits:
                    await NetworkManager.send_message(websocket, "error", {
                        "message": "Invalid suit choice. Please choose from hearts/diamonds/clubs/spades"
                    })
                    continue
                
                game = games.get(room_code)
                if game and player.username == game.hakem:
                    if game.set_trump_suit(suit):
                        print(f"Suit of room {room_code} is currently [{suit}]")
                        print(f"hokm is {suit}")  # <-- Add this line
                        
                        # Broadcast trump selection to all players
                        for p in rooms[room_code]:
                            await NetworkManager.send_message(
                                p.wsconnection,
                                "trump_selected",
                                {"suit": suit, "hakem": game.hakem}
                            )
                        
                        # Deal remaining cards
                        game.final_deal()
                        for p in rooms[room_code]:
                            await NetworkManager.send_message(
                                p.wsconnection,
                                "final_deal",
                                {"hand": game.hands[p.username][:]}
                            )
                        
                        # Start first trick
                        await start_first_trick(room_code)
                    else:
                        await NetworkManager.send_message(websocket, "error", {
                            "message": "Failed to set trump suit"
                        })
            
            # Handle card play
            elif data.get('type') == 'play_card':
                game = games.get(room_code)
                if not game:
                    await NetworkManager.send_message(websocket, "error", {
                        "message": "Not in active game"
                    })
                    continue

                card = data.get('card')
                print(f"room [{room_code}], Player {player.username} played {card}")  # <-- Add this line
                result = game.play_card(player.username, card)
                
                if not result.get('valid'):
                    await NetworkManager.send_message(websocket, "error", {
                        "message": result.get('message', 'Invalid play')
                    })
                    continue

                # Broadcast played card to all players
                for p in rooms[room_code]:
                    await NetworkManager.send_message(
                        p.wsconnection,
                        "card_played",
                        {
                            "player": player.username,
                            "card": card,  # send raw card string
                            "remaining_hand": game.hands[p.username][:]
                        }
                    )

                # Handle completed trick
                if "trick_winner" in result:
                    print(f"Trick won by {result['trick_winner']}. Team 1: {game.tricks[0]} tricks, Team 2: {game.tricks[1]} tricks.")
                    
                    # Broadcast trick result
                    for p in rooms[room_code]:
                        await NetworkManager.send_message(
                            p.wsconnection,
                            "trick_result",
                            {
                                "winner": result["trick_winner"],
                                "team1_tricks": game.tricks[0],
                                "team2_tricks": game.tricks[1]
                            }
                        )
                    
                    # Check for hand end (7 tricks won)
                    if game.tricks[0] >= 7 or game.tricks[1] >= 7:
                        winning_team = 0 if game.tricks[0] >= 7 else 1
                        game.update_score(winning_team)
                        
                        for p in rooms[room_code]:
                            await NetworkManager.send_message(
                                p.wsconnection,
                                "hand_complete",
                                {
                                    "winning_team": winning_team,
                                    "scores": game.scores,
                                    "tricks": game.tricks
                                }
                            )
                        
                        # Check for game end (7 points)
                        if game.is_game_over():
                            for p in rooms[room_code]:
                                await NetworkManager.send_message(
                                    p.wsconnection,
                                    "game_over",
                                    {
                                        "winning_team": 0 if game.scores[0] >= 7 else 1,
                                        "final_scores": game.scores
                                    }
                                )
                            # Clean up game
                            del games[room_code]
                            return

                # Count hand completion for round tracking
                if result.get('hand_complete'):
                    # Count how many hands have been completed in this game
                    if not hasattr(game, 'round_number'):
                        game.round_number = 1
                    else:
                        game.round_number += 1
                    print(f"room [{room_code}], Round {game.round_number} finished")

                # Start next turn
                next_player = game.players[game.current_turn]
                for p in rooms[room_code]:
                    hand = [c for c in game.hands[p.username] if c not in game.played_cards]
                    await NetworkManager.send_message(
                        p.wsconnection,
                        "turn_start",
                        {
                            "current_player": next_player,
                            "your_turn": p.username == next_player,
                            "hand": hand
                        }
                    )
                    
    except websockets.ConnectionClosed:
        print(f"Player {username} disconnected.")
        # Clean up player mappings
        if websocket in player_objects:
            del player_objects[websocket]
        if websocket in player_rooms:
            room_code = player_rooms[websocket]
            del player_rooms[websocket]
            
            # Remove player from room
            if room_code in rooms and player in rooms[room_code]:
                rooms[room_code].remove(player)
                if not rooms[room_code]:
                    # Clean up empty room
                    del rooms[room_code]
                    if room_code in games:
                        del games[room_code]
                else:
                    # Broadcast updated room status
                    await broadcast_room_status(room_code)

async def broadcast_room_status(room_code):
    """Broadcast current room status to all players"""
    players = rooms[room_code]
    usernames = [p.username for p in players]
    
    for idx, p in enumerate(players):
        await NetworkManager.send_message(
            p.wsconnection,
            "room_status",
            {
                "room_id": room_code,
                "player_number": idx + 1,
                "your_name": p.username,
                "usernames": usernames,
                "total_players": len(players)
            }
        )

async def main():
    print("Starting Hokm WebSocket server on ws://0.0.0.0:8765")
    async with websockets.serve(handle_connection, "0.0.0.0", 8765):
        await asyncio.Future()  # Run forever

if __name__ == "__main__":
    asyncio.run(main())
