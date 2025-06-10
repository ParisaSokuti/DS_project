# server.py

import asyncio
import sys
import websockets
import json
import uuid
import random
import time
from player import Player
from network import NetworkManager
from game_board import GameBoard
from game_states import GameState
from redis_manager import RedisManager
from auth import register_user, authenticate_user

# Constants
ROOM_SIZE = 4    # Single game storage system

# Redis integration
redis_manager = RedisManager()

# Keep only WebSocket references in memory
# These can't be stored in Redis since they are live connections
player_rooms = {}  # Maps WebSocket -> room_code for quick lookup
player_objects = {}  # Maps WebSocket -> Player object for active connections
active_games = {}   # Maps room_code -> GameBoard for active games only

# Fixed room for testing
SINGLE_TEST_ROOM = "9999"
redis_manager.create_room(SINGLE_TEST_ROOM)

async def handle_join(websocket, data):
    try:
        room_code = data.get('room_code', '9999')
        base_username = data.get('username', 'player')
        
        # Check if room is full before allowing join
        room_players = redis_manager.get_room_players(room_code)
        if len(room_players) >= ROOM_SIZE:
            await NetworkManager.send_message(
                websocket,
                "error",
                {"message": "Room is full"}
            )
            return None
        
        # Assign player number based on room size
        player_number = len(room_players) + 1
        username = f"Player {player_number}"
        
        # Create new player object with sequential number
        player_id = str(uuid.uuid4())
        player = Player(player_id=player_id, wsconnection=websocket, username=username)
        
        # Save player session data with 1 hour expiration
        session_data = {
            'username': username,
            'room_code': room_code,
            'connected_at': str(int(time.time())),
            'player_id': player_id,
            'expires_at': str(int(time.time()) + 3600)  # 1 hour expiration
        }
        
        try:
            redis_manager.save_player_session(player_id, session_data)
        except Exception as e:
            print(f"[ERROR] Failed to save session: {str(e)}")
            await NetworkManager.send_message(
                websocket,
                "error",
                {"message": "Failed to create session"}
            )
            return None
        
        # Store player object in memory
        player_objects[websocket] = player
        
        # Create or join room
        try:
            if not redis_manager.room_exists(room_code):
                redis_manager.create_room(room_code)
                print(f"[LOG] Room {room_code} is created [PHASE: {GameState.WAITING_FOR_PLAYERS.value}]")
                
            # Add to room with extra metadata
            redis_manager.add_player_to_room(room_code, {
                'username': username,
                'player_id': player_id,
                'joined_at': str(int(time.time())),
                'player_number': player_number
            })
            player_rooms[websocket] = room_code
            
            # Send join confirmation
            await NetworkManager.send_message(
                websocket,
                "join_success",
                {
                    "username": username,
                    "player_id": player_id,
                    "room_code": room_code,
                    "player_number": player_number
                }
            )
            
            print(f"[LOG] Room {room_code}: {username} joined [PHASE: {GameState.WAITING_FOR_PLAYERS.value}]")
            
            # Notify all players in the room about the new player
            await broadcast_room_status(room_code)
            return player
            
        except Exception as e:
            print(f"[ERROR] Failed to join room: {str(e)}")
            # Clean up on failure
            if player_id:
                redis_manager.delete_player_session(player_id)
            if websocket in player_objects:
                del player_objects[websocket]
            await NetworkManager.send_message(
                websocket,
                "error",
                {"message": "Failed to join room"}
            )
            return None
            
    except Exception as e:
        print(f"[ERROR] Unexpected error in handle_join: {str(e)}")
        await NetworkManager.send_message(
            websocket,
            "error",
            {"message": "Internal server error"}
        )
        return None

def generate_room_code():
    return f"{random.randint(1000, 9999)}"

