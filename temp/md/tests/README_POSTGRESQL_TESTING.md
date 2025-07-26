# Comprehensive PostgreSQL Integration Testing Framework

This directory contains comprehensive pytest-asyncio integration tests for the PostgreSQL-integrated Hokm game server.

## 🧪 Test Structure

```
tests/
├── conftest.py                     # Pytest configuration and fixtures
├── test_database_integration.py    # Core database integration tests
├── test_performance_benchmarks.py  # Performance testing
├── test_transaction_management.py  # Transaction safety tests
├── test_concurrent_operations.py   # Concurrency and race condition tests
├── test_database_schema.py         # Database setup and schema validation
├── test_e2e_integration.py         # End-to-end integration tests
├── test_utils.py                   # Test utility functions and helpers
├── run_tests.py                    # Comprehensive test runner
├── setup_test_env.py               # Test environment setup
└── pytest.ini                     # Pytest configuration
```

## 🚀 Quick Start

### 1. Environment Setup

```bash
# Set up test environment (creates database, installs dependencies)
python tests/setup_test_env.py --setup

# Or manually configure:
export TEST_DATABASE_URL="postgresql://test_user:test_pass@localhost:5432/hokm_test"
export DATABASE_ENVIRONMENT="test"

# Install test dependencies
pip install -r requirements.txt
```

### 2. Run Tests

```bash
# Run all tests with comprehensive reporting
python tests/run_tests.py --full --coverage --benchmark

# Run specific test categories
python tests/run_tests.py --integration    # Database integration tests
python tests/run_tests.py --performance   # Performance benchmarks
python tests/run_tests.py --transaction   # Transaction management tests
python tests/run_tests.py --concurrent    # Concurrent operations tests

# Run with pytest directly
pytest tests/ -v                          # All tests
pytest tests/test_database_integration.py -v  # Specific test file
pytest -m "integration and not slow" -v   # Tests by marker
```

### 3. Check Environment

```bash
# Check test environment status
python tests/setup_test_env.py --check

# Show current configuration
python tests/setup_test_env.py --config
```

## 📊 Test Categories

### 1. Database Integration Tests (`test_database_integration.py`)
**Purpose**: Test core database functionality and integration
- ✅ Connection management and pooling
- ✅ Session management and isolation
- ✅ Transaction rollback for test isolation
- ✅ Connection pool behavior under load
- ✅ Error handling and recovery
- ✅ Player data management (CRUD operations)
- ✅ Game state management (sessions, participants, moves)
- ✅ Statistics and analytics queries
- ✅ Circuit breaker functionality

**Run**: `pytest tests/test_database_integration.py -v`

### 2. Performance Benchmarks (`test_performance_benchmarks.py`)
**Purpose**: Test performance under various load conditions
- ⚡ Player creation performance (concurrent users)
- ⚡ Game state persistence benchmarks
- ⚡ Connection pool performance
- ⚡ Bulk operations benchmarks
- ⚡ Query optimization validation
- ⚡ Memory usage profiling
- ⚡ Sustained load testing
- ⚡ Scalability testing

**Run**: `pytest tests/test_performance_benchmarks.py --benchmark-only`

### 3. Transaction Management (`test_transaction_management.py`)
**Purpose**: Test ACID properties and transaction safety
- 🔄 Basic transaction commit/rollback
- 🔄 Exception handling in transactions
- 🔄 Savepoint management
- 🔄 Isolation level testing
- 🔄 Deadlock detection and recovery
- 🔄 Long-running transaction handling
- 🔄 Retry logic validation
- 🔄 Batch operation transactions
- 🔄 Connection failure recovery

**Run**: `pytest tests/test_transaction_management.py -v`

### 4. Concurrent Operations (`test_concurrent_operations.py`)
**Purpose**: Test race conditions and concurrent access patterns
- 🚀 Concurrent player creation
- 🚀 Concurrent game session joins
- 🚀 Concurrent game moves
- 🚀 Deadlock detection and recovery
- 🚀 Connection pool under load
- 🚀 Concurrent statistics updates
- 🚀 Race condition handling
- 🚀 Stress testing with sustained load

**Run**: `pytest tests/test_concurrent_operations.py -v`

### 5. Database Schema Tests (`test_database_schema.py`)
**Purpose**: Test database setup, migrations, and schema validation
- 🗄️ Database connection string validation
- 🗄️ Table schema structure validation
- 🗄️ Index existence and performance
- 🗄️ Constraint validation (PK, FK, unique)
- 🗄️ Trigger and function validation
- 🗄️ Permission and security checks
- 🗄️ Migration version tracking
- 🗄️ Backup and recovery capabilities

