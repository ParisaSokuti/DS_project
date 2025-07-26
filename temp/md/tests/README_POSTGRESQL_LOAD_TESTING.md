# PostgreSQL Load Testing Framework

A comprehensive load testing framework specifically designed for PostgreSQL integration in the Hokm game server. This framework provides detailed performance analysis, migration testing, and scaling recommendations.

## Overview

The PostgreSQL Load Testing Framework consists of several specialized tools:

1. **PostgreSQL Load Test** (`postgresql_load_test.py`) - Core database performance testing
2. **Migration Load Test** (`migration_load_test.py`) - Testing during Redis-to-PostgreSQL migration
3. **Comprehensive Test Runner** (`run_comprehensive_load_tests.py`) - Orchestrates multiple test scenarios
4. **Demo Script** (`demo_postgresql_load_testing.py`) - Showcases framework capabilities

## Features

### 🎯 Core Load Testing
- **Realistic User Simulation**: Simulates concurrent database operations with realistic patterns
- **Multiple Query Types**: Tests SELECT, INSERT, UPDATE, DELETE, and complex queries
- **Transaction Testing**: Validates transaction performance and rollback scenarios
- **Batch Operations**: Tests bulk data operations and their impact

### 📊 Comprehensive Monitoring
- **Connection Pool Monitoring**: Tracks active/idle connections, timeouts, and pool utilization
- **Query Performance**: Measures response times, identifies slow queries, and tracks query types
- **Lock Contention**: Monitors deadlocks, blocking queries, and lock wait times
- **Buffer Cache Analysis**: Evaluates cache hit ratios and memory efficiency
- **Database Size Tracking**: Monitors database and table growth during testing

### 🔄 Migration-Specific Testing
- **Migration Phase Testing**: Tests each phase of the migration process
- **User Impact Assessment**: Measures user experience degradation during migration
- **Data Consistency Validation**: Verifies data integrity across systems
- **Rollback Testing**: Validates rollback procedures and recovery mechanisms

### 📈 Performance Analysis
- **Threshold Validation**: Compares performance against predefined thresholds
- **Bottleneck Identification**: Identifies system bottlenecks and resource constraints
- **Scaling Analysis**: Analyzes performance characteristics under different loads
- **Comparative Analysis**: Compares performance across different test scenarios

### 📋 Reporting and Recommendations
- **Multiple Output Formats**: JSON, Markdown, and CSV reports
- **Actionable Recommendations**: Provides specific optimization suggestions
- **Performance Trends**: Tracks performance changes over time
- **Executive Summaries**: High-level summaries for stakeholders

## Installation

### Prerequisites
- Python 3.8+
- PostgreSQL 12+
- Redis (for migration testing)

### Dependencies
```bash
pip install asyncpg aiohttp websockets psutil redis
```

### Database Setup
1. Create the PostgreSQL database:
```sql
CREATE DATABASE hokm_game;
```

2. Create required tables:
```sql
CREATE TABLE games (
    game_id VARCHAR(255) PRIMARY KEY,
    status VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    current_phase VARCHAR(50),
    player_count INTEGER DEFAULT 0,
    game_data JSONB
);

CREATE TABLE players (
    player_id VARCHAR(255) PRIMARY KEY,
    username VARCHAR(255),
    total_games INTEGER DEFAULT 0,
    wins INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    player_data JSONB
);

CREATE TABLE sessions (
    session_id VARCHAR(255) PRIMARY KEY,
    player_id VARCHAR(255),
    game_id VARCHAR(255),
    created_at TIMESTAMP DEFAULT NOW(),
    last_activity TIMESTAMP DEFAULT NOW(),
    connection_state VARCHAR(50),
    session_data JSONB
);

CREATE TABLE game_events (
    event_id SERIAL PRIMARY KEY,
    game_id VARCHAR(255),
    event_type VARCHAR(100),
    event_data JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE game_players (
    game_id VARCHAR(255),
    player_id VARCHAR(255),
    joined_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (game_id, player_id)
);
```

3. Enable pg_stat_statements for query monitoring:
```sql
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
```

## Configuration

### Basic Configuration
Create `postgresql_load_test_config.json`:
```json
{
  "database": {
    "host": "localhost",
    "port": 5432,
    "database": "hokm_game",
    "user": "postgres",
    "password": "your_password"
  },
  "load_profile": {
    "concurrent_connections": 50,
    "queries_per_second_target": 1000,
    "read_write_ratio": 0.7,
    "duration_minutes": 10
  },
  "performance_thresholds": {
    "max_avg_query_time_ms": 50,
    "max_p95_query_time_ms": 100,
    "max_error_rate_percent": 1.0
  }
}
```

