# redis_cluster_config.py
"""
Redis Cluster Configuration and Setup
"""

import os
import logging
from typing import Dict, List, Any
from dataclasses import dataclass

@dataclass
class RedisNodeConfig:
    host: str
    port: int
    password: str = None
    max_memory: str = "512mb"
    max_memory_policy: str = "allkeys-lru"
    appendonly: bool = True
    save_interval: str = "900 1 300 10 60 10000"  # RDB save intervals

@dataclass
class ClusterConfig:
    nodes: List[RedisNodeConfig]
    sentinel_nodes: List[RedisNodeConfig] = None
    cluster_enabled: bool = True
    cluster_node_timeout: int = 15000
    cluster_migration_barrier: int = 1
    cluster_require_full_coverage: bool = False
    max_connections_per_node: int = 100
    health_check_interval: int = 30

# Production cluster configuration
PRODUCTION_CLUSTER_CONFIG = ClusterConfig(
    nodes=[
        # Master nodes
        RedisNodeConfig(host="redis-master-1.gameserver.com", port=7000, password=os.getenv("REDIS_PASSWORD")),
        RedisNodeConfig(host="redis-master-2.gameserver.com", port=7001, password=os.getenv("REDIS_PASSWORD")),
        RedisNodeConfig(host="redis-master-3.gameserver.com", port=7002, password=os.getenv("REDIS_PASSWORD")),
        
        # Replica nodes
        RedisNodeConfig(host="redis-replica-1.gameserver.com", port=7003, password=os.getenv("REDIS_PASSWORD")),
        RedisNodeConfig(host="redis-replica-2.gameserver.com", port=7004, password=os.getenv("REDIS_PASSWORD")),
        RedisNodeConfig(host="redis-replica-3.gameserver.com", port=7005, password=os.getenv("REDIS_PASSWORD")),
    ],
    sentinel_nodes=[
        RedisNodeConfig(host="redis-sentinel-1.gameserver.com", port=26379),
        RedisNodeConfig(host="redis-sentinel-2.gameserver.com", port=26380),
        RedisNodeConfig(host="redis-sentinel-3.gameserver.com", port=26381),
    ],
    max_connections_per_node=200,
    health_check_interval=10
)

# Development/Testing cluster configuration
DEVELOPMENT_CLUSTER_CONFIG = ClusterConfig(
    nodes=[
        RedisNodeConfig(host="localhost", port=7000),
        RedisNodeConfig(host="localhost", port=7001),
        RedisNodeConfig(host="localhost", port=7002),
        RedisNodeConfig(host="localhost", port=7003),
        RedisNodeConfig(host="localhost", port=7004),
        RedisNodeConfig(host="localhost", port=7005),
    ],
    max_connections_per_node=50,
    health_check_interval=30
)

# Single node configuration (fallback)
SINGLE_NODE_CONFIG = ClusterConfig(
    nodes=[
        RedisNodeConfig(host="localhost", port=6379)
    ],
    cluster_enabled=False
)

def get_cluster_config(environment: str = "development") -> ClusterConfig:
    """Get cluster configuration based on environment"""
    configs = {
        "production": PRODUCTION_CLUSTER_CONFIG,
        "development": DEVELOPMENT_CLUSTER_CONFIG,
        "single": SINGLE_NODE_CONFIG
    }
    
    return configs.get(environment, DEVELOPMENT_CLUSTER_CONFIG)

def generate_redis_config_file(node: RedisNodeConfig, data_dir: str = "/var/lib/redis") -> str:
    """Generate Redis configuration file content for a node"""
    
    config_content = f"""
# Redis {node.host}:{node.port} Configuration

# Network
bind 0.0.0.0
port {node.port}
protected-mode yes
timeout 0
tcp-keepalive 300

# General
daemonize no
supervised no
pidfile /var/run/redis_{node.port}.pid
loglevel notice
logfile /var/log/redis/redis_{node.port}.log
databases 16

# Snapshotting
save {node.save_interval}
stop-writes-on-bgsave-error yes
rdbcompression yes
rdbchecksum yes
dbfilename dump_{node.port}.rdb
dir {data_dir}

# Replication
replica-serve-stale-data yes
replica-read-only yes
repl-diskless-sync no
repl-diskless-sync-delay 5
repl-ping-replica-period 10
repl-timeout 60
repl-disable-tcp-nodelay no
repl-backlog-size 1mb
repl-backlog-ttl 3600

# Security
{"requirepass " + node.password if node.password else "# requirepass foobared"}

# Memory Management
maxmemory {node.max_memory}
maxmemory-policy {node.max_memory_policy}

# Append Only File
appendonly {str(node.appendonly).lower()}
appendfilename "appendonly_{node.port}.aof"
appendfsync everysec
no-appendfsync-on-rewrite no
auto-aof-rewrite-percentage 100
auto-aof-rewrite-min-size 64mb
aof-load-truncated yes

# Cluster Configuration
cluster-enabled yes
cluster-config-file nodes_{node.port}.conf
cluster-node-timeout 15000
cluster-migration-barrier 1
cluster-require-full-coverage no

# Slow Log
slowlog-log-slower-than 10000
slowlog-max-len 128

# Latency Monitor
latency-monitor-threshold 100

# Event Notification
notify-keyspace-events ""

# Advanced Config
hash-max-ziplist-entries 512
hash-max-ziplist-value 64
list-max-ziplist-size -2
list-compress-depth 0
set-max-intset-entries 512
zset-max-ziplist-entries 128
zset-max-ziplist-value 64
hll-sparse-max-bytes 3000
stream-node-max-bytes 4096
stream-node-max-entries 100
activerehashing yes
client-output-buffer-limit normal 0 0 0
client-output-buffer-limit replica 256mb 64mb 60
client-output-buffer-limit pubsub 32mb 8mb 60
hz 10
dynamic-hz yes
aof-rewrite-incremental-fsync yes
rdb-save-incremental-fsync yes
"""
    
    return config_content.strip()

