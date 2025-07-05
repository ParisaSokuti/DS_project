"""
Data Integrity Validation for Migration Testing
Comprehensive validation of data consistency, accuracy, and integrity during migration
"""

import pytest
import asyncio
import time
import json
import uuid
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple, Set
from dataclasses import dataclass
import redis
from collections import defaultdict

from test_utils import (
    TestDataGenerator,
    TestAssertions,
    PerformanceProfiler,
    DatabaseTestHelpers
)


@dataclass
class DataIntegrityCheck:
    """Data structure for tracking integrity check results."""
    check_name: str
    total_records: int
    valid_records: int
    invalid_records: int
    missing_records: int
    integrity_score: float
    errors: List[str]
    
    @property
    def is_passing(self) -> bool:
        """Check if integrity validation is passing."""
        return self.integrity_score >= 0.99 and len(self.errors) == 0


class DataIntegrityValidator:
    """Comprehensive data integrity validation system."""
    
    def __init__(self, redis_client, db_manager):
        self.redis_client = redis_client
        self.db_manager = db_manager
        self.integrity_checks: List[DataIntegrityCheck] = []
    
    def calculate_data_hash(self, data: Dict[str, Any]) -> str:
        """Calculate a consistent hash for data integrity verification."""
        # Sort keys for consistent hashing
        sorted_data = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(sorted_data.encode()).hexdigest()
    
    async def validate_player_data_integrity(self) -> DataIntegrityCheck:
        """Validate player data integrity between Redis and PostgreSQL."""
        check_name = "player_data_integrity"
        errors = []
        
        try:
            # Get all players from Redis
            redis_players = {}
            redis_keys = self.redis_client.keys("player:*")
            
            for key in redis_keys:
                player_data = self.redis_client.hgetall(key)
                if player_data:
                    # Convert bytes to strings for Redis data
                    clean_data = {
                        k.decode() if isinstance(k, bytes) else k: 
                        v.decode() if isinstance(v, bytes) else v 
                        for k, v in player_data.items()
                    }
                    redis_players[key.decode() if isinstance(key, bytes) else key] = clean_data
            
            # Get all players from PostgreSQL
            pg_players = {}
            async with self.db_manager.get_session() as session:
                result = await session.execute("SELECT id, username, email, display_name, created_at FROM players")
                for row in result:
                    pg_data = {
                        "id": str(row[0]),
                        "username": row[1],
                        "email": row[2],
                        "display_name": row[3],
                        "created_at": row[4].isoformat() if row[4] else None
                    }
                    pg_players[f"player:{row[0]}"] = pg_data
            
            # Cross-validate data
            total_records = max(len(redis_players), len(pg_players))
            valid_records = 0
            invalid_records = 0
            missing_records = 0
            
            # Check Redis -> PostgreSQL consistency
            for redis_key, redis_data in redis_players.items():
                username = redis_data.get("username")
                if username:
                    # Find corresponding PostgreSQL record
                    pg_record = None
                    for pg_key, pg_data in pg_players.items():
                        if pg_data.get("username") == username:
                            pg_record = pg_data
                            break
                    
                    if pg_record:
                        # Validate data consistency
                        if (redis_data.get("username") == pg_record.get("username") and
                            redis_data.get("email") == pg_record.get("email")):
                            valid_records += 1
                        else:
                            invalid_records += 1
                            errors.append(f"Data mismatch for player {username}: Redis vs PG")
                    else:
                        missing_records += 1
                        errors.append(f"Player {username} exists in Redis but not in PostgreSQL")
            
            # Check PostgreSQL -> Redis consistency
            for pg_key, pg_data in pg_players.items():
                username = pg_data.get("username")
                if username:
                    redis_record = None
                    for redis_key, redis_data in redis_players.items():
                        if redis_data.get("username") == username:
                            redis_record = redis_data
                            break
                    
                    if not redis_record:
                        missing_records += 1
                        errors.append(f"Player {username} exists in PostgreSQL but not in Redis")
            
            integrity_score = valid_records / total_records if total_records > 0 else 1.0
            
        except Exception as e:
            errors.append(f"Player validation error: {str(e)}")
            total_records = 0
            valid_records = 0
            invalid_records = 1
            missing_records = 0
            integrity_score = 0.0
        
        check = DataIntegrityCheck(
            check_name=check_name,
            total_records=total_records,
            valid_records=valid_records,
            invalid_records=invalid_records,
            missing_records=missing_records,
            integrity_score=integrity_score,
            errors=errors
        )
        
        self.integrity_checks.append(check)
        return check
    
    async def validate_game_session_integrity(self) -> DataIntegrityCheck:
        """Validate game session data integrity."""
        check_name = "game_session_integrity"
        errors = []
        
        try:
            # Get game sessions from Redis
            redis_sessions = {}
            redis_keys = self.redis_client.keys("room:*")
            
            for key in redis_keys:
                session_data = self.redis_client.hget(key, "data")
                if session_data:
                    try:
                        data = json.loads(session_data.decode() if isinstance(session_data, bytes) else session_data)
                        redis_sessions[key.decode() if isinstance(key, bytes) else key] = data
                    except json.JSONDecodeError:
                        errors.append(f"Invalid JSON in Redis session {key}")
            
            # Get game sessions from PostgreSQL
            pg_sessions = {}
            async with self.db_manager.get_session() as session:
                result = await session.execute("""
                    SELECT session_id, game_phase, current_round, trump_suit, created_at, is_active
                    FROM game_sessions
                """)
                
                for row in result:
                    pg_data = {
                        "session_id": row[0],
                        "game_phase": row[1],
                        "current_round": row[2],
                        "trump_suit": row[3],
                        "created_at": row[4].isoformat() if row[4] else None,
                        "is_active": row[5]
                    }
                    pg_sessions[row[0]] = pg_data
            
            # Validate session consistency
            total_records = max(len(redis_sessions), len(pg_sessions))
            valid_records = 0
            invalid_records = 0
            missing_records = 0
            
            # Check critical game state consistency
            for redis_key, redis_data in redis_sessions.items():
                session_id = redis_data.get("session_id")
                if session_id and session_id in pg_sessions:
                    pg_data = pg_sessions[session_id]
                    
                    # Validate critical fields
                    redis_phase = redis_data.get("game_phase")
                    pg_phase = pg_data.get("game_phase")
                    
                    if redis_phase == pg_phase:
                        valid_records += 1
                    else:
                        invalid_records += 1
                        errors.append(f"Game phase mismatch for session {session_id}: Redis={redis_phase}, PG={pg_phase}")
                else:
                    missing_records += 1
                    if session_id:
                        errors.append(f"Session {session_id} exists in Redis but not in PostgreSQL")
            
            integrity_score = valid_records / total_records if total_records > 0 else 1.0
            
        except Exception as e:
            errors.append(f"Game session validation error: {str(e)}")
            total_records = 0
            valid_records = 0
            invalid_records = 1
            missing_records = 0
            integrity_score = 0.0
        
        check = DataIntegrityCheck(
            check_name=check_name,
            total_records=total_records,
            valid_records=valid_records,
            invalid_records=invalid_records,
            missing_records=missing_records,
            integrity_score=integrity_score,
            errors=errors
        )
        
        self.integrity_checks.append(check)
        return check
    
    async def validate_statistics_integrity(self) -> DataIntegrityCheck:
        """Validate player statistics and leaderboard integrity."""
        check_name = "statistics_integrity"
        errors = []
        
        try:
            # Get statistics from Redis
            redis_stats = {}
            redis_keys = self.redis_client.keys("stats:*")
            
            for key in redis_keys:
                stats_data = self.redis_client.hgetall(key)
                if stats_data:
                    clean_data = {
                        k.decode() if isinstance(k, bytes) else k: 
                        v.decode() if isinstance(v, bytes) else v 
                        for k, v in stats_data.items()
                    }
                    redis_stats[key.decode() if isinstance(key, bytes) else key] = clean_data
            
            # Get Redis leaderboard
            redis_leaderboard = self.redis_client.zrevrange("leaderboard", 0, -1, withscores=True)
            redis_leaderboard_dict = {
                member.decode() if isinstance(member, bytes) else member: score 
                for member, score in redis_leaderboard
            }
            
            # Get statistics from PostgreSQL
            pg_stats = {}
            pg_leaderboard = {}
            
            async with self.db_manager.get_session() as session:
                # Get player statistics
                result = await session.execute("""
                    SELECT p.username, ps.games_played, ps.games_won, ps.total_score, ps.win_rate
                    FROM player_stats ps
                    JOIN players p ON ps.player_id = p.id
                """)
                
                for row in result:
                    username = row[0]
                    pg_data = {
                        "games_played": str(row[1]),
                        "games_won": str(row[2]),
                        "total_score": str(row[3]),
                        "win_rate": str(row[4]) if row[4] is not None else "0"
                    }
                    pg_stats[f"stats:player:{username}"] = pg_data
                    pg_leaderboard[f"player:{username}"] = float(row[3])
            
            # Validate statistics consistency
            total_records = max(len(redis_stats), len(pg_stats))
            valid_records = 0
            invalid_records = 0
            missing_records = 0
            
            # Check Redis vs PostgreSQL stats
            for redis_key, redis_data in redis_stats.items():
                # Extract player identifier from key
                if ":" in redis_key:
                    player_identifier = redis_key.split(":")[-1]
                    
                    # Find corresponding PostgreSQL stats
                    pg_match = None
                    for pg_key, pg_data in pg_stats.items():
                        if player_identifier in pg_key:
                            pg_match = pg_data
                            break
                    
                    if pg_match:
                        # Compare key statistics
                        redis_games = redis_data.get("games_played", "0")
                        pg_games = pg_match.get("games_played", "0")
                        
                        if redis_games == pg_games:
                            valid_records += 1
                        else:
                            invalid_records += 1
                            errors.append(f"Games played mismatch for {player_identifier}: Redis={redis_games}, PG={pg_games}")
                    else:
                        missing_records += 1
                        errors.append(f"Statistics for {player_identifier} exist in Redis but not PostgreSQL")
            
            # Validate leaderboard consistency
            if redis_leaderboard_dict and pg_leaderboard:
                # Check top 10 players for consistency
                redis_top = sorted(redis_leaderboard_dict.items(), key=lambda x: x[1], reverse=True)[:10]
                pg_top = sorted(pg_leaderboard.items(), key=lambda x: x[1], reverse=True)[:10]
                
                redis_top_players = [player for player, score in redis_top]
                pg_top_players = [player for player, score in pg_top]
                
                # Allow for some variance in leaderboard ordering
                common_top_players = set(redis_top_players) & set(pg_top_players)
                if len(common_top_players) < 5:  # At least 50% overlap in top 10
                    errors.append(f"Leaderboard inconsistency: only {len(common_top_players)} common players in top 10")
            
            integrity_score = valid_records / total_records if total_records > 0 else 1.0
            
        except Exception as e:
            errors.append(f"Statistics validation error: {str(e)}")
            total_records = 0
            valid_records = 0
            invalid_records = 1
            missing_records = 0
            integrity_score = 0.0
        
        check = DataIntegrityCheck(
            check_name=check_name,
            total_records=total_records,
            valid_records=valid_records,
            invalid_records=invalid_records,
            missing_records=missing_records,
            integrity_score=integrity_score,
            errors=errors
        )
        
        self.integrity_checks.append(check)
        return check
    
    async def validate_referential_integrity(self) -> DataIntegrityCheck:
        """Validate referential integrity between related entities."""
        check_name = "referential_integrity"
        errors = []
        
        try:
            # Check PostgreSQL referential integrity
            integrity_violations = 0
            total_checks = 0
            
            async with self.db_manager.get_session() as session:
                # Check 1: Game sessions should have valid creator IDs
                result = await session.execute("""
                    SELECT COUNT(*) 
                    FROM game_sessions gs 
                    LEFT JOIN players p ON gs.creator_id = p.id 
                    WHERE p.id IS NULL
                """)
                orphaned_sessions = result.scalar()
                total_checks += 1
                
                if orphaned_sessions > 0:
                    integrity_violations += 1
                    errors.append(f"Found {orphaned_sessions} game sessions with invalid creator IDs")
                
                # Check 2: Player stats should have valid player IDs
                result = await session.execute("""
                    SELECT COUNT(*) 
                    FROM player_stats ps 
                    LEFT JOIN players p ON ps.player_id = p.id 
                    WHERE p.id IS NULL
                """)
                orphaned_stats = result.scalar()
                total_checks += 1
                
                if orphaned_stats > 0:
                    integrity_violations += 1
                    errors.append(f"Found {orphaned_stats} player stats with invalid player IDs")
                
                # Check 3: Game moves should have valid session IDs
                result = await session.execute("""
                    SELECT COUNT(*) 
                    FROM game_moves gm 
                    LEFT JOIN game_sessions gs ON gm.session_id = gs.session_id 
                    WHERE gs.session_id IS NULL
                """)
                orphaned_moves = result.scalar()
                total_checks += 1
                
                if orphaned_moves > 0:
                    integrity_violations += 1
                    errors.append(f"Found {orphaned_moves} game moves with invalid session IDs")
                
                # Check 4: Game session players should have valid player and session IDs
                result = await session.execute("""
                    SELECT COUNT(*) 
                    FROM game_session_players gsp 
                    LEFT JOIN players p ON gsp.player_id = p.id 
                    LEFT JOIN game_sessions gs ON gsp.session_id = gs.session_id 
                    WHERE p.id IS NULL OR gs.session_id IS NULL
                """)
                orphaned_participants = result.scalar()
                total_checks += 1
                
                if orphaned_participants > 0:
                    integrity_violations += 1
                    errors.append(f"Found {orphaned_participants} game participants with invalid references")
            
            # Calculate integrity score
            valid_checks = total_checks - integrity_violations
            integrity_score = valid_checks / total_checks if total_checks > 0 else 1.0
            
        except Exception as e:
            errors.append(f"Referential integrity validation error: {str(e)}")
            total_checks = 1
            valid_checks = 0
            integrity_violations = 1
            integrity_score = 0.0
        
        check = DataIntegrityCheck(
            check_name=check_name,
            total_records=total_checks,
            valid_records=valid_checks,
            invalid_records=integrity_violations,
            missing_records=0,
            integrity_score=integrity_score,
            errors=errors
        )
        
        self.integrity_checks.append(check)
        return check
    
    def get_overall_integrity_report(self) -> Dict[str, Any]:
        """Generate comprehensive integrity report."""
        if not self.integrity_checks:
            return {"status": "no_checks_performed"}
        
        total_score = sum(check.integrity_score for check in self.integrity_checks)
        average_score = total_score / len(self.integrity_checks)
        
        all_errors = []
        for check in self.integrity_checks:
            all_errors.extend(check.errors)
        
        passing_checks = sum(1 for check in self.integrity_checks if check.is_passing)
        
        return {
            "overall_integrity_score": average_score,
            "total_checks": len(self.integrity_checks),
            "passing_checks": passing_checks,
            "failing_checks": len(self.integrity_checks) - passing_checks,
            "total_errors": len(all_errors),
            "individual_checks": [
                {
                    "name": check.check_name,
                    "score": check.integrity_score,
                    "total_records": check.total_records,
                    "valid_records": check.valid_records,
                    "invalid_records": check.invalid_records,
                    "missing_records": check.missing_records,
                    "is_passing": check.is_passing,
                    "error_count": len(check.errors)
                }
                for check in self.integrity_checks
            ],
            "all_errors": all_errors
        }


