# Hybrid Data Architecture - Usage Guide

## 🎯 Overview

This guide demonstrates how to use the comprehensive hybrid data architecture implemented for the Hokm game server. The architecture combines Redis for low-latency real-time operations with PostgreSQL for reliable persistent storage.

## 📁 Architecture Components

### Core Files
- **`HYBRID_DATA_ARCHITECTURE_STRATEGY.md`** - Complete architectural strategy and patterns
- **`backend/hybrid_data_layer.py`** - Main unified data access layer
- **`backend/redis_game_state.py`** - Redis-based real-time game state manager
- **`backend/postgresql_persistence.py`** - PostgreSQL persistence and analytics
- **`backend/data_synchronization.py`** - Cross-database synchronization manager
- **`examples/hybrid_integration_example.py`** - Integration demonstration

### Supporting Components
- **`backend/database/session_manager.py`** - PostgreSQL session management with circuit breakers
- **`backend/circuit_breaker.py`** - Circuit breaker for Redis
- **`backend/database/postgresql_circuit_breaker.py`** - Circuit breaker for PostgreSQL

## 🚀 Quick Start

### 1. Initialize the Hybrid Data Layer

```python
from backend.hybrid_data_layer import HybridDataLayer, HybridDataConfig

# Configure the hybrid layer
config = HybridDataConfig(
    redis_url="redis://localhost:6379",
    redis_prefix="hokm:",
    redis_default_ttl=3600,
    enable_write_through=True,
    enable_write_behind=True
)

# Initialize
hybrid_data = HybridDataLayer(config)
await hybrid_data.initialize()
```

### 2. Basic Data Operations

```python
# Create a game session (stored in both Redis and PostgreSQL)
game_data = {
    'room_code': 'ROOM_001',
    'players': ['alice', 'bob', 'charlie', 'david'],
    'phase': 'waiting_for_players'
}

await hybrid_data.create_game_session('ROOM_001', game_data)

# Get game session (tries Redis first, falls back to PostgreSQL)
session = await hybrid_data.get_game_session('ROOM_001')

# Update game session (immediate Redis, queued PostgreSQL)
session['phase'] = 'playing'
await hybrid_data.update_game_session('ROOM_001', session)
```

### 3. Transaction Patterns

#### Write-Through (High Consistency)
```python
from backend.data_synchronization import TransactionType

# For critical operations that require immediate consistency
async with hybrid_data.sync_manager.hybrid_transaction(
    TransactionType.HYBRID_WRITE_THROUGH
) as tx:
    # Both Redis and PostgreSQL updated immediately
    await hybrid_data.create_game_session(room_code, critical_data)
```

#### Write-Behind (High Performance)
```python
# For non-critical operations prioritizing speed
async with hybrid_data.sync_manager.hybrid_transaction(
    TransactionType.HYBRID_WRITE_BEHIND
) as tx:
    # Redis updated immediately, PostgreSQL queued for later
    await hybrid_data.update_player_stats(player_id, stats)
```

#### Eventual Consistency
```python
# For operations where slight delay is acceptable
async with hybrid_data.sync_manager.hybrid_transaction(
    TransactionType.HYBRID_EVENTUAL
) as tx:
    # Primary layer updated, secondary synced eventually
    await hybrid_data.log_player_action(player_id, action)
```

## 🎮 Game-Specific Usage Patterns

### 1. Real-Time Game Operations

```python
# Player joins game - immediate Redis update
await hybrid_data.redis_manager.add_player_to_game(
    room_code='ROOM_001',
    player_data={
        'player_id': 'player_123',
        'username': 'alice',
        'joined_at': datetime.utcnow()
    }
)

# Get live game state for WebSocket updates
game_state = await hybrid_data.redis_manager.get_live_game_state('ROOM_001')
```

### 2. Move Processing

```python
# Process a card play with atomic Redis operations
move_result = await hybrid_data.redis_manager.execute_player_move(
    room_code='ROOM_001',
    player_id='player_123',
    move_data={'card': 'ace_of_spades', 'position': 1}
)

# Log move to PostgreSQL asynchronously
await hybrid_data.sync_manager.queue_sync_task(
    operation=SyncOperation.CREATE,
    priority=SyncPriority.MEDIUM,
    source_layer="redis",
    target_layer="postgresql",
    data_type="game_move",
    data_key=f"ROOM_001:player_123",
    data_payload=move_result
)
```

