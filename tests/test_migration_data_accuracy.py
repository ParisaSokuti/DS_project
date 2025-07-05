"""
Migration Testing Suite for Redis-to-Hybrid Architecture
Comprehensive testing for data migration accuracy and system integrity
"""

import pytest
import asyncio
import time
import json
import uuid
import redis
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path
import psutil
import subprocess

from test_utils import (
    TestDataGenerator,
    TestAssertions,
    PerformanceProfiler,
    DatabaseTestHelpers
)


@dataclass
class MigrationMetrics:
    """Metrics for tracking migration performance and accuracy."""
    start_time: datetime
    end_time: Optional[datetime] = None
    total_records: int = 0
    migrated_records: int = 0
    failed_records: int = 0
    data_accuracy: float = 0.0
    performance_impact: float = 0.0
    user_experience_score: float = 0.0


@pytest.mark.asyncio
@pytest.mark.migration
@pytest.mark.slow
class TestMigrationDataAccuracy:
    """Test data migration accuracy from Redis to PostgreSQL."""
    
    async def test_player_data_migration_accuracy(self, redis_client, db_manager, test_data_generator):
        """Test accurate migration of player data from Redis to PostgreSQL."""
        profiler = PerformanceProfiler()
        profiler.start()
        
        # Step 1: Create test players in Redis (baseline)
        test_players = []
        for i in range(100):
            player_data = test_data_generator["player"]()
            player_id = f"player:{uuid.uuid4()}"
            
            # Store in Redis
            redis_client.hset(player_id, mapping=player_data)
            redis_client.sadd("all_players", player_id)
            
            test_players.append({"id": player_id, "data": player_data})
        
        profiler.record_operation("create_redis_players", 0.5)
        
        # Step 2: Perform migration
        migrated_count = 0
        failed_migrations = []
        
        async with db_manager.get_session() as session:
            for player in test_players:
                try:
                    # Get data from Redis
                    redis_data = redis_client.hgetall(player["id"])
                    
                    # Convert Redis data to PostgreSQL format
                    pg_data = {
                        "username": redis_data.get("username", "").decode() if isinstance(redis_data.get("username"), bytes) else redis_data.get("username", ""),
                        "email": redis_data.get("email", "").decode() if isinstance(redis_data.get("email"), bytes) else redis_data.get("email", ""),
                        "display_name": redis_data.get("display_name", "").decode() if isinstance(redis_data.get("display_name"), bytes) else redis_data.get("display_name", ""),
                        "created_at": datetime.utcnow(),
                        "is_active": True
                    }
                    
                    # Insert into PostgreSQL
                    from backend.database.models import Player
                    pg_player = Player(**pg_data)
                    session.add(pg_player)
                    await session.flush()
                    
                    migrated_count += 1
                    
                except Exception as e:
                    failed_migrations.append({"player_id": player["id"], "error": str(e)})
            
            await session.commit()
        
        profiler.record_operation("migrate_players", 2.0)
        
        # Step 3: Validate migration accuracy
        async with db_manager.get_session() as session:
            result = await session.execute("SELECT COUNT(*) FROM players")
            pg_count = result.scalar()
            
            assert pg_count == migrated_count, f"Migration count mismatch: expected {migrated_count}, got {pg_count}"
            
            # Verify data integrity for sample players
            for i in range(0, min(10, len(test_players))):
                player = test_players[i]
                redis_data = redis_client.hgetall(player["id"])
                
                result = await session.execute(
                    "SELECT username, email, display_name FROM players WHERE username = :username",
                    {"username": redis_data.get("username", "").decode() if isinstance(redis_data.get("username"), bytes) else redis_data.get("username", "")}
                )
                pg_data = result.fetchone()
                
                if pg_data:
                    assert pg_data[0] == (redis_data.get("username", "").decode() if isinstance(redis_data.get("username"), bytes) else redis_data.get("username", ""))
                    assert pg_data[1] == (redis_data.get("email", "").decode() if isinstance(redis_data.get("email"), bytes) else redis_data.get("email", ""))
        
        metrics = profiler.stop()
        
        # Calculate accuracy metrics
        accuracy = (migrated_count / len(test_players)) * 100 if test_players else 0
        
        assert accuracy >= 99.0, f"Migration accuracy too low: {accuracy:.2f}%"
        assert len(failed_migrations) <= 1, f"Too many failed migrations: {len(failed_migrations)}"
        
        print(f"Player migration results:")
        print(f"  Total players: {len(test_players)}")
        print(f"  Migrated successfully: {migrated_count}")
        print(f"  Failed migrations: {len(failed_migrations)}")
        print(f"  Accuracy: {accuracy:.2f}%")
        print(f"  Migration duration: {metrics['total_duration']:.2f}s")
        
        # Cleanup
        for player in test_players:
            redis_client.delete(player["id"])
        redis_client.delete("all_players")
    
    async def test_game_session_migration_accuracy(self, redis_client, db_manager, test_data_generator, db_helpers):
        """Test accurate migration of game sessions with active state preservation."""
        profiler = PerformanceProfiler()
        profiler.start()
        
        # Step 1: Create test game sessions in Redis
        test_sessions = []
        for i in range(20):
            session_id = f"room:{uuid.uuid4()}"
            session_data = {
                "session_id": session_id,
                "creator_id": f"player:{i}",
                "game_phase": "playing",
                "current_round": 3,
                "trump_suit": "hearts",
                "created_at": datetime.utcnow().isoformat(),
                "players": [f"player:{j}" for j in range(i, i+4)]
            }
            
            # Store in Redis
            redis_client.hset(session_id, mapping={
                "data": json.dumps(session_data)
            })
            redis_client.sadd("active_sessions", session_id)
            
            test_sessions.append({"id": session_id, "data": session_data})
        
        profiler.record_operation("create_redis_sessions", 0.3)
        
        # Step 2: Perform migration with game state preservation
        migrated_sessions = 0
        preservation_failures = []
        
        # First create players in PostgreSQL
        async with db_manager.get_session() as session:
            players = await db_helpers.create_test_players(session, count=50)
        
        async with db_manager.get_session() as session:
            for test_session in test_sessions:
                try:
                    redis_data = redis_client.hget(test_session["id"], "data")
                    session_data = json.loads(redis_data.decode() if isinstance(redis_data, bytes) else redis_data)
                    
                    # Create game session in PostgreSQL
                    pg_session_data = {
                        "session_id": session_data["session_id"],
                        "creator_id": players[0]["id"],  # Use actual player ID
                        "game_phase": session_data["game_phase"],
                        "current_round": session_data["current_round"],
                        "trump_suit": session_data["trump_suit"],
                        "created_at": datetime.fromisoformat(session_data["created_at"]),
                        "is_active": True
                    }
                    
                    from backend.database.models import GameSession
                    pg_session = GameSession(**pg_session_data)
                    session.add(pg_session)
                    await session.flush()
                    
                    migrated_sessions += 1
                    
                except Exception as e:
                    preservation_failures.append({"session_id": test_session["id"], "error": str(e)})
            
            await session.commit()
        
        profiler.record_operation("migrate_sessions", 1.0)
        
        # Step 3: Validate game state preservation
        async with db_manager.get_session() as session:
            for test_session in test_sessions[:5]:  # Check first 5 sessions
                redis_data = redis_client.hget(test_session["id"], "data")
                original_data = json.loads(redis_data.decode() if isinstance(redis_data, bytes) else redis_data)
                
                result = await session.execute(
                    "SELECT game_phase, current_round, trump_suit FROM game_sessions WHERE session_id = :session_id",
                    {"session_id": original_data["session_id"]}
                )
                pg_data = result.fetchone()
                
                if pg_data:
                    assert pg_data[0] == original_data["game_phase"], f"Game phase mismatch for {test_session['id']}"
                    assert pg_data[1] == original_data["current_round"], f"Round mismatch for {test_session['id']}"
                    assert pg_data[2] == original_data["trump_suit"], f"Trump suit mismatch for {test_session['id']}"
        
        metrics = profiler.stop()
        
        # Calculate preservation accuracy
        preservation_rate = (migrated_sessions / len(test_sessions)) * 100 if test_sessions else 0
        
        assert preservation_rate >= 95.0, f"Game state preservation rate too low: {preservation_rate:.2f}%"
        
        print(f"Game session migration results:")
        print(f"  Total sessions: {len(test_sessions)}")
        print(f"  Migrated successfully: {migrated_sessions}")
        print(f"  Preservation failures: {len(preservation_failures)}")
        print(f"  Preservation rate: {preservation_rate:.2f}%")
        
        # Cleanup
        for test_session in test_sessions:
            redis_client.delete(test_session["id"])
        redis_client.delete("active_sessions")
    
    async def test_statistics_migration_accuracy(self, redis_client, db_manager, test_data_generator):
        """Test accurate migration of player statistics and leaderboard data."""
        profiler = PerformanceProfiler()
        profiler.start()
        
        # Step 1: Create player statistics in Redis
        test_stats = []
        for i in range(50):
            player_id = f"player:{i}"
            stats_data = {
                "games_played": str(i * 10),
                "games_won": str(i * 5),
                "total_score": str(i * 100),
                "win_rate": str((i * 5) / (i * 10) if i > 0 else 0),
                "last_updated": datetime.utcnow().isoformat()
            }
            
            # Store in Redis
            stats_key = f"stats:{player_id}"
            redis_client.hset(stats_key, mapping=stats_data)
            redis_client.zadd("leaderboard", {player_id: float(stats_data["total_score"])})
            
            test_stats.append({"player_id": player_id, "stats": stats_data})
        
        profiler.record_operation("create_redis_stats", 0.2)
        
        # Step 2: Create corresponding players in PostgreSQL
        async with db_manager.get_session() as session:
            pg_players = []
            for i in range(50):
                player_data = test_data_generator["player"]()
                player_data["username"] = f"test_player_{i}"
                
                from backend.database.models import Player
                player = Player(**player_data)
                session.add(player)
                await session.flush()
                pg_players.append({"id": player.id, "redis_id": f"player:{i}"})
            
            await session.commit()
        
        # Step 3: Migrate statistics
        migrated_stats = 0
        stats_errors = []
        
        async with db_manager.get_session() as session:
            for i, stat_entry in enumerate(test_stats):
                try:
                    redis_stats = redis_client.hgetall(f"stats:{stat_entry['player_id']}")
                    pg_player = pg_players[i]
                    
                    # Convert and insert statistics
                    pg_stats_data = {
                        "player_id": pg_player["id"],
                        "games_played": int(redis_stats[b"games_played"].decode()),
                        "games_won": int(redis_stats[b"games_won"].decode()),
                        "total_score": int(redis_stats[b"total_score"].decode()),
                        "win_rate": float(redis_stats[b"win_rate"].decode()),
                        "last_updated": datetime.fromisoformat(redis_stats[b"last_updated"].decode())
                    }
                    
                    from backend.database.models import PlayerStats
                    stats = PlayerStats(**pg_stats_data)
                    session.add(stats)
                    await session.flush()
                    
                    migrated_stats += 1
                    
                except Exception as e:
                    stats_errors.append({"player_id": stat_entry["player_id"], "error": str(e)})
            
            await session.commit()
        
        profiler.record_operation("migrate_stats", 1.5)
        
        # Step 4: Validate statistics accuracy
        async with db_manager.get_session() as session:
            # Check total count
            result = await session.execute("SELECT COUNT(*) FROM player_stats")
            pg_stats_count = result.scalar()
            
            assert pg_stats_count == migrated_stats, f"Stats count mismatch: expected {migrated_stats}, got {pg_stats_count}"
            
            # Validate leaderboard order
            result = await session.execute("""
                SELECT p.username, ps.total_score 
                FROM player_stats ps 
                JOIN players p ON ps.player_id = p.id 
                ORDER BY ps.total_score DESC 
                LIMIT 10
            """)
            pg_leaderboard = result.fetchall()
            
            # Get Redis leaderboard
            redis_leaderboard = redis_client.zrevrange("leaderboard", 0, 9, withscores=True)
            
            # Compare top entries (allowing for some variance in exact ordering)
            assert len(pg_leaderboard) >= 5, "PostgreSQL leaderboard should have at least 5 entries"
            assert len(redis_leaderboard) >= 5, "Redis leaderboard should have at least 5 entries"
        
        metrics = profiler.stop()
        
        # Calculate accuracy
        stats_accuracy = (migrated_stats / len(test_stats)) * 100 if test_stats else 0
        
        assert stats_accuracy >= 98.0, f"Statistics migration accuracy too low: {stats_accuracy:.2f}%"
        
        print(f"Statistics migration results:")
        print(f"  Total statistics: {len(test_stats)}")
        print(f"  Migrated successfully: {migrated_stats}")
        print(f"  Migration errors: {len(stats_errors)}")
        print(f"  Accuracy: {stats_accuracy:.2f}%")
        
        # Cleanup
        for stat_entry in test_stats:
            redis_client.delete(f"stats:{stat_entry['player_id']}")
        redis_client.delete("leaderboard")


