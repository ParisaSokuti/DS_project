# game_state_delta.py
"""
Delta/Incremental Game State Update System

This module provides:
1. State diffing to identify changes between game states
2. Delta compression and patch generation
3. State reconciliation for missed updates
4. Optimized bandwidth usage for real-time card games
"""

import json
import zlib
import base64
import time
import hashlib
from typing import Dict, List, Optional, Any, Tuple, Set
from enum import Enum
from dataclasses import dataclass, asdict
from copy import deepcopy


class UpdateType(Enum):
    """Types of game state updates for efficient categorization"""
    HAND_UPDATE = "hand_update"           # Cards added/removed from player hands
    TRICK_RESULT = "trick_result"         # Trick completion and winner
    TURN_TRANSITION = "turn_transition"   # Current player changes
    SCORE_CHANGE = "score_change"         # Team scores, trick counts
    PHASE_CHANGE = "phase_change"         # Game phase transitions
    PLAYER_ACTION = "player_action"       # Card plays, hokm selection
    GAME_SETUP = "game_setup"            # Teams, hakem assignment
    FULL_SYNC = "full_sync"              # Complete state (fallback)


@dataclass
class StateDelta:
    """Represents a change in game state"""
    update_type: UpdateType
    timestamp: float
    sequence_id: int
    changes: Dict[str, Any]
    affected_players: List[str]
    checksum: str
    compressed_size: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            'update_type': self.update_type.value,
            'timestamp': self.timestamp,
            'sequence_id': self.sequence_id,
            'changes': self.changes,
            'affected_players': self.affected_players,
            'checksum': self.checksum,
            'compressed_size': self.compressed_size
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'StateDelta':
        """Create from dictionary"""
        return cls(
            update_type=UpdateType(data['update_type']),
            timestamp=data['timestamp'],
            sequence_id=data['sequence_id'],
            changes=data['changes'],
            affected_players=data['affected_players'],
            checksum=data['checksum'],
            compressed_size=data.get('compressed_size', 0)
        )