### 3. Game Completion

```python
# Complete game with full persistence
async with hybrid_data.sync_manager.hybrid_transaction(
    TransactionType.HYBRID_WRITE_THROUGH
) as tx:
    
    # Update final game state
    final_state = await hybrid_data.complete_game_session(
        room_code='ROOM_001',
        final_scores={'team1': 7, 'team2': 6}
    )
    
    # Update player statistics
    for player_id in final_state['players']:
        await hybrid_data.update_player_statistics(
            player_id, 
            calculate_stats_update(player_id, final_state)
        )
```

### 4. Player Reconnection

```python
# Handle reconnection with Redis cache
try:
    # Try Redis first for active games
    reconnection_data = await hybrid_data.redis_manager.get_player_reconnection_data(
        player_id='player_123',
        room_code='ROOM_001'
    )
    
    if reconnection_data:
        return reconnection_data
        
except Exception:
    # Fallback to PostgreSQL for completed games
    historical_data = await hybrid_data.postgresql_manager.get_historical_game_data(
        player_id='player_123',
        room_code='ROOM_001'
    )
    return historical_data
```

## 📊 Analytics and Reporting

### 1. Real-Time Analytics

```python
# Get current active games from Redis
active_games = await hybrid_data.redis_manager.get_active_games_stats()

# Get real-time player counts
player_counts = await hybrid_data.redis_manager.get_concurrent_player_count()
```

### 2. Historical Analytics

```python
# Generate player performance reports from PostgreSQL
player_stats = await hybrid_data.postgresql_manager.generate_player_performance_report(
    player_id='player_123',
    date_range=(start_date, end_date)
)

# Get game outcome patterns
game_patterns = await hybrid_data.postgresql_manager.analyze_game_patterns(
    filters={'game_type': '4_player', 'completed': True}
)
```

### 3. Leaderboards

```python
# Get cached leaderboard (Redis) or generate new one (PostgreSQL)
leaderboard = await hybrid_data.get_leaderboard(
    leaderboard_type='global',
    limit=50,
    cache_ttl=300  # 5 minutes
)
```

## 🔧 Configuration Options

### Redis Configuration

```python
redis_config = {
    'redis_url': 'redis://localhost:6379',
    'redis_prefix': 'hokm:',
    'redis_default_ttl': 3600,  # 1 hour
    'redis_max_connections': 50,
    'redis_retry_attempts': 3,
    'enable_redis_clustering': False
}
```

### PostgreSQL Configuration

```python
postgres_config = {
    'connection_url': 'postgresql+asyncpg://user:pass@localhost/hokm_db',
    'pool_size': 20,
    'max_overflow': 50,
    'pool_timeout': 30,
    'enable_query_logging': True,
    'enable_performance_tracking': True
}
```

### Synchronization Configuration

```python
sync_config = {
    'sync_batch_size': 100,
    'sync_interval_seconds': 30,
    'max_retry_attempts': 3,
    'retry_backoff_multiplier': 2.0,
    'dead_letter_queue_enabled': True,
    'enable_conflict_resolution': True
}
```

## ⚡ Performance Optimization

### 1. Connection Pooling

```python
# Redis connection pool
await hybrid_data.redis_manager.configure_connection_pool(
    max_connections=50,
    retry_on_timeout=True
)

# PostgreSQL connection pool
await hybrid_data.postgresql_manager.configure_connection_pool(
    pool_size=20,
    max_overflow=30
)
```

### 2. Batch Operations

```python
# Batch multiple operations for better performance
batch_operations = [
    ('update_player_stats', player_id_1, stats_1),
    ('update_player_stats', player_id_2, stats_2),
    ('log_game_event', room_code, event_data)
]

await hybrid_data.sync_manager.execute_batch_operations(batch_operations)
```

### 3. Monitoring and Metrics

```python
# Get performance metrics
metrics = await hybrid_data.get_performance_metrics()

print(f"Redis operations/sec: {metrics['redis']['ops_per_second']}")
print(f"PostgreSQL avg query time: {metrics['postgresql']['avg_query_time_ms']}ms")
print(f"Sync queue depth: {metrics['sync']['queue_depth']}")
print(f"Error rate: {metrics['overall']['error_rate']}%")
```

## 🔒 Error Handling and Recovery