def generate_sentinel_config_file(sentinel_node: RedisNodeConfig, 
                                master_nodes: List[RedisNodeConfig]) -> str:
    """Generate Redis Sentinel configuration file"""
    
    config_content = f"""
# Redis Sentinel {sentinel_node.host}:{sentinel_node.port} Configuration

# Network
bind 0.0.0.0
port {sentinel_node.port}
sentinel announce-ip {sentinel_node.host}
sentinel announce-port {sentinel_node.port}

# General
daemonize no
supervised no
pidfile /var/run/redis-sentinel_{sentinel_node.port}.pid
logfile /var/log/redis/sentinel_{sentinel_node.port}.log
dir /tmp

"""
    
    # Add master configurations
    for i, master in enumerate(master_nodes[:3]):  # Only first 3 as masters
        master_name = f"mymaster{i+1}"
        config_content += f"""
# Master {i+1} Configuration
sentinel monitor {master_name} {master.host} {master.port} 2
sentinel down-after-milliseconds {master_name} 5000
sentinel parallel-syncs {master_name} 1
sentinel failover-timeout {master_name} 30000
{"sentinel auth-pass " + master_name + " " + master.password if master.password else ""}

"""
    
    return config_content.strip()

def generate_docker_compose_cluster() -> str:
    """Generate Docker Compose file for Redis cluster"""
    
    compose_content = """
version: '3.8'

services:
  redis-1:
    image: redis:7-alpine
    container_name: redis-node-1
    command: redis-server /usr/local/etc/redis/redis.conf
    ports:
      - "7000:7000"
      - "17000:17000"
    volumes:
      - ./config/redis-7000.conf:/usr/local/etc/redis/redis.conf:ro
      - redis-1-data:/data
    networks:
      - redis-cluster

  redis-2:
    image: redis:7-alpine
    container_name: redis-node-2
    command: redis-server /usr/local/etc/redis/redis.conf
    ports:
      - "7001:7001"
      - "17001:17001"
    volumes:
      - ./config/redis-7001.conf:/usr/local/etc/redis/redis.conf:ro
      - redis-2-data:/data
    networks:
      - redis-cluster

  redis-3:
    image: redis:7-alpine
    container_name: redis-node-3
    command: redis-server /usr/local/etc/redis/redis.conf
    ports:
      - "7002:7002"
      - "17002:17002"
    volumes:
      - ./config/redis-7002.conf:/usr/local/etc/redis/redis.conf:ro
      - redis-3-data:/data
    networks:
      - redis-cluster

  redis-4:
    image: redis:7-alpine
    container_name: redis-node-4
    command: redis-server /usr/local/etc/redis/redis.conf
    ports:
      - "7003:7003"
      - "17003:17003"
    volumes:
      - ./config/redis-7003.conf:/usr/local/etc/redis/redis.conf:ro
      - redis-4-data:/data
    networks:
      - redis-cluster

  redis-5:
    image: redis:7-alpine
    container_name: redis-node-5
    command: redis-server /usr/local/etc/redis/redis.conf
    ports:
      - "7004:7004"
      - "17004:17004"
    volumes:
      - ./config/redis-7004.conf:/usr/local/etc/redis/redis.conf:ro
      - redis-5-data:/data
    networks:
      - redis-cluster

  redis-6:
    image: redis:7-alpine
    container_name: redis-node-6
    command: redis-server /usr/local/etc/redis/redis.conf
    ports:
      - "7005:7005"
      - "17005:17005"
    volumes:
      - ./config/redis-7005.conf:/usr/local/etc/redis/redis.conf:ro
      - redis-6-data:/data
    networks:
      - redis-cluster

  redis-sentinel-1:
    image: redis:7-alpine
    container_name: redis-sentinel-1
    command: redis-sentinel /usr/local/etc/redis/sentinel.conf
    ports:
      - "26379:26379"
    volumes:
      - ./config/sentinel-26379.conf:/usr/local/etc/redis/sentinel.conf:ro
    networks:
      - redis-cluster
    depends_on:
      - redis-1
      - redis-2
      - redis-3

  redis-sentinel-2:
    image: redis:7-alpine
    container_name: redis-sentinel-2
    command: redis-sentinel /usr/local/etc/redis/sentinel.conf
    ports:
      - "26380:26380"
    volumes:
      - ./config/sentinel-26380.conf:/usr/local/etc/redis/sentinel.conf:ro
    networks:
      - redis-cluster
    depends_on:
      - redis-1
      - redis-2
      - redis-3

  redis-sentinel-3:
    image: redis:7-alpine
    container_name: redis-sentinel-3
    command: redis-sentinel /usr/local/etc/redis/sentinel.conf
    ports:
      - "26381:26381"
    volumes:
      - ./config/sentinel-26381.conf:/usr/local/etc/redis/sentinel.conf:ro
    networks:
      - redis-cluster
    depends_on:
      - redis-1
      - redis-2
      - redis-3

  cluster-init:
    image: redis:7-alpine
    container_name: redis-cluster-init
    command: >
      sh -c "
        sleep 10 &&
        redis-cli --cluster create 
        redis-1:7000 redis-2:7001 redis-3:7002 
        redis-4:7003 redis-5:7004 redis-6:7005 
        --cluster-replicas 1 --cluster-yes
      "
    networks:
      - redis-cluster
    depends_on:
      - redis-1
      - redis-2
      - redis-3
      - redis-4
      - redis-5
      - redis-6

volumes:
  redis-1-data:
  redis-2-data:
  redis-3-data:
  redis-4-data:
  redis-5-data:
  redis-6-data:

networks:
  redis-cluster:
    driver: bridge
"""
    
    return compose_content.strip()

