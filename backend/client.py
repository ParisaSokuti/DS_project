# client.py
import asyncio
import websockets
import json
import sys
import random
from game_board import card_to_emoji
from network import NetworkManager


SERVER_URI = "ws://localhost:8765"

def card_to_emoji(card: str) -> str:
    suit_emojis = {
        'hearts': '❤️',
        'diamonds': '♦️',
        'clubs': '♣️',
        'spades': '♠️'
    }
    try:
        rank, suit = card.split('_')
        return f"{suit_emojis[suit]}{rank}"
    except Exception:
        return card

def get_suit_emoji(suit):
    emojis = {
        'hearts': '❤️',
        'diamonds': '♦️',
        'clubs': '♣️',
        'spades': '♠️'
    }
    return emojis.get(suit, '❓')

def display_hand_by_suit(hand, trump_suit=None):
    suits = ['hearts', 'diamonds', 'clubs', 'spades']
    suit_cards = {suit: [] for suit in suits}
    for card in hand:
        if '_' in card:
            suit = card.split('_')[1]
            if suit in suit_cards:
                suit_cards[suit].append(card)
    # Trump first
    if trump_suit and suit_cards[trump_suit]:
        print(f"\n🎺 TRUMP - {get_suit_emoji(trump_suit)} {trump_suit.title()}:")
        display_suit_cards(suit_cards[trump_suit])
    for suit in suits:
        if suit != trump_suit and suit_cards[suit]:
            print(f"\n{get_suit_emoji(suit)} {suit.title()}:")
            display_suit_cards(suit_cards[suit])

def display_suit_cards(cards):
    for i, card in enumerate(cards):
        print(f"  {i+1:2d}. {card_to_emoji(card)}", end="")
        if (i + 1) % 6 == 0:
            print()
    print()

async def get_valid_suit_choice():
    suits = ['hearts', 'diamonds', 'clubs', 'spades']
    suit_emojis = ['❤️', '♦️', '♣️', '♠️']
    print("\nSelect Trump Suit:")
    for i, (suit, emoji) in enumerate(zip(suits, suit_emojis), 1):
        print(f"{i}. {emoji} {suit.title()}")
    while True:
        try:
            choice = input("\nEnter choice (1-4): ").strip()
            num = int(choice)
            if 1 <= num <= 4:
                return suits[num-1]
            print("❌ Please enter 1, 2, 3, or 4")
        except ValueError:
            print("❌ Please enter a valid number")

