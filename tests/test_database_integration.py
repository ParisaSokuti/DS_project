"""
Comprehensive PostgreSQL integration tests for Hokm game server.
Tests database operations, connections, and data persistence.
"""

import pytest
import asyncio
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List
from unittest.mock import AsyncMock, patch

from conftest import (
    assert_player_data_equal, 
    assert_game_state_valid
)


@pytest.mark.asyncio
@pytest.mark.integration
class TestDatabaseIntegration:
    """Test core database integration functionality."""
    
    async def test_database_connection(self, db_manager):
        """Test database connection establishment."""
        assert db_manager is not None
        
        # Test connection pool
        async with db_manager.get_session() as session:
            result = await session.execute("SELECT 1 as test")
            row = result.fetchone()
            assert row[0] == 1
    
    async def test_session_management(self, db_manager):
        """Test database session management and isolation."""
        # Test multiple concurrent sessions
        sessions = []
        for _ in range(5):
            session = await db_manager.get_session().__aenter__()
            sessions.append(session)
        
        # Each session should be independent
        assert len(sessions) == 5
        
        # Cleanup sessions
        for session in sessions:
            await session.close()
    
    async def test_transaction_rollback(self, db_session, test_data_generator):
        """Test transaction rollback for test isolation."""
        # Create test data
        player_data = test_data_generator["player"]()
        
        # Insert data in transaction
        from backend.database.models import Player
        player = Player(**player_data)
        db_session.add(player)
        await db_session.flush()
        
        # Verify data exists in current session
        result = await db_session.execute(
            "SELECT username FROM players WHERE username = :username",
            {"username": player_data["username"]}
        )
        assert result.fetchone() is not None
        
        # Transaction will be rolled back by fixture
        # Data should not persist to other sessions
    
    async def test_connection_pool_limits(self, db_manager, performance_config):
        """Test connection pool behavior under load."""
        concurrent_connections = performance_config["concurrent_users"] // 2
        
        async def get_connection():
            async with db_manager.get_session() as session:
                result = await session.execute("SELECT pg_backend_pid()")
                return result.fetchone()[0]
        
        # Test concurrent connections
        start_time = time.time()
        tasks = [get_connection() for _ in range(concurrent_connections)]
        pids = await asyncio.gather(*tasks)
        duration = time.time() - start_time
        
        # All connections should complete successfully
        assert len(pids) == concurrent_connections
        assert len(set(pids)) <= db_manager.pool_size  # PIDs should be within pool size
        assert duration < 5.0  # Should complete quickly
    
    async def test_database_error_handling(self, db_session):
        """Test database error handling and recovery."""
        # Test invalid SQL
        with pytest.raises(Exception):
            await db_session.execute("INVALID SQL STATEMENT")
        
        # Session should still be usable after error
        result = await db_session.execute("SELECT 1")
        assert result.fetchone()[0] == 1
    
    async def test_concurrent_transactions(self, db_manager, sample_players):
        """Test concurrent transaction handling."""
        async def update_player_stats(player_id: int, increment: int):
            async with db_manager.get_session() as session:
                async with session.begin():
                    # Simulate updating player statistics
                    await session.execute(
                        """
                        UPDATE players 
                        SET total_games = total_games + :increment,
                            last_active = NOW()
                        WHERE id = :player_id
                        """,
                        {"increment": increment, "player_id": player_id}
                    )
                    
                    # Small delay to increase chance of race condition
                    await asyncio.sleep(0.01)
        
        # Run concurrent updates on same player
        player_id = sample_players[0].id
        tasks = [update_player_stats(player_id, 1) for _ in range(10)]
        await asyncio.gather(*tasks)
        
        # Verify final state
        async with db_manager.get_session() as session:
            result = await session.execute(
                "SELECT total_games FROM players WHERE id = :player_id",
                {"player_id": player_id}
            )
            final_games = result.fetchone()[0]
            # Should be at least the original + 10 (may be more due to concurrent access)
            assert final_games >= 10


