# Horizontal Scaling Architecture for Hokm Game Server

## Overview

This document outlines a comprehensive horizontal scaling solution for the Hokm WebSocket card game server, featuring WebSocket-aware load balancing, sticky sessions, inter-server communication, and auto-scaling capabilities.

## Architecture Components

### 1. Load Balancer Layer
- **HAProxy** with WebSocket support and sticky sessions
- **Session affinity** based on room codes
- **Health checks** for server instances
- **SSL termination** and security headers

### 2. Server Instance Management
- **Multiple game server instances** running on different ports
- **Service discovery** with Redis-based registry
- **Health monitoring** and automatic failover
- **Graceful shutdown** with game migration

### 3. Inter-Server Communication
- **Redis Pub/Sub** for real-time state synchronization
- **Shared Redis cluster** for persistent game data
- **Event-driven architecture** for cross-server coordination
- **Message queuing** for reliable communication

### 4. Auto-Scaling System
- **Metrics-based scaling** (CPU, memory, connection count)
- **Game-aware scaling** (active rooms, player distribution)
- **Predictive scaling** based on historical patterns
- **Cost optimization** with intelligent instance management

## Detailed Implementation

### Load Balancer Configuration (HAProxy)

```haproxy
global
    daemon
    log stdout local0
    chroot /var/lib/haproxy
    stats socket /run/haproxy/admin.sock mode 660 level admin
    stats timeout 30s
    user haproxy
    group haproxy

defaults
    mode http
    timeout connect 5000ms
    timeout client 50000ms
    timeout server 50000ms
    option httplog
    log global

# Frontend for WebSocket connections
frontend hokm_websocket
    bind *:8765
    bind *:8766 ssl crt /etc/ssl/certs/hokm.pem
    
    # WebSocket upgrade handling
    acl is_websocket hdr(Connection) -i upgrade
    acl is_websocket hdr(Upgrade) -i websocket
    
    # Extract room code from WebSocket subprotocol or query string
    acl has_room_code url_param(room_code) -m found
    
    # Sticky session based on room code
    use_backend hokm_servers if is_websocket
    
    # Health check endpoint
    acl is_health_check path_beg /health
    use_backend hokm_health if is_health_check

# Backend server pool
backend hokm_servers
    balance source
    hash-type consistent
    
    # Sticky sessions based on room code
    stick-table type string len 32 size 10k expire 4h
    stick on url_param(room_code)
    
    # Server health checks
    option httpchk GET /health
    http-check expect status 200
    
    # Server instances (dynamically managed)
    server hokm1 127.0.0.1:8001 check inter 5s fall 3 rise 2
    server hokm2 127.0.0.1:8002 check inter 5s fall 3 rise 2
    server hokm3 127.0.0.1:8003 check inter 5s fall 3 rise 2
    server hokm4 127.0.0.1:8004 check inter 5s fall 3 rise 2
    
    # Backup servers for failover
    server hokm5 127.0.0.1:8005 check inter 5s fall 3 rise 2 backup
    server hokm6 127.0.0.1:8006 check inter 5s fall 3 rise 2 backup

# Health check backend
backend hokm_health
    http-request return status 200 content-type text/plain string "OK"

# Statistics interface
listen stats
    bind *:8404
    stats enable
    stats uri /stats
    stats refresh 30s
    stats admin if TRUE
```

### Server Instance with Service Discovery

