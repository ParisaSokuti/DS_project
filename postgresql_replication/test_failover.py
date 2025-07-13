#!/usr/bin/env python3
"""
PostgreSQL Failover Test for Hokm Game
Demonstrates automatic failover and fault tolerance
"""

import asyncio
import asyncpg
import time
import json
import logging
from datetime import datetime
from typing import Dict, List

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class PostgreSQLFailoverTest:
    def __init__(self):
        self.primary_config = {
            'host': 'localhost',
            'port': 5432,
            'database': 'hokm_game',
            'user': 'game_user',
            'password': 'game_password123'
        }
        
        self.standby_config = {
            'host': 'localhost',
            'port': 5433,
            'database': 'hokm_game', 
            'user': 'game_user',
            'password': 'game_password123'
        }
        
        self.primary_conn = None
        self.standby_conn = None
        
    async def connect_to_databases(self):
        """Connect to both primary and standby databases"""
        try:
            # Connect to primary
            self.primary_conn = await asyncpg.connect(**self.primary_config)
            logger.info("✅ Connected to PRIMARY database")
            
            # Connect to standby
            self.standby_conn = await asyncpg.connect(**self.standby_config)
            logger.info("✅ Connected to STANDBY database")
            
        except Exception as e:
            logger.error(f"❌ Database connection failed: {e}")
            raise
    
    async def test_replication_lag(self):
        """Test replication lag between primary and standby"""
        try:
            # Insert test data on primary
            test_data = {
                'room_code': f'TEST_{int(time.time())}',
                'test_time': datetime.now().isoformat(),
                'status': 'replication_test'
            }
            
            insert_query = """
                INSERT INTO game_sessions (room_code, game_state, status)
                VALUES ($1, $2, $3)
                RETURNING id, created_at
            """
            
            # Insert on primary
            result = await self.primary_conn.fetchrow(
                insert_query, 
                test_data['room_code'],
                json.dumps(test_data),
                test_data['status']
            )
            
            session_id = result['id']
            insert_time = time.time()
            logger.info(f"📝 Inserted test data on PRIMARY: {session_id}")
            
            # Wait and check standby
            max_wait = 10  # seconds
            found_on_standby = False
            
            for attempt in range(max_wait):
                try:
                    standby_result = await self.standby_conn.fetchrow(
                        "SELECT id, created_at FROM game_sessions WHERE id = $1",
                        session_id
                    )
                    
                    if standby_result:
                        replication_lag = time.time() - insert_time
                        logger.info(f"✅ Data replicated to STANDBY in {replication_lag:.2f} seconds")
                        found_on_standby = True
                        break
                        
                except Exception as e:
                    logger.warning(f"Standby query attempt {attempt + 1} failed: {e}")
                
                await asyncio.sleep(1)
            
            if not found_on_standby:
                logger.error("❌ Data NOT found on standby after 10 seconds")
                return False
                
            return True
            
        except Exception as e:
            logger.error(f"❌ Replication test failed: {e}")
            return False
    
    async def test_read_operations(self):
        """Test read operations on both servers"""
        try:
            # Test read on primary
            primary_count = await self.primary_conn.fetchval(
                "SELECT COUNT(*) FROM game_sessions"
            )
            logger.info(f"📊 PRIMARY - Total game sessions: {primary_count}")
            
            # Test read on standby
            standby_count = await self.standby_conn.fetchval(
                "SELECT COUNT(*) FROM game_sessions"
            )
            logger.info(f"📊 STANDBY - Total game sessions: {standby_count}")
            
            if abs(primary_count - standby_count) <= 1:  # Allow small lag
                logger.info("✅ Read operations successful on both servers")
                return True
            else:
                logger.warning(f"⚠️  Count mismatch: Primary={primary_count}, Standby={standby_count}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Read test failed: {e}")
            return False
    
    async def test_failover_scenario(self):
        """Simulate failover scenario"""
        logger.info("🔄 Testing failover scenario...")
        
        try:
            # Step 1: Insert data on primary
            failover_data = {
                'room_code': f'FAILOVER_{int(time.time())}',
                'test_type': 'failover_simulation',
                'status': 'before_failover'
            }
            
            result = await self.primary_conn.fetchrow(
                """INSERT INTO game_sessions (room_code, game_state, status)
                   VALUES ($1, $2, $3) RETURNING id""",
                failover_data['room_code'],
                json.dumps(failover_data),
                failover_data['status']
            )
            
            session_id = result['id']
            logger.info(f"📝 Created test session before failover: {session_id}")
            
            # Step 2: Wait for replication
            await asyncio.sleep(2)
            
            # Step 3: Simulate primary failure by closing connection
            await self.primary_conn.close()
            logger.info("🔌 Simulated PRIMARY failure (connection closed)")
            
            # Step 4: Test if standby can handle reads
            try:
                standby_result = await self.standby_conn.fetchrow(
                    "SELECT id, room_code, status FROM game_sessions WHERE id = $1",
                    session_id
                )
                
                if standby_result:
                    logger.info("✅ STANDBY successfully served read request during primary failure")
                    logger.info(f"   Data: {standby_result['room_code']} - {standby_result['status']}")
                    return True
                else:
                    logger.error("❌ STANDBY could not find data during primary failure")
                    return False
                    
            except Exception as e:
                logger.error(f"❌ STANDBY failed during primary failure: {e}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Failover test failed: {e}")
            return False
    
    async def cleanup_test_data(self):
        """Clean up test data"""
        try:
            if self.standby_conn and not self.standby_conn.is_closed():
                # Note: Standby is read-only, so we can only clean up if it's promoted
                pass
                
            if self.primary_conn and not self.primary_conn.is_closed():
                await self.primary_conn.execute(
                    "DELETE FROM game_sessions WHERE room_code LIKE 'TEST_%' OR room_code LIKE 'FAILOVER_%'"
                )
                logger.info("🧹 Cleaned up test data")
                
        except Exception as e:
            logger.warning(f"⚠️  Cleanup warning: {e}")
    
    async def close_connections(self):
        """Close database connections"""
        if self.primary_conn and not self.primary_conn.is_closed():
            await self.primary_conn.close()
        if self.standby_conn and not self.standby_conn.is_closed():
            await self.standby_conn.close()
        logger.info("🔌 Database connections closed")

