# client.py
import asyncio
import websockets
import json
import sys
import random
from network import NetworkManager
from game_states import GameState


SERVER_URI = "ws://localhost:8765"

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
    while True:
        try:
            choice = input("\nEnter choice (1-4): ").strip()
            num = int(choice)
            if 1 <= num <= 4:
                return suits[num-1]
            print("❌ Please enter 1, 2, 3, or 4")
        except ValueError:
            print("❌ Please enter a valid number")

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

def print_summary_and_hand(summary, hand):
    room_code = summary.get('room_code', '9999')
    teams = summary.get('teams', {})
    hakem = summary.get('hakem')
    hokm = summary.get('hokm')
    you = summary.get('you')

    print("="*40)
    print(f"Room {room_code}")
    print("-"*40)
    def format_player_name(player):
        return f"{player} (You)" if player == you else player
    team1_players = [format_player_name(p) for p in teams.get('1', [])]
    team2_players = [format_player_name(p) for p in teams.get('2', [])]
    print(f"Team 1: {', '.join(team1_players)}")
    print(f"Team 2: {', '.join(team2_players)}")
    print("-"*40)
    print(f"Hakem is: {format_player_name(hakem)}")
    your_team = "1" if you in teams.get('1', []) else "2"
    print(f"You are on Team {your_team}")
    if hakem == you:
        print("You are the Hakem!")
    print()
    if hokm:
        print(f"Hokm is: {hokm}")
    print("="*40)
    print("\nYour hand:")
    for idx, card in enumerate(hand.get('hand', []), 1):
        print(f"{idx}. {card}")