### Test Scenarios Configuration
Create comprehensive test configuration:
```json
{
  "test_scenarios": {
    "baseline_performance": {
      "enabled": true,
      "concurrent_connections": 20,
      "duration_minutes": 5
    },
    "normal_load": {
      "enabled": true,
      "concurrent_connections": 50,
      "duration_minutes": 10
    },
    "peak_load": {
      "enabled": true,
      "concurrent_connections": 100,
      "duration_minutes": 15
    },
    "stress_test": {
      "enabled": true,
      "concurrent_connections": 200,
      "duration_minutes": 20
    },
    "migration_load": {
      "enabled": true,
      "concurrent_users": 50,
      "duration_minutes": 10
    }
  }
}
```

## Usage

### 1. Basic PostgreSQL Load Test
```bash
# Quick test with default settings
python postgresql_load_test.py

# Custom configuration
python postgresql_load_test.py \
  --duration 15 \
  --connections 100 \
  --qps-target 1500 \
  --output results.json

# Using configuration file
python postgresql_load_test.py \
  --config postgresql_load_test_config.json \
  --output detailed_results.json
```

### 2. Migration Load Testing
```bash
# Test migration under load
python migration_load_test.py \
  --duration 10 \
  --concurrent-users 50 \
  --postgres-host localhost \
  --postgres-db hokm_game \
  --redis-host localhost

# With custom parameters
python migration_load_test.py \
  --duration 15 \
  --concurrent-users 100 \
  --output migration_results.json
```

### 3. Comprehensive Test Suite
```bash
# Run all enabled test scenarios
python run_comprehensive_load_tests.py

# Run with custom configuration
python run_comprehensive_load_tests.py \
  --config comprehensive_config.json \
  --output-dir test_results

# Run specific scenarios only
python run_comprehensive_load_tests.py \
  --scenarios normal_load peak_load stress_test

# Create sample configuration
python run_comprehensive_load_tests.py \
  --create-config sample_config.json
```

### 4. Demo and Validation
```bash
# Run demo to validate setup
python demo_postgresql_load_testing.py
```

## Test Scenarios

### Baseline Performance
- **Purpose**: Establish performance baseline
- **Load**: 20 concurrent connections, 5 minutes
- **Metrics**: Basic query performance, connection handling

### Normal Load
- **Purpose**: Simulate typical operational load
- **Load**: 50 concurrent connections, 10 minutes
- **Metrics**: Standard performance under normal conditions

### Peak Load
- **Purpose**: Test high-traffic scenarios
- **Load**: 100 concurrent connections, 15 minutes
- **Metrics**: Performance degradation, resource utilization

### Stress Test
- **Purpose**: Find system breaking points
- **Load**: 200+ concurrent connections, 20 minutes
- **Metrics**: Failure modes, recovery capabilities

### Migration Load
- **Purpose**: Test migration impact on users
- **Load**: 50 concurrent users during migration
- **Metrics**: User experience, data consistency, migration performance

### Endurance Test
- **Purpose**: Long-term stability testing
- **Load**: 75 concurrent connections, 60+ minutes
- **Metrics**: Memory leaks, connection stability, performance drift

## Monitoring and Metrics

### Database Metrics
- **Connection Pool**: Active/idle connections, timeouts, wait times
- **Query Performance**: Response times by query type, slow queries
- **Lock Contention**: Deadlocks, blocking queries, lock wait times
- **Buffer Cache**: Hit ratios, memory efficiency
- **Index Usage**: Index hits/misses, sequential scans
- **Transaction Stats**: Commit/rollback rates, transaction times

### System Metrics
- **CPU Usage**: During load testing
- **Memory Usage**: Memory consumption patterns
- **Network I/O**: Database connection traffic
- **Disk I/O**: Database read/write operations

### User Experience Metrics
- **Response Times**: End-to-end request latency
- **Error Rates**: Failed requests, timeouts
- **Throughput**: Requests per second
- **Availability**: Service uptime during tests

## Performance Thresholds

### Default Thresholds
```json
{
  "max_avg_response_time_ms": 500,
  "max_p95_response_time_ms": 1000,
  "max_p99_response_time_ms": 2000,
  "max_error_rate_percent": 1.0,
  "max_connection_failure_rate_percent": 2.0,
  "min_games_completion_rate_percent": 90.0,
  "max_cpu_usage_percent": 80.0,
  "max_memory_usage_percent": 85.0,
  "max_db_connection_pool_usage_percent": 90.0,
  "max_db_query_time_ms": 100.0
}
```

### Customizing Thresholds
Adjust thresholds based on your specific requirements:
- **Response Time**: Based on user experience requirements
- **Error Rate**: Based on acceptable failure levels
- **Resource Usage**: Based on available hardware
- **Database Performance**: Based on query complexity

## Reporting

