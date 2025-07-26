# PostgreSQL High Availability - Client Integration Guide

This document provides examples and best practices for integrating your Hokm game application with the PostgreSQL High Availability setup.

## Connection Configuration

### 1. Database Connection Strings

The HA setup provides multiple connection endpoints:

```python
# Primary connection strings
DATABASE_CONFIGS = {
    # Main write connection (through HAProxy)
    'primary': {
        'host': 'haproxy',
        'port': 5432,
        'database': 'hokm_game',
        'user': 'hokm_app',
        'password': 'your_password'
    },
    
    # Read replica connection (through HAProxy)
    'read_replica': {
        'host': 'haproxy',
        'port': 5433,
        'database': 'hokm_game',
        'user': 'hokm_read',
        'password': 'your_password'
    },
    
    # Connection pooling (through PgBouncer)
    'pooled': {
        'host': 'pgbouncer',
        'port': 6432,
        'database': 'hokm_primary',
        'user': 'hokm_app',
        'password': 'your_password'
    },
    
    # Direct connections (failover scenarios)
    'direct_primary': {
        'host': 'postgresql-primary',
        'port': 5432,
        'database': 'hokm_game',
        'user': 'hokm_app',
        'password': 'your_password'
    },
    
    'direct_replica1': {
        'host': 'postgresql-replica1',
        'port': 5432,
        'database': 'hokm_game',
        'user': 'hokm_read',
        'password': 'your_password'
    }
}
```

### 2. Connection with Failover Support

```python
import psycopg2
import time
import logging
from typing import Optional

class HADatabaseConnection:
    def __init__(self, configs: dict):
        self.configs = configs
        self.logger = logging.getLogger(__name__)
        self.primary_conn = None
        self.read_conn = None
        
    def get_write_connection(self) -> psycopg2.connection:
        """Get connection for write operations with failover"""
        connection_attempts = [
            ('pooled', self.configs['pooled']),
            ('primary', self.configs['primary']),
            ('direct_primary', self.configs['direct_primary'])
        ]
        
        for attempt_name, config in connection_attempts:
            try:
                conn = psycopg2.connect(
                    host=config['host'],
                    port=config['port'],
                    database=config['database'],
                    user=config['user'],
                    password=config['password'],
                    connect_timeout=5,
                    application_name='hokm_game'
                )
                
                # Test connection
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    
                self.logger.info(f"Write connection established via {attempt_name}")
                return conn
                
            except Exception as e:
                self.logger.warning(f"Failed to connect via {attempt_name}: {e}")
                continue
                
        raise Exception("Failed to establish write connection to any database")
    
    def get_read_connection(self) -> psycopg2.connection:
        """Get connection for read operations with failover"""
        connection_attempts = [
            ('read_replica', self.configs['read_replica']),
            ('direct_replica1', self.configs['direct_replica1']),
            ('primary', self.configs['primary'])  # Fallback to primary
        ]
        
        for attempt_name, config in connection_attempts:
            try:
                conn = psycopg2.connect(
                    host=config['host'],
                    port=config['port'],
                    database=config['database'],
                    user=config.get('user', 'hokm_read'),
                    password=config['password'],
                    connect_timeout=3,
                    application_name='hokm_game_read'
                )
                
                # Test connection
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    
                self.logger.info(f"Read connection established via {attempt_name}")
                return conn
                
            except Exception as e:
                self.logger.warning(f"Failed to connect via {attempt_name}: {e}")
                continue
                
        raise Exception("Failed to establish read connection to any database")

# Usage example
db_manager = HADatabaseConnection(DATABASE_CONFIGS)

# For write operations
try:
    write_conn = db_manager.get_write_connection()
    with write_conn.cursor() as cur:
        cur.execute("INSERT INTO game_sessions (player_id, session_data) VALUES (%s, %s)", 
                   (player_id, session_data))
    write_conn.commit()
except Exception as e:
    logging.error(f"Write operation failed: {e}")

# For read operations
try:
    read_conn = db_manager.get_read_connection()
    with read_conn.cursor() as cur:
        cur.execute("SELECT * FROM game_leaderboard ORDER BY score DESC LIMIT 10")
        results = cur.fetchall()
except Exception as e:
    logging.error(f"Read operation failed: {e}")
```

### 3. SQLAlchemy Integration