async def main():
    # Remove the random player assignment and just use "player" as base name
    player_base = "player"
    username = player_base  # Server will assign the number
    
    if not username:
        print("Username cannot be empty")
        return
        
    current_state = GameState.WAITING_FOR_PLAYERS
    your_turn = False
    hand = []
    hokm = None
    last_turn_hand = None
    round_number = 1
    
    print(f"\nConnecting to server...")
    
    summary_info = {}
    hand_info = {}

    # Track reconnection state
    player_id = None
    is_reconnecting = False
    
    async with websockets.connect(SERVER_URI) as ws:
        # Try to reconnect if we have a player_id
        try:
            with open('.player_session', 'r') as f:
                player_id = f.read().strip()
                is_reconnecting = True
        except FileNotFoundError:
            pass
            
        if is_reconnecting and player_id:
            # Attempt to reconnect
            print("Attempting to reconnect to previous session...")
            await ws.send(json.dumps({
                "type": "reconnect",
                "player_id": player_id
            }))
        else:
            # New connection
            await ws.send(json.dumps({
                "type": "join",
                "username": player_base,
                "room_code": "9999"
            }))
        
        while True:
            try:
                msg = await ws.recv()
                data = json.loads(msg)
                msg_type = data.get('type')
                
                # Save player_id when we get it from join response
                if msg_type == 'join_success' and not is_reconnecting:
                    player_id = data.get('player_id')
                    if player_id:
                        with open('.player_session', 'w') as f:
                            f.write(player_id)
                
                # Store summary info when received
                if msg_type == 'join_success':
                    if is_reconnecting:
                        print("Successfully reconnected to game!")
                        username = data.get('username')  # Restore username from saved session
                    else:
                        print("Successfully joined game!")
                    # Update any game state sent with join response
                    if 'game_state' in data:
                        current_state = GameState(data['game_state'].get('phase', current_state))
                        hokm = data['game_state'].get('hokm', hokm)
                
                elif msg_type == 'team_assignment':
                    summary_info.clear()
                    summary_info.update(data)
                    if hand_info:
                        print_summary_and_hand(summary_info, hand_info)
                        hand_info.clear()
                        summary_info.clear()
                
                elif msg_type == 'final_deal':
                    hand_info.clear()
                    hand_info.update(data)
                    if summary_info:
                        print_summary_and_hand(summary_info, hand_info)
                        hand_info.clear()
                        summary_info.clear()
                
                # Handle all other message types
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

                # Update state based on message type
                # (state_handlers is not defined, so this block is removed)

                # Remove duplicate room_status handler - we already handle it above

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

                elif msg_type == 'team_assignment':
                    room_code = data.get('room_code', '9999')
                    teams = data.get('teams', {})
                    hakem = data.get('hakem')
                    you = data.get('you')
                    
                    print("\n" + "="*40)
                    print(f"Room {room_code}")
                    print("-"*40)
                    
                    # Add "(You)" marker to the player's username
                    def format_player_name(player):
                        return f"{player} (You)" if player == you else player
                    
                    team1_players = [format_player_name(p) for p in teams.get('1', [])]
                    team2_players = [format_player_name(p) for p in teams.get('2', [])]
                    
                    print(f"Team 1: {', '.join(team1_players)}")
                    print(f"Team 2: {', '.join(team2_players)}")
                    print("-"*40)
                    print(f"Hakem is: {format_player_name(hakem)}")
                    
                    your_team = "1" if you in teams.get('1', []) else "2"
                    print(f"\nYou are on Team {your_team}")
                    if hakem == you:
                        print("You are the Hakem!")
                    print("="*40 + "\n")

                elif msg_type == 'initial_deal':
                    your_hand = data['hand']
                    print("\n=== Initial 5 Cards Dealt ===")
                    for idx, card in enumerate(your_hand, 1):
                        print(f"{idx}. {card}")
                    if data.get('is_hakem'):
                        print("\nYou are the Hakem! Choose hokm:")
                        suit = await get_valid_suit_choice()
                        await ws.send(json.dumps({
                            'type': 'hokm_selected',
                            'suit': suit
                        }))
                    else:
                        print(f"\nWaiting for Hakem ({data.get('hakem')}) to choose hokm...")

                elif msg_type == 'hokm_selected':
                    suit = data['suit']
                    hakem = data['hakem']
                    hokm = suit
                    print(f"\nHakem ({hakem}) has chosen {suit.title()} as hokm!")

                elif msg_type == 'final_deal':
                    your_hand = data['hand']
                    hokm = data.get('hokm', hokm)
                    print("\nYour hand:")
                    sorted_hand = sort_hand(your_hand, hokm)
                    for idx, card in enumerate(sorted_hand, 1):
                        print(f"{idx}. {card}")
                    print("\n=== Game Starting ===\n")

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
                                # Prompt for card play
                                while True:
                                    try:
                                        card_idx = int(input(f"Select a card to play (1-{len(sorted_hand)}): ")) - 1
                                        if 0 <= card_idx < len(sorted_hand):
                                            card = sorted_hand[card_idx]
                                            await ws.send(json.dumps({
                                                "type": "play_card",
                                                "card": card
                                            }))
                                            break
                                        else:
                                            print(f"❌ Please enter a number between 1 and {len(sorted_hand)}")
                                    except ValueError:
                                        print("❌ Please enter a valid number")
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
                    print(f"Team {team} player {player} played [{card}]")

                elif data.get('type') == 'trick_result':
                    print(f"\nTrick won by: {data['winner']}")
                    print(f"Team 1 tricks: {data['team1_tricks']} | Team 2 tricks: {data['team2_tricks']}\n")

                elif data.get('type') == 'hand_complete':
                    winning_team = data['winning_team'] + 1
                    tricks_team1 = data['tricks'][0]
                    tricks_team2 = data['tricks'][1]
                    
                    print(f"\n=== Hand Complete ===")
                    print(f"Team {winning_team} wins the hand!")
                    print(f"Final trick count:")
                    print(f"Team 1: {tricks_team1} tricks")
                    print(f"Team 2: {tricks_team2} tricks")
                    print(f"Round {round_number} finished\n")
                    round_number += 1  # Increment for next round

                elif data.get('type') == 'error':
                    print(f"❌ {data.get('message', 'Invalid move')}")
                    if your_turn and last_turn_hand:
                        sorted_hand = sort_hand(last_turn_hand, hokm)
                        while True:
                            try:
                                card_idx = int(input(f"Select a card to play (1-{len(sorted_hand)}): ")) - 1
                                if 0 <= card_idx < len(sorted_hand):
                                    card = sorted_hand[card_idx]
                                    await ws.send(json.dumps({
                                        "type": "play_card",
                                        "card": card
                                    }))
                                    break
                                else:
                                    print(f"❌ Please enter a number between 1 and {len(sorted_hand)}")
                            except ValueError:
                                print("❌ Please enter a valid number")

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

                # State-specific validations
                if msg_type == 'play_card' and current_state != GameState.GAMEPLAY:
                    print("❌ Cannot play card in current state:", current_state.value)
                    continue
                    
                if msg_type == 'hokm_selected' and current_state != GameState.WAITING_FOR_HOKM:
                    print("❌ Cannot select hokm in current state:", current_state.value)
                    continue

                # Remove the floating else and except blocks
                if msg_type not in ['room_status', 'room_full', 'team_assignment', 
                                  'initial_deal', 'hokm_selected', 'final_deal',
                                  'turn_start', 'card_played', 'trick_result',
                                  'hand_complete', 'game_over', 'error', 
                                  'round_result', 'trick_complete']:
                    print("Server:", data)
            except Exception as e:
                print(f"Error receiving or processing message: {e}")
                break

if __name__ == "__main__":
    asyncio.run(main())