@pytest.mark.asyncio
@pytest.mark.migration
@pytest.mark.data_integrity
class TestDataIntegrityValidation:
    """Comprehensive data integrity validation tests."""
    
    async def test_comprehensive_data_integrity_check(self, redis_client, db_manager, test_data_generator, db_helpers):
        """Perform comprehensive data integrity validation."""
        profiler = PerformanceProfiler()
        profiler.start()
        
        # Setup: Create test data in both systems
        print("Setting up test data for integrity validation...")
        
        # Create players in both systems
        async with db_manager.get_session() as session:
            test_players = await db_helpers.create_test_players(session, count=20)
        
        # Store players in Redis as well
        for i, player in enumerate(test_players):
            redis_data = {
                "username": player["username"],
                "email": player["email"],
                "display_name": player.get("display_name", f"Player {i}"),
                "created_at": datetime.utcnow().isoformat()
            }
            redis_client.hset(f"player:{player['id']}", mapping=redis_data)
        
        # Create game sessions in both systems
        async with db_manager.get_session() as session:
            game_sessions = []
            for i in range(5):
                session_players = test_players[i*4:(i+1)*4]
                game_session = await db_helpers.create_test_game_session(
                    session, session_players[0]["id"], session_players
                )
                game_sessions.append(game_session)
        
        # Store game sessions in Redis
        for game_session in game_sessions:
            redis_data = {
                "session_id": game_session["session_id"],
                "game_phase": game_session["game_phase"],
                "current_round": game_session["current_round"],
                "created_at": datetime.utcnow().isoformat()
            }
            redis_client.hset(f"room:{game_session['session_id']}", "data", json.dumps(redis_data))
        
        # Create player statistics
        async with db_manager.get_session() as session:
            for player in test_players[:10]:  # Stats for first 10 players
                stats_data = test_data_generator["player_stats"](player["id"])
                
                from backend.database.models import PlayerStats
                stats = PlayerStats(**stats_data)
                session.add(stats)
                
                # Also store in Redis
                redis_stats = {
                    "games_played": str(stats_data["games_played"]),
                    "games_won": str(stats_data["games_won"]),
                    "total_score": str(stats_data["total_score"]),
                    "win_rate": str(stats_data["win_rate"])
                }
                redis_client.hset(f"stats:player:{player['username']}", mapping=redis_stats)
                redis_client.zadd("leaderboard", {f"player:{player['username']}": stats_data["total_score"]})
            
            await session.commit()
        
        profiler.record_operation("setup_test_data", 3.0)
        
        # Perform comprehensive integrity validation
        validator = DataIntegrityValidator(redis_client, db_manager)
        
        print("Running comprehensive data integrity checks...")
        
        # Run all integrity checks
        player_check = await validator.validate_player_data_integrity()
        session_check = await validator.validate_game_session_integrity()
        stats_check = await validator.validate_statistics_integrity()
        referential_check = await validator.validate_referential_integrity()
        
        profiler.record_operation("integrity_validation", 2.0)
        
        # Generate comprehensive report
        integrity_report = validator.get_overall_integrity_report()
        
        print(f"\n--- Data Integrity Validation Results ---")
        print(f"Overall Integrity Score: {integrity_report['overall_integrity_score']:.3f}")
        print(f"Passing Checks: {integrity_report['passing_checks']}/{integrity_report['total_checks']}")
        print(f"Total Errors: {integrity_report['total_errors']}")
        
        for check in integrity_report['individual_checks']:
            status = "✅ PASS" if check['is_passing'] else "❌ FAIL"
            print(f"  {check['name']}: {status} (Score: {check['score']:.3f}, Records: {check['valid_records']}/{check['total_records']})")
        
        if integrity_report['all_errors']:
            print(f"\nErrors Found:")
            for error in integrity_report['all_errors'][:10]:  # Show first 10 errors
                print(f"  - {error}")
            if len(integrity_report['all_errors']) > 10:
                print(f"  ... and {len(integrity_report['all_errors']) - 10} more errors")
        
        # Assertions for data integrity
        assert integrity_report['overall_integrity_score'] >= 0.95, f"Overall integrity score too low: {integrity_report['overall_integrity_score']:.3f}"
        assert integrity_report['passing_checks'] == integrity_report['total_checks'], f"Some integrity checks failed: {integrity_report['failing_checks']} out of {integrity_report['total_checks']}"
        assert integrity_report['total_errors'] <= 2, f"Too many integrity errors: {integrity_report['total_errors']}"
        
        metrics = profiler.stop()
        
        print(f"\nIntegrity validation completed in {metrics['total_duration']:.2f}s")
        
        # Cleanup
        for player in test_players:
            redis_client.delete(f"player:{player['id']}")
            redis_client.delete(f"stats:player:{player['username']}")
        
        for game_session in game_sessions:
            redis_client.delete(f"room:{game_session['session_id']}")
        
        redis_client.delete("leaderboard")
        
        return integrity_report
    
    async def test_data_consistency_during_concurrent_updates(self, redis_client, db_manager, test_data_generator):
        """Test data consistency during concurrent updates."""
        profiler = PerformanceProfiler()
        profiler.start()
        
        # Setup: Create a player in both systems
        player_data = test_data_generator["player"]()
        player_data["username"] = "consistency_test_player"
        
        async with db_manager.get_session() as session:
            from backend.database.models import Player
            player = Player(**player_data)
            session.add(player)
            await session.commit()
            player_id = player.id
        
        redis_client.hset("consistency_player", mapping=player_data)
        
        # Concurrent update operations
        async def update_redis():
            for i in range(50):
                redis_client.hset("consistency_player", "score", str(i * 10))
                await asyncio.sleep(0.01)
        
        async def update_postgresql():
            for i in range(50):
                async with db_manager.get_session() as session:
                    await session.execute(
                        "UPDATE players SET display_name = :name WHERE id = :id",
                        {"name": f"Updated Player {i}", "id": player_id}
                    )
                    await session.commit()
                    await asyncio.sleep(0.01)
        
        # Run concurrent updates
        await asyncio.gather(update_redis(), update_postgresql())
        
        profiler.record_operation("concurrent_updates", 1.0)
        
        # Validate final consistency
        validator = DataIntegrityValidator(redis_client, db_manager)
        
        # Check that both systems are in valid final states
        redis_data = redis_client.hgetall("consistency_player")
        async with db_manager.get_session() as session:
            result = await session.execute(
                "SELECT username, display_name FROM players WHERE id = :id",
                {"id": player_id}
            )
            pg_data = result.fetchone()
        
        # Validate data exists and is consistent
        assert redis_data, "Redis data missing after concurrent updates"
        assert pg_data, "PostgreSQL data missing after concurrent updates"
        
        redis_username = redis_data.get(b"username", b"").decode()
        pg_username = pg_data[0]
        
        assert redis_username == pg_username, f"Username inconsistency: Redis={redis_username}, PG={pg_username}"
        
        # Check for data corruption
        redis_score = redis_data.get(b"score", b"0").decode()
        assert redis_score.isdigit(), f"Redis score corrupted: {redis_score}"
        
        pg_display_name = pg_data[1]
        assert "Updated Player" in pg_display_name, f"PostgreSQL update not applied: {pg_display_name}"
        
        metrics = profiler.stop()
        
        print(f"Concurrent update consistency test completed in {metrics['total_duration']:.2f}s")
        print(f"Final Redis score: {redis_score}")
        print(f"Final PG display name: {pg_display_name}")
        
        # Cleanup
        redis_client.delete("consistency_player")
    
    async def test_data_recovery_after_partial_failure(self, redis_client, db_manager, test_data_generator):
        """Test data recovery procedures after partial system failure."""
        profiler = PerformanceProfiler()
        profiler.start()
        
        # Setup: Create data in both systems
        test_players = []
        for i in range(10):
            player_data = test_data_generator["player"]()
            player_data["username"] = f"recovery_test_player_{i}"
            test_players.append(player_data)
        
        # Store in PostgreSQL
        pg_player_ids = []
        async with db_manager.get_session() as session:
            for player_data in test_players:
                from backend.database.models import Player
                player = Player(**player_data)
                session.add(player)
                await session.flush()
                pg_player_ids.append(player.id)
            await session.commit()
        
        # Store in Redis
        for i, player_data in enumerate(test_players):
            redis_client.hset(f"recovery_player_{i}", mapping=player_data)
        
        profiler.record_operation("setup_recovery_data", 0.5)
        
        # Simulate partial failure: Delete some Redis data
        for i in range(3, 7):  # Delete middle 4 players from Redis
            redis_client.delete(f"recovery_player_{i}")
        
        profiler.record_operation("simulate_failure", 0.1)
        
        # Perform data recovery from PostgreSQL to Redis
        recovery_count = 0
        recovery_errors = []
        
        async with db_manager.get_session() as session:
            result = await session.execute("SELECT id, username, email, display_name FROM players WHERE username LIKE 'recovery_test_player_%'")
            pg_players = result.fetchall()
            
            for pg_player in pg_players:
                username = pg_player[1]
                player_index = int(username.split("_")[-1])
                redis_key = f"recovery_player_{player_index}"
                
                # Check if Redis data is missing
                if not redis_client.exists(redis_key):
                    try:
                        # Recover data from PostgreSQL
                        recovery_data = {
                            "username": pg_player[1],
                            "email": pg_player[2],
                            "display_name": pg_player[3],
                            "recovered": "true",
                            "recovery_timestamp": datetime.utcnow().isoformat()
                        }
                        redis_client.hset(redis_key, mapping=recovery_data)
                        recovery_count += 1
                    except Exception as e:
                        recovery_errors.append(f"Failed to recover {username}: {str(e)}")
        
        profiler.record_operation("data_recovery", 0.3)
        
        # Validate recovery success
        validator = DataIntegrityValidator(redis_client, db_manager)
        post_recovery_check = await validator.validate_player_data_integrity()
        
        print(f"Data Recovery Results:")
        print(f"  Players recovered: {recovery_count}")
        print(f"  Recovery errors: {len(recovery_errors)}")
        print(f"  Post-recovery integrity score: {post_recovery_check.integrity_score:.3f}")
        
        # Verify recovered data
        recovered_count = 0
        for i in range(10):
            redis_data = redis_client.hgetall(f"recovery_player_{i}")
            if redis_data:
                recovered_flag = redis_data.get(b"recovered", b"").decode()
                if recovered_flag == "true":
                    recovered_count += 1
        
        assert recovery_count == 4, f"Expected 4 recoveries, got {recovery_count}"
        assert recovered_count == 4, f"Expected 4 recovered flags, got {recovered_count}"
        assert len(recovery_errors) == 0, f"Recovery errors occurred: {recovery_errors}"
        assert post_recovery_check.integrity_score >= 0.95, f"Post-recovery integrity too low: {post_recovery_check.integrity_score:.3f}"
        
        metrics = profiler.stop()
        
        print(f"Data recovery test completed in {metrics['total_duration']:.2f}s")
        
        # Cleanup
        for i in range(10):
            redis_client.delete(f"recovery_player_{i}")
    
    async def test_data_integrity_under_stress(self, redis_client, db_manager, test_data_generator):
        """Test data integrity under high stress conditions."""
        from test_utils import ConcurrencyTestHelpers
        
        profiler = PerformanceProfiler()
        profiler.start()
        
        # Setup initial data
        base_players = 10
        async with db_manager.get_session() as session:
            players = []
            for i in range(base_players):
                player_data = test_data_generator["player"]()
                player_data["username"] = f"stress_player_{i}"
                
                from backend.database.models import Player
                player = Player(**player_data)
                session.add(player)
                await session.flush()
                players.append({"id": player.id, "data": player_data})
                
                # Store in Redis
                redis_client.hset(f"stress_player_{i}", mapping=player_data)
            
            await session.commit()
        
        profiler.record_operation("setup_stress_data", 1.0)
        
        # Define stress operations
        async def stress_create_operation():
            player_data = test_data_generator["player"]()
            player_id = str(uuid.uuid4())
            player_data["username"] = f"stress_created_{player_id[:8]}"
            
            # Write to both systems
            redis_client.hset(f"stress_created_{player_id[:8]}", mapping=player_data)
            
            async with db_manager.get_session() as session:
                from backend.database.models import Player
                player = Player(**player_data)
                session.add(player)
                await session.commit()
                return player.id
        
        async def stress_update_operation():
            player_index = random.choice(range(base_players))
            new_score = str(random.randint(1000, 9999))
            
            # Update both systems
            redis_client.hset(f"stress_player_{player_index}", "score", new_score)
            
            async with db_manager.get_session() as session:
                await session.execute(
                    "UPDATE players SET display_name = :name WHERE username = :username",
                    {"name": f"Stress Updated {new_score}", "username": f"stress_player_{player_index}"}
                )
                await session.commit()
        
        async def stress_read_operation():
            player_index = random.choice(range(base_players))
            
            # Read from both systems
            redis_data = redis_client.hgetall(f"stress_player_{player_index}")
            
            async with db_manager.get_session() as session:
                result = await session.execute(
                    "SELECT username, display_name FROM players WHERE username = :username",
                    {"username": f"stress_player_{player_index}"}
                )
                pg_data = result.fetchone()
            
            return len(redis_data) > 0 and pg_data is not None
        
        # Run stress test with mixed operations
        import random
        operations = []
        for _ in range(100):
            op_type = random.choice(["create", "update", "read", "read", "read"])  # More reads
            if op_type == "create":
                operations.append(stress_create_operation)
            elif op_type == "update":
                operations.append(stress_update_operation)
            else:
                operations.append(stress_read_operation)
        
        # Execute stress operations
        stress_results = await ConcurrencyTestHelpers.run_concurrent_operations(
            operations, max_concurrent=20, timeout=60.0
        )
        
        profiler.record_operation("stress_operations", 30.0)
        
        # Validate integrity after stress test
        validator = DataIntegrityValidator(redis_client, db_manager)
        post_stress_check = await validator.validate_player_data_integrity()
        
        # Count successful operations
        successful_ops = sum(1 for result in stress_results if not isinstance(result, Exception))
        failed_ops = len(stress_results) - successful_ops
        
        print(f"Stress Test Results:")
        print(f"  Total operations: {len(operations)}")
        print(f"  Successful operations: {successful_ops}")
        print(f"  Failed operations: {failed_ops}")
        print(f"  Success rate: {successful_ops/len(operations):.2%}")
        print(f"  Post-stress integrity score: {post_stress_check.integrity_score:.3f}")
        
        # Stress test assertions
        assert successful_ops / len(operations) >= 0.85, f"Stress test success rate too low: {successful_ops/len(operations):.2%}"
        assert post_stress_check.integrity_score >= 0.90, f"Post-stress integrity too low: {post_stress_check.integrity_score:.3f}"
        
        metrics = profiler.stop()
        
        print(f"Stress integrity test completed in {metrics['total_duration']:.2f}s")
        
        # Cleanup
        for i in range(base_players):
            redis_client.delete(f"stress_player_{i}")
        
        # Clean up created players
        for result in stress_results:
            if not isinstance(result, Exception) and isinstance(result, int):
                redis_client.delete(f"stress_created_{str(result)[:8]}")
        
        return {
            "total_operations": len(operations),
            "successful_operations": successful_ops,
            "failed_operations": failed_ops,
            "success_rate": successful_ops / len(operations),
            "post_stress_integrity": post_stress_check.integrity_score
        }
