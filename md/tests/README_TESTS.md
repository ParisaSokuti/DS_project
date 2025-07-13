# Tests Directory Organization

This directory contains all test files, debug utilities, and demo scripts for the Hokm game server project.

## Directory Structure

### Test Categories

#### 1. Core Game Tests
- `test_basic_game.py` - Basic game functionality tests
- `test_game_completion.py` - Game completion flow tests
- `test_complete_game_flow.py` - End-to-end game flow tests
- `test_complete_hakem_flow.py` - Hakem selection and gameplay tests
- `test_gameboard_completion.py` - GameBoard class completion tests

#### 2. Server and Network Tests
- `test_server_*.py` - Server functionality tests
- `test_client_*.py` - Client connection and behavior tests
- `test_connection_reliability.py` - Network connection stability tests
- `test_simple_*.py` - Simple scenario tests

#### 3. Reconnection and Persistence Tests
- `test_reconnection*.py` - Player reconnection functionality
- `test_disconnect_*.py` - Disconnection handling tests
- `test_session_*.py` - Session persistence tests

#### 4. Database and Integration Tests
- `test_postgresql_*.py` - PostgreSQL integration tests
- `test_async_database_integration.py` - Async database operations
- `test_redis_integrity.py` - Redis data integrity tests
- `test_database_*.py` - Database schema and operations

#### 5. Performance and Stress Tests
- `test_stress*.py` - Server stress testing
- `test_server_stress.py` - High-load scenario tests
- `postgresql_load_test.py` - Database performance tests
- `comprehensive_load_test.py` - Full system load testing

#### 6. Bug Fix Verification Tests
- `test_*_fix.py` - Tests verifying specific bug fixes
- `test_ace_hearts_*.py` - Ace of hearts specific bug tests
- `test_hand_complete_fix.py` - Hand completion bug fixes
- `test_suit_following_*.py` - Suit following rule tests

#### 7. Circuit Breaker and Resilience Tests
- `test_circuit_breaker_*.py` - Circuit breaker functionality
- `circuit_breaker_demo.py` - Circuit breaker demonstration

### Debug Utilities

#### Debug Scripts
- `debug_*.py` - Various debugging utilities for different components
- `debug_client_server_interaction.py` - Client-server communication debugging
- `debug_connection_close.py` - Connection closure debugging
- `debug_game_state.py` - Game state inspection
- `debug_redis_storage.py` - Redis storage debugging

### Demo Scripts

#### Demonstration Scripts
- `demo_*.py` - Demonstration scripts for various features
- `demo_reconnection.py` - Reconnection feature demonstration
- `demo_session_persistence.py` - Session persistence demonstration

### Utility Scripts

#### Test Infrastructure
- `run_*.py` - Test runner scripts
- `conftest.py` - Pytest configuration
- `pytest.ini` - Pytest settings
- `setup_test_env.py` - Test environment setup

#### Migration and Database Tools
- `migration_*.py` - Database migration utilities
- `data_migration_utils.py` - Migration helper functions

### Test Data and Configuration
- `*.json` - Test configuration files
- `migrations/` - Database migration files
- `*.log` - Test execution logs

## Running Tests

### Basic Test Execution
```bash
# Run all tests
python -m pytest

# Run specific test file
python -m pytest test_basic_game.py

# Run tests with verbose output
python -m pytest -v

# Run specific test category
python -m pytest -k "reconnection"
```

### Specialized Test Runners
```bash
# Run comprehensive tests
python run_tests.py

# Run load tests
python run_comprehensive_load_tests.py

# Run migration tests
python run_migration_tests.py

# Run session tests
python run_session_tests.py
```

### Debug and Demo Scripts
```bash
# Run debugging utilities
python debug_game_state.py

# Run demonstrations
python demo_reconnection.py

# Quick testing
python quick_test.py
```

## Test Organization Principles

1. **Categorization**: Tests are organized by functionality and purpose
2. **Naming Convention**: Clear, descriptive names indicating test purpose
3. **Isolation**: Each test file focuses on specific functionality
4. **Documentation**: Tests include docstrings and comments
5. **Reusability**: Common utilities are shared across tests

## Contributing

When adding new tests:
1. Follow the existing naming convention
2. Place tests in appropriate categories
3. Include proper documentation
4. Ensure tests are isolated and repeatable
5. Update this README if adding new categories

## Test Coverage

This test suite covers:
- Core game logic and rules
- Network communication
- Database operations
- Error handling and recovery
- Performance under load
- Reconnection scenarios
- Data persistence
- Security considerations
