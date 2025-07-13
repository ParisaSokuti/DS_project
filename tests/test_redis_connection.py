#!/usr/bin/env python3
"""
Test Redis connection and basic operations
"""
import redis
import time
import json

def test_redis_connection():
    """Test basic Redis connection and operations"""
    print("=== Testing Redis Connection ===")
    
    try:
        # Test basic connection
        r = redis.Redis(host='localhost', port=6379, db=0, socket_timeout=5.0)
        print("1. Testing ping...")
        result = r.ping()
        print(f"   Ping result: {result}")
        
        # Test set/get
        print("2. Testing set/get...")
        test_key = "test_key_123"
        test_value = "test_value_123"
        r.set(test_key, test_value)
        retrieved = r.get(test_key)
        print(f"   Set/get result: {retrieved}")
        
        # Test hset/hgetall (the problematic operation)
        print("3. Testing hset/hgetall...")
        hash_key = "test_hash_123"
        hash_data = {
            "field1": "value1",
            "field2": json.dumps({"nested": "data"}),
            "field3": "value3"
        }
        
        r.hset(hash_key, mapping=hash_data)
        print("   hset completed")
        
        start_time = time.time()
        retrieved_hash = r.hgetall(hash_key)
        elapsed = time.time() - start_time
        print(f"   hgetall completed in {elapsed:.3f}s")
        print(f"   Retrieved hash: {retrieved_hash}")
        
        # Test with game-specific key pattern
        print("4. Testing game-specific key...")
        game_key = "game:9999:state"
        game_data = {
            "phase": "waiting_for_players",
            "players": json.dumps(["arvin"]),
            "created_at": str(int(time.time()))
        }
        
        r.hset(game_key, mapping=game_data)
        print("   Game hset completed")
        
        start_time = time.time()
        game_state = r.hgetall(game_key)
        elapsed = time.time() - start_time
        print(f"   Game hgetall completed in {elapsed:.3f}s")
        print(f"   Game state: {game_state}")
        
        # Check if key exists
        exists = r.exists(game_key)
        print(f"   Key exists: {exists}")
        
        # Clean up
        r.delete(test_key, hash_key, game_key)
        print("5. Cleanup completed")
        
        print("✅ Redis connection test passed!")
        return True
        
    except Exception as e:
        print(f"❌ Redis connection test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_redis_server_status():
    """Check Redis server status"""
    print("\n=== Testing Redis Server Status ===")
    
    try:
        r = redis.Redis(host='localhost', port=6379, db=0)
        info = r.info()
        
        print(f"Redis version: {info.get('redis_version')}")
        print(f"Connected clients: {info.get('connected_clients')}")
        print(f"Used memory: {info.get('used_memory_human')}")
        print(f"Total commands processed: {info.get('total_commands_processed')}")
        
        # Check for any slow operations
        slowlog = r.slowlog_get(10)
        if slowlog:
            print(f"Recent slow operations: {len(slowlog)}")
            for entry in slowlog:
                print(f"  - {entry['command']} took {entry['duration']}μs")
        else:
            print("No slow operations detected")
            
    except Exception as e:
        print(f"❌ Redis server status check failed: {e}")

if __name__ == "__main__":
    success = test_redis_connection()
    test_redis_server_status()
    
    if success:
        print("\n✅ Redis appears to be working correctly")
    else:
        print("\n❌ Redis has issues that need to be addressed")
