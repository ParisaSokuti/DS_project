# SQLAlchemy 2.0 Async Integration Quick Start Guide

This guide will help you get started with the comprehensive SQLAlchemy 2.0 async integration for your Hokm game server.

## 🚀 Quick Start

### 1. Environment Setup

First, copy the environment configuration:

```bash
cp .env.database.example .env
```

Edit `.env` with your database credentials:

```bash
# Basic database connection
DATABASE_HOST=localhost
DATABASE_PORT=5432
DATABASE_NAME=hokm_game
DATABASE_USER=hokm_app
DATABASE_PASSWORD=your_secure_password

# Environment
DATABASE_ENVIRONMENT=development
```

### 2. Install Dependencies

Make sure you have all required dependencies:

```bash
pip install -r requirements-postgresql.txt
```

Required packages:
- `asyncpg` - Async PostgreSQL driver
- `sqlalchemy[asyncio]>=2.0.0` - SQLAlchemy 2.0 with async support
- `psycopg2-binary` - PostgreSQL adapter

### 3. Database Schema Setup

Apply the database schema:

```bash
# Create database and apply schema
psql -U postgres -c "CREATE DATABASE hokm_game;"
psql -U postgres -d hokm_game -f database_schema.sql
```

### 4. Test the Integration

Run the comprehensive test suite:

```bash
python test_comprehensive_async_integration.py
```

Expected output:
```
🚀 Starting SQLAlchemy 2.0 Async Database Integration Tests...
✅ PASSED: Create new player Alice
✅ PASSED: Game room creation
✅ PASSED: All players joined successfully
📊 Total Tests: 25+
✅ Success Rate: 90%+
```

## 📋 Integration Overview

### Core Components

1. **Database Configuration** (`backend/database/config.py`)
   - Environment-based configuration
   - Connection pooling settings
   - SSL/TLS support

2. **Session Manager** (`backend/database/session_manager.py`)
   - Async session management
   - Connection pooling with circuit breaker
   - Transaction context managers
   - Health monitoring

3. **ORM Models** (`backend/database/models.py`)
   - SQLAlchemy 2.0 async models
   - Gaming-optimized relationships
   - Comprehensive constraints and indexes

4. **CRUD Operations** (`backend/database/crud.py`)
   - Async CRUD for all entities
   - Optimized queries for gaming workloads
   - Proper error handling

5. **Integration Layer** (`backend/database/integration.py`)
   - High-level game operations
   - Transaction-safe multi-step operations
   - WebSocket connection management

## 🎮 Using the Integration in Your Server

### Basic Usage Pattern

```python
from backend.database import get_session_manager, game_integration

# Initialize in your server startup
async def init_server():
    session_manager = await get_session_manager()
    health = await session_manager.health_check()
    print(f"Database health: {health}")

# Use in your WebSocket handlers
async def handle_player_join(websocket, data):
    # Create or get player
    player, is_new = await game_integration.create_player_if_not_exists(
        username=data['username'],
        email=data.get('email')
    )
    
    # Join game room
    game, participant = await game_integration.join_game_room(
        room_id=data['room_code'],
        username=data['username'],
        connection_id=connection_id,
        ip_address=websocket.remote_address[0]
    )
    
    # Send response
    await websocket.send(json.dumps({
        'type': 'join_success',
        'player_id': str(player.id),
        'position': participant.position,
        'team': participant.team
    }))
```

### Enhanced Server Integration

Use the enhanced server that combines Redis and PostgreSQL:

```python
from enhanced_server_integration import EnhancedHokmGameServer

async def main():
    server = EnhancedHokmGameServer()
    await server.initialize()
    
    # Start WebSocket server
    async with websockets.serve(server.handle_connection, "localhost", 8765):
        print("Enhanced server running with dual storage (Redis + PostgreSQL)")
        await asyncio.Future()  # Run forever

if __name__ == "__main__":
    asyncio.run(main())
```

## 🔧 Key Features

### 1. Connection Pooling
- Configurable pool size (default: 20 connections)
- Overflow handling (default: +30 connections)
- Connection health monitoring
- Automatic connection recycling

### 2. Transaction Management
```python
# Automatic transaction handling
async def complex_game_operation():
    # This automatically handles transactions
    await game_integration.complete_game(
        room_id="ROOM123",
        winner_data={'winners': ['Alice', 'Bob']},
        final_scores={'Alice': 150, 'Bob': 150, 'Charlie': 100, 'Diana': 100},
        game_duration=3600.0
    )
    # Transaction automatically committed or rolled back on error
```

### 3. Real-time WebSocket Support
```python
# Track WebSocket connections in database
connection = await game_integration.register_websocket_connection(
    connection_id="conn_12345",
    username="Alice",
    room_id="ROOM123",
    ip_address="192.168.1.100",
    user_agent="GameClient/1.0"
)

# Update connection status
await game_integration.update_websocket_connection(
    connection_id="conn_12345",
    status='reconnected'
)
```

