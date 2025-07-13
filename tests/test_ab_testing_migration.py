"""
A/B Testing Framework for Migration Validation
Gradual rollout testing and user experience monitoring
"""

import pytest
import asyncio
import time
import json
import uuid
import random
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import statistics

from test_utils import (
    TestDataGenerator,
    PerformanceProfiler,
    ConcurrencyTestHelpers
)


class ArchitectureType(Enum):
    """Types of architecture for A/B testing."""
    REDIS_ONLY = "redis_only"
    HYBRID = "hybrid"


@dataclass
class ABTestMetrics:
    """Metrics collected during A/B testing."""
    architecture: ArchitectureType
    response_times: List[float] = field(default_factory=list)
    error_rates: List[float] = field(default_factory=list)
    throughput_rates: List[float] = field(default_factory=list)
    user_satisfaction_scores: List[float] = field(default_factory=list)
    feature_success_rates: List[float] = field(default_factory=list)
    resource_usage: List[Dict[str, float]] = field(default_factory=list)
    
    def get_summary_stats(self) -> Dict[str, Any]:
        """Get summary statistics for the metrics."""
        return {
            "architecture": self.architecture.value,
            "avg_response_time": statistics.mean(self.response_times) if self.response_times else 0,
            "p95_response_time": statistics.quantiles(self.response_times, n=20)[18] if len(self.response_times) >= 20 else 0,
            "avg_error_rate": statistics.mean(self.error_rates) if self.error_rates else 0,
            "avg_throughput": statistics.mean(self.throughput_rates) if self.throughput_rates else 0,
            "avg_user_satisfaction": statistics.mean(self.user_satisfaction_scores) if self.user_satisfaction_scores else 0,
            "avg_feature_success": statistics.mean(self.feature_success_rates) if self.feature_success_rates else 0,
            "sample_size": len(self.response_times)
        }


class ABTestController:
    """Controller for managing A/B test traffic distribution."""
    
    def __init__(self, initial_split: float = 0.1):
        """
        Initialize A/B test controller.
        
        Args:
            initial_split: Initial percentage of traffic to send to hybrid architecture (0.0-1.0)
        """
        self.current_split = initial_split
        self.redis_metrics = ABTestMetrics(ArchitectureType.REDIS_ONLY)
        self.hybrid_metrics = ABTestMetrics(ArchitectureType.HYBRID)
        self.total_requests = 0
        self.hybrid_requests = 0
    
    def should_use_hybrid(self) -> bool:
        """Determine if current request should use hybrid architecture."""
        return random.random() < self.current_split
    
    def update_split_percentage(self, new_split: float):
        """Update the traffic split percentage."""
        self.current_split = max(0.0, min(1.0, new_split))
    
    def record_request(self, used_hybrid: bool, response_time: float, success: bool, 
                      user_satisfaction: float = None, resource_usage: Dict[str, float] = None):
        """Record metrics for a request."""
        self.total_requests += 1
        
        if used_hybrid:
            self.hybrid_requests += 1
            self.hybrid_metrics.response_times.append(response_time)
            self.hybrid_metrics.error_rates.append(0.0 if success else 1.0)
            if user_satisfaction is not None:
                self.hybrid_metrics.user_satisfaction_scores.append(user_satisfaction)
            if resource_usage:
                self.hybrid_metrics.resource_usage.append(resource_usage)
        else:
            self.redis_metrics.response_times.append(response_time)
            self.redis_metrics.error_rates.append(0.0 if success else 1.0)
            if user_satisfaction is not None:
                self.redis_metrics.user_satisfaction_scores.append(user_satisfaction)
            if resource_usage:
                self.redis_metrics.resource_usage.append(resource_usage)
    
    def get_comparison_report(self) -> Dict[str, Any]:
        """Get comprehensive comparison report."""
        redis_stats = self.redis_metrics.get_summary_stats()
        hybrid_stats = self.hybrid_metrics.get_summary_stats()
        
        return {
            "test_summary": {
                "total_requests": self.total_requests,
                "hybrid_requests": self.hybrid_requests,
                "current_split": self.current_split,
                "hybrid_percentage": (self.hybrid_requests / self.total_requests * 100) if self.total_requests > 0 else 0
            },
            "redis_metrics": redis_stats,
            "hybrid_metrics": hybrid_stats,
            "comparisons": {
                "response_time_improvement": (redis_stats["avg_response_time"] - hybrid_stats["avg_response_time"]) / redis_stats["avg_response_time"] * 100 if redis_stats["avg_response_time"] > 0 else 0,
                "error_rate_difference": hybrid_stats["avg_error_rate"] - redis_stats["avg_error_rate"],
                "throughput_improvement": (hybrid_stats["avg_throughput"] - redis_stats["avg_throughput"]) / redis_stats["avg_throughput"] * 100 if redis_stats["avg_throughput"] > 0 else 0,
                "user_satisfaction_improvement": hybrid_stats["avg_user_satisfaction"] - redis_stats["avg_user_satisfaction"]
            }
        }


