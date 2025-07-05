"""
Test utilities and helpers for PostgreSQL integration testing.
Provides common functionality for data generation, assertions, and test management.
"""

import asyncio
import json
import time
import uuid
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Callable, AsyncGenerator, Tuple
from faker import Faker
import random
import redis.asyncio as redis
import asyncpg
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
from dataclasses import dataclass, field
from enum import Enum
import numpy as np
from collections import defaultdict

fake = Faker()
logger = logging.getLogger(__name__)

# Migration Testing Enhancements

@dataclass
class MigrationTestMetrics:
    """Comprehensive metrics for migration testing"""
    start_time: datetime
    end_time: Optional[datetime] = None
    operation_counts: Dict[str, int] = field(default_factory=dict)
    response_times: List[float] = field(default_factory=list)
    error_counts: Dict[str, int] = field(default_factory=dict)
    data_consistency_scores: List[float] = field(default_factory=list)
    user_experience_scores: List[float] = field(default_factory=list)

class MigrationTestDataGenerator:
    """Advanced data generator for migration testing scenarios"""
    
    @staticmethod
    def generate_bulk_player_data(count: int, consistency_ratio: float = 0.9) -> List[Dict[str, Any]]:
        """Generate bulk player data with configurable consistency"""
        players = []
        
        for i in range(count):
            base_data = {
                "player_id": f"migration_test_player_{i}",
                "username": f"test_user_{i}_{fake.user_name()}",
                "email": f"test{i}@{fake.domain_name()}",
                "stats": {
                    "games_played": random.randint(0, 1000),
                    "games_won": random.randint(0, 500),
                    "total_points": random.randint(0, 50000),
                    "average_score": round(random.uniform(60.0, 95.0), 2),
                    "win_rate": round(random.uniform(0.3, 0.8), 3)
                },
                "preferences": {
                    "theme": random.choice(["dark", "light", "auto"]),
                    "sound_enabled": random.choice([True, False]),
                    "notifications": random.choice([True, False]),
                    "auto_play": random.choice([True, False]),
                    "language": random.choice(["en", "fa", "es"])
                },
                "created_at": fake.date_time_between(start_date="-2y", end_date="-1y").isoformat(),
                "last_active": fake.date_time_between(start_date="-1m", end_date="now").isoformat()
            }
            
            # Introduce inconsistencies for testing
            if random.random() > consistency_ratio:
                base_data["_inconsistent"] = True
                # Add fields that might cause migration issues
                base_data["corrupted_field"] = "invalid_json_data"
                base_data["missing_stats"] = None
            
            players.append(base_data)
        
        return players
    
    @staticmethod
    def generate_game_session_batch(count: int, player_ids: List[str]) -> List[Dict[str, Any]]:
        """Generate batch of game sessions for testing"""
        sessions = []
        
        for i in range(count):
            # Randomly select 4 players for the session
            session_players = random.sample(player_ids, min(4, len(player_ids)))
            
            session_data = {
                "session_id": f"migration_session_{i}_{uuid.uuid4()}",
                "game_type": "hokm",
                "status": random.choice(["waiting", "active", "paused", "completed"]),
                "players": session_players,
                "teams": {
                    "team_1": session_players[:2] if len(session_players) >= 2 else [],
                    "team_2": session_players[2:4] if len(session_players) >= 4 else []
                },
                "current_round": random.randint(1, 7),
                "scores": {
                    "team_1": random.randint(0, 165),
                    "team_2": random.randint(0, 165)
                },
                "game_state": {
                    "phase": random.choice(["trump_selection", "playing", "round_end"]),
                    "current_player": random.choice(session_players) if session_players else None,
                    "trump_suit": random.choice(["hearts", "diamonds", "clubs", "spades", None]),
                    "cards_played": random.randint(0, 52),
                    "hakem": random.choice(session_players) if session_players else None
                },
                "created_at": fake.date_time_between(start_date="-1w", end_date="now").isoformat(),
                "updated_at": fake.date_time_between(start_date="-1d", end_date="now").isoformat()
            }
            
            sessions.append(session_data)
        
        return sessions

