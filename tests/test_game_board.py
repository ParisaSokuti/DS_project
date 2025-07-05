"""
Unit tests for the GameBoard class.

Tests cover:
1. Card deck creation and shuffling
2. Team assignment logic fairness  
3. Hokm selection validation
4. Card play validation (suit following)
5. Trick winner calculation
6. Round scoring logic

Usage:
    pytest tests/test_game_board.py
    pytest tests/test_game_board.py -v  # verbose output
    pytest tests/test_game_board.py::TestDeckCreation  # specific test class
"""

import pytest
import json
import time
from unittest.mock import Mock, patch, MagicMock
from collections import Counter

# Add backend directory to path for imports
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from game_board import GameBoard


class TestGameBoardInitialization:
    """Test GameBoard initialization and basic setup."""
    
    def test_initialization_with_valid_players(self):
        """Test creating GameBoard with exactly 4 players."""
        players = ["Player1", "Player2", "Player3", "Player4"]
        game = GameBoard(players)
        
        assert game.players == players
        assert len(game.deck) == 52
        assert game.teams == {}
        assert game.hakem is None
        assert game.hokm is None
        assert game.current_turn == 0
        assert game.tricks == {0: 0, 1: 0}
        assert game.round_scores == {0: 0, 1: 0}
        assert game.game_phase == "lobby"
        assert len(game.hands) == 4
        for player in players:
            assert game.hands[player] == []
    
    def test_initialization_with_room_code(self):
        """Test GameBoard initialization with room code."""
        players = ["P1", "P2", "P3", "P4"]
        room_code = "TEST123"
        game = GameBoard(players, room_code)
        
        assert game.room_code == room_code
        assert hasattr(game, 'created_at')
        assert hasattr(game, 'last_move_at')
    
    def test_initialization_invalid_player_count(self):
        """Test GameBoard rejects invalid player counts."""
        # Too few players
        with pytest.raises(ValueError, match="Hokm requires exactly 4 players"):
            GameBoard(["P1", "P2"])
        
        # Too many players
        with pytest.raises(ValueError, match="Hokm requires exactly 4 players"):
            GameBoard(["P1", "P2", "P3", "P4", "P5"])
        
        # Empty list
        with pytest.raises(ValueError, match="Hokm requires exactly 4 players"):
            GameBoard([])


class TestDeckCreation:
    """Test card deck creation and properties."""
    
    def test_deck_creation(self):
        """Test deck is created with correct cards."""
        players = ["P1", "P2", "P3", "P4"]
        game = GameBoard(players)
        
        assert len(game.deck) == 52
        
        # Check all expected cards are present
        expected_suits = ['hearts', 'diamonds', 'clubs', 'spades']
        expected_ranks = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
        
        for suit in expected_suits:
            for rank in expected_ranks:
                expected_card = f"{rank}_{suit}"
                assert expected_card in game.deck
    
    def test_deck_uniqueness(self):
        """Test deck contains no duplicate cards."""
        players = ["P1", "P2", "P3", "P4"]
        game = GameBoard(players)
        
        # Check for duplicates
        card_counts = Counter(game.deck)
        for card, count in card_counts.items():
            assert count == 1, f"Card {card} appears {count} times"
    
    def test_deck_composition(self):
        """Test deck has correct number of each suit and rank."""
        players = ["P1", "P2", "P3", "P4"]
        game = GameBoard(players)
        
        # Count suits
        suits = [card.split('_')[1] for card in game.deck]
        suit_counts = Counter(suits)
        assert all(count == 13 for count in suit_counts.values())
        
        # Count ranks
        ranks = [card.split('_')[0] for card in game.deck]
        rank_counts = Counter(ranks)
        assert all(count == 4 for count in rank_counts.values())


