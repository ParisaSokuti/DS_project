# client.py
import asyncio
import websockets
import json
import sys
import random
import os

# Add current directory to Python path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from game_states import GameState


SERVER_URI = "ws://localhost:8765"
SESSION_FILE = os.environ.get('PLAYER_SESSION', '.player_session')  # Allow configurable session file

def display_hand_by_suit(hand, hokm=None):
    suits = ['hearts', 'diamonds', 'clubs', 'spades']
    suit_cards = {suit: [] for suit in suits}
    for card in hand:
        if '_' in card:
            suit = card.split('_')[1]
            if suit in suit_cards:
                suit_cards[suit].append(card)
    # Hokm first
    if hokm and suit_cards[hokm]:
        print(f"\nHOKM - {hokm.title()}:")
        display_suit_cards(suit_cards[hokm])
    for suit in suits:
        if suit != hokm and suit_cards[suit]:
            print(f"\n{suit.title()}:")
            display_suit_cards(suit_cards[suit])

def display_suit_cards(cards):
    for i, card in enumerate(cards):
        rank, suit = card.split('_')
        print(f"  {i+1:2d}. {rank} of {suit}")
    print()

async def get_valid_suit_choice():
    suits = ['hearts', 'diamonds', 'clubs', 'spades']
    print("\nSelect Hokm:")
    for i, suit in enumerate(suits, 1):
        print(f"{i}. {suit.title()}")
    print("(Type 'exit' to clear room and exit)")
    while True:
        try:
            choice = input("\nEnter choice (1-4) or 'exit': ").strip()
            if choice.lower() == 'exit':
                return "exit"
            num = int(choice)
            if 1 <= num <= 4:
                return suits[num-1]
            print("❌ Please enter 1, 2, 3, or 4 or 'exit'")
        except ValueError:
            if choice.lower() == 'exit':
                return "exit"
            print("❌ Please enter a valid number or 'exit'")

def sort_hand(hand, hokm):
    # Normalize suit names to match server format
    suits_order = [hokm, 'diamonds', 'clubs', 'spades']
    rank_values = {'A':14, 'K':13, 'Q':12, 'J':11, '10':10, '9':9, 
                  '8':8, '7':7, '6':6, '5':5, '4':4, '3':3, '2':2}
    def parse(card):
        rank, suit = card.split('_')
        return suit, rank
    # Sort by suit priority, then by rank descending
    return sorted(
        hand,
        key=lambda card: (
            suits_order.index(parse(card)[0]) if parse(card)[0] in suits_order else 99,
            -rank_values.get(parse(card)[0].upper() if parse(card)[0].upper() in rank_values else parse(card)[1], 0)
        )
    )

# Function removed - was never used

def format_player_name(player, you):
    """Helper function to format player names with (You) marker"""
    return f"{player} (You)" if player == you else player

async def check_for_exit(ws, room_code):
    """Asynchronously check for exit command from user"""
    while True:
        # Use asyncio.create_task to run this concurrently with main loop
        cmd = await asyncio.get_event_loop().run_in_executor(None, input)
        
        if cmd and cmd.strip().lower() == 'exit':
            print("\nSending command to clear room 9999 and exiting...")
            try:
                await ws.send(json.dumps({
                    'type': 'clear_room',
                    'room_code': room_code
                }))
                print("Room 9999 cleared. Exiting client.")
                return True  # Signal that we should exit
            except Exception as e:
                print(f"Error sending clear room command: {e}")
                return True
        await asyncio.sleep(0.1)  # Small delay to prevent hogging CPU

