# PostgreSQL Integration for Hokm Game Server

This document provides comprehensive information about the PostgreSQL database integration for the Hokm card game server, including setup, configuration, and usage.

## 🏗️ Architecture Overview

The PostgreSQL integration provides a robust, scalable database solution for the Hokm game server with the following components:

### Database Architecture
```
Load Balancer (HAProxy/NGINX)
        ↓
    Game Servers (Multiple Instances)
        ↓
    pgBouncer (Connection Pooling)
        ↓
PostgreSQL Primary ←→ PostgreSQL Read Replica
        ↓
    Redis (Session Cache)
```

### Key Features
- **PostgreSQL 15** with gaming-optimized configuration
- **Connection Pooling** via pgBouncer for high concurrency
- **Read Replica** for analytics and reporting queries
- **Redis Integration** for session caching and fast lookups
- **Circuit Breaker Pattern** for database resilience
- **Comprehensive Monitoring** with Prometheus and Grafana
- **Automated Backups** with retention policies
- **Analytics Views** for game insights and reporting

## 🚀 Quick Start

### 1. Initial Setup
```bash
# Clone the repository and navigate to project directory
cd DS_project

# Run the setup script
./setup-postgresql.sh

# Review and update environment variables
cp .env.example .env
# Edit .env file with your desired settings
```

### 2. Start Services
```bash
# Start all services
docker-compose up -d

# Check service status
docker-compose ps

# View logs
docker-compose logs -f postgres-primary
```

### 3. Verify Installation
```bash
# Install Python dependencies
pip install -r requirements-postgresql.txt

# Run comprehensive test suite
python test_postgresql_integration.py
```

## 📊 Database Schema

### Core Tables

#### `players`
Stores player information and statistics.
```sql
- id (UUID, Primary Key)
- username (VARCHAR, Unique)
- email (VARCHAR, Unique, Optional)
- password_hash (VARCHAR, Optional)
- created_at, updated_at, last_seen (TIMESTAMP)
- total_games, wins, losses, rating (INTEGER)
```

#### `game_sessions`
Manages game sessions and room data.
```sql
- id (UUID, Primary Key)
- room_id (VARCHAR, Unique)
- session_key (VARCHAR, Unique)
- status (VARCHAR: waiting, active, completed, abandoned)
- game_state (JSONB) - Flexible game state storage
- scores (JSONB) - Team scores
- created_at, started_at, completed_at (TIMESTAMP)
```

#### `game_participants`
Links players to game sessions.
```sql
- id (UUID, Primary Key)
- game_session_id (UUID, FK)
- player_id (UUID, FK)
- position (INTEGER: 0-3)
- team (INTEGER: 1-2)
- is_connected (BOOLEAN)
```

#### `game_moves`
Records all game actions for audit and replay.
```sql
- id (UUID, Primary Key)
- game_session_id (UUID, FK)
- player_id (UUID, FK)
- move_type (VARCHAR: play_card, choose_trump, etc.)
- move_data (JSONB)
- sequence_number (INTEGER)
```

#### `websocket_connections`
Tracks WebSocket connections for session management.
```sql
- id (UUID, Primary Key)
- player_id (UUID, FK)
- connection_id (VARCHAR, Unique)
- connected_at, last_ping, disconnected_at (TIMESTAMP)
- is_active (BOOLEAN)
```

### Analytics Views

#### `analytics.player_performance`
Player statistics and performance metrics.

#### `analytics.game_statistics_summary`
Daily game statistics and trends.

#### `analytics.active_sessions`
Currently active game sessions.

#### `analytics.leaderboard`
Top players ranking by rating.

## ⚙️ Configuration

### Environment Variables

Key environment variables for configuration:

```bash
# Database Configuration
DATABASE_URL=postgresql://user:password@localhost:6432/hokm_game
DATABASE_READ_URL=postgresql://user:password@localhost:5433/hokm_game
REDIS_URL=redis://:password@localhost:6379/0

# Performance Settings
POSTGRES_MAX_CONNECTIONS=200
POSTGRES_SHARED_BUFFERS=256MB
POSTGRES_WORK_MEM=4MB

# Connection Pooling
PGBOUNCER_POOL_MODE=transaction
PGBOUNCER_DEFAULT_POOL_SIZE=25
PGBOUNCER_MAX_CLIENT_CONN=100
```

### Gaming-Optimized PostgreSQL Settings

The database is configured with gaming-specific optimizations:

- **Memory Settings**: Optimized for high-concurrency gaming workloads
- **Checkpoint Settings**: Frequent checkpoints for write-heavy operations
- **Connection Pooling**: pgBouncer for efficient connection management
- **WAL Configuration**: Optimized write-ahead logging for durability
- **Lock Management**: Higher lock limits for complex game transactions

## 🔧 Usage

### Database Integration in Python

```python
from backend.game_database_integration import create_database_integration

# Initialize database integration
db_integration = await create_database_integration()

# Create or get player
player = await db_integration.create_or_get_player(
    username="player1",
    connection_info={"ip_address": "127.0.0.1"}
)

# Create game session
session = await db_integration.create_game_session(
    room_id="room123",
    session_key="session_key_123"
)

# Add player to game
await db_integration.add_player_to_session(
    room_id="room123",
    player_id=player["id"],
    position=0,
    team=1,
    connection_id="conn123"
)

# Update game state
await db_integration.update_game_state_from_game_board(
    room_id="room123",
    game_board=game_board_instance
)

# Record player move
await db_integration.record_player_move(
    room_id="room123",
    player_id=player["id"],
    move_type="play_card",
    move_data={"card": {"suit": "hearts", "rank": "A"}},
    round_number=1
)
```

### Database Manager Direct Usage

```python
from backend.database_manager import DatabaseManager

# Initialize database manager
db_manager = DatabaseManager(
    primary_dsn="postgresql://...",
    replica_dsn="postgresql://...",
    redis_url="redis://..."
)

await db_manager.initialize()

# Execute queries
result = await db_manager.execute_query(
    "SELECT * FROM players WHERE username = $1",
    "player1"
)

# Execute commands
await db_manager.execute_command(
    "UPDATE players SET last_seen = NOW() WHERE id = $1",
    player_id
)

# Use transactions
operations = [
    ("INSERT INTO players (username) VALUES ($1)", ("new_player",)),
    ("UPDATE game_sessions SET status = 'active' WHERE id = $1", (session_id,))
]
await db_manager.execute_in_transaction(operations)
```

## 📈 Monitoring and Analytics

### Prometheus Metrics

The system exports comprehensive metrics:
- Database connection pool status
- Query performance metrics
- Circuit breaker states
- Game session statistics
- Player activity metrics

### Grafana Dashboards

Pre-configured dashboards for:
- Database performance monitoring
- Game server metrics
- Player activity analysis
- System health overview

### Analytics Queries

Example analytics queries:

```sql
-- Top players by rating
SELECT * FROM analytics.leaderboard LIMIT 10;

-- Daily game statistics
SELECT * FROM analytics.game_statistics_summary 
ORDER BY game_date DESC LIMIT 7;

-- Active sessions
SELECT * FROM analytics.active_sessions;

-- Player activity heatmap
SELECT * FROM analytics.player_activity_heatmap;
```

## 🔒 Security Features

### Authentication and Authorization
- Role-based database access (admin, application, readonly)
- Secure password storage with bcrypt
- JWT tokens for session management
- Audit logging for sensitive operations

### Data Protection
- Encrypted connections (SSL/TLS in production)
- Input validation and SQL injection prevention
- Rate limiting for API endpoints
- Data retention policies

### Network Security
- Firewall rules for database access
- VPC/network isolation in production
- Connection pooling for DoS protection

## 🔄 Backup and Recovery

