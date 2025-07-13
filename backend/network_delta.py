# network_delta.py
"""
Delta-enabled Network Manager for optimized game state updates

This module extends the existing network manager with:
1. Delta-based state broadcasting
2. Player-specific update optimization
3. State reconciliation for reconnecting players
4. Bandwidth usage monitoring
"""

import asyncio
import json
import time
import logging
from typing import Dict, List, Optional, Any, Set
from collections import defaultdict

from network import NetworkManager
from game_state_delta import GameStateDeltaManager, UpdateType, StateDelta


class DeltaNetworkManager(NetworkManager):
    """
    Enhanced NetworkManager with delta update capabilities
    """
    
    def __init__(self):
        super().__init__()
        
        # Delta management
        self.delta_manager = GameStateDeltaManager()
        
        # Per-room state tracking
        self.room_states: Dict[str, Dict[str, Any]] = {}  # room_code -> last_state
        self.room_delta_managers: Dict[str, GameStateDeltaManager] = {}
        
        # Player tracking for reconciliation
        self.player_last_updates: Dict[str, Dict[str, Any]] = {}  # player_id -> {sequence_id, timestamp}
        
        # Bandwidth monitoring
        self.bandwidth_stats = {
            'delta_updates_sent': 0,
            'full_syncs_sent': 0,
            'bytes_saved': 0,
            'total_bytes_sent': 0,
            'compression_saves': 0
        }
        
        # Update batching
        self.pending_updates: Dict[str, List[Dict[str, Any]]] = defaultdict(list)  # room_code -> updates
        self.batch_timers: Dict[str, Any] = {}  # room_code -> timer
        self.batch_delay = 0.1  # 100ms batching delay
        
        # Setup logging
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)
    
    def get_room_delta_manager(self, room_code: str) -> GameStateDeltaManager:
        """Get or create delta manager for a room"""
        if room_code not in self.room_delta_managers:
            self.room_delta_managers[room_code] = GameStateDeltaManager()
        return self.room_delta_managers[room_code]
    
    async def broadcast_game_state_delta(self, 
                                       room_code: str, 
                                       new_state: Dict[str, Any],
                                       redis_manager,
                                       update_type: Optional[UpdateType] = None,
                                       affected_players: Optional[List[str]] = None,
                                       force_full_sync: bool = False) -> Dict[str, Any]:
        """
        Broadcast game state using delta updates
        
        Args:
            room_code: Room to broadcast to
            new_state: New game state
            redis_manager: Redis manager for persistence
            update_type: Type of update (optional, will be auto-detected)
            affected_players: Players affected by update
            force_full_sync: Force full state sync instead of delta
            
        Returns:
            Statistics about the broadcast
        """
        try:
            # Get previous state
            old_state = self.room_states.get(room_code, {})
            delta_manager = self.get_room_delta_manager(room_code)
            
            # Save new state
            self.room_states[room_code] = new_state.copy()
            
            # Persist to Redis first
            redis_manager.save_game_state(room_code, new_state)
            
            # Get room players
            try:
                players = redis_manager.get_room_players(room_code)
            except Exception as e:
                self.logger.error(f"Failed to get room players: {e}")
                return {'error': 'Failed to get room players'}
            
            broadcast_stats = {
                'room_code': room_code,
                'total_players': len(players),
                'delta_updates': 0,
                'full_syncs': 0,
                'bytes_sent': 0,
                'compression_used': False,
                'update_type': update_type.value if update_type else 'auto'
            }
            
            # Determine if we should use delta or full sync
            use_delta = not force_full_sync and old_state and len(old_state) > 0
            
            if use_delta:
                # Generate delta
                delta = delta_manager.generate_delta(old_state, new_state, affected_players)
                
                # Only send delta if there are actual changes
                if not delta.changes:
                    self.logger.debug(f"No changes detected for room {room_code}, skipping broadcast")
                    return broadcast_stats
                
                self.logger.info(f"Broadcasting delta update to room {room_code}: {delta.update_type.value}")
                self.logger.debug(f"Delta changes: {list(delta.changes.keys())}")
                
                # Send optimized updates to each player
                for player in players:
                    player_id = player.get('player_id')
                    username = player.get('username')
                    
                    if not player_id or not username:
                        continue
                    
                    # Get live connection
                    ws = self.get_live_connection(player_id)
                    if not ws:
                        continue
                    
                    try:
                        # Create player-specific optimized update
                        update_data = delta_manager.create_optimized_update(
                            old_state, new_state, username, affected_players
                        )
                        
                        # Add player context
                        update_data.update({
                            'room_code': room_code,
                            'timestamp': time.time(),
                            'your_username': username
                        })
                        
                        # Send update
                        await self._send_delta_update(ws, update_data)
                        
                        # Update player tracking
                        self._update_player_tracking(player_id, delta.sequence_id, update_data)
                        
                        broadcast_stats['delta_updates'] += 1
                        broadcast_stats['bytes_sent'] += len(json.dumps(update_data))
                        
                    except Exception as e:
                        self.logger.error(f"Failed to send delta to player {username}: {e}")
                        # Fallback: remove failed connection
                        self.remove_connection(ws)
                
                self.bandwidth_stats['delta_updates_sent'] += broadcast_stats['delta_updates']
                
            else:
                # Send full sync to all players
                self.logger.info(f"Broadcasting full sync to room {room_code}")
                
                for player in players:
                    player_id = player.get('player_id')
                    username = player.get('username')
                    
                    if not player_id or not username:
                        continue
                    
                    ws = self.get_live_connection(player_id)
                    if not ws:
                        continue
                    
                    try:
                        # Create full sync for player
                        sync_data = delta_manager.create_full_sync(new_state, username)
                        sync_data.update({
                            'room_code': room_code,
                            'timestamp': time.time(),
                            'your_username': username
                        })
                        
                        # Send full sync
                        await self.send_message(ws, 'full_sync', sync_data)
                        
                        # Update player tracking
                        self._update_player_tracking(player_id, sync_data['sequence_id'], sync_data)
                        
                        broadcast_stats['full_syncs'] += 1
                        broadcast_stats['bytes_sent'] += len(json.dumps(sync_data))
                        
                    except Exception as e:
                        self.logger.error(f"Failed to send full sync to player {username}: {e}")
                        self.remove_connection(ws)
                
                self.bandwidth_stats['full_syncs_sent'] += broadcast_stats['full_syncs']
            
            # Update total bandwidth stats
            self.bandwidth_stats['total_bytes_sent'] += broadcast_stats['bytes_sent']
            
            # Clean up old history periodically
            if len(self.room_delta_managers) > 0:
                delta_manager.cleanup_old_history()
            
            return broadcast_stats
            
        except Exception as e:
            self.logger.error(f"Failed to broadcast game state delta: {e}")
            return {'error': str(e)}
    
    async def _send_delta_update(self, websocket, update_data: Dict[str, Any]) -> bool:
        """Send a delta update to a websocket"""
        try:
            # Check if data is compressed
            is_compressed = update_data.get('compressed', False)
            
            if is_compressed:
                # Send compressed data indicator first
                await websocket.send(json.dumps({
                    'type': 'compressed_delta',
                    'compressed': True,
                    'size': len(update_data['data'])
                }))
                
                # Send compressed data
                await websocket.send(update_data['data'])
                self.bandwidth_stats['compression_saves'] += 1
            else:
                # Send regular delta update
                await websocket.send(json.dumps(update_data))
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to send delta update: {e}")
            return False
    
    async def handle_player_reconnection_with_reconciliation(self, 
                                                           websocket, 
                                                           player_id: str, 
                                                           room_code: str,
                                                           redis_manager) -> bool:
        """
        Handle player reconnection with state reconciliation
        """
        try:
            # Get player's last known sequence
            last_sequence = self.delta_manager.get_player_last_sequence(player_id)
            
            # Get current game state
            current_state = redis_manager.get_game_state(room_code)
            if not current_state:
                await self.notify_error(websocket, "No active game found")
                return False
            
            # Get room delta manager
            delta_manager = self.get_room_delta_manager(room_code)
            
            # Generate reconciliation patch
            reconciliation = delta_manager.generate_reconciliation_patch(
                player_id, last_sequence, current_state
            )
            
            # Send reconciliation data
            await self.send_message(websocket, 'reconnection_reconciliation', reconciliation)
            
            # Update player tracking
            sequence_id = reconciliation.get('delta', {}).get('sequence_id', 0)
            self._update_player_tracking(player_id, sequence_id, reconciliation)
            
            self.logger.info(f"Sent reconciliation patch to player {player_id} "
                           f"(last sequence: {last_sequence}, current: {sequence_id})")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to handle reconnection reconciliation: {e}")
            await self.notify_error(websocket, "Failed to reconcile game state")
            return False
    
    def _update_player_tracking(self, player_id: str, sequence_id: int, data: Dict[str, Any]):
        """Update player's last known state for reconciliation"""
        self.player_last_updates[player_id] = {
            'sequence_id': sequence_id,
            'timestamp': time.time(),
            'data_size': len(json.dumps(data))
        }
        
        # Update delta manager tracking
        self.delta_manager.update_player_state(player_id, sequence_id, data)
    
    async def broadcast_specific_update(self, 
                                      room_code: str,
                                      update_type: UpdateType,
                                      changes: Dict[str, Any],
                                      affected_players: List[str],
                                      redis_manager) -> Dict[str, Any]:
        """
        Broadcast a specific type of update with minimal data
        
        This is optimized for high-frequency updates like turn transitions
        """
        try:
            delta_manager = self.get_room_delta_manager(room_code)
            
            # Create minimal delta
            delta_manager.sequence_counter += 1
            delta = StateDelta(
                update_type=update_type,
                timestamp=time.time(),
                sequence_id=delta_manager.sequence_counter,
                changes=changes,
                affected_players=affected_players,
                checksum=""  # Skip checksum for fast updates
            )
            
            # Get live connections for affected players
            live_players = []
            for player_name in affected_players:
                # Find player_id from connection metadata
                for ws, metadata in self.connection_metadata.items():
                    if metadata.get('username') == player_name:
                        live_players.append({
                            'websocket': ws,
                            'player_id': metadata.get('player_id'),
                            'username': player_name
                        })
                        break
            
            broadcast_stats = {
                'update_type': update_type.value,
                'affected_players': len(affected_players),
                'live_players': len(live_players),
                'bytes_sent': 0
            }
            
            # Send to live players
            for player_info in live_players:
                try:
                    update_data = {
                        'type': 'specific_update',
                        'update_type': update_type.value,
                        'sequence_id': delta.sequence_id,
                        'changes': changes,
                        'timestamp': delta.timestamp,
                        'room_code': room_code
                    }
                    
                    await self.send_message(player_info['websocket'], 'specific_update', update_data)
                    
                    # Update tracking
                    self._update_player_tracking(
                        player_info['player_id'], 
                        delta.sequence_id, 
                        update_data
                    )
                    
                    broadcast_stats['bytes_sent'] += len(json.dumps(update_data))
                    
                except Exception as e:
                    self.logger.error(f"Failed to send specific update to {player_info['username']}: {e}")
            
            return broadcast_stats
            
        except Exception as e:
            self.logger.error(f"Failed to broadcast specific update: {e}")
            return {'error': str(e)}
    
    async def batch_updates(self, room_code: str, update_data: Dict[str, Any]):
        """
        Batch multiple updates together to reduce message frequency
        """
        self.pending_updates[room_code].append(update_data)
        
        # Cancel existing timer if present
        if room_code in self.batch_timers:
            self.batch_timers[room_code].cancel()
        
        # Start new timer
        self.batch_timers[room_code] = asyncio.create_task(
            self._flush_batched_updates(room_code)
        )
    
    async def _flush_batched_updates(self, room_code: str):
        """Flush batched updates after delay"""
        try:
            await asyncio.sleep(self.batch_delay)
            
            updates = self.pending_updates[room_code]
            if not updates:
                return
            
            # Clear pending updates
            self.pending_updates[room_code] = []
            
            # Combine updates efficiently
            if len(updates) == 1:
                # Single update - send directly
                update = updates[0]
                # Send to affected players
                # Implementation depends on update structure
                
            else:
                # Multiple updates - merge changes
                merged_changes = {}
                affected_players = set()
                
                for update in updates:
                    if 'changes' in update:
                        merged_changes.update(update['changes'])
                    if 'affected_players' in update:
                        affected_players.update(update['affected_players'])
                
                # Create merged update
                # Implementation continues...
                
        except Exception as e:
            self.logger.error(f"Failed to flush batched updates: {e}")
        finally:
            # Clean up timer
            if room_code in self.batch_timers:
                del self.batch_timers[room_code]
    
    def get_bandwidth_statistics(self) -> Dict[str, Any]:
        """Get bandwidth usage and optimization statistics"""
        total_updates = self.bandwidth_stats['delta_updates_sent'] + self.bandwidth_stats['full_syncs_sent']
        
        stats = {
            **self.bandwidth_stats,
            'total_updates': total_updates,
            'delta_ratio': (self.bandwidth_stats['delta_updates_sent'] / total_updates 
                          if total_updates > 0 else 0),
            'avg_bytes_per_update': (self.bandwidth_stats['total_bytes_sent'] / total_updates 
                                   if total_updates > 0 else 0),
            'rooms_with_deltas': len(self.room_delta_managers),
            'total_players_tracked': len(self.player_last_updates)
        }
        
        # Get compression stats from delta managers
        compression_stats = []
        for room_code, delta_manager in self.room_delta_managers.items():
            compression_stats.append({
                'room_code': room_code,
                **delta_manager.get_compression_stats()
            })
        
        stats['compression_stats'] = compression_stats
        
        return stats
    
    def cleanup_room_data(self, room_code: str):
        """Clean up data for a completed/closed room"""
        if room_code in self.room_states:
            del self.room_states[room_code]
        
        if room_code in self.room_delta_managers:
            del self.room_delta_managers[room_code]
        
        if room_code in self.pending_updates:
            del self.pending_updates[room_code]
        
        if room_code in self.batch_timers:
            self.batch_timers[room_code].cancel()
            del self.batch_timers[room_code]
        
        self.logger.info(f"Cleaned up delta data for room {room_code}")
    
    # Convenience methods for common game updates
    
    async def broadcast_hand_update(self, 
                                  room_code: str, 
                                  player_hands: Dict[str, List[str]], 
                                  redis_manager):
        """Optimized broadcast for hand updates (deals, card plays)"""
        changes = {f'hand_{player}': hand for player, hand in player_hands.items()}
        affected_players = list(player_hands.keys())
        
        return await self.broadcast_specific_update(
            room_code, UpdateType.HAND_UPDATE, changes, affected_players, redis_manager
        )
    
    async def broadcast_turn_transition(self, 
                                      room_code: str, 
                                      current_turn: int, 
                                      current_player: str,
                                      redis_manager):
        """Optimized broadcast for turn changes"""
        changes = {
            'current_turn': current_turn,
            'current_player': current_player,
            'timestamp': time.time()
        }
        
        # All players need to know about turn changes
        try:
            players = redis_manager.get_room_players(room_code)
            affected_players = [p.get('username') for p in players if p.get('username')]
        except Exception:
            affected_players = [current_player]
        
        return await self.broadcast_specific_update(
            room_code, UpdateType.TURN_TRANSITION, changes, affected_players, redis_manager
        )
    
    async def broadcast_trick_result(self, 
                                   room_code: str, 
                                   trick_data: Dict[str, Any], 
                                   redis_manager):
        """Optimized broadcast for trick completion"""
        changes = {
            'current_trick': [],  # Trick is complete, reset
            'tricks': trick_data.get('team_tricks', {}),
            'trick_winner': trick_data.get('trick_winner'),
            'next_player': trick_data.get('next_player'),
            'led_suit': None  # Reset led suit
        }
        
        # All players affected by trick results
        try:
            players = redis_manager.get_room_players(room_code)
            affected_players = [p.get('username') for p in players if p.get('username')]
        except Exception:
            affected_players = ['all']
        
        return await self.broadcast_specific_update(
            room_code, UpdateType.TRICK_RESULT, changes, affected_players, redis_manager
        )
    
    async def broadcast_score_change(self, 
                                   room_code: str, 
                                   score_data: Dict[str, Any], 
                                   redis_manager):
        """Optimized broadcast for score updates"""
        changes = {
            'round_scores': score_data.get('round_scores', {}),
            'tricks': score_data.get('tricks', {}),
            'completed_tricks': score_data.get('completed_tricks', 0)
        }
        
        try:
            players = redis_manager.get_room_players(room_code)
            affected_players = [p.get('username') for p in players if p.get('username')]
        except Exception:
            affected_players = ['all']
        
        return await self.broadcast_specific_update(
            room_code, UpdateType.SCORE_CHANGE, changes, affected_players, redis_manager
        )