async def main():
    you = None
    hakem = None
    
    # Check for special command
    if len(sys.argv) > 1 and sys.argv[1] == "killroom":
        print("Connecting to server to clear room 9999...")
        room_code = "9999"
        try:
            async with websockets.connect(SERVER_URI) as ws:
                await ws.send(json.dumps({
                    'type': 'clear_room',
                    'room_code': room_code
                }))
                print("Room 9999 cleared successfully. Exiting.")
                return
        except Exception as e:
            print(f"Failed to clear room: {e}")
            return
    
    # Regular client initialization
    player_base = "player"
    username = player_base  # Server will assign the number
    
    if not username:
        print("Username cannot be empty")
        return
        
    # Initialize game state variables
    current_state = GameState.WAITING_FOR_PLAYERS
    your_turn = False
    hand = []
    hokm = None
    last_turn_hand = None
    round_number = 1
    hakem = None
    your_team = None
    await_hokm_selection = False  # Flag to indicate we need to select hokm
    room_code = "9999"  # Default room code
    
    print(f"\nConnecting to server...")
    
    summary_info = {}
    hand_info = {}

    # Track player ID for gameplay
    player_id = None
    
    # Check for and remove any old session file
    if os.path.exists(SESSION_FILE):
        try:
            os.remove(SESSION_FILE)
            print("Removed old session data")
        except:
            print("Failed to remove old session file")
    
    async with websockets.connect(SERVER_URI) as ws:
        # Always start a new session - no reconnection attempts
        await ws.send(json.dumps({
            "type": "join",
            "username": player_base,
            "room_code": "9999"
        }))
        
        while True:
            try:
                msg = await ws.recv()
                
                # Handle edge cases for message types
                if msg is None or msg == "":
                    print("Received empty message, continuing...")
                    continue
                
                # Handle numeric messages that shouldn't be processed as JSON
                if isinstance(msg, (int, float)) or (isinstance(msg, str) and msg.isdigit()):
                    print(f"[DEBUG] Received unexpected numeric message: {msg}, ignoring...")
                    continue
                
                # Handle empty strings or whitespace-only messages
                if isinstance(msg, str) and msg.strip() == "":
                    print(f"[DEBUG] Received empty string message, ignoring...")
                    continue
                    
                # Parse JSON message
                try:
                    data = json.loads(msg)
                except json.JSONDecodeError as e:
                    print(f"❌ Failed to parse JSON message: {msg[:100]}... Error: {e}")
                    continue
                    
                msg_type = data.get('type')
                
                # Handle errors first
                if msg_type == 'error':
                    error_msg = data.get('message', 'Unknown error')
                    print(f"\n❌ Error: {error_msg}")
                    print(f"[DEBUG] Error handler state - your_turn: {your_turn}, last_turn_hand: {last_turn_hand is not None}, hand: {hand is not None}")
                    
                    # Handle connection/player not found errors
                    if ("Player not found in room" in error_msg or 
                        "Connection lost" in error_msg or
                        "try reconnecting" in error_msg):
                        print("\n🔄 CONNECTION ISSUE DETECTED")
                        print("This usually happens when the server loses track of your player ID.")
                        print("\nOptions:")
                        print("1. Type 'exit' to leave and rejoin the game")
                        print("2. Wait a moment - the server may recover automatically")
                        print("3. If this keeps happening, restart the server")
                        continue
                    
                    # Handle suit-following errors by re-prompting for card selection
                    if "You must follow suit" in error_msg:
                        # Use current hand if last_turn_hand is not available
                        current_hand = last_turn_hand if last_turn_hand else hand
                        if current_hand:
                            print("\nPlease select a valid card that follows suit:")
                            sorted_hand = sort_hand(current_hand, hokm)
                            for idx, card in enumerate(sorted_hand, 1):
                                print(f"{idx}. {card}")
                            
                            print("(Type 'exit' to clear room and exit)")
                            while True:
                                try:
                                    choice = input(f"Select a card to play (1-{len(sorted_hand)}) or 'exit': ")
                                    print(f"[DEBUG] Error re-prompt - User input: '{choice}', Hand size: {len(sorted_hand)}")
                                    
                                    if choice.lower() == 'exit':
                                        print("Sending command to clear room and exiting...")
                                        await ws.send(json.dumps({
                                            'type': 'clear_room',
                                            'room_code': room_code
                                        }))
                                        print("Room cleared. Exiting client.")
                                        await ws.close()
                                        return
                                        
                                    card_idx = int(choice) - 1
                                    print(f"[DEBUG] Error re-prompt - Calculated card_idx: {card_idx}, Valid range: 0 to {len(sorted_hand)-1}")
                                    
                                    if 0 <= card_idx < len(sorted_hand):
                                        card = sorted_hand[card_idx]
                                        print(f"[DEBUG] Error re-prompt - Selected card: {card}")
                                        await ws.send(json.dumps({
                                            "type": "play_card",
                                            "room_code": room_code,
                                            "player_id": player_id,
                                            "card": card
                                        }))
                                        break
                                    else:
                                        print(f"❌ Please enter a number between 1 and {len(sorted_hand)} or 'exit'")
                                except ValueError as ve:
                                    print(f"[DEBUG] Error re-prompt - ValueError: {ve}")
                                    if choice.lower() == 'exit':
                                        print("Sending command to clear room and exiting...")
                                        await ws.send(json.dumps({
                                            'type': 'clear_room',
                                            'room_code': room_code
                                        }))
                                        print("Room cleared. Exiting client.")
                                        await ws.close()
                                        return
                                    print(f"❌ Please enter a valid number or 'exit'")
                        else:
                            print(f"❌ Error: {error_msg}")
                            print("Unable to re-prompt - hand data not available. Please try reconnecting.")
                    continue

                # Handle join success - extract and save player_id
                elif msg_type == 'join_success':
                    player_id = data.get('player_id')
                    username = data.get('username', username)
                    
                    if player_id:
                        # Save player_id to session file for reconnection
                        try:
                            with open(SESSION_FILE, 'w') as f:
                                f.write(player_id)
                            print(f"✅ Successfully joined as {username}")
                        except Exception as e:
                            print(f"⚠️ Warning: Could not save session: {e}")
                    else:
                        print("⚠️ Warning: No player_id received from server")
                    continue

                # Handle team assignment
                elif msg_type == 'team_assignment':
                            teams = data.get('teams', {})
                            hakem = data.get('hakem')
                            you = data.get('you')
                            # Only print team assignment info here, not on phase_change or summary
                            print("\n" + "="*40)
                            print("Teams have been assigned!")
                            print("-"*40)
                            team1_players = [format_player_name(p, you) for p in teams.get('1', [])]
                            team2_players = [format_player_name(p, you) for p in teams.get('2', [])]
                            print(f"Team 1: {', '.join(team1_players)}")
                            print(f"Team 2: {', '.join(team2_players)}")
                            print("-"*40)
                            print(f"Hakem is: {format_player_name(hakem, you)}")
                            your_team = "1" if you in teams.get('1', []) else "2"
                            print(f"\nYou are on Team {your_team}")
                            if hakem == you:
                                print("You are the Hakem!")
                            print("="*40 + "\n")

                            # Just mark that we need to select hokm later if we're the hakem
                            if hakem == you:
                                await_hokm_selection = True

                        # Handle phase changes, but do NOT print team/Hakem info or call print_summary_and_hand here
                elif msg_type == 'phase_change':
                    new_phase = data.get('new_phase')
                    print(f"\n🔄 Game phase changed: {current_state.value} -> {new_phase}")
                    current_state = GameState(new_phase)
                    # Only track that hokm selection is pending; actual prompt will occur after initial_deal
                    if new_phase == GameState.WAITING_FOR_HOKM.value and hakem == you:
                        await_hokm_selection = True
                    elif new_phase == GameState.GAMEPLAY.value:
                        print("\n=== Game is starting! ===")
                    continue

                # Handle initial deal and hokm selection
                elif msg_type == 'initial_deal':
                    hand = data.get('hand', [])
                    is_hakem = data.get('is_hakem', False)
                    hakem = data.get('hakem')  # Make sure to update the global hakem variable

                    print("\n=== Initial 5 Cards Dealt ===")
                    for idx, card in enumerate(hand, 1):
                        print(f"{idx}. {card}")

                    # Prompt for hokm immediately after deal if needed
                    if is_hakem and (await_hokm_selection or current_state == GameState.WAITING_FOR_HOKM):
                        print("\nNow you can choose hokm (hearts/diamonds/clubs/spades):")
                        suit = await get_valid_suit_choice()
                        if suit == 'exit':
                            await ws.send(json.dumps({'type':'clear_room','room_code':room_code}))
                            return
                        await ws.send(json.dumps({'type':'hokm_selected','suit':suit,'room_code':room_code}))
                        await_hokm_selection = False
                    elif is_hakem:
                        print(f"\nYou are the Hakem! Waiting for phase to choose hokm...")
                    else:
                        print(f"\nWaiting for {hakem} to choose hokm...")

                # Handle hokm selection announcement
                elif msg_type == 'hokm_selected':
                    suit = data.get('suit')
                    hokm = suit
                    print(f"\n🎴 Hakem ({hakem}) has chosen {suit.upper()} as hokm!")
                    print("Dealing remaining cards...\n")

                # Handle final deal after hokm selection
                elif msg_type == 'final_deal':
                    hand = data.get('hand', [])
                    hokm = data.get('hokm', hokm)
                    print("\n=== Your Complete Hand ===")
                    sorted_hand = sort_hand(hand, hokm)
                    for idx, card in enumerate(sorted_hand, 1):
                        print(f"{idx}. {card}")
                    print(f"\nHokm is: {hokm.upper()}")
                    print("Ready to start playing!\n")

                # Handle room status updates
                elif msg_type == 'room_status':
                    print(f"\nCurrent players in room [9999]:")
                    players = data.get('usernames', [])
                    total_players = data.get('total_players', 0)
                    
                    # Show players in order of joining
                    for idx, name in enumerate(players, 1):
                        you_marker = " (You)" if name == username else ""
                        print(f"Player {idx}: {name}{you_marker}")
                    
                    print(f"\nPlayers in room: {total_players}/4")
                    if total_players < 4:
                        print(f"Waiting for {4 - total_players} more players to join...")
                    else:
                        print("\nRoom full! Game starting...")

                # Track state changes
                if 'state' in data:
                    new_state = GameState(data['state'])
                    print(f"\nGame state changed: {current_state.value} -> {new_state.value}")
                    current_state = new_state

                # Handle room full notification
                elif msg_type == 'room_full':
                    print(data.get('message'))
                    answer = input("Create a new room? (y/n): ").strip().lower()
                    if answer == 'y':
                        await ws.send(json.dumps({
                            "type": "create_room",
                            "username": username,
                            "response": "y"
                        }))
                    else:
                        print("bye bye")
                        await ws.close()
                        break

                        # Remove this duplicate handler - we already handled 'hokm_selected' above

                        # Remove this duplicate handler - we already handled 'final_deal' above

                elif msg_type == "turn_start":
                    hand = data["hand"]
                    last_turn_hand = hand[:]  # Store for error re-prompt
                    your_turn = data.get('your_turn', False)
                    current_player = data.get('current_player')
                    hokm = data.get('hokm', hokm)  # Get hokm from turn_start
                    
                    if current_state == GameState.GAMEPLAY:
                        print(f"\nCurrent turn: {current_player}")
                        # Only show hand and prompt if player has cards
                        if hand:
                            print("\nYour hand (organized):")
                            sorted_hand = sort_hand(hand, hokm)
                            for idx, card in enumerate(sorted_hand, 1):
                                print(f"{idx}. {card}")
                            
                            if your_turn:
                                # Prompt for card play                                        print("(Type 'exit' to clear room and exit)")
                                while True:
                                    try:
                                        choice = input(f"Select a card to play (1-{len(sorted_hand)}) or 'exit': ")
                                        print(f"[DEBUG] User input: '{choice}', Hand size: {len(sorted_hand)}")
                                        
                                        if choice.lower() == 'exit':
                                            print("Sending command to clear room and exiting...")
                                            await ws.send(json.dumps({
                                                'type': 'clear_room',
                                                'room_code': room_code
                                            }))
                                            print("Room cleared. Exiting client.")
                                            await ws.close()
                                            break
                                            
                                        card_idx = int(choice) - 1
                                        print(f"[DEBUG] Calculated card_idx: {card_idx}, Valid range: 0 to {len(sorted_hand)-1}")
                                        
                                        if 0 <= card_idx < len(sorted_hand):
                                            card = sorted_hand[card_idx]
                                            print(f"[DEBUG] Selected card: {card}")
                                            await ws.send(json.dumps({
                                                "type": "play_card",
                                                "room_code": room_code,
                                                "player_id": player_id,
                                                "card": card
                                            }))
                                            # Don't break here - wait for server response
                                            # If valid, we'll get card_played. If invalid, we'll get error and re-prompt
                                            break
                                        else:
                                            print(f"❌ Please enter a number between 1 and {len(sorted_hand)} or 'exit'")
                                    except ValueError as ve:
                                        print(f"[DEBUG] ValueError: {ve}")
                                        if choice.lower() == 'exit':
                                            print("Sending command to clear room and exiting...")
                                            await ws.send(json.dumps({
                                                'type': 'clear_room',
                                                'room_code': room_code
                                            }))
                                            print("Room cleared. Exiting client.")
                                            await ws.close()
                                            break
                                        print(f"❌ Please enter a valid number or 'exit'")
                            else:
                                # If hand is empty, just display waiting message
                                print(f"\nWaiting for {data['current_player']} to play...")
                        else:
                            # If hand is empty, just display waiting message
                            print("\nTrick finished. Waiting for other players...")
                elif data.get('type') == 'card_played':
                    player = data['player']
                    card = data['card']
                    team = data.get('team', '?')
                    message_player_id = data.get('player_id')
                    
                    if player_id == message_player_id:
                        print(f"You played [{card}]")
                    else:
                        print(f"Team {team} player {player} played [{card}]")
                    
                    # Remove card from local hand if it was you
                    if player_id == message_player_id and card in hand:
                        hand.remove(card)

                elif data.get('type') == 'trick_result':
                    print(f"\nTrick won by: {data['winner']}")
                    print(f"Team 1 tricks: {data['team1_tricks']} | Team 2 tricks: {data['team2_tricks']}\n")

                elif data.get('type') == 'hand_complete':
                    print(f"[DEBUG] Processing hand_complete message: {data}")
                    try:
                        winning_team = data['winning_team'] + 1
                        
                        # Handle tricks data - convert string keys to integers
                        tricks_data = data.get('tricks', {})
                        if isinstance(tricks_data, dict):
                            # Server sends {'0': count, '1': count} - convert to int
                            tricks_team1 = int(tricks_data.get('0', 0)) if '0' in tricks_data else int(tricks_data.get(0, 0))
                            tricks_team2 = int(tricks_data.get('1', 0)) if '1' in tricks_data else int(tricks_data.get(1, 0))
                        else:
                            # Fallback for list format
                            tricks_team1 = tricks_data[0] if len(tricks_data) > 0 else 0
                            tricks_team2 = tricks_data[1] if len(tricks_data) > 1 else 0
                        
                        print(f"\n=== Hand Complete ===")
                        print(f"Team {winning_team} wins the hand!")
                        print(f"Final trick count:")
                        print(f"Team 1: {tricks_team1} tricks")
                        print(f"Team 2: {tricks_team2} tricks")
                        
                        # Display round summary if available
                        if 'round_scores' in data:
                            scores = data.get('round_scores', {})
                            # Handle string keys for round_scores too
                            team1_rounds = int(scores.get('0', 0)) if '0' in scores else int(scores.get(0, 0))
                            team2_rounds = int(scores.get('1', 0)) if '1' in scores else int(scores.get(1, 0))
                            print("\nRound Score:")
                            print(f"Team 1: {team1_rounds} hands")
                            print(f"Team 2: {team2_rounds} hands")
                        print(f"Round {round_number} finished\n")
                        round_number += 1  # Increment for next round
                        
                        # If game is complete, notify
                        if data.get('game_complete'):
                            print("🎉 Game Over! 🎉")
                            print(f"Team {data.get('round_winner')} wins the game!")
                            print("Thank you for playing.")
                            await ws.close()
                            break
                    except Exception as hand_error:
                        print(f"❌ Error processing hand_complete: {hand_error}")
                        print(f"[DEBUG] Data received: {data}")
                        continue

                elif data.get('type') == 'new_round_start':
                    try:
                        round_number = data.get('round_number', 1)
                        hakem = data.get('hakem', 'Unknown')
                        team_scores = data.get('team_scores', {0: 0, 1: 0})
                        you = data.get('you', username)
                        new_phase = data.get('phase', 'hokm_selection')
                        
                        # Update the current state from the new round info
                        if new_phase == 'hokm_selection':
                            current_state = GameState.WAITING_FOR_HOKM
                        elif new_phase == 'gameplay':
                            current_state = GameState.GAMEPLAY
                        elif new_phase == 'final_deal':
                            current_state = GameState.FINAL_DEAL
                        
                        print(f"\n{'='*50}")
                        print(f"🎯 ROUND {round_number} STARTING 🎯")
                        print(f"{'='*50}")
                        print(f"New Hakem: {format_player_name(hakem, you)}")
                        
                        # Show current game score
                        team1_score = int(team_scores.get('0', 0)) if '0' in team_scores else int(team_scores.get(0, 0))
                        team2_score = int(team_scores.get('1', 0)) if '1' in team_scores else int(team_scores.get(1, 0))
                        print(f"Game Score - Team 1: {team1_score} | Team 2: {team2_score}")
                        
                        if hakem == you:
                            print("🎖️  YOU ARE THE HAKEM! 🎖️")
                            print("You will choose the Hokm (trump suit) after seeing your first 5 cards.")
                            await_hokm_selection = True  # Set flag for hokm selection
                        else:
                            print(f"{format_player_name(hakem, you)} is the Hakem and will choose Hokm.")
                        
                        print("Waiting for initial cards...")
                        print("-" * 50)
                        
                    except Exception as round_error:
                        print(f"❌ Error processing new_round_start: {round_error}")
                        print(f"[DEBUG] Data received: {data}")
                        continue

                elif data.get('type') == 'game_over':
                    winner_team = data.get('winner_team')
                    print("\n🎉 Game Over! 🎉")
                    print(f"Team {winner_team} wins the game!")
                    print("Thank you for playing.")
                    await ws.close()
                    break

                elif data.get('type') == 'error':
                    print(f"❌ {data.get('message', 'Invalid move')}")
                    if your_turn and last_turn_hand:
                        sorted_hand = sort_hand(last_turn_hand, hokm)
                        print("(Type 'exit' to clear room and exit)")
                        while True:
                            try:
                                choice = input(f"Select a card to play (1-{len(sorted_hand)}) or 'exit': ")
                                if choice.lower() == 'exit':
                                    print("Sending command to clear room and exiting...")
                                    await ws.send(json.dumps({
                                        'type': 'clear_room',
                                        'room_code': room_code
                                    }))
                                    print("Room cleared. Exiting client.")
                                    await ws.close()
                                    break
                                card_idx = int(choice) - 1
                                if 0 <= card_idx < len(sorted_hand):
                                    card = sorted_hand[card_idx]
                                    await ws.send(json.dumps({
                                        "type": "play_card",
                                        "room_code": room_code,
                                        "player_id": player_id,
                                        "card": card
                                    }))
                                    # Do NOT break here; wait for server response to see if move is valid
                                else:
                                    print(f"❌ Please enter a number between 1 and {len(sorted_hand)} or 'exit'")
                            except ValueError:
                                if choice.lower() == 'exit':
                                    print("Sending command to clear room and exiting...")
                                    await ws.send(json.dumps({
                                        'type': 'clear_room',
                                        'room_code': room_code
                                    }))
                                    print("Room cleared. Exiting client.")
                                    await ws.close()
                                    break
                                print(f"❌ Please enter a valid number or 'exit'")
                        # After breaking, do not break outer loop; let main loop continue to process next server message

                elif data.get('type') == 'round_result':
                    winner = data['winner']
                    winner_team = data.get('winner_team', 1)
                    round_counts = data.get('round_counts', {})
                    player_rounds = data.get('player_rounds', {})
                    
                    # Convert string keys to integers if needed
                    if isinstance(round_counts, dict):
                        round_counts = {int(k): v for k, v in round_counts.items()}
                    
                    print("\n" + "="*40)
                    print(f"🎉 Round Winner: {winner} (Team {winner_team})")
                    print("-" * 40)
                    print("Round Score:")
                    print(f"Team 1: {round_counts.get(0, 0)} rounds")  # Use .get() with default
                    print(f"Team 2: {round_counts.get(1, 0)} rounds")  # Use .get() with default
                    print("-" * 40)
                    print("Player Round Wins:")
                    for player, wins in player_rounds.items():
                        print(f"  {player}: {wins} rounds")
                    print("=" * 40 + "\n")

                elif data.get('type') == 'trick_complete':
                    winning_team = data['winning_team']
                    next_hakem = data['next_hakem']
                    round_summary = data.get('round_summary', {})
                    
                    print("\n" + "="*50)
                    print("🎉 TRICK COMPLETE 🎉")
                    print("=" * 50)
                    print(f"Winning Team: Team {winning_team + 1}")
                    print(f"Next Hakem: {next_hakem}")
                    print("\nRound Summary:")
                    for player, wins in round_summary.items():
                        print(f"  {player}: {wins} rounds")
                    print("=" * 50)
                    print("\nWaiting for next trick to start...")
                    
                # Add handlers for reconnection messages
                elif msg_type == 'player_reconnected':
                    username = data.get('username')
                    active_players = data.get('active_players', 0)
                    print(f"\n🔄 Player reconnected: {username} ({active_players} active players)")
                
                elif msg_type == 'reconnect_success':
                    # Restore game state from reconnect data
                    hand = data.get('hand', [])
                    is_hakem = data.get('is_hakem', False)
                    hakem = data.get('hakem')
                    hokm = data.get('hokm')
                    phase = data.get('phase')
                    your_turn = data.get('your_turn', False)
                    
                    # Update game state
                    current_state = GameState(phase) if phase else current_state
                    
                    print("\n=== Session Restored ===")
                    print(f"Current phase: {phase}")
                    print(f"Hakem: {hakem}" + (" (You!)" if is_hakem else ""))
                    if hokm:
                        print(f"Hokm: {hokm.upper()}")
                    
                    # Show restored hand
                    if hand:
                        print("\nYour hand:")
                        sorted_hand = sort_hand(hand, hokm) if hokm else hand
                        for idx, card in enumerate(sorted_hand, 1):
                            print(f"{idx}. {card}")
                        
                    if your_turn:
                        print("\n⭐ It's your turn!")

                # State-specific validations
                if msg_type == 'play_card' and current_state != GameState.GAMEPLAY:
                    print("❌ Cannot play card in current state:", current_state.value)
                    continue
                    
                if msg_type == 'hokm_selected' and current_state != GameState.WAITING_FOR_HOKM:
                    print("❌ Cannot select hokm in current state:", current_state.value)
                    continue

                # Handle any unknown message types
                if msg_type not in ['room_status', 'room_full', 'team_assignment', 
                                  'initial_deal', 'hokm_selected', 'final_deal',
                                  'turn_start', 'card_played', 'trick_result',
                                  'hand_complete', 'game_over', 'error', 
                                  'round_result', 'trick_complete',
                                  'player_reconnected', 'reconnect_success']:
                    print("Server:", data)
            except websockets.exceptions.ConnectionClosed:
                print("❌ Connection closed by server")
                break
            except Exception as e:
                print(f"❌ Error receiving or processing message: {e}")
                print(f"[DEBUG] Message type: {type(msg) if 'msg' in locals() else 'No message variable'}")
                print(f"[DEBUG] Raw message: {repr(msg) if 'msg' in locals() else 'No message'}")
                # Continue processing instead of breaking the connection
                continue

        # Temporary auto-hokm for testing (removed invalid code using 'self')
        # If you want to auto-select hokm for testing, implement it on the server side or adjust the client logic accordingly.

if __name__ == "__main__":
    asyncio.run(main())
