# redis_cluster_integration.py
"""
Redis Cluster Integration Example for Game Server
"""

import asyncio
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime

from redis_cluster_manager import RedisClusterManager, RedisClusterWrapper
from redis_cluster_config import get_cluster_config
from redis_cluster_monitor import RedisClusterMonitor

class GameServerRedisCluster:
    """
    Game Server Integration with Redis Cluster
    
    Features:
    - High availability Redis cluster
    - Automatic failover for game sessions
    - Monitoring and health checks
    - Performance optimization
    - Graceful degradation
    """
    
    def __init__(self, environment: str = "development"):
        self.environment = environment
        self.config = get_cluster_config(environment)
        
        # Initialize cluster manager
        cluster_config = {
            'cluster_nodes': [
                {'host': node.host, 'port': node.port} 
                for node in self.config.nodes
            ],
            'sentinel_nodes': [
                {'host': node.host, 'port': node.port}
                for node in (self.config.sentinel_nodes or [])
            ] if self.config.sentinel_nodes else None,
            'max_connections_per_node': self.config.max_connections_per_node
        }
        
        self.cluster_manager = RedisClusterManager(**cluster_config)
        self.redis_wrapper = RedisClusterWrapper(cluster_config)
        
        # Initialize monitoring
        self.monitor = RedisClusterMonitor(self.cluster_manager)
        self.monitor.add_alert_callback(self._handle_alert)
        
        # Performance tracking
        self.performance_stats = {
            'requests_total': 0,
            'requests_failed': 0,
            'avg_latency_ms': 0.0,
            'game_operations': 0,
            'player_operations': 0
        }
        
        logging.info(f"Game server Redis cluster initialized for {environment}")
    
    async def start(self):
        """Start the Redis cluster and monitoring"""
        try:
            # Start monitoring
            self.monitor.start_monitoring()
            
            # Verify cluster connectivity
            await self._verify_cluster_health()
            
            logging.info("Redis cluster started successfully")
            return True
            
        except Exception as e:
            logging.error(f"Failed to start Redis cluster: {e}")
            return False
    
    async def stop(self):
        """Stop the Redis cluster and monitoring"""
        try:
            self.monitor.stop_monitoring()
            self.cluster_manager.shutdown()
            
            logging.info("Redis cluster stopped")
            
        except Exception as e:
            logging.error(f"Error stopping Redis cluster: {e}")
    
    async def _verify_cluster_health(self):
        """Verify cluster is healthy and ready"""
        status = self.cluster_manager.get_cluster_status()
        
        if status['overall_health'] == 'failed':
            raise Exception("Cluster is in failed state")
        
        healthy_nodes = status['metrics']['healthy_nodes']
        total_nodes = status['metrics']['total_nodes']
        
        if healthy_nodes < total_nodes * 0.5:
            logging.warning(f"Only {healthy_nodes}/{total_nodes} nodes are healthy")
        
        logging.info(f"Cluster health check passed: {healthy_nodes}/{total_nodes} nodes healthy")
    
    def _handle_alert(self, alert: Dict[str, Any]):
        """Handle cluster alerts"""
        level = alert['level']
        message = alert['message']
        
        if level == 'critical':
            logging.critical(f"CRITICAL ALERT: {message}")
            # Could trigger notifications, automatic scaling, etc.
        else:
            logging.warning(f"ALERT: {message}")
    
    # Game-specific operations with cluster support
    
    async def create_game_room(self, room_code: str, initial_state: Dict[str, Any]) -> bool:
        """Create a new game room with cluster placement"""
        try:
            # Add metadata for tracking
            initial_state.update({
                'created_at': datetime.utcnow().isoformat(),
                'cluster_node': self.cluster_manager.get_node_for_room(room_code),
                'version': 1
            })
            
            success = self.redis_wrapper.save_game_state(room_code, initial_state)
            
            if success:
                self.performance_stats['game_operations'] += 1
                logging.info(f"Created game room {room_code} on node {initial_state['cluster_node']}")
            
            return success
            
        except Exception as e:
            logging.error(f"Failed to create game room {room_code}: {e}")
            self.performance_stats['requests_failed'] += 1
            return False
    
    async def get_game_state(self, room_code: str) -> Optional[Dict[str, Any]]:
        """Get game state with automatic failover"""
        try:
            state = self.redis_wrapper.get_game_state(room_code)
            
            if state:
                self.performance_stats['game_operations'] += 1
                
                # Update last accessed time
                state['last_accessed'] = datetime.utcnow().isoformat()
                # Note: We could save this back, but it would increase write load
            
            return state if state else None
            
        except Exception as e:
            logging.error(f"Failed to get game state for {room_code}: {e}")
            self.performance_stats['requests_failed'] += 1
            return None
    
    async def update_game_state(self, room_code: str, updates: Dict[str, Any]) -> bool:
        """Update game state with version control"""
        try:
            # Get current state
            current_state = await self.get_game_state(room_code)
            if not current_state:
                logging.warning(f"Cannot update non-existent game room {room_code}")
                return False
            
            # Merge updates
            current_state.update(updates)
            current_state['last_updated'] = datetime.utcnow().isoformat()
            current_state['version'] = current_state.get('version', 1) + 1
            
            # Save updated state
            success = self.redis_wrapper.save_game_state(room_code, current_state)
            
            if success:
                self.performance_stats['game_operations'] += 1
            
            return success
            
        except Exception as e:
            logging.error(f"Failed to update game state for {room_code}: {e}")
            self.performance_stats['requests_failed'] += 1
            return False
    
    async def add_player_to_room(self, room_code: str, player_data: Dict[str, Any]) -> bool:
        """Add player to room with cluster awareness"""
        try:
            # Ensure player data has required fields
            player_data.update({
                'joined_at': datetime.utcnow().isoformat(),
                'cluster_node': self.cluster_manager.get_node_for_room(room_code)
            })
            
            # Get the specific node for this room
            node_id = self.cluster_manager.get_node_for_room(room_code)
            
            def add_player_operation(client, room_code, player_data):
                key = f"room:{room_code}:players"
                client.rpush(key, player_data)
                client.expire(key, 3600)
                return True
            
            success = self.cluster_manager.execute_on_node(
                node_id, add_player_operation, room_code, player_data
            )
            
            if success:
                self.performance_stats['player_operations'] += 1
                logging.debug(f"Added player {player_data.get('player_id')} to room {room_code}")
            
            return success
            
        except Exception as e:
            logging.error(f"Failed to add player to room {room_code}: {e}")
            self.performance_stats['requests_failed'] += 1
            return False
    
    async def save_player_session(self, player_id: str, session_data: Dict[str, Any]) -> bool:
        """Save player session with automatic node selection"""
        try:
            # Add session metadata
            session_data.update({
                'last_updated': datetime.utcnow().isoformat(),
                'cluster_session': True
            })
            
            success = self.redis_wrapper.save_player_session(player_id, session_data)
            
            if success:
                self.performance_stats['player_operations'] += 1
            
            return success
            
        except Exception as e:
            logging.error(f"Failed to save session for player {player_id}: {e}")
            self.performance_stats['requests_failed'] += 1
            return False
    
    async def get_player_session(self, player_id: str) -> Optional[Dict[str, Any]]:
        """Get player session with fallback"""
        try:
            # Use consistent hashing to find the right node
            node_id = self.cluster_manager.hash_ring.get_node(f"session:{player_id}")
            
            def get_session_operation(client, player_id):
                key = f"session:{player_id}"
                return {k.decode(): v.decode() for k, v in client.hgetall(key).items()}
            
            session = self.cluster_manager.execute_on_node(
                node_id, get_session_operation, player_id
            )
            
            if session:
                self.performance_stats['player_operations'] += 1
                return session
            
            return None
            
        except Exception as e:
            logging.error(f"Failed to get session for player {player_id}: {e}")
            self.performance_stats['requests_failed'] += 1
            return None
    
    async def handle_player_disconnect(self, player_id: str, room_code: str):
        """Handle player disconnect with cluster cleanup"""
        try:
            # Update player session
            session_data = await self.get_player_session(player_id)
            if session_data:
                session_data.update({
                    'connection_status': 'disconnected',
                    'disconnected_at': datetime.utcnow().isoformat()
                })
                await self.save_player_session(player_id, session_data)
            
            # Update game state if needed
            game_state = await self.get_game_state(room_code)
            if game_state:
                # Mark player as disconnected in game state
                players = game_state.get('players', [])
                for player in players:
                    if player.get('player_id') == player_id:
                        player['connection_status'] = 'disconnected'
                        break
                
                await self.update_game_state(room_code, {'players': players})
            
            logging.info(f"Handled disconnect for player {player_id} in room {room_code}")
            
        except Exception as e:
            logging.error(f"Failed to handle disconnect for player {player_id}: {e}")
    
    async def migrate_game_room(self, room_code: str, target_node: str) -> bool:
        """Manually migrate a game room to a different node"""
        try:
            current_node = self.cluster_manager.game_session_nodes.get(room_code)
            if not current_node:
                logging.warning(f"Room {room_code} not found for migration")
                return False
            
            if current_node == target_node:
                logging.info(f"Room {room_code} already on target node {target_node}")
                return True
            
            # Get room data
            room_data = self.cluster_manager._get_room_data_from_node(room_code, current_node)
            
            # Migrate to target node
            self.cluster_manager._migrate_room_data(room_code, target_node, room_data)
            
            # Update tracking
            del self.cluster_manager.game_session_nodes[room_code]
            self.cluster_manager.node_game_sessions[current_node].discard(room_code)
            
            self.cluster_manager.game_session_nodes[room_code] = target_node
            self.cluster_manager.node_game_sessions[target_node].add(room_code)
            
            logging.info(f"Successfully migrated room {room_code} from {current_node} to {target_node}")
            return True
            
        except Exception as e:
            logging.error(f"Failed to migrate room {room_code}: {e}")
            return False
    
    # Monitoring and maintenance operations
    
    async def get_cluster_status(self) -> Dict[str, Any]:
        """Get comprehensive cluster status"""
        try:
            status = self.cluster_manager.get_cluster_status()
            dashboard_data = self.monitor.get_dashboard_data()
            
            # Add performance stats
            total_requests = self.performance_stats['requests_total']
            failed_requests = self.performance_stats['requests_failed']
            
            status['performance'] = {
                'total_requests': total_requests,
                'failed_requests': failed_requests,
                'success_rate': ((total_requests - failed_requests) / max(total_requests, 1)) * 100,
                'game_operations': self.performance_stats['game_operations'],
                'player_operations': self.performance_stats['player_operations']
            }
            
            status['monitoring'] = dashboard_data['monitoring_status']
            
            return status
            
        except Exception as e:
            logging.error(f"Failed to get cluster status: {e}")
            return {'error': str(e)}
    
    async def rebalance_cluster(self) -> bool:
        """Trigger cluster rebalancing"""
        try:
            return self.cluster_manager.rebalance_cluster()
        except Exception as e:
            logging.error(f"Failed to rebalance cluster: {e}")
            return False
    
    async def get_node_details(self, node_id: str) -> Dict[str, Any]:
        """Get detailed node information"""
        try:
            return self.monitor.get_node_details(node_id)
        except Exception as e:
            logging.error(f"Failed to get node details for {node_id}: {e}")
            return {'error': str(e)}
    
    async def cleanup_expired_sessions(self):
        """Clean up expired player sessions across the cluster"""
        try:
            current_time = datetime.utcnow().timestamp()
            cleaned_count = 0
            
            # Check each node for expired sessions
            for node_id, client in self.cluster_manager.node_clients.items():
                try:
                    def cleanup_operation(client):
                        count = 0
                        for key in client.scan_iter("session:*"):
                            try:
                                session = client.hgetall(key)
                                if not session:
                                    continue
                                
                                last_heartbeat = int(session.get(b'last_heartbeat', b'0').decode())
                                if current_time - last_heartbeat > 3600:  # 1 hour timeout
                                    client.delete(key)
                                    count += 1
                            except:
                                pass
                        return count
                    
                    node_cleaned = self.cluster_manager.execute_on_node(node_id, cleanup_operation)
                    cleaned_count += node_cleaned
                    
                except Exception as e:
                    logging.warning(f"Failed to cleanup sessions on node {node_id}: {e}")
            
            logging.info(f"Cleaned up {cleaned_count} expired sessions")
            return cleaned_count
            
        except Exception as e:
            logging.error(f"Failed to cleanup expired sessions: {e}")
            return 0