### JSON Reports
Detailed technical reports with all metrics:
```json
{
  "test_summary": {
    "duration_minutes": 10,
    "concurrent_connections": 50,
    "queries_executed": 45678,
    "queries_failed": 12
  },
  "database_metrics": {
    "connection_stats": {...},
    "query_performance": {...},
    "lock_contention": {...}
  },
  "recommendations": [...]
}
```

### Markdown Summaries
Human-readable summaries:
```markdown
# Load Test Results

## Test Summary
- Duration: 10 minutes
- Concurrent Connections: 50
- Queries Executed: 45,678
- Error Rate: 0.03%

## Key Findings
- Average query time: 25ms
- P95 query time: 78ms
- Connection pool utilization: 85%

## Recommendations
- Increase connection pool size
- Optimize slow queries
- Add database indexes
```

### Performance Dashboards
The framework generates data suitable for:
- Grafana dashboards
- Application performance monitoring
- Custom visualization tools

## Troubleshooting

### Common Issues

#### Connection Failures
```bash
# Check PostgreSQL is running
pg_isready -h localhost -p 5432

# Verify connection parameters
psql -h localhost -p 5432 -d hokm_game -U postgres
```

#### Slow Performance
- Check database indexes
- Verify PostgreSQL configuration
- Monitor system resources (CPU, memory, disk)
- Review query execution plans

#### Test Failures
- Verify database schema matches expectations
- Check that required extensions are installed
- Ensure adequate system resources
- Review log files for detailed error messages

### Debug Mode
Enable verbose logging:
```bash
python postgresql_load_test.py --verbose
```

### Log Analysis
Check logs for:
- Connection errors
- Query timeouts
- Resource constraints
- Database errors

## Best Practices

### Test Environment
- Use dedicated test environment
- Match production hardware specifications
- Isolate test traffic from production
- Monitor system resources during tests

### Test Data
- Use realistic data volumes
- Include representative query patterns
- Test with production-like data distribution
- Clean up test data after tests

### Performance Tuning
- Baseline before optimization
- Test one change at a time
- Document configuration changes
- Validate improvements with repeat tests

### Monitoring
- Set up continuous monitoring
- Track trends over time
- Alert on threshold violations
- Regular performance reviews

## Integration

### CI/CD Pipeline
Example GitHub Actions workflow:
```yaml
name: PostgreSQL Load Tests
on:
  push:
    branches: [ main ]
  schedule:
    - cron: '0 2 * * *'  # Daily at 2 AM

jobs:
  load-test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:13
        env:
          POSTGRES_PASSWORD: postgres
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
    - uses: actions/checkout@v2
    
    - name: Set up Python
      uses: actions/setup-python@v2
      with:
        python-version: 3.9
    
    - name: Install dependencies
      run: |
        pip install -r requirements.txt
    
    - name: Run load tests
      run: |
        python run_comprehensive_load_tests.py \
          --scenarios baseline_performance normal_load \
          --output-dir test_results
    
    - name: Archive results
      uses: actions/upload-artifact@v2
      with:
        name: load-test-results
        path: test_results/
```

### Application Monitoring
Integrate with monitoring tools:
- **Prometheus**: Export metrics for monitoring
- **Grafana**: Create performance dashboards
- **Datadog**: Application performance monitoring
- **New Relic**: End-to-end performance tracking

## Advanced Usage

### Custom Load Patterns
Extend the framework for specific use cases:
```python
class CustomLoadProfile(DatabaseLoadProfile):
    def __init__(self):
        super().__init__()
        self.game_specific_queries = True
        self.card_game_simulation = True
```

### Custom Metrics
Add application-specific metrics:
```python
class GameSpecificMetrics(PostgreSQLMetrics):
    def __init__(self):
        super().__init__()
        self.games_completed = 0
        self.average_game_duration = 0
        self.player_actions_per_second = 0
```

### Load Test Automation
Automate load testing:
```python
async def automated_load_testing():
    scenarios = ['baseline', 'normal_load', 'peak_load']
    
    for scenario in scenarios:
        result = await run_load_test(scenario)
        if not meets_performance_criteria(result):
            alert_development_team(scenario, result)
            break
```

## Contributing

### Development Setup
1. Clone the repository
2. Install development dependencies
3. Set up test database
4. Run tests to verify setup

### Adding New Features
1. Follow existing code patterns
2. Add comprehensive tests
3. Update documentation
4. Submit pull request

### Reporting Issues
Include:
- System configuration
- Test configuration
- Error messages
- Steps to reproduce

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For support and questions:
- Create an issue in the repository
- Check the troubleshooting section
- Review existing documentation
- Contact the development team

## Changelog

### Version 1.0.0
- Initial release
- Basic PostgreSQL load testing
- Migration load testing
- Comprehensive test orchestration
- Multiple output formats
- Performance analysis and recommendations
