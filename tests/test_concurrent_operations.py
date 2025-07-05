"""
Concurrent operations tests for PostgreSQL integration.
Tests race conditions, deadlock handling, and concurrent access patterns.
"""

import pytest
import asyncio
import time
import random
from typing import Dict, List, Any
from unittest.mock import patch

from test_utils import (
    TestDataGenerator,
    TestAssertions, 
    ConcurrencyTestHelpers,
    PerformanceProfiler
)


@pytest.mark.asyncio
@pytest.mark.concurrent
@pytest.mark.integration
class TestConcurrentOperations:
    """Test concurrent database operations and race condition handling."""
    
    async def test_concurrent_player_creation(self, db_manager, test_data_generator):
        """Test concurrent player creation without conflicts."""
        num_concurrent = 20
        
        async def create_player():
            async with db_manager.get_session() as session:
                player_data = test_data_generator["player"]()
                
                from backend.database.models import Player
                player = Player(**player_data)
                session.add(player)
                await session.commit()
                return player.id
        
        # Create operations
        operations = [create_player for _ in range(num_concurrent)]
        
        # Run concurrently
        results = await ConcurrencyTestHelpers.run_concurrent_operations(
            operations, max_concurrent=10, timeout=30.0
        )
        
        # Verify all succeeded and are unique
        successful_results = [r for r in results if not isinstance(r, Exception)]
        assert len(successful_results) == num_concurrent, f"Expected {num_concurrent} successes, got {len(successful_results)}"
        assert len(set(successful_results)) == num_concurrent, "Player IDs should be unique"
    
    async def test_concurrent_game_session_joins(self, db_manager, test_data_generator, db_helpers):
        """Test concurrent players joining the same game session."""
        # Create test players
        async with db_manager.get_session() as session:
            players = await db_helpers.create_test_players(session, count=10)
        
        # Create game session
        async with db_manager.get_session() as session:
            game_session = await db_helpers.create_test_game_session(
                session, players[0]["id"], players[:1]
            )
        
        session_id = game_session["session_id"]
        join_attempts = 0
        successful_joins = 0
        
        async def join_game_session(player_id: int):
            nonlocal join_attempts, successful_joins
            join_attempts += 1
            
            async with db_manager.get_session() as session:
                try:
                    # Simulate joining game session logic
                    # Check if session has space
                    result = await session.execute(
                        "SELECT COUNT(*) FROM game_session_players WHERE session_id = :session_id",
                        {"session_id": session_id}
                    )
                    current_players = result.scalar()
                    
                    if current_players < 4:  # Max 4 players
                        await session.execute(
                            "INSERT INTO game_session_players (session_id, player_id, joined_at) VALUES (:session_id, :player_id, NOW())",
                            {"session_id": session_id, "player_id": player_id}
                        )
                        await session.commit()
                        successful_joins += 1
                        return True
                    return False
                    
                except Exception as e:
                    await session.rollback()
                    raise e
        
        # Attempt concurrent joins (more attempts than available slots)
        operations = [lambda p_id=p["id"]: join_game_session(p_id) for p in players[1:8]]  # 7 attempts for 3 slots
        
        results = await ConcurrencyTestHelpers.run_concurrent_operations(
            operations, max_concurrent=7, timeout=30.0
        )
        
        # Verify only 3 additional players joined (total 4)
        async with db_manager.get_session() as session:
            result = await session.execute(
                "SELECT COUNT(*) FROM game_session_players WHERE session_id = :session_id",
                {"session_id": session_id}
            )
            final_count = result.scalar()
            assert final_count <= 4, f"Too many players in session: {final_count}"
    
    async def test_concurrent_game_moves(self, db_manager, test_data_generator, db_helpers):
        """Test concurrent game moves within the same turn."""
        # Create game with 4 players
        async with db_manager.get_session() as session:
            players = await db_helpers.create_test_players(session, count=4)
            game_session = await db_helpers.create_test_game_session(
                session, players[0]["id"], players
            )
        
        session_id = game_session["session_id"]
        round_number = 1
        
        async def play_card(player_id: int, turn_order: int):
            async with db_manager.get_session() as session:
                try:
                    move_data = test_data_generator["game_move"](session_id, player_id, round_number)
                    move_data["turn_order"] = turn_order
                    
                    from backend.database.models import GameMove
                    move = GameMove(**move_data)
                    session.add(move)
                    await session.commit()
                    return move.id
                    
                except Exception as e:
                    await session.rollback()
                    raise e
        
        # All players try to play simultaneously (only current turn should succeed)
        operations = [lambda p_id=p["id"], i=i: play_card(p_id, i+1) for i, p in enumerate(players)]
        
        start_time = time.perf_counter()
        results = await ConcurrencyTestHelpers.run_concurrent_operations(
            operations, max_concurrent=4, timeout=30.0
        )
        end_time = time.perf_counter()
        
        # Verify results
        successful_moves = [r for r in results if not isinstance(r, Exception)]
        assert len(successful_moves) >= 1, "At least one move should succeed"
        
        print(f"Concurrent moves test completed in {end_time - start_time:.2f}s")
        print(f"Successful moves: {len(successful_moves)}/{len(operations)}")
    
    async def test_deadlock_detection_and_recovery(self, db_manager, test_data_generator):
        """Test deadlock detection and recovery mechanisms."""
        deadlock_detected = False
        retry_count = 0
        
        async def operation_a():
            nonlocal retry_count
            async with db_manager.get_session() as session:
                try:
                    # Lock resource A then B
                    await session.execute("SELECT pg_advisory_lock(1)")
                    await asyncio.sleep(0.1)  # Simulate work
                    await session.execute("SELECT pg_advisory_lock(2)")
                    await session.execute("SELECT pg_advisory_unlock_all()")
                    return "success_a"
                except Exception as e:
                    retry_count += 1
                    await session.execute("SELECT pg_advisory_unlock_all()")
                    raise e
        
        async def operation_b():
            nonlocal deadlock_detected
            async with db_manager.get_session() as session:
                try:
                    # Lock resource B then A (potential deadlock)
                    await session.execute("SELECT pg_advisory_lock(2)")
                    await asyncio.sleep(0.1)  # Simulate work
                    await session.execute("SELECT pg_advisory_lock(1)")
                    await session.execute("SELECT pg_advisory_unlock_all()")
                    return "success_b"
                except Exception as e:
                    deadlock_detected = True
                    await session.execute("SELECT pg_advisory_unlock_all()")
                    raise e
        
        # Run operations that can cause deadlock
        results = await ConcurrencyTestHelpers.run_concurrent_operations(
            [operation_a, operation_b], max_concurrent=2, timeout=30.0
        )
        
        # At least one should complete successfully
        successful_results = [r for r in results if not isinstance(r, Exception)]
        assert len(successful_results) >= 1, "At least one operation should complete"
    
    async def test_connection_pool_under_load(self, db_manager):
        """Test connection pool behavior under concurrent load."""
        pool_exhaustion_detected = False
        successful_operations = 0
        failed_operations = 0
        
        async def database_operation():
            nonlocal successful_operations, failed_operations, pool_exhaustion_detected
            try:
                async with db_manager.get_session() as session:
                    # Simulate database work
                    await session.execute("SELECT pg_sleep(0.1)")
                    await session.execute("SELECT 1")
                    successful_operations += 1
                    return "success"
            except Exception as e:
                failed_operations += 1
                if "pool" in str(e).lower():
                    pool_exhaustion_detected = True
                raise e
        
        # Create more operations than the pool size
        num_operations = 50  # More than typical pool size
        operations = [database_operation for _ in range(num_operations)]
        
        profiler = PerformanceProfiler()
        profiler.start()
        
        results = await ConcurrencyTestHelpers.run_concurrent_operations(
            operations, max_concurrent=30, timeout=60.0
        )
        
        metrics = profiler.stop()
        
        # Analyze results
        successful_results = [r for r in results if not isinstance(r, Exception)]
        failed_results = [r for r in results if isinstance(r, Exception)]
        
        print(f"Connection pool test results:")
        print(f"  Successful: {len(successful_results)}")
        print(f"  Failed: {len(failed_results)}")
        print(f"  Pool exhaustion detected: {pool_exhaustion_detected}")
        print(f"  Total duration: {metrics['total_duration']:.2f}s")
        
        # Most operations should succeed
        success_rate = len(successful_results) / num_operations
        assert success_rate >= 0.8, f"Success rate too low: {success_rate:.2%}"
    
    async def test_concurrent_statistics_updates(self, db_manager, test_data_generator, db_helpers):
        """Test concurrent updates to player statistics."""
        # Create test player
        async with db_manager.get_session() as session:
            players = await db_helpers.create_test_players(session, count=1)
        
        player_id = players[0]["id"]
        num_concurrent_updates = 20
        
        async def update_player_stats():
            async with db_manager.get_session() as session:
                try:
                    # Increment games played and won
                    await session.execute("""
                        UPDATE player_stats 
                        SET games_played = games_played + 1,
                            games_won = games_won + 1,
                            total_score = total_score + :score_increment
                        WHERE player_id = :player_id
                    """, {"player_id": player_id, "score_increment": random.randint(1, 100)})
                    
                    await session.commit()
                    return "success"
                except Exception as e:
                    await session.rollback()
                    raise e
        
        # Run concurrent updates
        operations = [update_player_stats for _ in range(num_concurrent_updates)]
        
        results = await ConcurrencyTestHelpers.run_concurrent_operations(
            operations, max_concurrent=10, timeout=30.0
        )
        
        # Verify all updates succeeded
        successful_updates = [r for r in results if not isinstance(r, Exception)]
        assert len(successful_updates) == num_concurrent_updates, f"Some updates failed: {len(successful_updates)}/{num_concurrent_updates}"
        
        # Verify final statistics are consistent
        async with db_manager.get_session() as session:
            result = await session.execute(
                "SELECT games_played, games_won FROM player_stats WHERE player_id = :player_id",
                {"player_id": player_id}
            )
            stats = result.fetchone()
            
            if stats:
                assert stats[0] == num_concurrent_updates, f"Games played mismatch: {stats[0]} != {num_concurrent_updates}"
                assert stats[1] == num_concurrent_updates, f"Games won mismatch: {stats[1]} != {num_concurrent_updates}"
    
    async def test_race_condition_in_game_completion(self, db_manager, test_data_generator, db_helpers):
        """Test race conditions when multiple processes try to complete the same game."""
        # Create game session
        async with db_manager.get_session() as session:
            players = await db_helpers.create_test_players(session, count=4)
            game_session = await db_helpers.create_test_game_session(
                session, players[0]["id"], players
            )
        
        session_id = game_session["session_id"]
        completion_attempts = 0
        successful_completions = 0
        
        async def complete_game():
            nonlocal completion_attempts, successful_completions
            completion_attempts += 1
            
            async with db_manager.get_session() as session:
                try:
                    # Check if game is already completed
                    result = await session.execute(
                        "SELECT game_phase FROM game_sessions WHERE session_id = :session_id FOR UPDATE",
                        {"session_id": session_id}
                    )
                    current_phase = result.scalar()
                    
                    if current_phase != "completed":
                        # Update game to completed
                        await session.execute(
                            "UPDATE game_sessions SET game_phase = 'completed', completed_at = NOW() WHERE session_id = :session_id",
                            {"session_id": session_id}
                        )
                        await session.commit()
                        successful_completions += 1
                        return "completed"
                    else:
                        return "already_completed"
                        
                except Exception as e:
                    await session.rollback()
                    raise e
        
        # Multiple processes try to complete the same game
        operations = [complete_game for _ in range(5)]
        
        results = await ConcurrencyTestHelpers.run_concurrent_operations(
            operations, max_concurrent=5, timeout=30.0
        )
        
        # Only one completion should succeed
        assert successful_completions == 1, f"Expected 1 successful completion, got {successful_completions}"
        
        # Verify game is in completed state
        async with db_manager.get_session() as session:
            result = await session.execute(
                "SELECT game_phase FROM game_sessions WHERE session_id = :session_id",
                {"session_id": session_id}
            )
            final_phase = result.scalar()
            assert final_phase == "completed", f"Game should be completed, but is {final_phase}"


