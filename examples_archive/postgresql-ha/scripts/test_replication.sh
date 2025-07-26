#!/bin/bash

# PostgreSQL Streaming Replication Test Script
# This script tests the replication setup to ensure it's working correctly

set -e

# Configuration
PRIMARY_HOST="localhost"
PRIMARY_PORT="5432"
STANDBY_HOST="localhost"
STANDBY_PORT="5433"
DB_NAME="hokm_db"
DB_USER="hokm_user"
DB_PASSWORD="hokm_password"
REPLICATION_USER="replicator"
REPLICATION_PASSWORD="replicator_password"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to display test results
show_result() {
    if [ $1 -eq 0 ]; then
        echo -e "${GREEN}✓ $2${NC}"
    else
        echo -e "${RED}✗ $2${NC}"
        return 1
    fi
}

# Function to run SQL command on primary
run_primary_sql() {
    PGPASSWORD=$DB_PASSWORD psql -h $PRIMARY_HOST -p $PRIMARY_PORT -U $DB_USER -d $DB_NAME -c "$1" -t -A 2>/dev/null
}

# Function to run SQL command on standby
run_standby_sql() {
    PGPASSWORD=$DB_PASSWORD psql -h $STANDBY_HOST -p $STANDBY_PORT -U $DB_USER -d $DB_NAME -c "$1" -t -A 2>/dev/null
}

# Function to check connection
check_connection() {
    local host=$1
    local port=$2
    local server_type=$3
    
    if pg_isready -h $host -p $port -U $DB_USER > /dev/null 2>&1; then
        show_result 0 "$server_type server connection ($host:$port)"
        return 0
    else
        show_result 1 "$server_type server connection ($host:$port)"
        return 1
    fi
}

# Function to check server role
check_server_role() {
    local host=$1
    local port=$2
    local expected_role=$3
    
    local is_recovery=$(PGPASSWORD=$DB_PASSWORD psql -h $host -p $port -U $DB_USER -d $DB_NAME -c "SELECT pg_is_in_recovery();" -t -A 2>/dev/null)
    
    if [ "$expected_role" = "primary" ] && [ "$is_recovery" = "f" ]; then
        show_result 0 "Primary server role verification"
        return 0
    elif [ "$expected_role" = "standby" ] && [ "$is_recovery" = "t" ]; then
        show_result 0 "Standby server role verification"
        return 0
    else
        show_result 1 "$expected_role server role verification (expected: $expected_role, got: $is_recovery)"
        return 1
    fi
}

# Function to test replication
test_replication() {
    local test_data="replication_test_$(date +%s)"
    
    echo -e "${YELLOW}Testing data replication...${NC}"
    
    # Insert test data on primary
    if run_primary_sql "INSERT INTO replication_test (data) VALUES ('$test_data');" > /dev/null 2>&1; then
        show_result 0 "Insert test data on primary"
    else
        show_result 1 "Insert test data on primary"
        return 1
    fi
    
    # Wait for replication
    sleep 2
    
    # Check if data exists on standby
    if run_standby_sql "SELECT COUNT(*) FROM replication_test WHERE data = '$test_data';" | grep -q "1"; then
        show_result 0 "Data replicated to standby"
    else
        show_result 1 "Data replicated to standby"
        return 1
    fi
    
    # Clean up test data
    run_primary_sql "DELETE FROM replication_test WHERE data = '$test_data';" > /dev/null 2>&1
}

# Function to check replication lag
check_replication_lag() {
    local lag=$(run_standby_sql "SELECT EXTRACT(EPOCH FROM now() - pg_last_xact_replay_timestamp()) AS lag_seconds;" 2>/dev/null)
    
    if [ -z "$lag" ] || [ "$lag" = "" ]; then
        show_result 1 "Replication lag measurement (no data)"
        return 1
    fi
    
    # Convert to integer for comparison
    lag_int=$(echo "$lag" | cut -d. -f1)
    
    if [ "$lag_int" -lt 30 ]; then
        show_result 0 "Replication lag ($lag seconds)"
    else
        show_result 1 "Replication lag ($lag seconds - too high)"
        return 1
    fi
}

# Function to check replication status
check_replication_status() {
    local active_replicas=$(run_primary_sql "SELECT COUNT(*) FROM pg_stat_replication WHERE state = 'streaming';" 2>/dev/null)
    
    if [ "$active_replicas" -gt 0 ]; then
        show_result 0 "Active replication connections ($active_replicas)"
    else
        show_result 1 "Active replication connections ($active_replicas)"
        return 1
    fi
}

# Function to check WAL receiver status
check_wal_receiver() {
    local receiver_status=$(run_standby_sql "SELECT status FROM pg_stat_wal_receiver;" 2>/dev/null)
    
    if [ "$receiver_status" = "streaming" ]; then
        show_result 0 "WAL receiver status ($receiver_status)"
    else
        show_result 1 "WAL receiver status ($receiver_status)"
        return 1
    fi
}