**Run**: `pytest tests/test_database_schema.py -v`

### 6. End-to-End Integration (`test_e2e_integration.py`)
**Purpose**: Test complete game scenarios from start to finish
- 🎮 Complete 4-player game flow
- 🎮 Player reconnection scenarios
- 🎮 Concurrent game sessions
- 🎮 Game timeout and cleanup
- 🎮 Database consistency after errors
- 📈 Analytics and reporting
- 📊 Performance metrics collection

**Run**: `pytest tests/test_e2e_integration.py -v`

## 🔧 Configuration Options

### Environment Variables

```bash
# Database Configuration
TEST_DATABASE_URL="postgresql://user:pass@localhost:5432/test_db"
DATABASE_ENVIRONMENT="test"
TEST_DB_POOL_SIZE="10"
TEST_DB_MAX_OVERFLOW="20"
TEST_DB_TIMEOUT="30.0"

# Performance Testing
MAX_RESPONSE_TIME="1.0"
MAX_CONCURRENT_OPS="100"
TARGET_OPS_PER_SEC="50"
SLOW_TEST_THRESHOLD="5.0"

# Test Execution
TEST_PARALLEL_WORKERS="4"
COVERAGE_THRESHOLD="80.0"
GENERATE_HTML_REPORT="true"
CLEANUP_TEST_DATA="true"
```

### Pytest Markers

- `@pytest.mark.integration` - Database integration tests
- `@pytest.mark.performance` - Performance tests
- `@pytest.mark.benchmark` - Benchmark tests
- `@pytest.mark.concurrent` - Concurrency tests
- `@pytest.mark.slow` - Slow-running tests
- `@pytest.mark.e2e` - End-to-end tests
- `@pytest.mark.database` - Tests requiring database

## 📈 Performance Baselines

### Response Time Requirements
- **Player Operations**: < 500ms average
- **Game State Operations**: < 1000ms average
- **Analytics Queries**: < 2000ms average
- **Bulk Operations**: < 5000ms for 100+ records

### Concurrency Requirements
- **Concurrent Connections**: 50+ simultaneous
- **Concurrent Operations**: 100+ operations/second
- **Connection Pool**: Efficient utilization under load
- **Deadlock Recovery**: < 1% of operations affected

### Memory and Resource Usage
- **Memory Growth**: < 10MB per 1000 operations
- **Connection Leaks**: Zero leaked connections
- **Transaction Rollback**: 100% data consistency
- **Error Recovery**: 99.9% operation success rate

## 🧪 Advanced Testing Features

### Test Data Generation
```python
from test_utils import TestDataGenerator

# Generate realistic test data
player_data = TestDataGenerator.generate_player_data()
game_data = TestDataGenerator.generate_game_session_data(creator_id=1)
move_data = TestDataGenerator.generate_game_move_data(session_id="123", player_id=1, round_num=1)
```

### Performance Profiling
```python
from test_utils import PerformanceProfiler

profiler = PerformanceProfiler()
profiler.start()

# Your test operations
profiler.record_operation("operation_name", duration)

metrics = profiler.stop()
# metrics contains: total_duration, avg_operation_time, ops_per_second, etc.
```

### Concurrency Testing
```python
from test_utils import ConcurrencyTestHelpers

# Run operations concurrently
results = await ConcurrencyTestHelpers.run_concurrent_operations(
    operations_list, max_concurrent=10, timeout=30.0
)

# Stress test an operation
stress_results = await ConcurrencyTestHelpers.stress_test_operation(
    operation, duration_seconds=10.0, target_ops_per_second=50
)
```

### Custom Assertions
```python
from test_utils import TestAssertions

# Validate player data
TestAssertions.assert_player_data_equal(actual, expected)

# Validate game state
TestAssertions.assert_game_state_valid(game_state)

# Validate performance metrics
TestAssertions.assert_performance_metrics_valid(metrics, max_response_time=1.0)
```

## 📋 Test Execution Examples

### Development Testing
```bash
# Quick integration test during development
pytest tests/test_database_integration.py::TestDatabaseIntegration::test_database_connection -v

# Test specific functionality
pytest tests/test_database_integration.py -k "player_management" -v

# Run with coverage
pytest tests/test_database_integration.py --cov=backend --cov-report=html
```

