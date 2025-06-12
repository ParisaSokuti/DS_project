# game_board.py
import random
import json
import time
from typing import List, Dict, Tuple, Optional, Any, ClassVar

class GameBoard:
    def __init__(self, players: List[str], room_code: Optional[str] = None):
        if len(players) != 4:
            raise ValueError("Hokm requires exactly 4 players")
        
        # Game state components
        self.players = players.copy()  # Maintain original order until team assignment
        self.deck = self._create_deck()
        self.teams = {}
        self.hakem = None
        self.hokm = None
        self.current_turn = 0
        self.tricks = {0: 0, 1: 0}          # current‐hand trick counts
        self.round_scores = {0: 0, 1: 0}   # number of hands won per team
        self.completed_tricks = 0         # count of tricks played in this hand
        self.hands = {player: [] for player in players}
        self.current_trick = []
        self.led_suit = None
        self.game_phase = "lobby"  # lobby -> initial_deal -> hokm_selection -> gameplay -> completed
        self.played_cards = []  # Track all played cards
        
        # Room tracking for persistence
        self.room_code = room_code  # Store room code for Redis operations
        self.created_at = int(time.time())
        self.last_move_at = self.created_at

    def _create_deck(self) -> List[str]:
        """Create a standard 52-card deck"""
        suits = ['hearts', 'diamonds', 'clubs', 'spades']
        ranks = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
        return [f"{rank}_{suit}" for suit in suits for rank in ranks]

    def assign_teams_and_hakem(self, redis_manager=None) -> Dict[str, Any]:
        """
        Assign teams using the following flow:
        1. Choose 1 player randomly for Team 1
        2. Select a second player from remaining 3 players for Team 1
        3. Assign remaining 2 players to Team 2
        4. Choose Hakem randomly from all players (equal chance for everyone)
        """
        print("=== Team Assignment Process ===")
        print(f"Players: {self.players}")
        
        # Step 1: Choose first player for Team 1
        first_team1_player = random.choice(self.players)
        print(f"First Team 1 player selected: {first_team1_player}")
        
        # Step 2: Choose second player for Team 1 from remaining players
        remaining_players = [p for p in self.players if p != first_team1_player]
        second_team1_player = random.choice(remaining_players)
        print(f"Second Team 1 player selected: {second_team1_player}")
        
        # Step 3: Assign remaining players to Team 2
        team2_players = [p for p in remaining_players if p != second_team1_player]
        print(f"Team 2 players: {team2_players}")
        
        # Step 4: Choose Hakem randomly from all players (equal chance)
        self.hakem = random.choice(self.players)
        print(f"Hakem selected (random from all players): {self.hakem}")
        
        # Assign teams
        self.teams = {
            first_team1_player: 0,
            second_team1_player: 0,
            team2_players[0]: 1,
            team2_players[1]: 1
        }
        
        # Reorder players: Hakem first, then clockwise order
        hakem_idx = self.players.index(self.hakem)
        self.players = self.players[hakem_idx:] + self.players[:hakem_idx]
        self.current_turn = 0
        
        self.game_phase = "initial_deal"
        
        # Save team assignments and hakem selection to Redis
        if self.room_code and redis_manager:
            game_state = {
                'teams': json.dumps(self.teams),
                'hakem': self.hakem,
                'phase': 'team_assignment'
            }
            redis_manager.save_game_state(self.room_code, game_state)
        
        result = {
            "teams": {
                "1": [first_team1_player, second_team1_player],
                "2": team2_players
            },
            "hakem": self.hakem
        }
        
        print(f"Teams: Team 1: {[first_team1_player, second_team1_player]}")
        print(f"       Team 2: {team2_players}")
        print("=== End Team Assignment ===\n")
        
        return result

    def initial_deal(self) -> Dict[str, List[str]]:
        """Deal first 5 cards to all players"""
        if self.game_phase != "initial_deal":
            raise ValueError("Invalid game phase for initial deal")
        
        random.shuffle(self.deck)
        for _ in range(5):
            for player in self.players:
                self.hands[player].append(self.deck.pop(0))
        
        print(f"[LOG] Initial deal completed. Changing phase from {self.game_phase} to hokm_selection")
        self.game_phase = "hokm_selection"
        return {p: self.hands[p].copy() for p in self.players}

    def set_hokm(self, suit: str, redis_manager=None, room_code=None) -> bool:
        """Validate and set hokm suit with Redis persistence and broadcasting"""
        if self.game_phase != "hokm_selection":
            print(f"[ERROR] Cannot set hokm in phase: {self.game_phase}. Expected: hokm_selection")
            return False
        
        if suit.lower() not in {'hearts', 'diamonds', 'clubs', 'spades'}:
            print(f"[ERROR] Invalid hokm suit: {suit}")
            return False
        
        print(f"[LOG] Setting hokm to {suit.lower()} and changing phase from {self.game_phase} to final_deal")
        self.hokm = suit.lower()
        self.game_phase = "final_deal"
        
        # Store hokm selection in Redis
        if self.room_code and redis_manager:
            try:
                # Save game state with hokm selection
                game_state = {
                    'phase': self.game_phase,
                    'hokm': self.hokm,
                    'hakem': self.hakem,
                    'last_activity': str(int(time.time()))
                }
                redis_manager.save_game_state(self.room_code, game_state)
                
                # Store room_code for future operations if provided externally
                if room_code:
                    self.room_code = room_code
                
            except Exception as e:
                print(f"[WARNING] Failed to persist hokm selection: {str(e)}")
        
        return True

    def broadcast_hokm_selection(self, redis_manager, network_manager):
        """Broadcast hokm selection to all players - call this from server.py"""
        if not (redis_manager and hasattr(self, 'room_code') and self.room_code):
            return
            
        try:
            import asyncio
            # Create the broadcast task
            broadcast_data = {
                'hokm': self.hokm,
                'hakem': self.hakem,
                'phase': self.game_phase,
                'timestamp': str(int(time.time()))
            }
            
            # This will be called from server.py with proper async context
            print(f"📡 Broadcasting hokm selection '{self.hokm}' to room {self.room_code}")
            return broadcast_data
        except Exception as e:
            print(f"[ERROR] Failed to prepare hokm broadcast: {str(e)}")
            return None

    def final_deal(self, redis_manager=None) -> Dict[str, List[str]]:
        """Deal remaining 8 cards after hokm selection with Redis persistence"""
        if self.game_phase != "final_deal":
            raise ValueError("Invalid game phase for final deal")
        
        # Deal remaining cards in Hakem-first order
        for _ in range(8):
            for player in self.players:
                if self.deck:
                    self.hands[player].append(self.deck.pop(0))
        
        self.game_phase = "gameplay"
        
        # 🔥 NEW: Persist final deal state
        if redis_manager and hasattr(self, 'room_code') and self.room_code:
            try:
                game_state = self.to_redis_dict()
                redis_manager.save_game_state(self.room_code, game_state)
                print(f"✅ Final deal saved to Redis for room {self.room_code}")
            except Exception as e:
                print(f"[WARNING] Failed to persist final deal: {str(e)}")
        
        return {p: self.hands[p].copy() for p in self.players}

    def validate_play(self, player, card):
        # Only allow play if it's player's turn and card is in hand
        if self.game_phase != "gameplay":
            return False, "Game not in progress"
        if player != self.players[self.current_turn]:
            return False, "Not your turn"
        if card not in self.hands[player]:
            return False, "Card not in hand"

        # Enforce follow suit
        if self.current_trick:
            led_suit = self.current_trick[0][1].split('_')[1]
            card_suit = card.split('_')[1]
            has_led_suit = any(c.split('_')[1] == led_suit for c in self.hands[player])
            if has_led_suit and card_suit != led_suit:
                return False, f"You must follow suit: {led_suit}"
        return True, ""

    def play_card(self, player: str, card: str, redis_manager=None) -> Dict[str, Any]:
        """
        Process a card play and update game state.
        If redis_manager is provided, persists state after the move.
        """
        valid, message = self.validate_play(player, card)
        if not valid:
            return {"valid": False, "message": message}
        
        try:
            # Remove card from hand and add to trick
            self.hands[player].remove(card)
            self.played_cards.append(card)  # Track played card
            
            # Add card to current trick
            self.current_trick.append((player, card))
            
            # Set led suit if first card in trick
            if len(self.current_trick) == 1:
                self.led_suit = card.split('_')[1]
            
            # Move to next player
            self.current_turn = (self.current_turn + 1) % 4
            
            result = {
                "valid": True,
                "trick_complete": False,
                "player": player,
                "card": card,
                "next_turn": self.players[self.current_turn],
                "led_suit": self.led_suit
            }
            
            # Check if trick is complete
            if len(self.current_trick) == 4:
                trick_result = self._resolve_trick()
                result.update(trick_result)
                
            # Persist state if Redis manager provided
            if redis_manager and hasattr(self, 'room_code'):
                try:
                    # Get serialized state
                    game_state = self.to_redis_dict()
                    
                    # Add move history
                    move_data = {
                        'player': player,
                        'card': card,
                        'timestamp': str(int(time.time())),
                        'trick_number': len(self.played_cards) // 4
                    }
                    
                    # Get existing move history or start new
                    move_history_key = f'moves:{self.room_code}'
                    redis_manager.redis.rpush(move_history_key, json.dumps(move_data))
                    
                    # Save game state
                    redis_manager.save_game_state(self.room_code, game_state)
                    
                except Exception as e:
                    print(f"[WARNING] Failed to persist game state: {str(e)}")
                    # Don't block the game if persistence fails
                    pass
                    
            return result
            
        except Exception as e:
            print(f"[ERROR] Error processing card play: {str(e)}")
            return {"valid": False, "message": "Internal error processing move"}

    def _resolve_trick(self) -> Dict[str, Any]:
        """Determine trick winner and update game state"""
        trick_winner = None
        highest_value = -1
        trump_played = False
        
        for player, card in self.current_trick:
            rank, suit = card.split('_')
            value = self._card_value(rank)
            
            # Hokm handling
            if suit == self.hokm:
                if not trump_played or value > highest_value:
                    trick_winner = player
                    highest_value = value
                    trump_played = True
            elif not trump_played and suit == self.led_suit:
                if value > highest_value:
                    trick_winner = player
                    highest_value = value
        
        # update trick‐counts
        winner_idx = self.teams[trick_winner]
        self.tricks[winner_idx] += 1
        self.completed_tricks += 1

        # decide if this hand (13 tricks) is done
        hand_done = (self.completed_tricks >= 13)

        result = {
            "trick_complete": True,
            "trick_winner": trick_winner,
            "team_tricks": self.tricks.copy(),      # e.g. {0:8,1:5}
            "next_player": trick_winner,
            "hand_complete": hand_done
        }
        
        # Reset for next trick
        self.current_trick = []
        self.led_suit = None
        self.current_turn = self.players.index(trick_winner)
        
        if hand_done:
            # determine which team won this hand
            # (tie goes to Hakem’s team or pick arbitrary)
            if self.tricks[0] > self.tricks[1]:
                hand_winner_idx = 0
            else:
                hand_winner_idx = 1

            # record round score
            self.round_scores[hand_winner_idx] += 1
            result["round_winner"]  = hand_winner_idx + 1
            result["round_scores"]  = self.round_scores.copy()

            # check for game over (first to 7 hand‐wins)
            if self.round_scores[hand_winner_idx] >= 7:
                self.game_phase = "completed"
                result["game_complete"] = True

            # reset for next hand
            self._prepare_new_hand()

        return result

    def _prepare_new_hand(self):
        """Reset state for new hand"""
        self.deck = self._create_deck()
        self.hands = {p: [] for p in self.players}
        self.hokm = None
        self.tricks = {0: 0, 1: 0}
        self.completed_tricks = 0
        self.current_trick = []
        self.led_suit = None
        self.game_phase = "initial_deal"
        self.played_cards = []

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
            "hokm": self.hokm,
            "current_turn": self.players[self.current_turn] if self.game_phase == "gameplay" else None,
            "tricks": self.tricks.copy(),
            "led_suit": self.led_suit,
            "current_trick": [(p, card) for p, card in self.current_trick]
        }
        
        if player:
            state["your_hand"] = self.hands.get(player, [])
            state["your_team"] = self.teams.get(player, -1)
        else:
            state["all_hands"] = {p: cards.copy() for p, cards in self.hands.items()}
            
        return state
        
    def to_redis_dict(self) -> Dict[str, str]:
        """
        Serialize the game state to a Redis-compatible dictionary.
        All values must be strings or JSON-encoded strings.
        """
        try:
            game_state = {
                # Basic game state
                'game_phase': self.game_phase,
                'hokm': self.hokm or '',
                'hakem': self.hakem or '',
                
                # Players and teams
                'players': json.dumps(self.players),
                'teams': json.dumps(self.teams),
                'current_turn': str(self.current_turn),
                
                # Game progress
                'tricks': json.dumps(self.tricks),
                'round_scores': json.dumps(self.round_scores),
                'completed_tricks': str(self.completed_tricks),
                'led_suit': self.led_suit or '',
                'current_trick': json.dumps(self.current_trick),
                'played_cards': json.dumps(self.played_cards),
                
                # Player hands (stored separately for privacy)
                **{f'hand_{player}': json.dumps(hand) 
                   for player, hand in self.hands.items()},
                
                # Metadata
                'created_at': str(getattr(self, 'created_at', int(time.time()))),
                'last_activity': str(int(time.time())),
                'last_updated': str(int(time.time()))
            }
            return game_state
        except Exception as e:
            print(f"Error serializing game state: {str(e)}")
            raise
            
    @classmethod
    def from_redis_dict(cls, state_dict: Dict[str, str], players: List[str]) -> 'GameBoard':
        """
        Create a new GameBoard instance from Redis-stored state dictionary.
        
        Args:
            state_dict: Dictionary of game state from Redis
            players: List of player usernames
            
        Returns:
            GameBoard: New instance with restored state
        """
        try:
            # Create new instance
            game = cls(players)
            
            # Restore basic game state
            game.game_phase = state_dict.get('game_phase', 'lobby')
            game.hokm = state_dict.get('hokm') or None
            game.hakem = state_dict.get('hakem') or None
            
            # Restore players and teams
            if 'players' in state_dict:
                game.players = json.loads(state_dict['players'])
            if 'teams' in state_dict:
                game.teams = json.loads(state_dict['teams'])
            if 'current_turn' in state_dict:
                game.current_turn = int(state_dict['current_turn'])
                
            # Restore game progress
            if 'tricks' in state_dict:
                game.tricks = json.loads(state_dict['tricks'])
            if 'round_scores' in state_dict:
                game.round_scores = json.loads(state_dict['round_scores'])
            if 'completed_tricks' in state_dict:
                game.completed_tricks = int(state_dict['completed_tricks'])
            game.led_suit = state_dict.get('led_suit') or None
            if 'current_trick' in state_dict:
                game.current_trick = json.loads(state_dict['current_trick'])
            if 'played_cards' in state_dict:
                game.played_cards = json.loads(state_dict['played_cards'])
                
            # Restore player hands
            game.hands = {}
            for player in players:
                hand_key = f'hand_{player}'
                if hand_key in state_dict:
                    game.hands[player] = json.loads(state_dict[hand_key])
                else:
                    game.hands[player] = []
                    
            return game
            
        except Exception as e:
            print(f"Error deserializing game state: {str(e)}")
            raise
            
    def validate_state(self) -> bool:
        """
        Validate the consistency of the game state after deserialization.
        Returns True if state is valid, False otherwise.
        """
        try:
            # Validate player lists
            if not isinstance(self.players, list) or len(self.players) != 4:
                return False
                
            # Validate teams
            if not isinstance(self.teams, dict) or len(self.teams) != 4:
                return False
                
            # Validate hands
            if not isinstance(self.hands, dict) or len(self.hands) != 4:
                return False
                
            # Validate card consistency
            played = set(self.played_cards)
            in_hands = set()
            for hand in self.hands.values():
                in_hands.update(hand)
                
            # No card should be both played and in hand
            if played & in_hands:
                return False
                
            # Validate current turn
            if not isinstance(self.current_turn, int) or self.current_turn < 0 or self.current_turn >= 4:
                return False
                
            return True
            
        except Exception:
            return False