# Function to display detailed status
show_detailed_status() {
    echo -e "${BLUE}=== Detailed Replication Status ===${NC}"
    
    echo -e "${YELLOW}Primary Server Status:${NC}"
    run_primary_sql "SELECT * FROM pg_stat_replication;" 2>/dev/null || echo "No replication connections"
    
    echo -e "${YELLOW}Standby Server Status:${NC}"
    run_standby_sql "SELECT * FROM pg_stat_wal_receiver;" 2>/dev/null || echo "WAL receiver not active"
    
    echo -e "${YELLOW}Replication Lag:${NC}"
    run_standby_sql "SELECT EXTRACT(EPOCH FROM now() - pg_last_xact_replay_timestamp()) AS lag_seconds;" 2>/dev/null || echo "Cannot calculate lag"
    
    echo -e "${YELLOW}Data Counts:${NC}"
    echo "Primary: $(run_primary_sql "SELECT COUNT(*) FROM replication_test;" 2>/dev/null || echo "Error")"
    echo "Standby: $(run_standby_sql "SELECT COUNT(*) FROM replication_test;" 2>/dev/null || echo "Error")"
}

# Function to run performance test
run_performance_test() {
    echo -e "${BLUE}=== Performance Test ===${NC}"
    
    # Generate test data on primary
    echo -e "${YELLOW}Generating test data...${NC}"
    if run_primary_sql "SELECT generate_test_data(100);" > /dev/null 2>&1; then
        show_result 0 "Generated 100 test records"
    else
        show_result 1 "Generate test data"
        return 1
    fi
    
    # Wait for replication
    sleep 3
    
    # Check data count on both servers
    local primary_count=$(run_primary_sql "SELECT COUNT(*) FROM replication_test;" 2>/dev/null)
    local standby_count=$(run_standby_sql "SELECT COUNT(*) FROM replication_test;" 2>/dev/null)
    
    if [ "$primary_count" = "$standby_count" ]; then
        show_result 0 "Data consistency (Primary: $primary_count, Standby: $standby_count)"
    else
        show_result 1 "Data consistency (Primary: $primary_count, Standby: $standby_count)"
        return 1
    fi
    
    # Clean up test data
    run_primary_sql "DELETE FROM replication_test WHERE data LIKE 'Test data %';" > /dev/null 2>&1
}

# Main test function
run_tests() {
    echo -e "${BLUE}=== PostgreSQL Streaming Replication Tests ===${NC}"
    echo
    
    local test_count=0
    local passed_count=0
    
    # Test 1: Connection tests
    echo -e "${YELLOW}1. Connection Tests:${NC}"
    ((test_count++))
    check_connection $PRIMARY_HOST $PRIMARY_PORT "Primary" && ((passed_count++))
    ((test_count++))
    check_connection $STANDBY_HOST $STANDBY_PORT "Standby" && ((passed_count++))
    echo
    
    # Test 2: Server role verification
    echo -e "${YELLOW}2. Server Role Verification:${NC}"
    ((test_count++))
    check_server_role $PRIMARY_HOST $PRIMARY_PORT "primary" && ((passed_count++))
    ((test_count++))
    check_server_role $STANDBY_HOST $STANDBY_PORT "standby" && ((passed_count++))
    echo
    
    # Test 3: Replication status
    echo -e "${YELLOW}3. Replication Status:${NC}"
    ((test_count++))
    check_replication_status && ((passed_count++))
    ((test_count++))
    check_wal_receiver && ((passed_count++))
    echo
    
    # Test 4: Replication lag
    echo -e "${YELLOW}4. Replication Lag:${NC}"
    ((test_count++))
    check_replication_lag && ((passed_count++))
    echo
    
    # Test 5: Data replication
    echo -e "${YELLOW}5. Data Replication:${NC}"
    ((test_count++))
    test_replication && ((passed_count++))
    echo
    
    # Test 6: Performance test (optional)
    if [ "$1" = "--performance" ]; then
        echo -e "${YELLOW}6. Performance Test:${NC}"
        ((test_count++))
        run_performance_test && ((passed_count++))
        echo
    fi
    
    # Display results
    echo -e "${BLUE}=== Test Results ===${NC}"
    echo "Passed: $passed_count / $test_count"
    
    if [ $passed_count -eq $test_count ]; then
        echo -e "${GREEN}All tests passed! Replication is working correctly.${NC}"
        return 0
    else
        echo -e "${RED}Some tests failed. Please check the configuration.${NC}"
        return 1
    fi
}

# Function to show help
show_help() {
    echo "PostgreSQL Streaming Replication Test Script"
    echo
    echo "Usage: $0 [options]"
    echo
    echo "Options:"
    echo "  --performance    Run performance tests"
    echo "  --status         Show detailed status only"
    echo "  --help           Show this help message"
    echo
    echo "Examples:"
    echo "  $0                 # Run basic tests"
    echo "  $0 --performance   # Run all tests including performance"
    echo "  $0 --status        # Show detailed status only"
    echo
}

# Main script logic
case "$1" in
    --performance)
        run_tests --performance
        ;;
    --status)
        show_detailed_status
        ;;
    --help)
        show_help
        ;;
    *)
        run_tests
        ;;
esac

# Show detailed status if tests passed
if [ $? -eq 0 ] && [ "$1" != "--status" ]; then
    echo
    show_detailed_status
fi