### 4. Game State Persistence
```python
# Update game state
await game_integration.update_game_state(
    room_id="ROOM123",
    game_phase='hokm_selection',
    current_turn=2,
    additional_data={
        'hakem': 'Alice',
        'hokm': 'hearts',
        'round': 3
    }
)

# Get comprehensive game state
game_state = await game_integration.get_game_state("ROOM123")
```

### 5. Player Statistics
```python
# Get player statistics
stats = await game_integration.get_player_statistics("Alice")
print(f"Win rate: {stats['win_rate']:.1f}%")
print(f"Total games: {stats['total_games']}")
print(f"Rating: {stats['rating']}")
```

## 🏗️ Architecture Benefits

### Dual Storage Strategy
- **Redis**: Fast session management, real-time game state
- **PostgreSQL**: Persistent player data, game history, analytics

### Async Performance
- Non-blocking database operations
- Connection pooling for high concurrency
- Optimized for WebSocket workloads

### Production Ready
- Circuit breaker pattern for resilience
- Comprehensive error handling
- Health monitoring and metrics
- Transaction safety

### Scalability
- Horizontal scaling support
- Read replica configuration
- Connection pooling optimization
- Query optimization for gaming workloads

## 📊 Monitoring & Health Checks

### Database Health
```python
health = await session_manager.health_check()
print(health)
# {
#   'status': 'healthy',
#   'response_time': 0.05,
#   'pool_stats': {'active': 5, 'idle': 15}
# }
```

### Connection Pool Stats
```python
stats = await session_manager.get_pool_stats()
print(stats)
# {
#   'pool_size': 20,
#   'checked_out': 3,
#   'overflow': 0,
#   'invalid': 0
# }
```

## 🛠️ Configuration Options

### Development Environment
```bash
DATABASE_ENVIRONMENT=development
DATABASE_ECHO_SQL=true
DATABASE_POOL_SIZE=10
```

### Production Environment
```bash
DATABASE_ENVIRONMENT=production
DATABASE_ECHO_SQL=false
DATABASE_POOL_SIZE=25
DATABASE_MAX_OVERFLOW=50
DATABASE_SSL_MODE=require
```

### Testing Environment
```bash
DATABASE_ENVIRONMENT=test
DATABASE_NAME=hokm_game_test
DATABASE_POOL_SIZE=5
```

## 🔍 Common Operations

### Create a Complete Game Flow
```python
# 1. Create players
players = []
for username in ['Alice', 'Bob', 'Charlie', 'Diana']:
    player, _ = await game_integration.create_player_if_not_exists(username)
    players.append(player)

# 2. Create game room
game = await game_integration.create_game_room(
    room_id="GAME123",
    creator_username="Alice",
    game_type="hokm"
)

# 3. Join all players
for player in players:
    await game_integration.join_game_room(
        room_id="GAME123",
        username=player.username,
        connection_id=f"conn_{player.username}"
    )

# 4. Record game moves
await game_integration.record_game_move(
    room_id="GAME123",
    username="Alice",
    move_type="play_card",
    move_data={'card': 'AS', 'suit': 'spades'}
)

# 5. Complete game
await game_integration.complete_game(
    room_id="GAME123",
    winner_data={'winners': ['Alice', 'Charlie'], 'team': 1},
    final_scores={'Alice': 150, 'Bob': 100, 'Charlie': 150, 'Diana': 100},
    game_duration=1800.0
)
```

## 🚨 Error Handling

### Transaction Rollback
```python
try:
    async with get_db_transaction() as session:
        # Multiple operations here
        await game_session_crud.create_game(session, ...)
        await game_participant_crud.add_participant(session, ...)
        # If any operation fails, entire transaction rolls back
except Exception as e:
    logger.error(f"Transaction failed: {e}")
    # Transaction automatically rolled back
```

### Circuit Breaker
```python
# Circuit breaker automatically handles database failures
# Falls back to Redis-only mode when database is unavailable
try:
    result = await game_integration.some_database_operation()
except CircuitBreakerOpen:
    # Handle fallback to Redis-only mode
    result = await redis_fallback_operation()
```

## 📈 Performance Tips

1. **Use Connection Pooling**: Configured automatically
2. **Batch Operations**: Use transaction context managers
3. **Query Optimization**: Leverage built-in optimized queries
4. **Async Everywhere**: All operations are async-ready
5. **Monitor Pool Health**: Regular health checks included

## 🎯 Next Steps

1. **Run the Tests**: Verify everything works
2. **Integrate with Your Server**: Use the enhanced server example
3. **Configure Production**: Update environment variables
4. **Monitor Performance**: Use built-in health checks
5. **Scale Up**: Add read replicas and horizontal scaling

Your SQLAlchemy 2.0 async integration is now production-ready for your Hokm game server! 🎉
