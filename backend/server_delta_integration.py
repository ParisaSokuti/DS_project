# server_delta_integration.py
"""
Example integration of delta update system with existing server.py

This shows how to integrate the delta system with minimal changes to existing code
"""

import asyncio
import json
import time
from typing import Dict, Any, Optional

# Import delta components
from network_delta import DeltaNetworkManager
from game_board_delta import DeltaGameBoard
from game_state_delta import UpdateType


class DeltaGameServer:
    """
    Enhanced GameServer with delta update capabilities
    
    This can be used as a drop-in replacement for the existing GameServer
    with significant bandwidth optimizations.
    """
    
    def __init__(self):
        # Use delta-enabled network manager
        self.network_manager = DeltaNetworkManager()
        
        # Game storage (enhanced with delta support)
        self.active_games = {}  # room_code -> DeltaGameBoard
        
        # Redis manager (use existing)
        from redis_manager_hybrid import HybridRedisManager
        self.redis_manager = HybridRedisManager()
        
        # Delta-specific configuration
        self.delta_config = {
            'auto_broadcast': True,
            'compression_threshold': 500,  # Compress deltas > 500 bytes
            'batch_delay': 0.1,           # 100ms batching
            'max_delta_history': 50       # Keep 50 deltas for reconciliation
        }
    
    async def startup(self):
        """Initialize server with delta support"""
        # Connect to Redis
        await self.redis_manager.connect_async()
        
        # Additional delta setup if needed
        print("✓ Delta-enabled game server started")
        return True
    
    async def handle_join_delta(self, websocket, data):
        """
        Enhanced join handler with delta support
        
        Minimal changes from original - just uses delta network manager
        """
        try:
            room_code = data.get('room_code', '9999')
            player_id = data.get('player_id') or f"player_{int(time.time())}"
            username = data.get('username', f'Player_{player_id[:8]}')
            
            # Check if room exists
            room_exists = await self.redis_manager.room_exists_async(room_code)
            
            if not room_exists:
                # Create new room
                await self.redis_manager.create_room_async(room_code)
                print(f"Created new room {room_code}")
            
            # Player data
            player_data = {
                'player_id': player_id,
                'username': username,
                'connection_status': 'active',
                'joined_at': str(int(time.time()))
            }
            
            # Add to room
            await self.redis_manager.add_player_to_room_async(room_code, player_data)
            
            # Register connection with delta network manager
            self.network_manager.register_connection(websocket, player_id, room_code, username)
            
            # Get current game state
            game_state = await self.redis_manager.get_game_state_async(room_code)
            
            # Send join confirmation with optimized state
            join_response = {
                'type': 'join_success',
                'player_id': player_id,
                'username': username,
                'room_code': room_code
            }
            
            if game_state:
                # Create optimized state for this player
                if room_code in self.active_games:
                    game = self.active_games[room_code]
                    join_response['game_state'] = game.get_player_optimized_state(username)
                else:
                    # Fallback to full state
                    join_response['game_state'] = game_state
            
            await self.network_manager.send_message(websocket, 'join_success', join_response)
            
            # Check if room is ready to start
            await self._check_room_ready_delta(room_code)
            
        except Exception as e:
            print(f"[ERROR] Join failed: {e}")
            await self.network_manager.notify_error(websocket, "Failed to join game")
    
    async def _check_room_ready_delta(self, room_code: str):
        """Check if room is ready and start with delta broadcasting"""
        try:
            players = await self.redis_manager.get_room_players_async(room_code)
            active_players = [p for p in players if p.get('connection_status') == 'active']
            
            if len(active_players) >= 4:  # Assuming 4-player game
                await self.start_team_assignment_delta(room_code)
                
        except Exception as e:
            print(f"[ERROR] Failed to check room ready: {e}")
    
    async def start_team_assignment_delta(self, room_code: str):
        """Start team assignment with delta broadcasting"""
        try:
            players = await self.redis_manager.get_room_players_async(room_code)
            player_names = [p['username'] for p in players]
            
            # Create delta-enabled game
            game = DeltaGameBoard(
                players=player_names,
                room_code=room_code,
                network_manager=self.network_manager
            )
            
            self.active_games[room_code] = game
            
            # Assign teams with delta broadcasting
            result = await game.assign_teams_and_hakem_delta(self.redis_manager)
            
            if 'error' not in result:
                print(f"Started team assignment for room {room_code} with delta updates")
            
        except Exception as e:
            print(f"[ERROR] Failed to start team assignment: {e}")
    
    async def handle_card_play_delta(self, websocket, data):
        """
        Handle card play with optimized delta updates
        
        This replaces the original card play handler with delta-optimized version
        """
        try:
            room_code = data.get('room_code')
            player = data.get('player')
            card = data.get('card')
            
            if not all([room_code, player, card]):
                await self.network_manager.notify_error(websocket, "Missing card play data")
                return
            
            # Get game
            game = self.active_games.get(room_code)
            if not game:
                await self.network_manager.notify_error(websocket, "Game not found")
                return
            
            # Execute card play with delta broadcasting
            result = await game.play_card_delta(player, card, self.redis_manager)
            
            if not result.get('valid'):
                await self.network_manager.notify_error(websocket, result.get('message', 'Invalid play'))
                return
            
            # Delta updates are automatically sent by game.play_card_delta()
            # No need for manual broadcasting - it's handled efficiently
            
            print(f"Card play processed with delta updates: {player} played {card}")
            
        except Exception as e:
            print(f"[ERROR] Card play failed: {e}")
            await self.network_manager.notify_error(websocket, "Failed to play card")
    
    async def handle_hokm_selection_delta(self, websocket, data):
        """Handle hokm selection with delta updates"""
        try:
            room_code = data.get('room_code')
            suit = data.get('suit')
            player = data.get('player')
            
            game = self.active_games.get(room_code)
            if not game:
                await self.network_manager.notify_error(websocket, "Game not found")
                return
            
            # Validate hakem
            if player != game.hakem:
                await self.network_manager.notify_error(websocket, "Only hakem can choose hokm")
                return
            
            # Set hokm with delta broadcasting
            success = await game.set_hokm_delta(suit, self.redis_manager, room_code)
            
            if success:
                # Start final deal
                await game.final_deal_delta(self.redis_manager)
                print(f"Hokm selected ({suit}) and final deal completed with delta updates")
            else:
                await self.network_manager.notify_error(websocket, "Failed to set hokm")
                
        except Exception as e:
            print(f"[ERROR] Hokm selection failed: {e}")
            await self.network_manager.notify_error(websocket, "Failed to select hokm")
    
    async def handle_player_reconnection_delta(self, websocket, data):
        """
        Handle player reconnection with state reconciliation
        
        This provides much better reconnection experience with minimal bandwidth
        """
        try:
            player_id = data.get('player_id')
            
            if not player_id:
                await self.network_manager.notify_error(websocket, "Missing player ID")
                return
            
            # Get player session
            session = await self.redis_manager.get_player_session_async(player_id)
            if not session:
                await self.network_manager.notify_error(websocket, "Session not found")
                return
            
            room_code = session.get('room_code')
            username = session.get('username')
            
            # Handle reconnection with state reconciliation
            success = await self.network_manager.handle_player_reconnection_with_reconciliation(
                websocket, player_id, room_code, self.redis_manager
            )
            
            if success:
                print(f"Player {username} reconnected with delta reconciliation")
            else:
                print(f"Failed to reconnect player {username}")
                
        except Exception as e:
            print(f"[ERROR] Reconnection failed: {e}")
            await self.network_manager.notify_error(websocket, "Reconnection failed")
    
    async def handle_websocket_delta(self, websocket, path):
        """
        Enhanced WebSocket handler with delta support
        
        This replaces the original WebSocket handler
        """
        try:
            print(f"New connection: {websocket.remote_address}")
            
            async for message in websocket:
                try:
                    data = json.loads(message)
                    message_type = data.get('type')
                    
                    # Route messages to delta-enabled handlers
                    if message_type == 'join':
                        await self.handle_join_delta(websocket, data)
                    
                    elif message_type == 'play_card':
                        await self.handle_card_play_delta(websocket, data)
                    
                    elif message_type == 'choose_hokm':
                        await self.handle_hokm_selection_delta(websocket, data)
                    
                    elif message_type == 'reconnect':
                        await self.handle_player_reconnection_delta(websocket, data)
                    
                    elif message_type == 'get_stats':
                        # Send bandwidth statistics
                        stats = self.network_manager.get_bandwidth_statistics()
                        await self.network_manager.send_message(websocket, 'stats', stats)
                    
                    else:
                        await self.network_manager.notify_error(websocket, f"Unknown message type: {message_type}")
                        
                except json.JSONDecodeError:
                    await self.network_manager.notify_error(websocket, "Invalid JSON")
                    
                except Exception as e:
                    print(f"[ERROR] Message handling failed: {e}")
                    await self.network_manager.notify_error(websocket, "Internal error")
        
        except Exception as e:
            print(f"[ERROR] WebSocket error: {e}")
        
        finally:
            # Clean up connection
            self.network_manager.remove_connection(websocket)
    
    def get_optimization_report(self) -> Dict[str, Any]:
        """Get comprehensive optimization report"""
        network_stats = self.network_manager.get_bandwidth_statistics()
        
        game_stats = {}
        for room_code, game in self.active_games.items():
            game_stats[room_code] = game.get_update_statistics()
        
        return {
            'network_optimization': network_stats,
            'game_optimizations': game_stats,
            'total_rooms': len(self.active_games),
            'timestamp': time.time()
        }