```python
# backend/scalable_server.py
import asyncio
import websockets
import json
import time
import threading
import os
import signal
from typing import Dict, Set, Optional
from dataclasses import dataclass, asdict

from redis_manager_resilient import ResilientRedisManager
from circuit_breaker_monitor import CircuitBreakerMonitor
from game_board import GameBoard
from network import NetworkManager

@dataclass
class ServerInstance:
    """Server instance metadata"""
    instance_id: str
    host: str
    port: int
    status: str  # 'starting', 'ready', 'draining', 'stopped'
    started_at: float
    active_games: int
    connected_players: int
    cpu_usage: float
    memory_usage: float
    last_heartbeat: float

class ServiceRegistry:
    """Service discovery and registration"""
    
    def __init__(self, redis_manager: ResilientRedisManager):
        self.redis = redis_manager
        self.instance_id = f"hokm-{os.getpid()}-{int(time.time())}"
        self.heartbeat_interval = 30  # seconds
        self.cleanup_interval = 60    # seconds
        self._heartbeat_task = None
        self._cleanup_task = None
        
    async def register_instance(self, instance: ServerInstance):
        """Register this server instance"""
        key = f"service:hokm:instances:{instance.instance_id}"
        data = asdict(instance)
        
        # Register with TTL
        self.redis.redis.hset(key, mapping={k: str(v) for k, v in data.items()})
        self.redis.redis.expire(key, self.heartbeat_interval * 3)
        
        print(f"[SERVICE] Registered instance {instance.instance_id}")
    
    async def update_instance_metrics(self, instance: ServerInstance):
        """Update instance metrics"""
        key = f"service:hokm:instances:{instance.instance_id}"
        metrics = {
            'active_games': str(instance.active_games),
            'connected_players': str(instance.connected_players),
            'cpu_usage': str(instance.cpu_usage),
            'memory_usage': str(instance.memory_usage),
            'last_heartbeat': str(time.time())
        }
        
        self.redis.redis.hset(key, mapping=metrics)
        self.redis.redis.expire(key, self.heartbeat_interval * 3)
    
    async def get_all_instances(self) -> Dict[str, ServerInstance]:
        """Get all registered server instances"""
        pattern = "service:hokm:instances:*"
        instances = {}
        
        for key in self.redis.redis.scan_iter(pattern):
            instance_data = self.redis.redis.hgetall(key)
            if instance_data:
                instance_id = key.decode().split(':')[-1]
                instances[instance_id] = ServerInstance(
                    instance_id=instance_id,
                    host=instance_data[b'host'].decode(),
                    port=int(instance_data[b'port']),
                    status=instance_data[b'status'].decode(),
                    started_at=float(instance_data[b'started_at']),
                    active_games=int(instance_data[b'active_games']),
                    connected_players=int(instance_data[b'connected_players']),
                    cpu_usage=float(instance_data[b'cpu_usage']),
                    memory_usage=float(instance_data[b'memory_usage']),
                    last_heartbeat=float(instance_data[b'last_heartbeat'])
                )
        
        return instances
    
    async def start_heartbeat(self, instance: ServerInstance):
        """Start heartbeat process"""
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop(instance))
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
    
    async def stop_heartbeat(self):
        """Stop heartbeat process"""
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        if self._cleanup_task:
            self._cleanup_task.cancel()
        
        # Deregister instance
        key = f"service:hokm:instances:{self.instance_id}"
        self.redis.redis.delete(key)
    
    async def _heartbeat_loop(self, instance: ServerInstance):
        """Heartbeat loop"""
        while True:
            try:
                await self.update_instance_metrics(instance)
                await asyncio.sleep(self.heartbeat_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[SERVICE] Heartbeat error: {e}")
                await asyncio.sleep(5)
    
    async def _cleanup_loop(self):
        """Cleanup dead instances"""
        while True:
            try:
                await asyncio.sleep(self.cleanup_interval)
                
                current_time = time.time()
                instances = await self.get_all_instances()
                
                for instance_id, instance in instances.items():
                    if current_time - instance.last_heartbeat > self.heartbeat_interval * 2:
                        # Instance is dead, remove it
                        key = f"service:hokm:instances:{instance_id}"
                        self.redis.redis.delete(key)
                        print(f"[SERVICE] Removed dead instance {instance_id}")
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[SERVICE] Cleanup error: {e}")

class InterServerCommunication:
    """Handles communication between server instances"""
    
    def __init__(self, redis_manager: ResilientRedisManager, instance_id: str):
        self.redis = redis_manager
        self.instance_id = instance_id
        self.pubsub = None
        self.message_handlers = {}
        self._listen_task = None
    
    async def start(self):
        """Start inter-server communication"""
        self.pubsub = self.redis.redis.pubsub()
        
        # Subscribe to channels
        channels = [
            f"hokm:broadcast",           # Global broadcasts
            f"hokm:instance:{self.instance_id}",  # Instance-specific messages
            f"hokm:game_migration",     # Game migration events
            f"hokm:scaling_events"      # Scaling events
        ]
        
        for channel in channels:
            await self.pubsub.subscribe(channel)
        
        self._listen_task = asyncio.create_task(self._message_listener())
        print(f"[COMM] Inter-server communication started for {self.instance_id}")
    
    async def stop(self):
        """Stop inter-server communication"""
        if self._listen_task:
            self._listen_task.cancel()
        if self.pubsub:
            await self.pubsub.close()
    
    async def broadcast_message(self, message_type: str, data: dict):
        """Broadcast message to all servers"""
        message = {
            'type': message_type,
            'source': self.instance_id,
            'timestamp': time.time(),
            'data': data
        }
        
        await self.redis.redis.publish('hokm:broadcast', json.dumps(message))
    
    async def send_to_instance(self, target_instance: str, message_type: str, data: dict):
        """Send message to specific instance"""
        message = {
            'type': message_type,
            'source': self.instance_id,
            'timestamp': time.time(),
            'data': data
        }
        
        channel = f"hokm:instance:{target_instance}"
        await self.redis.redis.publish(channel, json.dumps(message))
    
    def register_handler(self, message_type: str, handler):
        """Register message handler"""
        self.message_handlers[message_type] = handler
    
    async def _message_listener(self):
        """Listen for inter-server messages"""
        try:
            async for message in self.pubsub.listen():
                if message['type'] == 'message':
                    try:
                        data = json.loads(message['data'].decode())
                        message_type = data.get('type')
                        
                        if message_type in self.message_handlers:
                            await self.message_handlers[message_type](data)
                            
                    except Exception as e:
                        print(f"[COMM] Message handling error: {e}")
                        
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"[COMM] Message listener error: {e}")

class ScalableGameServer:
    """Main scalable game server with load balancing support"""
    
    def __init__(self, host='0.0.0.0', port=8001):
        self.host = host
        self.port = port
        self.instance_id = f"hokm-{os.getpid()}-{int(time.time())}"
        
        # Core components
        self.redis_manager = ResilientRedisManager()
        self.circuit_breaker_monitor = CircuitBreakerMonitor(self.redis_manager)
        self.network_manager = NetworkManager()
        
        # Scaling components
        self.service_registry = ServiceRegistry(self.redis_manager)
        self.inter_server_comm = InterServerCommunication(self.redis_manager, self.instance_id)
        
        # Game state
        self.active_games = {}
        self.room_assignments = {}  # room_code -> instance_id
        
        # Server state
        self.status = 'starting'
        self.graceful_shutdown = False
        self.shutdown_timeout = 300  # 5 minutes
        
        # Metrics
        self.connected_players = 0
        self.start_time = time.time()
        
        # Setup signal handlers
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
        
        print(f"[SERVER] Scalable server initialized: {self.instance_id}")
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        print(f"[SERVER] Received signal {signum}, initiating graceful shutdown")
        asyncio.create_task(self.graceful_shutdown_sequence())
    
    async def start(self):
        """Start the scalable server"""
        try:
            # Create server instance metadata
            instance = ServerInstance(
                instance_id=self.instance_id,
                host=self.host,
                port=self.port,
                status='starting',
                started_at=self.start_time,
                active_games=0,
                connected_players=0,
                cpu_usage=0.0,
                memory_usage=0.0,
                last_heartbeat=time.time()
            )
            
            # Register with service discovery
            await self.service_registry.register_instance(instance)
            await self.service_registry.start_heartbeat(instance)
            
            # Start inter-server communication
            await self.inter_server_comm.start()
            self._register_inter_server_handlers()
            
            # Load active games from Redis
            await self.load_active_games_from_redis()
            
            # Update status to ready
            self.status = 'ready'
            instance.status = 'ready'
            await self.service_registry.update_instance_metrics(instance)
            
            # Start WebSocket server
            print(f"[SERVER] Starting WebSocket server on {self.host}:{self.port}")
            async with websockets.serve(
                self.handle_connection,
                self.host,
                self.port,
                ping_interval=20,
                ping_timeout=10,
                close_timeout=10
            ):
                print(f"[SERVER] Server {self.instance_id} ready on {self.host}:{self.port}")
                
                # Keep server running
                while not self.graceful_shutdown:
                    await asyncio.sleep(1)
                    
                    # Update metrics periodically
                    if int(time.time()) % 30 == 0:  # Every 30 seconds
                        await self._update_metrics(instance)
            
        except Exception as e:
            print(f"[SERVER] Server startup failed: {e}")
            self.status = 'error'
        finally:
            await self.cleanup()
    
    async def _update_metrics(self, instance: ServerInstance):
        """Update server metrics"""
        import psutil
        
        instance.active_games = len(self.active_games)
        instance.connected_players = self.connected_players
        instance.cpu_usage = psutil.cpu_percent()
        instance.memory_usage = psutil.virtual_memory().percent
        instance.last_heartbeat = time.time()
        
        await self.service_registry.update_instance_metrics(instance)
    
    def _register_inter_server_handlers(self):
        """Register handlers for inter-server messages"""
        self.inter_server_comm.register_handler('game_migration_request', self._handle_game_migration_request)
        self.inter_server_comm.register_handler('game_migration_data', self._handle_game_migration_data)
        self.inter_server_comm.register_handler('player_reconnect_query', self._handle_player_reconnect_query)
        self.inter_server_comm.register_handler('room_assignment_update', self._handle_room_assignment_update)
        self.inter_server_comm.register_handler('scaling_event', self._handle_scaling_event)
    
    async def _handle_game_migration_request(self, message):
        """Handle game migration request from another server"""
        data = message['data']
        room_code = data['room_code']
        target_instance = data['target_instance']
        
        if room_code in self.active_games and target_instance != self.instance_id:
            # Prepare game for migration
            game_data = await self._serialize_game_state(room_code)
            
            # Send game data to target instance
            await self.inter_server_comm.send_to_instance(
                target_instance,
                'game_migration_data',
                {
                    'room_code': room_code,
                    'game_data': game_data,
                    'source_instance': self.instance_id
                }
            )
            
            print(f"[MIGRATION] Sent game {room_code} to {target_instance}")
    
    async def _handle_game_migration_data(self, message):
        """Handle incoming game migration data"""
        data = message['data']
        room_code = data['room_code']
        game_data = data['game_data']
        source_instance = data['source_instance']
        
        # Restore game state
        await self._deserialize_game_state(room_code, game_data)
        
        # Update room assignment
        self.room_assignments[room_code] = self.instance_id
        
        print(f"[MIGRATION] Received game {room_code} from {source_instance}")
    
    async def _handle_player_reconnect_query(self, message):
        """Handle player reconnection query"""
        data = message['data']
        player_id = data['player_id']
        querying_instance = message['source']
        
        # Check if player is in any of our games
        for room_code, game in self.active_games.items():
            if self._player_in_game(player_id, game):
                # Send room info back to querying instance
                await self.inter_server_comm.send_to_instance(
                    querying_instance,
                    'player_reconnect_response',
                    {
                        'player_id': player_id,
                        'room_code': room_code,
                        'target_instance': self.instance_id
                    }
                )
                break
    
    async def _handle_room_assignment_update(self, message):
        """Handle room assignment updates"""
        data = message['data']
        room_code = data['room_code']
        instance_id = data['instance_id']
        
        self.room_assignments[room_code] = instance_id
    
    async def _handle_scaling_event(self, message):
        """Handle scaling events"""
        data = message['data']
        event_type = data['event_type']
        
        if event_type == 'scale_down_prepare':
            # Prepare for scale down by migrating games
            target_instances = data['target_instances']
            await self._migrate_games_for_scale_down(target_instances)
        elif event_type == 'scale_up_complete':
            # New instances are available
            await self._rebalance_games()
    
    async def graceful_shutdown_sequence(self):
        """Perform graceful shutdown"""
        print(f"[SERVER] Starting graceful shutdown for {self.instance_id}")
        
        self.status = 'draining'
        self.graceful_shutdown = True
        
        # Stop accepting new connections
        # Migrate active games to other instances
        if self.active_games:
            print(f"[SERVER] Migrating {len(self.active_games)} active games")
            
            # Get available instances
            instances = await self.service_registry.get_all_instances()
            available_instances = [
                iid for iid, inst in instances.items() 
                if inst.status == 'ready' and iid != self.instance_id
            ]
            
            if available_instances:
                await self._migrate_all_games(available_instances)
            else:
                print("[SERVER] No available instances for game migration")
        
        # Wait for games to finish or timeout
        shutdown_start = time.time()
        while self.active_games and (time.time() - shutdown_start) < self.shutdown_timeout:
            await asyncio.sleep(1)
        
        print(f"[SERVER] Graceful shutdown complete for {self.instance_id}")
    
    async def cleanup(self):
        """Cleanup server resources"""
        await self.service_registry.stop_heartbeat()
        await self.inter_server_comm.stop()
        self.status = 'stopped'
    
    # Additional methods for game migration, load balancing, etc.
    # [Implementation continues...]

if __name__ == "__main__":
    import sys
    
    # Get port from command line or environment
    port = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get('PORT', 8001))
    
    server = ScalableGameServer(port=port)
    
    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        print("Server stopped by user")
    except Exception as e:
        print(f"Server error: {e}")
```

This implementation provides:

1. **WebSocket-aware load balancing** with HAProxy
2. **Sticky session handling** based on room codes
3. **Service discovery** with Redis-based registry
4. **Inter-server communication** using Redis Pub/Sub
5. **Graceful shutdown** with game migration capabilities
6. **Health monitoring** and automatic failover

The system ensures players in the same game connect to the same server instance while providing horizontal scaling capabilities. Would you like me to continue with the auto-scaling triggers and deployment configuration?
