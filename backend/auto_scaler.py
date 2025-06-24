#!/usr/bin/env python3
"""
Auto-Scaling System for Hokm Game Server
Provides intelligent scaling based on game metrics, player load, and resource utilization
"""

import asyncio
import time
import json
import psutil
import threading
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum

class ScalingAction(Enum):
    SCALE_UP = "scale_up"
    SCALE_DOWN = "scale_down"
    NO_ACTION = "no_action"

@dataclass
class ScalingMetrics:
    """Metrics used for scaling decisions"""
    timestamp: float
    total_instances: int
    healthy_instances: int
    total_players: int
    total_games: int
    avg_cpu_usage: float
    avg_memory_usage: float
    peak_connections_per_instance: int
    avg_connections_per_instance: float
    game_creation_rate: float  # games per minute
    player_join_rate: float    # players per minute
    queue_length: int          # waiting players
    response_time_p95: float   # 95th percentile response time
    error_rate: float          # percentage of failed operations

@dataclass
class ScalingRule:
    """Scaling rule configuration"""
    name: str
    metric: str
    operator: str  # '>', '<', '>=', '<=', '=='
    threshold: float
    duration: int  # seconds the condition must persist
    action: ScalingAction
    cooldown: int  # seconds before rule can trigger again
    priority: int  # higher number = higher priority
    enabled: bool = True

@dataclass
class ScalingDecision:
    """Scaling decision result"""
    action: ScalingAction
    reason: str
    target_instances: int
    triggered_rules: List[str]
    confidence: float
    timestamp: float

