"""
Circuit Breaker Monitoring and Health Check System
Provides comprehensive monitoring, alerting, and health checking for Redis circuit breakers
"""

import time
import json
import threading
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum

class HealthStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    CRITICAL = "critical"

@dataclass
class HealthCheckResult:
    service: str
    status: HealthStatus
    message: str
    timestamp: datetime
    response_time: float
    details: Dict[str, Any] = None

@dataclass
class AlertRule:
    name: str
    condition: str  # e.g., "failure_rate > 0.5"
    threshold: float
    duration: int  # seconds
    severity: str  # info, warning, error, critical
    enabled: bool = True

class CircuitBreakerMonitor:
    """
    Comprehensive monitoring system for circuit breakers
    
    Features:
    - Real-time health monitoring
    - Alerting based on configurable rules
    - Performance trend analysis
    - Historical metrics storage
    - Dashboard data export
    """
    
    def __init__(self, redis_manager):
        self.redis_manager = redis_manager
        self.health_checks = {}
        self.alerts = []
        self.alert_rules = self._create_default_alert_rules()
        self.metrics_history = []
        self.max_history_size = 1000
        self._lock = threading.Lock()
        self._monitoring_thread = None
        self._stop_monitoring = False
        
        # Start monitoring
        self.start_monitoring()
    
    def _create_default_alert_rules(self) -> List[AlertRule]:
        """Create default alerting rules"""
        return [
            AlertRule(
                name="high_failure_rate",
                condition="failure_rate > 0.8",
                threshold=0.8,
                duration=60,
                severity="critical"
            ),
            AlertRule(
                name="circuit_open",
                condition="circuit_state == 'open'",
                threshold=1,
                duration=30,
                severity="error"
            ),
            AlertRule(
                name="high_response_time",
                condition="avg_response_time > 5.0",
                threshold=5.0,
                duration=120,
                severity="warning"
            ),
            AlertRule(
                name="many_fallback_executions",
                condition="fallback_rate > 0.5",
                threshold=0.5,
                duration=180,
                severity="warning"
            )
        ]
    
    def start_monitoring(self, interval: int = 30):
        """Start the monitoring thread"""
        if self._monitoring_thread and self._monitoring_thread.is_alive():
            return
        
        self._stop_monitoring = False
        self._monitoring_thread = threading.Thread(
            target=self._monitoring_loop,
            args=(interval,),
            daemon=True
        )
        self._monitoring_thread.start()
    
    def stop_monitoring(self):
        """Stop the monitoring thread"""
        self._stop_monitoring = True
        if self._monitoring_thread:
            self._monitoring_thread.join(timeout=5)
    
    def _monitoring_loop(self, interval: int):
        """Main monitoring loop"""
        while not self._stop_monitoring:
            try:
                # Perform health checks
                self._perform_health_checks()
                
                # Check alerting rules
                self._check_alert_rules()
                
                # Store metrics history
                self._store_metrics_snapshot()
                
                # Sleep until next interval
                time.sleep(interval)
                
            except Exception as e:
                print(f"[ERROR] Monitoring loop error: {e}")
                time.sleep(interval)
    
    def _perform_health_checks(self):
        """Perform comprehensive health checks"""
        with self._lock:
            # Check Redis connectivity
            redis_health = self._check_redis_health()
            self.health_checks['redis'] = redis_health
            
            # Check circuit breaker states
            circuit_health = self._check_circuit_breaker_health()
            self.health_checks['circuit_breakers'] = circuit_health
            
            # Check overall system health
            system_health = self._check_system_health()
            self.health_checks['system'] = system_health
    
    def _check_redis_health(self) -> HealthCheckResult:
        """Check Redis connection health"""
        start_time = time.time()
        
        try:
            # Test basic connectivity
            is_healthy = self.redis_manager.is_healthy()
            response_time = time.time() - start_time
            
            if is_healthy:
                return HealthCheckResult(
                    service="redis",
                    status=HealthStatus.HEALTHY,
                    message="Redis connection is healthy",
                    timestamp=datetime.now(),
                    response_time=response_time
                )
            else:
                return HealthCheckResult(
                    service="redis",
                    status=HealthStatus.UNHEALTHY,
                    message="Redis connection failed",
                    timestamp=datetime.now(),
                    response_time=response_time
                )
                
        except Exception as e:
            response_time = time.time() - start_time
            return HealthCheckResult(
                service="redis",
                status=HealthStatus.CRITICAL,
                message=f"Redis health check failed: {str(e)}",
                timestamp=datetime.now(),
                response_time=response_time
            )
    
    def _check_circuit_breaker_health(self) -> Dict[str, HealthCheckResult]:
        """Check health of all circuit breakers"""
        circuit_results = {}
        
        try:
            cb_status = self.redis_manager.get_circuit_breaker_status()
            
            for name, status in cb_status.items():
                state = status['state']
                metrics = status['metrics']
                
                # Determine health based on state and metrics
                if state == 'closed':
                    failure_rate = metrics.get('failure_rate', 0)
                    if failure_rate < 0.1:
                        health_status = HealthStatus.HEALTHY
                        message = "Circuit breaker operating normally"
                    elif failure_rate < 0.5:
                        health_status = HealthStatus.DEGRADED
                        message = f"Elevated failure rate: {failure_rate:.2%}"
                    else:
                        health_status = HealthStatus.UNHEALTHY
                        message = f"High failure rate: {failure_rate:.2%}"
                elif state == 'half_open':
                    health_status = HealthStatus.DEGRADED
                    message = "Circuit breaker testing recovery"
                else:  # open
                    health_status = HealthStatus.CRITICAL
                    message = "Circuit breaker is open - service unavailable"
                
                circuit_results[name] = HealthCheckResult(
                    service=f"circuit_breaker_{name}",
                    status=health_status,
                    message=message,
                    timestamp=datetime.now(),
                    response_time=metrics.get('avg_response_time', 0),
                    details=metrics
                )
                
        except Exception as e:
            circuit_results['error'] = HealthCheckResult(
                service="circuit_breakers",
                status=HealthStatus.CRITICAL,
                message=f"Failed to check circuit breaker health: {str(e)}",
                timestamp=datetime.now(),
                response_time=0
            )
        
        return circuit_results
    
    def _check_system_health(self) -> HealthCheckResult:
        """Check overall system health"""
        try:
            # Analyze overall health based on individual components
            redis_health = self.health_checks.get('redis')
            circuit_health = self.health_checks.get('circuit_breakers', {})
            
            # Determine overall status
            if not redis_health:
                status = HealthStatus.CRITICAL
                message = "System health check incomplete"
            elif redis_health.status == HealthStatus.CRITICAL:
                status = HealthStatus.CRITICAL
                message = "Redis is critical - system severely degraded"
            elif any(cb.status == HealthStatus.CRITICAL for cb in circuit_health.values()):
                status = HealthStatus.UNHEALTHY
                message = "One or more circuit breakers are critical"
            elif redis_health.status == HealthStatus.UNHEALTHY:
                status = HealthStatus.UNHEALTHY
                message = "Redis is unhealthy - system degraded"
            elif any(cb.status == HealthStatus.UNHEALTHY for cb in circuit_health.values()):
                status = HealthStatus.DEGRADED
                message = "Some circuit breakers are unhealthy"
            elif redis_health.status == HealthStatus.DEGRADED:
                status = HealthStatus.DEGRADED
                message = "Redis performance degraded"
            else:
                status = HealthStatus.HEALTHY
                message = "All systems operating normally"
            
            return HealthCheckResult(
                service="system",
                status=status,
                message=message,
                timestamp=datetime.now(),
                response_time=0,
                details={
                    'redis_status': redis_health.status.value if redis_health else 'unknown',
                    'circuit_breaker_count': len(circuit_health),
                    'critical_circuits': len([cb for cb in circuit_health.values() 
                                            if cb.status == HealthStatus.CRITICAL])
                }
            )
            
        except Exception as e:
            return HealthCheckResult(
                service="system",
                status=HealthStatus.CRITICAL,
                message=f"System health check failed: {str(e)}",
                timestamp=datetime.now(),
                response_time=0
            )
    
    def _check_alert_rules(self):
        """Check all alert rules and generate alerts"""
        try:
            current_metrics = self.get_comprehensive_metrics()
            
            for rule in self.alert_rules:
                if not rule.enabled:
                    continue
                
                # Evaluate rule condition
                if self._evaluate_alert_rule(rule, current_metrics):
                    self._generate_alert(rule, current_metrics)
                    
        except Exception as e:
            print(f"[ERROR] Alert rule checking failed: {e}")
    
    def _evaluate_alert_rule(self, rule: AlertRule, metrics: Dict[str, Any]) -> bool:
        """Evaluate if an alert rule should fire"""
        try:
            # Simple rule evaluation (can be extended with more complex logic)
            if "failure_rate >" in rule.condition:
                overall_failure_rate = self._calculate_overall_failure_rate(metrics)
                return overall_failure_rate > rule.threshold
            
            elif "circuit_state ==" in rule.condition:
                # Check if any circuit is in the specified state
                circuit_status = metrics.get('circuit_breakers', {})
                target_state = rule.condition.split("==")[1].strip().strip("'\"")
                return any(cb['state'] == target_state for cb in circuit_status.values())
            
            elif "avg_response_time >" in rule.condition:
                avg_response_time = self._calculate_avg_response_time(metrics)
                return avg_response_time > rule.threshold
            
            elif "fallback_rate >" in rule.condition:
                fallback_rate = self._calculate_fallback_rate(metrics)
                return fallback_rate > rule.threshold
            
            return False
            
        except Exception as e:
            print(f"[ERROR] Rule evaluation failed for {rule.name}: {e}")
            return False
    
    def _calculate_overall_failure_rate(self, metrics: Dict[str, Any]) -> float:
        """Calculate overall failure rate across all circuits"""
        circuit_metrics = metrics.get('circuit_breakers', {})
        if not circuit_metrics:
            return 0.0
        
        total_requests = sum(cb.get('total_requests', 0) for cb in circuit_metrics.values())
        total_failures = sum(cb.get('total_failures', 0) for cb in circuit_metrics.values())
        
        return total_failures / total_requests if total_requests > 0 else 0.0
    
    def _calculate_avg_response_time(self, metrics: Dict[str, Any]) -> float:
        """Calculate average response time across all circuits"""
        circuit_metrics = metrics.get('circuit_breakers', {})
        if not circuit_metrics:
            return 0.0
        
        response_times = [cb.get('avg_response_time', 0) for cb in circuit_metrics.values()]
        return sum(response_times) / len(response_times) if response_times else 0.0
    
    def _calculate_fallback_rate(self, metrics: Dict[str, Any]) -> float:
        """Calculate fallback execution rate"""
        circuit_metrics = metrics.get('circuit_breakers', {})
        if not circuit_metrics:
            return 0.0
        
        total_requests = sum(cb.get('total_requests', 0) for cb in circuit_metrics.values())
        total_fallbacks = sum(cb.get('fallback_executions', 0) for cb in circuit_metrics.values())
        
        return total_fallbacks / total_requests if total_requests > 0 else 0.0
    
    def _generate_alert(self, rule: AlertRule, metrics: Dict[str, Any]):
        """Generate an alert"""
        alert = {
            'rule': rule.name,
            'severity': rule.severity,
            'message': f"Alert rule '{rule.name}' triggered",
            'condition': rule.condition,
            'timestamp': datetime.now().isoformat(),
            'metrics_snapshot': metrics
        }
        
        with self._lock:
            self.alerts.append(alert)
            
            # Keep only recent alerts (last 100)
            if len(self.alerts) > 100:
                self.alerts = self.alerts[-100:]
        
        print(f"[ALERT] {rule.severity.upper()}: {alert['message']}")
    
    def _store_metrics_snapshot(self):
        """Store current metrics for historical analysis"""
        try:
            snapshot = {
                'timestamp': datetime.now().isoformat(),
                'metrics': self.get_comprehensive_metrics(),
                'health_checks': {
                    name: asdict(result) if hasattr(result, '__dict__') else result
                    for name, result in self.health_checks.items()
                }
            }
            
            with self._lock:
                self.metrics_history.append(snapshot)
                
                # Keep only recent history
                if len(self.metrics_history) > self.max_history_size:
                    self.metrics_history = self.metrics_history[-self.max_history_size:]
                    
        except Exception as e:
            print(f"[ERROR] Failed to store metrics snapshot: {e}")
    
    def get_comprehensive_metrics(self) -> Dict[str, Any]:
        """Get comprehensive metrics from all sources"""
        try:
            base_metrics = self.redis_manager.get_performance_metrics()
            
            # Add monitoring-specific metrics
            monitoring_metrics = {
                'monitoring_active': not self._stop_monitoring,
                'alerts_count': len(self.alerts),
                'recent_alerts': len([a for a in self.alerts 
                                    if datetime.fromisoformat(a['timestamp']) > 
                                    datetime.now() - timedelta(hours=1)]),
                'health_status': {
                    name: result.status.value if hasattr(result, 'status') else 'unknown'
                    for name, result in self.health_checks.items()
                }
            }
            
            base_metrics.update(monitoring_metrics)
            return base_metrics
            
        except Exception as e:
            print(f"[ERROR] Failed to get comprehensive metrics: {e}")
            return {}
    
    def get_health_report(self) -> Dict[str, Any]:
        """Get detailed health report"""
        with self._lock:
            return {
                'timestamp': datetime.now().isoformat(),
                'overall_status': self.health_checks.get('system', {}).get('status', 'unknown'),
                'health_checks': {
                    name: asdict(result) if hasattr(result, '__dict__') else result
                    for name, result in self.health_checks.items()
                },
                'recent_alerts': [a for a in self.alerts 
                                if datetime.fromisoformat(a['timestamp']) > 
                                datetime.now() - timedelta(hours=1)],
                'metrics': self.get_comprehensive_metrics()
            }
    
    def get_dashboard_data(self) -> Dict[str, Any]:
        """Get data formatted for monitoring dashboard"""
        health_report = self.get_health_report()
        
        # Process data for dashboard consumption
        dashboard_data = {
            'status': {
                'overall': health_report['overall_status'],
                'redis': health_report['health_checks'].get('redis', {}).get('status', 'unknown'),
                'timestamp': health_report['timestamp']
            },
            'circuit_breakers': {},
            'metrics': {
                'failure_rate': self._calculate_overall_failure_rate(health_report['metrics']),
                'avg_response_time': self._calculate_avg_response_time(health_report['metrics']),
                'fallback_rate': self._calculate_fallback_rate(health_report['metrics'])
            },
            'alerts': {
                'total': len(self.alerts),
                'recent': len(health_report['recent_alerts']),
                'critical': len([a for a in health_report['recent_alerts'] 
                               if a['severity'] == 'critical'])
            },
            'trends': self._calculate_trends()
        }
        
        # Add circuit breaker details
        cb_health = health_report['health_checks'].get('circuit_breakers', {})
        for name, health in cb_health.items():
            if hasattr(health, '__dict__'):
                dashboard_data['circuit_breakers'][name] = {
                    'status': health.status.value if hasattr(health, 'status') else 'unknown',
                    'response_time': health.response_time if hasattr(health, 'response_time') else 0,
                    'details': health.details if hasattr(health, 'details') else {}
                }
        
        return dashboard_data
    
    def _calculate_trends(self) -> Dict[str, Any]:
        """Calculate trends from historical data"""
        if len(self.metrics_history) < 2:
            return {'error': 'Insufficient data for trends'}
        
        try:
            recent_metrics = self.metrics_history[-10:]  # Last 10 snapshots
            
            # Calculate failure rate trend
            failure_rates = []
            response_times = []
            
            for snapshot in recent_metrics:
                metrics = snapshot.get('metrics', {})
                failure_rates.append(self._calculate_overall_failure_rate(metrics))
                response_times.append(self._calculate_avg_response_time(metrics))
            
            return {
                'failure_rate_trend': self._calculate_trend_direction(failure_rates),
                'response_time_trend': self._calculate_trend_direction(response_times),
                'data_points': len(recent_metrics)
            }
            
        except Exception as e:
            return {'error': f'Trend calculation failed: {str(e)}'}
    
    def _calculate_trend_direction(self, values: List[float]) -> str:
        """Calculate if trend is improving, degrading, or stable"""
        if len(values) < 2:
            return 'unknown'
        
        recent_avg = sum(values[-3:]) / len(values[-3:]) if len(values) >= 3 else values[-1]
        older_avg = sum(values[:-3]) / len(values[:-3]) if len(values) > 3 else values[0]
        
        change_percent = ((recent_avg - older_avg) / older_avg * 100) if older_avg > 0 else 0
        
        if change_percent > 10:
            return 'degrading'
        elif change_percent < -10:
            return 'improving'
        else:
            return 'stable'
    
    def add_alert_rule(self, rule: AlertRule):
        """Add a new alert rule"""
        self.alert_rules.append(rule)
    
    def remove_alert_rule(self, rule_name: str):
        """Remove an alert rule"""
        self.alert_rules = [r for r in self.alert_rules if r.name != rule_name]
    
    def clear_alerts(self):
        """Clear all alerts"""
        with self._lock:
            self.alerts.clear()
    
    def export_metrics_history(self, hours: int = 24) -> List[Dict[str, Any]]:
        """Export metrics history for analysis"""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        with self._lock:
            return [
                snapshot for snapshot in self.metrics_history
                if datetime.fromisoformat(snapshot['timestamp']) > cutoff_time
            ]