```python
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

class HASQLAlchemyManager:
    def __init__(self, configs: dict):
        self.configs = configs
        self.write_engine = None
        self.read_engine = None
        self.setup_engines()
        
    def setup_engines(self):
        # Write engine with connection pooling
        write_url = self.build_url(self.configs['pooled'])
        self.write_engine = create_engine(
            write_url,
            poolclass=QueuePool,
            pool_size=20,
            max_overflow=30,
            pool_timeout=30,
            pool_recycle=3600,
            pool_pre_ping=True,
            echo=False
        )
        
        # Read engine for replicas
        read_url = self.build_url(self.configs['read_replica'])
        self.read_engine = create_engine(
            read_url,
            poolclass=QueuePool,
            pool_size=15,
            max_overflow=20,
            pool_timeout=10,
            pool_recycle=3600,
            pool_pre_ping=True,
            echo=False
        )
        
        # Add event listeners for connection management
        self.setup_event_listeners()
    
    def build_url(self, config: dict) -> str:
        return f"postgresql://{config['user']}:{config['password']}@{config['host']}:{config['port']}/{config['database']}"
    
    def setup_event_listeners(self):
        @event.listens_for(self.write_engine, "connect")
        def set_write_connection_properties(dbapi_connection, connection_record):
            with dbapi_connection.cursor() as cursor:
                cursor.execute("SET application_name = 'hokm_game_write'")
                cursor.execute("SET statement_timeout = '30s'")
        
        @event.listens_for(self.read_engine, "connect")
        def set_read_connection_properties(dbapi_connection, connection_record):
            with dbapi_connection.cursor() as cursor:
                cursor.execute("SET application_name = 'hokm_game_read'")
                cursor.execute("SET default_transaction_isolation = 'read committed'")
                cursor.execute("SET statement_timeout = '10s'")
    
    def get_write_session(self):
        Session = sessionmaker(bind=self.write_engine)
        return Session()
    
    def get_read_session(self):
        Session = sessionmaker(bind=self.read_engine)
        return Session()

# Usage
ha_db = HASQLAlchemyManager(DATABASE_CONFIGS)

# Write operations
with ha_db.get_write_session() as session:
    new_game = GameSession(player_id=123, game_type='hokm')
    session.add(new_game)
    session.commit()

# Read operations
with ha_db.get_read_session() as session:
    leaderboard = session.query(Player).order_by(Player.score.desc()).limit(10).all()
```

### 4. Redis Integration for Session Management

```python
import redis
import json
from typing import Optional

class HASessionManager:
    def __init__(self, redis_config: dict, db_manager: HADatabaseConnection):
        self.redis_client = redis.Redis(**redis_config)
        self.db_manager = db_manager
        
    def get_session(self, session_id: str) -> Optional[dict]:
        """Get session data from Redis first, fallback to database"""
        try:
            # Try Redis first (fastest)
            session_data = self.redis_client.get(f"session:{session_id}")
            if session_data:
                return json.loads(session_data)
        except Exception as e:
            logging.warning(f"Redis session lookup failed: {e}")
        
        # Fallback to database
        try:
            conn = self.db_manager.get_read_connection()
            with conn.cursor() as cur:
                cur.execute("SELECT session_data FROM game_sessions WHERE session_id = %s", 
                           (session_id,))
                result = cur.fetchone()
                if result:
                    session_data = result[0]
                    # Cache in Redis for future use
                    self.redis_client.setex(f"session:{session_id}", 3600, 
                                          json.dumps(session_data))
                    return session_data
        except Exception as e:
            logging.error(f"Database session lookup failed: {e}")
        
        return None
    
    def save_session(self, session_id: str, session_data: dict):
        """Save session to both Redis and database"""
        try:
            # Save to Redis
            self.redis_client.setex(f"session:{session_id}", 3600, 
                                  json.dumps(session_data))
            
            # Save to database
            conn = self.db_manager.get_write_connection()
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO game_sessions (session_id, session_data, updated_at) 
                    VALUES (%s, %s, NOW()) 
                    ON CONFLICT (session_id) 
                    DO UPDATE SET session_data = EXCLUDED.session_data, 
                                  updated_at = NOW()
                """, (session_id, json.dumps(session_data)))
            conn.commit()
            
        except Exception as e:
            logging.error(f"Failed to save session: {e}")
            raise
```

### 5. Health Check Integration

```python
class HAHealthChecker:
    def __init__(self, db_manager: HADatabaseConnection):
        self.db_manager = db_manager
        
    def check_database_health(self) -> dict:
        """Check health of all database components"""
        health_status = {
            'timestamp': time.time(),
            'primary': False,
            'replicas': [],
            'overall_status': 'unhealthy'
        }
        
        # Check primary
        try:
            conn = self.db_manager.get_write_connection()
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                health_status['primary'] = True
        except Exception as e:
            logging.error(f"Primary health check failed: {e}")
        
        # Check replicas
        for replica_name in ['direct_replica1', 'direct_replica2']:
            try:
                config = self.db_manager.configs[replica_name]
                conn = psycopg2.connect(**config, connect_timeout=3)
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                health_status['replicas'].append({
                    'name': replica_name,
                    'status': 'healthy'
                })
            except Exception as e:
                health_status['replicas'].append({
                    'name': replica_name,
                    'status': 'unhealthy',
                    'error': str(e)
                })
        
        # Overall status
        if health_status['primary'] or len([r for r in health_status['replicas'] if r['status'] == 'healthy']) > 0:
            health_status['overall_status'] = 'healthy'
        
        return health_status

# Integration with FastAPI health endpoint
from fastapi import FastAPI

app = FastAPI()
health_checker = HAHealthChecker(db_manager)

@app.get("/health/database")
async def database_health():
    return health_checker.check_database_health()
```