class TestTeamAssignment:
    """Test team assignment logic and fairness."""
    
    @patch('random.choice')
    def test_team_assignment_deterministic(self, mock_choice):
        """Test team assignment with mocked randomness."""
        players = ["Alice", "Bob", "Charlie", "Diana"]
        game = GameBoard(players)
        
        # Mock random choices: Alice for team1, Bob for team1 partner, Charlie as hakem
        mock_choice.side_effect = ["Alice", "Bob", "Charlie"]
        
        result = game.assign_teams_and_hakem()
        
        # Check team assignments
        assert game.teams["Alice"] == 0  # Team 1
        assert game.teams["Bob"] == 0    # Team 1
        assert game.teams["Charlie"] == 1  # Team 2
        assert game.teams["Diana"] == 1    # Team 2
        
        # Check hakem
        assert game.hakem == "Charlie"
        
        # Check return structure
        assert "teams" in result
        assert "hakem" in result
        assert result["teams"]["1"] == ["Alice", "Bob"]
        assert result["teams"]["2"] == ["Charlie", "Diana"]
        assert result["hakem"] == "Charlie"
    
    def test_team_assignment_fairness(self):
        """Test team assignment distributes fairly over multiple runs."""
        players = ["P1", "P2", "P3", "P4"]
        
        team_assignments = {player: {"team1": 0, "team2": 0} for player in players}
        hakem_assignments = {player: 0 for player in players}
        
        # Run many assignments
        for _ in range(1000):
            game = GameBoard(players.copy())
            result = game.assign_teams_and_hakem()
            
            # Count team assignments
            for team_id, team_players in result["teams"].items():
                for player in team_players:
                    team_key = f"team{team_id}"
                    team_assignments[player][team_key] += 1
            
            # Count hakem assignments
            hakem_assignments[result["hakem"]] += 1
        
        # Check fairness (allow some variance)
        for player in players:
            # Each player should be on team1 roughly 50% of the time
            team1_ratio = team_assignments[player]["team1"] / 1000
            assert 0.4 < team1_ratio < 0.6, f"Player {player} team1 ratio: {team1_ratio}"
            
            # Each player should be hakem roughly 25% of the time
            hakem_ratio = hakem_assignments[player] / 1000
            assert 0.15 < hakem_ratio < 0.35, f"Player {player} hakem ratio: {hakem_ratio}"
    
    def test_team_assignment_game_state_changes(self):
        """Test team assignment properly updates game state."""
        players = ["P1", "P2", "P3", "P4"]
        game = GameBoard(players)
        
        initial_phase = game.game_phase
        result = game.assign_teams_and_hakem()
        
        # Check phase transition
        assert game.game_phase == "initial_deal"
        
        # Check hakem is first in player order
        assert game.players[0] == game.hakem
        assert game.current_turn == 0
        
        # Check all players assigned to teams
        assert len(game.teams) == 4
        assert set(game.teams.keys()) == set(players)
        
        # Check team distribution (2 players per team)
        team_counts = Counter(game.teams.values())
        assert team_counts[0] == 2
        assert team_counts[1] == 2


class TestHokmSelection:
    """Test hokm selection validation and logic."""
    
    def test_valid_hokm_selection(self):
        """Test setting valid hokm suit."""
        players = ["P1", "P2", "P3", "P4"]
        game = GameBoard(players)
        game.game_phase = "hokm_selection"  # Set correct phase
        
        valid_suits = ['hearts', 'diamonds', 'clubs', 'spades']
        
        for suit in valid_suits:
            game_copy = GameBoard(players)
            game_copy.game_phase = "hokm_selection"
            
            result = game_copy.set_hokm(suit)
            assert result is True
            assert game_copy.hokm == suit.lower()
            assert game_copy.game_phase == "final_deal"
    
    def test_invalid_hokm_selection(self):
        """Test rejecting invalid hokm suits."""
        players = ["P1", "P2", "P3", "P4"]
        game = GameBoard(players)
        game.game_phase = "hokm_selection"
        
        invalid_suits = ['invalidsuit', '', 'trump', 'joker', '123']
        
        for suit in invalid_suits:
            result = game.set_hokm(suit)
            assert result is False
            assert game.hokm is None
            assert game.game_phase == "hokm_selection"  # Phase unchanged
    
    def test_hokm_selection_wrong_phase(self):
        """Test hokm selection fails in wrong game phase."""
        players = ["P1", "P2", "P3", "P4"]
        game = GameBoard(players)
        
        wrong_phases = ["lobby", "initial_deal", "final_deal", "gameplay", "completed"]
        
        for phase in wrong_phases:
            game.game_phase = phase
            result = game.set_hokm("hearts")
            assert result is False
            assert game.hokm is None
    
    def test_hokm_selection_case_insensitive(self):
        """Test hokm selection handles different cases."""
        players = ["P1", "P2", "P3", "P4"]
        game = GameBoard(players)
        game.game_phase = "hokm_selection"
        
        test_cases = ["Hearts", "DIAMONDS", "cLuBs", "SPADES"]
        expected = ["hearts", "diamonds", "clubs", "spades"]
        
        for i, suit in enumerate(test_cases):
            game_copy = GameBoard(players)
            game_copy.game_phase = "hokm_selection"
            
            result = game_copy.set_hokm(suit)
            assert result is True
            assert game_copy.hokm == expected[i]


