#!/bin/bash

# Failover Testing Script
# Tests the keepalived and DNS-based failover mechanisms

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
PRIMARY_SERVER="192.168.1.26"     # Primary server IP
BACKUP_SERVER="192.168.1.27"      # Backup server IP
VIRTUAL_IP="192.168.1.25"         # Virtual IP (for keepalived)
GAME_PORT=8765                     # WebSocket port
TEST_TIMEOUT=60                    # Test timeout in seconds

# Test results
TESTS_PASSED=0
TESTS_FAILED=0
FAILED_TESTS=()

# Logging function
log() {
    echo -e "${BLUE}[$(date '+%H:%M:%S')]${NC} $1"
}

success() {
    TESTS_PASSED=$((TESTS_PASSED + 1))
    echo -e "${GREEN}✅ PASSED${NC}: $1"
}

failed() {
    TESTS_FAILED=$((TESTS_FAILED + 1))
    FAILED_TESTS+=("$1")
    echo -e "${RED}❌ FAILED${NC}: $1"
}

warning() {
    echo -e "${YELLOW}⚠️  WARNING${NC}: $1"
}

# Test server connectivity
test_server_connectivity() {
    local server="$1"
    local port="$2"
    local name="$3"
    
    if timeout 10 bash -c "cat < /dev/null > /dev/tcp/$server/$port" 2>/dev/null; then
        success "$name connectivity ($server:$port)"
        return 0
    else
        failed "$name connectivity ($server:$port)"
        return 1
    fi
}

# Test WebSocket health endpoint
test_health_endpoint() {
    local server="$1"
    local port="$2"
    local name="$3"
    
    if curl -f -s -m 10 "http://$server:$port/health" >/dev/null 2>&1; then
        success "$name health endpoint"
        return 0
    else
        failed "$name health endpoint"
        return 1
    fi
}

# Test game client connection
test_game_connection() {
    local server="$1"
    local port="$2"
    local name="$3"
    
    log "Testing game client connection to $name..."
    
    timeout 30 python3 << EOF
import asyncio
import websockets
import json
import sys

async def test_connection():
    try:
        uri = 'ws://$server:$port'
        async with websockets.connect(uri) as websocket:
            # Send a simple test message
            test_msg = {"type": "ping", "test": True}
            await websocket.send(json.dumps(test_msg))
            
            # Wait for any response (or timeout)
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=10)
                print("Received response from server")
                return True
            except asyncio.TimeoutError:
                # No response is okay for a ping
                print("No response to ping (this is normal)")
                return True
                
    except Exception as e:
        print(f"Connection test failed: {e}")
        return False

result = asyncio.run(test_connection())
sys.exit(0 if result else 1)
EOF

    if [ $? -eq 0 ]; then
        success "$name game client connection"
        return 0
    else
        failed "$name game client connection"
        return 1
    fi
}

# Test keepalived status
test_keepalived_status() {
    local server="$1"
    local name="$2"
    
    log "Testing keepalived status on $name..."
    
    if ssh -o ConnectTimeout=10 "$server" "systemctl is-active keepalived" >/dev/null 2>&1; then
        success "$name keepalived service running"
        
        # Check if it has the virtual IP
        if ssh "$server" "ip addr show | grep -q $VIRTUAL_IP" 2>/dev/null; then
            success "$name has virtual IP ($VIRTUAL_IP)"
            return 0
        else
            log "$name does not have virtual IP (normal for backup)"
            return 1
        fi
    else
        failed "$name keepalived service"
        return 1
    fi
}

# Test failover simulation
test_failover_simulation() {
    log "Testing failover simulation..."
    
    # Find which server currently has the VIP
    local current_master=""
    if ssh "$PRIMARY_SERVER" "ip addr show | grep -q $VIRTUAL_IP" 2>/dev/null; then
        current_master="$PRIMARY_SERVER"
        local standby_server="$BACKUP_SERVER"
    elif ssh "$BACKUP_SERVER" "ip addr show | grep -q $VIRTUAL_IP" 2>/dev/null; then
        current_master="$BACKUP_SERVER"
        local standby_server="$PRIMARY_SERVER"
    else
        failed "No server has virtual IP"
        return 1
    fi
    
    log "Current master: $current_master, Standby: $standby_server"
    
    # Stop keepalived on current master to trigger failover
    log "Stopping keepalived on master to trigger failover..."
    ssh "$current_master" "sudo systemctl stop keepalived" 2>/dev/null || true
    
    # Wait for failover to complete
    log "Waiting for failover to complete (30 seconds)..."
    sleep 30
    
    # Check if standby now has the VIP
    if ssh "$standby_server" "ip addr show | grep -q $VIRTUAL_IP" 2>/dev/null; then
        success "Failover completed - standby now has VIP"
        
        # Test connectivity through VIP
        if test_server_connectivity "$VIRTUAL_IP" "$GAME_PORT" "Virtual IP after failover"; then
            success "Virtual IP connectivity after failover"
        fi
        
        # Restart keepalived on original master
        log "Restarting keepalived on original master..."
        ssh "$current_master" "sudo systemctl start keepalived" 2>/dev/null || true
        
        # Wait for potential failback
        sleep 20
        
        success "Failover simulation completed"
        return 0
    else
        failed "Failover did not complete - standby does not have VIP"
        
        # Restart keepalived on original master
        ssh "$current_master" "sudo systemctl start keepalived" 2>/dev/null || true
        return 1
    fi
}