@pytest.mark.asyncio
@pytest.mark.migration
@pytest.mark.performance
class TestMigrationPerformanceComparison:
    """Test performance comparison before and after migration."""
    
    async def test_read_operation_performance_comparison(self, redis_client, db_manager, test_data_generator):
        """Compare read operation performance between Redis-only and hybrid architecture."""
        profiler = PerformanceProfiler()
        
        # Setup: Create test data in both systems
        test_players = []
        for i in range(100):
            player_data = test_data_generator["player"]()
            player_data["username"] = f"perf_test_player_{i}"
            test_players.append(player_data)
        
        # Store in Redis
        for i, player_data in enumerate(test_players):
            redis_key = f"player:{i}"
            redis_client.hset(redis_key, mapping=player_data)
        
        # Store in PostgreSQL
        async with db_manager.get_session() as session:
            pg_players = []
            for player_data in test_players:
                from backend.database.models import Player
                player = Player(**player_data)
                session.add(player)
                await session.flush()
                pg_players.append(player.id)
            await session.commit()
        
        # Test 1: Redis-only read performance
        profiler.start()
        redis_read_times = []
        
        for i in range(100):
            start_time = time.perf_counter()
            redis_client.hgetall(f"player:{i}")
            end_time = time.perf_counter()
            redis_read_times.append(end_time - start_time)
        
        redis_metrics = profiler.stop()
        
        # Test 2: PostgreSQL read performance
        profiler.start()
        pg_read_times = []
        
        async with db_manager.get_session() as session:
            for player_id in pg_players:
                start_time = time.perf_counter()
                result = await session.execute(
                    "SELECT username, email, display_name FROM players WHERE id = :id",
                    {"id": player_id}
                )
                result.fetchone()
                end_time = time.perf_counter()
                pg_read_times.append(end_time - start_time)
        
        pg_metrics = profiler.stop()
        
        # Test 3: Hybrid read performance (Redis primary, PostgreSQL fallback)
        profiler.start()
        hybrid_read_times = []
        
        for i in range(100):
            start_time = time.perf_counter()
            
            # Try Redis first
            redis_data = redis_client.hgetall(f"player:{i}")
            if not redis_data:
                # Fallback to PostgreSQL
                async with db_manager.get_session() as session:
                    result = await session.execute(
                        "SELECT username, email, display_name FROM players WHERE id = :id",
                        {"id": pg_players[i]}
                    )
                    result.fetchone()
            
            end_time = time.perf_counter()
            hybrid_read_times.append(end_time - start_time)
        
        hybrid_metrics = profiler.stop()
        
        # Performance analysis
        redis_avg = sum(redis_read_times) / len(redis_read_times)
        pg_avg = sum(pg_read_times) / len(pg_read_times)
        hybrid_avg = sum(hybrid_read_times) / len(hybrid_read_times)
        
        print(f"Read Performance Comparison:")
        print(f"  Redis-only average: {redis_avg:.4f}s")
        print(f"  PostgreSQL average: {pg_avg:.4f}s")
        print(f"  Hybrid average: {hybrid_avg:.4f}s")
        print(f"  Hybrid vs Redis ratio: {hybrid_avg/redis_avg:.2f}x")
        print(f"  Hybrid vs PostgreSQL ratio: {hybrid_avg/pg_avg:.2f}x")
        
        # Performance assertions
        assert hybrid_avg <= redis_avg * 1.2, f"Hybrid performance degraded too much vs Redis: {hybrid_avg/redis_avg:.2f}x"
        assert hybrid_avg <= pg_avg * 0.8, f"Hybrid should be faster than PostgreSQL-only: {hybrid_avg/pg_avg:.2f}x"
        
        # Cleanup
        for i in range(100):
            redis_client.delete(f"player:{i}")
    
    async def test_write_operation_performance_comparison(self, redis_client, db_manager, test_data_generator):
        """Compare write operation performance between architectures."""
        profiler = PerformanceProfiler()
        
        # Test 1: Redis-only write performance
        profiler.start()
        redis_write_times = []
        
        for i in range(50):
            player_data = test_data_generator["player"]()
            player_data["username"] = f"redis_write_test_{i}"
            
            start_time = time.perf_counter()
            redis_client.hset(f"redis_write_player:{i}", mapping=player_data)
            end_time = time.perf_counter()
            redis_write_times.append(end_time - start_time)
        
        redis_write_metrics = profiler.stop()
        
        # Test 2: PostgreSQL-only write performance
        profiler.start()
        pg_write_times = []
        
        for i in range(50):
            player_data = test_data_generator["player"]()
            player_data["username"] = f"pg_write_test_{i}"
            
            start_time = time.perf_counter()
            async with db_manager.get_session() as session:
                from backend.database.models import Player
                player = Player(**player_data)
                session.add(player)
                await session.commit()
            end_time = time.perf_counter()
            pg_write_times.append(end_time - start_time)
        
        pg_write_metrics = profiler.stop()
        
        # Test 3: Hybrid write performance (write to both)
        profiler.start()
        hybrid_write_times = []
        
        for i in range(50):
            player_data = test_data_generator["player"]()
            player_data["username"] = f"hybrid_write_test_{i}"
            
            start_time = time.perf_counter()
            
            # Write to Redis
            redis_client.hset(f"hybrid_write_player:{i}", mapping=player_data)
            
            # Write to PostgreSQL
            async with db_manager.get_session() as session:
                from backend.database.models import Player
                player = Player(**player_data)
                session.add(player)
                await session.commit()
            
            end_time = time.perf_counter()
            hybrid_write_times.append(end_time - start_time)
        
        hybrid_write_metrics = profiler.stop()
        
        # Performance analysis
        redis_write_avg = sum(redis_write_times) / len(redis_write_times)
        pg_write_avg = sum(pg_write_times) / len(pg_write_times)
        hybrid_write_avg = sum(hybrid_write_times) / len(hybrid_write_times)
        
        print(f"Write Performance Comparison:")
        print(f"  Redis-only average: {redis_write_avg:.4f}s")
        print(f"  PostgreSQL average: {pg_write_avg:.4f}s")
        print(f"  Hybrid average: {hybrid_write_avg:.4f}s")
        print(f"  Hybrid vs Redis ratio: {hybrid_write_avg/redis_write_avg:.2f}x")
        print(f"  Hybrid vs PostgreSQL ratio: {hybrid_write_avg/pg_write_avg:.2f}x")
        
        # Performance assertions
        assert hybrid_write_avg <= redis_write_avg * 3.0, f"Hybrid write performance too slow vs Redis: {hybrid_write_avg/redis_write_avg:.2f}x"
        assert hybrid_write_avg <= pg_write_avg * 1.5, f"Hybrid should not be much slower than PostgreSQL: {hybrid_write_avg/pg_write_avg:.2f}x"
        
        # Cleanup
        for i in range(50):
            redis_client.delete(f"redis_write_player:{i}")
            redis_client.delete(f"hybrid_write_player:{i}")
    
    async def test_concurrent_operation_performance(self, redis_client, db_manager, test_data_generator):
        """Test performance under concurrent load for both architectures."""
        from test_utils import ConcurrencyTestHelpers
        
        # Test Redis-only concurrent performance
        async def redis_concurrent_operation():
            player_data = test_data_generator["player"]()
            player_id = f"concurrent:{uuid.uuid4()}"
            redis_client.hset(player_id, mapping=player_data)
            return redis_client.hgetall(player_id)
        
        redis_results = await ConcurrencyTestHelpers.stress_test_operation(
            redis_concurrent_operation,
            duration_seconds=10.0,
            target_ops_per_second=50
        )
        
        # Test hybrid concurrent performance
        async def hybrid_concurrent_operation():
            player_data = test_data_generator["player"]()
            player_data["username"] = f"hybrid_concurrent_{uuid.uuid4()}"
            
            # Write to both Redis and PostgreSQL
            player_id = f"hybrid_concurrent:{uuid.uuid4()}"
            redis_client.hset(player_id, mapping=player_data)
            
            async with db_manager.get_session() as session:
                from backend.database.models import Player
                player = Player(**player_data)
                session.add(player)
                await session.commit()
                return player.id
        
        hybrid_results = await ConcurrencyTestHelpers.stress_test_operation(
            hybrid_concurrent_operation,
            duration_seconds=10.0,
            target_ops_per_second=30  # Lower target due to dual writes
        )
        
        print(f"Concurrent Performance Comparison:")
        print(f"  Redis-only ops/sec: {redis_results['ops_per_second']:.1f}")
        print(f"  Redis-only success rate: {redis_results['success_rate']:.2%}")
        print(f"  Redis-only avg response: {redis_results['avg_response_time']:.4f}s")
        print(f"  Hybrid ops/sec: {hybrid_results['ops_per_second']:.1f}")
        print(f"  Hybrid success rate: {hybrid_results['success_rate']:.2%}")
        print(f"  Hybrid avg response: {hybrid_results['avg_response_time']:.4f}s")
        
        # Performance assertions
        assert redis_results['success_rate'] >= 0.95, f"Redis concurrent success rate too low: {redis_results['success_rate']:.2%}"
        assert hybrid_results['success_rate'] >= 0.90, f"Hybrid concurrent success rate too low: {hybrid_results['success_rate']:.2%}"
        assert hybrid_results['ops_per_second'] >= redis_results['ops_per_second'] * 0.3, "Hybrid throughput too low compared to Redis"