class TestCardPlayValidation:
    """Test card play validation including suit following."""
    
    def setup_method(self):
        """Set up game for card play tests."""
        self.players = ["P1", "P2", "P3", "P4"]
        self.game = GameBoard(self.players)
        self.game.game_phase = "gameplay"
        self.game.hokm = "hearts"
        
        # Give players some test cards
        self.game.hands = {
            "P1": ["A_hearts", "K_spades", "Q_diamonds"],
            "P2": ["J_hearts", "10_spades", "9_clubs"],
            "P3": ["8_hearts", "7_diamonds", "6_clubs"],
            "P4": ["5_hearts", "4_spades", "3_diamonds"]
        }
        self.game.current_turn = 0  # P1's turn
    
    def test_valid_card_play_first_card(self):
        """Test playing first card of trick."""
        valid, message = self.game.validate_play("P1", "A_hearts")
        assert valid is True
        assert message == ""
    
    def test_invalid_card_not_in_hand(self):
        """Test playing card not in hand."""
        valid, message = self.game.validate_play("P1", "2_clubs")
        assert valid is False
        assert "Card not in hand" in message
    
    def test_invalid_not_players_turn(self):
        """Test playing card when it's not player's turn."""
        valid, message = self.game.validate_play("P2", "J_hearts")  # P2 plays when it's P1's turn
        assert valid is False
        assert "Not your turn" in message
    
    def test_invalid_wrong_game_phase(self):
        """Test playing card in wrong game phase."""
        self.game.game_phase = "lobby"
        valid, message = self.game.validate_play("P1", "A_hearts")
        assert valid is False
        assert "Game not in progress" in message
    
    def test_suit_following_required(self):
        """Test suit following when player has led suit."""
        # P1 plays hearts (leads)
        self.game.current_trick = [("P1", "A_hearts")]
        self.game.current_turn = 1  # Now P2's turn
        
        # P2 has hearts but tries to play spades
        valid, message = self.game.validate_play("P2", "10_spades")
        assert valid is False
        assert "must follow suit: hearts" in message
    
    def test_suit_following_allowed_when_no_led_suit(self):
        """Test playing different suit when player has no led suit."""
        # P1 plays hearts (leads)
        self.game.current_trick = [("P1", "A_hearts")]
        self.game.current_turn = 1  # Now P2's turn
        
        # Remove hearts from P2's hand
        self.game.hands["P2"] = ["10_spades", "9_clubs", "8_diamonds"]
        
        # P2 should be allowed to play any suit
        valid, message = self.game.validate_play("P2", "10_spades")
        assert valid is True
        assert message == ""
    
    def test_suit_following_with_mixed_hand(self):
        """Test suit following validation with complex hand."""
        # Set up specific scenario
        self.game.hands["P2"] = ["J_hearts", "10_spades", "9_clubs", "8_diamonds"]
        self.game.current_trick = [("P1", "A_diamonds")]  # Diamonds led
        self.game.current_turn = 1  # P2's turn
        
        # P2 has diamonds but tries to play hearts
        valid, message = self.game.validate_play("P2", "J_hearts")
        assert valid is False
        assert "must follow suit: diamonds" in message
        
        # P2 plays diamonds - should be valid
        valid, message = self.game.validate_play("P2", "8_diamonds")
        assert valid is True


class TestCardPlay:
    """Test card play execution and state updates."""
    
    def setup_method(self):
        """Set up game for card play tests."""
        self.players = ["P1", "P2", "P3", "P4"]
        self.game = GameBoard(self.players)
        self.game.game_phase = "gameplay"
        self.game.hokm = "hearts"
        self.game.hands = {
            "P1": ["A_hearts", "K_spades"],
            "P2": ["J_hearts", "Q_spades"],
            "P3": ["10_hearts", "9_spades"],
            "P4": ["8_hearts", "7_spades"]
        }
        self.game.current_turn = 0
    
    def test_successful_card_play(self):
        """Test successful card play updates game state."""
        result = self.game.play_card("P1", "A_hearts")
        
        assert result["valid"] is True
        assert result["player"] == "P1"
        assert result["card"] == "A_hearts"
        assert result["next_turn"] == "P2"
        assert result["led_suit"] == "hearts"
        assert result["trick_complete"] is False
        
        # Check game state updates
        assert "A_hearts" not in self.game.hands["P1"]
        assert "A_hearts" in self.game.played_cards
        assert len(self.game.current_trick) == 1
        assert self.game.current_trick[0] == ("P1", "A_hearts")
        assert self.game.led_suit == "hearts"
        assert self.game.current_turn == 1
    
    def test_invalid_card_play_no_state_change(self):
        """Test invalid card play doesn't change game state."""
        original_hands = {p: cards.copy() for p, cards in self.game.hands.items()}
        original_turn = self.game.current_turn
        original_trick = self.game.current_trick.copy()
        
        result = self.game.play_card("P2", "J_hearts")  # Wrong turn
        
        assert result["valid"] is False
        
        # Check no state changes
        assert self.game.hands == original_hands
        assert self.game.current_turn == original_turn
        assert self.game.current_trick == original_trick
        assert len(self.game.played_cards) == 0


