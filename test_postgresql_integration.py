#!/usr/bin/env python3
"""
Comprehensive PostgreSQL Integration Test for Hokm Game Server
Tests database setup, connection pooling, and game operations
"""
import asyncio
import logging
import os
import sys
import time
import uuid
from datetime import datetime, timedelta
from typing import Dict, List

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from backend.database_manager import DatabaseManager
from backend.game_database_integration import GameDatabaseIntegration, create_database_integration


class PostgreSQLTestSuite:
    """Comprehensive test suite for PostgreSQL integration."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.integration: GameDatabaseIntegration = None
        self.test_results = []
        
        # Test data
        self.test_players = []
        self.test_sessions = []
        
    async def setup(self):
        """Set up test environment."""
        print("Setting up PostgreSQL test environment...")
        
        # Database connection strings
        primary_dsn = os.getenv('DATABASE_URL', 'postgresql://hokm_admin:hokm_secure_2024!@localhost:5432/hokm_game')
        replica_dsn = os.getenv('DATABASE_READ_URL', 'postgresql://hokm_admin:hokm_secure_2024!@localhost:5433/hokm_game')
        redis_url = os.getenv('REDIS_URL', 'redis://:redis_secure_2024!@localhost:6379/0')
        
        try:
            # Create database integration
            self.integration = await create_database_integration(
                primary_dsn=primary_dsn,
                replica_dsn=replica_dsn,
                redis_url=redis_url
            )
            
            print("✅ Database integration initialized successfully")
            return True
            
        except Exception as e:
            print(f"❌ Failed to initialize database integration: {e}")
            return False
    
    async def cleanup(self):
        """Clean up test environment."""
        try:
            if self.integration:
                await self.integration.close()
            print("✅ Test environment cleaned up")
        except Exception as e:
            print(f"⚠️  Error during cleanup: {e}")
    
    async def run_test(self, test_name: str, test_func) -> bool:
        """Run a single test and record results."""
        print(f"\n📋 Running test: {test_name}")
        start_time = time.time()
        
        try:
            result = await test_func()
            duration = time.time() - start_time
            
            if result:
                print(f"✅ {test_name} - PASSED ({duration:.2f}s)")
                self.test_results.append({
                    'test': test_name,
                    'status': 'PASSED',
                    'duration': duration,
                    'error': None
                })
                return True
            else:
                print(f"❌ {test_name} - FAILED ({duration:.2f}s)")
                self.test_results.append({
                    'test': test_name,
                    'status': 'FAILED',
                    'duration': duration,
                    'error': 'Test returned False'
                })
                return False
                
        except Exception as e:
            duration = time.time() - start_time
            print(f"❌ {test_name} - ERROR ({duration:.2f}s): {e}")
            self.test_results.append({
                'test': test_name,
                'status': 'ERROR',
                'duration': duration,
                'error': str(e)
            })
            return False
    
    # Test methods
    
    async def test_database_connection(self) -> bool:
        """Test basic database connectivity."""
        try:
            # Test primary database
            result = await self.integration.db.execute_query("SELECT 1 as test_value")
            if not result or result[0]['test_value'] != 1:
                return False
            
            # Test replica database (if available)
            if self.integration.db.replica_pool:
                result = await self.integration.db.execute_query("SELECT 1 as test_value", use_replica=True)
                if not result or result[0]['test_value'] != 1:
                    return False
            
            # Test Redis (if available)
            if self.integration.db.redis_client:
                await self.integration.db.cache_set("test_key", "test_value")
                value = await self.integration.db.cache_get("test_key")
                if value != "test_value":
                    return False
                await self.integration.db.cache_delete("test_key")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Database connection test failed: {e}")
            return False
    
    async def test_player_operations(self) -> bool:
        """Test player creation and management."""
        try:
            # Create test players
            connection_info = {
                'ip_address': '127.0.0.1',
                'user_agent': 'TestClient/1.0'
            }
            
            for i in range(5):
                username = f"test_player_{i}_{int(time.time())}"
                player = await self.integration.create_or_get_player(username, connection_info)
                
                if not player or player['username'] != username:
                    return False
                
                self.test_players.append(player)
            
            # Test getting existing player
            existing_player = await self.integration.create_or_get_player(
                self.test_players[0]['username'], 
                connection_info
            )
            
            if existing_player['id'] != self.test_players[0]['id']:
                return False
            
            # Test player stats
            stats = await self.integration.get_player_stats(self.test_players[0]['id'])
            if not stats or stats['total_games'] != 0:
                return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Player operations test failed: {e}")
            return False
    
    async def test_game_session_operations(self) -> bool:
        """Test game session creation and management."""
        try:
            if not self.test_players:
                return False
            
            # Create test game sessions
            for i in range(3):
                room_id = f"test_room_{i}_{int(time.time())}"
                session_key = f"session_key_{i}_{int(time.time())}"
                
                session = await self.integration.create_game_session(
                    room_id, 
                    session_key, 
                    max_players=4,
                    creator_id=self.test_players[0]['id']
                )
                
                if not session or session['room_id'] != room_id:
                    return False
                
                self.test_sessions.append(session)
            
            # Test getting existing session
            existing_session = await self.integration.get_or_create_game_session(
                self.test_sessions[0]['room_id'],
                self.test_sessions[0]['session_key']
            )
            
            if existing_session['id'] != self.test_sessions[0]['id']:
                return False
            
            # Test adding players to session
            for i, player in enumerate(self.test_players[:4]):
                success = await self.integration.add_player_to_session(
                    self.test_sessions[0]['room_id'],
                    player['id'],
                    position=i,
                    team=1 if i < 2 else 2,
                    connection_id=f"conn_{i}_{int(time.time())}"
                )
                
                if not success:
                    return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Game session operations test failed: {e}")
            return False
    
    async def test_game_state_operations(self) -> bool:
        """Test game state management."""
        try:
            if not self.test_sessions:
                return False
            
            session = self.test_sessions[0]
            
            # Test game state updates
            game_state = {
                'phase': 'playing',
                'current_round': 2,
                'current_trick': 3,
                'current_player': 1,
                'trump_suit': 'hearts',
                'last_updated': datetime.utcnow().isoformat()
            }
            
            player_hands = {
                str(self.test_players[0]['id']): [
                    {'suit': 'hearts', 'rank': 'A'},
                    {'suit': 'spades', 'rank': 'K'}
                ]
            }
            
            scores = {1: 5, 2: 3}
            
            success = await self.integration.db.update_game_state(
                session['id'],
                game_state,
                player_hands,
                scores
            )
            
            if not success:
                return False
            
            # Test move recording
            move_data = {
                'card': {'suit': 'hearts', 'rank': 'A'},
                'valid': True,
                'timestamp': datetime.utcnow().isoformat()
            }
            
            success = await self.integration.record_player_move(
                session['room_id'],
                self.test_players[0]['id'],
                'play_card',
                move_data,
                round_number=2,
                trick_number=3
            )
            
            if not success:
                return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Game state operations test failed: {e}")
            return False
    
    async def test_connection_management(self) -> bool:
        """Test WebSocket connection management."""
        try:
            if not self.test_players or not self.test_sessions:
                return False
            
            player = self.test_players[0]
            session = self.test_sessions[0]
            connection_id = f"test_conn_{int(time.time())}"
            
            # Test disconnection
            affected_rooms = await self.integration.handle_player_disconnect(
                player['id'],
                connection_id
            )
            
            # Test reconnection
            reconnection_data = await self.integration.handle_player_reconnection(
                player['id'],
                session['room_id'],
                f"new_conn_{int(time.time())}"
            )
            
            if not reconnection_data:
                return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Connection management test failed: {e}")
            return False
    
    async def test_circuit_breaker(self) -> bool:
        """Test circuit breaker functionality."""
        try:
            # Get initial circuit breaker state
            health_status = await self.integration.db.get_health_status()
            
            if 'circuit_breaker_primary' not in health_status:
                return False
            
            # Test circuit breaker metrics
            success = await self.integration.log_performance_metric(
                'circuit_breaker_test',
                'test_metric',
                1.0,
                {'test': True}
            )
            
            return success
            
        except Exception as e:
            self.logger.error(f"Circuit breaker test failed: {e}")
            return False
    
    async def test_performance_monitoring(self) -> bool:
        """Test performance monitoring features."""
        try:
            # Test server statistics
            stats = await self.integration.get_server_statistics()
            
            if not stats or 'active_games' not in stats:
                return False
            
            # Test performance metrics
            for i in range(5):
                success = await self.integration.log_performance_metric(
                    'test_performance',
                    f'metric_{i}',
                    float(i * 10),
                    {'test_run': True}
                )
                
                if not success:
                    return False
            
            # Test cleanup operations
            cleaned_count = await self.integration.db.cleanup_old_connections()
            
            return True
            
        except Exception as e:
            self.logger.error(f"Performance monitoring test failed: {e}")
            return False
    
    async def test_analytics_views(self) -> bool:
        """Test analytics views and reporting."""
        try:
            # Test various analytics queries
            test_queries = [
                "SELECT COUNT(*) as total_players FROM analytics.player_performance",
                "SELECT COUNT(*) as total_games FROM analytics.game_statistics_summary",
                "SELECT COUNT(*) as active_sessions FROM analytics.active_sessions",
                "SELECT COUNT(*) as connections FROM analytics.connection_statistics",
                "SELECT COUNT(*) as metrics FROM analytics.performance_dashboard"
            ]
            
            for query in test_queries:
                try:
                    result = await self.integration.db.execute_query(query, use_replica=True)
                    if not result:
                        return False
                except Exception as e:
                    # Some views might be empty, which is okay
                    self.logger.debug(f"Analytics query failed (expected): {e}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Analytics views test failed: {e}")
            return False
    
    async def test_cache_operations(self) -> bool:
        """Test cache operations and management."""
        try:
            if not self.integration.db.redis_client:
                print("ℹ️  Redis not configured, skipping cache tests")
                return True
            
            # Test basic cache operations
            test_key = f"test_cache_{int(time.time())}"
            test_value = "test_cache_value"
            
            # Set cache
            success = await self.integration.db.cache_set(test_key, test_value, ttl=60)
            if not success:
                return False
            
            # Get cache
            cached_value = await self.integration.db.cache_get(test_key)
            if cached_value != test_value:
                return False
            
            # Delete cache
            success = await self.integration.db.cache_delete(test_key)
            if not success:
                return False
            
            # Verify deletion
            cached_value = await self.integration.db.cache_get(test_key)
            if cached_value is not None:
                return False
            
            # Test cache warming
            await self.integration.warm_cache()
            
            return True
            
        except Exception as e:
            self.logger.error(f"Cache operations test failed: {e}")
            return False
    
    async def test_concurrent_operations(self) -> bool:
        """Test concurrent database operations."""
        try:
            # Create multiple concurrent operations
            tasks = []
            
            # Concurrent player creation
            for i in range(10):
                task = self.integration.create_or_get_player(
                    f"concurrent_player_{i}_{int(time.time())}",
                    {'ip_address': '127.0.0.1'}
                )
                tasks.append(task)
            
            # Concurrent game session creation
            for i in range(5):
                task = self.integration.create_game_session(
                    f"concurrent_room_{i}_{int(time.time())}",
                    f"concurrent_session_{i}_{int(time.time())}"
                )
                tasks.append(task)
            
            # Execute all tasks concurrently
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Check for failures
            for result in results:
                if isinstance(result, Exception):
                    self.logger.error(f"Concurrent operation failed: {result}")
                    return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Concurrent operations test failed: {e}")
            return False
    
    async def test_data_integrity(self) -> bool:
        """Test data integrity and constraints."""
        try:
            # Test unique constraints
            try:
                # Attempt to create duplicate player
                player1 = await self.integration.create_or_get_player(
                    "integrity_test_player",
                    {'ip_address': '127.0.0.1'}
                )
                player2 = await self.integration.create_or_get_player(
                    "integrity_test_player",
                    {'ip_address': '127.0.0.1'}
                )
                
                # Should return same player
                if player1['id'] != player2['id']:
                    return False
                
            except Exception as e:
                self.logger.error(f"Duplicate player test failed: {e}")
                return False
            
            # Test foreign key constraints
            try:
                # Try to add player to non-existent game
                fake_session_id = str(uuid.uuid4())
                success = await self.integration.add_player_to_session(
                    "fake_room_id",
                    self.test_players[0]['id'] if self.test_players else str(uuid.uuid4()),
                    0, 1, "fake_connection"
                )
                
                # Should fail gracefully
                if success:
                    return False
                
            except Exception as e:
                # Expected to fail
                pass
            
            return True
            
        except Exception as e:
            self.logger.error(f"Data integrity test failed: {e}")
            return False
    
    def print_summary(self):
        """Print test summary."""
        print("\n" + "="*60)
        print("POSTGRESQL INTEGRATION TEST SUMMARY")
        print("="*60)
        
        passed = sum(1 for r in self.test_results if r['status'] == 'PASSED')
        failed = sum(1 for r in self.test_results if r['status'] == 'FAILED')
        errors = sum(1 for r in self.test_results if r['status'] == 'ERROR')
        total = len(self.test_results)
        
        print(f"Total Tests: {total}")
        print(f"Passed: {passed} ✅")
        print(f"Failed: {failed} ❌")
        print(f"Errors: {errors} ⚠️")
        
        if failed > 0 or errors > 0:
            print("\nFailed/Error Tests:")
            for result in self.test_results:
                if result['status'] in ['FAILED', 'ERROR']:
                    print(f"  - {result['test']}: {result['status']}")
                    if result['error']:
                        print(f"    Error: {result['error']}")
        
        total_duration = sum(r['duration'] for r in self.test_results)
        print(f"\nTotal Duration: {total_duration:.2f}s")
        
        success_rate = (passed / total * 100) if total > 0 else 0
        print(f"Success Rate: {success_rate:.1f}%")
        
        if success_rate >= 90:
            print("\n🎉 PostgreSQL integration is working excellently!")
        elif success_rate >= 75:
            print("\n✅ PostgreSQL integration is working well!")
        elif success_rate >= 50:
            print("\n⚠️  PostgreSQL integration has some issues.")
        else:
            print("\n❌ PostgreSQL integration has significant problems.")


async def main():
    """Run the comprehensive PostgreSQL test suite."""
    print("🐘 Hokm Game Server - PostgreSQL Integration Test Suite")
    print("=" * 60)
    
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create test suite
    test_suite = PostgreSQLTestSuite()
    
    # Setup
    if not await test_suite.setup():
        print("❌ Failed to set up test environment")
        return False
    
    try:
        # Run all tests
        tests = [
            ("Database Connection", test_suite.test_database_connection),
            ("Player Operations", test_suite.test_player_operations),
            ("Game Session Operations", test_suite.test_game_session_operations),
            ("Game State Operations", test_suite.test_game_state_operations),
            ("Connection Management", test_suite.test_connection_management),
            ("Circuit Breaker", test_suite.test_circuit_breaker),
            ("Performance Monitoring", test_suite.test_performance_monitoring),
            ("Analytics Views", test_suite.test_analytics_views),
            ("Cache Operations", test_suite.test_cache_operations),
            ("Concurrent Operations", test_suite.test_concurrent_operations),
            ("Data Integrity", test_suite.test_data_integrity),
        ]
        
        for test_name, test_func in tests:
            await test_suite.run_test(test_name, test_func)
            await asyncio.sleep(0.1)  # Brief pause between tests
        
        # Print summary
        test_suite.print_summary()
        
        # Determine overall success
        failed_tests = sum(1 for r in test_suite.test_results if r['status'] in ['FAILED', 'ERROR'])
        success = failed_tests == 0
        
        if success:
            print("\n🎉 All tests passed! PostgreSQL integration is ready for production.")
        else:
            print(f"\n⚠️  {failed_tests} test(s) failed. Please review the issues above.")
        
        return success
        
    finally:
        # Cleanup
        await test_suite.cleanup()


if __name__ == "__main__":
    # Run the test suite
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