def generate_k8s_deployment() -> str:
    """Generate Kubernetes deployment for Redis cluster"""
    
    k8s_content = """
apiVersion: v1
kind: ConfigMap
metadata:
  name: redis-cluster-config
data:
  redis.conf: |
    cluster-enabled yes
    cluster-config-file nodes.conf
    cluster-node-timeout 15000
    cluster-migration-barrier 1
    cluster-require-full-coverage no
    appendonly yes
    maxmemory 512mb
    maxmemory-policy allkeys-lru
    
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: redis-cluster
spec:
  serviceName: redis-cluster
  replicas: 6
  selector:
    matchLabels:
      app: redis-cluster
  template:
    metadata:
      labels:
        app: redis-cluster
    spec:
      containers:
      - name: redis
        image: redis:7-alpine
        command:
        - redis-server
        - /etc/redis/redis.conf
        - --cluster-enabled
        - "yes"
        - --cluster-config-file
        - /data/nodes.conf
        - --cluster-node-timeout
        - "15000"
        - --appendonly
        - "yes"
        ports:
        - containerPort: 6379
          name: client
        - containerPort: 16379
          name: cluster
        volumeMounts:
        - name: data
          mountPath: /data
        - name: config
          mountPath: /etc/redis
        resources:
          requests:
            memory: "512Mi"
            cpu: "100m"
          limits:
            memory: "1Gi"
            cpu: "500m"
      volumes:
      - name: config
        configMap:
          name: redis-cluster-config
  volumeClaimTemplates:
  - metadata:
      name: data
    spec:
      accessModes: ["ReadWriteOnce"]
      resources:
        requests:
          storage: 10Gi

---
apiVersion: v1
kind: Service
metadata:
  name: redis-cluster
spec:
  clusterIP: None
  selector:
    app: redis-cluster
  ports:
  - port: 6379
    targetPort: 6379
    name: client
  - port: 16379
    targetPort: 16379
    name: cluster

---
apiVersion: batch/v1
kind: Job
metadata:
  name: redis-cluster-init
spec:
  template:
    spec:
      restartPolicy: OnFailure
      containers:
      - name: cluster-init
        image: redis:7-alpine
        command:
        - /bin/sh
        - -c
        - |
          sleep 30
          redis-cli --cluster create \\
            redis-cluster-0.redis-cluster.default.svc.cluster.local:6379 \\
            redis-cluster-1.redis-cluster.default.svc.cluster.local:6379 \\
            redis-cluster-2.redis-cluster.default.svc.cluster.local:6379 \\
            redis-cluster-3.redis-cluster.default.svc.cluster.local:6379 \\
            redis-cluster-4.redis-cluster.default.svc.cluster.local:6379 \\
            redis-cluster-5.redis-cluster.default.svc.cluster.local:6379 \\
            --cluster-replicas 1 --cluster-yes
"""
    
    return k8s_content.strip()

# Environment detection
def detect_environment() -> str:
    """Detect the current environment"""
    if os.getenv("KUBERNETES_SERVICE_HOST"):
        return "production"
    elif os.getenv("DOCKER_ENV"):
        return "development"
    else:
        return "single"
