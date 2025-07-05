# New Round Implementation

## Overview
This implementation adds support for starting subsequent rounds after the first round completes. In these new rounds:

1. The player from the winning team with the most tricks becomes the new hakem
2. First 5 cards are dealt to all players
3. The new hakem chooses the hokm (trump suit)
4. The remaining 8 cards are dealt
5. Game continues with the new hakem leading the first trick

## Key Components

### 1. Player Trick Tracking
- Added individual player trick counting to track who won how many tricks
- This allows selecting the player with most tricks as the next hakem

### 2. Hakem Selection Logic
- After a hand completes, the player from the winning team with the most tricks becomes the new hakem
- In case of a tie, the first player found with the maximum tricks is selected

### 3. Round Transition
- After hand_complete is broadcast, a delay occurs before starting the next round
- The server sends a new_round_start message to all clients
- The new hakem is announced and round scores are updated

### 4. Card Dealing Flow
- First 5 cards are dealt for hokm selection (initial_deal)
- Hakem selects hokm
- Remaining 8 cards are dealt (final_deal)

## Server Changes
1. Updated `_prepare_new_hand()` to select new hakem based on trick counts
2. Added `_select_new_hakem()` method to find player with most tricks
3. Added `start_next_round()` method to handle the new round flow
4. Updated trick resolution to track individual player tricks
5. Added delay mechanism for smoother game flow between rounds

## Client Changes
1. Added handler for the new_round_start message to show:
   - Round number
   - New hakem
   - Current game score
   - Instructions for hokm selection if player is hakem

## Testing
- A comprehensive test file tests the hakem selection logic
- Verifies that the player with most tricks from the winning team becomes hakem
- Tests multiple rounds of play to ensure continuity

## Flow Diagram
```
Round ends (Team X wins)
  │
  ▼
Select player with most tricks from winning team as new hakem
  │
  ▼
Send new_round_start message
  │
  ▼
Deal 5 cards (initial_deal)
  │
  ▼
Hakem selects hokm
  │
  ▼
Deal remaining 8 cards (final_deal)
  │
  ▼
New round starts with new hakem
```