class MigrationTestAssertions:
    """Specialized assertions for migration testing"""
    
    @staticmethod
    def assert_data_consistency(redis_data: Dict[str, Any], postgres_data: Dict[str, Any], 
                              tolerance: float = 0.01) -> List[str]:
        """Assert data consistency between Redis and PostgreSQL with detailed reporting"""
        inconsistencies = []
        
        # Check for missing keys
        redis_keys = set(redis_data.keys())
        postgres_keys = set(postgres_data.keys())
        
        missing_in_postgres = redis_keys - postgres_keys
        missing_in_redis = postgres_keys - redis_keys
        
        if missing_in_postgres:
            inconsistencies.append(f"Missing in PostgreSQL: {missing_in_postgres}")
        if missing_in_redis:
            inconsistencies.append(f"Missing in Redis: {missing_in_redis}")
        
        # Check common keys for value consistency
        common_keys = redis_keys & postgres_keys
        for key in common_keys:
            redis_val = redis_data[key]
            postgres_val = postgres_data[key]
            
            # Handle JSON fields
            if key in ["stats", "preferences", "teams", "scores", "game_state"]:
                try:
                    redis_json = json.loads(redis_val) if isinstance(redis_val, str) else redis_val
                    postgres_json = json.loads(postgres_val) if isinstance(postgres_val, str) else postgres_val
                    
                    if redis_json != postgres_json:
                        inconsistencies.append(f"JSON field '{key}' differs: Redis={redis_json} vs PostgreSQL={postgres_json}")
                        
                except (json.JSONDecodeError, TypeError) as e:
                    inconsistencies.append(f"JSON parsing error for '{key}': {e}")
            else:
                # String comparison for non-JSON fields
                if str(redis_val) != str(postgres_val):
                    inconsistencies.append(f"Field '{key}' differs: Redis='{redis_val}' vs PostgreSQL='{postgres_val}'")
        
        return inconsistencies
    
    @staticmethod
    def assert_performance_within_bounds(actual_time: float, baseline_time: float, 
                                       max_degradation: float = 0.5) -> None:
        """Assert that performance is within acceptable bounds"""
        if baseline_time > 0:
            degradation = (actual_time - baseline_time) / baseline_time
            assert degradation <= max_degradation, \
                f"Performance degraded by {degradation:.2%}, exceeding limit of {max_degradation:.2%}"
    
    @staticmethod
    def assert_migration_completeness(total_records: int, migrated_records: int, 
                                    success_threshold: float = 0.99) -> None:
        """Assert that migration completed successfully"""
        completion_rate = migrated_records / total_records if total_records > 0 else 0
        assert completion_rate >= success_threshold, \
            f"Migration completion rate {completion_rate:.2%} below threshold {success_threshold:.2%}"