@pytest.mark.asyncio
@pytest.mark.integration
class TestPlayerManagement:
    """Test player data management operations."""
    
    async def test_create_player(self, game_integration, test_data_generator):
        """Test player creation."""
        player_data = test_data_generator["player"]()
        
        player, is_new = await game_integration.create_player_if_not_exists(
            username=player_data["username"],
            email=player_data["email"],
            display_name=player_data["display_name"]
        )
        
        assert player is not None
        assert is_new is True
        assert_player_data_equal(player, player_data)
    
    async def test_duplicate_player_handling(self, game_integration, sample_player):
        """Test handling of duplicate player creation."""
        # Try to create player with same username
        player, is_new = await game_integration.create_player_if_not_exists(
            username=sample_player.username,
            email="different@email.com",
            display_name="Different Name"
        )
        
        assert player is not None
        assert is_new is False
        assert player.username == sample_player.username
        assert player.email == sample_player.email  # Original email preserved
    
    async def test_update_player_stats(self, game_integration, sample_player):
        """Test updating player statistics."""
        original_games = sample_player.total_games
        
        await game_integration.update_player_stats(
            player_id=sample_player.id,
            games_played=5,
            games_won=3,
            games_lost=2,
            total_score=150
        )
        
        # Verify updates
        updated_player = await game_integration.get_player_by_id(sample_player.id)
        assert updated_player.total_games == original_games + 5
        assert updated_player.games_won == 3
        assert updated_player.games_lost == 2
        assert updated_player.total_score == 150
    
    async def test_player_authentication(self, game_integration, sample_player):
        """Test player authentication logic."""
        # Test valid authentication
        authenticated_player = await game_integration.authenticate_player(
            username=sample_player.username,
            password_hash="valid_hash"  # In real implementation, this would be hashed
        )
        
        # For now, just test that we can retrieve the player
        assert authenticated_player is not None
        assert authenticated_player.username == sample_player.username
    
    async def test_player_search_and_filtering(self, game_integration, sample_players):
        """Test player search and filtering capabilities."""
        # Test search by username pattern
        search_results = await game_integration.search_players(
            username_pattern="player_",
            limit=10
        )
        
        assert len(search_results) >= 1
        assert all("player_" in player.username for player in search_results)
        
        # Test filtering by activity
        active_players = await game_integration.get_active_players(
            minutes_threshold=60
        )
        
        assert len(active_players) >= 0
        for player in active_players:
            time_diff = datetime.utcnow() - player.last_active
            assert time_diff.total_seconds() < 3600  # Within 1 hour
    
    async def test_concurrent_player_operations(self, game_integration, sample_players):
        """Test concurrent player operations."""
        async def update_player_concurrently(player):
            await game_integration.update_player_stats(
                player_id=player.id,
                games_played=1,
                total_score=10
            )
        
        # Update all players concurrently
        tasks = [update_player_concurrently(player) for player in sample_players]
        await asyncio.gather(*tasks)
        
        # Verify all updates completed
        for player in sample_players:
            updated_player = await game_integration.get_player_by_id(player.id)
            assert updated_player.total_games >= 1
            assert updated_player.total_score >= 10


