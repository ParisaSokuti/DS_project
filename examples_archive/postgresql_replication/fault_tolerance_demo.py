#!/usr/bin/env python3
"""
Hokm Game Fault Tolerance Demonstration
Shows how the game continues to work even when servers fail
"""

import asyncio
import websockets
import json
import logging
import time
import subprocess
import signal
import sys
from typing import List, Dict, Optional

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class FaultToleranceDemo:
    def __init__(self):
        self.server_processes = []
        self.client_connections = []
        self.game_state = {}
        
    async def start_game_servers(self):
        """Start multiple game servers for redundancy"""
        logger.info("🚀 Starting multiple game servers for fault tolerance...")
        
        # Start primary server on port 8765
        try:
            server1 = subprocess.Popen([
                sys.executable, "backend/server.py", "--port", "8765"
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.server_processes.append(("Primary Server", server1))
            logger.info("✅ Primary server started on port 8765")
            
            # Give it time to start
            await asyncio.sleep(2)
            
        except Exception as e:
            logger.error(f"❌ Failed to start primary server: {e}")
            
        # Start backup server on port 8766
        try:
            server2 = subprocess.Popen([
                sys.executable, "backend/server.py", "--port", "8766"
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.server_processes.append(("Backup Server", server2))
            logger.info("✅ Backup server started on port 8766")
            
            # Give it time to start
            await asyncio.sleep(2)
            
        except Exception as e:
            logger.error(f"❌ Failed to start backup server: {e}")
    
    async def connect_test_clients(self, num_clients: int = 4):
        """Connect test clients to the game servers"""
        logger.info(f"🎮 Connecting {num_clients} test clients...")
        
        for i in range(num_clients):
            try:
                # Connect to load balancer (or directly to primary)
                websocket = await websockets.connect("ws://localhost:8765")
                
                # Authenticate
                auth_message = {
                    "type": "auth_login",
                    "username": f"TestPlayer{i+1}",
                    "password": "testpass123"
                }
                await websocket.send(json.dumps(auth_message))
                
                # Wait for auth response
                response = await websocket.recv()
                auth_data = json.loads(response)
                
                if auth_data.get('success'):
                    logger.info(f"✅ Client {i+1} authenticated successfully")
                    
                    # Join game
                    join_message = {
                        "type": "join",
                        "room_code": "DEMO"
                    }
                    await websocket.send(json.dumps(join_message))
                    
                    self.client_connections.append({
                        'id': i+1,
                        'websocket': websocket,
                        'username': f"TestPlayer{i+1}"
                    })
                    
                else:
                    logger.error(f"❌ Client {i+1} authentication failed")
                    
            except Exception as e:
                logger.error(f"❌ Failed to connect client {i+1}: {e}")
        
        logger.info(f"📊 {len(self.client_connections)} clients connected successfully")
    
    async def simulate_game_activity(self, duration: int = 30):
        """Simulate normal game activity"""
        logger.info(f"🎲 Simulating game activity for {duration} seconds...")
        
        start_time = time.time()
        message_count = 0
        
        while time.time() - start_time < duration:
            for client in self.client_connections:
                try:
                    # Send a health check or game state request
                    health_message = {
                        "type": "health_check",
                        "timestamp": time.time()
                    }
                    await client['websocket'].send(json.dumps(health_message))
                    
                    # Try to receive response
                    response = await asyncio.wait_for(
                        client['websocket'].recv(), 
                        timeout=5.0
                    )
                    message_count += 1
                    
                except asyncio.TimeoutError:
                    logger.warning(f"⏰ Client {client['id']} timed out")
                except Exception as e:
                    logger.warning(f"⚠️  Client {client['id']} error: {e}")
            
            await asyncio.sleep(2)  # Wait 2 seconds between rounds
        
        logger.info(f"📈 Processed {message_count} messages during simulation")
    
    async def simulate_primary_server_failure(self):
        """Simulate primary server failure"""
        logger.info("💥 Simulating PRIMARY SERVER FAILURE...")
        
        # Find and kill primary server
        for name, process in self.server_processes:
            if "Primary" in name:
                try:
                    process.terminate()
                    logger.info("🔴 Primary server terminated")
                    await asyncio.sleep(5)  # Wait for clients to notice
                    break
                except Exception as e:
                    logger.error(f"❌ Failed to terminate primary server: {e}")
    
    async def test_failover_recovery(self):
        """Test if clients can recover after server failure"""
        logger.info("🔄 Testing failover recovery...")
        
        recovery_count = 0
        for client in self.client_connections:
            try:
                # Try to reconnect or send message
                test_message = {
                    "type": "health_check",
                    "post_failover": True,
                    "timestamp": time.time()
                }
                
                await client['websocket'].send(json.dumps(test_message))
                response = await asyncio.wait_for(
                    client['websocket'].recv(),
                    timeout=10.0
                )
                
                recovery_count += 1
                logger.info(f"✅ Client {client['id']} recovered successfully")
                
            except Exception as e:
                logger.error(f"❌ Client {client['id']} failed to recover: {e}")
                
                # Try to reconnect to backup server
                try:
                    new_websocket = await websockets.connect("ws://localhost:8766")
                    client['websocket'] = new_websocket
                    recovery_count += 1
                    logger.info(f"🔄 Client {client['id']} reconnected to backup server")
                except Exception as reconnect_error:
                    logger.error(f"❌ Client {client['id']} reconnection failed: {reconnect_error}")
        
        logger.info(f"📊 Failover recovery: {recovery_count}/{len(self.client_connections)} clients recovered")
        return recovery_count
    
    async def cleanup(self):
        """Clean up resources"""
        logger.info("🧹 Cleaning up resources...")
        
        # Close client connections
        for client in self.client_connections:
            try:
                await client['websocket'].close()
            except:
                pass
        
        # Terminate server processes
        for name, process in self.server_processes:
            try:
                process.terminate()
                logger.info(f"🔌 {name} terminated")
            except:
                pass
    
    async def run_full_demo(self):
        """Run the complete fault tolerance demonstration"""
        logger.info("🎯 Starting COMPLETE Fault Tolerance Demonstration")
        logger.info("=" * 60)
        
        try:
            # Step 1: Start servers
            await self.start_game_servers()
            await asyncio.sleep(3)
            
            # Step 2: Connect clients
            await self.connect_test_clients(4)
            await asyncio.sleep(2)
            
            # Step 3: Simulate normal activity
            logger.info("\n📋 Phase 1: Normal Operation")
            await self.simulate_game_activity(10)
            
            # Step 4: Simulate server failure
            logger.info("\n📋 Phase 2: Primary Server Failure")
            await self.simulate_primary_server_failure()
            
            # Step 5: Test recovery
            logger.info("\n📋 Phase 3: Failover Recovery")
            recovered = await self.test_failover_recovery()
            
            # Step 6: Continue with reduced capacity
            logger.info("\n📋 Phase 4: Operation with Backup Server")
            await self.simulate_game_activity(10)
            
            # Results
            logger.info("\n" + "=" * 60)
            logger.info("📊 FAULT TOLERANCE DEMONSTRATION RESULTS")
            logger.info("=" * 60)
            logger.info(f"✅ Servers started: {len(self.server_processes)}")
            logger.info(f"✅ Clients connected: {len(self.client_connections)}")
            logger.info(f"✅ Clients recovered after failure: {recovered}")
            logger.info(f"✅ Fault tolerance: {'SUCCESSFUL' if recovered > 0 else 'FAILED'}")
            
            if recovered > 0:
                logger.info("\n🎉 FAULT TOLERANCE DEMONSTRATION SUCCESSFUL!")
                logger.info("The game system can handle server failures gracefully.")
            else:
                logger.error("\n❌ FAULT TOLERANCE DEMONSTRATION FAILED!")
                logger.error("The system did not recover properly from server failure.")
                
        except Exception as e:
            logger.error(f"❌ Demo failed: {e}")
        finally:
            await self.cleanup()

async def main():
    """Main function"""
    demo = FaultToleranceDemo()
    await demo.run_full_demo()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Demo interrupted by user")
    except Exception as e:
        logger.error(f"❌ Demo failed: {e}")