@pytest.mark.asyncio
@pytest.mark.stress
@pytest.mark.slow
class TestStressAndLoadTesting:
    """Stress testing for database operations under heavy load."""
    
    async def test_sustained_concurrent_load(self, db_manager, test_data_generator):
        """Test database performance under sustained concurrent load."""
        duration_seconds = 30.0
        target_ops_per_second = 50
        
        async def mixed_database_operation():
            async with db_manager.get_session() as session:
                operation_type = random.choice(["create_player", "query_player", "update_stats"])
                
                if operation_type == "create_player":
                    player_data = test_data_generator["player"]()
                    from backend.database.models import Player
                    player = Player(**player_data)
                    session.add(player)
                    await session.commit()
                    
                elif operation_type == "query_player":
                    await session.execute("SELECT COUNT(*) FROM players")
                    
                elif operation_type == "update_stats":
                    await session.execute(
                        "UPDATE player_stats SET last_updated = NOW() WHERE player_id = (SELECT id FROM players ORDER BY RANDOM() LIMIT 1)"
                    )
                    await session.commit()
        
        # Run stress test
        results = await ConcurrencyTestHelpers.stress_test_operation(
            mixed_database_operation,
            duration_seconds=duration_seconds,
            target_ops_per_second=target_ops_per_second
        )
        
        # Verify performance requirements
        assert results["success_rate"] >= 0.95, f"Success rate too low: {results['success_rate']:.2%}"
        assert results["avg_response_time"] <= 1.0, f"Average response time too high: {results['avg_response_time']:.3f}s"
        
        print(f"Stress test results:")
        print(f"  Duration: {results['duration']:.1f}s")
        print(f"  Total operations: {results['total_operations']}")
        print(f"  Ops/second: {results['ops_per_second']:.1f}")
        print(f"  Success rate: {results['success_rate']:.2%}")
        print(f"  Avg response time: {results['avg_response_time']:.3f}s")
