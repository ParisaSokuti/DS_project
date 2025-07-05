# Horizontal Scaling Deployment Guide

## Overview

This guide provides step-by-step instructions for deploying the horizontally scalable Hokm game server with WebSocket-aware load balancing, sticky sessions, and auto-scaling capabilities.

## Architecture Summary

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Load Balancer │    │   Game Servers   │    │   Redis Cluster │
│    (HAProxy)    │────│  (Multiple pods) │────│  (Master/Slave) │
│  - WebSocket    │    │  - Sticky rooms  │    │  - Persistence  │
│  - SSL/TLS      │    │  - Auto-scaling  │    │  - Pub/Sub      │
│  - Health check │    │  - Circuit break │    │  - Failover     │
└─────────────────┘    └──────────────────┘    └─────────────────┘
         │                       │                       │
         │              ┌────────────────┐              │
         │              │   Monitoring   │              │
         └──────────────│   - Prometheus │──────────────┘
                        │   - Grafana    │
                        │   - Alerting   │
                        └────────────────┘
```

## Deployment Options

### 1. Docker Compose (Development/Testing)

**Prerequisites:**
- Docker 20.10+
- Docker Compose 2.0+
- 4GB RAM minimum
- 2 CPU cores minimum

**Setup:**
```bash
# Clone repository
git clone <your-repo-url>
cd DS_project

# Create necessary directories
mkdir -p config/ssl
mkdir -p logs

# Generate SSL certificates (self-signed for testing)
openssl req -x509 -newkey rsa:4096 -keyout config/ssl/hokm.key -out config/ssl/hokm.crt -days 365 -nodes

# Create HAProxy configuration
cp config/haproxy.cfg.example config/haproxy.cfg

# Build and start services
docker-compose -f docker-compose.scaling.yml up -d

# Scale game servers
docker-compose -f docker-compose.scaling.yml up -d --scale hokm-server=4

# View logs
docker-compose -f docker-compose.scaling.yml logs -f hokm-server-1

# Monitor scaling
docker-compose -f docker-compose.scaling.yml exec auto-scaler python monitor_scaling.py
```

**Configuration Files:**

`config/haproxy.cfg`:
```haproxy
global
    daemon
    log stdout local0
    stats socket /var/lib/haproxy/admin.sock mode 660 level admin

defaults
    mode http
    timeout connect 5000ms
    timeout client 50000ms
    timeout server 50000ms
    option httplog

frontend hokm_websocket
    bind *:8765
    bind *:8766 ssl crt /etc/ssl/certs/hokm.pem
    
    # WebSocket upgrade detection
    acl is_websocket hdr(Connection) -i upgrade
    acl is_websocket hdr(Upgrade) -i websocket
    
    # Room-based sticky sessions
    stick-table type string len 32 size 10k expire 4h
    stick on url_param(room_code)
    
    use_backend hokm_servers if is_websocket

backend hokm_servers
    balance source
    option httpchk GET /health
    
    server hokm1 hokm-server-1:8001 check
    server hokm2 hokm-server-2:8002 check
    server hokm3 hokm-server-3:8003 check
    server hokm4 hokm-server-4:8004 check
```

### 2. Kubernetes (Production)

**Prerequisites:**
- Kubernetes 1.24+
- kubectl configured
- Helm 3.0+
- Ingress controller (NGINX recommended)
- Cert-manager for SSL
- Prometheus operator for monitoring

**Setup:**
```bash
# Create namespace
kubectl create namespace hokm-game

# Deploy Redis
kubectl apply -f k8s/redis-deployment.yml

# Deploy game servers
kubectl apply -f k8s-deployment.yml

# Verify deployment
kubectl get pods -n hokm-game
kubectl get services -n hokm-game
kubectl get ingress -n hokm-game

# Check auto-scaling
kubectl get hpa -n hokm-game
kubectl describe hpa hokm-server-hpa -n hokm-game

# Monitor scaling events
kubectl get events -n hokm-game --sort-by='.lastTimestamp'

# Scale manually if needed
kubectl scale deployment hokm-server --replicas=5 -n hokm-game
```

**Ingress Configuration:**
```yaml
# ingress-nginx configuration for WebSocket support
apiVersion: v1
kind: ConfigMap
metadata:
  name: nginx-configuration
  namespace: ingress-nginx
data:
  proxy-read-timeout: "3600"
  proxy-send-timeout: "3600"
  client-max-body-size: "1m"
  upstream-hash-by: "$arg_room_code"
```

### 3. AWS ECS (Cloud Production)

**Prerequisites:**
- AWS CLI configured
- ECS CLI installed
- ECR repository created
- Application Load Balancer
- RDS Redis cluster

**Setup:**
```bash
# Build and push Docker image
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 123456789012.dkr.ecr.us-east-1.amazonaws.com

