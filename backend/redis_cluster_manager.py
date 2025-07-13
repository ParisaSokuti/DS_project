# redis_cluster_manager.py
import redis
import redis.sentinel
from rediscluster import RedisCluster
import json
import time
import hashlib
import asyncio
import logging
from typing import Dict, List, Optional, Any, Tuple, Set
from dataclasses import dataclass
from enum import Enum
import threading
from collections import defaultdict
import psutil

class ClusterHealth(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded" 
    CRITICAL = "critical"
    FAILED = "failed"

@dataclass
class NodeInfo:
    host: str
    port: int
    node_id: str
    is_master: bool
    slots: List[int]
    health_status: ClusterHealth
    last_ping: float
    connections: int
    memory_usage: float
    cpu_usage: float
    
@dataclass 
class ClusterMetrics:
    total_nodes: int
    healthy_nodes: int
    total_operations: int
    failed_operations: int
    cross_slot_operations: int
    rebalance_operations: int
    failover_count: int
    avg_latency: float
    memory_usage: Dict[str, float]
    connection_pool_usage: Dict[str, int]

class ConsistentHashRing:
    """Consistent hashing implementation for game room distribution"""
    
    def __init__(self, nodes: List[str], replicas: int = 150):
        self.replicas = replicas
        self.ring = {}
        self.sorted_keys = []
        self.nodes = set()
        
        for node in nodes:
            self.add_node(node)
    
    def _hash(self, key: str) -> int:
        """Generate hash for consistent hashing"""
        return int(hashlib.md5(key.encode('utf-8')).hexdigest(), 16)
    
    def add_node(self, node: str):
        """Add a node to the hash ring"""
        if node in self.nodes:
            return
            
        self.nodes.add(node)
        for i in range(self.replicas):
            replica_key = f"{node}:{i}"
            key = self._hash(replica_key)
            self.ring[key] = node
            
        self.sorted_keys = sorted(self.ring.keys())
        
    def remove_node(self, node: str):
        """Remove a node from the hash ring"""
        if node not in self.nodes:
            return
            
        self.nodes.remove(node)
        keys_to_remove = []
        
        for key, mapped_node in self.ring.items():
            if mapped_node == node:
                keys_to_remove.append(key)
                
        for key in keys_to_remove:
            del self.ring[key]
            
        self.sorted_keys = sorted(self.ring.keys())
    
    def get_node(self, key: str) -> Optional[str]:
        """Get the node responsible for a given key"""
        if not self.ring:
            return None
            
        key_hash = self._hash(key)
        
        # Find the first node with hash >= key_hash
        for ring_key in self.sorted_keys:
            if ring_key >= key_hash:
                return self.ring[ring_key]
                
        # If we've gone past the end, wrap around to the first node
        return self.ring[self.sorted_keys[0]]
    
    def get_nodes_for_key(self, key: str, count: int = 3) -> List[str]:
        """Get multiple nodes for redundancy"""
        if not self.ring or count <= 0:
            return []
            
        key_hash = self._hash(key)
        nodes = []
        seen_nodes = set()
        
        # Start from the primary node position
        start_index = 0
        for i, ring_key in enumerate(self.sorted_keys):
            if ring_key >= key_hash:
                start_index = i
                break
        
        # Collect unique nodes
        for i in range(len(self.sorted_keys)):
            index = (start_index + i) % len(self.sorted_keys)
            node = self.ring[self.sorted_keys[index]]
            
            if node not in seen_nodes:
                nodes.append(node)
                seen_nodes.add(node)
                
                if len(nodes) >= count:
                    break
                    
        return nodes

class RedisClusterManager:
    """
    High-availability Redis cluster manager with:
    - Consistent hashing for game room distribution
    - Automatic failover capabilities
    - Cross-slot operations handling
    - Cluster health monitoring
    - Game session persistence
    """
    
    def __init__(self, cluster_nodes: List[Dict[str, Any]], 
                 sentinel_nodes: Optional[List[Dict[str, Any]]] = None,
                 max_connections_per_node: int = 100):
        
        # Configuration
        self.cluster_nodes = cluster_nodes
        self.sentinel_nodes = sentinel_nodes or []
        self.max_connections_per_node = max_connections_per_node
        
        # Initialize connections
        self.cluster_client = None
        self.sentinel_client = None
        self.node_clients = {}
        self.connection_pools = {}
        
        # Consistent hashing
        node_names = [f"{node['host']}:{node['port']}" for node in cluster_nodes]
        self.hash_ring = ConsistentHashRing(node_names)
        
        # Health monitoring
        self.node_health = {}
        self.cluster_metrics = ClusterMetrics(
            total_nodes=len(cluster_nodes),
            healthy_nodes=0,
            total_operations=0,
            failed_operations=0,
            cross_slot_operations=0,
            rebalance_operations=0,
            failover_count=0,
            avg_latency=0.0,
            memory_usage={},
            connection_pool_usage={}
        )
        
        # Game session tracking
        self.game_session_nodes = {}  # room_code -> node_id
        self.node_game_sessions = defaultdict(set)  # node_id -> set of room_codes
        
        # Monitoring thread
        self.monitoring_thread = None
        self.monitoring_active = False
        
        # Initialize cluster
        self._initialize_cluster()
        self._start_health_monitoring()
    
    def _initialize_cluster(self):
        """Initialize Redis cluster connections"""
        try:
            # Initialize cluster client
            if self.cluster_nodes:
                startup_nodes = [
                    {"host": node["host"], "port": node["port"]} 
                    for node in self.cluster_nodes
                ]
                
                self.cluster_client = RedisCluster(
                    startup_nodes=startup_nodes,
                    decode_responses=True,
                    skip_full_coverage_check=True,
                    max_connections_per_node=self.max_connections_per_node,
                    retry_on_timeout=True,
                    health_check_interval=30
                )
            
            # Initialize sentinel client if configured
            if self.sentinel_nodes:
                sentinels = [(node["host"], node["port"]) for node in self.sentinel_nodes]
                self.sentinel_client = redis.sentinel.Sentinel(sentinels)
            
            # Initialize individual node clients for direct operations
            for node in self.cluster_nodes:
                node_id = f"{node['host']}:{node['port']}"
                try:
                    client = redis.Redis(
                        host=node['host'],
                        port=node['port'],
                        decode_responses=True,
                        socket_connect_timeout=5,
                        socket_timeout=10,
                        retry_on_timeout=True
                    )
                    
                    # Test connection
                    client.ping()
                    self.node_clients[node_id] = client
                    
                    self.node_health[node_id] = NodeInfo(
                        host=node['host'],
                        port=node['port'],
                        node_id=node_id,
                        is_master=True,  # Will be updated during health check
                        slots=[],
                        health_status=ClusterHealth.HEALTHY,
                        last_ping=time.time(),
                        connections=0,
                        memory_usage=0.0,
                        cpu_usage=0.0
                    )
                    
                except Exception as e:
                    logging.error(f"Failed to connect to node {node_id}: {e}")
                    self.node_health[node_id] = NodeInfo(
                        host=node['host'],
                        port=node['port'],
                        node_id=node_id,
                        is_master=False,
                        slots=[],
                        health_status=ClusterHealth.FAILED,
                        last_ping=0,
                        connections=0,
                        memory_usage=0.0,
                        cpu_usage=0.0
                    )
            
            logging.info(f"Initialized Redis cluster with {len(self.node_clients)} nodes")
            
        except Exception as e:
            logging.error(f"Failed to initialize Redis cluster: {e}")
            raise
    
    def _start_health_monitoring(self):
        """Start background health monitoring"""
        self.monitoring_active = True
        self.monitoring_thread = threading.Thread(target=self._health_monitor_loop)
        self.monitoring_thread.daemon = True
        self.monitoring_thread.start()
    
    def _health_monitor_loop(self):
        """Background health monitoring loop"""
        while self.monitoring_active:
            try:
                self._check_cluster_health()
                self._update_cluster_metrics()
                time.sleep(10)  # Check every 10 seconds
            except Exception as e:
                logging.error(f"Health monitoring error: {e}")
                time.sleep(5)  # Shorter sleep on error
    
    def _check_cluster_health(self):
        """Check health of all cluster nodes"""
        healthy_count = 0
        
        for node_id, client in self.node_clients.items():
            try:
                start_time = time.time()
                
                # Ping test
                client.ping()
                ping_time = time.time() - start_time
                
                # Get node info
                info = client.info()
                
                # Update node health
                if node_id in self.node_health:
                    node_info = self.node_health[node_id]
                    node_info.last_ping = time.time()
                    node_info.memory_usage = info.get('used_memory', 0)
                    node_info.connections = info.get('connected_clients', 0)
                    
                    # Determine health status
                    if ping_time < 0.1:  # < 100ms
                        node_info.health_status = ClusterHealth.HEALTHY
                    elif ping_time < 0.5:  # < 500ms
                        node_info.health_status = ClusterHealth.DEGRADED
                    else:
                        node_info.health_status = ClusterHealth.CRITICAL
                    
                    if node_info.health_status in [ClusterHealth.HEALTHY, ClusterHealth.DEGRADED]:
                        healthy_count += 1
                        
            except Exception as e:
                logging.warning(f"Health check failed for node {node_id}: {e}")
                if node_id in self.node_health:
                    self.node_health[node_id].health_status = ClusterHealth.FAILED
                    
                # Try to reconnect failed nodes
                self._attempt_node_reconnection(node_id)
        
        self.cluster_metrics.healthy_nodes = healthy_count
    
    def _attempt_node_reconnection(self, node_id: str):
        """Attempt to reconnect to a failed node"""
        try:
            if node_id not in self.node_health:
                return
                
            node_info = self.node_health[node_id]
            
            # Create new client
            client = redis.Redis(
                host=node_info.host,
                port=node_info.port,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=10
            )
            
            # Test connection
            client.ping()
            
            # Update client and status
            self.node_clients[node_id] = client
            node_info.health_status = ClusterHealth.HEALTHY
            node_info.last_ping = time.time()
            
            logging.info(f"Successfully reconnected to node {node_id}")
            
        except Exception as e:
            logging.warning(f"Failed to reconnect to node {node_id}: {e}")
    
    def _update_cluster_metrics(self):
        """Update cluster-wide metrics"""
        try:
            # Update memory usage per node
            for node_id, node_info in self.node_health.items():
                if node_info.health_status != ClusterHealth.FAILED:
                    self.cluster_metrics.memory_usage[node_id] = node_info.memory_usage
                    
                    if node_id in self.node_clients:
                        pool_size = getattr(self.node_clients[node_id].connection_pool, 
                                          'created_connections', 0)
                        self.cluster_metrics.connection_pool_usage[node_id] = pool_size
            
        except Exception as e:
            logging.error(f"Failed to update cluster metrics: {e}")
    
    def get_node_for_room(self, room_code: str) -> str:
        """Get the responsible node for a game room using consistent hashing"""
        # Check if room already has an assigned node
        if room_code in self.game_session_nodes:
            assigned_node = self.game_session_nodes[room_code]
            
            # Verify node is still healthy
            if (assigned_node in self.node_health and 
                self.node_health[assigned_node].health_status in 
                [ClusterHealth.HEALTHY, ClusterHealth.DEGRADED]):
                return assigned_node
            else:
                # Node failed, need to reassign
                logging.warning(f"Assigned node {assigned_node} for room {room_code} is unhealthy, reassigning")
                self._handle_room_failover(room_code, assigned_node)
        
        # Get node from consistent hash ring
        target_node = self.hash_ring.get_node(room_code)
        
        # Verify target node is healthy
        if (target_node and target_node in self.node_health and
            self.node_health[target_node].health_status in 
            [ClusterHealth.HEALTHY, ClusterHealth.DEGRADED]):
            
            # Assign room to node
            self.game_session_nodes[room_code] = target_node
            self.node_game_sessions[target_node].add(room_code)
            return target_node
        
        # Find alternative healthy node
        for node_id, node_info in self.node_health.items():
            if node_info.health_status in [ClusterHealth.HEALTHY, ClusterHealth.DEGRADED]:
                self.game_session_nodes[room_code] = node_id
                self.node_game_sessions[node_id].add(room_code)
                logging.info(f"Assigned room {room_code} to alternative node {node_id}")
                return node_id
        
        # Critical: No healthy nodes available
        logging.critical("No healthy nodes available for room assignment!")
        raise Exception("Cluster critical failure: No healthy nodes available")
    
    def _handle_room_failover(self, room_code: str, failed_node: str):
        """Handle failover of a game room to a new node"""
        try:
            logging.info(f"Starting failover for room {room_code} from failed node {failed_node}")
            
            # Get room data from failed node (if possible)
            room_data = None
            try:
                if failed_node in self.node_clients:
                    room_data = self._get_room_data_from_node(room_code, failed_node)
            except:
                logging.warning(f"Could not retrieve room data from failed node {failed_node}")
            
            # Remove room from failed node tracking
            if room_code in self.game_session_nodes:
                del self.game_session_nodes[room_code]
            if failed_node in self.node_game_sessions:
                self.node_game_sessions[failed_node].discard(room_code)
            
            # Find new node for room
            new_node = self.get_node_for_room(room_code)
            
            # Migrate room data if available
            if room_data and new_node != failed_node:
                self._migrate_room_data(room_code, new_node, room_data)
                logging.info(f"Successfully failed over room {room_code} to node {new_node}")
            
            self.cluster_metrics.failover_count += 1
            
        except Exception as e:
            logging.error(f"Failover failed for room {room_code}: {e}")
    
    def _get_room_data_from_node(self, room_code: str, node_id: str) -> Dict[str, Any]:
        """Get all room data from a specific node"""
        client = self.node_clients[node_id]
        room_data = {}
        
        # Get game state
        game_key = f"game:{room_code}:state"
        game_state = client.hgetall(game_key)
        if game_state:
            room_data['game_state'] = game_state
        
        # Get players
        players_key = f"room:{room_code}:players"
        players = client.lrange(players_key, 0, -1)
        if players:
            room_data['players'] = players
        
        # Get any other room-related keys
        for key in client.scan_iter(f"*{room_code}*"):
            if key not in [game_key, players_key]:
                key_type = client.type(key)
                if key_type == 'string':
                    room_data[key] = client.get(key)
                elif key_type == 'hash':
                    room_data[key] = client.hgetall(key)
                elif key_type == 'list':
                    room_data[key] = client.lrange(key, 0, -1)
                elif key_type == 'set':
                    room_data[key] = client.smembers(key)
        
        return room_data
    
    def _migrate_room_data(self, room_code: str, target_node: str, room_data: Dict[str, Any]):
        """Migrate room data to a new node"""
        client = self.node_clients[target_node]
        
        # Migrate game state
        if 'game_state' in room_data:
            game_key = f"game:{room_code}:state"
            client.hset(game_key, mapping=room_data['game_state'])
            client.expire(game_key, 3600)
        
        # Migrate players
        if 'players' in room_data:
            players_key = f"room:{room_code}:players"
            client.delete(players_key)  # Clear existing
            for player in room_data['players']:
                client.rpush(players_key, player)
            client.expire(players_key, 3600)
        
        # Migrate other keys
        for key, value in room_data.items():
            if key not in ['game_state', 'players']:
                if isinstance(value, dict):
                    client.hset(key, mapping=value)
                elif isinstance(value, list):
                    client.delete(key)
                    for item in value:
                        client.rpush(key, item)
                elif isinstance(value, set):
                    client.delete(key)
                    for item in value:
                        client.sadd(key, item)
                else:
                    client.set(key, value)
                
                client.expire(key, 3600)
    
    def execute_on_node(self, node_id: str, operation: callable, *args, **kwargs):
        """Execute an operation on a specific node"""
        if node_id not in self.node_clients:
            raise Exception(f"Node {node_id} not available")
        
        client = self.node_clients[node_id]
        start_time = time.time()
        
        try:
            result = operation(client, *args, **kwargs)
            
            # Update metrics
            self.cluster_metrics.total_operations += 1
            latency = time.time() - start_time
            
            # Update running average
            total_ops = self.cluster_metrics.total_operations
            current_avg = self.cluster_metrics.avg_latency
            self.cluster_metrics.avg_latency = ((current_avg * (total_ops - 1)) + latency) / total_ops
            
            return result
            
        except Exception as e:
            self.cluster_metrics.failed_operations += 1
            logging.error(f"Operation failed on node {node_id}: {e}")
            raise
    
    def save_game_state(self, room_code: str, game_state: dict) -> bool:
        """Save game state to the appropriate node"""
        try:
            node_id = self.get_node_for_room(room_code)
            
            def save_operation(client, room_code, state):
                # Add metadata
                if 'created_at' not in state:
                    state['created_at'] = str(int(time.time()))
                state['last_activity'] = str(int(time.time()))
                
                # Encode state
                encoded_state = {}
                for k, v in state.items():
                    if isinstance(v, (dict, list)):
                        encoded_state[k] = json.dumps(v)
                    else:
                        encoded_state[k] = str(v)
                
                # Save with pipeline for atomicity
                pipe = client.pipeline()
                key = f"game:{room_code}:state"
                pipe.hset(key, mapping=encoded_state)
                pipe.expire(key, 3600)
                pipe.execute()
                return True
            
            return self.execute_on_node(node_id, save_operation, room_code, game_state)
            
        except Exception as e:
            logging.error(f"Failed to save game state for room {room_code}: {e}")
            return False
    
    def get_game_state(self, room_code: str) -> dict:
        """Get game state from the appropriate node"""
        try:
            node_id = self.get_node_for_room(room_code)
            
            def get_operation(client, room_code):
                key = f"game:{room_code}:state"
                raw_state = client.hgetall(key)
                if not raw_state:
                    return {}
                
                # Decode state
                state = {}
                for k, v in raw_state.items():
                    try:
                        if k in ['teams', 'players', 'tricks', 'player_order'] or k.startswith('hand_'):
                            state[k] = json.loads(v)
                        else:
                            state[k] = v
                    except json.JSONDecodeError:
                        state[k] = v
                
                return state
            
            return self.execute_on_node(node_id, get_operation, room_code)
            
        except Exception as e:
            logging.error(f"Failed to get game state for room {room_code}: {e}")
            return {}
    
    def save_player_session(self, player_id: str, session_data: dict) -> bool:
        """Save player session using consistent hashing"""
        try:
            # Use player_id for consistent hashing of sessions
            node_id = self.hash_ring.get_node(f"session:{player_id}")
            
            # Find healthy node
            if (node_id not in self.node_health or 
                self.node_health[node_id].health_status == ClusterHealth.FAILED):
                # Find alternative healthy node
                for nid, node_info in self.node_health.items():
                    if node_info.health_status in [ClusterHealth.HEALTHY, ClusterHealth.DEGRADED]:
                        node_id = nid
                        break
            
            def save_session_operation(client, player_id, data):
                key = f"session:{player_id}"
                updated_data = {
                    'last_heartbeat': str(int(time.time()))
                }
                if 'connection_status' not in data:
                    updated_data['connection_status'] = 'active'
                
                updated_data.update(data)
                client.hset(key, mapping=updated_data)
                client.expire(key, 3600)
                return True
            
            return self.execute_on_node(node_id, save_session_operation, player_id, session_data)
            
        except Exception as e:
            logging.error(f"Failed to save session for player {player_id}: {e}")
            return False
    
    def handle_cross_slot_operation(self, keys: List[str], operation: callable, *args, **kwargs):
        """Handle operations that span multiple slots/nodes"""
        self.cluster_metrics.cross_slot_operations += 1
        
        try:
            # Group keys by their target nodes
            node_groups = defaultdict(list)
            for key in keys:
                if key.startswith('session:'):
                    node_id = self.hash_ring.get_node(key)
                else:
                    # Extract room code from key pattern
                    parts = key.split(':')
                    if len(parts) >= 2:
                        room_code = parts[1]
                        node_id = self.get_node_for_room(room_code)
                    else:
                        node_id = self.hash_ring.get_node(key)
                
                node_groups[node_id].append(key)
            
            # Execute operation on each node with its keys
            results = {}
            for node_id, node_keys in node_groups.items():
                try:
                    result = self.execute_on_node(node_id, operation, node_keys, *args, **kwargs)
                    results[node_id] = result
                except Exception as e:
                    logging.error(f"Cross-slot operation failed on node {node_id}: {e}")
                    results[node_id] = None
            
            return results
            
        except Exception as e:
            logging.error(f"Cross-slot operation failed: {e}")
            return {}
    
    def get_cluster_status(self) -> Dict[str, Any]:
        """Get comprehensive cluster status"""
        healthy_nodes = sum(1 for node in self.node_health.values() 
                          if node.health_status in [ClusterHealth.HEALTHY, ClusterHealth.DEGRADED])
        
        overall_health = ClusterHealth.HEALTHY
        if healthy_nodes == 0:
            overall_health = ClusterHealth.FAILED
        elif healthy_nodes < len(self.node_health) * 0.5:
            overall_health = ClusterHealth.CRITICAL
        elif healthy_nodes < len(self.node_health):
            overall_health = ClusterHealth.DEGRADED
        
        return {
            'overall_health': overall_health.value,
            'nodes': {
                node_id: {
                    'host': info.host,
                    'port': info.port,
                    'health': info.health_status.value,
                    'last_ping': info.last_ping,
                    'connections': info.connections,
                    'memory_usage': info.memory_usage,
                    'game_sessions': len(self.node_game_sessions.get(node_id, set()))
                }
                for node_id, info in self.node_health.items()
            },
            'metrics': {
                'total_nodes': self.cluster_metrics.total_nodes,
                'healthy_nodes': healthy_nodes,
                'total_operations': self.cluster_metrics.total_operations,
                'failed_operations': self.cluster_metrics.failed_operations,
                'error_rate': (self.cluster_metrics.failed_operations / 
                              max(1, self.cluster_metrics.total_operations)) * 100,
                'avg_latency_ms': self.cluster_metrics.avg_latency * 1000,
                'cross_slot_operations': self.cluster_metrics.cross_slot_operations,
                'failover_count': self.cluster_metrics.failover_count
            },
            'game_distribution': {
                node_id: len(sessions) 
                for node_id, sessions in self.node_game_sessions.items()
            }
        }
    
    def rebalance_cluster(self) -> bool:
        """Rebalance game sessions across healthy nodes"""
        try:
            logging.info("Starting cluster rebalancing...")
            
            healthy_nodes = [
                node_id for node_id, info in self.node_health.items()
                if info.health_status in [ClusterHealth.HEALTHY, ClusterHealth.DEGRADED]
            ]
            
            if len(healthy_nodes) < 2:
                logging.warning("Not enough healthy nodes for rebalancing")
                return False
            
            # Calculate target distribution
            total_sessions = sum(len(sessions) for sessions in self.node_game_sessions.values())
            target_per_node = total_sessions // len(healthy_nodes)
            
            # Find overloaded and underloaded nodes
            overloaded = []
            underloaded = []
            
            for node_id in healthy_nodes:
                session_count = len(self.node_game_sessions.get(node_id, set()))
                if session_count > target_per_node + 1:
                    overloaded.append((node_id, session_count))
                elif session_count < target_per_node:
                    underloaded.append((node_id, session_count))
            
            # Move sessions from overloaded to underloaded nodes
            migrations = 0
            for overloaded_node, session_count in overloaded:
                sessions_to_move = session_count - target_per_node
                sessions = list(self.node_game_sessions[overloaded_node])
                
                for i in range(min(sessions_to_move, len(sessions))):
                    if not underloaded:
                        break
                    
                    room_code = sessions[i]
                    target_node, target_count = underloaded[0]
                    
                    # Migrate the session
                    try:
                        room_data = self._get_room_data_from_node(room_code, overloaded_node)
                        self._migrate_room_data(room_code, target_node, room_data)
                        
                        # Update tracking
                        self.node_game_sessions[overloaded_node].discard(room_code)
                        self.node_game_sessions[target_node].add(room_code)
                        self.game_session_nodes[room_code] = target_node
                        
                        migrations += 1
                        
                        # Update underloaded list
                        underloaded[0] = (target_node, target_count + 1)
                        if target_count + 1 >= target_per_node:
                            underloaded.pop(0)
                            
                    except Exception as e:
                        logging.error(f"Failed to migrate session {room_code}: {e}")
            
            self.cluster_metrics.rebalance_operations += 1
            logging.info(f"Rebalancing completed. Migrated {migrations} sessions.")
            return True
            
        except Exception as e:
            logging.error(f"Cluster rebalancing failed: {e}")
            return False
    
    def shutdown(self):
        """Gracefully shutdown the cluster manager"""
        logging.info("Shutting down Redis cluster manager...")
        
        # Stop monitoring
        self.monitoring_active = False
        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=5)
        
        # Close connections
        if self.cluster_client:
            self.cluster_client.close()
        
        for client in self.node_clients.values():
            try:
                client.close()
            except:
                pass
        
        logging.info("Redis cluster manager shutdown complete")