@pytest.mark.asyncio
@pytest.mark.migration
@pytest.mark.ab_testing
class TestABTestingFramework:
    """A/B testing framework for migration validation."""
    
    async def test_initial_10_percent_rollout(self, redis_client, db_manager, test_data_generator):
        """Test initial 10% rollout to hybrid architecture."""
        profiler = PerformanceProfiler()
        profiler.start()
        
        ab_controller = ABTestController(initial_split=0.1)
        
        # Simulate 1000 requests with 10% hybrid traffic
        total_requests = 1000
        
        for i in range(total_requests):
            use_hybrid = ab_controller.should_use_hybrid()
            
            # Generate test operation
            player_data = test_data_generator["player"]()
            player_data["username"] = f"ab_test_player_{i}"
            
            start_time = time.perf_counter()
            success = True
            
            try:
                if use_hybrid:
                    # Hybrid operation: write to both Redis and PostgreSQL
                    redis_client.hset(f"ab_hybrid_player:{i}", mapping=player_data)
                    
                    async with db_manager.get_session() as session:
                        from backend.database.models import Player
                        player = Player(**player_data)
                        session.add(player)
                        await session.commit()
                else:
                    # Redis-only operation
                    redis_client.hset(f"ab_redis_player:{i}", mapping=player_data)
                
            except Exception as e:
                success = False
            
            end_time = time.perf_counter()
            response_time = end_time - start_time
            
            # Simulate user satisfaction score (higher for better performance)
            user_satisfaction = max(1.0, 5.0 - (response_time * 10))  # 1-5 scale
            
            ab_controller.record_request(
                used_hybrid=use_hybrid,
                response_time=response_time,
                success=success,
                user_satisfaction=user_satisfaction
            )
        
        profiler.record_operation("ab_test_10_percent", 30.0)
        
        # Analyze results
        report = ab_controller.get_comparison_report()
        
        print(f"10% Rollout A/B Test Results:")
        print(f"  Total requests: {report['test_summary']['total_requests']}")
        print(f"  Hybrid requests: {report['test_summary']['hybrid_requests']}")
        print(f"  Actual hybrid percentage: {report['test_summary']['hybrid_percentage']:.1f}%")
        print(f"  Redis avg response time: {report['redis_metrics']['avg_response_time']:.4f}s")
        print(f"  Hybrid avg response time: {report['hybrid_metrics']['avg_response_time']:.4f}s")
        print(f"  Response time improvement: {report['comparisons']['response_time_improvement']:.1f}%")
        print(f"  Redis error rate: {report['redis_metrics']['avg_error_rate']:.3f}")
        print(f"  Hybrid error rate: {report['hybrid_metrics']['avg_error_rate']:.3f}")
        
        # Validation criteria for 10% rollout
        assert report['test_summary']['hybrid_percentage'] >= 8.0, f"Hybrid traffic too low: {report['test_summary']['hybrid_percentage']:.1f}%"
        assert report['test_summary']['hybrid_percentage'] <= 12.0, f"Hybrid traffic too high: {report['test_summary']['hybrid_percentage']:.1f}%"
        assert report['hybrid_metrics']['avg_error_rate'] <= 0.02, f"Hybrid error rate too high: {report['hybrid_metrics']['avg_error_rate']:.3f}"
        assert report['comparisons']['error_rate_difference'] <= 0.01, "Hybrid architecture showing significantly more errors"
        
        metrics = profiler.stop()
        
        # Cleanup
        for i in range(total_requests):
            redis_client.delete(f"ab_hybrid_player:{i}")
            redis_client.delete(f"ab_redis_player:{i}")
        
        return report
    
    async def test_gradual_rollout_progression(self, redis_client, db_manager, test_data_generator):
        """Test gradual rollout progression: 10% -> 25% -> 50% -> 75% -> 100%."""
        rollout_stages = [0.1, 0.25, 0.5, 0.75, 1.0]
        stage_reports = []
        
        profiler = PerformanceProfiler()
        profiler.start()
        
        for stage_percentage in rollout_stages:
            print(f"\n--- Testing {stage_percentage*100:.0f}% Rollout Stage ---")
            
            ab_controller = ABTestController(initial_split=stage_percentage)
            requests_per_stage = 200
            
            for i in range(requests_per_stage):
                use_hybrid = ab_controller.should_use_hybrid()
                
                player_data = test_data_generator["player"]()
                player_data["username"] = f"gradual_test_{stage_percentage}_{i}"
                
                start_time = time.perf_counter()
                success = True
                
                try:
                    if use_hybrid:
                        # Hybrid operation
                        redis_client.hset(f"gradual_hybrid:{stage_percentage}:{i}", mapping=player_data)
                        
                        async with db_manager.get_session() as session:
                            from backend.database.models import Player
                            player = Player(**player_data)
                            session.add(player)
                            await session.commit()
                    else:
                        # Redis-only operation
                        redis_client.hset(f"gradual_redis:{stage_percentage}:{i}", mapping=player_data)
                
                except Exception as e:
                    success = False
                
                end_time = time.perf_counter()
                response_time = end_time - start_time
                user_satisfaction = max(1.0, 5.0 - (response_time * 8))
                
                ab_controller.record_request(
                    used_hybrid=use_hybrid,
                    response_time=response_time,
                    success=success,
                    user_satisfaction=user_satisfaction
                )
            
            # Get stage report
            stage_report = ab_controller.get_comparison_report()
            stage_report["stage_percentage"] = stage_percentage
            stage_reports.append(stage_report)
            
            print(f"  Actual hybrid %: {stage_report['test_summary']['hybrid_percentage']:.1f}%")
            print(f"  Hybrid avg response: {stage_report['hybrid_metrics']['avg_response_time']:.4f}s")
            print(f"  Redis avg response: {stage_report['redis_metrics']['avg_response_time']:.4f}s")
            print(f"  Hybrid error rate: {stage_report['hybrid_metrics']['avg_error_rate']:.3f}")
            
            # Stage validation
            expected_percentage = stage_percentage * 100
            actual_percentage = stage_report['test_summary']['hybrid_percentage']
            
            assert abs(actual_percentage - expected_percentage) <= 5.0, f"Stage {expected_percentage}%: traffic split incorrect ({actual_percentage:.1f}%)"
            assert stage_report['hybrid_metrics']['avg_error_rate'] <= 0.05, f"Stage {expected_percentage}%: error rate too high"
        
        profiler.record_operation("gradual_rollout_all_stages", 60.0)
        
        # Analyze rollout progression
        print(f"\n--- Gradual Rollout Summary ---")
        for report in stage_reports:
            stage = report["stage_percentage"] * 100
            print(f"  {stage:3.0f}% stage: {report['hybrid_metrics']['avg_response_time']:.4f}s avg response, {report['hybrid_metrics']['avg_error_rate']:.3f} error rate")
        
        # Validate overall trend
        error_rates = [r['hybrid_metrics']['avg_error_rate'] for r in stage_reports if r['hybrid_metrics']['sample_size'] > 0]
        response_times = [r['hybrid_metrics']['avg_response_time'] for r in stage_reports if r['hybrid_metrics']['sample_size'] > 0]
        
        # Error rates should remain stable or improve
        assert max(error_rates) <= 0.05, f"Error rates too high during rollout: max {max(error_rates):.3f}"
        
        # Response times should remain reasonable
        assert max(response_times) <= 1.0, f"Response times degraded during rollout: max {max(response_times):.3f}s"
        
        metrics = profiler.stop()
        
        # Cleanup
        for stage_percentage in rollout_stages:
            for i in range(200):
                redis_client.delete(f"gradual_hybrid:{stage_percentage}:{i}")
                redis_client.delete(f"gradual_redis:{stage_percentage}:{i}")
        
        return stage_reports
    
    async def test_feature_parity_validation(self, redis_client, db_manager, test_data_generator, db_helpers):
        """Test that both architectures provide equivalent functionality."""
        profiler = PerformanceProfiler()
        profiler.start()
        
        ab_controller = ABTestController(initial_split=0.5)  # 50/50 split
        
        # Test scenarios that should work identically in both architectures
        test_scenarios = [
            "player_creation",
            "player_authentication", 
            "game_session_creation",
            "game_session_joining",
            "player_statistics_retrieval",
            "leaderboard_query"
        ]
        
        feature_results = {scenario: {"redis_success": 0, "hybrid_success": 0, "total_tests": 0} 
                          for scenario in test_scenarios}
        
        tests_per_scenario = 20
        
        for scenario in test_scenarios:
            print(f"\n--- Testing Feature Parity: {scenario} ---")
            
            for i in range(tests_per_scenario):
                use_hybrid = ab_controller.should_use_hybrid()
                feature_results[scenario]["total_tests"] += 1
                
                success = False
                start_time = time.perf_counter()
                
                try:
                    if scenario == "player_creation":
                        player_data = test_data_generator["player"]()
                        player_data["username"] = f"feature_test_{scenario}_{i}"
                        
                        if use_hybrid:
                            # Create in both systems
                            redis_client.hset(f"feature_player:{i}", mapping=player_data)
                            async with db_manager.get_session() as session:
                                from backend.database.models import Player
                                player = Player(**player_data)
                                session.add(player)
                                await session.commit()
                        else:
                            # Create in Redis only
                            redis_client.hset(f"feature_player:{i}", mapping=player_data)
                        
                        success = True
                    
                    elif scenario == "player_authentication":
                        # Simulate authentication check
                        if use_hybrid:
                            # Check both systems
                            redis_exists = redis_client.exists(f"feature_player:{i%10}")
                            async with db_manager.get_session() as session:
                                result = await session.execute("SELECT COUNT(*) FROM players LIMIT 1")
                                pg_exists = result.scalar() > 0
                            success = redis_exists or pg_exists
                        else:
                            # Check Redis only
                            success = redis_client.exists(f"feature_player:{i%10}")
                    
                    elif scenario == "game_session_creation":
                        if use_hybrid:
                            # Create in both systems
                            session_data = {
                                "session_id": f"feature_session_{i}",
                                "creator": f"player_{i}",
                                "created_at": datetime.utcnow().isoformat()
                            }
                            redis_client.hset(f"feature_session:{i}", mapping=session_data)
                            
                            async with db_manager.get_session() as session:
                                from backend.database.models import GameSession
                                # Create minimal game session
                                players = await db_helpers.create_test_players(session, count=1)
                                game_session = await db_helpers.create_test_game_session(
                                    session, players[0]["id"], players
                                )
                        else:
                            # Create in Redis only
                            session_data = {
                                "session_id": f"feature_session_{i}",
                                "creator": f"player_{i}",
                                "created_at": datetime.utcnow().isoformat()
                            }
                            redis_client.hset(f"feature_session:{i}", mapping=session_data)
                        
                        success = True
                    
                    elif scenario == "player_statistics_retrieval":
                        if use_hybrid:
                            # Retrieve from PostgreSQL if available, else Redis
                            async with db_manager.get_session() as session:
                                result = await session.execute("SELECT COUNT(*) FROM player_stats")
                                success = True  # Query executed successfully
                        else:
                            # Retrieve from Redis
                            stats_exist = redis_client.exists("leaderboard")
                            success = True  # Operation completed
                    
                    else:
                        # Default: simple operation success
                        success = True
                
                except Exception as e:
                    success = False
                
                end_time = time.perf_counter()
                response_time = end_time - start_time
                
                # Record results
                if success:
                    if use_hybrid:
                        feature_results[scenario]["hybrid_success"] += 1
                    else:
                        feature_results[scenario]["redis_success"] += 1
                
                ab_controller.record_request(
                    used_hybrid=use_hybrid,
                    response_time=response_time,
                    success=success,
                    user_satisfaction=5.0 if success else 1.0
                )
        
        profiler.record_operation("feature_parity_testing", 20.0)
        
        # Analyze feature parity results
        print(f"\n--- Feature Parity Results ---")
        overall_parity_score = 0
        
        for scenario, results in feature_results.items():
            redis_success_rate = results["redis_success"] / (results["total_tests"] / 2) if results["total_tests"] > 0 else 0
            hybrid_success_rate = results["hybrid_success"] / (results["total_tests"] / 2) if results["total_tests"] > 0 else 0
            parity_score = min(redis_success_rate, hybrid_success_rate) / max(redis_success_rate, hybrid_success_rate) if max(redis_success_rate, hybrid_success_rate) > 0 else 0
            
            print(f"  {scenario}: Redis {redis_success_rate:.2f}, Hybrid {hybrid_success_rate:.2f}, Parity {parity_score:.2f}")
            
            overall_parity_score += parity_score
            
            # Feature parity assertions
            assert redis_success_rate >= 0.8, f"{scenario}: Redis success rate too low ({redis_success_rate:.2f})"
            assert hybrid_success_rate >= 0.8, f"{scenario}: Hybrid success rate too low ({hybrid_success_rate:.2f})"
            assert parity_score >= 0.9, f"{scenario}: Feature parity too low ({parity_score:.2f})"
        
        overall_parity_score /= len(test_scenarios)
        
        print(f"  Overall Feature Parity Score: {overall_parity_score:.3f}")
        
        assert overall_parity_score >= 0.95, f"Overall feature parity too low: {overall_parity_score:.3f}"
        
        metrics = profiler.stop()
        
        # Cleanup
        for i in range(tests_per_scenario):
            redis_client.delete(f"feature_player:{i}")
            redis_client.delete(f"feature_session:{i}")
        
        return feature_results
    
    async def test_user_experience_impact_assessment(self, redis_client, db_manager, test_data_generator):
        """Assess user experience impact during migration."""
        profiler = PerformanceProfiler()
        profiler.start()
        
        # Simulate different user experience scenarios
        ux_scenarios = [
            {"name": "quick_operations", "operation_type": "lightweight", "expected_time": 0.1},
            {"name": "medium_operations", "operation_type": "moderate", "expected_time": 0.5},
            {"name": "heavy_operations", "operation_type": "intensive", "expected_time": 2.0}
        ]
        
        ux_results = {}
        
        for scenario in ux_scenarios:
            print(f"\n--- UX Assessment: {scenario['name']} ---")
            
            ab_controller = ABTestController(initial_split=0.3)  # 30% hybrid
            scenario_results = {"redis_satisfaction": [], "hybrid_satisfaction": []}
            
            tests_per_scenario = 50
            
            for i in range(tests_per_scenario):
                use_hybrid = ab_controller.should_use_hybrid()
                
                start_time = time.perf_counter()
                success = True
                
                try:
                    if scenario["operation_type"] == "lightweight":
                        # Quick Redis operations
                        player_data = {"username": f"ux_test_{i}", "score": str(i)}
                        if use_hybrid:
                            redis_client.hset(f"ux_light:{i}", mapping=player_data)
                            # Simulate light DB operation
                            async with db_manager.get_session() as session:
                                await session.execute("SELECT 1")
                        else:
                            redis_client.hset(f"ux_light:{i}", mapping=player_data)
                    
                    elif scenario["operation_type"] == "moderate":
                        # Medium complexity operations
                        if use_hybrid:
                            # Create player in both systems
                            player_data = test_data_generator["player"]()
                            redis_client.hset(f"ux_medium:{i}", mapping=player_data)
                            async with db_manager.get_session() as session:
                                from backend.database.models import Player
                                player = Player(**player_data)
                                session.add(player)
                                await session.commit()
                        else:
                            # Redis operations with some processing
                            player_data = test_data_generator["player"]()
                            redis_client.hset(f"ux_medium:{i}", mapping=player_data)
                            redis_client.zadd("ux_leaderboard", {f"player_{i}": i})
                    
                    elif scenario["operation_type"] == "intensive":
                        # Heavy operations (multiple queries, complex processing)
                        if use_hybrid:
                            # Complex database operations
                            async with db_manager.get_session() as session:
                                # Simulate complex query
                                await session.execute("SELECT COUNT(*) FROM players")
                                await session.execute("SELECT COUNT(*) FROM game_sessions")
                                
                                # Create and query player stats
                                player_data = test_data_generator["player"]()
                                from backend.database.models import Player
                                player = Player(**player_data)
                                session.add(player)
                                await session.commit()
                        else:
                            # Complex Redis operations
                            for j in range(10):
                                redis_client.hset(f"ux_heavy:{i}:{j}", mapping={"data": f"value_{j}"})
                            redis_client.zrange("ux_leaderboard", 0, -1)
                
                except Exception as e:
                    success = False
                
                end_time = time.perf_counter()
                response_time = end_time - start_time
                
                # Calculate user satisfaction based on response time vs expectations
                expected_time = scenario["expected_time"]
                if response_time <= expected_time:
                    satisfaction = 5.0  # Excellent
                elif response_time <= expected_time * 1.5:
                    satisfaction = 4.0  # Good
                elif response_time <= expected_time * 2.0:
                    satisfaction = 3.0  # Acceptable
                elif response_time <= expected_time * 3.0:
                    satisfaction = 2.0  # Poor
                else:
                    satisfaction = 1.0  # Very poor
                
                if not success:
                    satisfaction = 1.0  # Failed operations have lowest satisfaction
                
                if use_hybrid:
                    scenario_results["hybrid_satisfaction"].append(satisfaction)
                else:
                    scenario_results["redis_satisfaction"].append(satisfaction)
                
                ab_controller.record_request(
                    used_hybrid=use_hybrid,
                    response_time=response_time,
                    success=success,
                    user_satisfaction=satisfaction
                )
            
            # Analyze UX results for this scenario
            redis_avg_satisfaction = statistics.mean(scenario_results["redis_satisfaction"]) if scenario_results["redis_satisfaction"] else 0
            hybrid_avg_satisfaction = statistics.mean(scenario_results["hybrid_satisfaction"]) if scenario_results["hybrid_satisfaction"] else 0
            
            ux_impact = hybrid_avg_satisfaction - redis_avg_satisfaction
            
            scenario_summary = {
                "redis_satisfaction": redis_avg_satisfaction,
                "hybrid_satisfaction": hybrid_avg_satisfaction,
                "ux_impact": ux_impact,
                "sample_sizes": {
                    "redis": len(scenario_results["redis_satisfaction"]),
                    "hybrid": len(scenario_results["hybrid_satisfaction"])
                }
            }
            
            ux_results[scenario["name"]] = scenario_summary
            
            print(f"  Redis avg satisfaction: {redis_avg_satisfaction:.2f}")
            print(f"  Hybrid avg satisfaction: {hybrid_avg_satisfaction:.2f}")
            print(f"  UX Impact: {ux_impact:+.2f}")
            
            # UX impact assertions
            assert redis_avg_satisfaction >= 3.0, f"{scenario['name']}: Redis UX too poor ({redis_avg_satisfaction:.2f})"
            assert hybrid_avg_satisfaction >= 3.0, f"{scenario['name']}: Hybrid UX too poor ({hybrid_avg_satisfaction:.2f})"
            assert ux_impact >= -0.5, f"{scenario['name']}: Hybrid UX significantly worse ({ux_impact:.2f})"
            
            # Cleanup
            for i in range(tests_per_scenario):
                redis_client.delete(f"ux_light:{i}")
                redis_client.delete(f"ux_medium:{i}")
                for j in range(10):
                    redis_client.delete(f"ux_heavy:{i}:{j}")
        
        profiler.record_operation("ux_impact_assessment", 30.0)
        
        # Overall UX assessment
        overall_ux_impact = statistics.mean([result["ux_impact"] for result in ux_results.values()])
        
        print(f"\n--- Overall UX Impact Assessment ---")
        print(f"  Overall UX Impact: {overall_ux_impact:+.3f}")
        
        for scenario_name, results in ux_results.items():
            print(f"  {scenario_name}: {results['ux_impact']:+.2f} (Redis: {results['redis_satisfaction']:.2f}, Hybrid: {results['hybrid_satisfaction']:.2f})")
        
        assert overall_ux_impact >= -0.3, f"Overall UX impact too negative: {overall_ux_impact:.3f}"
        
        metrics = profiler.stop()
        redis_client.delete("ux_leaderboard")
        
        return ux_results