docker build -t hokm-game .
docker tag hokm-game:latest 123456789012.dkr.ecr.us-east-1.amazonaws.com/hokm-game:latest
docker push 123456789012.dkr.ecr.us-east-1.amazonaws.com/hokm-game:latest

# Deploy ECS service
aws ecs create-cluster --cluster-name hokm-cluster

# Create task definition
aws ecs register-task-definition --cli-input-json file://ecs-task-definition.json

# Create service with auto-scaling
aws ecs create-service \
  --cluster hokm-cluster \
  --service-name hokm-service \
  --task-definition hokm-task:1 \
  --desired-count 2 \
  --launch-type FARGATE \
  --load-balancers targetGroupArn=arn:aws:elasticloadbalancing:us-east-1:123456789012:targetgroup/hokm-tg/1234567890123456,containerName=hokm-server,containerPort=8001

# Setup auto-scaling
aws application-autoscaling register-scalable-target \
  --service-namespace ecs \
  --scalable-dimension ecs:service:DesiredCount \
  --resource-id service/hokm-cluster/hokm-service \
  --min-capacity 2 \
  --max-capacity 20
```

## Load Balancer Configuration

### HAProxy (Recommended)

**Key Features:**
- WebSocket protocol upgrade handling
- Sticky sessions based on room code
- Health checks with automatic failover
- SSL termination
- Real-time statistics

**Configuration:**
```haproxy
# Sticky sessions based on room code
stick-table type string len 32 size 10k expire 4h
stick on url_param(room_code)

# Alternative: use WebSocket subprotocol
stick on hdr_sub(Sec-WebSocket-Protocol) room_code

# Health check endpoint
option httpchk GET /health HTTP/1.1\r\nHost:\ localhost
http-check expect status 200
```

### NGINX (Alternative)

**Configuration:**
```nginx
upstream hokm_servers {
    # Consistent hashing based on room code
    hash $arg_room_code consistent;
    
    server hokm-server-1:8001 max_fails=3 fail_timeout=30s;
    server hokm-server-2:8002 max_fails=3 fail_timeout=30s;
    server hokm-server-3:8003 max_fails=3 fail_timeout=30s;
    server hokm-server-4:8004 max_fails=3 fail_timeout=30s;
}

server {
    listen 8765;
    location / {
        proxy_pass http://hokm_servers;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket timeout
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }
}
```

## Auto-Scaling Configuration

### Metrics-Based Scaling Rules

**CPU and Memory:**
```yaml
# Scale up when CPU > 70% for 2 minutes
- name: high_cpu_usage
  metric: avg_cpu_usage
  threshold: 70.0
  duration: 120
  action: scale_up
  
# Scale up when memory > 80% for 2 minutes
- name: high_memory_usage
  metric: avg_memory_usage
  threshold: 80.0
  duration: 120
  action: scale_up
```

**Game-Specific Metrics:**
```yaml
# Scale up when average connections per instance > 100
- name: high_player_density
  metric: avg_connections_per_instance
  threshold: 100.0
  duration: 180
  action: scale_up

# Scale up when game creation rate > 10 games/minute
- name: high_game_creation_rate
  metric: game_creation_rate
  threshold: 10.0
  duration: 120
  action: scale_up

# Scale up when player queue > 20
- name: player_queue_length
  metric: queue_length
  threshold: 20.0
  duration: 60
  action: scale_up
```

**Scale Down Rules:**
```yaml
# Scale down when CPU < 20% for 10 minutes
- name: low_cpu_usage
  metric: avg_cpu_usage
  threshold: 20.0  
  duration: 600
  action: scale_down

# Scale down when connections per instance < 20 for 15 minutes
- name: low_player_density
  metric: avg_connections_per_instance
  threshold: 20.0
  duration: 900
  action: scale_down
```

### Custom Metrics Setup

**Prometheus Configuration:**
```yaml
# prometheus.yml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'hokm-servers'
    static_configs:
      - targets: ['hokm-server-1:8001', 'hokm-server-2:8002']
    metrics_path: /metrics
    scrape_interval: 30s

  - job_name: 'redis'
    static_configs:
      - targets: ['redis-master:6379']
```

**Game Server Metrics Endpoint:**
```python
# In your server.py
from prometheus_client import Counter, Gauge, Histogram, generate_latest

# Metrics
active_games = Gauge('hokm_active_games', 'Number of active games')
connected_players = Gauge('hokm_connected_players', 'Number of connected players')
games_created = Counter('hokm_games_created_total', 'Total games created')
websocket_connections = Gauge('hokm_websocket_connections', 'Active WebSocket connections')
response_time = Histogram('hokm_response_time_seconds', 'Response time in seconds')

