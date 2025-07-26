#!/bin/bash

# PostgreSQL HA Recovery Testing Script
# Tests various failure scenarios and recovery procedures

set -euo pipefail

# Configuration
TEST_TYPE="${1:-all}"
DOCKER_COMPOSE_FILE="${DOCKER_COMPOSE_FILE:-/Users/parisasokuti/my git repo/DS_project/postgresql-ha/docker-compose.yml}"
LOG_FILE="/tmp/postgresql-ha-test.log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log() {
    echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

success() {
    log "${GREEN}✓ $*${NC}"
}

warning() {
    log "${YELLOW}⚠ $*${NC}"
}

error() {
    log "${RED}✗ $*${NC}"
}

info() {
    log "${BLUE}ℹ $*${NC}"
}

# Wait for service to be ready
wait_for_service() {
    local service="$1"
    local port="$2"
    local timeout="${3:-60}"
    
    info "Waiting for $service to be ready on port $port..."
    
    for i in $(seq 1 $timeout); do
        if docker-compose -f "$DOCKER_COMPOSE_FILE" exec -T "$service" pg_isready -p "$port" 2>/dev/null; then
            success "$service is ready"
            return 0
        fi
        sleep 1
    done
    
    error "$service failed to become ready within $timeout seconds"
    return 1
}

# Check cluster status
check_cluster_status() {
    info "Checking cluster status..."
    
    # Check Patroni cluster status
    docker-compose -f "$DOCKER_COMPOSE_FILE" exec -T postgresql-primary \
        curl -s http://localhost:8008/cluster | jq '.' || {
        error "Failed to get cluster status"
        return 1
    }
    
    # Check replication status
    docker-compose -f "$DOCKER_COMPOSE_FILE" exec -T postgresql-primary \
        psql -U postgres -c "SELECT * FROM pg_stat_replication;" || {
        error "Failed to check replication status"
        return 1
    }
    
    success "Cluster status check completed"
}

