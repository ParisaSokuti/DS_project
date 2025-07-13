"""
Optimized Game States for Hokm Card Game
Efficient enumeration of game phases with type safety
"""

from enum import Enum, auto


class GameState(Enum):
    """Game state enumeration with optimized phase management"""
    
    # Authentication and setup phases
    AUTHENTICATION = "authentication"
    WAITING_FOR_PLAYERS = "waiting_for_players"
    TEAM_ASSIGNMENT = "team_assignment"
    
    # Game phases
    WAITING_FOR_HOKM = "hokm_selection"
    FINAL_DEAL = "final_deal"
    GAMEPLAY = "gameplay"
    
    # End game phases
    HAND_COMPLETE = "hand_complete"
    GAME_OVER = "game_over"
    
    @classmethod
    def is_valid_state(cls, state: str) -> bool:
        """Check if a state string is valid"""
        return state in cls._value2member_map_
    
    @classmethod
    def get_next_state(cls, current_state: str) -> str:
        """Get the next logical state in the game flow"""
        state_flow = {
            cls.AUTHENTICATION.value: cls.WAITING_FOR_PLAYERS.value,
            cls.WAITING_FOR_PLAYERS.value: cls.TEAM_ASSIGNMENT.value,
            cls.TEAM_ASSIGNMENT.value: cls.WAITING_FOR_HOKM.value,
            cls.WAITING_FOR_HOKM.value: cls.FINAL_DEAL.value,
            cls.FINAL_DEAL.value: cls.GAMEPLAY.value,
            cls.GAMEPLAY.value: cls.HAND_COMPLETE.value,
            cls.HAND_COMPLETE.value: cls.GAME_OVER.value,
            cls.GAME_OVER.value: cls.WAITING_FOR_PLAYERS.value,
        }
        return state_flow.get(current_state, current_state)