class AutoScaler:
    """
    Intelligent auto-scaling system for game servers
    
    Features:
    - Game-aware scaling based on room occupancy
    - Predictive scaling using historical patterns
    - Cost optimization with intelligent instance management
    - Multi-metric decision making with rule engine
    - Graceful scaling with minimal game disruption
    """
    
    def __init__(self, redis_manager, min_instances=2, max_instances=20):
        self.redis = redis_manager
        self.min_instances = min_instances
        self.max_instances = max_instances
        
        # Scaling configuration
        self.scaling_interval = 60  # Check every minute
        self.metrics_history_size = 100
        self.prediction_window = 300  # 5 minutes
        
        # State tracking
        self.metrics_history = []
        self.scaling_history = []
        self.last_scaling_action = None
        self.last_scaling_time = 0
        
        # Rules engine
        self.scaling_rules = self._create_default_scaling_rules()
        self.rule_triggers = {}  # Track when rules were triggered
        
        # Background tasks
        self._scaling_task = None
        self._metrics_task = None
        self._cleanup_task = None
        self._stop_event = asyncio.Event()
        
        print(f"[AUTOSCALER] Initialized with {min_instances}-{max_instances} instances")
    
    def _create_default_scaling_rules(self) -> List[ScalingRule]:
        """Create default scaling rules"""
        return [
            # High priority emergency scaling
            ScalingRule(
                name="emergency_cpu_high",
                metric="avg_cpu_usage",
                operator=">=",
                threshold=90.0,
                duration=60,
                action=ScalingAction.SCALE_UP,
                cooldown=120,
                priority=100
            ),
            ScalingRule(
                name="emergency_memory_high",
                metric="avg_memory_usage",
                operator=">=",
                threshold=85.0,
                duration=60,
                action=ScalingAction.SCALE_UP,
                cooldown=120,
                priority=100
            ),
            ScalingRule(
                name="high_error_rate",
                metric="error_rate",
                operator=">=",
                threshold=5.0,
                duration=120,
                action=ScalingAction.SCALE_UP,
                cooldown=300,
                priority=90
            ),
            
            # Game-specific scaling rules
            ScalingRule(
                name="high_player_density",
                metric="avg_connections_per_instance",
                operator=">=",
                threshold=100.0,
                duration=180,
                action=ScalingAction.SCALE_UP,
                cooldown=300,
                priority=80
            ),
            ScalingRule(
                name="high_game_creation_rate",
                metric="game_creation_rate",
                operator=">=",
                threshold=10.0,  # 10 games per minute
                duration=120,
                action=ScalingAction.SCALE_UP,
                cooldown=240,
                priority=75
            ),
            ScalingRule(
                name="players_waiting_queue",
                metric="queue_length",
                operator=">",
                threshold=20.0,
                duration=60,
                action=ScalingAction.SCALE_UP,
                cooldown=180,
                priority=85
            ),
            
            # Performance-based scaling
            ScalingRule(
                name="high_response_time",
                metric="response_time_p95",
                operator=">=",
                threshold=2000.0,  # 2 seconds
                duration=180,
                action=ScalingAction.SCALE_UP,
                cooldown=300,
                priority=70
            ),
            ScalingRule(
                name="sustained_high_cpu",
                metric="avg_cpu_usage",
                operator=">=",
                threshold=70.0,
                duration=300,  # 5 minutes
                action=ScalingAction.SCALE_UP,
                cooldown=600,
                priority=60
            ),
            
            # Scale down rules
            ScalingRule(
                name="low_utilization",
                metric="avg_cpu_usage",
                operator="<=",
                threshold=20.0,
                duration=600,  # 10 minutes
                action=ScalingAction.SCALE_DOWN,
                cooldown=900,
                priority=50
            ),
            ScalingRule(
                name="low_player_density",
                metric="avg_connections_per_instance",
                operator="<=",
                threshold=20.0,
                duration=900,  # 15 minutes
                action=ScalingAction.SCALE_DOWN,
                cooldown=1200,
                priority=40
            ),
            ScalingRule(
                name="excess_capacity",
                metric="total_instances",
                operator=">",
                threshold=0,  # Dynamic threshold based on current load
                duration=600,
                action=ScalingAction.SCALE_DOWN,
                cooldown=900,
                priority=30
            )
        ]
    
    async def start(self):
        """Start the auto-scaling system"""
        print("[AUTOSCALER] Starting auto-scaling system")
        
        self._scaling_task = asyncio.create_task(self._scaling_loop())
        self._metrics_task = asyncio.create_task(self._metrics_collection_loop())
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        
        print("[AUTOSCALER] Auto-scaling system started")
    
    async def stop(self):
        """Stop the auto-scaling system"""
        print("[AUTOSCALER] Stopping auto-scaling system")
        
        self._stop_event.set()
        
        if self._scaling_task:
            self._scaling_task.cancel()
        if self._metrics_task:
            self._metrics_task.cancel()
        if self._cleanup_task:
            self._cleanup_task.cancel()
        
        print("[AUTOSCALER] Auto-scaling system stopped")
    
    async def _scaling_loop(self):
        """Main scaling decision loop"""
        while not self._stop_event.is_set():
            try:
                await asyncio.sleep(self.scaling_interval)
                
                # Collect current metrics
                metrics = await self._collect_current_metrics()
                if metrics:
                    # Store metrics history
                    self.metrics_history.append(metrics)
                    if len(self.metrics_history) > self.metrics_history_size:
                        self.metrics_history.pop(0)
                    
                    # Make scaling decision
                    decision = await self._make_scaling_decision(metrics)
                    
                    if decision.action != ScalingAction.NO_ACTION:
                        await self._execute_scaling_decision(decision)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[AUTOSCALER] Scaling loop error: {e}")
                await asyncio.sleep(30)  # Wait before retrying
    
    async def _metrics_collection_loop(self):
        """Collect and aggregate metrics from all instances"""
        while not self._stop_event.is_set():
            try:
                await asyncio.sleep(30)  # Collect metrics every 30 seconds
                
                # Update predictive models
                await self._update_prediction_models()
                
                # Clean old metrics
                current_time = time.time()
                cutoff_time = current_time - (24 * 3600)  # Keep 24 hours
                
                self.metrics_history = [
                    m for m in self.metrics_history 
                    if m.timestamp > cutoff_time
                ]
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[AUTOSCALER] Metrics collection error: {e}")
    
    async def _cleanup_loop(self):
        """Cleanup old data and optimize performance"""
        while not self._stop_event.is_set():
            try:
                await asyncio.sleep(3600)  # Run every hour
                
                # Clean old scaling history
                current_time = time.time()
                cutoff_time = current_time - (7 * 24 * 3600)  # Keep 7 days
                
                self.scaling_history = [
                    s for s in self.scaling_history 
                    if s.timestamp > cutoff_time
                ]
                
                # Reset rule triggers that are too old
                for rule_name, trigger_time in list(self.rule_triggers.items()):
                    if current_time - trigger_time > 3600:  # 1 hour
                        del self.rule_triggers[rule_name]
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[AUTOSCALER] Cleanup error: {e}")
    
    async def _collect_current_metrics(self) -> Optional[ScalingMetrics]:
        """Collect current system metrics"""
        try:
            # Get all server instances
            instances = await self._get_all_instances()
            if not instances:
                return None
            
            # Aggregate metrics
            total_instances = len(instances)
            healthy_instances = sum(1 for i in instances.values() if i.get('status') == 'ready')
            total_players = sum(i.get('connected_players', 0) for i in instances.values())
            total_games = sum(i.get('active_games', 0) for i in instances.values())
            
            cpu_values = [i.get('cpu_usage', 0) for i in instances.values()]
            memory_values = [i.get('memory_usage', 0) for i in instances.values()]
            connection_values = [i.get('connected_players', 0) for i in instances.values()]
            
            avg_cpu_usage = sum(cpu_values) / len(cpu_values) if cpu_values else 0
            avg_memory_usage = sum(memory_values) / len(memory_values) if memory_values else 0
            avg_connections_per_instance = sum(connection_values) / len(connection_values) if connection_values else 0
            peak_connections_per_instance = max(connection_values) if connection_values else 0
            
            # Calculate rates from history
            game_creation_rate = await self._calculate_game_creation_rate()
            player_join_rate = await self._calculate_player_join_rate()
            
            # Get additional metrics
            queue_length = await self._get_queue_length()
            response_time_p95 = await self._get_response_time_p95()
            error_rate = await self._get_error_rate()
            
            return ScalingMetrics(
                timestamp=time.time(),
                total_instances=total_instances,
                healthy_instances=healthy_instances,
                total_players=total_players,
                total_games=total_games,
                avg_cpu_usage=avg_cpu_usage,
                avg_memory_usage=avg_memory_usage,
                peak_connections_per_instance=peak_connections_per_instance,
                avg_connections_per_instance=avg_connections_per_instance,
                game_creation_rate=game_creation_rate,
                player_join_rate=player_join_rate,
                queue_length=queue_length,
                response_time_p95=response_time_p95,
                error_rate=error_rate
            )
            
        except Exception as e:
            print(f"[AUTOSCALER] Error collecting metrics: {e}")
            return None
    
    async def _make_scaling_decision(self, metrics: ScalingMetrics) -> ScalingDecision:
        """Make scaling decision based on metrics and rules"""
        triggered_rules = []
        scale_up_score = 0
        scale_down_score = 0
        
        current_time = time.time()
        
        for rule in self.scaling_rules:
            if not rule.enabled:
                continue
            
            # Check cooldown
            last_trigger = self.rule_triggers.get(rule.name, 0)
            if current_time - last_trigger < rule.cooldown:
                continue
            
            # Evaluate rule condition
            metric_value = getattr(metrics, rule.metric, 0)
            
            # Special handling for dynamic thresholds
            if rule.name == "excess_capacity":
                # Calculate optimal instance count based on current load
                optimal_instances = max(
                    self.min_instances,
                    int((metrics.total_players / 80) + 1)  # ~80 players per instance
                )
                rule.threshold = optimal_instances
                metric_value = metrics.total_instances
            
            # Check if rule condition is met
            condition_met = self._evaluate_condition(metric_value, rule.operator, rule.threshold)
            
            if condition_met:
                # Check if condition has persisted long enough
                rule_key = f"rule_condition_{rule.name}"
                condition_start = await self._get_condition_start_time(rule_key)
                
                if condition_start is None:
                    # First time condition is met
                    await self._set_condition_start_time(rule_key, current_time)
                    continue
                elif current_time - condition_start >= rule.duration:
                    # Condition has persisted long enough
                    triggered_rules.append(rule.name)
                    self.rule_triggers[rule.name] = current_time
                    
                    if rule.action == ScalingAction.SCALE_UP:
                        scale_up_score += rule.priority
                    elif rule.action == ScalingAction.SCALE_DOWN:
                        scale_down_score += rule.priority
                    
                    # Clear condition tracking
                    await self._clear_condition_start_time(rule_key)
            else:
                # Condition not met, clear tracking
                rule_key = f"rule_condition_{rule.name}"
                await self._clear_condition_start_time(rule_key)
        
        # Make decision based on scores
        if scale_up_score > scale_down_score and scale_up_score > 0:
            target_instances = min(
                metrics.total_instances + self._calculate_scale_up_amount(metrics),
                self.max_instances
            )
            return ScalingDecision(
                action=ScalingAction.SCALE_UP,
                reason=f"Scale up triggered by rules: {', '.join(triggered_rules)}",
                target_instances=target_instances,
                triggered_rules=triggered_rules,
                confidence=min(scale_up_score / 100.0, 1.0),
                timestamp=current_time
            )
        elif scale_down_score > scale_up_score and scale_down_score > 0:
            target_instances = max(
                metrics.total_instances - self._calculate_scale_down_amount(metrics),
                self.min_instances
            )
            return ScalingDecision(
                action=ScalingAction.SCALE_DOWN,
                reason=f"Scale down triggered by rules: {', '.join(triggered_rules)}",
                target_instances=target_instances,
                triggered_rules=triggered_rules,
                confidence=min(scale_down_score / 100.0, 1.0),
                timestamp=current_time
            )
        else:
            return ScalingDecision(
                action=ScalingAction.NO_ACTION,
                reason="No scaling rules triggered",
                target_instances=metrics.total_instances,
                triggered_rules=[],
                confidence=1.0,
                timestamp=current_time
            )
    
    def _calculate_scale_up_amount(self, metrics: ScalingMetrics) -> int:
        """Calculate how many instances to add"""
        # Base scale up amount
        base_amount = 1
        
        # Scale more aggressively for high load
        if metrics.avg_cpu_usage > 80:
            base_amount = 2
        if metrics.queue_length > 50:
            base_amount = max(base_amount, int(metrics.queue_length / 25))
        if metrics.error_rate > 10:
            base_amount = max(base_amount, 3)
        
        # Don't scale more than 50% of current instances at once
        max_amount = max(1, int(metrics.total_instances * 0.5))
        
        return min(base_amount, max_amount)
    
    def _calculate_scale_down_amount(self, metrics: ScalingMetrics) -> int:
        """Calculate how many instances to remove"""
        # Conservative scale down
        base_amount = 1
        
        # Only scale down more if utilization is very low
        if metrics.avg_cpu_usage < 10 and metrics.avg_connections_per_instance < 10:
            base_amount = 2
        
        # Never scale down more than 25% at once
        max_amount = max(1, int(metrics.total_instances * 0.25))
        
        return min(base_amount, max_amount)
    
    def _evaluate_condition(self, value: float, operator: str, threshold: float) -> bool:
        """Evaluate a rule condition"""
        if operator == '>':
            return value > threshold
        elif operator == '>=':
            return value >= threshold
        elif operator == '<':
            return value < threshold
        elif operator == '<=':
            return value <= threshold
        elif operator == '==':
            return abs(value - threshold) < 0.001  # Float equality
        else:
            return False
    
    async def _execute_scaling_decision(self, decision: ScalingDecision):
        """Execute a scaling decision"""
        print(f"[AUTOSCALER] Executing scaling decision: {decision.action.value}")
        print(f"[AUTOSCALER] Reason: {decision.reason}")
        print(f"[AUTOSCALER] Target instances: {decision.target_instances}")
        print(f"[AUTOSCALER] Confidence: {decision.confidence:.2f}")
        
        try:
            if decision.action == ScalingAction.SCALE_UP:
                await self._scale_up(decision.target_instances)
            elif decision.action == ScalingAction.SCALE_DOWN:
                await self._scale_down(decision.target_instances)
            
            # Record scaling action
            self.scaling_history.append(decision)
            self.last_scaling_action = decision.action
            self.last_scaling_time = decision.timestamp
            
            # Broadcast scaling event to all instances
            await self._broadcast_scaling_event(decision)
            
        except Exception as e:
            print(f"[AUTOSCALER] Failed to execute scaling decision: {e}")
    
    async def _scale_up(self, target_instances: int):
        """Scale up to target number of instances"""
        current_instances = await self._get_current_instance_count()
        instances_to_add = target_instances - current_instances
        
        print(f"[AUTOSCALER] Scaling up: adding {instances_to_add} instances")
        
        # Implementation depends on deployment platform
        # This is a placeholder for the actual scaling implementation
        
        # For Docker Compose:
        # await self._scale_docker_compose(target_instances)
        
        # For Kubernetes:
        # await self._scale_kubernetes_deployment(target_instances)
        
        # For AWS ECS:
        # await self._scale_ecs_service(target_instances)
        
        # For now, log the action
        await self._log_scaling_action("scale_up", current_instances, target_instances)
    
    async def _scale_down(self, target_instances: int):
        """Scale down to target number of instances"""
        current_instances = await self._get_current_instance_count()
        instances_to_remove = current_instances - target_instances
        
        print(f"[AUTOSCALER] Scaling down: removing {instances_to_remove} instances")
        
        # Select instances for graceful shutdown
        instances_to_shutdown = await self._select_instances_for_shutdown(instances_to_remove)
        
        # Trigger graceful shutdown on selected instances
        for instance_id in instances_to_shutdown:
            await self._trigger_graceful_shutdown(instance_id)
        
        await self._log_scaling_action("scale_down", current_instances, target_instances)
    
    # Helper methods for metrics and instance management
    # [Additional implementation methods would continue here...]

if __name__ == "__main__":
    # Example usage
    from redis_manager_resilient import ResilientRedisManager
    
    async def main():
        redis_manager = ResilientRedisManager()
        autoscaler = AutoScaler(redis_manager, min_instances=2, max_instances=10)
        
        try:
            await autoscaler.start()
            
            # Keep running
            while True:
                await asyncio.sleep(60)
                
        except KeyboardInterrupt:
            print("Stopping auto-scaler...")
            await autoscaler.stop()
    
    asyncio.run(main())