### 6. Environment Variables Configuration

```bash
# .env file for Hokm game
# PostgreSQL HA Configuration

# Primary database settings
DB_PRIMARY_HOST=haproxy
DB_PRIMARY_PORT=5432
DB_PRIMARY_NAME=hokm_game
DB_PRIMARY_USER=hokm_app
DB_PRIMARY_PASSWORD=your_secure_password

# Read replica settings
DB_READ_HOST=haproxy
DB_READ_PORT=5433
DB_READ_USER=hokm_read
DB_READ_PASSWORD=your_secure_password

# Connection pooling
DB_POOL_HOST=pgbouncer
DB_POOL_PORT=6432
DB_POOL_DATABASE=hokm_primary

# Failover settings
DB_DIRECT_PRIMARY_HOST=postgresql-primary
DB_DIRECT_REPLICA1_HOST=postgresql-replica1
DB_DIRECT_REPLICA2_HOST=postgresql-replica2

# Connection pool settings
DB_POOL_SIZE=20
DB_MAX_OVERFLOW=30
DB_POOL_TIMEOUT=30
DB_POOL_RECYCLE=3600

# Redis settings for session management
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=your_redis_password
REDIS_DB=0

# Health check settings
HEALTH_CHECK_INTERVAL=30
HEALTH_CHECK_TIMEOUT=5
```

### 7. Monitoring Integration

```python
import time
import logging
from prometheus_client import Counter, Histogram, Gauge

# Metrics for monitoring
DB_OPERATIONS_TOTAL = Counter('db_operations_total', 'Total database operations', ['operation_type', 'status'])
DB_OPERATION_DURATION = Histogram('db_operation_duration_seconds', 'Database operation duration')
DB_CONNECTIONS_ACTIVE = Gauge('db_connections_active', 'Active database connections', ['connection_type'])

class MonitoredDatabaseManager:
    def __init__(self, ha_manager: HADatabaseConnection):
        self.ha_manager = ha_manager
        
    def execute_write(self, query: str, params: tuple = None):
        start_time = time.time()
        try:
            conn = self.ha_manager.get_write_connection()
            with conn.cursor() as cur:
                cur.execute(query, params)
            conn.commit()
            
            # Record metrics
            DB_OPERATIONS_TOTAL.labels(operation_type='write', status='success').inc()
            DB_OPERATION_DURATION.observe(time.time() - start_time)
            
        except Exception as e:
            DB_OPERATIONS_TOTAL.labels(operation_type='write', status='error').inc()
            logging.error(f"Write operation failed: {e}")
            raise
    
    def execute_read(self, query: str, params: tuple = None):
        start_time = time.time()
        try:
            conn = self.ha_manager.get_read_connection()
            with conn.cursor() as cur:
                cur.execute(query, params)
                result = cur.fetchall()
            
            # Record metrics
            DB_OPERATIONS_TOTAL.labels(operation_type='read', status='success').inc()
            DB_OPERATION_DURATION.observe(time.time() - start_time)
            
            return result
            
        except Exception as e:
            DB_OPERATIONS_TOTAL.labels(operation_type='read', status='error').inc()
            logging.error(f"Read operation failed: {e}")
            raise
```

## Best Practices

1. **Connection Management**:
   - Always use connection pooling
   - Implement proper connection timeout handling
   - Use read replicas for read-heavy operations

2. **Error Handling**:
   - Implement retry logic with exponential backoff
   - Have fallback mechanisms for database failures
   - Monitor and log all database errors

3. **Performance Optimization**:
   - Use prepared statements when possible
   - Implement proper indexing strategies
   - Monitor query performance regularly

4. **Security**:
   - Use strong passwords and rotate them regularly
   - Implement proper access controls
   - Enable SSL/TLS for all connections

5. **Monitoring**:
   - Track all database operations
   - Monitor connection pool usage
   - Set up alerts for critical failures

This integration guide provides a complete framework for connecting your Hokm game application to the PostgreSQL HA setup with proper failover handling, performance optimization, and monitoring.
