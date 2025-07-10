# redis_cluster_monitor.py
"""
Redis Cluster Health Monitoring and Dashboard
"""

import asyncio
import json
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from collections import defaultdict, deque
import threading

import redis
from redis.exceptions import ConnectionError, TimeoutError
import psutil

@dataclass
class HealthMetric:
    timestamp: float
    value: float
    status: str  # "healthy", "warning", "critical"

@dataclass
class NodeMetrics:
    node_id: str
    host: str
    port: int
    
    # Performance metrics
    latency_ms: float
    memory_usage_mb: float
    memory_usage_percent: float
    cpu_usage_percent: float
    connections_count: int
    operations_per_second: float
    
    # Health status
    is_available: bool
    last_ping: float
    uptime_seconds: float
    
    # Game-specific metrics
    game_sessions_count: int
    players_count: int
    
    # Historical data (last 24 hours)
    latency_history: List[HealthMetric]
    memory_history: List[HealthMetric]
    cpu_history: List[HealthMetric]

class RedisClusterMonitor:
    """
    Comprehensive Redis cluster monitoring with:
    - Real-time health metrics
    - Performance tracking
    - Game-specific monitoring
    - Alerting system
    - Historical data retention
    """
    
    def __init__(self, cluster_manager, alert_thresholds: Dict[str, float] = None):
        self.cluster_manager = cluster_manager
        self.monitoring_active = False
        self.monitoring_thread = None
        
        # Alert thresholds
        self.alert_thresholds = alert_thresholds or {
            'latency_ms': 100.0,      # Alert if latency > 100ms
            'memory_percent': 85.0,    # Alert if memory > 85%
            'cpu_percent': 80.0,       # Alert if CPU > 80%
            'error_rate': 5.0,         # Alert if error rate > 5%
            'node_down_minutes': 2.0   # Alert if node down > 2 minutes
        }
        
        # Metrics storage (in-memory with limited history)
        self.node_metrics: Dict[str, NodeMetrics] = {}
        self.cluster_metrics_history: deque = deque(maxlen=1440)  # 24 hours of minute data
        self.alerts_history: deque = deque(maxlen=1000)  # Last 1000 alerts
        
        # Monitoring configuration
        self.monitoring_interval = 10  # seconds
        self.metrics_retention_hours = 24
        
        # Alert callbacks
        self.alert_callbacks = []
        
        # Performance counters
        self.performance_counters = defaultdict(lambda: {
            'operations': 0,
            'errors': 0,
            'last_reset': time.time()
        })
        
        logging.info("Redis cluster monitor initialized")
    
    def add_alert_callback(self, callback):
        """Add a callback function for alerts"""
        self.alert_callbacks.append(callback)
    
    def start_monitoring(self):
        """Start background monitoring"""
        if self.monitoring_active:
            logging.warning("Monitoring already active")
            return
        
        self.monitoring_active = True
        self.monitoring_thread = threading.Thread(target=self._monitoring_loop)
        self.monitoring_thread.daemon = True
        self.monitoring_thread.start()
        
        logging.info("Redis cluster monitoring started")
    
    def stop_monitoring(self):
        """Stop background monitoring"""
        self.monitoring_active = False
        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=5)
        
        logging.info("Redis cluster monitoring stopped")
    
    def _monitoring_loop(self):
        """Main monitoring loop"""
        while self.monitoring_active:
            try:
                self._collect_metrics()
                self._check_alerts()
                self._cleanup_old_metrics()
                time.sleep(self.monitoring_interval)
            except Exception as e:
                logging.error(f"Monitoring loop error: {e}")
                time.sleep(5)  # Shorter sleep on error
    
    def _collect_metrics(self):
        """Collect metrics from all cluster nodes"""
        current_time = time.time()
        
        for node_id, node_info in self.cluster_manager.node_health.items():
            try:
                metrics = self._collect_node_metrics(node_id, node_info)
                
                # Update node metrics
                if node_id not in self.node_metrics:
                    self.node_metrics[node_id] = metrics
                else:
                    # Update existing metrics and maintain history
                    existing = self.node_metrics[node_id]
                    
                    # Add to history
                    self._add_to_history(existing.latency_history, metrics.latency_ms, current_time)
                    self._add_to_history(existing.memory_history, metrics.memory_usage_percent, current_time)
                    self._add_to_history(existing.cpu_history, metrics.cpu_usage_percent, current_time)
                    
                    # Update current values
                    self.node_metrics[node_id] = metrics
                    self.node_metrics[node_id].latency_history = existing.latency_history
                    self.node_metrics[node_id].memory_history = existing.memory_history
                    self.node_metrics[node_id].cpu_history = existing.cpu_history
                
            except Exception as e:
                logging.error(f"Failed to collect metrics for node {node_id}: {e}")
                # Mark node as unavailable
                if node_id in self.node_metrics:
                    self.node_metrics[node_id].is_available = False
        
        # Collect cluster-wide metrics
        self._collect_cluster_metrics(current_time)
    
    def _collect_node_metrics(self, node_id: str, node_info) -> NodeMetrics:
        """Collect metrics for a single node"""
        client = self.cluster_manager.node_clients.get(node_id)
        current_time = time.time()
        
        # Initialize default metrics
        metrics = NodeMetrics(
            node_id=node_id,
            host=node_info.host,
            port=node_info.port,
            latency_ms=999.0,
            memory_usage_mb=0.0,
            memory_usage_percent=0.0,
            cpu_usage_percent=0.0,
            connections_count=0,
            operations_per_second=0.0,
            is_available=False,
            last_ping=0.0,
            uptime_seconds=0.0,
            game_sessions_count=0,
            players_count=0,
            latency_history=[],
            memory_history=[],
            cpu_history=[]
        )
        
        if not client:
            return metrics
        
        try:
            # Measure latency
            start_time = time.time()
            client.ping()
            latency = (time.time() - start_time) * 1000  # Convert to ms
            
            # Get Redis info
            info = client.info()
            
            # Update metrics
            metrics.latency_ms = latency
            metrics.memory_usage_mb = info.get('used_memory', 0) / (1024 * 1024)
            metrics.memory_usage_percent = (info.get('used_memory', 0) / 
                                          max(info.get('maxmemory', 1), 1)) * 100
            metrics.connections_count = info.get('connected_clients', 0)
            metrics.is_available = True
            metrics.last_ping = current_time
            metrics.uptime_seconds = info.get('uptime_in_seconds', 0)
            
            # Calculate operations per second
            total_commands = info.get('total_commands_processed', 0)
            if node_id in self.performance_counters:
                prev_commands = self.performance_counters[node_id].get('prev_commands', 0)
                prev_time = self.performance_counters[node_id].get('prev_time', current_time)
                time_diff = current_time - prev_time
                
                if time_diff > 0:
                    metrics.operations_per_second = (total_commands - prev_commands) / time_diff
            
            self.performance_counters[node_id]['prev_commands'] = total_commands
            self.performance_counters[node_id]['prev_time'] = current_time
            
            # Get CPU usage (if available)
            try:
                metrics.cpu_usage_percent = psutil.cpu_percent(interval=None)
            except:
                pass
            
            # Count game sessions and players for this node
            node_sessions = self.cluster_manager.node_game_sessions.get(node_id, set())
            metrics.game_sessions_count = len(node_sessions)
            
            # Count players in these sessions
            total_players = 0
            for room_code in node_sessions:
                try:
                    # Get room players count
                    players_key = f"room:{room_code}:players"
                    player_count = client.llen(players_key)
                    total_players += player_count
                except:
                    pass
            
            metrics.players_count = total_players
            
        except Exception as e:
            logging.warning(f"Failed to collect metrics for node {node_id}: {e}")
            metrics.is_available = False
        
        return metrics
    
    def _collect_cluster_metrics(self, current_time: float):
        """Collect cluster-wide metrics"""
        cluster_metrics = {
            'timestamp': current_time,
            'total_nodes': len(self.cluster_manager.node_health),
            'healthy_nodes': sum(1 for m in self.node_metrics.values() if m.is_available),
            'total_memory_mb': sum(m.memory_usage_mb for m in self.node_metrics.values()),
            'total_connections': sum(m.connections_count for m in self.node_metrics.values()),
            'total_game_sessions': sum(m.game_sessions_count for m in self.node_metrics.values()),
            'total_players': sum(m.players_count for m in self.node_metrics.values()),
            'avg_latency_ms': 0.0,
            'max_latency_ms': 0.0,
            'total_ops_per_second': sum(m.operations_per_second for m in self.node_metrics.values())
        }
        
        # Calculate average and max latency
        available_nodes = [m for m in self.node_metrics.values() if m.is_available]
        if available_nodes:
            latencies = [m.latency_ms for m in available_nodes]
            cluster_metrics['avg_latency_ms'] = sum(latencies) / len(latencies)
            cluster_metrics['max_latency_ms'] = max(latencies)
        
        self.cluster_metrics_history.append(cluster_metrics)
    
    def _add_to_history(self, history: List[HealthMetric], value: float, timestamp: float):
        """Add a metric to history with appropriate status"""
        # Determine status based on thresholds
        if isinstance(value, float):
            if value > 90:  # Generic high threshold
                status = "critical"
            elif value > 70:  # Generic warning threshold
                status = "warning"
            else:
                status = "healthy"
        else:
            status = "healthy"
        
        metric = HealthMetric(timestamp=timestamp, value=value, status=status)
        history.append(metric)
        
        # Limit history size (24 hours of data points)
        max_history = int(24 * 60 * 60 / self.monitoring_interval)
        if len(history) > max_history:
            history.pop(0)
    
    def _check_alerts(self):
        """Check for alert conditions"""
        current_time = time.time()
        
        for node_id, metrics in self.node_metrics.items():
            # Check latency alerts
            if metrics.is_available and metrics.latency_ms > self.alert_thresholds['latency_ms']:
                self._trigger_alert(
                    level="warning",
                    node_id=node_id,
                    metric="latency",
                    value=metrics.latency_ms,
                    threshold=self.alert_thresholds['latency_ms'],
                    message=f"High latency on node {node_id}: {metrics.latency_ms:.2f}ms"
                )
            
            # Check memory alerts
            if metrics.is_available and metrics.memory_usage_percent > self.alert_thresholds['memory_percent']:
                self._trigger_alert(
                    level="warning",
                    node_id=node_id,
                    metric="memory",
                    value=metrics.memory_usage_percent,
                    threshold=self.alert_thresholds['memory_percent'],
                    message=f"High memory usage on node {node_id}: {metrics.memory_usage_percent:.1f}%"
                )
            
            # Check CPU alerts
            if metrics.is_available and metrics.cpu_usage_percent > self.alert_thresholds['cpu_percent']:
                self._trigger_alert(
                    level="warning",
                    node_id=node_id,
                    metric="cpu",
                    value=metrics.cpu_usage_percent,
                    threshold=self.alert_thresholds['cpu_percent'],
                    message=f"High CPU usage on node {node_id}: {metrics.cpu_usage_percent:.1f}%"
                )
            
            # Check node availability
            if not metrics.is_available:
                down_time = current_time - metrics.last_ping
                if down_time > (self.alert_thresholds['node_down_minutes'] * 60):
                    self._trigger_alert(
                        level="critical",
                        node_id=node_id,
                        metric="availability",
                        value=down_time,
                        threshold=self.alert_thresholds['node_down_minutes'] * 60,
                        message=f"Node {node_id} has been down for {down_time/60:.1f} minutes"
                    )
    
    def _trigger_alert(self, level: str, node_id: str, metric: str, 
                      value: float, threshold: float, message: str):
        """Trigger an alert"""
        alert = {
            'timestamp': time.time(),
            'level': level,
            'node_id': node_id,
            'metric': metric,
            'value': value,
            'threshold': threshold,
            'message': message
        }
        
        self.alerts_history.append(alert)
        
        # Log alert
        log_level = logging.CRITICAL if level == "critical" else logging.WARNING
        logging.log(log_level, f"ALERT [{level.upper()}] {message}")
        
        # Call alert callbacks
        for callback in self.alert_callbacks:
            try:
                callback(alert)
            except Exception as e:
                logging.error(f"Alert callback failed: {e}")
    
    def _cleanup_old_metrics(self):
        """Clean up old metrics data"""
        cutoff_time = time.time() - (self.metrics_retention_hours * 3600)
        
        # Clean up node history
        for metrics in self.node_metrics.values():
            for history in [metrics.latency_history, metrics.memory_history, metrics.cpu_history]:
                while history and history[0].timestamp < cutoff_time:
                    history.pop(0)
        
        # Clean up cluster metrics history
        while (self.cluster_metrics_history and 
               self.cluster_metrics_history[0]['timestamp'] < cutoff_time):
            self.cluster_metrics_history.popleft()
    
    def get_dashboard_data(self) -> Dict[str, Any]:
        """Get comprehensive dashboard data"""
        current_time = time.time()
        
        # Node summary
        nodes_data = []
        for node_id, metrics in self.node_metrics.items():
            node_data = {
                'node_id': node_id,
                'host': metrics.host,
                'port': metrics.port,
                'status': 'healthy' if metrics.is_available else 'down',
                'latency_ms': round(metrics.latency_ms, 2),
                'memory_usage_mb': round(metrics.memory_usage_mb, 2),
                'memory_usage_percent': round(metrics.memory_usage_percent, 1),
                'cpu_usage_percent': round(metrics.cpu_usage_percent, 1),
                'connections': metrics.connections_count,
                'operations_per_second': round(metrics.operations_per_second, 2),
                'game_sessions': metrics.game_sessions_count,
                'players': metrics.players_count,
                'uptime_hours': round(metrics.uptime_seconds / 3600, 1)
            }
            nodes_data.append(node_data)
        
        # Cluster summary
        cluster_summary = {
            'total_nodes': len(self.node_metrics),
            'healthy_nodes': sum(1 for m in self.node_metrics.values() if m.is_available),
            'total_memory_mb': round(sum(m.memory_usage_mb for m in self.node_metrics.values()), 2),
            'total_connections': sum(m.connections_count for m in self.node_metrics.values()),
            'total_game_sessions': sum(m.game_sessions_count for m in self.node_metrics.values()),
            'total_players': sum(m.players_count for m in self.node_metrics.values()),
            'total_ops_per_second': round(sum(m.operations_per_second for m in self.node_metrics.values()), 2)
        }
        
        # Recent alerts
        recent_alerts = []
        cutoff_time = current_time - (24 * 3600)  # Last 24 hours
        for alert in reversed(self.alerts_history):
            if alert['timestamp'] >= cutoff_time:
                alert_copy = alert.copy()
                alert_copy['timestamp'] = datetime.fromtimestamp(alert['timestamp']).isoformat()
                recent_alerts.append(alert_copy)
        
        # Performance trends (last hour)
        hour_ago = current_time - 3600
        recent_cluster_metrics = [
            m for m in self.cluster_metrics_history 
            if m['timestamp'] >= hour_ago
        ]
        
        return {
            'timestamp': datetime.fromtimestamp(current_time).isoformat(),
            'cluster_summary': cluster_summary,
            'nodes': nodes_data,
            'recent_alerts': recent_alerts[:50],  # Last 50 alerts
            'performance_trends': recent_cluster_metrics,
            'monitoring_status': {
                'active': self.monitoring_active,
                'interval_seconds': self.monitoring_interval,
                'uptime_hours': round((current_time - self.performance_counters.get('monitor_start', current_time)) / 3600, 1)
            }
        }
    
    def get_node_details(self, node_id: str) -> Dict[str, Any]:
        """Get detailed metrics for a specific node"""
        if node_id not in self.node_metrics:
            return {"error": f"Node {node_id} not found"}
        
        metrics = self.node_metrics[node_id]
        
        return {
            'node_id': node_id,
            'basic_info': {
                'host': metrics.host,
                'port': metrics.port,
                'status': 'healthy' if metrics.is_available else 'down',
                'uptime_hours': round(metrics.uptime_seconds / 3600, 1)
            },
            'performance': {
                'latency_ms': round(metrics.latency_ms, 2),
                'memory_usage_mb': round(metrics.memory_usage_mb, 2),
                'memory_usage_percent': round(metrics.memory_usage_percent, 1),
                'cpu_usage_percent': round(metrics.cpu_usage_percent, 1),
                'operations_per_second': round(metrics.operations_per_second, 2)
            },
            'connections': {
                'count': metrics.connections_count
            },
            'game_data': {
                'sessions_count': metrics.game_sessions_count,
                'players_count': metrics.players_count
            },
            'history': {
                'latency': [asdict(h) for h in metrics.latency_history[-60:]],  # Last hour
                'memory': [asdict(h) for h in metrics.memory_history[-60:]],
                'cpu': [asdict(h) for h in metrics.cpu_history[-60:]]
            }
        }
    
    def export_metrics(self, format: str = "json") -> str:
        """Export metrics in various formats"""
        data = self.get_dashboard_data()
        
        if format.lower() == "json":
            return json.dumps(data, indent=2)
        elif format.lower() == "csv":
            # Simple CSV export for cluster summary
            import csv
            import io
            
            output = io.StringIO()
            writer = csv.writer(output)
            
            # Write cluster summary
            writer.writerow(["Metric", "Value"])
            for key, value in data['cluster_summary'].items():
                writer.writerow([key, value])
            
            writer.writerow([])  # Empty row
            
            # Write node data
            if data['nodes']:
                writer.writerow(data['nodes'][0].keys())
                for node in data['nodes']:
                    writer.writerow(node.values())
            
            return output.getvalue()
        else:
            return f"Unsupported format: {format}"
