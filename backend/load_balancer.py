#!/usr/bin/env python3
"""
Smart Load Balancer for High Availability Game Server
Routes client connections to healthy servers with automatic failover
"""

import asyncio
import websockets
import json
import logging
import time
from typing import Dict, List, Optional, Set
from dataclasses import dataclass
import redis.asyncio as redis

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('LoadBalancer')

@dataclass
class ServerEndpoint:
    """Represents a game server endpoint"""
    host: str
    port: int
    status: str = "unknown"  # unknown, healthy, unhealthy
    last_check: float = 0
    connection_count: int = 0
    response_time: float = 0
    consecutive_failures: int = 0

class GameServerLoadBalancer:
    """
    Smart load balancer for game servers with health monitoring and failover
    
    Features:
    - Health monitoring of backend servers
    - Automatic failover to healthy servers
    - Connection counting and load balancing
    - WebSocket proxy with transparent failover
    - Real-time server status updates
    """
    
    def __init__(self, listen_port=8760):
        self.listen_port = listen_port
        
        # Backend servers
        self.servers = {
            'primary': ServerEndpoint('localhost', 8765),  # Your machine
            'secondary': ServerEndpoint('192.168.1.92', 8765),  # Friend's machine
        }
        
        # Configuration
        self.health_check_interval = 2  # seconds - faster detection
        self.failover_threshold = 1  # consecutive failures - immediate failover
        self.connection_timeout = 10  # seconds
        
        # State
        self.active_connections = {}  # websocket -> server_name
        self.connection_states = {}  # websocket -> state (connecting, connected, disconnected)
        self.reconnect_attempts = {}  # websocket -> (count, last_attempt_time)
        self.monitoring_task = None
        self.server_task = None
        self.is_running = False
        
        # Redis connection for game state
        self.redis_client = None
    
    async def health_check_server(self, server_name: str, server: ServerEndpoint) -> bool:
        """Perform health check on a specific server"""
        previous_status = server.status
        
        try:
            start_time = time.time()
            
            # Try to connect to the server
            uri = f"ws://{server.host}:{server.port}"
            async with websockets.connect(
                uri,
                ping_timeout=3,
                close_timeout=3,
                open_timeout=5
            ) as websocket:
                # Send health check message
                health_msg = {
                    "type": "health_check",
                    "timestamp": time.time()
                }
                await websocket.send(json.dumps(health_msg))
                
                # Wait for any response
                try:
                    await asyncio.wait_for(websocket.recv(), timeout=3)
                except asyncio.TimeoutError:
                    pass  # Server might not respond to health checks, but connection worked
                
                # Calculate response time
                server.response_time = time.time() - start_time
                server.last_check = time.time()
                server.consecutive_failures = 0
                
                if server.status != "healthy":
                    logger.info(f"✅ Server {server_name} is now healthy (response: {server.response_time:.3f}s)")
                    server.status = "healthy"
                
                return True
                
        except Exception as e:
            server.consecutive_failures += 1
            server.last_check = time.time()
            
            if server.status == "healthy":
                logger.warning(f"⚠️ Server {server_name} health check failed: {e}")
            
            if server.consecutive_failures >= self.failover_threshold:
                if server.status != "unhealthy":
                    logger.error(f"❌ Server {server_name} marked as unhealthy after {server.consecutive_failures} failures")
                    server.status = "unhealthy"
                    
                    # CRITICAL: Migrate existing connections when server fails
                    if previous_status == "healthy":
                        await self.migrate_connections_from_failed_server(server_name)
            
            return False
    
    async def get_healthy_server(self) -> Optional[str]:
        """Get the name of a healthy server for new connections"""
        # First, try primary if it's healthy
        if self.servers['primary'].status == "healthy":
            return 'primary'
        
        # Then try secondary
        if self.servers['secondary'].status == "healthy":
            return 'secondary'
        
        # No healthy servers
        return None
    
    async def proxy_websocket(self, client_websocket):
        """Proxy WebSocket connection to a healthy backend server"""
        client_addr = client_websocket.remote_address
        logger.info(f"🔗 New client connection from {client_addr}")
        
        # Check if this client is already being handled
        if client_websocket in self.connection_states:
            logger.warning(f"⚠️ Client {client_addr} already being handled")
            return
        
        # Mark as connecting
        self.connection_states[client_websocket] = "connecting"
        
        try:
            server_name = await self.get_healthy_server()
            
            if not server_name:
                logger.error("❌ No healthy servers available for new connection")
                await client_websocket.close(code=1011, reason="No healthy servers available")
                return
            
            server = self.servers[server_name]
            server_uri = f"ws://{server.host}:{server.port}"
            
            logger.info(f"🔗 Proxying new connection to {server_name} server ({server_uri})")
            
            # Mark as connected
            self.connection_states[client_websocket] = "connected"
            
            # Connect to backend server
            async with websockets.connect(
                server_uri,
                ping_interval=60,
                ping_timeout=300,
                close_timeout=300
            ) as server_websocket:
                
                # Track the connection
                self.active_connections[client_websocket] = server_name
                server.connection_count += 1
                
                # Create bidirectional proxy with proper message handling
                async def client_to_server():
                    try:
                        while True:
                            try:
                                message = await client_websocket.recv()
                                await server_websocket.send(message)
                            except websockets.exceptions.ConnectionClosed:
                                break
                            except Exception as e:
                                logger.error(f"❌ Client->Server proxy error: {e}")
                                break
                    except Exception as e:
                        logger.warning(f"⚠️ Proxy task failed: {e}")
                
                async def server_to_client():
                    try:
                        while True:
                            try:
                                message = await server_websocket.recv()
                                await client_websocket.send(message)
                            except websockets.exceptions.ConnectionClosed:
                                break
                            except Exception as e:
                                logger.error(f"❌ Server->Client proxy error: {e}")
                                break
                    except Exception as e:
                        logger.warning(f"⚠️ Proxy task failed: {e}")
                
                # Run both directions concurrently with proper cancellation
                client_task = asyncio.create_task(client_to_server())
                server_task = asyncio.create_task(server_to_client())
                
                try:
                    # Wait for either task to complete (indicating connection closed)
                    done, pending = await asyncio.wait(
                        [client_task, server_task],
                        return_when=asyncio.FIRST_COMPLETED
                    )
                    
                    # Cancel remaining tasks
                    for task in pending:
                        task.cancel()
                        try:
                            await task
                        except asyncio.CancelledError:
                            pass
                        
                except Exception as e:
                    logger.error(f"❌ Proxy error: {e}")
                finally:
                    # Ensure tasks are cancelled
                    client_task.cancel()
                    server_task.cancel()
                
        except Exception as e:
            logger.error(f"❌ Failed to connect to {server_name} server: {e}")
            
            # Check reconnection rate limiting
            current_time = time.time()
            reconnect_info = self.reconnect_attempts.get(client_websocket, (0, 0))
            attempts, last_attempt = reconnect_info
            
            # Reset counter if enough time has passed
            if current_time - last_attempt > 60:  # Reset after 1 minute
                attempts = 0
            
            # Only try failover if we haven't exceeded limits and not already in a failover loop
            if (attempts < 3 and 
                self.connection_states.get(client_websocket) == "connected" and
                current_time - last_attempt > 5):  # Min 5 seconds between attempts
                
                # Update reconnection tracking
                self.reconnect_attempts[client_websocket] = (attempts + 1, current_time)
                
                # Try to failover to another server
                if server_name == 'primary':
                    fallback_server = 'secondary'
                else:
                    fallback_server = 'primary'
                
                if self.servers[fallback_server].status == "healthy":
                    logger.info(f"🔄 Attempting server reconnection (attempt {attempts + 1})")
                    self.connection_states[client_websocket] = "reconnecting"
                    await self.proxy_to_server(client_websocket, fallback_server)
                    return  # Don't close connection, let failover handle it
                else:
                    logger.error("❌ No healthy fallback server available")
            else:
                if attempts >= 3:
                    logger.error(f"❌ Max reconnection attempts ({attempts}) exceeded for client")
                
            # Close connection if failover not possible or limits exceeded
            try:
                await client_websocket.close(code=1011, reason="Server unavailable")
            except:
                pass
        
        finally:
            # Clean up connection tracking
            if client_websocket in self.active_connections:
                server_name = self.active_connections[client_websocket]
                del self.active_connections[client_websocket]
                if server_name in self.servers:
                    self.servers[server_name].connection_count = max(0, self.servers[server_name].connection_count - 1)
            
            # Clean up connection state and reconnection tracking
            if client_websocket in self.connection_states:
                del self.connection_states[client_websocket]
            if client_websocket in self.reconnect_attempts:
                del self.reconnect_attempts[client_websocket]
    
    async def proxy_to_server(self, client_websocket, server_name: str):
        """Proxy to a specific server (used for failover)"""
        server = self.servers[server_name]
        server_uri = f"ws://{server.host}:{server.port}"
        
        try:
            async with websockets.connect(server_uri) as server_websocket:
                self.active_connections[client_websocket] = server_name
                server.connection_count += 1
                
                # Simplified proxy for failover
                async def proxy_messages():
                    client_task = asyncio.create_task(self.forward_messages(client_websocket, server_websocket))
                    server_task = asyncio.create_task(self.forward_messages(server_websocket, client_websocket))
                    
                    done, pending = await asyncio.wait(
                        [client_task, server_task],
                        return_when=asyncio.FIRST_COMPLETED
                    )
                    
                    # Cancel remaining tasks
                    for task in pending:
                        task.cancel()
                
                await proxy_messages()
                
        except Exception as e:
            logger.error(f"❌ Failover to {server_name} failed: {e}")
        finally:
            if client_websocket in self.active_connections:
                del self.active_connections[client_websocket]
                server.connection_count = max(0, server.connection_count - 1)
    
    async def forward_messages(self, source, destination):
        """Forward messages from source to destination websocket"""
        try:
            async for message in source:
                await destination.send(message)
        except websockets.exceptions.ConnectionClosed:
            pass
    
    async def monitoring_loop(self):
        """Monitor backend server health"""
        logger.info("🔍 Starting server health monitoring...")
        
        while self.is_running:
            try:
                # Check health of all servers
                tasks = []
                for server_name, server in self.servers.items():
                    task = self.health_check_server(server_name, server)
                    tasks.append(task)
                
                await asyncio.gather(*tasks, return_exceptions=True)
                
                # Log status
                self.log_status()
                
                await asyncio.sleep(self.health_check_interval)
                
            except Exception as e:
                logger.error(f"❌ Monitoring loop error: {e}")
                await asyncio.sleep(5)
    
    def log_status(self):
        """Log current load balancer status"""
        total_connections = sum(server.connection_count for server in self.servers.values())
        healthy_servers = [name for name, server in self.servers.items() if server.status == "healthy"]
        
        status_parts = []
        for name, server in self.servers.items():
            emoji = "🟢" if server.status == "healthy" else "🔴" if server.status == "unhealthy" else "🟡"
            status_parts.append(f"{emoji}{name}({server.connection_count})")
        
        status = " ".join(status_parts)
        logger.info(f"📊 Servers: {status} | Total connections: {total_connections} | Healthy: {len(healthy_servers)}")
    
    async def start(self):
        """Start the load balancer"""
        logger.info(f"🚀 Starting Load Balancer on port {self.listen_port}...")
        self.is_running = True
        
        # Initialize Redis connection
        try:
            self.redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)
            await self.redis_client.ping()
            logger.info("✅ Connected to Redis")
        except Exception as e:
            logger.warning(f"⚠️ Redis connection failed: {e}. Game state monitoring disabled.")
            self.redis_client = None
        
        # Start health monitoring
        self.monitoring_task = asyncio.create_task(self.monitoring_loop())
        
        # Start WebSocket server
        self.server_task = await websockets.serve(
            self.proxy_websocket,
            "localhost",
            self.listen_port,
            ping_interval=60,
            ping_timeout=300
        )
        
        logger.info(f"✅ Load Balancer started on ws://localhost:{self.listen_port}")
        logger.info(f"🎯 Routing to servers: {list(self.servers.keys())}")
        
        # Wait for server to start
        await asyncio.sleep(1)
        
        return True
    
    async def stop(self):
        """Stop the load balancer"""
        logger.info("🛑 Stopping Load Balancer...")
        self.is_running = False
        
        # Stop monitoring
        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass
        
        # Stop server
        if self.server_task:
            self.server_task.cancel()
        
        logger.info("✅ Load Balancer stopped")
    
    async def migrate_connections_from_failed_server(self, failed_server_name: str):
        """Migrate all connections from a failed server to a healthy one"""
        # Find a healthy fallback server
        fallback_server = None
        if failed_server_name == 'primary' and self.servers['secondary'].status == "healthy":
            fallback_server = 'secondary'
        elif failed_server_name == 'secondary' and self.servers['primary'].status == "healthy":
            fallback_server = 'primary'
        
        if not fallback_server:
            logger.error(f"❌ No healthy server available for migration from {failed_server_name}")
            return
        
        # Find all connections that were connected to the failed server
        connections_to_migrate = []
        for client_ws, server_name in list(self.active_connections.items()):
            if server_name == failed_server_name:
                connections_to_migrate.append(client_ws)
        
        if not connections_to_migrate:
            logger.info(f"ℹ️ No active connections to migrate from {failed_server_name}")
            return
        
        logger.info(f"🔄 Migrating {len(connections_to_migrate)} connections from {failed_server_name} to {fallback_server}")
        
        # Migrate each connection
        migration_tasks = []
        for client_ws in connections_to_migrate:
            task = asyncio.create_task(self.migrate_single_connection(client_ws, fallback_server))
            migration_tasks.append(task)
        
        # Wait for all migrations to complete
        results = await asyncio.gather(*migration_tasks, return_exceptions=True)
        
        # Count successful migrations
        successful = sum(1 for result in results if result is True)
        logger.info(f"✅ Successfully migrated {successful}/{len(connections_to_migrate)} connections to {fallback_server}")
    
    async def migrate_single_connection(self, client_websocket, target_server_name: str) -> bool:
        """Migrate a single client connection to a target server"""
        try:
            logger.info(f"🔄 Starting migration of client connection to {target_server_name}")
            
            # Update connection state
            if client_websocket in self.connection_states:
                self.connection_states[client_websocket] = "migrating"
            
            # Get room context if Redis is available
            room_context = None
            if self.redis_client:
                try:
                    # Try to find which room this client is in
                    room_keys = await self.redis_client.keys("room:*")
                    for room_key in room_keys:
                        room_data = await self.redis_client.hgetall(room_key)
                        # Check if client is in this room (basic check)
                        if room_data and len(room_data) > 0:
                            room_context = {
                                "room_id": room_key.split(":")[1],
                                "has_active_game": "current_player" in room_data
                            }
                            break
                except Exception as e:
                    logger.warning(f"⚠️ Could not retrieve room context: {e}")
            
            # Send a reconnection signal to the client first
            try:
                reconnect_message = {
                    "type": "server_migration",
                    "reason": "Server failover in progress",
                    "new_server": target_server_name,
                    "action": "reconnect",
                    "room_context": room_context
                }
                await client_websocket.send(json.dumps(reconnect_message))
                logger.info(f"📡 Sent migration signal to client")
            except Exception as e:
                logger.warning(f"⚠️ Could not send migration signal to client: {e}")
                # Continue with migration even if signal fails
            
            # Wait a bit for client to process
            await asyncio.sleep(1.0)
            
            # Now establish new connection to target server
            target_server = self.servers[target_server_name]
            target_uri = f"ws://{target_server.host}:{target_server.port}"
            
            logger.info(f"🔗 Connecting to target server: {target_uri}")
            
            # Create new connection to target server
            try:
                async with websockets.connect(
                    target_uri,
                    ping_interval=60,
                    ping_timeout=300,
                    close_timeout=300
                ) as new_server_websocket:
                    
                    # Update connection tracking
                    old_server_name = self.active_connections.get(client_websocket)
                    if old_server_name and old_server_name in self.servers:
                        self.servers[old_server_name].connection_count = max(0, self.servers[old_server_name].connection_count - 1)
                    
                    self.active_connections[client_websocket] = target_server_name
                    target_server.connection_count += 1
                    self.connection_states[client_websocket] = "connected"
                    
                    logger.info(f"✅ Successfully established connection to {target_server_name}")
                    
                    # Start bidirectional proxy
                    async def client_to_server():
                        try:
                            while True:
                                try:
                                    message = await client_websocket.recv()
                                    await new_server_websocket.send(message)
                                except websockets.exceptions.ConnectionClosed:
                                    logger.info("Client connection closed during migration")
                                    break
                                except Exception as e:
                                    logger.error(f"❌ Client->Server proxy error during migration: {e}")
                                    break
                        except Exception as e:
                            logger.warning(f"⚠️ Client to server proxy failed: {e}")
                    
                    async def server_to_client():
                        try:
                            while True:
                                try:
                                    message = await new_server_websocket.recv()
                                    await client_websocket.send(message)
                                except websockets.exceptions.ConnectionClosed:
                                    logger.info("Server connection closed during migration")
                                    break
                                except Exception as e:
                                    logger.error(f"❌ Server->Client proxy error during migration: {e}")
                                    break
                        except Exception as e:
                            logger.warning(f"⚠️ Server to client proxy failed: {e}")
                    
                    # Run proxy tasks
                    client_task = asyncio.create_task(client_to_server())
                    server_task = asyncio.create_task(server_to_client())
                    
                    try:
                        # Wait for either connection to close
                        done, pending = await asyncio.wait(
                            [client_task, server_task],
                            return_when=asyncio.FIRST_COMPLETED
                        )
                        
                        # Cancel remaining tasks
                        for task in pending:
                            task.cancel()
                            try:
                                await task
                            except asyncio.CancelledError:
                                pass
                                
                        logger.info(f"✅ Migration proxy completed for {target_server_name}")
                        return True
                        
                    except Exception as e:
                        logger.error(f"❌ Migration proxy error: {e}")
                        return False
                    finally:
                        # Ensure cleanup
                        client_task.cancel()
                        server_task.cancel()
                        
            except Exception as e:
                logger.error(f"❌ Failed to connect to target server {target_server_name}: {e}")
                return False
            
        except Exception as e:
            logger.error(f"❌ Migration failed: {e}")
            return False

async def main():
    """Main function"""
    load_balancer = GameServerLoadBalancer()
    
    try:
        await load_balancer.start()
        
        logger.info("Load Balancer is running. Press Ctrl+C to stop.")
        
        # Keep running
        while load_balancer.is_running:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
    finally:
        await load_balancer.stop()

if __name__ == "__main__":
    asyncio.run(main())