### 1. Circuit Breaker Pattern

```python
from backend.circuit_breaker import CircuitBreakerConfig

# Configure circuit breakers
redis_cb_config = CircuitBreakerConfig(
    failure_threshold=5,
    timeout_seconds=30,
    recovery_attempts=3
)

postgresql_cb_config = CircuitBreakerConfig(
    failure_threshold=3,
    timeout_seconds=60,
    recovery_attempts=5
)
```

### 2. Fallback Mechanisms

```python
async def get_player_data_with_fallback(player_id: str):
    try:
        # Try Redis first
        return await hybrid_data.redis_manager.get_player_session(player_id)
    except RedisConnectionError:
        # Fallback to PostgreSQL
        return await hybrid_data.postgresql_manager.get_player_profile(player_id)
    except Exception:
        # Final fallback to local cache
        return await hybrid_data.get_cached_player_data(player_id)
```

### 3. Data Consistency Checks

```python
# Verify data consistency between Redis and PostgreSQL
inconsistencies = await hybrid_data.sync_manager.check_data_consistency(
    data_type='game_sessions',
    sample_size=100
)

if inconsistencies:
    await hybrid_data.sync_manager.resolve_inconsistencies(inconsistencies)
```

## 🧪 Testing

### 1. Unit Tests

```python
import pytest
from unittest.mock import AsyncMock

@pytest.mark.asyncio
async def test_hybrid_game_session_creation():
    hybrid_data = HybridDataLayer(test_config)
    await hybrid_data.initialize()
    
    # Test game session creation
    game_data = {'room_code': 'TEST_001', 'players': ['p1', 'p2']}
    result = await hybrid_data.create_game_session('TEST_001', game_data)
    
    assert result['room_code'] == 'TEST_001'
    assert len(result['players']) == 2
```

### 2. Integration Tests

Run the comprehensive integration example:

```bash
python examples/hybrid_integration_example.py
```

### 3. Load Testing

```python
import asyncio
import time

async def load_test_hybrid_operations():
    """Test hybrid data layer under load"""
    hybrid_data = HybridDataLayer(config)
    await hybrid_data.initialize()
    
    start_time = time.time()
    tasks = []
    
    # Create 100 concurrent operations
    for i in range(100):
        task = hybrid_data.create_game_session(f'LOAD_TEST_{i}', test_data)
        tasks.append(task)
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    success_count = sum(1 for r in results if not isinstance(r, Exception))
    duration = time.time() - start_time
    
    print(f"Load test: {success_count}/100 operations succeeded in {duration:.2f}s")
```

## 🚀 Production Deployment

### 1. Environment Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export REDIS_URL="redis://redis-server:6379"
export DATABASE_URL="postgresql+asyncpg://user:pass@postgres-server/hokm_db"
export SYNC_BATCH_SIZE=100
export ENABLE_QUERY_LOGGING=false
```

### 2. Health Checks

```python
async def health_check():
    """Comprehensive health check for production"""
    health_status = {
        'redis': await hybrid_data.redis_manager.health_check(),
        'postgresql': await hybrid_data.postgresql_manager.health_check(),
        'sync': await hybrid_data.sync_manager.health_check(),
        'overall': True
    }
    
    health_status['overall'] = all(health_status.values())
    return health_status
```

### 3. Monitoring Setup

```python
# Set up monitoring endpoints
@app.route('/metrics')
async def metrics_endpoint():
    return await hybrid_data.get_performance_metrics()

@app.route('/health')
async def health_endpoint():
    return await health_check()
```

## 📚 Additional Resources

- **Strategy Document**: `HYBRID_DATA_ARCHITECTURE_STRATEGY.md` - Complete architectural overview
- **API Reference**: See docstrings in each component file
- **Performance Tuning**: Check the strategy document for optimization guidelines
- **Troubleshooting**: Review error handling patterns in the sync manager

## 🤝 Contributing

When extending the hybrid data architecture:

1. Follow the established patterns for data routing
2. Add appropriate error handling and circuit breakers
3. Include performance metrics and monitoring
4. Write tests for new functionality
5. Update documentation

## 📞 Support

For questions about the hybrid data architecture implementation:

1. Review the strategy document for architectural decisions
2. Check the integration example for usage patterns
3. Examine the component docstrings for API details
4. Run the test suite to verify functionality