class GameStateDeltaManager:
    """
    Manages delta generation, compression, and state reconciliation for game updates
    """
    
    def __init__(self, compression_threshold: int = 500):
        self.compression_threshold = compression_threshold  # Compress if delta > 500 bytes
        self.sequence_counter = 0
        self.state_history: List[Dict[str, Any]] = []  # Keep last N states for diffing
        self.delta_history: List[StateDelta] = []      # Keep delta history for reconciliation
        self.max_history = 50                          # Maximum states/deltas to keep
        
        # Player-specific state tracking
        self.player_states: Dict[str, Dict[str, Any]] = {}
        self.player_sequence_ids: Dict[str, int] = {}
        
        # Pre-defined static fields (don't delta these unless they actually change)
        self.static_fields = {
            'created_at', 'room_code', 'teams', 'players', 'hakem'
        }
        
        # High-frequency update fields
        self.volatile_fields = {
            'current_turn', 'current_trick', 'led_suit', 'last_activity'
        }
    
    def compute_state_checksum(self, state: Dict[str, Any]) -> str:
        """Compute MD5 checksum of state for validation"""
        # Sort keys for consistent hashing
        state_str = json.dumps(state, sort_keys=True, default=str)
        return hashlib.md5(state_str.encode()).hexdigest()[:8]
    
    def generate_delta(self, 
                      old_state: Dict[str, Any], 
                      new_state: Dict[str, Any],
                      affected_players: Optional[List[str]] = None) -> StateDelta:
        """
        Generate a delta between two game states
        
        Args:
            old_state: Previous game state
            new_state: Current game state
            affected_players: Players affected by this update (optional)
            
        Returns:
            StateDelta object containing only the changes
        """
        changes = {}
        update_types = set()
        
        # Compare all fields and identify changes
        all_keys = set(old_state.keys()) | set(new_state.keys())
        
        for key in all_keys:
            old_value = old_state.get(key)
            new_value = new_state.get(key)
            
            if old_value != new_value:
                changes[key] = new_value
                
                # Categorize the change
                if key.startswith('hand_'):
                    update_types.add(UpdateType.HAND_UPDATE)
                elif key in ['current_turn']:
                    update_types.add(UpdateType.TURN_TRANSITION)
                elif key in ['tricks', 'round_scores', 'completed_tricks']:
                    update_types.add(UpdateType.SCORE_CHANGE)
                elif key in ['phase', 'game_phase']:
                    update_types.add(UpdateType.PHASE_CHANGE)
                elif key in ['hokm', 'current_trick', 'led_suit']:
                    update_types.add(UpdateType.PLAYER_ACTION)
                elif key in ['teams', 'hakem']:
                    update_types.add(UpdateType.GAME_SETUP)
        
        # Determine primary update type
        if UpdateType.TRICK_RESULT in update_types or (
            UpdateType.SCORE_CHANGE in update_types and 
            'current_trick' in changes and not changes['current_trick']
        ):
            primary_type = UpdateType.TRICK_RESULT
        elif update_types:
            primary_type = list(update_types)[0]
        else:
            primary_type = UpdateType.FULL_SYNC
        
        # Auto-detect affected players if not specified
        if affected_players is None:
            affected_players = self._detect_affected_players(changes, old_state, new_state)
        
        # Create delta
        self.sequence_counter += 1
        delta = StateDelta(
            update_type=primary_type,
            timestamp=time.time(),
            sequence_id=self.sequence_counter,
            changes=changes,
            affected_players=affected_players,
            checksum=self.compute_state_checksum(new_state)
        )
        
        # Store in history
        self.delta_history.append(delta)
        if len(self.delta_history) > self.max_history:
            self.delta_history.pop(0)
        
        return delta
    
    def _detect_affected_players(self, 
                                changes: Dict[str, Any], 
                                old_state: Dict[str, Any], 
                                new_state: Dict[str, Any]) -> List[str]:
        """Automatically detect which players are affected by changes"""
        affected = set()
        
        # Hand changes affect specific players
        for key in changes:
            if key.startswith('hand_'):
                player = key.replace('hand_', '')
                affected.add(player)
        
        # Turn changes affect current and next players
        if 'current_turn' in changes:
            try:
                players = new_state.get('players', [])
                if isinstance(players, str):
                    players = json.loads(players)
                
                current_turn = changes['current_turn']
                if isinstance(current_turn, int) and 0 <= current_turn < len(players):
                    affected.add(players[current_turn])
                
                # Also affect previous player
                old_turn = old_state.get('current_turn', 0)
                if isinstance(old_turn, int) and 0 <= old_turn < len(players):
                    affected.add(players[old_turn])
            except (json.JSONDecodeError, IndexError, TypeError):
                pass
        
        # Trick results affect all players
        if any(key in changes for key in ['tricks', 'current_trick', 'round_scores']):
            try:
                players = new_state.get('players', [])
                if isinstance(players, str):
                    players = json.loads(players)
                affected.update(players)
            except (json.JSONDecodeError, TypeError):
                pass
        
        # Default to all players if we can't determine
        if not affected:
            try:
                players = new_state.get('players', [])
                if isinstance(players, str):
                    players = json.loads(players)
                affected.update(players)
            except (json.JSONDecodeError, TypeError):
                affected = ['all']
        
        return list(affected)
    
    def compress_delta(self, delta: StateDelta) -> Tuple[str, bool]:
        """
        Compress delta if it's larger than threshold
        
        Returns:
            (compressed_data, was_compressed)
        """
        delta_json = json.dumps(delta.to_dict())
        original_size = len(delta_json.encode())
        
        if original_size > self.compression_threshold:
            # Compress using zlib and encode as base64
            compressed = zlib.compress(delta_json.encode(), level=6)
            compressed_b64 = base64.b64encode(compressed).decode()
            
            delta.compressed_size = len(compressed_b64)
            
            return compressed_b64, True
        
        return delta_json, False
    
    def decompress_delta(self, compressed_data: str, is_compressed: bool) -> StateDelta:
        """Decompress and parse delta"""
        if is_compressed:
            try:
                compressed_bytes = base64.b64decode(compressed_data.encode())
                decompressed = zlib.decompress(compressed_bytes)
                delta_json = decompressed.decode()
            except Exception as e:
                raise ValueError(f"Failed to decompress delta: {e}")
        else:
            delta_json = compressed_data
        
        try:
            delta_dict = json.loads(delta_json)
            return StateDelta.from_dict(delta_dict)
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse delta JSON: {e}")
    
    def create_optimized_update(self, 
                              old_state: Dict[str, Any], 
                              new_state: Dict[str, Any],
                              target_player: str,
                              affected_players: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Create an optimized update for a specific player
        
        This method creates player-specific deltas that only include
        information relevant to that player.
        """
        # Generate base delta
        delta = self.generate_delta(old_state, new_state, affected_players)
        
        # Filter changes for target player
        player_changes = {}
        
        for key, value in delta.changes.items():
            # Include player's own hand
            if key == f'hand_{target_player}':
                player_changes[key] = value
            
            # Include global game state (but not other players' hands)
            elif not key.startswith('hand_') or key == f'hand_{target_player}':
                player_changes[key] = value
            
            # Include turn information if it affects this player
            elif key == 'current_turn':
                try:
                    players = new_state.get('players', [])
                    if isinstance(players, str):
                        players = json.loads(players)
                    
                    current_player = players[value] if 0 <= value < len(players) else None
                    if current_player == target_player or target_player in affected_players:
                        player_changes[key] = value
                        player_changes['your_turn'] = (current_player == target_player)
                except (json.JSONDecodeError, IndexError, TypeError):
                    player_changes[key] = value
        
        # Create optimized delta
        optimized_delta = StateDelta(
            update_type=delta.update_type,
            timestamp=delta.timestamp,
            sequence_id=delta.sequence_id,
            changes=player_changes,
            affected_players=[target_player],
            checksum=delta.checksum
        )
        
        # Compress if needed
        compressed_data, is_compressed = self.compress_delta(optimized_delta)
        
        return {
            'type': 'delta_update',
            'delta': optimized_delta.to_dict(),
            'compressed': is_compressed,
            'data': compressed_data,
            'target_player': target_player
        }
    
    def create_full_sync(self, 
                        state: Dict[str, Any], 
                        target_player: str) -> Dict[str, Any]:
        """Create a full state synchronization for a player"""
        # Filter state for player
        player_state = {}
        
        for key, value in state.items():
            # Include player's own hand
            if key == f'hand_{target_player}':
                player_state['hand'] = value if isinstance(value, list) else json.loads(value or '[]')
            
            # Include global state (excluding other players' hands)
            elif not key.startswith('hand_'):
                if key == 'teams' and isinstance(value, str):
                    player_state[key] = json.loads(value)
                elif key == 'players' and isinstance(value, str):
                    player_state[key] = json.loads(value)
                elif key in ['tricks', 'round_scores'] and isinstance(value, str):
                    player_state[key] = json.loads(value)
                else:
                    player_state[key] = value
        
        # Add player-specific metadata
        player_state['target_player'] = target_player
        player_state['sync_timestamp'] = time.time()
        
        self.sequence_counter += 1
        
        return {
            'type': 'full_sync',
            'sequence_id': self.sequence_counter,
            'state': player_state,
            'checksum': self.compute_state_checksum(state),
            'target_player': target_player
        }
    
    def generate_reconciliation_patch(self, 
                                    player_id: str,
                                    last_known_sequence: int,
                                    current_state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate a reconciliation patch for a player who missed updates
        
        Args:
            player_id: Player who needs reconciliation
            last_known_sequence: Last sequence ID the player received
            current_state: Current game state
            
        Returns:
            Reconciliation patch or full sync if too many missed updates
        """
        # Find deltas since last known sequence
        missed_deltas = [
            delta for delta in self.delta_history 
            if delta.sequence_id > last_known_sequence
        ]
        
        # If too many missed updates, send full sync
        if len(missed_deltas) > 10:
            return self.create_full_sync(current_state, player_id)
        
        # Aggregate missed changes
        aggregated_changes = {}
        update_types = set()
        
        for delta in missed_deltas:
            # Only include changes relevant to this player
            for key, value in delta.changes.items():
                if (key == f'hand_{player_id}' or 
                    not key.startswith('hand_') or
                    player_id in delta.affected_players):
                    aggregated_changes[key] = value
            
            update_types.add(delta.update_type)
        
        # Create reconciliation delta
        self.sequence_counter += 1
        reconciliation_delta = StateDelta(
            update_type=UpdateType.FULL_SYNC if len(update_types) > 3 else UpdateType.PLAYER_ACTION,
            timestamp=time.time(),
            sequence_id=self.sequence_counter,
            changes=aggregated_changes,
            affected_players=[player_id],
            checksum=self.compute_state_checksum(current_state)
        )
        
        # Compress if needed
        compressed_data, is_compressed = self.compress_delta(reconciliation_delta)
        
        return {
            'type': 'reconciliation_patch',
            'delta': reconciliation_delta.to_dict(),
            'compressed': is_compressed,
            'data': compressed_data,
            'missed_sequences': [d.sequence_id for d in missed_deltas],
            'target_player': player_id
        }
    
    def update_player_state(self, player_id: str, sequence_id: int, state_changes: Dict[str, Any]):
        """Update tracking for a player's last known state"""
        self.player_sequence_ids[player_id] = sequence_id
        
        if player_id not in self.player_states:
            self.player_states[player_id] = {}
        
        self.player_states[player_id].update(state_changes)
    
    def get_player_last_sequence(self, player_id: str) -> int:
        """Get the last sequence ID a player received"""
        return self.player_sequence_ids.get(player_id, 0)
    
    def cleanup_old_history(self):
        """Remove old history to prevent memory growth"""
        current_time = time.time()
        
        # Remove deltas older than 5 minutes
        self.delta_history = [
            delta for delta in self.delta_history
            if current_time - delta.timestamp < 300
        ]
        
        # Keep only max_history items
        if len(self.delta_history) > self.max_history:
            self.delta_history = self.delta_history[-self.max_history:]
        
        if len(self.state_history) > self.max_history:
            self.state_history = self.state_history[-self.max_history:]
    
    def get_compression_stats(self) -> Dict[str, Any]:
        """Get compression and efficiency statistics"""
        if not self.delta_history:
            return {'total_deltas': 0}
        
        total_deltas = len(self.delta_history)
        compressed_deltas = sum(1 for d in self.delta_history if d.compressed_size > 0)
        
        # Calculate average sizes
        avg_delta_size = sum(len(json.dumps(d.changes)) for d in self.delta_history) / total_deltas
        
        return {
            'total_deltas': total_deltas,
            'compressed_deltas': compressed_deltas,
            'compression_ratio': compressed_deltas / total_deltas if total_deltas > 0 else 0,
            'avg_delta_size': avg_delta_size,
            'update_types': {
                update_type.value: sum(1 for d in self.delta_history if d.update_type == update_type)
                for update_type in UpdateType
            }
        }