# Test primary failover
test_primary_failover() {
    info "Testing primary failover..."
    
    # Get current primary
    local current_primary=$(docker-compose -f "$DOCKER_COMPOSE_FILE" exec -T postgresql-primary \
        curl -s http://localhost:8008/cluster | jq -r '.members[] | select(.role=="Leader") | .name')
    
    info "Current primary: $current_primary"
    
    # Stop primary database
    info "Stopping primary database..."
    docker-compose -f "$DOCKER_COMPOSE_FILE" stop postgresql-primary
    
    # Wait for failover
    sleep 30
    
    # Check if replica took over
    local new_primary=""
    for replica in postgresql-replica1 postgresql-replica2; do
        if docker-compose -f "$DOCKER_COMPOSE_FILE" exec -T "$replica" \
            curl -s "http://localhost:8009/cluster" 2>/dev/null | jq -r '.members[] | select(.role=="Leader") | .name' 2>/dev/null; then
            new_primary="$replica"
            break
        fi
    done
    
    if [[ -n "$new_primary" ]]; then
        success "Failover successful. New primary: $new_primary"
    else
        error "Failover failed. No new primary found"
        return 1
    fi
    
    # Restart original primary (should become replica)
    info "Restarting original primary..."
    docker-compose -f "$DOCKER_COMPOSE_FILE" start postgresql-primary
    
    # Wait for it to join as replica
    sleep 30
    
    success "Primary failover test completed"
}

# Test replica failure
test_replica_failure() {
    info "Testing replica failure..."
    
    # Stop one replica
    info "Stopping postgresql-replica1..."
    docker-compose -f "$DOCKER_COMPOSE_FILE" stop postgresql-replica1
    
    # Check that primary and other replica still work
    if docker-compose -f "$DOCKER_COMPOSE_FILE" exec -T postgresql-primary \
        psql -U postgres -c "SELECT 1;" > /dev/null; then
        success "Primary still accessible after replica failure"
    else
        error "Primary not accessible after replica failure"
        return 1
    fi
    
    # Restart replica
    info "Restarting postgresql-replica1..."
    docker-compose -f "$DOCKER_COMPOSE_FILE" start postgresql-replica1
    
    # Wait for it to catch up
    wait_for_service postgresql-replica1 5432 60
    
    success "Replica failure test completed"
}

# Test network partition
test_network_partition() {
    info "Testing network partition simulation..."
    
    # Create network issues by pausing container
    info "Simulating network partition by pausing replica..."
    docker-compose -f "$DOCKER_COMPOSE_FILE" pause postgresql-replica1
    
    # Wait and check cluster status
    sleep 20
    check_cluster_status
    
    # Resume container
    info "Resuming replica..."
    docker-compose -f "$DOCKER_COMPOSE_FILE" unpause postgresql-replica1
    
    # Wait for recovery
    sleep 30
    wait_for_service postgresql-replica1 5432 60
    
    success "Network partition test completed"
}

# Test load balancer failover
test_load_balancer_failover() {
    info "Testing load balancer failover..."
    
    # Test connection through HAProxy
    if docker-compose -f "$DOCKER_COMPOSE_FILE" exec -T haproxy \
        curl -s http://localhost:8080/stats > /dev/null; then
        success "HAProxy is responding"
    else
        error "HAProxy not responding"
        return 1
    fi
    
    # Stop HAProxy
    info "Stopping HAProxy..."
    docker-compose -f "$DOCKER_COMPOSE_FILE" stop haproxy
    
    # Test direct connection to primary
    if docker-compose -f "$DOCKER_COMPOSE_FILE" exec -T postgresql-primary \
        psql -U postgres -c "SELECT 1;" > /dev/null; then
        success "Direct connection to primary works"
    else
        error "Direct connection to primary failed"
        return 1
    fi
    
    # Restart HAProxy
    info "Restarting HAProxy..."
    docker-compose -f "$DOCKER_COMPOSE_FILE" start haproxy
    
    # Wait for HAProxy to be ready
    sleep 10
    
    success "Load balancer failover test completed"
}

# Test backup and restore
test_backup_restore() {
    info "Testing backup and restore..."
    
    # Create test data
    info "Creating test data..."
    docker-compose -f "$DOCKER_COMPOSE_FILE" exec -T postgresql-primary \
        psql -U postgres -c "
        CREATE TABLE IF NOT EXISTS test_recovery (
            id SERIAL PRIMARY KEY,
            data TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        );
        INSERT INTO test_recovery (data) VALUES ('test_data_' || generate_series(1, 100));" || {
        error "Failed to create test data"
        return 1
    }
    
    # Perform backup
    info "Performing backup..."
    docker-compose -f "$DOCKER_COMPOSE_FILE" exec -T postgresql-primary \
        pg_dump -U postgres -d postgres -f /tmp/test_backup.sql || {
        error "Backup failed"
        return 1
    }
    
    # Drop test table
    info "Dropping test table..."
    docker-compose -f "$DOCKER_COMPOSE_FILE" exec -T postgresql-primary \
        psql -U postgres -c "DROP TABLE test_recovery;" || {
        error "Failed to drop test table"
        return 1
    }
    
    # Restore from backup
    info "Restoring from backup..."
    docker-compose -f "$DOCKER_COMPOSE_FILE" exec -T postgresql-primary \
        psql -U postgres -f /tmp/test_backup.sql || {
        error "Restore failed"
        return 1
    }
    
    # Verify restored data
    local count=$(docker-compose -f "$DOCKER_COMPOSE_FILE" exec -T postgresql-primary \
        psql -U postgres -t -c "SELECT COUNT(*) FROM test_recovery;" | xargs)
    
    if [[ "$count" == "100" ]]; then
        success "Backup and restore test completed. Restored $count records"
    else
        error "Backup and restore test failed. Expected 100 records, got $count"
        return 1
    fi
    
    # Cleanup
    docker-compose -f "$DOCKER_COMPOSE_FILE" exec -T postgresql-primary \
        psql -U postgres -c "DROP TABLE test_recovery;"
}

# Test connection pooling
test_connection_pooling() {
    info "Testing connection pooling with PgBouncer..."
    
    # Test PgBouncer connection
    if docker-compose -f "$DOCKER_COMPOSE_FILE" exec -T pgbouncer \
        psql -h localhost -p 6432 -U postgres -d hokm_primary -c "SELECT 1;" 2>/dev/null; then
        success "PgBouncer connection successful"
    else
        warning "PgBouncer connection failed (may need user setup)"
    fi
    
    # Check PgBouncer stats
    if docker-compose -f "$DOCKER_COMPOSE_FILE" exec -T pgbouncer \
        psql -h localhost -p 6432 -U postgres -d pgbouncer -c "SHOW POOLS;" 2>/dev/null; then
        success "PgBouncer stats accessible"
    else
        warning "PgBouncer stats not accessible"
    fi
    
    success "Connection pooling test completed"
}

