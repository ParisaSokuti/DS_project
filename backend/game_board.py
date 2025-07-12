"""
Optimized Hokm Game Board
High-performance game logic for Persian card game
"""

import random
import time
from typing import List, Dict, Tuple, Optional, Any, Set

class GameBoard:
    """Optimized game board with efficient state management"""
    
    # Class-level constants for better performance
    SUITS = ['hearts', 'diamonds', 'clubs', 'spades']
    RANKS = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
    DECK_SIZE = 52
    HAND_SIZE = 13
    
    def __init__(self, players: List[str], room_code: Optional[str] = None):
        if len(players) != 4:
            raise ValueError("Hokm requires exactly 4 players")
        
        # Core game state
        self.players = players.copy()
        self.deck = self._create_deck()
        self.teams = {}
        self.hakem = None
        self.hokm = None
        self.current_turn = 0
        
        # Optimized scoring with default dict behavior
        self.tricks = {0: 0, 1: 0}
        self.round_scores = {0: 0, 1: 0}
        self.player_tricks = {player: 0 for player in players}
        
        # Game state tracking
        self.completed_tricks = 0
        self.hands = {player: [] for player in players}
        self.current_trick = []
        self.led_suit = None
        self.game_phase = "lobby"
        self.played_cards = []
        
        # Room metadata
        self.room_code = room_code
        self.created_at = int(time.time())
        self.last_move_at = self.created_at

    def _create_deck(self) -> List[str]:
        """Create a standard 52-card deck with optimized generation"""
        return [f"{rank}_{suit}" for suit in self.SUITS for rank in self.RANKS]

    def assign_teams_and_hakem(self, redis_manager=None) -> Dict[str, Any]:
        """Assign teams and hakem efficiently"""
        if len(self.players) != 4:
            return {"error": f"Expected 4 players, got {len(self.players)}"}
        
        # Random team assignment (2 players each)
        shuffled = self.players.copy()
        random.shuffle(shuffled)
        
        self.teams = {
            shuffled[0]: 0, shuffled[1]: 0,  # Team 1
            shuffled[2]: 1, shuffled[3]: 1   # Team 2
        }
        
        # Random hakem selection
        self.hakem = random.choice(self.players)
        
        # Reorder players with hakem first
        hakem_idx = self.players.index(self.hakem)
        self.players = self.players[hakem_idx:] + self.players[:hakem_idx]
        self.current_turn = 0
        
        print(f"[GAME] Teams: {self._get_team_display()}, Hakem: {self.hakem}")
        
        return {
            "teams": self.teams,
            "hakem": self.hakem,
            "players": self.players
        }

    def _get_team_display(self) -> Dict[int, List[str]]:
        """Get teams organized by team number"""
        teams_display = {0: [], 1: []}
        for player, team in self.teams.items():
            teams_display[team].append(player)
        return teams_display

    def initial_deal(self) -> Dict[str, List[str]]:
        """Deal initial 5 cards to each player"""
        if self.game_phase != "lobby":
            return {"error": "Invalid game phase for initial deal"}
        
        random.shuffle(self.deck)
        
        # Deal 5 cards per player in hakem-first order
        for _ in range(5):
            for player in self.players:
                if self.deck:
                    self.hands[player].append(self.deck.pop(0))
        
        self.game_phase = "waiting_for_hokm"
        return {player: hand.copy() for player, hand in self.hands.items()}

    def set_hokm(self, suit: str, redis_manager=None, room_code=None) -> bool:
        """Set hokm suit"""
        valid_suits = ['hearts', 'diamonds', 'clubs', 'spades']
        if suit not in valid_suits:
            return False
        
        self.hokm = suit
        self.game_phase = "final_deal"
        print(f"[GAME] Hokm set to {suit}")
        return True

    def final_deal(self, redis_manager=None) -> Dict[str, List[str]]:
        """Deal remaining 8 cards after hokm selection"""
        if self.game_phase != "final_deal":
            raise ValueError("Invalid game phase for final deal")
        
        # Deal remaining cards in hakem-first order
        for _ in range(8):
            for player in self.players:
                if self.deck:
                    self.hands[player].append(self.deck.pop(0))
        
        self.game_phase = "gameplay"
        return {player: hand.copy() for player, hand in self.hands.items()}

    def validate_play(self, player: str, card: str) -> Tuple[bool, str]:
        """Validate if a card play is legal"""
        if self.game_phase != "gameplay":
            return False, "Game not in progress"
        if player != self.players[self.current_turn]:
            return False, "Not your turn"
        if card not in self.hands[player]:
            return False, "Card not in hand"

        # Follow suit rule
        if self.current_trick:
            led_suit = self.current_trick[0][1].split('_')[1]
            card_suit = card.split('_')[1]
            has_led_suit = any(c.split('_')[1] == led_suit for c in self.hands[player])
            if has_led_suit and card_suit != led_suit:
                return False, f"Must follow suit: {led_suit}"
        
        return True, ""

    def play_card(self, player: str, card: str, redis_manager=None) -> Dict[str, Any]:
        """Process a card play and update game state"""
        valid, message = self.validate_play(player, card)
        if not valid:
            return {"valid": False, "message": message}
        
        # Remove card and add to trick
        self.hands[player].remove(card)
        self.played_cards.append(card)
        self.current_trick.append((player, card))
        
        # Set led suit for first card
        if len(self.current_trick) == 1:
            self.led_suit = card.split('_')[1]
        
        # Move to next player
        self.current_turn = (self.current_turn + 1) % 4
        next_player = self.players[self.current_turn]
        
        result = {
            "valid": True,
            "trick_complete": False,
            "next_turn": next_player,
            "led_suit": self.led_suit
        }
        
        # Check if trick is complete
        if len(self.current_trick) == 4:
            trick_result = self._resolve_trick()
            result.update(trick_result)
        
        self.last_move_at = int(time.time())
        return result

    def _resolve_trick(self) -> Dict[str, Any]:
        """Resolve a completed trick"""
        winner = self._find_trick_winner()
        winner_team = self.teams[winner]
        
        # Update scores
        self.tricks[winner_team] += 1
        self.player_tricks[winner] += 1
        self.completed_tricks += 1
        
        # Set winner as next player to lead
        self.current_turn = self.players.index(winner)
        
        # Clear trick state
        self.current_trick = []
        self.led_suit = None
        
        print(f"[GAME] Trick {self.completed_tricks}: {winner} wins, Team {winner_team+1} tricks: {self.tricks[winner_team]}")
        
        result = {
            "trick_complete": True,
            "trick_winner": winner,
            "team_tricks": self.tricks.copy(),
            "next_turn": winner
        }
        
        # Check if hand is complete (13 tricks)
        if self.completed_tricks >= 13:
            hand_result = self._resolve_hand()
            result.update(hand_result)
        
        return result

    def _find_trick_winner(self) -> str:
        """Find the winner of the current trick"""
        if not self.current_trick or len(self.current_trick) != 4:
            raise ValueError("Cannot determine winner of incomplete trick")
        
        led_suit = self.current_trick[0][1].split('_')[1]
        hokm_played = any(card.split('_')[1] == self.hokm for _, card in self.current_trick)
        
        if hokm_played:
            # Highest hokm wins
            hokm_cards = [(player, card) for player, card in self.current_trick 
                         if card.split('_')[1] == self.hokm]
            return max(hokm_cards, key=lambda x: self._card_value(x[1]))[0]
        else:
            # Highest card of led suit wins
            led_suit_cards = [(player, card) for player, card in self.current_trick 
                             if card.split('_')[1] == led_suit]
            return max(led_suit_cards, key=lambda x: self._card_value(x[1]))[0]

    def _card_value(self, card: str) -> int:
        """Get numeric value of card for comparison"""
        rank = card.split('_')[0]
        values = {'2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, 
                 '9': 9, '10': 10, 'J': 11, 'Q': 12, 'K': 13, 'A': 14}
        return values.get(rank, 0)

    def _resolve_hand(self) -> Dict[str, Any]:
        """Resolve a completed hand"""
        team1_tricks = self.tricks[0]
        team2_tricks = self.tricks[1]
        
        # Determine winning team (team with more tricks)
        if team1_tricks > team2_tricks:
            winner_team = 0
            round_winner = 1  # Team number for display
        else:
            winner_team = 1
            round_winner = 2
        
        # Award round score
        self.round_scores[winner_team] += 1
        
        print(f"[GAME] Hand complete: Team {round_winner} wins ({self.tricks[winner_team]} tricks)")
        
        result = {
            "hand_complete": True,
            "round_winner": round_winner,
            "round_scores": self.round_scores.copy(),
            "team_tricks": self.tricks.copy()
        }
        
        # Check if game is complete (best of 3 hands)
        if self.round_scores[winner_team] >= 2:
            self.game_phase = "completed"
            result["game_complete"] = True
            print(f"[GAME] Game complete: Team {round_winner} wins!")
        
        return result

    def start_new_round(self, redis_manager=None) -> Dict[str, List[str]]:
        """Start a new round after hand completion"""
        if self.game_phase == "completed":
            return {"error": "Game is already completed"}
        
        # Reset hand state
        self.deck = self._create_deck()
        self.hands = {player: [] for player in self.players}
        self.tricks = {0: 0, 1: 0}
        self.player_tricks = {player: 0 for player in self.players}
        self.completed_tricks = 0
        self.current_trick = []
        self.led_suit = None
        self.played_cards = []
        self.hokm = None
        
        # Rotate hakem to next player
        current_hakem_idx = self.players.index(self.hakem)
        new_hakem_idx = (current_hakem_idx + 1) % 4
        self.hakem = self.players[new_hakem_idx]
        
        # Reorder players with new hakem first
        self.players = self.players[new_hakem_idx:] + self.players[:new_hakem_idx]
        self.current_turn = 0
        
        # Deal initial cards
        self.game_phase = "waiting_for_hokm"
        return self.initial_deal()

    def get_new_round_info(self) -> Dict[str, Any]:
        """Get information for new round start"""
        return {
            "hakem": self.hakem,
            "round_scores": self.round_scores.copy(),
            "message": f"New round started. {self.hakem} is the new Hakem."
        }

    def to_redis_dict(self) -> Dict[str, Any]:
        """Convert game state to Redis-serializable dictionary"""
        return {
            'players': self.players,
            'teams': self.teams,
            'hakem': self.hakem,
            'hokm': self.hokm,
            'current_turn': self.current_turn,
            'tricks': self.tricks,
            'round_scores': self.round_scores,
            'player_tricks': self.player_tricks,
            'completed_tricks': self.completed_tricks,
            'hands': self.hands,
            'current_trick': self.current_trick,
            'led_suit': self.led_suit,
            'game_phase': self.game_phase,
            'phase': self.game_phase,  # Add phase field for validation compatibility
            'played_cards': self.played_cards,
            'room_code': self.room_code,
            'created_at': self.created_at,
            'last_move_at': self.last_move_at
        }

    @classmethod
    def from_redis_dict(cls, data: Dict[str, Any]) -> 'GameBoard':
        """Create GameBoard instance from Redis data"""
        players = data.get('players', [])
        room_code = data.get('room_code')
        
        # Create instance
        game = cls(players, room_code)
        
        # Restore state
        for key, value in data.items():
            if hasattr(game, key):
                setattr(game, key, value)
        
        return game

    def get_game_state_summary(self) -> Dict[str, Any]:
        """Get a summary of current game state"""
        return {
            'phase': self.game_phase,
            'hakem': self.hakem,
            'hokm': self.hokm,
            'current_player': self.players[self.current_turn] if self.players else None,
            'tricks': self.tricks,
            'round_scores': self.round_scores,
            'completed_tricks': self.completed_tricks,
            'teams': self._get_team_display()
        }