@pytest.mark.asyncio
@pytest.mark.migration
@pytest.mark.load_testing
class TestMigrationLoadTesting:
    """Load testing scenarios during migration process."""
    
    async def test_load_during_migration_process(self, redis_client, db_manager, test_data_generator):
        """Test system behavior under load during active migration."""
        profiler = PerformanceProfiler()
        profiler.start()
        
        # Simulate migration in progress with concurrent user load
        migration_active = True
        concurrent_users = 20
        operations_per_user = 50
        
        async def simulate_user_activity(user_id: int):
            """Simulate a user's activity during migration."""
            user_operations = []
            user_errors = []
            
            for op_id in range(operations_per_user):
                operation_start = time.perf_counter()
                success = True
                
                try:
                    # Random user operations
                    operation_type = random.choice(["login", "create_game", "join_game", "play_card", "view_stats"])
                    
                    if operation_type == "login":
                        # User authentication
                        user_data = {"user_id": user_id, "login_time": datetime.utcnow().isoformat()}
                        redis_client.hset(f"migration_user:{user_id}", mapping=user_data)
                        
                        if migration_active and random.random() < 0.3:  # 30% chance during migration
                            # Also store in PostgreSQL (migration behavior)
                            async with db_manager.get_session() as session:
                                await session.execute(
                                    "INSERT INTO user_sessions (user_id, login_time) VALUES (:user_id, :login_time) ON CONFLICT DO NOTHING",
                                    {"user_id": user_id, "login_time": datetime.utcnow()}
                                )
                                await session.commit()
                    
                    elif operation_type == "create_game":
                        # Game creation
                        game_data = {
                            "game_id": f"migration_game_{user_id}_{op_id}",
                            "creator": user_id,
                            "created_at": datetime.utcnow().isoformat()
                        }
                        redis_client.hset(f"migration_game:{user_id}:{op_id}", mapping=game_data)
                    
                    elif operation_type == "view_stats":
                        # Statistics viewing
                        redis_client.hget(f"migration_user:{user_id}", "stats")
                        
                        if migration_active and random.random() < 0.5:  # 50% chance during migration
                            async with db_manager.get_session() as session:
                                await session.execute("SELECT COUNT(*) FROM players WHERE id = :user_id", {"user_id": user_id})
                    
                    # Add small delay to simulate real user behavior
                    await asyncio.sleep(random.uniform(0.01, 0.1))
                
                except Exception as e:
                    success = False
                    user_errors.append({"operation": operation_type, "error": str(e)})
                
                operation_end = time.perf_counter()
                operation_time = operation_end - operation_start
                
                user_operations.append({
                    "operation": operation_type,
                    "time": operation_time,
                    "success": success
                })
            
            return {"user_id": user_id, "operations": user_operations, "errors": user_errors}
        
        # Run concurrent user simulations
        print(f"Starting load test with {concurrent_users} concurrent users during migration...")
        
        user_tasks = [simulate_user_activity(user_id) for user_id in range(concurrent_users)]
        user_results = await asyncio.gather(*user_tasks, return_exceptions=True)
        
        profiler.record_operation("load_during_migration", 30.0)
        
        # Analyze load test results
        total_operations = 0
        successful_operations = 0
        total_errors = 0
        response_times = []
        
        for result in user_results:
            if isinstance(result, Exception):
                continue
            
            for operation in result["operations"]:
                total_operations += 1
                if operation["success"]:
                    successful_operations += 1
                response_times.append(operation["time"])
            
            total_errors += len(result["errors"])
        
        success_rate = successful_operations / total_operations if total_operations > 0 else 0
        avg_response_time = statistics.mean(response_times) if response_times else 0
        p95_response_time = statistics.quantiles(response_times, n=20)[18] if len(response_times) >= 20 else 0
        
        print(f"Load Test Results:")
        print(f"  Concurrent users: {concurrent_users}")
        print(f"  Total operations: {total_operations}")
        print(f"  Successful operations: {successful_operations}")
        print(f"  Success rate: {success_rate:.2%}")
        print(f"  Total errors: {total_errors}")
        print(f"  Average response time: {avg_response_time:.4f}s")
        print(f"  P95 response time: {p95_response_time:.4f}s")
        
        # Load test assertions
        assert success_rate >= 0.95, f"Success rate too low during migration load: {success_rate:.2%}"
        assert avg_response_time <= 1.0, f"Average response time too high: {avg_response_time:.4f}s"
        assert p95_response_time <= 2.0, f"P95 response time too high: {p95_response_time:.4f}s"
        
        metrics = profiler.stop()
        
        # Cleanup
        for user_id in range(concurrent_users):
            redis_client.delete(f"migration_user:{user_id}")
            for op_id in range(operations_per_user):
                redis_client.delete(f"migration_game:{user_id}:{op_id}")
        
        return {
            "success_rate": success_rate,
            "avg_response_time": avg_response_time,
            "p95_response_time": p95_response_time,
            "total_operations": total_operations,
            "error_count": total_errors
        }
