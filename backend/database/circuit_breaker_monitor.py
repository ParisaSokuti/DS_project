"""
PostgreSQL Circuit Breaker Monitoring and Health Check System
Integrates with existing circuit breaker monitoring system to provide comprehensive
PostgreSQL-specific monitoring, alerting, and health checking
"""

import asyncio
import time
import json
import logging
from typing import Dict, List, Any, Optional, Set
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum
from collections import defaultdict, deque

from .postgresql_circuit_breaker import (
    PostgreSQLCircuitBreaker, PostgreSQLCircuitState, ErrorCategory,
    PostgreSQLCircuitBreakerConfig
)

logger = logging.getLogger(__name__)

class PostgreSQLHealthStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    CRITICAL = "critical"

@dataclass
class PostgreSQLHealthCheckResult:
    service: str
    status: PostgreSQLHealthStatus
    message: str
    timestamp: datetime
    response_time: float
    connection_pool_stats: Dict[str, Any] = None
    query_performance: Dict[str, Any] = None
    error_details: Dict[str, Any] = None

@dataclass
class PostgreSQLAlertRule:
    name: str
    condition: str  # e.g., "failure_rate > 0.5"
    threshold: float
    duration: int  # seconds
    severity: str  # info, warning, error, critical
    enabled: bool = True
    postgresql_specific: bool = True