async def start_first_trick(room_code):
    """Initialize the first trick after hokm selection"""
    game = active_games[room_code]
    game.current_turn = 0  # Hakem leads first trick
    first_player = game.players[game.current_turn]
    
    print(f"\n=== Starting first trick in room {room_code} ===")
    print(f"{first_player} (Hakem) leads the first trick")
    
    # Notify all players whose turn it is
    for p in redis_manager.get_room_players(room_code):
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
    player_objects = redis_manager.get_room_players(room_code)
    players = [p.username for p in player_objects]
    print(f"[LOG] handle_game_start called for room {room_code} with players: {players}")
    
    # Create new game instance
    game = GameBoard(players)
    active_games[room_code] = game
    
    # Assign teams and determine Hakem
    team_info = game.assign_teams_and_hakem()
    print(f"[LOG] Teams assigned: {team_info['teams']}, Hakem: {team_info['hakem']}")
    
    # Notify players about team assignments
    for p in redis_manager.get_room_players(room_code):
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
    print(f"[LOG] Initial 5 cards dealt to all players in room {room_code}")
    
    # Send initial hands and hokm selection prompt
    for player in player_objects:
        if player.username == game.hakem:
            print(f"[LOG] Prompting Hakem {player.username} to choose hokm.")
            await NetworkManager.send_message(
                player.wsconnection,
                "initial_deal",
                {
                    "hand": game.hands[player.username][:],
                    "is_hakem": True,
                    "message": "You are the Hakem. Choose hokm based on your 5 cards."
                }
            )
        else:
            await NetworkManager.send_message(
                player.wsconnection,
                "initial_deal",
                {
                    "hand": game.hands[player.username][:],
                    "is_hakem": False,
                    "message": f"Waiting for {game.hakem} to choose hokm."
                }
            )
    print(f"[LOG] Room {room_code}: Game starting [PHASE: {GameState.TEAM_ASSIGNMENT.value}]")
    
    # Save complete game state to Redis
    game_state = {
        # Team and player information
        'teams': json.dumps(team_info['teams']),
        'hakem': team_info['hakem'],
        'players': json.dumps(players),
        'player_order': json.dumps(game.players),
        
        # Game state information
        'phase': game.game_phase,
        'current_turn': str(game.current_turn),
        'tricks': json.dumps(game.tricks),
        
        # Initial hands (after first deal)
        **{f'hand_{username}': json.dumps(game.hands[username]) for username in players},
        
        # Metadata
        'created_at': str(int(time.time())),
        'last_activity': str(int(time.time())),
        'room_code': room_code,
        'state': GameState.TEAM_ASSIGNMENT.value
    }
    redis_manager.save_game_state(room_code, game_state)
    print(f"[LOG] Saved complete game state to Redis for room {room_code}")