class TestTrickWinnerCalculation:
    """Test trick winner calculation with various scenarios."""
    
    def setup_method(self):
        """Set up game for trick winner tests."""
        self.players = ["P1", "P2", "P3", "P4"]
        self.game = GameBoard(self.players)
        self.game.game_phase = "gameplay"
        self.game.hokm = "hearts"
        self.game.teams = {"P1": 0, "P2": 1, "P3": 0, "P4": 1}
    
    def test_card_value_calculation(self):
        """Test card value calculation."""
        assert self.game._card_value("2") == 2
        assert self.game._card_value("10") == 10
        assert self.game._card_value("J") == 11
        assert self.game._card_value("Q") == 12
        assert self.game._card_value("K") == 13
        assert self.game._card_value("A") == 14
    
    def test_trick_winner_highest_led_suit(self):
        """Test trick winner when highest card of led suit wins."""
        self.game.current_trick = [
            ("P1", "7_spades"),   # Led suit
            ("P2", "J_spades"),   # Higher spade
            ("P3", "A_diamonds"), # Different suit
            ("P4", "K_clubs")     # Different suit
        ]
        self.game.led_suit = "spades"
        
        result = self.game._resolve_trick()
        
        assert result["trick_winner"] == "P2"  # Highest spade
        assert result["trick_complete"] is True
    
    def test_trick_winner_trump_beats_led_suit(self):
        """Test trump card beats higher led suit card."""
        self.game.current_trick = [
            ("P1", "A_spades"),   # Highest spade (led)
            ("P2", "2_hearts"),   # Lowest trump
            ("P3", "K_spades"),   # High spade
            ("P4", "Q_diamonds")  # Different suit
        ]
        self.game.led_suit = "spades"
        
        result = self.game._resolve_trick()
        
        assert result["trick_winner"] == "P2"  # Trump wins
    
    def test_trick_winner_highest_trump(self):
        """Test highest trump wins when multiple trumps played."""
        self.game.current_trick = [
            ("P1", "A_spades"),   # Led suit
            ("P2", "3_hearts"),   # Low trump
            ("P3", "K_hearts"),   # High trump
            ("P4", "7_hearts")    # Mid trump
        ]
        self.game.led_suit = "spades"
        
        result = self.game._resolve_trick()
        
        assert result["trick_winner"] == "P3"  # Highest trump
    
    def test_trick_updates_team_scores(self):
        """Test trick completion updates team trick counts."""
        initial_tricks = self.game.tricks.copy()
        
        self.game.current_trick = [
            ("P1", "A_spades"),
            ("P2", "K_spades"),
            ("P3", "Q_spades"),
            ("P4", "J_spades")
        ]
        self.game.led_suit = "spades"
        
        result = self.game._resolve_trick()
        
        winner_team = self.game.teams[result["trick_winner"]]
        assert self.game.tricks[winner_team] == initial_tricks[winner_team] + 1
        assert result["team_tricks"] == self.game.tricks


