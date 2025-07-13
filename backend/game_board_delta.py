# game_board_delta.py
"""
Delta-optimized GameBoard that integrates with the incremental update system

This extends the existing GameBoard with:
1. Automatic delta generation for state changes
2. Optimized state tracking for minimal updates
3. Integration with DeltaNetworkManager
4. Efficient state serialization
"""

import json
import time
from typing import Dict, List, Optional, Any, Tuple
from copy import deepcopy

from game_board import GameBoard
from game_state_delta import UpdateType
from network_delta import DeltaNetworkManager


class DeltaGameBoard(GameBoard):
    """
    Enhanced GameBoard with delta update capabilities
    """
    
    def __init__(self, players: List[str], room_code: Optional[str] = None, network_manager: Optional[DeltaNetworkManager] = None):
        super().__init__(players, room_code)
        
        # Delta-specific properties
        self.network_manager = network_manager
        self.last_broadcasted_state = {}
        self.state_change_buffer = {}  # Buffer changes before broadcasting
        self.auto_broadcast = True     # Automatically broadcast changes
        
        # Track what has changed since last broadcast
        self.dirty_fields = set()
        
        # Performance tracking
        self.update_stats = {
            'total_updates': 0,
            'delta_updates': 0,
            'full_syncs': 0,
            'bytes_saved': 0
        }
    
    def _mark_dirty(self, field: str):
        """Mark a field as changed"""
        self.dirty_fields.add(field)
        if field not in self.state_change_buffer:
            self.state_change_buffer[field] = getattr(self, field, None)
    
    def _get_current_state_snapshot(self) -> Dict[str, Any]:
        """Get current complete state snapshot"""
        return self.to_redis_dict()
    
    async def _broadcast_changes(self, 
                               update_type: UpdateType = None,
                               affected_players: List[str] = None,
                               force_full_sync: bool = False,
                               redis_manager = None):
        """Broadcast state changes using delta updates"""
        if not self.network_manager or not self.room_code:
            return
        
        try:
            current_state = self._get_current_state_snapshot()
            
            # Broadcast using delta network manager
            stats = await self.network_manager.broadcast_game_state_delta(
                room_code=self.room_code,
                new_state=current_state,
                redis_manager=redis_manager,
                update_type=update_type,
                affected_players=affected_players,
                force_full_sync=force_full_sync
            )
            
            # Update our tracking
            self.last_broadcasted_state = current_state.copy()
            self.dirty_fields.clear()
            self.state_change_buffer.clear()
            
            # Update stats
            self.update_stats['total_updates'] += 1
            if stats.get('delta_updates', 0) > 0:
                self.update_stats['delta_updates'] += 1
            if stats.get('full_syncs', 0) > 0:
                self.update_stats['full_syncs'] += 1
            
            return stats
            
        except Exception as e:
            print(f"[ERROR] Failed to broadcast changes: {e}")
            return {'error': str(e)}
    
    # Override key methods to add delta broadcasting
    
    async def assign_teams_and_hakem_delta(self, redis_manager=None) -> Dict[str, Any]:
        """Team assignment with delta broadcasting"""
        result = self.assign_teams_and_hakem(redis_manager)
        
        if 'error' not in result and self.auto_broadcast:
            await self._broadcast_changes(
                update_type=UpdateType.GAME_SETUP,
                affected_players=self.players,
                redis_manager=redis_manager
            )
        
        return result
    
    async def initial_deal_delta(self, redis_manager=None) -> Dict[str, List[str]]:
        """Initial deal with optimized hand broadcasting"""
        hands = self.initial_deal()
        
        if self.auto_broadcast and self.network_manager:
            # Use optimized hand update broadcast
            await self.network_manager.broadcast_hand_update(
                room_code=self.room_code,
                player_hands=hands,
                redis_manager=redis_manager
            )
        
        return hands
    
    async def set_hokm_delta(self, suit: str, redis_manager=None, room_code=None) -> bool:
        """Hokm selection with delta broadcasting"""
        success = self.set_hokm(suit, redis_manager, room_code)
        
        if success and self.auto_broadcast:
            await self._broadcast_changes(
                update_type=UpdateType.PLAYER_ACTION,
                affected_players=self.players,
                redis_manager=redis_manager
            )
        
        return success
    
    async def final_deal_delta(self, redis_manager=None) -> Dict[str, List[str]]:
        """Final deal with optimized broadcasting"""
        hands = self.final_deal(redis_manager)
        
        if self.auto_broadcast and self.network_manager:
            # Use optimized hand update broadcast
            await self.network_manager.broadcast_hand_update(
                room_code=self.room_code,
                player_hands=hands,
                redis_manager=redis_manager
            )
        
        return hands
    
    async def play_card_delta(self, player: str, card: str, redis_manager=None) -> Dict[str, Any]:
        """Card play with optimized delta broadcasting"""
        # Store state before play
        old_current_turn = self.current_turn
        old_trick = self.current_trick.copy()
        
        # Execute the play
        result = self.play_card(player, card, redis_manager)
        
        if not result.get('valid'):
            return result
        
        # Determine what type of update to broadcast
        if self.auto_broadcast and self.network_manager:
            if result.get('trick_complete'):
                # Trick completed - broadcast trick result
                await self.network_manager.broadcast_trick_result(
                    room_code=self.room_code,
                    trick_data=result,
                    redis_manager=redis_manager
                )
                
                # If hand is complete, also broadcast score change
                if result.get('hand_complete'):
                    await self.network_manager.broadcast_score_change(
                        room_code=self.room_code,
                        score_data={
                            'round_scores': self.round_scores,
                            'tricks': self.tricks,
                            'completed_tricks': self.completed_tricks
                        },
                        redis_manager=redis_manager
                    )
            else:
                # Regular card play - broadcast turn transition and hand update
                
                # Update hand (card removed)
                await self.network_manager.broadcast_hand_update(
                    room_code=self.room_code,
                    player_hands={player: self.hands[player]},
                    redis_manager=redis_manager
                )
                
                # Update turn
                current_player = self.players[self.current_turn]
                await self.network_manager.broadcast_turn_transition(
                    room_code=self.room_code,
                    current_turn=self.current_turn,
                    current_player=current_player,
                    redis_manager=redis_manager
                )
                
                # Broadcast current trick update
                trick_changes = {
                    'current_trick': self.current_trick,
                    'led_suit': self.led_suit,
                    'played_card': {'player': player, 'card': card}
                }
                
                await self.network_manager.broadcast_specific_update(
                    room_code=self.room_code,
                    update_type=UpdateType.PLAYER_ACTION,
                    changes=trick_changes,
                    affected_players=self.players,
                    redis_manager=redis_manager
                )
        
        return result
    
    async def start_new_round_delta(self, redis_manager=None) -> Dict[str, Any]:
        """New round start with delta broadcasting"""
        result = self.start_new_round(redis_manager)
        
        if 'error' not in result and self.auto_broadcast:
            # New round is a major state change - use full sync
            await self._broadcast_changes(
                update_type=UpdateType.PHASE_CHANGE,
                affected_players=self.players,
                force_full_sync=True,
                redis_manager=redis_manager
            )
        
        return result
    
    # Optimized state querying methods
    
    def get_player_optimized_state(self, player: str) -> Dict[str, Any]:
        """Get optimized state for a specific player (minimal data)"""
        try:
            player_team = self.teams.get(player, -1)
            
            state = {
                # Essential player info
                'hand': self.hands.get(player, []),
                'your_team': player_team,
                'your_turn': self.players[self.current_turn] == player if self.game_phase == "gameplay" else False,
                
                # Current game status
                'phase': self.game_phase,
                'current_player': self.players[self.current_turn] if self.game_phase == "gameplay" else None,
                'hokm': self.hokm,
                'led_suit': self.led_suit,
                
                # Scores (compact format)
                'tricks': self.tricks,
                'round_scores': self.round_scores,
                
                # Current trick (if any)
                'current_trick': self.current_trick,
                'trick_count': self.completed_tricks
            }
            
            # Add hakem info only if relevant
            if self.hakem:
                state['hakem'] = self.hakem
                state['you_are_hakem'] = (player == self.hakem)
            
            return state
            
        except Exception as e:
            print(f"[ERROR] Failed to get optimized state for player {player}: {e}")
            return self.get_state(player)  # Fallback to full state
    
    def get_minimal_turn_state(self) -> Dict[str, Any]:
        """Get minimal state for turn transitions"""
        if self.game_phase != "gameplay":
            return {}
        
        return {
            'current_turn': self.current_turn,
            'current_player': self.players[self.current_turn],
            'led_suit': self.led_suit,
            'current_trick': self.current_trick,
            'timestamp': time.time()
        }
    
    def get_minimal_score_state(self) -> Dict[str, Any]:
        """Get minimal state for score updates"""
        return {
            'tricks': self.tricks,
            'round_scores': self.round_scores,
            'completed_tricks': self.completed_tricks,
            'timestamp': time.time()
        }
    
    # Batch update methods for efficiency
    
    async def batch_hand_updates(self, 
                                hand_changes: Dict[str, List[str]], 
                                redis_manager=None):
        """Efficiently update multiple player hands"""
        if not hand_changes:
            return
        
        # Update internal state
        for player, new_hand in hand_changes.items():
            if player in self.hands:
                self.hands[player] = new_hand.copy()
        
        # Broadcast optimized hand updates
        if self.auto_broadcast and self.network_manager:
            await self.network_manager.broadcast_hand_update(
                room_code=self.room_code,
                player_hands=hand_changes,
                redis_manager=redis_manager
            )
    
    def set_auto_broadcast(self, enabled: bool):
        """Enable or disable automatic broadcasting"""
        self.auto_broadcast = enabled
    
    def get_update_statistics(self) -> Dict[str, Any]:
        """Get statistics about delta updates"""
        total = self.update_stats['total_updates']
        
        return {
            **self.update_stats,
            'delta_ratio': (self.update_stats['delta_updates'] / total) if total > 0 else 0,
            'dirty_fields': list(self.dirty_fields),
            'network_stats': self.network_manager.get_bandwidth_statistics() if self.network_manager else {}
        }
    
    # State comparison and optimization
    
    def compare_states(self, other_state: Dict[str, Any]) -> Dict[str, Any]:
        """Compare current state with another state and return differences"""
        current = self._get_current_state_snapshot()
        differences = {}
        
        all_keys = set(current.keys()) | set(other_state.keys())
        
        for key in all_keys:
            current_val = current.get(key)
            other_val = other_state.get(key)
            
            if current_val != other_val:
                differences[key] = {
                    'old': other_val,
                    'new': current_val
                }
        
        return differences
    
    def estimate_state_size(self) -> Dict[str, int]:
        """Estimate size of different state components"""
        state = self._get_current_state_snapshot()
        sizes = {}
        
        for key, value in state.items():
            try:
                serialized = json.dumps(value)
                sizes[key] = len(serialized.encode())
            except Exception:
                sizes[key] = 0
        
        return sizes
    
    # Context managers for batch operations
    
    class BatchUpdateContext:
        """Context manager for batching multiple updates"""
        
        def __init__(self, game_board: 'DeltaGameBoard'):
            self.game_board = game_board
            self.original_auto_broadcast = None
        
        def __enter__(self):
            self.original_auto_broadcast = self.game_board.auto_broadcast
            self.game_board.set_auto_broadcast(False)
            return self
        
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            # Re-enable broadcasting
            self.game_board.set_auto_broadcast(self.original_auto_broadcast)
            
            # Send accumulated changes
            if self.original_auto_broadcast and self.game_board.dirty_fields:
                await self.game_board._broadcast_changes()
    
    def batch_updates(self):
        """Get context manager for batching updates"""
        return self.BatchUpdateContext(self)
    
    # Advanced delta features
    
    async def send_targeted_update(self, 
                                 target_players: List[str],
                                 update_type: UpdateType,
                                 changes: Dict[str, Any],
                                 redis_manager=None):
        """Send an update only to specific players"""
        if not self.network_manager:
            return
        
        return await self.network_manager.broadcast_specific_update(
            room_code=self.room_code,
            update_type=update_type,
            changes=changes,
            affected_players=target_players,
            redis_manager=redis_manager
        )
    
    async def force_full_resync(self, redis_manager=None):
        """Force a full state resync for all players"""
        if not self.network_manager:
            return
        
        return await self._broadcast_changes(
            update_type=UpdateType.FULL_SYNC,
            affected_players=self.players,
            force_full_sync=True,
            redis_manager=redis_manager
        )
    
    def cleanup_delta_data(self):
        """Clean up delta-related data when game ends"""
        if self.network_manager and self.room_code:
            self.network_manager.cleanup_room_data(self.room_code)
        
        self.last_broadcasted_state.clear()
        self.state_change_buffer.clear()
        self.dirty_fields.clear()
