#!/usr/bin/env python3
"""
Hybrid Data Architecture Integration Example
Demonstrates how to integrate the hybrid data layer into the Hokm game server
"""

import asyncio
import json
import logging
from typing import Dict, Any
from datetime import datetime

# Import the hybrid data architecture components
from backend.hybrid_data_layer import HybridDataLayer, HybridDataConfig
from backend.redis_game_state import RedisGameStateManager, GameStateConfig
from backend.postgresql_persistence import PostgreSQLPersistenceManager, PersistenceConfig
from backend.data_synchronization import (
    DataSynchronizationManager, SyncConfig, TransactionType,
    SyncOperation, SyncPriority
)
from backend.database.session_manager import AsyncSessionManager, DatabaseConfig

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class HybridGameServer:
    """
    Example integration of hybrid data architecture into the Hokm game server
    """
    
    def __init__(self):
        self.hybrid_data = None
        self.is_initialized = False
    
    async def initialize(self):
        """Initialize the hybrid data architecture"""
        try:
            logger.info("Initializing Hybrid Game Server...")
            
            # 1. Configure the hybrid data layer
            config = HybridDataConfig(
                redis_url="redis://localhost:6379",
                redis_prefix="hokm:",
                redis_default_ttl=3600,
                enable_write_through=True,
                enable_write_behind=True,
                sync_batch_size=50,
                sync_interval_seconds=30
            )
            
            # 2. Initialize the hybrid data layer
            self.hybrid_data = HybridDataLayer(config)
            await self.hybrid_data.initialize()
            
            self.is_initialized = True
            logger.info("✅ Hybrid Game Server initialized successfully!")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize Hybrid Game Server: {e}")
            raise
    
    async def create_game_session(self, room_code: str, players: list) -> Dict[str, Any]:
        """
        Example: Create a new game session using hybrid data architecture
        """
        if not self.is_initialized:
            raise RuntimeError("Server not initialized")
        
        try:
            # Use hybrid write-through transaction for critical game creation
            async with self.hybrid_data.sync_manager.hybrid_transaction(
                TransactionType.HYBRID_WRITE_THROUGH
            ) as tx:
                
                # 1. Create game session data
                game_data = {
                    'room_code': room_code,
                    'players': players,
                    'phase': 'waiting_for_players',
                    'created_at': datetime.utcnow().isoformat(),
                    'teams': {},
                    'hakem': None,
                    'hokm': None,
                    'current_turn': 0,
                    'tricks': {},
                    'scores': {'team1': 0, 'team2': 0}
                }
                
                # 2. Store in Redis for real-time access
                await self.hybrid_data.create_game_session(room_code, game_data)
                
                # 3. Log session creation to PostgreSQL
                await self.hybrid_data.sync_manager.sync_game_completion(
                    room_code, 
                    {'action': 'session_created', 'data': game_data}
                )
                
                logger.info(f"✅ Game session {room_code} created successfully")
                return game_data
                
        except Exception as e:
            logger.error(f"❌ Failed to create game session {room_code}: {e}")
            raise
    
    async def handle_player_move(self, room_code: str, player_id: str, move_data: Dict[str, Any]) -> bool:
        """
        Example: Handle a player move with hybrid data patterns
        """
        try:
            # Use write-behind for non-critical moves (better performance)
            async with self.hybrid_data.sync_manager.hybrid_transaction(
                TransactionType.HYBRID_WRITE_BEHIND
            ) as tx:
                
                # 1. Update game state in Redis immediately
                current_state = await self.hybrid_data.get_game_session(room_code)
                if not current_state:
                    raise ValueError(f"Game session {room_code} not found")
                
                # 2. Apply the move
                updated_state = self._apply_move(current_state, player_id, move_data)
                
                # 3. Save updated state to Redis
                await self.hybrid_data.update_game_session(room_code, updated_state)
                
                # 4. Queue move for PostgreSQL logging (async)
                await self.hybrid_data.sync_manager.queue_sync_task(
                    operation=SyncOperation.CREATE,
                    priority=SyncPriority.MEDIUM,
                    source_layer="redis",
                    target_layer="postgresql",
                    data_type="game_move",
                    data_key=f"{room_code}:{player_id}",
                    data_payload={
                        'room_code': room_code,
                        'player_id': player_id,
                        'move': move_data,
                        'timestamp': datetime.utcnow().isoformat()
                    }
                )
                
                logger.info(f"✅ Move processed for player {player_id} in room {room_code}")
                return True
                
        except Exception as e:
            logger.error(f"❌ Failed to process move for player {player_id}: {e}")
            return False
    
    async def handle_game_completion(self, room_code: str, final_scores: Dict[str, Any]) -> bool:
        """
        Example: Handle game completion with high-consistency requirements
        """
        try:
            # Use write-through for critical game completion data
            async with self.hybrid_data.sync_manager.hybrid_transaction(
                TransactionType.HYBRID_WRITE_THROUGH
            ) as tx:
                
                # 1. Get final game state
                game_state = await self.hybrid_data.get_game_session(room_code)
                if not game_state:
                    raise ValueError(f"Game session {room_code} not found")
                
                # 2. Update with final data
                game_state.update({
                    'phase': 'completed',
                    'final_scores': final_scores,
                    'completed_at': datetime.utcnow().isoformat()
                })
                
                # 3. Save to Redis
                await self.hybrid_data.update_game_session(room_code, game_state)
                
                # 4. Immediately persist to PostgreSQL
                await self.hybrid_data.sync_manager.sync_game_completion(
                    room_code, 
                    game_state
                )
                
                # 5. Update player statistics
                for player_id in game_state['players']:
                    stats_update = self._calculate_player_stats(player_id, final_scores)
                    await self.hybrid_data.sync_manager.sync_player_statistics(
                        player_id, 
                        stats_update
                    )
                
                # 6. Clean up Redis data after successful persistence
                await asyncio.sleep(300)  # Keep for 5 minutes for reconnections
                await self.hybrid_data.delete_game_session(room_code)
                
                logger.info(f"✅ Game {room_code} completed and persisted successfully")
                return True
                
        except Exception as e:
            logger.error(f"❌ Failed to complete game {room_code}: {e}")
            return False
    
    async def handle_player_reconnection(self, player_id: str, room_code: str) -> Dict[str, Any]:
        """
        Example: Handle player reconnection using cached data
        """
        try:
            # 1. Try to get game state from Redis (fast)
            game_state = await self.hybrid_data.get_game_session(room_code)
            
            if game_state:
                # 2. Get player-specific data
                player_data = await self.hybrid_data.get_player_session_data(player_id)
                
                # 3. Combine for reconnection response
                reconnection_data = {
                    'game_state': game_state,
                    'player_data': player_data,
                    'reconnected_at': datetime.utcnow().isoformat()
                }
                
                logger.info(f"✅ Player {player_id} reconnected to room {room_code}")
                return reconnection_data
            
            else:
                # 4. Fallback to PostgreSQL for completed games
                historical_data = await self.hybrid_data.get_historical_game_data(room_code)
                if historical_data:
                    logger.info(f"ℹ️ Returning historical data for completed game {room_code}")
                    return {'historical_game': historical_data}
                
                raise ValueError(f"No data found for game {room_code}")
                
        except Exception as e:
            logger.error(f"❌ Failed to handle reconnection for player {player_id}: {e}")
            raise
    
    async def get_leaderboard(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Example: Get leaderboard using caching patterns
        """
        try:
            # 1. Try Redis cache first
            cached_leaderboard = await self.hybrid_data.get_cached_data("leaderboard:global")
            
            if cached_leaderboard:
                logger.info("✅ Retrieved leaderboard from cache")
                return cached_leaderboard
            
            # 2. Generate from PostgreSQL and cache
            leaderboard_data = await self.hybrid_data.postgresql_manager.get_player_rankings(limit)
            
            # 3. Cache for future requests
            await self.hybrid_data.cache_data(
                "leaderboard:global", 
                leaderboard_data, 
                ttl=300  # 5 minutes
            )
            
            logger.info("✅ Generated and cached leaderboard from database")
            return leaderboard_data
            
        except Exception as e:
            logger.error(f"❌ Failed to get leaderboard: {e}")
            return []
    
    def _apply_move(self, game_state: Dict[str, Any], player_id: str, move_data: Dict[str, Any]) -> Dict[str, Any]:
        """Apply a move to the game state (simplified example)"""
        # This would contain your actual game logic
        game_state['last_move'] = {
            'player_id': player_id,
            'move': move_data,
            'timestamp': datetime.utcnow().isoformat()
        }
        return game_state
    
    def _calculate_player_stats(self, player_id: str, final_scores: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate player statistics update (simplified example)"""
        return {
            'games_played': 1,
            'points_scored': final_scores.get(player_id, 0),
            'last_played': datetime.utcnow().isoformat()
        }
    
    async def get_performance_metrics(self) -> Dict[str, Any]:
        """Get performance metrics from the hybrid data layer"""
        if not self.is_initialized:
            return {}
        
        return {
            'redis_metrics': await self.hybrid_data.redis_manager.get_performance_metrics(),
            'postgresql_metrics': await self.hybrid_data.postgresql_manager.get_performance_metrics(),
            'sync_metrics': await self.hybrid_data.sync_manager.get_sync_status()
        }
    
    async def cleanup(self):
        """Cleanup resources"""
        if self.hybrid_data:
            await self.hybrid_data.cleanup()
        logger.info("✅ Hybrid Game Server cleaned up")

# Example usage and testing
async def main():
    """Demonstration of the hybrid data architecture integration"""
    
    server = HybridGameServer()
    
    try:
        # Initialize the server
        await server.initialize()
        
        # Example 1: Create a game session
        room_code = "DEMO_001"
        players = ["player1", "player2", "player3", "player4"]
        
        print("\n🎮 Creating game session...")
        game_data = await server.create_game_session(room_code, players)
        print(f"Game created: {room_code}")
        
        # Example 2: Handle some player moves
        print("\n🎯 Processing player moves...")
        for i, player in enumerate(players):
            move_data = {'card': f'ace_of_hearts_{i}', 'action': 'play_card'}
            success = await server.handle_player_move(room_code, player, move_data)
            print(f"Move by {player}: {'✅' if success else '❌'}")
        
        # Example 3: Handle player reconnection
        print("\n🔄 Testing player reconnection...")
        reconnection_data = await server.handle_player_reconnection("player1", room_code)
        print(f"Reconnection data retrieved for player1")
        
        # Example 4: Complete the game
        print("\n🏁 Completing game...")
        final_scores = {'team1': 7, 'team2': 6}
        success = await server.handle_game_completion(room_code, final_scores)
        print(f"Game completion: {'✅' if success else '❌'}")
        
        # Example 5: Get leaderboard
        print("\n🏆 Getting leaderboard...")
        leaderboard = await server.get_leaderboard(5)
        print(f"Leaderboard entries: {len(leaderboard)}")
        
        # Example 6: Show performance metrics
        print("\n📊 Performance metrics...")
        metrics = await server.get_performance_metrics()
        print(f"Redis operations: {metrics.get('redis_metrics', {}).get('total_operations', 0)}")
        
        print("\n✅ All examples completed successfully!")
        
    except Exception as e:
        print(f"❌ Error during demonstration: {e}")
        
    finally:
        await server.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