### Performance Testing
```bash
# Run all performance tests
python tests/run_tests.py --performance --benchmark

# Benchmark specific operations
pytest tests/test_performance_benchmarks.py::TestPerformanceBenchmarks::test_player_creation_performance --benchmark-only

# Stress testing
pytest tests/test_concurrent_operations.py -m "stress" -v
```

### Continuous Integration
```bash
# Full test suite for CI
python tests/run_tests.py --full --coverage
pytest tests/ --junit-xml=junit.xml --cov=backend --cov-report=json --maxfail=5

# Parallel execution
pytest tests/ -n 4 --dist=loadfile
```

## 🔍 Debugging and Troubleshooting

### Common Issues

1. **Database Connection Errors**
   ```bash
   # Check database status
   python tests/setup_test_env.py --check
   
   # Verify connection string
   echo $TEST_DATABASE_URL
   ```

2. **Test Isolation Issues**
   ```bash
   # Run tests in isolation
   pytest tests/test_database_integration.py --forked
   
   # Clean test environment
   python tests/setup_test_env.py --cleanup
   ```

3. **Performance Test Failures**
   ```bash
   # Run with verbose performance output
   pytest tests/test_performance_benchmarks.py -v -s
   
   # Adjust performance thresholds
   export MAX_RESPONSE_TIME="2.0"
   ```

### Debug Mode
```bash
# Enable debug logging
export ENABLE_DEBUG_LOGGING="true"

# Run with Python debugger
pytest tests/test_database_integration.py --pdb

# Capture stdout/stderr
pytest tests/test_database_integration.py -s --capture=no
```

## 📊 Reporting and Analysis

### HTML Coverage Reports
```bash
pytest tests/ --cov=backend --cov-report=html
open htmlcov/index.html
```

### Benchmark Reports
```bash
pytest tests/test_performance_benchmarks.py --benchmark-save=baseline
pytest tests/test_performance_benchmarks.py --benchmark-compare=baseline
```

### Test Results Analysis
```bash
# Generate comprehensive test report
python tests/run_tests.py --full --coverage --benchmark

# Check test report
cat tests/test_report.json | jq .
```

## 🎯 Best Practices

### Writing New Tests
1. **Use async/await** for all database operations
2. **Leverage fixtures** from `conftest.py` for common setup
3. **Mark tests appropriately** with pytest markers
4. **Include performance assertions** for critical operations
5. **Test both success and failure scenarios**
6. **Use transaction rollback** for test isolation

### Performance Testing
1. **Set realistic baselines** based on production requirements
2. **Test under load** with concurrent operations
3. **Monitor resource usage** (memory, connections, CPU)
4. **Test scalability limits** with increasing load
5. **Validate consistency** under stress conditions

### Database Testing
1. **Always use test database** separate from development
2. **Ensure proper cleanup** after test completion
3. **Test transaction boundaries** and rollback scenarios
4. **Validate data integrity** constraints
5. **Test concurrent access** patterns

## 🚀 Continuous Integration Setup

### GitHub Actions Example
```yaml
name: PostgreSQL Integration Tests
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_PASSWORD: test_password
          POSTGRES_USER: test_user
          POSTGRES_DB: hokm_test
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
    - uses: actions/checkout@v3
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'
    
    - name: Install dependencies
      run: pip install -r requirements.txt
    
    - name: Set up test environment
      run: python tests/setup_test_env.py --setup
      env:
        TEST_DATABASE_URL: postgresql://test_user:test_password@localhost:5432/hokm_test
    
    - name: Run tests
      run: python tests/run_tests.py --full --coverage
      env:
        TEST_DATABASE_URL: postgresql://test_user:test_password@localhost:5432/hokm_test
    
    - name: Upload coverage reports
      uses: codecov/codecov-action@v3
```

## 📚 Additional Resources

- [pytest-asyncio Documentation](https://pytest-asyncio.readthedocs.io/)
- [PostgreSQL Testing Best Practices](https://www.postgresql.org/docs/current/regress.html)
- [SQLAlchemy Testing Guide](https://docs.sqlalchemy.org/en/20/orm/session_transaction.html#joining-a-session-into-an-external-transaction-such-as-for-test-suites)
- [pytest Benchmark Documentation](https://pytest-benchmark.readthedocs.io/)

---

**Status**: ✅ **Fully Implemented** - Comprehensive PostgreSQL integration testing framework with 100+ test cases covering functional correctness, performance characteristics, and production readiness.

**Test Categories**: 6 comprehensive test suites
**Test Coverage**: Database operations, concurrency, performance, end-to-end scenarios
**Performance Validation**: Response times, throughput, resource usage
**Reliability Testing**: Transaction safety, error recovery, data consistency
