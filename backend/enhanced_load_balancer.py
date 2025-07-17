#!/usr/bin/env python3
"""
Enhanced Load Balancer with Connection Migration Support
Handles existing connections during server failures for seamless failover
"""

import asyncio
import websockets
import json
import logging
import time
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass
import weakref

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

class ConnectionProxy:
    """Manages a single client-server connection with failover support"""
    
    def __init__(self, client_ws, load_balancer):
        self.client_ws = client_ws
        self.load_balancer = load_balancer
        self.server_ws = None
        self.current_server = None
        self.is_active = True
        self.reconnection_attempts = 0
        self.max_reconnection_attempts = 3
        
    async def start(self):
        """Start proxying with initial server connection"""
        await self.connect_to_server()
        
    async def connect_to_server(self):
        """Connect to a healthy server"""
        server_name = await self.load_balancer.get_healthy_server()
        
        if not server_name:
            logger.error("❌ No healthy servers available")
            await self.close("No healthy servers available")
            return False
            
        try:
            server = self.load_balancer.servers[server_name]
            server_uri = f"ws://{server.host}:{server.port}"
            
            logger.info(f"🔗 Connecting client to {server_name} server")
            
            self.server_ws = await websockets.connect(
                server_uri,
                ping_interval=60,
                ping_timeout=300,
                close_timeout=300
            )
            
            self.current_server = server_name
            server.connection_count += 1
            self.reconnection_attempts = 0
            
            # Start bidirectional proxy
            await self.start_proxy()
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to connect to {server_name}: {e}")
            await self.handle_server_failure()
            return False
    
    async def start_proxy(self):
        """Start bidirectional message proxying"""
        try:
            # Create proxy tasks
            client_to_server_task = asyncio.create_task(self.proxy_client_to_server())
            server_to_client_task = asyncio.create_task(self.proxy_server_to_client())
            
            # Wait for either to complete/fail
            done, pending = await asyncio.wait(
                [client_to_server_task, server_to_client_task],
                return_when=asyncio.FIRST_COMPLETED
            )
            
            # Cancel remaining tasks
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            
            # Check what happened
            for task in done:
                if task.exception():
                    logger.warning(f"⚠️ Proxy task failed: {task.exception()}")
                    await self.handle_server_failure()
                    
        except Exception as e:
            logger.error(f"❌ Proxy error: {e}")
            await self.handle_server_failure()
    
    async def proxy_client_to_server(self):
        """Proxy messages from client to server"""
        try:
            async for message in self.client_ws:
                if self.server_ws and not self.server_ws.closed:
                    await self.server_ws.send(message)
                else:
                    logger.warning("⚠️ Server connection lost during client message")
                    raise websockets.exceptions.ConnectionClosed(None, None)
        except websockets.exceptions.ConnectionClosed:
            logger.info("🔌 Client disconnected")
            self.is_active = False
        except Exception as e:
            logger.error(f"❌ Client->Server proxy error: {e}")
            raise
    
    async def proxy_server_to_client(self):
        """Proxy messages from server to client"""
        try:
            async for message in self.server_ws:
                if not self.client_ws.closed:
                    await self.client_ws.send(message)
                else:
                    logger.warning("⚠️ Client connection lost during server message")
                    raise websockets.exceptions.ConnectionClosed(None, None)
        except websockets.exceptions.ConnectionClosed:
            logger.info("🔌 Server disconnected")
            # This might be a server failure - attempt reconnection
            if self.is_active:
                await self.handle_server_failure()
        except Exception as e:
            logger.error(f"❌ Server->Client proxy error: {e}")
            raise
    
    async def handle_server_failure(self):
        """Handle server failure and attempt reconnection"""
        if not self.is_active:
            return
            
        self.reconnection_attempts += 1
        
        if self.reconnection_attempts > self.max_reconnection_attempts:
            logger.error(f"❌ Max reconnection attempts reached for client")
            await self.close("Server unavailable after multiple attempts")
            return
        
        logger.info(f"🔄 Attempting server reconnection (attempt {self.reconnection_attempts})")
        
        # Clean up current server connection
        if self.server_ws:
            try:
                await self.server_ws.close()
            except:
                pass
            self.server_ws = None
        
        if self.current_server:
            server = self.load_balancer.servers[self.current_server]
            server.connection_count = max(0, server.connection_count - 1)
            self.current_server = None
        
        # Wait a bit before reconnecting
        await asyncio.sleep(1)
        
        # Try to reconnect to a healthy server
        if await self.connect_to_server():
            logger.info("✅ Successfully reconnected to server")
        else:
            logger.error("❌ Reconnection failed")
            await self.close("Unable to reconnect to any server")
    
    async def close(self, reason="Connection closed"):
        """Close the connection"""
        self.is_active = False
        
        # Close client connection
        if not self.client_ws.closed:
            try:
                await self.client_ws.close(code=1011, reason=reason)
            except:
                pass
        
        # Close server connection
        if self.server_ws and not self.server_ws.closed:
            try:
                await self.server_ws.close()
            except:
                pass
        
        # Update server connection count
        if self.current_server:
            server = self.load_balancer.servers[self.current_server]
            server.connection_count = max(0, server.connection_count - 1)

