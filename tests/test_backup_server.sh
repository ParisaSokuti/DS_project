#!/bin/bash

# Backup Server Testing Script
# Tests all functionality of the backup server deployment

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
BACKUP_SERVER="backup.yourdomain.com"  # Replace with actual backup server
BACKUP_PORT="8765"
PRIMARY_SERVER="primary.yourdomain.com"  # Replace with actual primary server
TEST_LOG="/tmp/backup_server_test.log"

# Test results tracking
TESTS_PASSED=0
TESTS_FAILED=0
FAILED_TESTS=()

# Logging function
log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S'): $1" | tee -a "$TEST_LOG"
}

# Test result functions
test_passed() {
    TESTS_PASSED=$((TESTS_PASSED + 1))
    echo -e "${GREEN}✅ PASSED${NC}: $1"
    log "PASSED: $1"
}

test_failed() {
    TESTS_FAILED=$((TESTS_FAILED + 1))
    FAILED_TESTS+=("$1")
    echo -e "${RED}❌ FAILED${NC}: $1"
    log "FAILED: $1"
}

test_warning() {
    echo -e "${YELLOW}⚠️  WARNING${NC}: $1"
    log "WARNING: $1"
}

test_info() {
    echo -e "${BLUE}ℹ️  INFO${NC}: $1"
    log "INFO: $1"
}

# Test function template
run_test() {
    local test_name="$1"
    local test_command="$2"
    
    echo -e "\n${BLUE}🧪 Testing: $test_name${NC}"
    
    if eval "$test_command"; then
        test_passed "$test_name"
        return 0
    else
        test_failed "$test_name"
        return 1
    fi
}

# Individual test functions
test_backup_server_connectivity() {
    curl -f -s -m 10 "http://$BACKUP_SERVER:$BACKUP_PORT/health" > /dev/null
}

test_backup_server_websocket() {
    # Simple WebSocket test using Python
    python3 -c "
import asyncio
import websockets
import sys

async def test_ws():
    try:
        uri = 'ws://$BACKUP_SERVER:$BACKUP_PORT'
        async with websockets.connect(uri, timeout=10) as websocket:
            await websocket.send('{\"type\": \"ping\"}')
            response = await asyncio.wait_for(websocket.recv(), timeout=5)
            return True
    except Exception as e:
        print(f'WebSocket test failed: {e}', file=sys.stderr)
        return False

result = asyncio.run(test_ws())
sys.exit(0 if result else 1)
"
}

test_backup_service_status() {
    ssh gameserver@$BACKUP_SERVER "systemctl is-active hokm-game-backup" > /dev/null
}

test_backup_logs_present() {
    ssh gameserver@$BACKUP_SERVER "test -f /var/log/hokm-game/backup-server.log"
}

test_sync_script_exists() {
    ssh gameserver@$BACKUP_SERVER "test -x /usr/local/bin/sync_backup_server.sh"
}

test_health_monitor_exists() {
    ssh gameserver@$BACKUP_SERVER "test -x /usr/local/bin/backup_health_monitor.sh"
}

test_cron_jobs_installed() {
    ssh gameserver@$BACKUP_SERVER "crontab -l | grep -q sync_backup_server"
}

test_nginx_configuration() {
    ssh gameserver@$BACKUP_SERVER "nginx -t" > /dev/null 2>&1
}

test_environment_file() {
    ssh gameserver@$BACKUP_SERVER "test -f /opt/hokm-game/.env"
}

test_python_dependencies() {
    ssh gameserver@$BACKUP_SERVER "cd /opt/hokm-game && source venv/bin/activate && python -c 'import websockets, asyncio, json'"
}

test_database_connectivity() {
    ssh gameserver@$BACKUP_SERVER "pg_isready -h localhost -p 5432" > /dev/null 2>&1
}

test_redis_connectivity() {
    ssh gameserver@$BACKUP_SERVER "redis-cli ping" > /dev/null 2>&1
}