# Usage example
async def main():
    """Example usage of the Redis cluster integration"""
    
    # Initialize game server with Redis cluster
    game_cluster = GameServerRedisCluster("development")
    
    try:
        # Start the cluster
        if not await game_cluster.start():
            print("Failed to start Redis cluster")
            return
        
        print("Redis cluster started successfully!")
        
        # Create a test game room
        room_code = "TEST123"
        initial_state = {
            'phase': 'waiting_for_players',
            'players': [],
            'teams': {},
            'hokm': None,
            'current_turn': None
        }
        
        success = await game_cluster.create_game_room(room_code, initial_state)
        print(f"Created game room: {success}")
        
        # Add test players
        for i in range(4):
            player_data = {
                'player_id': f"player_{i}",
                'username': f"TestPlayer{i}",
                'connection_status': 'active'
            }
            
            await game_cluster.add_player_to_room(room_code, player_data)
            await game_cluster.save_player_session(f"player_{i}", {
                'room_code': room_code,
                'username': f"TestPlayer{i}",
                'connection_status': 'active'
            })
        
        print("Added test players")
        
        # Update game state
        await game_cluster.update_game_state(room_code, {
            'phase': 'team_assignment',
            'teams': {
                'player_0': 0,
                'player_1': 1,
                'player_2': 0,
                'player_3': 1
            }
        })
        
        print("Updated game state")
        
        # Get cluster status
        status = await game_cluster.get_cluster_status()
        print(f"Cluster status: {status['overall_health']}")
        print(f"Healthy nodes: {status['metrics']['healthy_nodes']}/{status['metrics']['total_nodes']}")
        print(f"Total game sessions: {status['metrics'].get('total_game_sessions', 0)}")
        
        # Wait a bit for monitoring data
        await asyncio.sleep(15)
        
        # Get monitoring dashboard data
        dashboard = game_cluster.monitor.get_dashboard_data()
        print(f"Total players in cluster: {dashboard['cluster_summary']['total_players']}")
        print(f"Total operations per second: {dashboard['cluster_summary']['total_ops_per_second']}")
        
    except KeyboardInterrupt:
        print("Shutting down...")
    finally:
        await game_cluster.stop()
        print("Redis cluster stopped")

if __name__ == "__main__":
    asyncio.run(main())
