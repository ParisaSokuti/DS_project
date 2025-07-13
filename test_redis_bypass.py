#!/usr/bin/env python3
"""
Test script to debug Redis hanging issue using bypass mode
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.redis_manager_resilient import ResilientRedisManager

def test_redis_bypass():
    """Test Redis operations with bypass mode enabled"""
    print("=== Testing Redis with bypass mode ===")
    
    # Create Redis manager
    redis_manager = ResilientRedisManager()
    
    # Enable bypass mode
    redis_manager.bypass_circuit_breaker = True
    print("Bypass mode enabled")
    
    # Test room creation
    print("\n1. Testing room creation...")
    room_code = "9999"
    success = redis_manager.create_room(room_code)
    print(f"Create room result: {success}")
    
    # Test get_game_state
    print("\n2. Testing get_game_state...")
    try:
        game_state = redis_manager.get_game_state(room_code)
        print(f"Game state retrieved: {game_state}")
    except Exception as e:
        print(f"Error in get_game_state: {e}")
        import traceback
        traceback.print_exc()
    
    # Test direct Redis connection
    print("\n3. Testing direct Redis connection...")
    try:
        redis_manager.redis.ping()
        print("Direct Redis ping successful")
        
        # Test specific key
        key = f"game:{room_code}:state"
        exists = redis_manager.redis.exists(key)
        print(f"Key {key} exists: {exists}")
        
        if exists:
            raw_data = redis_manager.redis.hgetall(key)
            print(f"Raw data: {raw_data}")
    except Exception as e:
        print(f"Direct Redis error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_redis_bypass()
