#!/usr/bin/env python3
"""
Test the phase change fix for new round start
"""

import sys
import os
import json
import asyncio
from unittest.mock import Mock, patch, MagicMock

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.game_board import GameBoard
from backend.server import GameServer
from backend.game_states import GameState

class AsyncMock(MagicMock):
    async def __call__(self, *args, **kwargs):
        return super(AsyncMock, self).__call__(*args, **kwargs)

async def test_phase_change_fix():
    """Test that the phase change is properly broadcasted during new round start"""
    
    print("=" * 70)
    print("TESTING PHASE CHANGE FIX FOR NEW ROUND START")
    print("=" * 70)
    
    # Create server and game
    server = GameServer()
    server.redis_manager = Mock()
    server.network_manager = Mock()
    
    players = ["Player 0", "Player 1", "Player 2", "Player 3"]
    game = GameBoard(players, "test_room")
    
    # Set up teams and game state
    game.teams = {
        "Player 0": 0,
        "Player 2": 0,
        "Player 1": 1,
        "Player 3": 1
    }
    game.hakem = "Player 0"
    game.hokm = "spades"
    game.game_phase = "initial_deal"  # After round completion
    game.round_scores = {0: 1, 1: 0}  # Team 0 won first round
    
    # Mock server components
    server.active_games["test_room"] = game
    server.redis_manager.get_room_players.return_value = [
        {'username': 'Player 0', 'player_id': 'id0'},
        {'username': 'Player 1', 'player_id': 'id1'},
        {'username': 'Player 2', 'player_id': 'id2'},
        {'username': 'Player 3', 'player_id': 'id3'}
    ]
    
    # Track broadcast calls
    broadcast_calls = []
    
    async def mock_broadcast(room_code, msg_type, data, redis_manager):
        print(f"[BROADCAST] {msg_type}: {data}")
        broadcast_calls.append((msg_type, data))
    
    server.network_manager.broadcast_to_room = mock_broadcast
    server.network_manager.get_live_connection = Mock(return_value=Mock())
    server.network_manager.send_message = AsyncMock()
    
    print("Starting next round test...")
    
    try:
        await server.start_next_round("test_room")
        
        print(f"\nBroadcast calls made: {len(broadcast_calls)}")
        
        # Check for phase_change broadcast
        phase_change_calls = [call for call in broadcast_calls if call[0] == 'phase_change']
        new_round_calls = [call for call in broadcast_calls if call[0] == 'new_round_start']
        
        print(f"Phase change calls: {len(phase_change_calls)}")
        print(f"New round start calls: {len(new_round_calls)}")
        
        if phase_change_calls:
            phase_data = phase_change_calls[0][1]
            print(f"Phase change data: {phase_data}")
            assert phase_data['new_phase'] == GameState.WAITING_FOR_HOKM.value, "Should change to WAITING_FOR_HOKM"
            print("✓ Phase change broadcast is correct")
        else:
            print("❌ No phase change broadcast found")
            
        if new_round_calls:
            round_data = new_round_calls[0][1]
            print(f"New round data: {round_data}")
            print("✓ New round start broadcast found")
        else:
            print("❌ No new round start broadcast found")
            
        # Verify the order - phase_change should come before new_round_start
        if len(broadcast_calls) >= 2:
            if broadcast_calls[0][0] == 'phase_change' and broadcast_calls[1][0] == 'new_round_start':
                print("✓ Broadcasts are in correct order: phase_change then new_round_start")
            else:
                print(f"❌ Incorrect order: {[call[0] for call in broadcast_calls]}")
        
        print(f"\n🎉 TEST COMPLETED!")
        print("The phase change should now be properly broadcasted during new round start.")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

if __name__ == "__main__":
    success = asyncio.run(test_phase_change_fix())
    if success:
        print("\n✅ Phase change fix test passed!")
    else:
        print("\n❌ Phase change fix test failed!")