@pytest.mark.asyncio
@pytest.mark.integration
class TestGameStateManagement:
    """Test game state persistence and management."""
    
    async def test_create_game_session(self, game_integration, sample_players):
        """Test creating a new game session."""
        room_id = f"TEST_ROOM_{int(time.time())}"
        
        game_session = await game_integration.create_game_session(
            room_id=room_id,
            max_players=4,
            game_type="hokm",
            created_by=sample_players[0].id
        )
        
        assert game_session is not None
        assert game_session.room_id == room_id
        assert game_session.max_players == 4
        assert game_session.status == "waiting"
        assert game_session.current_players == 0
    
    async def test_join_game_session(self, game_integration, sample_game_session, sample_players):
        """Test players joining a game session."""
        player = sample_players[0]
        
        # Join game
        participant = await game_integration.join_game_room(
            room_id=sample_game_session.room_id,
            player_id=player.id,
            connection_id=f"conn_{player.id}"
        )
        
        assert participant is not None
        assert participant.game_session_id == sample_game_session.id
        assert participant.player_id == player.id
        assert participant.status == "joined"
    
    async def test_game_state_persistence(self, game_integration, sample_game_session, sample_game_state):
        """Test persisting and retrieving game state."""
        # Update game state
        await game_integration.update_game_state(
            room_id=sample_game_session.room_id,
            game_state=sample_game_state
        )
        
        # Retrieve game state
        retrieved_state = await game_integration.get_game_state(
            room_id=sample_game_session.room_id
        )
        
        assert retrieved_state is not None
        assert_game_state_valid(retrieved_state)
        assert retrieved_state["phase"] == sample_game_state["phase"]
        assert retrieved_state["trump_suit"] == sample_game_state["trump_suit"]
    
    async def test_record_game_moves(self, game_integration, sample_game_session, sample_players):
        """Test recording game moves."""
        player = sample_players[0]
        move_data = {
            "card": "AS",
            "suit": "spades",
            "round": 1,
            "trick": 1
        }
        
        # Record move
        move = await game_integration.record_game_move(
            room_id=sample_game_session.room_id,
            player_id=player.id,
            move_type="play_card",
            move_data=move_data
        )
        
        assert move is not None
        assert move.game_session_id == sample_game_session.id
        assert move.player_id == player.id
        assert move.move_type == "play_card"
        assert move.move_data["card"] == "AS"
    
    async def test_game_completion(self, game_integration, sample_game_session, sample_players):
        """Test game completion and cleanup."""
        # Complete the game
        final_scores = {
            "team_1": 7,
            "team_2": 3,
            "winner": "team_1"
        }
        
        completed_game = await game_integration.complete_game(
            room_id=sample_game_session.room_id,
            final_scores=final_scores,
            game_duration_seconds=1800  # 30 minutes
        )
        
        assert completed_game is not None
        assert completed_game.status == "completed"
        assert completed_game.finished_at is not None
        assert completed_game.final_scores == final_scores
    
    async def test_concurrent_game_operations(self, game_integration, sample_game_session, sample_players):
        """Test concurrent game operations."""
        async def record_move(player, card_index):
            cards = ["AS", "KS", "QS", "JS"]
            await game_integration.record_game_move(
                room_id=sample_game_session.room_id,
                player_id=player.id,
                move_type="play_card",
                move_data={
                    "card": cards[card_index],
                    "suit": "spades",
                    "round": 1,
                    "trick": 1
                }
            )
        
        # Record moves from multiple players concurrently
        tasks = [
            record_move(sample_players[i], i) 
            for i in range(min(4, len(sample_players)))
        ]
        await asyncio.gather(*tasks)
        
        # Verify all moves were recorded
        moves = await game_integration.get_game_moves(
            room_id=sample_game_session.room_id
        )
        assert len(moves) == min(4, len(sample_players))


@pytest.mark.asyncio
@pytest.mark.integration
class TestStatisticsAndAnalytics:
    """Test statistics calculation and analytics."""
    
    async def test_player_statistics_calculation(self, analytics_manager, sample_players):
        """Test player statistics calculation."""
        player = sample_players[0]
        
        # Calculate statistics
        stats = await analytics_manager.calculate_player_stats(player.id)
        
        assert stats is not None
        assert stats["games_played"] >= 0
        assert stats["win_rate"] >= 0.0
        assert stats["average_score"] >= 0.0
    
    async def test_leaderboard_generation(self, analytics_manager, sample_players):
        """Test leaderboard generation."""
        # Generate leaderboard
        leaderboard = await analytics_manager.generate_leaderboard(
            metric="win_rate",
            limit=10
        )
        
        assert isinstance(leaderboard, list)
        assert len(leaderboard) <= 10
        
        # Verify sorting (win_rate descending)
        if len(leaderboard) > 1:
            for i in range(len(leaderboard) - 1):
                assert leaderboard[i]["win_rate"] >= leaderboard[i + 1]["win_rate"]
    
    async def test_game_analytics(self, analytics_manager, db_session):
        """Test game analytics and insights."""
        # Test game duration analytics
        duration_stats = await analytics_manager.get_game_duration_stats(
            days_back=30
        )
        
        assert "average_duration" in duration_stats
        assert "total_games" in duration_stats
        assert duration_stats["total_games"] >= 0
        
        # Test player activity analytics
        activity_stats = await analytics_manager.get_player_activity_stats(
            days_back=7
        )
        
        assert "active_players" in activity_stats
        assert "total_sessions" in activity_stats
    
    async def test_performance_metrics(self, analytics_manager):
        """Test performance metrics collection."""
        metrics = await analytics_manager.get_performance_metrics()
        
        assert "database_queries" in metrics
        assert "response_times" in metrics
        assert "error_rates" in metrics
        
        # Verify metric types
        assert isinstance(metrics["database_queries"], (int, float))
        assert isinstance(metrics["response_times"], dict)
        assert isinstance(metrics["error_rates"], dict)