class PerformanceProfiler:
    """Enhanced performance profiler for migration testing"""
    
    def __init__(self):
        self.metrics = MigrationTestMetrics(start_time=datetime.now())
        self.operation_timers = {}
        self.checkpoints = {}
    
    def start(self):
        """Start performance profiling"""
        self.metrics.start_time = datetime.now()
    
    def end(self):
        """End performance profiling"""
        self.metrics.end_time = datetime.now()
    
    def start_operation(self, operation_name: str):
        """Start timing an operation"""
        self.operation_timers[operation_name] = time.time()
    
    def end_operation(self, operation_name: str):
        """End timing an operation and record metrics"""
        if operation_name in self.operation_timers:
            duration = time.time() - self.operation_timers[operation_name]
            self.metrics.response_times.append(duration)
            
            # Count operations
            self.metrics.operation_counts[operation_name] = (
                self.metrics.operation_counts.get(operation_name, 0) + 1
            )
            
            del self.operation_timers[operation_name]
            return duration
        return None
    
    def record_error(self, error_type: str):
        """Record an error occurrence"""
        self.metrics.error_counts[error_type] = (
            self.metrics.error_counts.get(error_type, 0) + 1
        )
    
    def record_consistency_score(self, score: float):
        """Record a data consistency score"""
        self.metrics.data_consistency_scores.append(score)
    
    def record_user_experience_score(self, score: float):
        """Record a user experience score"""
        self.metrics.user_experience_scores.append(score)
    
    def add_checkpoint(self, name: str):
        """Add a performance checkpoint"""
        self.checkpoints[name] = datetime.now()
    
    def get_summary(self) -> Dict[str, Any]:
        """Get comprehensive performance summary"""
        duration = (self.metrics.end_time - self.metrics.start_time) if self.metrics.end_time else timedelta(0)
        
        return {
            "total_duration_seconds": duration.total_seconds(),
            "total_operations": sum(self.metrics.operation_counts.values()),
            "operations_per_second": sum(self.metrics.operation_counts.values()) / max(duration.total_seconds(), 1),
            "average_response_time": np.mean(self.metrics.response_times) if self.metrics.response_times else 0,
            "p95_response_time": np.percentile(self.metrics.response_times, 95) if self.metrics.response_times else 0,
            "p99_response_time": np.percentile(self.metrics.response_times, 99) if self.metrics.response_times else 0,
            "total_errors": sum(self.metrics.error_counts.values()),
            "error_rate": sum(self.metrics.error_counts.values()) / max(sum(self.metrics.operation_counts.values()), 1),
            "average_consistency_score": np.mean(self.metrics.data_consistency_scores) if self.metrics.data_consistency_scores else 1.0,
            "average_user_experience_score": np.mean(self.metrics.user_experience_scores) if self.metrics.user_experience_scores else 1.0,
            "operation_breakdown": dict(self.metrics.operation_counts),
            "error_breakdown": dict(self.metrics.error_counts),
            "checkpoints": {name: ts.isoformat() for name, ts in self.checkpoints.items()}
        }

class ConcurrencyTestHelper:
    """Helper for testing concurrent operations during migration"""
    
    @staticmethod
    async def run_concurrent_operations(operations: List[Callable], max_concurrent: int = 10) -> List[Any]:
        """Run operations concurrently with controlled concurrency"""
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def run_with_semaphore(operation):
            async with semaphore:
                return await operation()
        
        # Convert non-async operations to async
        async_operations = []
        for op in operations:
            if asyncio.iscoroutinefunction(op):
                async_operations.append(run_with_semaphore(op))
            else:
                async def async_wrapper():
                    return op()
                async_operations.append(run_with_semaphore(async_wrapper))
        
        return await asyncio.gather(*async_operations, return_exceptions=True)
    
    @staticmethod
    async def simulate_user_load(user_count: int, operations_per_user: int, 
                               operation_factory: Callable[[str], List[Callable]]) -> Dict[str, Any]:
        """Simulate concurrent user load"""
        all_operations = []
        
        # Generate operations for each user
        for user_id in range(user_count):
            user_operations = operation_factory(f"load_test_user_{user_id}")
            all_operations.extend(user_operations[:operations_per_user])
        
        # Run operations concurrently
        start_time = time.time()
        results = await ConcurrencyTestHelper.run_concurrent_operations(all_operations)
        end_time = time.time()
        
        # Analyze results
        successful_operations = [r for r in results if not isinstance(r, Exception)]
        failed_operations = [r for r in results if isinstance(r, Exception)]
        
        return {
            "total_operations": len(all_operations),
            "successful_operations": len(successful_operations),
            "failed_operations": len(failed_operations),
            "success_rate": len(successful_operations) / len(all_operations) if all_operations else 0,
            "total_duration": end_time - start_time,
            "operations_per_second": len(all_operations) / (end_time - start_time),
            "errors": [str(e) for e in failed_operations[:10]]  # First 10 errors for debugging
        }