# Usage example and compatibility wrapper
class RedisClusterWrapper:
    """
    Wrapper to maintain compatibility with existing RedisManager interface
    while adding cluster capabilities
    """
    
    def __init__(self, cluster_config: Dict[str, Any] = None):
        if cluster_config:
            self.cluster_manager = RedisClusterManager(**cluster_config)
            self.use_cluster = True
        else:
            # Fallback to single Redis instance
            from redis_manager import RedisManager
            self.redis_manager = RedisManager()
            self.use_cluster = False
    
    def save_game_state(self, room_code: str, game_state: dict) -> bool:
        if self.use_cluster:
            return self.cluster_manager.save_game_state(room_code, game_state)
        else:
            return self.redis_manager.save_game_state(room_code, game_state)
    
    def get_game_state(self, room_code: str) -> dict:
        if self.use_cluster:
            return self.cluster_manager.get_game_state(room_code)
        else:
            return self.redis_manager.get_game_state(room_code)
    
    def save_player_session(self, player_id: str, session_data: dict) -> bool:
        if self.use_cluster:
            return self.cluster_manager.save_player_session(player_id, session_data)
        else:
            return self.redis_manager.save_player_session(player_id, session_data)
    
    def get_cluster_status(self) -> Dict[str, Any]:
        if self.use_cluster:
            return self.cluster_manager.get_cluster_status()
        else:
            return {"status": "single_node", "health": "healthy"}