### Automated Backups
- Daily automated backups via Docker container
- Configurable retention periods
- Compressed backup storage
- Backup verification and monitoring

### Manual Backup
```bash
# Create manual backup
docker-compose exec postgres-primary pg_dump -U hokm_admin hokm_game > backup.sql

# Restore from backup
docker-compose exec -T postgres-primary psql -U hokm_admin hokm_game < backup.sql
```

### Point-in-Time Recovery
- WAL archiving for point-in-time recovery
- Streaming replication for high availability
- Automated failover capabilities

## 🎯 Performance Optimization

### Database Optimization
- Comprehensive indexing strategy
- Query optimization and monitoring
- Connection pooling with pgBouncer
- Read replica for analytics queries

### Application Optimization
- Circuit breaker pattern for resilience
- Caching layer with Redis
- Async database operations
- Connection pooling and reuse

### Monitoring and Tuning
- Performance metrics collection
- Slow query identification
- Resource usage monitoring
- Automatic performance alerts

## 🧪 Testing

### Test Suite
Comprehensive test suite covering:
- Database connectivity
- CRUD operations
- Concurrent access
- Circuit breaker functionality
- Performance monitoring
- Data integrity

### Running Tests
```bash
# Run full test suite
python test_postgresql_integration.py

# Run specific game server tests
python test_basic_game.py
python test_stress.py

# Run database-specific tests
pytest tests/test_database_integration.py -v
```

## 🚀 Deployment

### Development Environment
```bash
docker-compose up -d
```

### Production Environment
```bash
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

### Kubernetes Deployment
```bash
kubectl apply -f k8s-postgresql-deployment.yml
```

## 🔧 Troubleshooting

### Common Issues

#### Connection Issues
```bash
# Check service status
docker-compose ps

# Check logs
docker-compose logs postgres-primary

# Test connectivity
docker-compose exec postgres-primary pg_isready -U hokm_admin
```

#### Performance Issues
```bash
# Check active connections
docker-compose exec postgres-primary psql -U hokm_admin -d hokm_game -c "SELECT * FROM pg_stat_activity;"

# Check slow queries
docker-compose exec postgres-primary psql -U hokm_admin -d hokm_game -c "SELECT * FROM pg_stat_statements ORDER BY total_time DESC LIMIT 10;"
```

#### Data Issues
```bash
# Check database size
docker-compose exec postgres-primary psql -U hokm_admin -d hokm_game -c "SELECT pg_size_pretty(pg_database_size('hokm_game'));"

# Vacuum and analyze
docker-compose exec postgres-primary psql -U hokm_admin -d hokm_game -c "VACUUM ANALYZE;"
```

### Health Checks

The system provides comprehensive health checks:
- Database connectivity
- Circuit breaker status
- Connection pool status
- Redis connectivity
- Performance metrics

## 📚 Additional Resources

### Documentation
- [PostgreSQL 15 Documentation](https://www.postgresql.org/docs/15/)
- [pgBouncer Documentation](https://www.pgbouncer.org/usage.html)
- [asyncpg Documentation](https://magicstack.github.io/asyncpg/)

### Monitoring Tools
- Grafana: `http://localhost:3000` (admin/admin_secure_2024!)
- pgAdmin: `http://localhost:5050` (admin@hokm.local/admin_secure_2024!)
- Prometheus: `http://localhost:9090`

### Support
For issues and questions:
1. Check the troubleshooting section
2. Review Docker logs: `docker-compose logs`
3. Run the test suite: `python test_postgresql_integration.py`
4. Check system resources and connectivity

## 🎉 Success Metrics

Your PostgreSQL integration is successful when:
- ✅ All tests pass (90%+ success rate)
- ✅ Database connections are stable
- ✅ Game sessions persist correctly
- ✅ Performance metrics are healthy
- ✅ Backups are working
- ✅ Monitoring is operational

This PostgreSQL integration provides a robust, scalable foundation for your Hokm game server with enterprise-grade features for production deployment.