class TestRoundScoring:
    """Test round scoring and game completion logic."""
    
    def setup_method(self):
        """Set up game for scoring tests."""
        self.players = ["P1", "P2", "P3", "P4"]
        self.game = GameBoard(self.players)
        self.game.game_phase = "gameplay"
        self.game.hokm = "hearts"
        self.game.teams = {"P1": 0, "P2": 1, "P3": 0, "P4": 1}
        self.game.hakem = "P1"
    
    def test_hand_completion_seven_tricks(self):
        """Test hand completes when team reaches 7 tricks."""
        self.game.tricks = {0: 6, 1: 3}  # Team 0 about to win
        self.game.completed_tricks = 9
        
        # Simulate team 0 winning trick 7
        self.game.current_trick = [
            ("P1", "A_hearts"),
            ("P2", "K_spades"),
            ("P3", "Q_spades"),
            ("P4", "J_spades")
        ]
        self.game.led_suit = "hearts"
        
        result = self.game._resolve_trick()
        
        assert result["hand_complete"] is True
        assert result["round_winner"] == 1  # Team 0 (index 0) -> team number 1
        assert self.game.round_scores[0] == 1
    
    def test_hand_completion_all_tricks_played(self):
        """Test hand completes after 13 tricks even without 7 for one team."""
        self.game.tricks = {0: 6, 1: 6}  # Tied at 6-6
        self.game.completed_tricks = 12  # This will be trick 13
        
        self.game.current_trick = [
            ("P1", "A_hearts"),
            ("P2", "K_spades"),
            ("P3", "Q_spades"),
            ("P4", "J_spades")
        ]
        self.game.led_suit = "hearts"
        
        result = self.game._resolve_trick()
        
        assert result["hand_complete"] is True
        # Team 0 wins 7-6
        assert result["round_winner"] == 1  # Team 0 wins
        assert self.game.round_scores[0] == 1
    
    def test_game_completion_seven_rounds(self):
        """Test game completes when team wins 7 rounds."""
        self.game.round_scores = {0: 6, 1: 3}  # Team 0 about to win game
        self.game.tricks = {0: 6, 1: 3}
        self.game.completed_tricks = 9
        
        self.game.current_trick = [
            ("P1", "A_hearts"),
            ("P2", "K_spades"),
            ("P3", "Q_spades"),
            ("P4", "J_spades")
        ]
        self.game.led_suit = "hearts"
        
        result = self.game._resolve_trick()
        
        assert result["hand_complete"] is True
        assert result["game_complete"] is True
        assert self.game.game_phase == "completed"
        assert self.game.round_scores[0] == 7
    
    def test_new_hand_preparation(self):
        """Test preparation for new hand after completion."""
        # Set up completed hand state
        self.game.tricks = {0: 7, 1: 2}
        self.game.completed_tricks = 9
        self.game.played_cards = ["A_hearts", "K_spades"]
        self.game.current_trick = []
        
        # Mock the _select_new_hakem method to avoid complex setup
        with patch.object(self.game, '_select_new_hakem') as mock_select:
            mock_select.return_value = None
            self.game._prepare_new_hand()
        
        # Check reset state
        assert len(self.game.deck) == 52
        assert all(len(hand) == 0 for hand in self.game.hands.values())
        assert self.game.hokm is None
        assert self.game.tricks == {0: 0, 1: 0}
        assert self.game.completed_tricks == 0
        assert self.game.current_trick == []
        assert self.game.led_suit is None
        assert self.game.game_phase == "initial_deal"
        assert self.game.played_cards == []


class TestGameStateSerialization:
    """Test game state serialization and deserialization."""
    
    def setup_method(self):
        """Set up game for serialization tests."""
        self.players = ["P1", "P2", "P3", "P4"]
        self.game = GameBoard(self.players, "TEST_ROOM")
        self.game.teams = {"P1": 0, "P2": 1, "P3": 0, "P4": 1}
        self.game.hakem = "P1"
        self.game.hokm = "hearts"
        self.game.game_phase = "gameplay"
        self.game.hands = {
            "P1": ["A_hearts", "K_spades"],
            "P2": ["Q_hearts", "J_spades"],
            "P3": ["10_hearts", "9_spades"],
            "P4": ["8_hearts", "7_spades"]
        }
    
    def test_to_redis_dict_serialization(self):
        """Test converting game state to Redis-compatible dictionary."""
        state_dict = self.game.to_redis_dict()
        
        # Check required fields are present
        assert "phase" in state_dict
        assert "players" in state_dict
        assert "teams" in state_dict
        assert "hakem" in state_dict
        assert "hokm" in state_dict
        
        # Check JSON serialization
        players = json.loads(state_dict["players"])
        assert players == self.players
        
        teams = json.loads(state_dict["teams"])
        assert teams == self.game.teams
        
        # Check hands are stored separately
        for player in self.players:
            hand_key = f"hand_{player}"
            assert hand_key in state_dict
            hand = json.loads(state_dict[hand_key])
            assert hand == self.game.hands[player]
    
    def test_from_redis_dict_deserialization(self):
        """Test recreating game state from Redis dictionary."""
        # Serialize current state
        state_dict = self.game.to_redis_dict()
        
        # Create new game from serialized state
        new_game = GameBoard.from_redis_dict(state_dict, self.players)
        
        # Check basic fields
        assert new_game.players == self.game.players
        assert new_game.teams == self.game.teams
        assert new_game.hakem == self.game.hakem
        assert new_game.hokm == self.game.hokm
        assert new_game.hands == self.game.hands
    
    def test_state_validation(self):
        """Test game state validation after deserialization."""
        assert self.game.validate_state() is True
        
        # Test with invalid state
        invalid_game = GameBoard(self.players)
        invalid_game.players = ["P1", "P2"]  # Wrong number of players
        assert invalid_game.validate_state() is False
        
        # Test with card conflict
        conflict_game = GameBoard(self.players)
        conflict_game.hands = {"P1": ["A_hearts"], "P2": [], "P3": [], "P4": []}
        conflict_game.played_cards = ["A_hearts"]  # Same card in hand and played
        assert conflict_game.validate_state() is False


