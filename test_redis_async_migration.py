#!/usr/bin/env python3
"""
Test script for async Redis migration

This script tests:
1. AsyncRedisManager functionality
2. HybridRedisManager compatibility
3. Performance comparisons
4. Error handling scenarios
"""

import asyncio
import time
import json
import logging
from typing import List, Dict

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_async_redis_manager():
    """Test AsyncRedisManager functionality"""
    logger.info("Testing AsyncRedisManager...")
    
    try:
        from async_redis_manager import AsyncRedisManager
        
        redis_manager = AsyncRedisManager()
        
        # Test connection
        logger.info("Testing connection...")
        connected = await redis_manager.connect()
        assert connected, "Failed to connect to Redis"
        logger.info("✓ Connection successful")
        
        # Test room operations
        logger.info("Testing room operations...")
        room_code = f"TEST_ROOM_{int(time.time())}"
        
        # Create room
        success = await redis_manager.create_room(room_code)
        assert success, "Failed to create room"
        logger.info(f"✓ Created room {room_code}")
        
        # Check room exists
        exists = await redis_manager.room_exists(room_code)
        assert exists, "Room should exist"
        logger.info("✓ Room exists check passed")
        
        # Test player operations
        logger.info("Testing player operations...")
        player_data = {
            'player_id': 'test_player_1',
            'username': 'TestPlayer1',
            'connection_status': 'active'
        }
        
        # Add player to room
        success = await redis_manager.add_player_to_room(room_code, player_data)
        assert success, "Failed to add player to room"
        logger.info("✓ Added player to room")
        
        # Get room players
        players = await redis_manager.get_room_players(room_code)
        assert len(players) == 1, f"Expected 1 player, got {len(players)}"
        assert players[0]['username'] == 'TestPlayer1', "Player data mismatch"
        logger.info("✓ Retrieved room players")
        
        # Test session operations
        logger.info("Testing session operations...")
        session_data = {
            'room_code': room_code,
            'username': 'TestPlayer1',
            'connection_status': 'active'
        }
        
        # Save session
        success = await redis_manager.save_player_session('test_player_1', session_data)
        assert success, "Failed to save player session"
        logger.info("✓ Saved player session")
        
        # Get session
        retrieved_session = await redis_manager.get_player_session('test_player_1')
        assert retrieved_session['username'] == 'TestPlayer1', "Session data mismatch"
        logger.info("✓ Retrieved player session")
        
        # Test game state operations
        logger.info("Testing game state operations...")
        game_state = {
            'phase': 'waiting_for_players',
            'players': ['TestPlayer1'],
            'created_at': str(int(time.time())),
            'last_activity': str(int(time.time()))
        }
        
        # Save game state
        success = await redis_manager.save_game_state(room_code, game_state)
        assert success, "Failed to save game state"
        logger.info("✓ Saved game state")
        
        # Get game state
        retrieved_state = await redis_manager.get_game_state(room_code)
        assert retrieved_state['phase'] == 'waiting_for_players', "Game state mismatch"
        assert len(retrieved_state['players']) == 1, "Player count mismatch"
        logger.info("✓ Retrieved game state")
        
        # Test cleanup
        logger.info("Testing cleanup...")
        success = await redis_manager.clear_room(room_code)
        assert success, "Failed to clear room"
        
        success = await redis_manager.delete_player_session('test_player_1')
        assert success, "Failed to delete player session"
        logger.info("✓ Cleanup successful")
        
        # Test performance metrics
        metrics = redis_manager.get_performance_metrics()
        logger.info(f"Performance metrics: {metrics}")
        
        # Disconnect
        await redis_manager.disconnect()
        logger.info("✓ Disconnected successfully")
        
        logger.info("✅ AsyncRedisManager tests passed!")
        return True
        
    except Exception as e:
        logger.error(f"❌ AsyncRedisManager test failed: {e}")
        return False

