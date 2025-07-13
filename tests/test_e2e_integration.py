"""
End-to-end integration tests for the complete Hokm game flow with PostgreSQL backend.
Tests full game scenarios from player creation to game completion.
"""

import pytest
import asyncio
import json
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

from test_utils import (
    TestDataGenerator,
    TestAssertions,
    DatabaseTestHelpers,
    PerformanceProfiler
)


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.integration
@pytest.mark.slow
class TestEndToEndGameFlow:
    """End-to-end tests for complete game scenarios."""
    
    async def test_complete_4_player_game_flow(self, db_manager, test_data_generator, db_helpers):
        """Test complete 4-player game from start to finish."""
        profiler = PerformanceProfiler()
        profiler.start()
        
        # Step 1: Create 4 players
        async with db_manager.get_session() as session:
            players = await db_helpers.create_test_players(session, count=4)
        
        profiler.record_operation("create_players", 0.1)
        
        # Step 2: Create game session
        async with db_manager.get_session() as session:
            game_session = await db_helpers.create_test_game_session(
                session, players[0]["id"], players
            )
        
        session_id = game_session["session_id"]
        profiler.record_operation("create_game_session", 0.1)
        
        # Step 3: All players join the game
        async with db_manager.get_session() as session:
            for player in players[1:]:
                await session.execute(
                    "INSERT INTO game_session_players (session_id, player_id, joined_at) VALUES (:session_id, :player_id, NOW())",
                    {"session_id": session_id, "player_id": player["id"]}
                )
            await session.commit()
        
        profiler.record_operation("players_join", 0.1)
        
        # Step 4: Start game (select hakem and trump)
        async with db_manager.get_session() as session:
            await session.execute(
                "UPDATE game_sessions SET game_phase = 'trump_selection', hakem_id = :hakem_id WHERE session_id = :session_id",
                {"session_id": session_id, "hakem_id": players[0]["id"]}
            )
            await session.commit()
        
        profiler.record_operation("trump_selection", 0.05)
        
        # Step 5: Hakem selects trump suit
        trump_suit = "hearts"
        async with db_manager.get_session() as session:
            await session.execute(
                "UPDATE game_sessions SET trump_suit = :trump_suit, game_phase = 'playing' WHERE session_id = :session_id",
                {"session_id": session_id, "trump_suit": trump_suit}
            )
            await session.commit()
        
        profiler.record_operation("set_trump", 0.05)
        
        # Step 6: Play multiple rounds (simulate 7 rounds)
        for round_num in range(1, 8):
            async with db_manager.get_session() as session:
                # Update current round
                await session.execute(
                    "UPDATE game_sessions SET current_round = :round_num WHERE session_id = :session_id",
                    {"session_id": session_id, "round_num": round_num}
                )
                
                # Each player plays a card
                for turn_order, player in enumerate(players, 1):
                    move_data = test_data_generator["game_move"](session_id, player["id"], round_num)
                    move_data["turn_order"] = turn_order
                    
                    from backend.database.models import GameMove
                    move = GameMove(**move_data)
                    session.add(move)
                
                await session.commit()
            
            profiler.record_operation(f"round_{round_num}", 0.2)
        
        # Step 7: Complete the game
        winner_id = players[0]["id"]  # Assume player 1 wins
        async with db_manager.get_session() as session:
            await session.execute(
                "UPDATE game_sessions SET game_phase = 'completed', winner_id = :winner_id, completed_at = NOW() WHERE session_id = :session_id",
                {"session_id": session_id, "winner_id": winner_id}
            )
            await session.commit()
        
        profiler.record_operation("complete_game", 0.1)
        
        # Step 8: Update player statistics
        async with db_manager.get_session() as session:
            for player in players:
                is_winner = player["id"] == winner_id
                await session.execute("""
                    INSERT INTO player_stats (player_id, games_played, games_won, total_score, last_updated)
                    VALUES (:player_id, 1, :games_won, :score, NOW())
                    ON CONFLICT (player_id)
                    DO UPDATE SET 
                        games_played = player_stats.games_played + 1,
                        games_won = player_stats.games_won + :games_won,
                        total_score = player_stats.total_score + :score,
                        last_updated = NOW()
                """, {
                    "player_id": player["id"],
                    "games_won": 1 if is_winner else 0,
                    "score": 100 if is_winner else 25
                })
            await session.commit()
        
        profiler.record_operation("update_stats", 0.1)
        
        # Step 9: Verify final game state
        async with db_manager.get_session() as session:
            # Check game completion
            result = await session.execute(
                "SELECT game_phase, winner_id, completed_at FROM game_sessions WHERE session_id = :session_id",
                {"session_id": session_id}
            )
            game_state = result.fetchone()
            
            assert game_state[0] == "completed", f"Game should be completed, but is {game_state[0]}"
            assert game_state[1] == winner_id, f"Winner should be {winner_id}, but is {game_state[1]}"
            assert game_state[2] is not None, "Completion timestamp should be set"
            
            # Check move count (should be 28 moves: 7 rounds × 4 players)
            result = await session.execute(
                "SELECT COUNT(*) FROM game_moves WHERE session_id = :session_id",
                {"session_id": session_id}
            )
            move_count = result.scalar()
            assert move_count == 28, f"Expected 28 moves, but got {move_count}"
            
            # Check player statistics were updated
            result = await session.execute(
                "SELECT player_id, games_played, games_won FROM player_stats WHERE player_id = ANY(:player_ids)",
                {"player_ids": [p["id"] for p in players]}
            )
            stats = result.fetchall()
            
            assert len(stats) == 4, f"Expected stats for 4 players, got {len(stats)}"
            
            for player_id, games_played, games_won in stats:
                assert games_played >= 1, f"Player {player_id} should have at least 1 game played"
                if player_id == winner_id:
                    assert games_won >= 1, f"Winner {player_id} should have at least 1 game won"
        
        metrics = profiler.stop()
        
        # Performance assertions
        assert metrics["total_duration"] <= 5.0, f"Game flow too slow: {metrics['total_duration']:.2f}s"
        
        print(f"\nComplete game flow test results:")
        print(f"  Total duration: {metrics['total_duration']:.2f}s")
        print(f"  Total operations: {metrics['total_operations']}")
        print(f"  Average operation time: {metrics['avg_operation_time']:.3f}s")
    
    async def test_player_reconnection_scenario(self, db_manager, test_data_generator, db_helpers):
        """Test player reconnection during an active game."""
        # Create game in progress
        async with db_manager.get_session() as session:
            players = await db_helpers.create_test_players(session, count=4)
            game_session = await db_helpers.create_test_game_session(
                session, players[0]["id"], players
            )
        
        session_id = game_session["session_id"]
        
        # Simulate game in progress (round 3)
        async with db_manager.get_session() as session:
            await session.execute(
                "UPDATE game_sessions SET game_phase = 'playing', current_round = 3, trump_suit = 'spades' WHERE session_id = :session_id",
                {"session_id": session_id}
            )
            
            # Add some moves to previous rounds
            for round_num in range(1, 3):
                for turn_order, player in enumerate(players, 1):
                    move_data = test_data_generator["game_move"](session_id, player["id"], round_num)
                    move_data["turn_order"] = turn_order
                    
                    from backend.database.models import GameMove
                    move = GameMove(**move_data)
                    session.add(move)
            
            await session.commit()
        
        # Simulate player disconnection and reconnection
        disconnected_player = players[1]
        
        async with db_manager.get_session() as session:
            # Mark player as disconnected
            await session.execute(
                "UPDATE game_session_players SET is_connected = false, last_seen = NOW() - INTERVAL '5 minutes' WHERE session_id = :session_id AND player_id = :player_id",
                {"session_id": session_id, "player_id": disconnected_player["id"]}
            )
            await session.commit()
        
        # Player reconnects - should be able to get game state
        async with db_manager.get_session() as session:
            # Get current game state for reconnecting player
            result = await session.execute("""
                SELECT 
                    gs.game_phase,
                    gs.current_round,
                    gs.trump_suit,
                    gs.hakem_id,
                    COUNT(gm.id) as moves_played
                FROM game_sessions gs
                LEFT JOIN game_moves gm ON gs.session_id = gm.session_id
                WHERE gs.session_id = :session_id
                GROUP BY gs.session_id, gs.game_phase, gs.current_round, gs.trump_suit, gs.hakem_id
            """, {"session_id": session_id})
            
            game_state = result.fetchone()
            
            assert game_state is not None, "Could not retrieve game state for reconnection"
            assert game_state[0] == "playing", "Game should be in playing phase"
            assert game_state[1] == 3, "Should be in round 3"
            assert game_state[2] == "spades", "Trump suit should be spades"
            assert game_state[4] == 8, "Should have 8 moves (2 complete rounds)"
            
            # Mark player as reconnected
            await session.execute(
                "UPDATE game_session_players SET is_connected = true, last_seen = NOW() WHERE session_id = :session_id AND player_id = :player_id",
                {"session_id": session_id, "player_id": disconnected_player["id"]}
            )
            await session.commit()
        
        # Player should be able to continue playing
        async with db_manager.get_session() as session:
            move_data = test_data_generator["game_move"](session_id, disconnected_player["id"], 3)
            move_data["turn_order"] = 2
            
            from backend.database.models import GameMove
            move = GameMove(**move_data)
            session.add(move)
            await session.commit()
        
        print("Player reconnection scenario completed successfully")
    
    async def test_concurrent_game_sessions(self, db_manager, test_data_generator, db_helpers):
        """Test multiple concurrent game sessions."""
        num_concurrent_games = 5
        players_per_game = 4
        
        # Create players for all games
        total_players_needed = num_concurrent_games * players_per_game
        async with db_manager.get_session() as session:
            all_players = await db_helpers.create_test_players(session, count=total_players_needed)
        
        # Create concurrent game sessions
        game_sessions = []
        
        async def create_and_run_game(game_index: int):
            start_player_index = game_index * players_per_game
            game_players = all_players[start_player_index:start_player_index + players_per_game]
            
            # Create game session
            async with db_manager.get_session() as session:
                game_session = await db_helpers.create_test_game_session(
                    session, game_players[0]["id"], game_players
                )
            
            session_id = game_session["session_id"]
            
            # Play a few rounds
            async with db_manager.get_session() as session:
                await session.execute(
                    "UPDATE game_sessions SET game_phase = 'playing', trump_suit = 'hearts' WHERE session_id = :session_id",
                    {"session_id": session_id}
                )
                
                # Play 3 rounds
                for round_num in range(1, 4):
                    await session.execute(
                        "UPDATE game_sessions SET current_round = :round_num WHERE session_id = :session_id",
                        {"session_id": session_id, "round_num": round_num}
                    )
                    
                    for turn_order, player in enumerate(game_players, 1):
                        move_data = test_data_generator["game_move"](session_id, player["id"], round_num)
                        move_data["turn_order"] = turn_order
                        
                        from backend.database.models import GameMove
                        move = GameMove(**move_data)
                        session.add(move)
                
                await session.commit()
            
            return session_id
        
        # Run games concurrently
        tasks = [create_and_run_game(i) for i in range(num_concurrent_games)]
        completed_sessions = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Verify all games completed successfully
        successful_sessions = [s for s in completed_sessions if not isinstance(s, Exception)]
        assert len(successful_sessions) == num_concurrent_games, f"Only {len(successful_sessions)}/{num_concurrent_games} games completed successfully"
        
        # Verify game states
        async with db_manager.get_session() as session:
            for session_id in successful_sessions:
                result = await session.execute(
                    "SELECT current_round, COUNT(DISTINCT gm.id) as move_count FROM game_sessions gs LEFT JOIN game_moves gm ON gs.session_id = gm.session_id WHERE gs.session_id = :session_id GROUP BY gs.current_round",
                    {"session_id": session_id}
                )
                game_info = result.fetchone()
                
                assert game_info is not None, f"Game {session_id} not found"
                assert game_info[0] == 3, f"Game {session_id} should be in round 3"
                assert game_info[1] == 12, f"Game {session_id} should have 12 moves (3 rounds × 4 players)"
        
        print(f"Successfully ran {num_concurrent_games} concurrent games")
    
    async def test_game_timeout_and_cleanup(self, db_manager, test_data_generator, db_helpers):
        """Test game timeout handling and cleanup procedures."""
        # Create a game that will be considered "stale"
        async with db_manager.get_session() as session:
            players = await db_helpers.create_test_players(session, count=4)
            game_session = await db_helpers.create_test_game_session(
                session, players[0]["id"], players
            )
        
        session_id = game_session["session_id"]
        
        # Simulate old game by setting created_at to past
        async with db_manager.get_session() as session:
            await session.execute(
                "UPDATE game_sessions SET created_at = NOW() - INTERVAL '2 hours', last_activity = NOW() - INTERVAL '2 hours' WHERE session_id = :session_id",
                {"session_id": session_id}
            )
            await session.commit()
        
        # Simulate cleanup process
        async with db_manager.get_session() as session:
            # Find stale games (older than 1 hour with no activity)
            stale_games_result = await session.execute("""
                SELECT session_id, created_at, last_activity
                FROM game_sessions
                WHERE game_phase NOT IN ('completed', 'cancelled')
                AND (last_activity < NOW() - INTERVAL '1 hour' OR (last_activity IS NULL AND created_at < NOW() - INTERVAL '1 hour'))
            """)
            
            stale_games = stale_games_result.fetchall()
            assert len(stale_games) >= 1, "Should find at least one stale game"
            
            # Mark stale games as cancelled
            for game in stale_games:
                await session.execute(
                    "UPDATE game_sessions SET game_phase = 'cancelled', completed_at = NOW() WHERE session_id = :session_id",
                    {"session_id": game[0]}
                )
            
            await session.commit()
        
        # Verify cleanup worked
        async with db_manager.get_session() as session:
            result = await session.execute(
                "SELECT game_phase FROM game_sessions WHERE session_id = :session_id",
                {"session_id": session_id}
            )
            final_phase = result.scalar()
            assert final_phase == "cancelled", f"Game should be cancelled, but is {final_phase}"
        
        print("Game timeout and cleanup test completed successfully")
    
    async def test_database_consistency_after_errors(self, db_manager, test_data_generator, db_helpers):
        """Test database consistency after various error scenarios."""
        # Create test data
        async with db_manager.get_session() as session:
            players = await db_helpers.create_test_players(session, count=4)
            game_session = await db_helpers.create_test_game_session(
                session, players[0]["id"], players
            )
        
        session_id = game_session["session_id"]
        
        # Test 1: Simulate failed transaction during game move
        try:
            async with db_manager.get_session() as session:
                trans = await session.begin()
                
                # Add a move
                move_data = test_data_generator["game_move"](session_id, players[0]["id"], 1)
                from backend.database.models import GameMove
                move = GameMove(**move_data)
                session.add(move)
                
                # Simulate error and rollback
                raise Exception("Simulated error")
                
        except Exception:
            # Transaction should be rolled back automatically
            pass
        
        # Verify no partial data was saved
        async with db_manager.get_session() as session:
            result = await session.execute(
                "SELECT COUNT(*) FROM game_moves WHERE session_id = :session_id",
                {"session_id": session_id}
            )
            move_count = result.scalar()
            assert move_count == 0, "No moves should be saved after failed transaction"
        
        # Test 2: Successful transaction after error
        async with db_manager.get_session() as session:
            move_data = test_data_generator["game_move"](session_id, players[0]["id"], 1)
            from backend.database.models import GameMove
            move = GameMove(**move_data)
            session.add(move)
            await session.commit()
        
        # Verify successful transaction worked
        async with db_manager.get_session() as session:
            result = await session.execute(
                "SELECT COUNT(*) FROM game_moves WHERE session_id = :session_id",
                {"session_id": session_id}
            )
            move_count = result.scalar()
            assert move_count == 1, "One move should be saved after successful transaction"
        
        print("Database consistency after errors test completed successfully")


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.analytics
class TestAnalyticsAndReporting:
    """Test analytics and reporting features."""
    
    async def test_player_statistics_aggregation(self, db_manager, test_data_generator, db_helpers):
        """Test aggregation of player statistics across multiple games."""
        # Create players and multiple completed games
        async with db_manager.get_session() as session:
            players = await db_helpers.create_test_players(session, count=6)
        
        # Simulate 3 completed games with different winners
        game_results = [
            {"winner": players[0]["id"], "players": players[:4]},
            {"winner": players[1]["id"], "players": players[1:5]},
            {"winner": players[0]["id"], "players": players[2:6]}
        ]
        
        for i, game_result in enumerate(game_results):
            game_players = game_result["players"]
            winner_id = game_result["winner"]
            
            async with db_manager.get_session() as session:
                game_session = await db_helpers.create_test_game_session(
                    session, game_players[0]["id"], game_players
                )
                
                session_id = game_session["session_id"]
                
                # Complete the game
                await session.execute(
                    "UPDATE game_sessions SET game_phase = 'completed', winner_id = :winner_id, completed_at = NOW() WHERE session_id = :session_id",
                    {"session_id": session_id, "winner_id": winner_id}
                )
                
                # Update player statistics
                for player in game_players:
                    is_winner = player["id"] == winner_id
                    await session.execute("""
                        INSERT INTO player_stats (player_id, games_played, games_won, total_score, last_updated)
                        VALUES (:player_id, 1, :games_won, :score, NOW())
                        ON CONFLICT (player_id)
                        DO UPDATE SET 
                            games_played = player_stats.games_played + 1,
                            games_won = player_stats.games_won + :games_won,
                            total_score = player_stats.total_score + :score,
                            last_updated = NOW()
                    """, {
                        "player_id": player["id"],
                        "games_won": 1 if is_winner else 0,
                        "score": 100 if is_winner else 25
                    })
                
                await session.commit()
        
        # Test analytics queries
        async with db_manager.get_session() as session:
            # Top players by win rate
            leaderboard_result = await session.execute("""
                SELECT 
                    p.username,
                    ps.games_played,
                    ps.games_won,
                    CASE 
                        WHEN ps.games_played > 0 THEN (ps.games_won::float / ps.games_played::float) * 100
                        ELSE 0
                    END as win_rate,
                    ps.total_score
                FROM players p
                JOIN player_stats ps ON p.id = ps.player_id
                WHERE ps.games_played >= 2
                ORDER BY win_rate DESC, ps.total_score DESC
                LIMIT 5
            """)
            
            leaderboard = leaderboard_result.fetchall()
            assert len(leaderboard) > 0, "Should have leaderboard entries"
            
            # Verify top player statistics
            top_player = leaderboard[0]
            assert top_player[1] >= 2, "Top player should have played at least 2 games"
            assert top_player[2] >= 1, "Top player should have won at least 1 game"
            assert top_player[3] > 0, "Top player should have positive win rate"
            
            # Game activity statistics
            activity_result = await session.execute("""
                SELECT 
                    DATE(created_at) as game_date,
                    COUNT(*) as games_created,
                    COUNT(CASE WHEN game_phase = 'completed' THEN 1 END) as games_completed
                FROM game_sessions
                WHERE created_at >= CURRENT_DATE - INTERVAL '7 days'
                GROUP BY DATE(created_at)
                ORDER BY game_date DESC
            """)
            
            activity_stats = activity_result.fetchall()
            assert len(activity_stats) > 0, "Should have activity statistics"
        
        print(f"Analytics test completed - {len(leaderboard)} players on leaderboard")
    
    async def test_performance_metrics_collection(self, db_manager, test_data_generator):
        """Test collection of performance metrics."""
        profiler = PerformanceProfiler()
        profiler.start()
        
        # Simulate various database operations and measure performance
        operations_data = []
        
        for i in range(10):
            # Measure player creation
            start_time = asyncio.get_event_loop().time()
            async with db_manager.get_session() as session:
                player_data = test_data_generator["player"]()
                from backend.database.models import Player
                player = Player(**player_data)
                session.add(player)
                await session.commit()
            end_time = asyncio.get_event_loop().time()
            
            operations_data.append({
                "operation": "create_player",
                "duration": end_time - start_time,
                "timestamp": end_time
            })
            
            profiler.record_operation("create_player", end_time - start_time)
        
        metrics = profiler.stop()
        
        # Analyze performance metrics
        create_player_ops = [op for op in operations_data if op["operation"] == "create_player"]
        avg_create_time = sum(op["duration"] for op in create_player_ops) / len(create_player_ops)
        
        assert avg_create_time <= 0.5, f"Player creation too slow: {avg_create_time:.3f}s average"
        assert metrics["avg_operation_time"] <= 0.5, f"Overall operations too slow: {metrics['avg_operation_time']:.3f}s average"
        
        print(f"Performance metrics: avg_create_time={avg_create_time:.3f}s, total_ops={metrics['total_operations']}")
        
        # Store performance metrics in database for historical tracking
        async with db_manager.get_session() as session:
            await session.execute("""
                INSERT INTO performance_metrics (
                    metric_name, 
                    metric_value, 
                    measurement_timestamp,
                    metadata
                ) VALUES (
                    'avg_player_creation_time',
                    :avg_time,
                    NOW(),
                    :metadata
                )
            """, {
                "avg_time": avg_create_time,
                "metadata": json.dumps({"sample_size": len(create_player_ops), "test_run": True})
            })
            await session.commit()
        
        print("Performance metrics stored successfully")