async def handle_connection(websocket, path):
    try:
        async for message in websocket:
            data = json.loads(message)
            
            # Handle authentication requests first
            action = data.get('action')
            if action == 'register':
                username = data.get('username')
                password = data.get('password')
                if register_user(username, password):
                    await NetworkManager.send_message(
                        websocket,
                        "auth_response",
                        {'status': 'success', 'msg': 'Registered!'}
                    )
                else:
                    await NetworkManager.send_message(
                        websocket,
                        "auth_response",
                        {'status': 'error', 'msg': 'Username exists'}
                    )
                continue

            if action == 'login':
                username = data.get('username')
                password = data.get('password')
                if authenticate_user(username, password):
                    await NetworkManager.send_message(
                        websocket,
                        "auth_response",
                        {'status': 'success', 'msg': 'Login successful'}
                    )
                else:
                    await NetworkManager.send_message(
                        websocket,
                        "auth_response",
                        {'status': 'error', 'msg': 'Invalid credentials'}
                    )
                continue

            # Handle reconnection requests next
            if data.get('type') == 'reconnect':
                player_id = data.get('player_id')
                try:
                    # Validate session exists and hasn't expired
                    session = redis_manager.get_player_session(player_id)
                    if not session:
                        await NetworkManager.send_message(
                            websocket,
                            "error",
                            {"message": "Session expired or not found"}
                        )
                        continue

                    # Get session data
                    room_code = session['room_code']
                    username = session['username']
                    current_time = int(time.time())
                    
                    # Check session expiration
                    if int(session.get('expires_at', '0')) < current_time:
                        await NetworkManager.send_message(
                            websocket,
                            "error",
                            {"message": "Session expired. Please rejoin the game."}
                        )
                        redis_manager.delete_player_session(player_id)
                        continue

                    # Create new player object with restored session data
                    player = Player(player_id=player_id, wsconnection=websocket, username=username)
                    player.current_room = room_code
                    player_objects[websocket] = player
                    player_rooms[websocket] = room_code
                    
                    # Get current game state
                    game_state = redis_manager.get_game_state(room_code)
                    if game_state:
                        if room_code not in active_games and game_state.get('phase') != GameState.WAITING_FOR_PLAYERS.value:
                            try:
                                # Recreate game instance
                                players = redis_manager.get_room_players(room_code)
                                game = GameBoard([p.username for p in players])
                                active_games[room_code] = game
                                
                                # Restore complete game state
                                if 'teams' in game_state:
                                    game.teams = json.loads(game_state['teams'])
                                if 'hakem' in game_state:
                                    game.hakem = game_state['hakem']
                                if 'hokm' in game_state:
                                    game.hokm = game_state['hokm']
                                if 'current_turn' in game_state:
                                    game.current_turn = int(game_state['current_turn'])
                                if 'tricks' in game_state:
                                    game.tricks = json.loads(game_state['tricks'])
                                if 'game_phase' in game_state:
                                    game.game_phase = game_state['game_phase']
                                    
                                # Restore player order
                                if 'player_order' in game_state:
                                    game.players = json.loads(game_state['player_order'])
                                    
                                # Restore player hands
                                hand_key = f'hand_{username}'
                                if hand_key in game_state:
                                    game.hands[username] = json.loads(game_state[hand_key])
                                    
                                # Send complete game state to reconnected player
                                restored_state = {
                                    "type": "game_state",
                                    "state": game_state['phase'],
                                    "teams": json.loads(game_state['teams']),
                                    "hakem": game_state['hakem'],
                                    "hokm": game_state.get('hokm'),
                                    "hand": json.loads(game_state.get(f'hand_{username}', '[]')),
                                    "current_turn": int(game_state.get('current_turn', 0)),
                                    "tricks": json.loads(game_state.get('tricks', '{}')),
                                    "room_code": room_code,
                                    "you": username,
                                    "your_team": "1" if username in json.loads(game_state['teams'])['1'] else "2"
                                }
                                
                                await NetworkManager.send_message(
                                    websocket,
                                    "join_success",
                                    {
                                        "username": username,
                                        "player_id": player_id,
                                        "room_code": room_code,
                                        "game_state": restored_state
                                    }
                                )
                            except Exception as e:
                                print(f"[ERROR] Error restoring game state for player {username}: {str(e)}")
                                await NetworkManager.send_message(
                                    websocket,
                                    "error",
                                    {"message": "Failed to restore game state"}
                                )
                        
                        # Update session expiration
                        session['last_activity'] = str(current_time)
                        session['expires_at'] = str(current_time + 3600)  # Reset 1 hour expiration
                        redis_manager.save_player_session(player_id, session)
                        
                        print(f"[LOG] Player {username} reconnected to room {room_code}")
                        
                        # Notify other players about reconnection
                        await broadcast_room_status(room_code)
                        
                        # Update game state's last activity
                        if game_state:
                            game_state['last_activity'] = str(current_time)
                            redis_manager.save_game_state(room_code, game_state)
                            
                        continue
                except Exception as e:
                    print(f"[ERROR] Failed to restore session: {str(e)}")
                    await NetworkManager.send_message(
                        websocket,
                        "error",
                        {"message": "Failed to restore previous session"}
                    )
            
            message_type = data.get('type')
            print(f"[LOG] Received message: {message_type} from websocket {id(websocket)}")
            
            if message_type == 'join':
                await handle_join(websocket, data)
                room_code = data.get('room_code', '9999')
                player = player_objects[websocket]  # Get player object from handle_join
                player_rooms[websocket] = room_code
                # No broadcast_room_status here!
                # Check if room is full after join
                if len(redis_manager.get_room_players(room_code)) == ROOM_SIZE:
                    print(f"[LOG] Room {room_code} is full, ready to play! [PHASE: {GameState.TEAM_ASSIGNMENT.value}]")
                    await handle_game_start(room_code)
            elif message_type == 'play_card':
                player = player_objects[websocket]
                card = data.get('card')
                print(f"[LOG] Room {player_rooms[websocket]}: {player.username} played {card} [PHASE: {GameState.GAMEPLAY.value}]")
                # ...existing code for play_card...
            elif message_type == 'hokm_selected':
                player = player_objects[websocket]
                suit = data.get('suit')
                room_code = player_rooms[websocket]
                print(f"[LOG] Room {room_code}: Hakem {player.username} selected hokm: {suit}")
                game = active_games[room_code]
                if not game.set_hokm(suit):
                    print(f"[LOG] Invalid hokm selection: {suit}")
                    await NetworkManager.send_message(
                        websocket,
                        "error",
                        {"message": f"Invalid hokm selection: {suit}"}
                    )
                    return
                # Deal remaining 8 cards
                final_hands = game.final_deal()
                print(f"[LOG] Final 8 cards dealt to all players in room {room_code}")
                # Send each player their full hand and hokm
                for p in redis_manager.get_room_players(room_code):
                    await NetworkManager.send_message(
                        p.wsconnection,
                        "final_deal",
                        {
                            "hand": final_hands[p.username],
                            "hokm": game.hokm  # always use current value
                        }
                    )
                # Broadcast summary (teams, hakem, hokm) using current game state
                teams = {"1": [], "2": []}
                for uname, t in game.teams.items():
                    if t == 0:
                        teams["1"].append(uname)
                    else:
                        teams["2"].append(uname)
                summary = {
                    "teams": teams,
                    "hakem": game.hakem,  # always use current value
                    "hokm": game.hokm.capitalize() if game.hokm else None,
                    "room_code": room_code
                }
                for p in redis_manager.get_room_players(room_code):
                    message_data = summary.copy()
                    message_data.update({"you": p.username})
                    await NetworkManager.send_message(
                        p.wsconnection,
                        "team_assignment",
                        message_data
                    )
                print(f"[LOG] Broadcasted team/hakem/hokm summary to all players in room {room_code}")
                # Start first trick
                await start_first_trick(room_code)
                print(f"[LOG] First trick started in room {room_code}")
    except websockets.ConnectionClosed:
        # Get username from player object before cleanup
        player = player_objects.get(websocket)
        if not player:
            return
            
        username = player.username
        print(f"[LOG] Player {username} disconnected.")
        
        try:
            # Save current game state if in a game
            if websocket in player_rooms:
                room_code = player_rooms[websocket]
                if room_code in active_games:
                    game = active_games[room_code]
                    
                    # Save full game state
                    game_state = {
                        'phase': game.game_phase,
                        'teams': json.dumps(game.teams),
                        'hakem': game.hakem,
                        'hokm': game.hokm,
                        'current_turn': game.current_turn,
                        'last_activity': str(int(time.time()))
                    }
                    
                    # Save individual player hands
                    if game.hands:
                        for p_name, hand in game.hands.items():
                            game_state[f'hand_{p_name}'] = json.dumps(hand)
                            
                    redis_manager.save_game_state(room_code, game_state)
            
            # Clean up player mappings but preserve room data for reconnection
            if websocket in player_objects:
                del player_objects[websocket]
            if websocket in player_rooms:
                room_code = player_rooms[websocket]
                del player_rooms[websocket]
                
                # Don't immediately remove from game.players to allow reconnection
                # Only clean up if all players have been disconnected for a while
                remaining_players = redis_manager.get_room_players(room_code)
                if not remaining_players:
                    redis_manager.delete_room(room_code)
                    if room_code in active_games:
                        del active_games[room_code]
                else:
                    await broadcast_room_status(room_code)
                    
        except Exception as e:
            print(f"[ERROR] Error during disconnect cleanup: {str(e)}")

