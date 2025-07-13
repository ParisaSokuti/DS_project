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
            'primary': ServerEndpoint('localhost', 8765),
            'secondary': ServerEndpoint('localhost', 8766),
        }
        
        # Configuration
        self.health_check_interval = 5  # seconds
        self.failover_threshold = 3  # consecutive failures
        self.connection_timeout = 10  # seconds
        
        # State
        self.active_connections = {}  # websocket -> server_name
        self.monitoring_task = None
        self.server_task = None
        self.is_running = False
    
    async def health_check_server(self, server_name: str, server: ServerEndpoint) -> bool:
        """Perform health check on a specific server"""
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
        server_name = await self.get_healthy_server()
        
        if not server_name:
            logger.error("❌ No healthy servers available for new connection")
            await client_websocket.close(code=1011, reason="No healthy servers available")
            return
        
        server = self.servers[server_name]
        server_uri = f"ws://{server.host}:{server.port}"
        
        logger.info(f"🔗 Proxying new connection to {server_name} server ({server_uri})")
        
        try:
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
                
                # Create bidirectional proxy
                async def client_to_server():
                    try:
                        async for message in client_websocket:
                            await server_websocket.send(message)
                    except websockets.exceptions.ConnectionClosed:
                        pass
                    except Exception as e:
                        logger.error(f"❌ Client->Server proxy error: {e}")
                
                async def server_to_client():
                    try:
                        async for message in server_websocket:
                            await client_websocket.send(message)
                    except websockets.exceptions.ConnectionClosed:
                        pass
                    except Exception as e:
                        logger.error(f"❌ Server->Client proxy error: {e}")
                
                # Run both directions concurrently
                await asyncio.gather(
                    client_to_server(),
                    server_to_client(),
                    return_exceptions=True
                )
                
        except Exception as e:
            logger.error(f"❌ Failed to connect to {server_name} server: {e}")
            
            # Try to failover to another server
            if server_name == 'primary':
                fallback_server = 'secondary'
            else:
                fallback_server = 'primary'
            
            if self.servers[fallback_server].status == "healthy":
                logger.info(f"🔄 Attempting failover to {fallback_server}")
                await self.proxy_to_server(client_websocket, fallback_server)
            else:
                await client_websocket.close(code=1011, reason="All servers unavailable")
        
        finally:
            # Clean up connection tracking
            if client_websocket in self.active_connections:
                del self.active_connections[client_websocket]
                server.connection_count = max(0, server.connection_count - 1)
    
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
