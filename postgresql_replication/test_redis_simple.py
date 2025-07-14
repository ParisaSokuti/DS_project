#!/usr/bin/env python3
"""
Simplified Redis Master-Replica Testing
Tests Redis high availability setup for Hokm game using sync redis library
"""
import redis
import redis.sentinel
import time
import json
import logging
from datetime import datetime
from typing import Dict

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SimpleRedisHATest:
    """Simple Redis HA testing without asyncio dependencies"""
    
    def __init__(self):
        self.sentinel_hosts = [
            ('localhost', 26379),
            ('localhost', 26380),
            ('localhost', 26381)
        ]
        self.master_name = 'hokm-master'
        self.password = 'redis_game_password123'
        self.sentinel = None
        self.master_conn = None
        self.replica_conn = None
        
    def connect_to_sentinel(self) -> bool:
        """Connect to Redis Sentinel"""
        try:
            print("📡 Connecting to Redis Sentinel...")
            
            # Try to connect to any available sentinel
            for host, port in self.sentinel_hosts:
                try:
                    test_sentinel = redis.sentinel.Sentinel(
                        [(host, port)],
                        socket_timeout=5.0,
                        password=self.password
                    )
                    
                    # Test connection
                    masters = test_sentinel.discover_master(self.master_name)
                    print(f"✅ Sentinel connected via {host}:{port}, master at: {masters[0]}:{masters[1]}")
                    
                    # Use full sentinel configuration
                    self.sentinel = redis.sentinel.Sentinel(
                        self.sentinel_hosts,
                        socket_timeout=5.0,
                        password=self.password
                    )
                    return True
                    
                except Exception as e:
                    print(f"⚠️  Sentinel {host}:{port} failed: {e}")
                    continue
            
            print("❌ No Sentinels available")
            return False
            
        except Exception as e:
            print(f"❌ Sentinel connection failed: {e}")
            return False
    
    def connect_to_redis_instances(self) -> bool:
        """Connect to Redis master and replica"""
        try:
            print("🔗 Connecting to Redis instances...")
            
            if self.sentinel:
                try:
                    # Get master connection through Sentinel
                    self.master_conn = self.sentinel.master_for(
                        self.master_name,
                        socket_timeout=5.0,
                        password=self.password,
                        db=0
                    )
                    
                    # Test master connection
                    self.master_conn.ping()
                    print("✅ Master connection via Sentinel successful")
                    
                    # Try to get replica connection
                    try:
                        self.replica_conn = self.sentinel.slave_for(
                            self.master_name,
                            socket_timeout=5.0,
                            password=self.password,
                            db=0
                        )
                        self.replica_conn.ping()
                        print("✅ Replica connection via Sentinel successful")
                    except Exception as e:
                        print(f"⚠️  Replica via Sentinel failed: {e}")
                        # Try direct replica connection
                        self.replica_conn = redis.Redis(
                            host='localhost',
                            port=6380,
                            password=self.password,
                            db=0,
                            socket_timeout=5.0
                        )
                        self.replica_conn.ping()
                        print("✅ Direct replica connection successful")
                        
                except Exception as e:
                    print(f"⚠️  Sentinel connections failed: {e}, trying direct...")
                    raise
            else:
                # Direct connections fallback
                print("📡 Using direct Redis connections...")
                self.master_conn = redis.Redis(
                    host='localhost',
                    port=6379,
                    password=self.password,
                    db=0,
                    socket_timeout=5.0
                )
                
                self.replica_conn = redis.Redis(
                    host='localhost',
                    port=6380,
                    password=self.password,
                    db=0,
                    socket_timeout=5.0
                )
                
                # Test connections
                self.master_conn.ping()
                self.replica_conn.ping()
                print("✅ Direct connections established")
            
            return True
            
        except Exception as e:
            print(f"❌ Redis connection failed: {e}")
            return False
    
    def test_basic_connectivity(self) -> bool:
        """Test basic Redis connectivity"""
        try:
            print("\\n🧪 Testing basic connectivity...")
            
            # Test master
            master_ping = self.master_conn.ping()
            print(f"  Master ping: {'✅ OK' if master_ping else '❌ Failed'}")
            
            # Get master info
            master_info = self.master_conn.info('replication')
            print(f"  Master role: {master_info.get('role', 'unknown')}")
            print(f"  Connected replicas: {master_info.get('connected_slaves', 0)}")
            
            # Test replica
            try:
                replica_ping = self.replica_conn.ping()
                print(f"  Replica ping: {'✅ OK' if replica_ping else '❌ Failed'}")
                
                # Get replica info
                replica_info = self.replica_conn.info('replication')
                print(f"  Replica role: {replica_info.get('role', 'unknown')}")
                
                return master_ping and replica_ping
                
            except Exception as e:
                print(f"  Replica ping: ❌ Failed - {e}")
                return master_ping  # At least master works
                
        except Exception as e:
            print(f"❌ Basic connectivity test failed: {e}")
            return False
    
    def test_replication(self) -> bool:
        """Test Redis replication"""
        try:
            print("\\n🔄 Testing replication...")
            
            # Write to master
            test_key = f"replication_test_{int(time.time())}"
            test_value = f"hokm_test_{datetime.now().isoformat()}"
            
            print(f"  Writing to master: {test_key}")
            result = self.master_conn.set(test_key, test_value, ex=30)
            print(f"  Master write result: {'✅ OK' if result else '❌ Failed'}")
            
            if not result:
                return False
            
            # Wait for replication
            print("  Waiting for replication (3 seconds)...")
            time.sleep(3)
            
            # Read from replica
            try:
                replica_value = self.replica_conn.get(test_key)
                if replica_value:
                    replica_value = replica_value.decode('utf-8')
                    if replica_value == test_value:
                        print("  ✅ Replication successful - data matches")
                        return True
                    else:
                        print(f"  ❌ Data mismatch: expected '{test_value}', got '{replica_value}'")
                        return False
                else:
                    print("  ❌ Key not found on replica")
                    return False
                    
            except Exception as e:
                print(f"  ❌ Replica read failed: {e}")
                return False
                
        except Exception as e:
            print(f"❌ Replication test failed: {e}")
            return False
    
    def test_game_operations(self) -> bool:
        """Test game-specific operations"""
        try:
            print("\\n🎮 Testing game operations...")
            
            # Test session storage
            session_id = "test_session_12345"
            session_data = {
                "players": ["alice", "bob", "charlie", "david"],
                "game_state": "playing",
                "round": 3,
                "hokm": "hearts"
            }
            
            print(f"  Storing game session: {session_id}")
            
            # Store as hash
            pipe = self.master_conn.pipeline()
            pipe.hset(f"game_session:{session_id}", "data", json.dumps(session_data))
            pipe.expire(f"game_session:{session_id}", 3600)
            result = pipe.execute()
            
            print(f"  Session storage: {'✅ OK' if all(result) else '❌ Failed'}")
            
            # Wait for replication
            time.sleep(2)
            
            # Read from replica
            replica_data = self.replica_conn.hget(f"game_session:{session_id}", "data")
            if replica_data:
                replica_session = json.loads(replica_data.decode('utf-8'))
                if replica_session == session_data:
                    print("  ✅ Game session replication successful")
                else:
                    print("  ❌ Game session data mismatch")
                    return False
            else:
                print("  ❌ Game session not found on replica")
                return False
            
            # Test player data
            player_id = "player_alice_67890"
            player_data = {
                "username": "alice",
                "current_game": session_id,
                "cards": ["A_hearts", "K_spades"],
                "team": 1
            }
            
            print(f"  Storing player data: {player_id}")
            self.master_conn.set(
                f"player:{player_id}",
                json.dumps(player_data),
                ex=1800
            )
            
            # Wait and verify
            time.sleep(1)
            replica_player = self.replica_conn.get(f"player:{player_id}")
            
            if replica_player:
                replica_player_data = json.loads(replica_player.decode('utf-8'))
                if replica_player_data == player_data:
                    print("  ✅ Player data replication successful")
                    return True
                else:
                    print("  ❌ Player data mismatch")
                    return False
            else:
                print("  ❌ Player data not found on replica")
                return False
                
        except Exception as e:
            print(f"❌ Game operations test failed: {e}")
            return False
    
    def test_sentinel_info(self) -> bool:
        """Test Sentinel information"""
        try:
            print("\\n🔍 Testing Sentinel information...")
            
            if not self.sentinel:
                print("  ⚠️  No Sentinel available")
                return False
            
            # Get master info
            master_info = self.sentinel.discover_master(self.master_name)
            print(f"  Current master: {master_info[0]}:{master_info[1]}")
            
            # Get replica info
            try:
                replicas = self.sentinel.discover_slaves(self.master_name)
                print(f"  Discovered replicas: {len(replicas)}")
                for i, replica in enumerate(replicas):
                    print(f"    Replica {i+1}: {replica[0]}:{replica[1]}")
            except Exception as e:
                print(f"  ⚠️  Could not discover replicas: {e}")
            
            return True
            
        except Exception as e:
            print(f"❌ Sentinel info test failed: {e}")
            return False
    
    def run_tests(self) -> Dict[str, bool]:
        """Run all tests"""
        print("🎯 REDIS HIGH AVAILABILITY TEST")
        print("=" * 40)
        
        results = {}
        
        # Test 1: Sentinel Connection
        print("\\n[1/5] Testing Sentinel connection...")
        results['sentinel'] = self.connect_to_sentinel()
        
        # Test 2: Redis Connections  
        print("\\n[2/5] Testing Redis connections...")
        results['connections'] = self.connect_to_redis_instances()
        
        if not results['connections']:
            print("❌ Cannot proceed without Redis connections")
            return results
        
        # Test 3: Basic Operations
        print("\\n[3/5] Testing basic operations...")
        results['basic'] = self.test_basic_connectivity()
        
        # Test 4: Replication
        print("\\n[4/5] Testing replication...")
        results['replication'] = self.test_replication()
        
        # Test 5: Game Operations
        print("\\n[5/5] Testing game operations...")
        results['game_ops'] = self.test_game_operations()
        
        # Bonus: Sentinel Info
        if results['sentinel']:
            print("\\n[BONUS] Sentinel information...")
            results['sentinel_info'] = self.test_sentinel_info()
        
        return results
    
    def print_summary(self, results: Dict[str, bool]):
        """Print test summary"""
        print("\\n📊 TEST SUMMARY")
        print("=" * 25)
        
        passed = 0
        total = len(results)
        
        for test, result in results.items():
            status = "✅ PASS" if result else "❌ FAIL"
            test_name = test.replace('_', ' ').title()
            print(f"{test_name:.<20} {status}")
            if result:
                passed += 1
        
        print("-" * 25)
        print(f"Total: {passed}/{total} tests passed")
        
        if passed == total:
            print("🎉 ALL TESTS PASSED!")
            print("✅ Redis HA is working correctly")
        elif passed >= total * 0.8:
            print("⚠️  MOSTLY WORKING")
            print("   Some features may need attention")
        else:
            print("❌ SIGNIFICANT ISSUES")
            print("   Redis HA needs configuration fixes")
        
        return passed == total

def main():
    """Main test function"""
    print(f"🕐 Starting Redis HA test at {datetime.now().strftime('%H:%M:%S')}")
    
    tester = SimpleRedisHATest()
    
    try:
        results = tester.run_tests()
        success = tester.print_summary(results)
        
        if success:
            print("\\n✅ Redis HA setup is ready for game testing!")
        else:
            print("\\n⚠️  Fix Redis HA issues before proceeding")
        
        return success
        
    except KeyboardInterrupt:
        print("\\n⚠️  Test interrupted")
        return False
    except Exception as e:
        print(f"\\n❌ Test error: {e}")
        return False
    finally:
        # Cleanup
        try:
            if tester.master_conn:
                tester.master_conn.close()
            if tester.replica_conn:
                tester.replica_conn.close()
        except:
            pass
        print(f"\\n🕐 Test completed at {datetime.now().strftime('%H:%M:%S')}")

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