class TestCardDealing:
    """Test card dealing mechanics."""
    
    def setup_method(self):
        """Set up game for dealing tests."""
        self.players = ["P1", "P2", "P3", "P4"]
        self.game = GameBoard(self.players)
        self.game.assign_teams_and_hakem()  # Sets phase to initial_deal
    
    def test_initial_deal(self):
        """Test initial 5-card deal."""
        hands = self.game.initial_deal()
        
        # Check each player gets 5 cards
        assert all(len(hand) == 5 for hand in hands.values())
        assert all(len(self.game.hands[p]) == 5 for p in self.players)
        
        # Check cards are removed from deck
        assert len(self.game.deck) == 52 - 20  # 52 - (4 players * 5 cards)
        
        # Check phase transition
        assert self.game.game_phase == "hokm_selection"
        
        # Check no duplicate cards
        all_dealt_cards = []
        for hand in hands.values():
            all_dealt_cards.extend(hand)
        assert len(all_dealt_cards) == len(set(all_dealt_cards))
    
    def test_final_deal(self):
        """Test final 8-card deal after hokm selection."""
        # Set up for final deal
        self.game.initial_deal()
        self.game.set_hokm("hearts")
        
        hands = self.game.final_deal()
        
        # Check each player gets 13 total cards (5 + 8)
        assert all(len(hand) == 13 for hand in hands.values())
        assert all(len(self.game.hands[p]) == 13 for p in self.players)
        
        # Check deck is empty
        assert len(self.game.deck) == 0
        
        # Check phase transition
        assert self.game.game_phase == "gameplay"
    
    def test_dealing_wrong_phase(self):
        """Test dealing fails in wrong phase."""
        # Try initial deal in wrong phase
        self.game.game_phase = "lobby"
        with pytest.raises(ValueError, match="Invalid game phase for initial deal"):
            self.game.initial_deal()
        
        # Try final deal in wrong phase
        self.game.game_phase = "lobby"
        with pytest.raises(ValueError, match="Invalid game phase for final deal"):
            self.game.final_deal()


class TestGameStateQueries:
    """Test game state query methods."""
    
    def setup_method(self):
        """Set up game for state query tests."""
        self.players = ["P1", "P2", "P3", "P4"]
        self.game = GameBoard(self.players)
        self.game.assign_teams_and_hakem()
        self.game.initial_deal()
        self.game.set_hokm("hearts")
        self.game.final_deal()
    
    def test_get_state_general(self):
        """Test getting general game state."""
        state = self.game.get_state()
        
        assert "phase" in state
        assert "teams" in state
        assert "hakem" in state
        assert "hokm" in state
        assert "current_turn" in state
        assert "tricks" in state
        assert "all_hands" in state
        
        # Check data integrity
        assert state["phase"] == self.game.game_phase
        assert state["teams"] == self.game.teams
        assert state["hakem"] == self.game.hakem
        assert state["hokm"] == self.game.hokm
    
    def test_get_state_player_specific(self):
        """Test getting player-specific game state."""
        player = "P1"
        state = self.game.get_state(player)
        
        assert "your_hand" in state
        assert "your_team" in state
        assert "all_hands" not in state
        
        # Check player-specific data
        assert state["your_hand"] == self.game.hands[player]
        assert state["your_team"] == self.game.teams[player]


if __name__ == "__main__":
    # Run specific test categories
    print("Running GameBoard unit tests...")
    pytest.main([__file__, "-v"])