async def test_hybrid_redis_manager():
    """Test HybridRedisManager functionality"""
    logger.info("Testing HybridRedisManager...")
    
    try:
        from redis_manager_hybrid import HybridRedisManager
        
        redis_manager = HybridRedisManager()
        
        # Test async connection
        logger.info("Testing async connection...")
        connected = await redis_manager.connect_async()
        assert connected, "Failed to connect to Redis (async)"
        logger.info("✓ Async connection successful")
        
        room_code = f"HYBRID_TEST_{int(time.time())}"
        
        # Test async operations
        logger.info("Testing async operations...")
        success = await redis_manager.create_room_async(room_code)
        assert success, "Failed to create room (async)"
        
        exists = await redis_manager.room_exists_async(room_code)
        assert exists, "Room should exist (async)"
        logger.info("✓ Async operations successful")
        
        # Test sync operations (should work with async backend)
        logger.info("Testing sync operations with async backend...")
        player_data = {
            'player_id': 'hybrid_test_player',
            'username': 'HybridTestPlayer',
            'connection_status': 'active'
        }
        
        # Use sync interface with async backend
        success = redis_manager.add_player_to_room(room_code, player_data)
        assert success, "Failed to add player (sync interface)"
        
        players = redis_manager.get_room_players(room_code)
        assert len(players) == 1, f"Expected 1 player, got {len(players)}"
        logger.info("✓ Sync interface with async backend successful")
        
        # Cleanup
        await redis_manager.clear_room_async(room_code)
        await redis_manager.disconnect_async()
        
        logger.info("✅ HybridRedisManager tests passed!")
        return True
        
    except Exception as e:
        logger.error(f"❌ HybridRedisManager test failed: {e}")
        return False

async def performance_comparison():
    """Compare performance between old blocking and new async operations"""
    logger.info("Running performance comparison...")
    
    try:
        from async_redis_manager import AsyncRedisManager
        from redis_manager import RedisManager
        
        # Test with async manager
        async_manager = AsyncRedisManager()
        await async_manager.connect()
        
        # Test with sync manager (for comparison)
        sync_manager = RedisManager()
        
        num_operations = 10
        room_code = f"PERF_TEST_{int(time.time())}"
        
        # Async performance test
        start_time = time.time()
        for i in range(num_operations):
            await async_manager.create_room(f"{room_code}_async_{i}")
            await async_manager.room_exists(f"{room_code}_async_{i}")
            await async_manager.clear_room(f"{room_code}_async_{i}")
        async_time = time.time() - start_time
        
        # Sync performance test
        start_time = time.time()
        for i in range(num_operations):
            sync_manager.create_room(f"{room_code}_sync_{i}")
            sync_manager.room_exists(f"{room_code}_sync_{i}")
            sync_manager.clear_room(f"{room_code}_sync_{i}")
        sync_time = time.time() - start_time
        
        # Get metrics
        async_metrics = async_manager.get_performance_metrics()
        sync_metrics = sync_manager.get_performance_metrics()
        
        logger.info(f"Performance Results:")
        logger.info(f"  Async operations: {async_time:.3f}s for {num_operations} operations")
        logger.info(f"  Sync operations: {sync_time:.3f}s for {num_operations} operations")
        logger.info(f"  Async avg latency: {async_metrics.get('avg_latency', 0):.3f}s")
        logger.info(f"  Sync avg latency: {sync_metrics.get('avg_latency', 0):.3f}s")
        
        improvement = ((sync_time - async_time) / sync_time) * 100 if sync_time > 0 else 0
        logger.info(f"  Performance improvement: {improvement:.1f}%")
        
        await async_manager.disconnect()
        
        logger.info("✅ Performance comparison completed!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Performance comparison failed: {e}")
        return False

async def test_error_handling():
    """Test error handling scenarios"""
    logger.info("Testing error handling...")
    
    try:
        from async_redis_manager import AsyncRedisManager
        
        # Test with invalid Redis connection
        redis_manager = AsyncRedisManager(host='invalid_host', port=9999)
        
        # Should fail to connect
        connected = await redis_manager.connect()
        assert not connected, "Should fail to connect to invalid host"
        logger.info("✓ Invalid connection properly handled")
        
        # Test operations without connection
        success = await redis_manager.create_room("test_room")
        assert not success, "Operations should fail without connection"
        logger.info("✓ Operations properly fail without connection")
        
        logger.info("✅ Error handling tests passed!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error handling test failed: {e}")
        return False