# Integration helper functions

async def migrate_existing_game_to_delta(room_code: str, 
                                       existing_game, 
                                       network_manager: DeltaNetworkManager,
                                       redis_manager) -> DeltaGameBoard:
    """
    Migrate an existing GameBoard to DeltaGameBoard
    
    This can be used to gradually migrate existing games
    """
    # Create new delta game with same state
    delta_game = DeltaGameBoard(
        players=existing_game.players,
        room_code=room_code,
        network_manager=network_manager
    )
    
    # Copy all state
    delta_game.teams = existing_game.teams.copy()
    delta_game.hakem = existing_game.hakem
    delta_game.hokm = existing_game.hokm
    delta_game.current_turn = existing_game.current_turn
    delta_game.tricks = existing_game.tricks.copy()
    delta_game.round_scores = existing_game.round_scores.copy()
    delta_game.hands = {p: cards.copy() for p, cards in existing_game.hands.items()}
    delta_game.current_trick = existing_game.current_trick.copy()
    delta_game.led_suit = existing_game.led_suit
    delta_game.game_phase = existing_game.game_phase
    delta_game.played_cards = existing_game.played_cards.copy()
    delta_game.completed_tricks = existing_game.completed_tricks
    
    # Force full sync to establish baseline
    await delta_game.force_full_resync(redis_manager)
    
    return delta_game


