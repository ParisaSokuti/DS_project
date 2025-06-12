from enum import Enum

class GameState(Enum):
    WAITING_FOR_PLAYERS = "waiting_for_players"
    TEAM_ASSIGNMENT = "team_assignment"  # Keep this state
    WAITING_FOR_HOKM = "hokm_selection"  # Changed to match server expectation
    FINAL_DEAL = "final_deal"
    GAMEPLAY = "gameplay"
    HAND_COMPLETE = "hand_complete"
    GAME_OVER = "game_over"