test_git_repository() {
    ssh gameserver@$BACKUP_SERVER "cd /opt/hokm-game && git status" > /dev/null
}

test_ssl_certificates() {
    ssh gameserver@$BACKUP_SERVER "test -f /etc/ssl/certs/hokm-game/fullchain.pem"
}

test_backup_directories() {
    ssh gameserver@$BACKUP_SERVER "test -d /opt/hokm-game/backups && test -d /var/log/hokm-game"
}

test_file_permissions() {
    ssh gameserver@$BACKUP_SERVER "test -w /opt/hokm-game && test -w /var/log/hokm-game"
}

test_primary_server_connectivity() {
    curl -f -s -m 10 "https://$PRIMARY_SERVER/health" > /dev/null
}

test_disk_space() {
    local usage=$(ssh gameserver@$BACKUP_SERVER "df /opt/hokm-game | tail -1 | awk '{print \$5}' | sed 's/%//'")
    [ "$usage" -lt 90 ]
}

test_memory_usage() {
    local usage=$(ssh gameserver@$BACKUP_SERVER "free | grep Mem | awk '{printf \"%.0f\", \$3/\$2 * 100.0}'")
    [ "$usage" -lt 90 ]
}

test_load_average() {
    local load=$(ssh gameserver@$BACKUP_SERVER "uptime | awk -F'load average:' '{print \$2}' | awk '{print \$1}' | sed 's/,//'")
    local cores=$(ssh gameserver@$BACKUP_SERVER "nproc")
    local threshold=$(echo "$cores * 2" | bc)
    (( $(echo "$load < $threshold" | bc -l) ))
}

test_game_client_connection() {
    # Test game client connection to backup server
    timeout 30 python3 << EOF
import asyncio
import websockets
import json
import sys

async def test_game_connection():
    try:
        uri = 'ws://$BACKUP_SERVER:$BACKUP_PORT'
        async with websockets.connect(uri) as websocket:
            # Send join message
            join_msg = {
                "type": "join",
                "room_code": "test"
            }
            await websocket.send(json.dumps(join_msg))
            
            # Wait for response
            response = await asyncio.wait_for(websocket.recv(), timeout=10)
            data = json.loads(response)
            
            # Check if we get a valid response
            if 'type' in data:
                print("Game connection test successful")
                return True
            else:
                print("Invalid response from game server")
                return False
                
    except Exception as e:
        print(f"Game connection test failed: {e}")
        return False

result = asyncio.run(test_game_connection())
sys.exit(0 if result else 1)
EOF
}

test_failover_preparation() {
    # Check if failover mode can be enabled
    ssh gameserver@$BACKUP_SERVER "grep -q 'FAILOVER_MODE' /opt/hokm-game/.env"
}

test_monitoring_endpoints() {
    # Test monitoring endpoints
    curl -f -s -m 5 "http://$BACKUP_SERVER:$BACKUP_PORT/metrics" > /dev/null 2>&1 || return 0  # Optional
    curl -f -s -m 5 "http://$BACKUP_SERVER:$BACKUP_PORT/status" > /dev/null 2>&1 || return 0   # Optional
}