class PostgreSQLCircuitBreakerMonitor:
    """
    Comprehensive monitoring system for PostgreSQL circuit breakers
    
    Features:
    - Real-time PostgreSQL health monitoring
    - Database-specific alerting rules
    - Connection pool monitoring
    - Query performance analysis
    - Error pattern detection
    - Integration with existing monitoring system
    - Automatic circuit breaker management
    """
    
    def __init__(self, session_manager=None):
        self.session_manager = session_manager
        self.circuit_breakers: Dict[str, PostgreSQLCircuitBreaker] = {}
        self.health_checks = {}
        self.alerts = []
        self.alert_rules = self._create_postgresql_alert_rules()
        self.metrics_history = deque(maxlen=1000)
        
        # Performance tracking
        self.query_performance_tracker = QueryPerformanceTracker()
        self.connection_pool_monitor = ConnectionPoolMonitor()
        self.error_pattern_detector = ErrorPatternDetector()
        
        # Monitoring configuration
        self.monitoring_interval = 30  # seconds
        self.health_check_interval = 60  # seconds
        
        # Monitoring tasks
        self._monitoring_task = None
        self._health_check_task = None
        self._stop_monitoring = False
        
        logger.info("PostgreSQL Circuit Breaker Monitor initialized")
    
    def _create_postgresql_alert_rules(self) -> List[PostgreSQLAlertRule]:
        """Create PostgreSQL-specific alerting rules"""
        return [
            # Database connection issues
            PostgreSQLAlertRule(
                name="high_db_failure_rate",
                condition="failure_rate > 0.7",
                threshold=0.7,
                duration=60,
                severity="critical"
            ),
            PostgreSQLAlertRule(
                name="db_circuit_open",
                condition="circuit_state == 'open'",
                threshold=1,
                duration=30,
                severity="error"
            ),
            PostgreSQLAlertRule(
                name="slow_db_queries",
                condition="avg_response_time > 3.0",
                threshold=3.0,
                duration=120,
                severity="warning"
            ),
            PostgreSQLAlertRule(
                name="high_db_retry_rate",
                condition="retry_rate > 0.3",
                threshold=0.3,
                duration=90,
                severity="warning"
            ),
            PostgreSQLAlertRule(
                name="connection_pool_exhaustion",
                condition="pool_utilization > 0.9",
                threshold=0.9,
                duration=60,
                severity="error"
            ),
            PostgreSQLAlertRule(
                name="persistent_connection_errors",
                condition="consecutive_connection_failures > 5",
                threshold=5,
                duration=180,
                severity="critical"
            ),
            PostgreSQLAlertRule(
                name="high_fallback_usage",
                condition="fallback_rate > 0.4",
                threshold=0.4,
                duration=300,
                severity="warning"
            ),
            # Query-specific alerts
            PostgreSQLAlertRule(
                name="query_timeout_spike",
                condition="timeout_error_rate > 0.2",
                threshold=0.2,
                duration=120,
                severity="error"
            ),
            PostgreSQLAlertRule(
                name="deadlock_detection",
                condition="deadlock_rate > 0.1",
                threshold=0.1,
                duration=300,
                severity="warning"
            )
        ]
    
    def register_circuit_breaker(
        self, 
        name: str, 
        circuit_breaker: PostgreSQLCircuitBreaker
    ):
        """Register a circuit breaker for monitoring"""
        self.circuit_breakers[name] = circuit_breaker
        logger.info(f"Registered PostgreSQL circuit breaker '{name}' for monitoring")
    
    def create_circuit_breaker(
        self, 
        name: str,
        config: Optional[PostgreSQLCircuitBreakerConfig] = None,
        fallback_handler: Optional[callable] = None
    ) -> PostgreSQLCircuitBreaker:
        """Create and register a new circuit breaker"""
        cb = PostgreSQLCircuitBreaker(name, config, fallback_handler)
        self.register_circuit_breaker(name, cb)
        return cb
    
    async def start_monitoring(self):
        """Start the monitoring tasks"""
        if self._monitoring_task and not self._monitoring_task.done():
            return
        
        self._stop_monitoring = False
        
        # Start monitoring tasks
        self._monitoring_task = asyncio.create_task(self._monitoring_loop())
        self._health_check_task = asyncio.create_task(self._health_check_loop())
        
        logger.info("PostgreSQL circuit breaker monitoring started")
    
    async def stop_monitoring(self):
        """Stop the monitoring tasks"""
        self._stop_monitoring = True
        
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
        
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
        
        logger.info("PostgreSQL circuit breaker monitoring stopped")
    
    async def _monitoring_loop(self):
        """Main monitoring loop"""
        while not self._stop_monitoring:
            try:
                await self._collect_metrics()
                await self._check_alert_rules()
                await self._update_performance_tracking()
                await asyncio.sleep(self.monitoring_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(self.monitoring_interval)
    
    async def _health_check_loop(self):
        """Health check loop"""
        while not self._stop_monitoring:
            try:
                await self._perform_health_checks()
                await asyncio.sleep(self.health_check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in health check loop: {e}")
                await asyncio.sleep(self.health_check_interval)
    
    async def _collect_metrics(self):
        """Collect metrics from all circuit breakers"""
        timestamp = datetime.now()
        all_metrics = {}
        
        for name, cb in self.circuit_breakers.items():
            try:
                state_info = await cb.get_state()
                all_metrics[name] = {
                    'timestamp': timestamp.isoformat(),
                    'circuit_breaker': state_info,
                    'performance': await self.query_performance_tracker.get_metrics(name),
                    'connection_pool': await self.connection_pool_monitor.get_metrics(name),
                    'error_patterns': await self.error_pattern_detector.get_patterns(name)
                }
            except Exception as e:
                logger.error(f"Failed to collect metrics for circuit breaker '{name}': {e}")
        
        # Store metrics history
        self.metrics_history.append({
            'timestamp': timestamp,
            'metrics': all_metrics
        })
        
        # Update error pattern detection
        await self.error_pattern_detector.analyze_patterns(all_metrics)
    
    async def _check_alert_rules(self):
        """Check alert rules against current metrics"""
        current_metrics = self.metrics_history[-1]['metrics'] if self.metrics_history else {}
        
        for rule in self.alert_rules:
            if not rule.enabled:
                continue
            
            try:
                await self._evaluate_alert_rule(rule, current_metrics)
            except Exception as e:
                logger.error(f"Error evaluating alert rule '{rule.name}': {e}")
    
    async def _evaluate_alert_rule(
        self, 
        rule: PostgreSQLAlertRule, 
        metrics: Dict[str, Any]
    ):
        """Evaluate a single alert rule"""
        triggered_services = []
        
        for service_name, service_metrics in metrics.items():
            if self._rule_matches_metrics(rule, service_metrics):
                triggered_services.append(service_name)
        
        if triggered_services:
            alert = {
                'rule_name': rule.name,
                'condition': rule.condition,
                'threshold': rule.threshold,
                'severity': rule.severity,
                'services': triggered_services,
                'timestamp': datetime.now(),
                'message': f"Alert '{rule.name}' triggered for services: {', '.join(triggered_services)}"
            }
            
            self.alerts.append(alert)
            
            # Log alert
            log_level = getattr(logging, rule.severity.upper(), logging.WARNING)
            logger.log(log_level, alert['message'])
            
            # Could integrate with external alerting systems here
            await self._send_alert_notification(alert)
    
    def _rule_matches_metrics(self, rule: PostgreSQLAlertRule, metrics: Dict[str, Any]) -> bool:
        """Check if a rule matches the given metrics"""
        try:
            cb_metrics = metrics.get('circuit_breaker', {}).get('metrics', {})
            cb_state = metrics.get('circuit_breaker', {})
            perf_metrics = metrics.get('performance', {})
            pool_metrics = metrics.get('connection_pool', {})
            
            # Create evaluation context
            context = {
                'failure_rate': cb_metrics.get('failure_rate', 0) / 100,
                'circuit_state': cb_state.get('state', 'closed'),
                'avg_response_time': cb_metrics.get('avg_response_time', 0),
                'retry_rate': cb_metrics.get('total_retries', 0) / max(cb_metrics.get('total_requests', 1), 1),
                'fallback_rate': cb_metrics.get('fallback_executions', 0) / max(cb_metrics.get('total_requests', 1), 1),
                'pool_utilization': pool_metrics.get('utilization', 0),
                'consecutive_connection_failures': cb_metrics.get('consecutive_health_failures', 0),
                'timeout_error_rate': cb_metrics.get('error_categories', {}).get('timeout', 0) / max(cb_metrics.get('total_requests', 1), 1),
                'deadlock_rate': perf_metrics.get('deadlock_rate', 0)
            }
            
            # Simple condition evaluation
            if rule.condition in context:
                return context[rule.condition] > rule.threshold
            
            # More complex condition evaluation could be added here
            return False
            
        except Exception as e:
            logger.error(f"Error evaluating rule condition '{rule.condition}': {e}")
            return False
    
    async def _send_alert_notification(self, alert: Dict[str, Any]):
        """Send alert notification (could integrate with external systems)"""
        # This could be extended to send notifications to:
        # - Slack/Discord webhooks
        # - Email notifications
        # - PagerDuty/OpsGenie
        # - Custom webhook endpoints
        
        logger.info(f"Alert notification would be sent: {alert['message']}")
    
    async def _perform_health_checks(self):
        """Perform comprehensive health checks"""
        timestamp = datetime.now()
        
        for name, cb in self.circuit_breakers.items():
            try:
                health_result = await self._check_circuit_breaker_health(name, cb)
                self.health_checks[name] = health_result
                
                # Log health status changes
                if health_result.status != PostgreSQLHealthStatus.HEALTHY:
                    logger.warning(f"Health check for '{name}': {health_result.status.value} - {health_result.message}")
                
            except Exception as e:
                error_result = PostgreSQLHealthCheckResult(
                    service=name,
                    status=PostgreSQLHealthStatus.CRITICAL,
                    message=f"Health check failed: {str(e)}",
                    timestamp=timestamp,
                    response_time=-1
                )
                self.health_checks[name] = error_result
                logger.error(f"Health check failed for '{name}': {e}")
    
    async def _check_circuit_breaker_health(
        self, 
        name: str, 
        cb: PostgreSQLCircuitBreaker
    ) -> PostgreSQLHealthCheckResult:
        """Perform health check for a specific circuit breaker"""
        start_time = time.time()
        
        try:
            # Get circuit breaker state
            state_info = await cb.get_state()
            response_time = time.time() - start_time
            
            # Determine health status based on state and metrics
            status = self._determine_health_status(state_info)
            
            # Generate health message
            message = self._generate_health_message(state_info, status)
            
            return PostgreSQLHealthCheckResult(
                service=name,
                status=status,
                message=message,
                timestamp=datetime.now(),
                response_time=response_time,
                connection_pool_stats=await self.connection_pool_monitor.get_metrics(name),
                query_performance=await self.query_performance_tracker.get_metrics(name),
                error_details=state_info.get('metrics', {}).get('error_categories', {})
            )
            
        except Exception as e:
            return PostgreSQLHealthCheckResult(
                service=name,
                status=PostgreSQLHealthStatus.CRITICAL,
                message=f"Health check error: {str(e)}",
                timestamp=datetime.now(),
                response_time=time.time() - start_time
            )
    
    def _determine_health_status(self, state_info: Dict[str, Any]) -> PostgreSQLHealthStatus:
        """Determine health status based on circuit breaker state"""
        state = state_info.get('state', 'closed')
        metrics = state_info.get('metrics', {})
        
        failure_rate = metrics.get('failure_rate', 0)
        consecutive_failures = metrics.get('consecutive_health_failures', 0)
        avg_response_time = metrics.get('avg_response_time', 0)
        
        # Critical conditions
        if state == 'open' or consecutive_failures >= 5:
            return PostgreSQLHealthStatus.CRITICAL
        
        # Unhealthy conditions
        if failure_rate > 50 or avg_response_time > 5.0:
            return PostgreSQLHealthStatus.UNHEALTHY
        
        # Degraded conditions
        if failure_rate > 20 or avg_response_time > 2.0 or state == 'half_open':
            return PostgreSQLHealthStatus.DEGRADED
        
        return PostgreSQLHealthStatus.HEALTHY
    
    def _generate_health_message(
        self, 
        state_info: Dict[str, Any], 
        status: PostgreSQLHealthStatus
    ) -> str:
        """Generate human-readable health message"""
        state = state_info.get('state', 'closed')
        metrics = state_info.get('metrics', {})
        
        if status == PostgreSQLHealthStatus.HEALTHY:
            return f"Circuit {state}, {metrics.get('success_rate', 0):.1f}% success rate"
        
        elif status == PostgreSQLHealthStatus.DEGRADED:
            return f"Circuit {state}, {metrics.get('failure_rate', 0):.1f}% failure rate, {metrics.get('avg_response_time', 0):.2f}s avg response"
        
        elif status == PostgreSQLHealthStatus.UNHEALTHY:
            return f"Circuit {state}, high failure rate ({metrics.get('failure_rate', 0):.1f}%) or slow queries"
        
        else:  # CRITICAL
            return f"Circuit {state}, {metrics.get('consecutive_health_failures', 0)} consecutive failures"
    
    async def _update_performance_tracking(self):
        """Update performance tracking metrics"""
        try:
            await self.query_performance_tracker.update()
            await self.connection_pool_monitor.update()
        except Exception as e:
            logger.error(f"Error updating performance tracking: {e}")
    
    async def get_comprehensive_status(self) -> Dict[str, Any]:
        """Get comprehensive status of all monitored circuit breakers"""
        status = {
            'timestamp': datetime.now().isoformat(),
            'circuit_breakers': {},
            'health_checks': {},
            'alerts': {
                'active_alerts': len([a for a in self.alerts if (datetime.now() - a['timestamp']).seconds < 3600]),
                'recent_alerts': self.alerts[-10:] if self.alerts else []
            },
            'performance_summary': await self._get_performance_summary(),
            'monitoring_status': {
                'monitoring_active': not self._stop_monitoring,
                'monitored_services': len(self.circuit_breakers),
                'metrics_history_size': len(self.metrics_history)
            }
        }
        
        # Get circuit breaker states
        for name, cb in self.circuit_breakers.items():
            try:
                status['circuit_breakers'][name] = await cb.get_state()
            except Exception as e:
                status['circuit_breakers'][name] = {'error': str(e)}
        
        # Get health check results
        for name, health_result in self.health_checks.items():
            status['health_checks'][name] = asdict(health_result)
        
        return status
    
    async def _get_performance_summary(self) -> Dict[str, Any]:
        """Get performance summary across all services"""
        total_requests = 0
        total_failures = 0
        total_response_time = 0
        service_count = 0
        
        for name, cb in self.circuit_breakers.items():
            try:
                state_info = await cb.get_state()
                metrics = state_info.get('metrics', {})
                
                total_requests += metrics.get('total_requests', 0)
                total_failures += metrics.get('total_failures', 0)
                total_response_time += metrics.get('avg_response_time', 0)
                service_count += 1
                
            except Exception:
                continue
        
        return {
            'total_requests': total_requests,
            'overall_failure_rate': (total_failures / max(total_requests, 1)) * 100,
            'avg_response_time': total_response_time / max(service_count, 1),
            'monitored_services': service_count
        }
    
    async def reset_all_circuit_breakers(self):
        """Reset all monitored circuit breakers"""
        for name, cb in self.circuit_breakers.items():
            try:
                await cb.reset()
                logger.info(f"Reset circuit breaker '{name}'")
            except Exception as e:
                logger.error(f"Failed to reset circuit breaker '{name}': {e}")
    
    async def get_metrics_export(self) -> Dict[str, Any]:
        """Export metrics in a format suitable for external monitoring systems"""
        export_data = {
            'timestamp': datetime.now().isoformat(),
            'services': {}
        }
        
        for name, cb in self.circuit_breakers.items():
            try:
                state_info = await cb.get_state()
                metrics = state_info.get('metrics', {})
                
                export_data['services'][name] = {
                    'circuit_state': state_info.get('state'),
                    'requests_total': metrics.get('total_requests', 0),
                    'failures_total': metrics.get('total_failures', 0),
                    'success_rate': metrics.get('success_rate', 0),
                    'avg_response_time_seconds': metrics.get('avg_response_time', 0),
                    'circuit_opens_total': metrics.get('circuit_opens', 0),
                    'fallback_executions_total': metrics.get('fallback_executions', 0)
                }
            except Exception as e:
                logger.error(f"Failed to export metrics for '{name}': {e}")
        
        return export_data

class QueryPerformanceTracker:
    """Tracks query performance metrics"""
    
    def __init__(self):
        self.metrics = defaultdict(lambda: {
            'slow_queries': 0,
            'avg_query_time': 0.0,
            'query_timeouts': 0,
            'deadlocks': 0,
            'connection_errors': 0
        })
    
    async def get_metrics(self, service_name: str) -> Dict[str, Any]:
        """Get performance metrics for a service"""
        return dict(self.metrics[service_name])
    
    async def update(self):
        """Update performance metrics (placeholder for actual implementation)"""
        # This would integrate with actual query performance monitoring
        pass

class ConnectionPoolMonitor:
    """Monitors database connection pool metrics"""
    
    def __init__(self):
        self.metrics = defaultdict(lambda: {
            'active_connections': 0,
            'idle_connections': 0,
            'total_connections': 0,
            'utilization': 0.0,
            'connection_wait_time': 0.0
        })
    
    async def get_metrics(self, service_name: str) -> Dict[str, Any]:
        """Get connection pool metrics for a service"""
        return dict(self.metrics[service_name])
    
    async def update(self):
        """Update connection pool metrics (placeholder for actual implementation)"""
        # This would integrate with actual connection pool monitoring
        pass

class ErrorPatternDetector:
    """Detects patterns in database errors"""
    
    def __init__(self):
        self.patterns = defaultdict(list)
        self.detected_patterns = {}
    
    async def get_patterns(self, service_name: str) -> Dict[str, Any]:
        """Get detected error patterns for a service"""
        return self.detected_patterns.get(service_name, {})
    
    async def analyze_patterns(self, metrics: Dict[str, Any]):
        """Analyze error patterns across services"""
        # This would implement pattern detection algorithms
        pass