def calculate_bandwidth_savings(stats: Dict[str, Any]) -> Dict[str, Any]:
    """Calculate estimated bandwidth savings from delta updates"""
    total_updates = stats.get('total_updates', 0)
    delta_updates = stats.get('delta_updates', 0)
    full_syncs = stats.get('full_syncs', 0)
    
    # Estimate average sizes (these are rough estimates)
    avg_full_sync_size = 2000  # bytes
    avg_delta_size = 300       # bytes
    
    # Calculate theoretical full sync bytes
    theoretical_full_bytes = total_updates * avg_full_sync_size
    
    # Calculate actual bytes
    actual_bytes = (delta_updates * avg_delta_size) + (full_syncs * avg_full_sync_size)
    
    savings = theoretical_full_bytes - actual_bytes
    savings_percent = (savings / theoretical_full_bytes * 100) if theoretical_full_bytes > 0 else 0
    
    return {
        'theoretical_full_sync_bytes': theoretical_full_bytes,
        'actual_bytes_sent': actual_bytes,
        'bytes_saved': savings,
        'savings_percentage': savings_percent,
        'delta_ratio': (delta_updates / total_updates) if total_updates > 0 else 0
    }


# Example usage
async def main():
    """Example of running the delta-enabled server"""
    import websockets
    
    # Create delta-enabled server
    server = DeltaGameServer()
    
    # Start server
    if not await server.startup():
        print("Failed to start server")
        return
    
    try:
        # Start WebSocket server
        start_server = websockets.serve(
            server.handle_websocket_delta,
            "localhost",
            8765,
            ping_interval=20,
            ping_timeout=10
        )
        
        print("🚀 Delta-optimized game server started on ws://localhost:8765")
        print("📊 Bandwidth optimization enabled")
        
        await start_server
        await asyncio.Future()  # Run forever
        
    except KeyboardInterrupt:
        print("Server stopped")
        
        # Print optimization report
        report = server.get_optimization_report()
        print(f"📈 Optimization Report:")
        print(f"   Delta updates: {report['network_optimization']['delta_updates_sent']}")
        print(f"   Full syncs: {report['network_optimization']['full_syncs_sent']}")
        print(f"   Compression saves: {report['network_optimization']['compression_saves']}")
        
        savings = calculate_bandwidth_savings(report['network_optimization'])
        print(f"   Estimated bandwidth savings: {savings['savings_percentage']:.1f}%")
        
    finally:
        await server.redis_manager.disconnect_async()


if __name__ == "__main__":
    asyncio.run(main())