class DatabaseTestHelpers:
    """Enhanced database testing helpers"""
    
    @staticmethod
    async def create_redis_test_data(redis_client: redis.Redis, data_batch: List[Dict[str, Any]], 
                                   key_prefix: str) -> int:
        """Create test data in Redis efficiently"""
        created_count = 0
        
        for item in data_batch:
            try:
                # Extract ID from item
                item_id = item.get("player_id") or item.get("session_id") or str(uuid.uuid4())
                redis_key = f"{key_prefix}:{item_id}"
                
                # Prepare data for Redis (serialize JSON fields)
                redis_data = {}
                for key, value in item.items():
                    if isinstance(value, (dict, list)):
                        redis_data[key] = json.dumps(value)
                    else:
                        redis_data[key] = str(value)
                
                await redis_client.hset(redis_key, mapping=redis_data)
                created_count += 1
                
            except Exception as e:
                logger.error(f"Error creating Redis data for {item}: {e}")
        
        return created_count
    
    @staticmethod
    async def create_postgres_test_data(postgres_session: AsyncSession, data_batch: List[Dict[str, Any]], 
                                      table_name: str, conflict_action: str = "DO NOTHING") -> int:
        """Create test data in PostgreSQL efficiently"""
        if not data_batch:
            return 0
        
        created_count = 0
        
        try:
            # Build bulk insert query
            first_item = data_batch[0]
            columns = list(first_item.keys())
            placeholders = ", ".join([f"${i+1}" for i in range(len(columns))])
            
            base_query = f"""
            INSERT INTO {table_name} ({', '.join(columns)})
            VALUES ({placeholders})
            ON CONFLICT {conflict_action}
            """
            
            # Execute batch insert
            for item in data_batch:
                values = []
                for col in columns:
                    value = item.get(col)
                    if isinstance(value, (dict, list)):
                        values.append(json.dumps(value))
                    else:
                        values.append(value)
                
                await postgres_session.execute(text(base_query), values)
                created_count += 1
            
            await postgres_session.commit()
            
        except Exception as e:
            logger.error(f"Error creating PostgreSQL data: {e}")
            await postgres_session.rollback()
        
        return created_count
    
    @staticmethod
    async def verify_data_migration(redis_client: redis.Redis, postgres_session: AsyncSession,
                                  entity_type: str, entity_ids: List[str]) -> Dict[str, Any]:
        """Verify data migration between Redis and PostgreSQL"""
        verification_results = {
            "total_checked": len(entity_ids),
            "consistent_records": 0,
            "inconsistent_records": 0,
            "missing_in_redis": 0,
            "missing_in_postgres": 0,
            "inconsistencies": []
        }
        
        for entity_id in entity_ids:
            try:
                # Get data from both systems
                redis_data = await DatabaseTestHelpers.get_redis_entity(redis_client, entity_type, entity_id)
                postgres_data = await DatabaseTestHelpers.get_postgres_entity(postgres_session, entity_type, entity_id)
                
                if not redis_data and not postgres_data:
                    continue  # Both missing, skip
                elif not redis_data:
                    verification_results["missing_in_redis"] += 1
                elif not postgres_data:
                    verification_results["missing_in_postgres"] += 1
                else:
                    # Compare data
                    inconsistencies = MigrationTestAssertions.assert_data_consistency(redis_data, postgres_data)
                    if inconsistencies:
                        verification_results["inconsistent_records"] += 1
                        verification_results["inconsistencies"].extend([
                            f"{entity_id}: {inc}" for inc in inconsistencies
                        ])
                    else:
                        verification_results["consistent_records"] += 1
                        
            except Exception as e:
                logger.error(f"Error verifying {entity_id}: {e}")
                verification_results["inconsistencies"].append(f"{entity_id}: Verification error - {e}")
        
        # Calculate consistency score
        total_comparable = verification_results["consistent_records"] + verification_results["inconsistent_records"]
        verification_results["consistency_score"] = (
            verification_results["consistent_records"] / total_comparable if total_comparable > 0 else 1.0
        )
        
        return verification_results
    
    @staticmethod
    async def get_redis_entity(redis_client: redis.Redis, entity_type: str, entity_id: str) -> Optional[Dict[str, Any]]:
        """Get entity from Redis"""
        if entity_type == "player":
            data = await redis_client.hgetall(f"player:{entity_id}")
        elif entity_type == "game_session":
            data = await redis_client.hgetall(f"game_session:{entity_id}")
        else:
            return None
        
        return {k.decode(): v.decode() for k, v in data.items()} if data else None
    
    @staticmethod
    async def get_postgres_entity(postgres_session: AsyncSession, entity_type: str, entity_id: str) -> Optional[Dict[str, Any]]:
        """Get entity from PostgreSQL"""
        if entity_type == "player":
            query = "SELECT * FROM players WHERE player_id = $1"
            result = await postgres_session.execute(text(query), [entity_id])
            row = result.fetchone()
            if row:
                return {
                    "username": row.username,
                    "email": row.email,
                    "stats": row.stats,
                    "preferences": row.preferences,
                    "created_at": row.created_at,
                    "last_active": row.last_active
                }
        elif entity_type == "game_session":
            query = "SELECT * FROM game_sessions WHERE session_id = $1"
            result = await postgres_session.execute(text(query), [entity_id])
            row = result.fetchone()
            if row:
                return {
                    "game_type": row.game_type,
                    "status": row.status,
                    "players": row.players,
                    "teams": row.teams,
                    "current_round": str(row.current_round),
                    "scores": row.scores,
                    "game_state": row.game_state,
                    "created_at": row.created_at,
                    "updated_at": row.updated_at
                }
        
        return None