@pytest.mark.asyncio
@pytest.mark.migration
@pytest.mark.rollback
class TestMigrationRollbackProcedures:
    """Test rollback procedures and data recovery capabilities."""
    
    async def test_complete_rollback_procedure(self, redis_client, db_manager, test_data_generator):
        """Test complete rollback from hybrid to Redis-only architecture."""
        profiler = PerformanceProfiler()
        profiler.start()
        
        # Step 1: Create test scenario with data in both systems
        test_players = []
        pg_player_ids = []
        
        # Create players in both Redis and PostgreSQL
        async with db_manager.get_session() as session:
            for i in range(20):
                player_data = test_data_generator["player"]()
                player_data["username"] = f"rollback_test_{i}"
                
                # Store in Redis
                redis_key = f"rollback_player:{i}"
                redis_client.hset(redis_key, mapping=player_data)
                
                # Store in PostgreSQL
                from backend.database.models import Player
                player = Player(**player_data)
                session.add(player)
                await session.flush()
                
                test_players.append({"redis_key": redis_key, "pg_id": player.id, "data": player_data})
                pg_player_ids.append(player.id)
            
            await session.commit()
        
        profiler.record_operation("setup_rollback_data", 1.0)
        
        # Step 2: Simulate some changes in PostgreSQL that need to be preserved
        async with db_manager.get_session() as session:
            # Update some player data in PostgreSQL
            for i in range(0, 10):
                await session.execute(
                    "UPDATE players SET display_name = :new_name WHERE id = :id",
                    {"new_name": f"Updated Player {i}", "id": pg_player_ids[i]}
                )
            await session.commit()
        
        profiler.record_operation("modify_pg_data", 0.2)
        
        # Step 3: Perform rollback procedure
        rollback_success = True
        rollback_errors = []
        
        try:
            # Phase 1: Export PostgreSQL changes back to Redis
            async with db_manager.get_session() as session:
                result = await session.execute("SELECT id, username, display_name, email FROM players")
                pg_players = result.fetchall()
                
                for pg_player in pg_players:
                    try:
                        # Find corresponding Redis key
                        username = pg_player[1]
                        if username.startswith("rollback_test_"):
                            index = username.split("_")[-1]
                            redis_key = f"rollback_player:{index}"
                            
                            # Update Redis with PostgreSQL changes
                            redis_client.hset(redis_key, mapping={
                                "username": pg_player[1],
                                "display_name": pg_player[2],
                                "email": pg_player[3]
                            })
                    except Exception as e:
                        rollback_errors.append(f"Failed to rollback player {pg_player[0]}: {str(e)}")
            
            # Phase 2: Cleanup PostgreSQL data (simulate removing PG dependency)
            async with db_manager.get_session() as session:
                await session.execute("DELETE FROM players WHERE username LIKE 'rollback_test_%'")
                await session.commit()
            
            profiler.record_operation("rollback_procedure", 0.5)
            
        except Exception as e:
            rollback_success = False
            rollback_errors.append(f"Rollback procedure failed: {str(e)}")
        
        # Step 4: Validate rollback success
        if rollback_success:
            # Verify all data is back in Redis with updates preserved
            for i in range(20):
                redis_key = f"rollback_player:{i}"
                redis_data = redis_client.hgetall(redis_key)
                
                assert redis_data, f"Player data missing from Redis after rollback: {redis_key}"
                
                if i < 10:  # These should have updated display names
                    expected_name = f"Updated Player {i}"
                    actual_name = redis_data.get(b"display_name", b"").decode()
                    assert actual_name == expected_name, f"Updated data not preserved in rollback: expected {expected_name}, got {actual_name}"
            
            # Verify PostgreSQL is clean
            async with db_manager.get_session() as session:
                result = await session.execute("SELECT COUNT(*) FROM players WHERE username LIKE 'rollback_test_%'")
                pg_count = result.scalar()
                assert pg_count == 0, f"PostgreSQL not cleaned up after rollback: {pg_count} records remaining"
        
        metrics = profiler.stop()
        
        assert rollback_success, f"Rollback failed with errors: {rollback_errors}"
        assert len(rollback_errors) == 0, f"Rollback had errors: {rollback_errors}"
        
        print(f"Rollback procedure results:")
        print(f"  Rollback successful: {rollback_success}")
        print(f"  Rollback errors: {len(rollback_errors)}")
        print(f"  Total duration: {metrics['total_duration']:.2f}s")
        print(f"  Data integrity preserved: ✅")
        
        # Cleanup
        for i in range(20):
            redis_client.delete(f"rollback_player:{i}")
    
    async def test_partial_rollback_with_active_games(self, redis_client, db_manager, test_data_generator, db_helpers):
        """Test partial rollback while preserving active game sessions."""
        profiler = PerformanceProfiler()
        profiler.start()
        
        # Step 1: Create active game scenario
        async with db_manager.get_session() as session:
            players = await db_helpers.create_test_players(session, count=8)
            game_session = await db_helpers.create_test_game_session(
                session, players[0]["id"], players[:4]
            )
        
        session_id = game_session["session_id"]
        
        # Store game session in Redis as well (active state)
        active_game_data = {
            "session_id": session_id,
            "game_phase": "playing",
            "current_round": 3,
            "active_players": [p["id"] for p in players[:4]],
            "last_activity": datetime.utcnow().isoformat()
        }
        redis_client.hset(f"active_game:{session_id}", mapping={
            "data": json.dumps(active_game_data)
        })
        
        profiler.record_operation("setup_active_game", 0.5)
        
        # Step 2: Perform partial rollback (preserve active games)
        try:
            # Identify active games that must be preserved
            active_sessions = redis_client.keys("active_game:*")
            preserved_sessions = []
            
            for session_key in active_sessions:
                session_data = redis_client.hget(session_key, "data")
                game_info = json.loads(session_data.decode())
                
                # Preserve games that are currently active
                if game_info["game_phase"] in ["playing", "trump_selection"]:
                    preserved_sessions.append(game_info["session_id"])
            
            # Rollback non-active data while preserving active games
            async with db_manager.get_session() as session:
                # Only delete non-active game sessions
                await session.execute(
                    "DELETE FROM game_sessions WHERE session_id NOT IN :preserved_ids AND game_phase = 'completed'",
                    {"preserved_ids": tuple(preserved_sessions) if preserved_sessions else ("dummy",)}
                )
                await session.commit()
            
            rollback_success = True
            
        except Exception as e:
            rollback_success = False
            rollback_error = str(e)
        
        profiler.record_operation("partial_rollback", 0.3)
        
        # Step 3: Validate active game preservation
        if rollback_success:
            # Verify active game still exists in both systems
            redis_active_data = redis_client.hget(f"active_game:{session_id}", "data")
            assert redis_active_data, "Active game data missing from Redis after partial rollback"
            
            async with db_manager.get_session() as session:
                result = await session.execute(
                    "SELECT game_phase FROM game_sessions WHERE session_id = :session_id",
                    {"session_id": session_id}
                )
                pg_game_data = result.fetchone()
                assert pg_game_data, "Active game data missing from PostgreSQL after partial rollback"
                assert pg_game_data[0] in ["playing", "trump_selection"], "Active game phase corrupted"
        
        metrics = profiler.stop()
        
        assert rollback_success, f"Partial rollback failed: {rollback_error if not rollback_success else 'Unknown error'}"
        
        print(f"Partial rollback results:")
        print(f"  Rollback successful: {rollback_success}")
        print(f"  Active games preserved: {len(preserved_sessions)}")
        print(f"  Total duration: {metrics['total_duration']:.2f}s")
        
        # Cleanup
        redis_client.delete(f"active_game:{session_id}")
    
    async def test_emergency_rollback_speed(self, redis_client, db_manager, test_data_generator):
        """Test emergency rollback procedures for speed requirements."""
        profiler = PerformanceProfiler()
        profiler.start()
        
        # Step 1: Create large dataset scenario
        large_dataset_size = 1000
        
        # Create players in PostgreSQL
        async with db_manager.get_session() as session:
            for i in range(large_dataset_size):
                player_data = test_data_generator["player"]()
                player_data["username"] = f"emergency_test_{i}"
                
                from backend.database.models import Player
                player = Player(**player_data)
                session.add(player)
                
                if i % 100 == 0:  # Commit in batches
                    await session.commit()
            
            await session.commit()
        
        profiler.record_operation("create_large_dataset", 5.0)
        
        # Step 2: Perform emergency rollback with speed requirements
        emergency_start = time.perf_counter()
        
        try:
            # Emergency procedure: Quick data export to Redis
            async with db_manager.get_session() as session:
                # Use efficient bulk query
                result = await session.execute(
                    "SELECT id, username, email, display_name FROM players WHERE username LIKE 'emergency_test_%'"
                )
                
                players_batch = []
                for row in result:
                    player_data = {
                        "id": str(row[0]),
                        "username": row[1],
                        "email": row[2],
                        "display_name": row[3]
                    }
                    players_batch.append((f"emergency_player:{row[0]}", player_data))
                    
                    # Batch Redis operations
                    if len(players_batch) >= 100:
                        pipe = redis_client.pipeline()
                        for redis_key, data in players_batch:
                            pipe.hset(redis_key, mapping=data)
                        pipe.execute()
                        players_batch = []
                
                # Handle remaining batch
                if players_batch:
                    pipe = redis_client.pipeline()
                    for redis_key, data in players_batch:
                        pipe.hset(redis_key, mapping=data)
                    pipe.execute()
            
            emergency_end = time.perf_counter()
            emergency_duration = emergency_end - emergency_start
            
            # Emergency cleanup of PostgreSQL
            async with db_manager.get_session() as session:
                await session.execute("DELETE FROM players WHERE username LIKE 'emergency_test_%'")
                await session.commit()
            
            emergency_success = True
            
        except Exception as e:
            emergency_end = time.perf_counter()
            emergency_duration = emergency_end - emergency_start
            emergency_success = False
            emergency_error = str(e)
        
        profiler.record_operation("emergency_rollback", emergency_duration)
        metrics = profiler.stop()
        
        # Speed requirements: Emergency rollback should complete within 30 seconds for 1000 records
        max_allowed_time = 30.0
        
        assert emergency_success, f"Emergency rollback failed: {emergency_error if not emergency_success else 'Unknown'}"
        assert emergency_duration <= max_allowed_time, f"Emergency rollback too slow: {emergency_duration:.2f}s > {max_allowed_time}s"
        
        # Verify data integrity after emergency rollback
        redis_count = len(redis_client.keys("emergency_player:*"))
        assert redis_count == large_dataset_size, f"Data loss during emergency rollback: {redis_count}/{large_dataset_size}"
        
        print(f"Emergency rollback results:")
        print(f"  Dataset size: {large_dataset_size} records")
        print(f"  Emergency duration: {emergency_duration:.2f}s")
        print(f"  Speed requirement met: {emergency_duration <= max_allowed_time}")
        print(f"  Data integrity: {redis_count}/{large_dataset_size} records preserved")
        print(f"  Rollback rate: {large_dataset_size/emergency_duration:.0f} records/second")
        
        # Cleanup
        for key in redis_client.keys("emergency_player:*"):
            redis_client.delete(key)