class EnhancedLoadBalancer:
    """
    Enhanced load balancer with connection migration support
    """
    
    def __init__(self, listen_port=8760):
        self.listen_port = listen_port
        
        # Backend servers
        self.servers = {
            'primary': ServerEndpoint('localhost', 8765),
            'secondary': ServerEndpoint('localhost', 8766),
        }
        
        # Configuration
        self.health_check_interval = 3  # More frequent checks
        self.failover_threshold = 2  # Faster failover
        self.connection_timeout = 10
        
        # State
        self.active_proxies = set()  # Set of ConnectionProxy objects
        self.monitoring_task = None
        self.server_task = None
        self.is_running = False
    
    async def health_check_server(self, server_name: str, server: ServerEndpoint) -> bool:
        """Perform health check on a specific server"""
        try:
            start_time = time.time()
            
            uri = f"ws://{server.host}:{server.port}"
            async with websockets.connect(
                uri,
                ping_timeout=2,
                close_timeout=2,
                open_timeout=3
            ) as websocket:
                # Send health check message
                health_msg = {
                    "type": "health_check",
                    "timestamp": time.time()
                }
                await websocket.send(json.dumps(health_msg))
                
                # Wait for response (optional)
                try:
                    await asyncio.wait_for(websocket.recv(), timeout=2)
                except asyncio.TimeoutError:
                    pass
                
                # Success
                server.response_time = time.time() - start_time
                server.last_check = time.time()
                server.consecutive_failures = 0
                
                if server.status != "healthy":
                    logger.info(f"✅ Server {server_name} is now healthy")
                    server.status = "healthy"
                
                return True
                
        except Exception as e:
            server.consecutive_failures += 1
            server.last_check = time.time()
            
            if server.consecutive_failures >= self.failover_threshold:
                if server.status != "unhealthy":
                    logger.error(f"❌ Server {server_name} marked as unhealthy")
                    server.status = "unhealthy"
                    
                    # Trigger connection migration for affected connections
                    await self.handle_server_down(server_name)
            
            return False
    
    async def handle_server_down(self, failed_server: str):
        """Handle when a server goes down - trigger reconnection for affected clients"""
        logger.warning(f"🚨 Server {failed_server} is down - migrating connections")
        
        # Find all proxies connected to the failed server
        affected_proxies = [
            proxy for proxy in self.active_proxies 
            if proxy.current_server == failed_server and proxy.is_active
        ]
        
        logger.info(f"🔄 Migrating {len(affected_proxies)} connections from {failed_server}")
        
        # Trigger reconnection for all affected proxies
        migration_tasks = []
        for proxy in affected_proxies:
            task = asyncio.create_task(proxy.handle_server_failure())
            migration_tasks.append(task)
        
        if migration_tasks:
            # Wait for all migrations to complete
            await asyncio.gather(*migration_tasks, return_exceptions=True)
            logger.info(f"✅ Connection migration completed for {failed_server}")
    
    async def get_healthy_server(self) -> Optional[str]:
        """Get the name of a healthy server for new connections"""
        # Prefer primary if healthy
        if self.servers['primary'].status == "healthy":
            return 'primary'
        
        # Fall back to secondary
        if self.servers['secondary'].status == "healthy":
            return 'secondary'
        
        return None
    
    async def handle_client_connection(self, client_websocket):
        """Handle new client connection"""
        logger.info(f"🔗 New client connection from {client_websocket.remote_address}")
        
        # Create connection proxy
        proxy = ConnectionProxy(client_websocket, self)
        self.active_proxies.add(proxy)
        
        try:
            await proxy.start()
        except Exception as e:
            logger.error(f"❌ Proxy error: {e}")
        finally:
            # Clean up
            if proxy in self.active_proxies:
                self.active_proxies.remove(proxy)
            logger.info(f"🔌 Client connection closed")
    
    async def monitoring_loop(self):
        """Monitor backend server health"""
        logger.info("🔍 Starting enhanced server monitoring...")
        
        while self.is_running:
            try:
                # Check health of all servers
                tasks = []
                for server_name, server in self.servers.items():
                    task = self.health_check_server(server_name, server)
                    tasks.append(task)
                
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Log status
                self.log_status()
                
                await asyncio.sleep(self.health_check_interval)
                
            except Exception as e:
                logger.error(f"❌ Monitoring loop error: {e}")
                await asyncio.sleep(5)
    
    def log_status(self):
        """Log current load balancer status"""
        active_connections = len(self.active_proxies)
        healthy_servers = [name for name, server in self.servers.items() if server.status == "healthy"]
        
        status_parts = []
        for name, server in self.servers.items():
            emoji = "🟢" if server.status == "healthy" else "🔴" if server.status == "unhealthy" else "🟡"
            status_parts.append(f"{emoji}{name}({server.connection_count})")
        
        status = " ".join(status_parts)
        logger.info(f"📊 {status} | Active: {active_connections} | Healthy: {len(healthy_servers)}")
    
    async def start(self):
        """Start the enhanced load balancer"""
        logger.info(f"🚀 Starting Enhanced Load Balancer on port {self.listen_port}...")
        self.is_running = True
        
        # Start health monitoring
        self.monitoring_task = asyncio.create_task(self.monitoring_loop())
        
        # Start WebSocket server
        self.server_task = await websockets.serve(
            self.handle_client_connection,
            "localhost",
            self.listen_port,
            ping_interval=60,
            ping_timeout=300
        )
        
        logger.info(f"✅ Enhanced Load Balancer started on ws://localhost:{self.listen_port}")
        logger.info(f"🎯 Backend servers: {list(self.servers.keys())}")
        logger.info("🔄 Connection migration enabled for seamless failover")
        
        return True
    
    async def stop(self):
        """Stop the load balancer"""
        logger.info("🛑 Stopping Enhanced Load Balancer...")
        self.is_running = False
        
        # Close all active proxies
        close_tasks = []
        for proxy in list(self.active_proxies):
            task = asyncio.create_task(proxy.close("Load balancer shutting down"))
            close_tasks.append(task)
        
        if close_tasks:
            await asyncio.gather(*close_tasks, return_exceptions=True)
        
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
        
        logger.info("✅ Enhanced Load Balancer stopped")

async def main():
    """Main function"""
    load_balancer = EnhancedLoadBalancer()
    
    try:
        await load_balancer.start()
        
        logger.info("🛡️ Enhanced Load Balancer with failover support is running")
        logger.info("📝 Features: Connection migration, fast failover, health monitoring")
        logger.info("🔥 Press Ctrl+C to stop")
        
        # Keep running
        while load_balancer.is_running:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
    finally:
        await load_balancer.stop()

if __name__ == "__main__":
    asyncio.run(main())