async def stress_test():
    """Stress test with multiple concurrent operations"""
    logger.info("Running stress test...")
    
    try:
        from async_redis_manager import AsyncRedisManager
        
        redis_manager = AsyncRedisManager(pool_size=20)
        connected = await redis_manager.connect()
        assert connected, "Failed to connect for stress test"
        
        num_concurrent = 50
        base_room_code = f"STRESS_TEST_{int(time.time())}"
        
        async def create_room_and_players(room_index):
            """Create room and add players concurrently"""
            room_code = f"{base_room_code}_{room_index}"
            
            # Create room
            await redis_manager.create_room(room_code)
            
            # Add multiple players
            for player_index in range(4):
                player_data = {
                    'player_id': f'player_{room_index}_{player_index}',
                    'username': f'Player{room_index}_{player_index}',
                    'connection_status': 'active'
                }
                await redis_manager.add_player_to_room(room_code, player_data)
            
            # Save game state
            game_state = {
                'phase': 'waiting_for_players',
                'players': [f'Player{room_index}_{i}' for i in range(4)],
                'created_at': str(int(time.time())),
                'last_activity': str(int(time.time()))
            }
            await redis_manager.save_game_state(room_code, game_state)
            
            # Verify operations
            players = await redis_manager.get_room_players(room_code)
            assert len(players) == 4, f"Expected 4 players, got {len(players)}"
            
            state = await redis_manager.get_game_state(room_code)
            assert state['phase'] == 'waiting_for_players', "Game state mismatch"
            
            # Cleanup
            await redis_manager.clear_room(room_code)
            
            return room_index
        
        # Run concurrent operations
        start_time = time.time()
        tasks = [create_room_and_players(i) for i in range(num_concurrent)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        stress_time = time.time() - start_time
        
        # Check results
        successful = sum(1 for r in results if not isinstance(r, Exception))
        failed = len(results) - successful
        
        logger.info(f"Stress test results:")
        logger.info(f"  Concurrent operations: {num_concurrent}")
        logger.info(f"  Successful: {successful}")
        logger.info(f"  Failed: {failed}")
        logger.info(f"  Total time: {stress_time:.3f}s")
        logger.info(f"  Operations per second: {(num_concurrent * 8) / stress_time:.1f}")  # 8 ops per room
        
        # Get final metrics
        metrics = redis_manager.get_performance_metrics()
        logger.info(f"  Final metrics: {metrics}")
        
        await redis_manager.disconnect()
        
        assert successful >= num_concurrent * 0.95, f"Too many failures: {failed}/{num_concurrent}"
        
        logger.info("✅ Stress test passed!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Stress test failed: {e}")
        return False

async def main():
    """Run all tests"""
    logger.info("Starting Redis async migration tests...")
    
    tests = [
        ("AsyncRedisManager Basic Tests", test_async_redis_manager),
        ("HybridRedisManager Tests", test_hybrid_redis_manager),
        ("Performance Comparison", performance_comparison),
        ("Error Handling Tests", test_error_handling),
        ("Stress Test", stress_test),
    ]
    
    results = {}
    
    for test_name, test_func in tests:
        logger.info(f"\n{'='*50}")
        logger.info(f"Running: {test_name}")
        logger.info(f"{'='*50}")
        
        try:
            result = await test_func()
            results[test_name] = result
        except Exception as e:
            logger.error(f"Test {test_name} crashed: {e}")
            results[test_name] = False
        
        if results[test_name]:
            logger.info(f"✅ {test_name} PASSED")
        else:
            logger.error(f"❌ {test_name} FAILED")
    
    # Summary
    logger.info(f"\n{'='*50}")
    logger.info("TEST SUMMARY")
    logger.info(f"{'='*50}")
    
    passed = sum(1 for result in results.values() if result)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        logger.info(f"{test_name}: {status}")
    
    logger.info(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        logger.info("🎉 ALL TESTS PASSED! Ready for migration.")
    else:
        logger.error("❌ Some tests failed. Please fix issues before migration.")
    
    return passed == total

if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