async def main():
    """Main test function"""
    logger.info("🚀 Starting PostgreSQL Failover Test for Hokm Game")
    logger.info("=" * 60)
    
    test = PostgreSQLFailoverTest()
    
    try:
        # Connect to databases
        await test.connect_to_databases()
        
        # Run tests
        tests = [
            ("Replication Lag Test", test.test_replication_lag),
            ("Read Operations Test", test.test_read_operations),
            ("Failover Scenario Test", test.test_failover_scenario),
        ]
        
        results = {}
        for test_name, test_func in tests:
            logger.info(f"\n🧪 Running {test_name}...")
            results[test_name] = await test_func()
            logger.info(f"Result: {'✅ PASSED' if results[test_name] else '❌ FAILED'}")
        
        # Summary
        logger.info("\n" + "=" * 60)
        logger.info("📊 TEST SUMMARY")
        logger.info("=" * 60)
        
        passed = sum(results.values())
        total = len(results)
        
        for test_name, result in results.items():
            status = "✅ PASSED" if result else "❌ FAILED"
            logger.info(f"{test_name}: {status}")
        
        logger.info(f"\nOverall: {passed}/{total} tests passed")
        
        if passed == total:
            logger.info("🎉 All tests PASSED! PostgreSQL replication is working correctly.")
        else:
            logger.error("⚠️  Some tests FAILED. Check configuration.")
            
    except Exception as e:
        logger.error(f"❌ Test suite failed: {e}")
        
    finally:
        await test.cleanup_test_data()
        await test.close_connections()

if __name__ == "__main__":
    asyncio.run(main())