@pytest.mark.asyncio
@pytest.mark.integration 
class TestErrorHandlingAndRecovery:
    """Test error handling and recovery scenarios."""
    
    async def test_database_connection_recovery(self, db_manager):
        """Test database connection recovery after failure."""
        # Simulate connection failure and recovery
        with patch.object(db_manager, 'get_session') as mock_session:
            # First call raises an exception
            mock_session.side_effect = [
                Exception("Connection failed"),
                db_manager.get_session()
            ]
            
            # Should handle the error and retry
            with pytest.raises(Exception):
                async with mock_session():
                    pass
    
    async def test_transaction_rollback_on_error(self, game_integration, sample_player):
        """Test transaction rollback on errors."""
        original_games = sample_player.total_games
        
        try:
            # Start transaction that will fail
            async with game_integration.db_session.begin():
                await game_integration.update_player_stats(
                    player_id=sample_player.id,
                    games_played=5
                )
                # Force an error
                raise Exception("Simulated error")
        except Exception:
            pass
        
        # Verify rollback - stats should not have changed
        updated_player = await game_integration.get_player_by_id(sample_player.id)
        assert updated_player.total_games == original_games
    
    async def test_concurrent_access_handling(self, game_integration, sample_game_session):
        """Test handling of concurrent access to same resources."""
        async def update_game_state(phase: str):
            await game_integration.update_game_state(
                room_id=sample_game_session.room_id,
                game_state={"phase": phase, "current_turn": 0}
            )
        
        # Try to update game state concurrently
        tasks = [
            update_game_state("phase_1"),
            update_game_state("phase_2"),
            update_game_state("phase_3")
        ]
        
        # Should handle concurrent updates without corruption
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # Verify final state is consistent
        final_state = await game_integration.get_game_state(
            room_id=sample_game_session.room_id
        )
        assert final_state is not None
        assert "phase" in final_state


@pytest.mark.asyncio
@pytest.mark.slow
class TestDataIntegrity:
    """Test data integrity and consistency."""
    
    async def test_referential_integrity(self, game_integration, sample_players):
        """Test referential integrity constraints."""
        # Create game session
        room_id = f"INTEGRITY_TEST_{int(time.time())}"
        game_session = await game_integration.create_game_session(
            room_id=room_id,
            max_players=4,
            created_by=sample_players[0].id
        )
        
        # Add game moves
        move = await game_integration.record_game_move(
            room_id=room_id,
            player_id=sample_players[0].id,
            move_type="play_card",
            move_data={"card": "AS"}
        )
        
        # Verify relationships
        assert move.game_session_id == game_session.id
        assert move.player_id == sample_players[0].id
    
    async def test_data_consistency_across_operations(self, game_integration, sample_players):
        """Test data consistency across multiple operations."""
        player = sample_players[0]
        initial_games = player.total_games
        
        # Perform multiple related operations
        room_id = f"CONSISTENCY_TEST_{int(time.time())}"
        
        # Create game
        game = await game_integration.create_game_session(
            room_id=room_id,
            created_by=player.id
        )
        
        # Join game
        await game_integration.join_game_room(
            room_id=room_id,
            player_id=player.id
        )
        
        # Complete game
        await game_integration.complete_game(
            room_id=room_id,
            final_scores={"team_1": 7, "team_2": 0}
        )
        
        # Update player stats
        await game_integration.update_player_stats(
            player_id=player.id,
            games_played=1,
            games_won=1
        )
        
        # Verify consistency
        updated_player = await game_integration.get_player_by_id(player.id)
        completed_game = await game_integration.get_game_session(room_id)
        
        assert updated_player.total_games == initial_games + 1
        assert completed_game.status == "completed"