async def main():
    print("Welcome to Hokm!")
    # username = input("Enter your username (or press Enter for default): ").strip()  # uncomment later
    # if not username:  # uncomment later
    #     username = f"player{random.randint(100,999)}"  # uncomment later
    #     print(f"Using default username: {username}")  # uncomment later
    username = f"player{random.randint(100,999)}"  # auto-generate for testing

    # room_code = input("Enter your room code (or press Enter to create new room): ").strip()  # uncomment later
    # action = "join_room" if room_code else "create_room"  # uncomment later
    room_code = ""  # always create new room for testing
    action = "create_room"

    async with websockets.connect(SERVER_URI) as ws:
        msg = {
            "type": action,
            "username": username,
        }
        # if room_code:  # uncomment later
        #     msg["room_code"] = room_code  # uncomment later
        await ws.send(json.dumps(msg))
        your_hand = []
        trump_suit = None

        while True:
            try:
                msg = await ws.recv()
                data = json.loads(msg)

                if data.get('type') == 'room_status':
                    print(f"\nCurrent players in room [{data['room_id']}]:")

                    for idx, name in enumerate(data['usernames']):
                        you_marker = " (You)" if name == username else ""
                        print(f"Player {idx+1}: {name}{you_marker}")
                    print(f"Players in room: {data['total_players']}/4")
                    if data['total_players'] < 4:
                        print(f"\nWaiting for {4 - data['total_players']} other players to join...")

                elif data.get('type') == 'room_full':
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

                elif data.get('type') == 'team_assignment':
                    teams = data.get('teams', {})
                    hakem = data.get('hakem')
                    you = data.get('you')
                    team1_players = [p for p, t in teams.items() if t == 0]
                    team2_players = [p for p, t in teams.items() if t == 1]
                    print("\n=== Team Assignments ===")
                    print(f"Team 1: {' and '.join(team1_players)}")
                    print(f"Team 2: {' and '.join(team2_players)}")
                    if hakem == you:
                        print(f"\nYou are the Hakem!")
                    else:
                        print(f"\nHakem is: {hakem}")
                    print("=====================\n")

                elif data.get('type') == 'initial_deal':
                    your_hand = data['hand']
                    print("\n=== Initial 5 Cards Dealt ===")
                    for idx, card in enumerate(your_hand, 1):
                        print(f"{idx}. {card}")
                    if data.get('is_hakem'):
                        print("\nYou are the Hakem! Choose trump suit:")
                        suit = await get_valid_suit_choice()
                        await ws.send(json.dumps({
                            'type': 'trump_selected',
                            'suit': suit
                        }))
                    else:
                        print(f"\nWaiting for Hakem ({data.get('hakem')}) to choose trump suit...")

                elif data.get('type') == 'trump_selected':
                    suit = data['suit']
                    hakem = data['hakem']
                    trump_suit = suit
                    print(f"\nHakem ({hakem}) has chosen {get_suit_emoji(suit)} {suit.title()} as trump suit!")

                elif data.get('type') == 'final_deal':
                    your_hand = data['hand']
                    trump_suit = data.get('trump_suit', trump_suit)
                    print("\n=== Remaining Cards Dealt ===")
                    display_hand_by_suit(your_hand, trump_suit)
                    print("\n=== Game Starting ===\n")

                elif data.get('type') == 'turn_start':
                    if data.get('your_turn'):
                        your_hand = data['hand']
                        print("\nIt's your turn! Your hand:")
                        display_hand_by_suit(your_hand, trump_suit)
                        while True:
                            try:
                                card_idx = int(input(f"Select a card to play (1-{len(your_hand)}): ")) - 1
                                if 0 <= card_idx < len(your_hand):
                                    card = your_hand[card_idx]
                                    await ws.send(json.dumps({
                                        "type": "play_card",
                                        "card": card
                                    }))
                                    break
                                else:
                                    print(f"❌ Please enter a number between 1 and {len(your_hand)}")
                            except ValueError:
                                print("❌ Please enter a valid number")
                    else:
                        print(f"\nWaiting for {data['current_player']} to play...")

                elif data.get('type') == 'card_played':
                    print(f"{data['player']} played {data['card']}")

                elif data.get('type') == 'trick_result':
                    print(f"\nTrick won by: {data['winner']}")
                    print(f"Team 1 tricks: {data['team1_tricks']} | Team 2 tricks: {data['team2_tricks']}\n")

                elif data.get('type') == 'hand_complete':
                    print("\n=== Hand Complete ===")
                    print(f"Winning team: Team {data['winning_team']+1}")
                    print(f"Scores: Team 1: {data['scores'][0]} | Team 2: {data['scores'][1]}\n")

                elif data.get('type') == 'game_over':
                    print("\n=== GAME OVER ===")
                    print(f"Winning team: Team {data['winning_team']+1}")
                    print(f"Final scores: Team 1: {data['final_scores'][0]} | Team 2: {data['final_scores'][1]}")
                    print("Thank you for playing Hokm!")
                    break

                elif data.get('type') == 'error':
                    print("Error:", data.get('message'))
                    if "bye" in data.get('message', '').lower():
                        break

                else:
                    print("Server:", data)

            except websockets.ConnectionClosed:
                print("Connection closed by server.")
                break

if __name__ == "__main__":
    asyncio.run(main())