async def broadcast_room_status(room_code):
    """Broadcast current room status to all players"""
    players = redis_manager.get_room_players(room_code)
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

async def handle_room_full(room_code):
    """Handle room full event and start team assignment"""
    players = [p.username for p in redis_manager.get_room_players(room_code)]
    game = GameBoard(players)
    active_games[room_code] = game
    
    # Assign teams and Hakem
    team_info = game.assign_teams_and_hakem()
    
    # Notify all players about team assignments
    for player in redis_manager.get_room_players(room_code):
        await NetworkManager.send_message(
            player.wsconnection,
            "team_assignment",
            {
                "room_code": room_code,
                "teams": {
                    "1": [p for p, t in team_info["teams"].items() if t == 0],
                    "2": [p for p, t in team_info["teams"].items() if t == 1]
                },
                "hakem": team_info["hakem"],
                "you": player.username,
                "state": GameState.TEAM_ASSIGNMENT.value
            }
        )

async def broadcast_phase_update(room_code, phase, extra_data=None):
    print(f"Room {room_code}: Phase update to {phase}")
    players = redis_manager.get_room_players(room_code)
    for p in players:
        msg = {"phase": phase}
        if extra_data:
            msg.update(extra_data)
        await NetworkManager.send_message(p.wsconnection, "phase_update", msg)

async def cleanup_task():
    """Periodic task to cleanup expired sessions and inactive rooms"""
    while True:
        try:
            # Cleanup expired sessions
            redis_manager.cleanup_expired_sessions()
            
            # Check for inactive rooms
            current_time = int(time.time())
            for room_code in list(active_games.keys()):
                try:
                    game_state = redis_manager.get_game_state(room_code)
                    if game_state:
                        last_activity = int(game_state.get('last_activity', '0'))
                        if current_time - last_activity > 3600:  # 1 hour inactivity
                            print(f"[LOG] Cleaning up inactive room {room_code}")
                            redis_manager.delete_room(room_code)
                            del active_games[room_code]
                except Exception as e:
                    print(f"[ERROR] Error checking room {room_code}: {str(e)}")
                    
        except Exception as e:
            print(f"[ERROR] Error in cleanup task: {str(e)}")
            
        await asyncio.sleep(300)  # Run every 5 minutes

async def main():
    print("Starting Hokm WebSocket server on ws://0.0.0.0:8765")
    
    # Start cleanup task
    cleanup_loop = asyncio.create_task(cleanup_task())
    
    try:
        async with websockets.serve(handle_connection, "0.0.0.0", 8765):
            await asyncio.Future()  # Run forever
    except Exception as e:
        print(f"[ERROR] Server error: {str(e)}")
    finally:
        cleanup_loop.cancel()
        try:
            await cleanup_loop
        except asyncio.CancelledError:
            pass

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServer shutting down...")
    except Exception as e:
        print(f"[ERROR] Fatal error: {str(e)}")
        sys.exit(1)