# Main testing function
main() {
    echo -e "${BLUE}🚀 Starting Backup Server Test Suite${NC}"
    echo "==========================================="
    echo ""
    log "Starting backup server test suite"
    
    # Clear previous test log
    > "$TEST_LOG"
    
    echo -e "${BLUE}📋 Test Configuration:${NC}"
    echo "Backup Server: $BACKUP_SERVER:$BACKUP_PORT"
    echo "Primary Server: $PRIMARY_SERVER"
    echo "Test Log: $TEST_LOG"
    echo ""
    
    # Core Infrastructure Tests
    echo -e "${YELLOW}🏗️  Core Infrastructure Tests${NC}"
    run_test "Backup Server Service Status" "test_backup_service_status"
    run_test "Environment File Present" "test_environment_file"
    run_test "Git Repository Status" "test_git_repository"
    run_test "Python Dependencies" "test_python_dependencies"
    run_test "Log Files Present" "test_backup_logs_present"
    run_test "Backup Directories" "test_backup_directories"
    run_test "File Permissions" "test_file_permissions"
    
    # Network and Connectivity Tests
    echo -e "\n${YELLOW}🌐 Network and Connectivity Tests${NC}"
    run_test "Backup Server HTTP Health Check" "test_backup_server_connectivity"
    run_test "Backup Server WebSocket" "test_backup_server_websocket"
    run_test "Primary Server Connectivity" "test_primary_server_connectivity"
    run_test "Database Connectivity" "test_database_connectivity"
    run_test "Redis Connectivity" "test_redis_connectivity"
    
    # Configuration Tests
    echo -e "\n${YELLOW}⚙️  Configuration Tests${NC}"
    run_test "Nginx Configuration Valid" "test_nginx_configuration"
    run_test "SSL Certificates Present" "test_ssl_certificates"
    run_test "Sync Script Installed" "test_sync_script_exists"
    run_test "Health Monitor Installed" "test_health_monitor_exists"
    run_test "Cron Jobs Installed" "test_cron_jobs_installed"
    
    # System Health Tests
    echo -e "\n${YELLOW}🏥 System Health Tests${NC}"
    run_test "Disk Space Check" "test_disk_space"
    run_test "Memory Usage Check" "test_memory_usage"
    run_test "Load Average Check" "test_load_average"
    
    # Game Functionality Tests
    echo -e "\n${YELLOW}🎮 Game Functionality Tests${NC}"
    run_test "Game Client Connection" "test_game_client_connection"
    run_test "Failover Configuration" "test_failover_preparation"
    
    # Optional Monitoring Tests
    echo -e "\n${YELLOW}📊 Monitoring Tests (Optional)${NC}"
    run_test "Monitoring Endpoints" "test_monitoring_endpoints"
    
    # Test Summary
    echo ""
    echo -e "${BLUE}📊 Test Summary${NC}"
    echo "==============="
    echo -e "Tests Passed: ${GREEN}$TESTS_PASSED${NC}"
    echo -e "Tests Failed: ${RED}$TESTS_FAILED${NC}"
    echo -e "Total Tests: $((TESTS_PASSED + TESTS_FAILED))"
    
    if [ $TESTS_FAILED -eq 0 ]; then
        echo -e "\n${GREEN}🎉 All tests passed! Backup server is ready for production.${NC}"
        log "All tests passed successfully"
        exit 0
    else
        echo -e "\n${RED}❌ Some tests failed. Please review the following issues:${NC}"
        for failed_test in "${FAILED_TESTS[@]}"; do
            echo -e "  ${RED}•${NC} $failed_test"
        done
        echo -e "\nSee $TEST_LOG for detailed logs."
        log "Test suite completed with $TESTS_FAILED failures"
        exit 1
    fi
}

# Handle script arguments
case "${1:-test}" in
    "test")
        main
        ;;
    "connectivity")
        echo "Testing connectivity only..."
        run_test "Backup Server Connectivity" "test_backup_server_connectivity"
        run_test "Primary Server Connectivity" "test_primary_server_connectivity"
        ;;
    "service")
        echo "Testing service status..."
        run_test "Service Status" "test_backup_service_status"
        run_test "Health Check" "test_backup_server_connectivity"
        ;;
    "game")
        echo "Testing game functionality..."
        run_test "Game Client Connection" "test_game_client_connection"
        ;;
    *)
        echo "Usage: $0 {test|connectivity|service|game}"
        echo "  test         - Run full test suite (default)"
        echo "  connectivity - Test connectivity only"
        echo "  service      - Test service status only"
        echo "  game         - Test game functionality only"
        exit 1
        ;;
esac