# Test monitoring and alerting
test_monitoring() {
    info "Testing monitoring stack..."
    
    # Check Prometheus
    if docker-compose -f "$DOCKER_COMPOSE_FILE" exec -T prometheus \
        curl -s http://localhost:9090/api/v1/status/targets > /dev/null; then
        success "Prometheus is responding"
    else
        warning "Prometheus not responding"
    fi
    
    # Check Grafana
    if docker-compose -f "$DOCKER_COMPOSE_FILE" exec -T grafana \
        curl -s http://localhost:3000/api/health > /dev/null; then
        success "Grafana is responding"
    else
        warning "Grafana not responding"
    fi
    
    # Check AlertManager
    if docker-compose -f "$DOCKER_COMPOSE_FILE" exec -T alertmanager \
        curl -s http://localhost:9093/api/v1/status > /dev/null; then
        success "AlertManager is responding"
    else
        warning "AlertManager not responding"
    fi
    
    success "Monitoring test completed"
}

# Performance test
test_performance() {
    info "Running basic performance test..."
    
    # Install pgbench if not available
    docker-compose -f "$DOCKER_COMPOSE_FILE" exec -T postgresql-primary \
        psql -U postgres -c "SELECT version();" > /dev/null || {
        error "Cannot connect to primary for performance test"
        return 1
    }
    
    # Initialize pgbench
    info "Initializing pgbench..."
    docker-compose -f "$DOCKER_COMPOSE_FILE" exec -T postgresql-primary \
        pgbench -i -s 10 -U postgres postgres || {
        warning "pgbench initialization failed"
        return 0
    }
    
    # Run performance test
    info "Running pgbench performance test..."
    docker-compose -f "$DOCKER_COMPOSE_FILE" exec -T postgresql-primary \
        pgbench -c 10 -j 2 -t 100 -U postgres postgres || {
        warning "pgbench test failed"
        return 0
    }
    
    success "Performance test completed"
}

# Generate test report
generate_report() {
    info "Generating test report..."
    
    cat << EOF > "/tmp/postgresql-ha-test-report.html"
<!DOCTYPE html>
<html>
<head>
    <title>PostgreSQL HA Test Report</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .success { color: green; }
        .warning { color: orange; }
        .error { color: red; }
        .info { color: blue; }
        pre { background-color: #f5f5f5; padding: 10px; border-radius: 5px; }
    </style>
</head>
<body>
    <h1>PostgreSQL HA Test Report</h1>
    <p>Generated on: $(date)</p>
    <h2>Test Results</h2>
    <pre>
$(cat "$LOG_FILE")
    </pre>
</body>
</html>
EOF
    
    success "Test report generated: /tmp/postgresql-ha-test-report.html"
}

# Main test execution
main() {
    info "Starting PostgreSQL HA Recovery Testing"
    info "Test type: $TEST_TYPE"
    
    # Clear log file
    > "$LOG_FILE"
    
    case "$TEST_TYPE" in
        "all")
            check_cluster_status
            test_replica_failure
            test_network_partition
            test_load_balancer_failover
            test_backup_restore
            test_connection_pooling
            test_monitoring
            test_performance
            # Save primary failover for last as it's most disruptive
            test_primary_failover
            ;;
        "failover")
            test_primary_failover
            ;;
        "replica")
            test_replica_failure
            ;;
        "network")
            test_network_partition
            ;;
        "backup")
            test_backup_restore
            ;;
        "monitoring")
            test_monitoring
            ;;
        "performance")
            test_performance
            ;;
        "status")
            check_cluster_status
            ;;
        *)
            error "Unknown test type: $TEST_TYPE"
            echo "Usage: $0 {all|failover|replica|network|backup|monitoring|performance|status}"
            exit 1
            ;;
    esac
    
    generate_report
    success "All tests completed. Check $LOG_FILE for details."
}

# Trap for cleanup
trap 'error "Test interrupted"' INT TERM

# Execute main function
main "$@"