# Original test utilities continue below...

class TestDataGenerator:
    """Generate realistic test data for various entities."""
    
    @staticmethod
    def generate_player_data(username: Optional[str] = None) -> Dict[str, Any]:
        """Generate realistic player data."""
        return {
            "username": username or fake.user_name(),
            "email": fake.email(),
            "display_name": fake.name(),
            "password_hash": fake.sha256(),
            "is_active": True,
            "created_at": fake.date_time_between(start_date="-1y", end_date="now"),
            "last_login": fake.date_time_between(start_date="-1m", end_date="now"),
            "avatar_url": fake.image_url(),
            "preferred_language": random.choice(["en", "fa", "es", "fr"]),
            "timezone": fake.timezone()
        }
    
    @staticmethod
    def generate_game_session_data(creator_id: int, num_players: int = 4) -> Dict[str, Any]:
        """Generate realistic game session data."""
        return {
            "session_id": str(uuid.uuid4()),
            "creator_id": creator_id,
            "max_players": num_players,
            "game_phase": random.choice(["waiting", "trump_selection", "playing", "completed"]),
            "current_round": random.randint(1, 7),
            "hakem_id": creator_id,
            "trump_suit": random.choice(["hearts", "diamonds", "clubs", "spades", None]),
            "is_active": True,
            "created_at": fake.date_time_between(start_date="-1d", end_date="now"),
            "settings": {
                "time_limit": random.randint(30, 300),
                "auto_restart": fake.boolean(),
                "allow_spectators": fake.boolean()
            }
        }
    
    @staticmethod
    def generate_player_session_data(player_id: int, session_id: str) -> Dict[str, Any]:
        """Generate player session participation data."""
        return {
            "player_id": player_id,
            "session_id": session_id,
            "team": random.choice([1, 2]),
            "position": random.randint(1, 4),
            "joined_at": fake.date_time_between(start_date="-1h", end_date="now"),
            "is_ready": fake.boolean(),
            "score": random.randint(0, 165)
        }

# ... rest of the existing code continues unchanged ...