# Test DNS failover (if script exists)
test_dns_failover() {
    if [ -x "./dns_failover_monitor.sh" ]; then
        log "Testing DNS failover script..."
        
        if ./dns_failover_monitor.sh test >/dev/null 2>&1; then
            success "DNS failover script test"
        else
            failed "DNS failover script test"
        fi
    else
        warning "DNS failover script not found, skipping"
    fi
}

# Main test function
run_all_tests() {
    echo -e "${BLUE}🧪 Hokm Game Failover Testing${NC}"
    echo "====================================="
    echo ""
    
    log "Starting comprehensive failover tests..."
    
    echo -e "\n${YELLOW}📡 Basic Connectivity Tests${NC}"
    echo "--------------------------------"
    test_server_connectivity "$PRIMARY_SERVER" "$GAME_PORT" "Primary server"
    test_server_connectivity "$BACKUP_SERVER" "$GAME_PORT" "Backup server"
    test_server_connectivity "$VIRTUAL_IP" "$GAME_PORT" "Virtual IP"
    
    echo -e "\n${YELLOW}🏥 Health Endpoint Tests${NC}"
    echo "----------------------------"
    test_health_endpoint "$PRIMARY_SERVER" "$GAME_PORT" "Primary server"
    test_health_endpoint "$BACKUP_SERVER" "$GAME_PORT" "Backup server"
    test_health_endpoint "$VIRTUAL_IP" "$GAME_PORT" "Virtual IP"
    
    echo -e "\n${YELLOW}🎮 Game Connection Tests${NC}"
    echo "----------------------------"
    test_game_connection "$PRIMARY_SERVER" "$GAME_PORT" "Primary server"
    test_game_connection "$BACKUP_SERVER" "$GAME_PORT" "Backup server"
    test_game_connection "$VIRTUAL_IP" "$GAME_PORT" "Virtual IP"
    
    echo -e "\n${YELLOW}🔧 Keepalived Service Tests${NC}"
    echo "------------------------------"
    test_keepalived_status "$PRIMARY_SERVER" "Primary server"
    test_keepalived_status "$BACKUP_SERVER" "Backup server"
    
    echo -e "\n${YELLOW}🔄 Failover Simulation${NC}"
    echo "-------------------------"
    read -p "Do you want to test failover simulation? This will temporarily disrupt service. (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        test_failover_simulation
    else
        warning "Failover simulation skipped by user"
    fi
    
    echo -e "\n${YELLOW}🌐 DNS Failover Tests${NC}"
    echo "------------------------"
    test_dns_failover
    
    # Test Summary
    echo ""
    echo -e "${BLUE}📊 Test Summary${NC}"
    echo "=================="
    echo -e "Tests Passed: ${GREEN}$TESTS_PASSED${NC}"
    echo -e "Tests Failed: ${RED}$TESTS_FAILED${NC}"
    echo -e "Total Tests: $((TESTS_PASSED + TESTS_FAILED))"
    
    if [ $TESTS_FAILED -eq 0 ]; then
        echo -e "\n${GREEN}🎉 All tests passed! Failover system is working correctly.${NC}"
        return 0
    else
        echo -e "\n${RED}❌ Some tests failed. Please review the following issues:${NC}"
        for failed_test in "${FAILED_TESTS[@]}"; do
            echo -e "  ${RED}•${NC} $failed_test"
        done
        return 1
    fi
}

# Handle command line arguments
case "${1:-all}" in
    "all")
        run_all_tests
        ;;
    "connectivity")
        echo "Testing basic connectivity..."
        test_server_connectivity "$PRIMARY_SERVER" "$GAME_PORT" "Primary server"
        test_server_connectivity "$BACKUP_SERVER" "$GAME_PORT" "Backup server"
        test_server_connectivity "$VIRTUAL_IP" "$GAME_PORT" "Virtual IP"
        ;;
    "health")
        echo "Testing health endpoints..."
        test_health_endpoint "$PRIMARY_SERVER" "$GAME_PORT" "Primary server"
        test_health_endpoint "$BACKUP_SERVER" "$GAME_PORT" "Backup server"
        test_health_endpoint "$VIRTUAL_IP" "$GAME_PORT" "Virtual IP"
        ;;
    "game")
        echo "Testing game connections..."
        test_game_connection "$VIRTUAL_IP" "$GAME_PORT" "Virtual IP"
        ;;
    "keepalived")
        echo "Testing keepalived services..."
        test_keepalived_status "$PRIMARY_SERVER" "Primary server"
        test_keepalived_status "$BACKUP_SERVER" "Backup server"
        ;;
    "failover")
        echo "Testing failover simulation..."
        test_failover_simulation
        ;;
    *)
        echo "Usage: $0 {all|connectivity|health|game|keepalived|failover}"
        echo "  all          - Run all tests (default)"
        echo "  connectivity - Test basic connectivity"
        echo "  health       - Test health endpoints"
        echo "  game         - Test game connections"
        echo "  keepalived   - Test keepalived services"
        echo "  failover     - Test failover simulation"
        exit 1
        ;;
esac
