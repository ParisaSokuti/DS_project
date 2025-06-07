# game_board.py
import random
from typing import List, Dict, Tuple, Optional, Any

class GameBoard:
    def __init__(self, players: List[str]):
        if len(players) != 4:
            raise ValueError("Hokm requires exactly 4 players")
        
        # Game state components
        self.players = players.copy()  # Maintain original order until team assignment
        self.deck = self._create_deck()
        self.teams = {}
        self.hakem = None
        self.trump_suit = None
        self.current_turn = 0
        self.tricks = {0: 0, 1: 0}
        self.scores = {0: 0, 1: 0}
        self.hands = {player: [] for player in players}
        self.current_trick = []
        self.led_suit = None
        self.game_phase = "lobby"  # lobby -> initial_deal -> trump_selection -> gameplay -> completed

    def _create_deck(self) -> List[str]:
        """Create a standard 52-card deck"""
        suits = ['hearts', 'diamonds', 'clubs', 'spades']
        ranks = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
        return [f"{rank}_{suit}" for suit in suits for rank in ranks]

    def assign_teams_and_hakem(self) -> Dict[str, List[str]]:
        """Assign teams based on first two Aces found during dealing"""
        temp_deck = self.deck.copy()
        random.shuffle(temp_deck)
        aces_found = []
        current_player_idx = 0
        
        while len(aces_found) < 2 and temp_deck:
            card = temp_deck.pop(0)
            if card.startswith('A_'):
                aces_found.append(self.players[current_player_idx])
            current_player_idx = (current_player_idx + 1) % 4

        # Assign teams and reorder players
        if len(aces_found) >= 2:
            self.hakem = aces_found[0]
            partner = aces_found[1]
        else:
            self.hakem = random.choice(self.players)
            partner = random.choice([p for p in self.players if p != self.hakem])
        
        self.teams = {
            self.hakem: 0,
            partner: 0,
            **{p: 1 for p in self.players if p not in {self.hakem, partner}}
        }
        
        # Reorder players: Hakem first, then clockwise order
        hakem_idx = self.players.index(self.hakem)
        self.players = self.players[hakem_idx:] + self.players[:hakem_idx]
        self.current_turn = 0  # Hakem leads first
        
        self.game_phase = "initial_deal"
        return {"teams": self.teams, "hakem": self.hakem}

    def initial_deal(self) -> Dict[str, List[str]]:
        """Deal first 5 cards to all players"""
        if self.game_phase != "initial_deal":
            raise ValueError("Invalid game phase for initial deal")
        
        random.shuffle(self.deck)
        for _ in range(5):
            for player in self.players:
                self.hands[player].append(self.deck.pop(0))
        
        self.game_phase = "trump_selection"
        return {p: self.hands[p].copy() for p in self.players}

    def set_trump_suit(self, suit: str) -> bool:
        """Validate and set trump suit"""
        if self.game_phase != "trump_selection":
            return False
        
        if suit.lower() not in {'hearts', 'diamonds', 'clubs', 'spades'}:
            return False
        
        self.trump_suit = suit.lower()
        self.game_phase = "final_deal"
        return True

    def final_deal(self) -> Dict[str, List[str]]:
        """Deal remaining 8 cards after trump selection"""
        if self.game_phase != "final_deal":
            raise ValueError("Invalid game phase for final deal")
        
        # Deal remaining cards in Hakem-first order
        for _ in range(8):
            for player in self.players:
                if self.deck:
                    self.hands[player].append(self.deck.pop(0))
        
        self.game_phase = "gameplay"
        return {p: self.hands[p].copy() for p in self.players}

    def validate_play(self, player: str, card: str) -> Tuple[bool, str]:
        """Check if a card play is valid"""
        if self.game_phase != "gameplay":
            return False, "Game not in progress"
        
        if player != self.players[self.current_turn]:
            return False, "Not your turn"
        
        if card not in self.hands[player]:
            return False, "Card not in hand"
        
        # First card in trick sets led suit
        if not self.current_trick:
            return True, "Valid lead"
        
        # Check suit following rules
        led_suit = self.current_trick[0][1].split('_')[1]
        card_suit = card.split('_')[1]
        has_led_suit = any(c.split('_')[1] == led_suit for c in self.hands[player])
        
        if has_led_suit and card_suit != led_suit:
            return False, "Must follow led suit"
            
        return True, "Valid play"

    def play_card(self, player: str, card: str) -> Dict[str, Any]:
        """Process a card play and update game state"""
        valid, message = self.validate_play(player, card)
        if not valid:
            return {"valid": False, "message": message}
        
        # Remove card from hand and add to trick
        self.hands[player].remove(card)
        self.current_trick.append((player, card))
        
        # Set led suit if first card
        if len(self.current_trick) == 1:
            self.led_suit = card.split('_')[1]
        
        # Move to next player
        self.current_turn = (self.current_turn + 1) % 4
        
        result = {"valid": True, "trick_complete": False}
        
        # Check if trick is complete
        if len(self.current_trick) == 4:
            result.update(self._resolve_trick())
            
        return result

    def _resolve_trick(self) -> Dict[str, Any]:
        """Determine trick winner and update game state"""
        trick_winner = None
        highest_value = -1
        trump_played = False
        
        for player, card in self.current_trick:
            rank, suit = card.split('_')
            value = self._card_value(rank)
            
            # Trump handling
            if suit == self.trump_suit:
                if not trump_played or value > highest_value:
                    trick_winner = player
                    highest_value = value
                    trump_played = True
            elif not trump_played and suit == self.led_suit:
                if value > highest_value:
                    trick_winner = player
                    highest_value = value
        
        # Update trick count
        winner_team = self.teams[trick_winner]
        self.tricks[winner_team] += 1
        
        # Prepare result
        result = {
            "trick_complete": True,
            "trick_winner": trick_winner,
            "team_tricks": self.tricks.copy(),
            "next_player": trick_winner
        }
        
        # Check hand completion
        if any(count >= 7 for count in self.tricks.values()):
            result.update(self._complete_hand())
            
        # Reset for next trick
        self.current_trick = []
        self.led_suit = None
        self.current_turn = self.players.index(trick_winner)
        
        return result

    def _complete_hand(self) -> Dict[str, Any]:
        """Handle hand completion and scoring"""
        winning_team = 0 if self.tricks[0] >= 7 else 1
        is_sweep = self.tricks[1 - winning_team] == 0
        
        # Calculate score based on sweep rules
        if winning_team == 0:
            self.scores[0] += 2 if is_sweep else 1
        else:
            self.scores[1] += 3 if is_sweep else 1
        
        result = {
            "hand_complete": True,
            "winning_team": winning_team,
            "scores": self.scores.copy(),
            "game_over": self.scores[winning_team] >= 7
        }
        
        if result["game_over"]:
            self.game_phase = "completed"
        else:
            self._prepare_new_hand()
            
        return result

    def _prepare_new_hand(self):
        """Reset state for new hand"""
        self.deck = self._create_deck()
        self.hands = {p: [] for p in self.players}
        self.trump_suit = None
        self.tricks = {0: 0, 1: 0}
        self.current_trick = []
        self.led_suit = None
        self.game_phase = "initial_deal"

    def _card_value(self, rank: str) -> int:
        """Get numeric value for card comparison"""
        values = {
            '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7,
            '8': 8, '9': 9, '10': 10, 'J': 11, 'Q': 12, 'K': 13, 'A': 14
        }
        return values.get(rank, 0)

    def get_state(self, player: Optional[str] = None) -> Dict[str, Any]:
        """Get current game state"""
        state = {
            "phase": self.game_phase,
            "teams": self.teams.copy(),
            "hakem": self.hakem,
            "trump_suit": self.trump_suit,
            "current_turn": self.players[self.current_turn] if self.game_phase == "gameplay" else None,
            "tricks": self.tricks.copy(),
            "scores": self.scores.copy(),
            "led_suit": self.led_suit,
            "current_trick": [(p, card) for p, card in self.current_trick]
        }
        
        if player:
            state["your_hand"] = self.hands.get(player, [])
            state["your_team"] = self.teams.get(player, -1)
        else:
            state["all_hands"] = {p: cards.copy() for p, cards in self.hands.items()}
            
        return state

# Utility function for card display
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
    except:
        return card