async def handle_metrics(request):
    return web.Response(text=generate_latest(), content_type='text/plain')

# Add to your web app
app.router.add_get('/metrics', handle_metrics)
```

## Graceful Scaling Operations

### Scale Up Process

1. **Trigger Detection:**
   - Monitor metrics exceed thresholds
   - Auto-scaler decides to scale up
   - New instances are requested

2. **Instance Startup:**
   - New containers/pods are created
   - Health checks must pass
   - Service registration occurs

3. **Load Balancer Update:**
   - New instances added to backend pool
   - Traffic gradually shifted to new instances
   - Room assignments distributed

4. **Verification:**
   - Monitor metrics improve
   - No game disruption
   - Health checks remain green

### Scale Down Process

1. **Trigger Detection:**
   - Metrics below thresholds for sufficient time
   - Auto-scaler decides to scale down
   - Instances selected for removal

2. **Graceful Shutdown:**
   - Selected instances stop accepting new games
   - Existing games are migrated to other instances
   - WebSocket connections are gracefully closed

3. **Instance Removal:**
   - Instance removed from load balancer
   - Container/pod is terminated  
   - Resources are freed

4. **Verification:**
   - No game disruption occurred
   - Remaining instances handle load
   - Metrics remain stable

## Monitoring and Alerting

### Key Metrics to Monitor

**Infrastructure:**
- CPU usage per instance
- Memory usage per instance
- Network I/O
- Disk I/O
- Instance health status

**Application:**
- Active WebSocket connections
- Active games count
- Players per instance
- Game creation rate
- Player join rate
- Response times (P50, P95, P99)
- Error rates

**Business:**
- Peak concurrent players
- Games completed per hour
- Average game duration
- Player retention rate
- Revenue per game (if applicable)

### Alerting Rules

**Critical Alerts:**
```yaml
- alert: HighErrorRate
  expr: hokm_error_rate > 0.05
  for: 2m
  labels:
    severity: critical
  annotations:
    summary: "High error rate detected"

- alert: AllInstancesDown
  expr: up{job="hokm-servers"} == 0
  for: 1m
  labels:
    severity: critical
  annotations:
    summary: "All game server instances are down"
```

**Warning Alerts:**
```yaml
- alert: HighCPUUsage
  expr: hokm_cpu_usage > 0.8
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "High CPU usage on game servers"

- alert: ScalingEventFrequent
  expr: increase(hokm_scaling_events_total[1h]) > 5
  for: 0m
  labels:
    severity: warning
  annotations:
    summary: "Frequent scaling events detected"
```

## Testing Scaling Behavior

### Load Testing

```bash
# Test with increasing load
python test_scaling_load.py --initial-players 10 --max-players 500 --ramp-up-time 300

# Test scaling triggers
python test_scaling_triggers.py --trigger-cpu-load --trigger-memory-load

# Test graceful shutdown
python test_graceful_shutdown.py --instance hokm-server-3
```

### Scaling Validation

```bash
# Monitor scaling in real-time
kubectl get hpa -w -n hokm-game

# Check scaling events
kubectl describe hpa hokm-server-hpa -n hokm-game

# Verify no game disruption
python test_game_continuity.py --during-scaling
```

## Troubleshooting

### Common Issues

**Sticky Sessions Not Working:**
- Check room code parameter extraction
- Verify load balancer configuration
- Test with manual room assignments

**Scaling Too Aggressive:**
- Increase scaling thresholds
- Extend observation windows
- Add cooldown periods

**Games Lost During Scaling:**
- Verify graceful shutdown implementation
- Check game migration logic
- Ensure Redis persistence

**High Response Times:**
- Check inter-server communication
- Verify Redis cluster performance
- Monitor network latency

### Debug Commands

```bash
# Check load balancer status
curl http://localhost:8404/stats

# Verify instance registration
redis-cli KEYS "service:hokm:instances:*"

# Check scaling metrics
curl http://localhost:9090/api/v1/query?query=hokm_active_games

# Monitor WebSocket connections
ss -tulpn | grep :8765
```

## Performance Benchmarks

### Expected Performance

**Single Instance:**
- 100-200 concurrent players
- 25-50 active games
- < 100ms response time
- < 5% CPU usage per 10 concurrent games

**Scaled Deployment (4 instances):**
- 400-800 concurrent players
- 100-200 active games
- < 150ms response time
- Auto-scaling triggers at 70% CPU

**Large Scale (20 instances):**
- 2000-4000 concurrent players
- 500-1000 active games
- < 200ms response time
- Graceful degradation under load

This horizontal scaling solution provides enterprise-grade reliability, automatic scaling, and seamless player experience while maintaining game session integrity across all instances.
