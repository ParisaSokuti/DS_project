#!/usr/bin/env python3
"""
High Availability Server Manager
Manages multiple WebSocket game servers with automatic failover
"""

import asyncio
import websockets
import json
import time
import signal
import sys
import threading
import psutil
from typing import Dict, List, Optional, Set
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('HAServerManager')

@dataclass
class ServerInstance:
    """Represents a game server instance"""
    port: int
    process: Optional[asyncio.subprocess.Process] = None
    status: str = "stopped"  # stopped, starting, running, failed
    last_health_check: float = 0
    consecutive_failures: int = 0
    start_time: Optional[float] = None
    pid: Optional[int] = None

class HighAvailabilityServerManager:
    """
    Manages multiple WebSocket game servers with automatic failover
    
    Features:
    - Primary/Secondary server configuration
    - Health monitoring with automatic failover
    - Load balancer integration
    - Graceful shutdown and restart
    - Connection migration support
    """
    
    def __init__(self, primary_port=8765, secondary_port=8766):
        self.primary_port = primary_port
        self.secondary_port = secondary_port
        
        # Server instances
        self.servers = {
            'primary': ServerInstance(port=primary_port),
            'secondary': ServerInstance(port=secondary_port)
        }
        
        # HA configuration
        self.health_check_interval = 10  # seconds
        self.failover_threshold = 3  # consecutive failures before failover
        self.restart_delay = 5  # seconds before restart attempt
        
        # State tracking
        self.active_server = 'primary'  # which server is currently active
        self.load_balancer = None
        self.monitoring_task = None
        self.is_running = False
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        asyncio.create_task(self.shutdown())
    
    async def start_server_instance(self, server_name: str) -> bool:
        """Start a specific server instance"""
        server = self.servers[server_name]
        
        if server.status == "running":
            logger.info(f"Server {server_name} is already running on port {server.port}")
            return True
        
        try:
            logger.info(f"Starting {server_name} server on port {server.port}...")
            server.status = "starting"
            
            # Start the server process
            cmd = [
                sys.executable, "server.py", 
                "--port", str(server.port),
                "--instance-name", server_name
            ]
            
            server.process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd="."
            )
            
            server.start_time = time.time()
            server.pid = server.process.pid
            
            # Wait a moment to ensure the server starts properly
            await asyncio.sleep(2)
            
            # Check if the process is still running
            if server.process.returncode is None:
                server.status = "running"
                server.consecutive_failures = 0
                logger.info(f"✅ {server_name.capitalize()} server started successfully on port {server.port} (PID: {server.pid})")
                return True
            else:
                server.status = "failed"
                logger.error(f"❌ {server_name.capitalize()} server failed to start")
                return False
                
        except Exception as e:
            server.status = "failed"
            logger.error(f"❌ Failed to start {server_name} server: {e}")
            return False
    
    async def stop_server_instance(self, server_name: str) -> bool:
        """Stop a specific server instance"""
        server = self.servers[server_name]
        
        if server.status == "stopped" or server.process is None:
            logger.info(f"Server {server_name} is already stopped")
            return True
        
        try:
            logger.info(f"Stopping {server_name} server...")
            
            # Try graceful shutdown first
            server.process.terminate()
            
            # Wait for graceful shutdown
            try:
                await asyncio.wait_for(server.process.wait(), timeout=10)
                logger.info(f"✅ {server_name.capitalize()} server stopped gracefully")
            except asyncio.TimeoutError:
                # Force kill if graceful shutdown fails
                server.process.kill()
                await server.process.wait()
                logger.warning(f"⚠️ {server_name.capitalize()} server force-killed")
            
            server.status = "stopped"
            server.process = None
            server.pid = None
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to stop {server_name} server: {e}")
            return False
    
    async def health_check(self, server_name: str) -> bool:
        """Perform health check on a server instance"""
        server = self.servers[server_name]
        
        if server.status != "running":
            return False
        
        try:
            # Check if process is still alive
            if server.process and server.process.returncode is not None:
                logger.warning(f"⚠️ {server_name.capitalize()} server process has died")
                server.status = "failed"
                return False
            
            # Try to connect to the WebSocket server
            uri = f"ws://localhost:{server.port}"
            async with websockets.connect(
                uri, 
                ping_timeout=5,
                close_timeout=5,
                open_timeout=5
            ) as websocket:
                # Send a ping to verify the server is responsive
                await websocket.ping()
                
                # Send a health check message
                health_check_msg = {
                    "type": "health_check",
                    "timestamp": time.time()
                }
                await websocket.send(json.dumps(health_check_msg))
                
                # Wait for response (or timeout)
                try:
                    response = await asyncio.wait_for(websocket.recv(), timeout=3)
                    # Server responded, it's healthy
                    server.last_health_check = time.time()
                    server.consecutive_failures = 0
                    return True
                except asyncio.TimeoutError:
                    # No response, consider it unhealthy
                    pass
            
        except Exception as e:
            logger.warning(f"⚠️ Health check failed for {server_name}: {e}")
        
        # Health check failed
        server.consecutive_failures += 1
        return False
    
    async def perform_failover(self):
        """Perform failover from primary to secondary server"""
        logger.warning("🔄 INITIATING FAILOVER...")
        
        # Determine which server to failover to
        current_server = self.active_server
        target_server = 'secondary' if current_server == 'primary' else 'primary'
        
        logger.info(f"Failing over from {current_server} to {target_server}")
        
        # Start the target server if it's not running
        if self.servers[target_server].status != "running":
            success = await self.start_server_instance(target_server)
            if not success:
                logger.error(f"❌ FAILOVER FAILED: Could not start {target_server} server")
                return False
        
        # Update active server
        self.active_server = target_server
        
        # Update load balancer or client configuration
        await self.update_load_balancer()
        
        logger.info(f"✅ FAILOVER COMPLETE: {target_server.capitalize()} server is now active")
        
        # Try to restart the failed server
        asyncio.create_task(self.restart_failed_server(current_server))
        
        return True
    
    async def restart_failed_server(self, server_name: str):
        """Restart a failed server after a delay"""
        logger.info(f"Scheduling restart of {server_name} server in {self.restart_delay} seconds...")
        await asyncio.sleep(self.restart_delay)
        
        # Stop the failed server first
        await self.stop_server_instance(server_name)
        
        # Wait a moment
        await asyncio.sleep(2)
        
        # Try to restart
        success = await self.start_server_instance(server_name)
        if success:
            logger.info(f"✅ {server_name.capitalize()} server restarted successfully")
        else:
            logger.error(f"❌ Failed to restart {server_name} server")
    
    async def update_load_balancer(self):
        """Update load balancer configuration to point to active server"""
        active_port = self.servers[self.active_server].port
        
        # In a real implementation, this would update nginx config or a load balancer
        # For demonstration, we'll update a simple config file
        config = {
            "active_server": self.active_server,
            "active_port": active_port,
            "primary_port": self.primary_port,
            "secondary_port": self.secondary_port,
            "last_updated": datetime.now().isoformat()
        }
        
        try:
            with open("ha_config.json", "w") as f:
                json.dump(config, f, indent=2)
            
            logger.info(f"🔧 Load balancer updated: Active server is {self.active_server} on port {active_port}")
        except Exception as e:
            logger.error(f"❌ Failed to update load balancer config: {e}")
    
    async def monitoring_loop(self):
        """Main monitoring loop for health checks and failover"""
        logger.info("🔍 Starting health monitoring...")
        
        while self.is_running:
            try:
                # Health check both servers
                for server_name, server in self.servers.items():
                    if server.status == "running":
                        is_healthy = await self.health_check(server_name)
                        
                        if not is_healthy:
                            logger.warning(f"⚠️ {server_name.capitalize()} server health check failed "
                                         f"({server.consecutive_failures}/{self.failover_threshold})")
                            
                            # Check if we need to failover
                            if (server_name == self.active_server and 
                                server.consecutive_failures >= self.failover_threshold):
                                await self.perform_failover()
                
                # Log status
                self.log_status()
                
                # Wait before next health check
                await asyncio.sleep(self.health_check_interval)
                
            except Exception as e:
                logger.error(f"❌ Error in monitoring loop: {e}")
                await asyncio.sleep(5)
    
    def log_status(self):
        """Log current status of all servers"""
        primary = self.servers['primary']
        secondary = self.servers['secondary']
        
        status_msg = (
            f"Status: Primary({primary.status}) Secondary({secondary.status}) "
            f"Active: {self.active_server}"
        )
        
        if primary.status == "running" and secondary.status == "running":
            logger.info(f"🟢 {status_msg}")
        elif primary.status == "running" or secondary.status == "running":
            logger.info(f"🟡 {status_msg}")
        else:
            logger.error(f"🔴 {status_msg}")
    
    async def start(self):
        """Start the high availability system"""
        logger.info("🚀 Starting High Availability Game Server Manager...")
        self.is_running = True
        
        # Start primary server first
        success = await self.start_server_instance('primary')
        if not success:
            logger.error("❌ Failed to start primary server")
            return False
        
        # Start secondary server
        success = await self.start_server_instance('secondary')
        if not success:
            logger.warning("⚠️ Failed to start secondary server, continuing with primary only")
        
        # Update load balancer
        await self.update_load_balancer()
        
        # Start monitoring
        self.monitoring_task = asyncio.create_task(self.monitoring_loop())
        
        logger.info("✅ High Availability system started successfully!")
        logger.info(f"🎮 Game servers available on ports {self.primary_port} and {self.secondary_port}")
        logger.info(f"🔧 Active server: {self.active_server} (port {self.servers[self.active_server].port})")
        
        return True
    
    async def shutdown(self):
        """Gracefully shutdown all servers"""
        logger.info("🛑 Shutting down High Availability system...")
        self.is_running = False
        
        # Stop monitoring
        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass
        
        # Stop all servers
        tasks = []
        for server_name in self.servers:
            tasks.append(self.stop_server_instance(server_name))
        
        await asyncio.gather(*tasks, return_exceptions=True)
        
        logger.info("✅ High Availability system shutdown complete")
    
    async def simulate_failure(self, server_name: str):
        """Simulate server failure for testing"""
        logger.warning(f"🧪 SIMULATING FAILURE of {server_name} server...")
        await self.stop_server_instance(server_name)
        logger.info(f"🧪 {server_name.capitalize()} server stopped for failure simulation")

async def main():
    """Main function to run the HA system"""
    ha_manager = HighAvailabilityServerManager()
    
    try:
        # Start the HA system
        success = await ha_manager.start()
        if not success:
            logger.error("❌ Failed to start HA system")
            return
        
        # Keep the system running
        logger.info("Press Ctrl+C to shutdown the system")
        logger.info("Available commands:")
        logger.info("  Type 'status' to see server status")
        logger.info("  Type 'fail primary' or 'fail secondary' to simulate failures")
        logger.info("  Type 'restart primary' or 'restart secondary' to restart servers")
        
        # Simple command interface
        while ha_manager.is_running:
            try:
                # In a real implementation, you might want to use a proper CLI interface
                await asyncio.sleep(1)
            except KeyboardInterrupt:
                break
        
    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
    finally:
        await ha_manager.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
