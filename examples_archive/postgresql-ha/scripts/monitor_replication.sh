#!/bin/bash

# PostgreSQL Replication Monitoring Script
# Script to monitor the health and status of PostgreSQL streaming replication

set -e

# Configuration variables
POSTGRES_USER="postgres"
POSTGRES_DB="hokm_db"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to display header
show_header() {
    echo -e "${BLUE}================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}================================${NC}"
}

# Function to check if server is primary or standby
check_server_role() {
    local is_recovery=$(sudo -u postgres psql -t -c "SELECT pg_is_in_recovery();" | tr -d ' ')
    if [ "$is_recovery" = "f" ]; then
        echo -e "${GREEN}PRIMARY${NC}"
        return 0
    else
        echo -e "${YELLOW}STANDBY${NC}"
        return 1
    fi
}

# Function to monitor primary server
monitor_primary() {
    show_header "PRIMARY SERVER MONITORING"
    
    echo -e "${YELLOW}Server Role:${NC} $(check_server_role)"
    echo
    
    # Replication slots
    echo -e "${YELLOW}Replication Slots:${NC}"
    sudo -u postgres psql -c "SELECT slot_name, slot_type, active, restart_lsn, confirmed_flush_lsn FROM pg_replication_slots;"
    echo
    
    # Active replication connections
    echo -e "${YELLOW}Active Replication Connections:${NC}"
    sudo -u postgres psql -c "SELECT client_addr, client_hostname, state, sent_lsn, write_lsn, flush_lsn, replay_lsn, write_lag, flush_lag, replay_lag FROM pg_stat_replication;"
    echo
    
    # WAL status
    echo -e "${YELLOW}WAL Status:${NC}"
    sudo -u postgres psql -c "SELECT pg_current_wal_lsn() AS current_wal_lsn, pg_walfile_name(pg_current_wal_lsn()) AS current_wal_file;"
    echo
    
    # Database size
    echo -e "${YELLOW}Database Size:${NC}"
    sudo -u postgres psql -c "SELECT pg_database.datname, pg_size_pretty(pg_database_size(pg_database.datname)) AS size FROM pg_database WHERE datname = '${POSTGRES_DB}';"
    echo
}

# Function to monitor standby server
monitor_standby() {
    show_header "STANDBY SERVER MONITORING"
    
    echo -e "${YELLOW}Server Role:${NC} $(check_server_role)"
    echo
    
    # WAL receiver status
    echo -e "${YELLOW}WAL Receiver Status:${NC}"
    sudo -u postgres psql -c "SELECT pid, status, receive_start_lsn, receive_start_tli, received_lsn, received_tli, last_msg_send_time, last_msg_receipt_time, latest_end_lsn, latest_end_time, slot_name, sender_host, sender_port FROM pg_stat_wal_receiver;"
    echo
    
    # Replication lag
    echo -e "${YELLOW}Replication Lag:${NC}"
    sudo -u postgres psql -c "SELECT CASE WHEN pg_last_wal_receive_lsn() = pg_last_wal_replay_lsn() THEN 0 ELSE EXTRACT (EPOCH FROM now() - pg_last_xact_replay_timestamp()) END AS lag_seconds;"
    echo
    
    # Last replay timestamp
    echo -e "${YELLOW}Last Replay Timestamp:${NC}"
    sudo -u postgres psql -c "SELECT pg_last_xact_replay_timestamp() AS last_replay_timestamp;"
    echo
    
    # Recovery status
    echo -e "${YELLOW}Recovery Status:${NC}"
    sudo -u postgres psql -c "SELECT pg_last_wal_receive_lsn() AS last_received_lsn, pg_last_wal_replay_lsn() AS last_replayed_lsn, pg_last_xact_replay_timestamp() AS last_replay_time;"
    echo
}

# Function to show general server information
show_server_info() {
    show_header "SERVER INFORMATION"
    
    echo -e "${YELLOW}PostgreSQL Version:${NC}"
    sudo -u postgres psql -c "SELECT version();"
    echo
    
    echo -e "${YELLOW}Server Uptime:${NC}"
    sudo -u postgres psql -c "SELECT pg_postmaster_start_time();"
    echo
    
    echo -e "${YELLOW}Active Connections:${NC}"
    sudo -u postgres psql -c "SELECT count(*) FROM pg_stat_activity WHERE state = 'active';"
    echo
    
    echo -e "${YELLOW}Database Connections:${NC}"
    sudo -u postgres psql -c "SELECT datname, count(*) FROM pg_stat_activity GROUP BY datname ORDER BY count(*) DESC;"
    echo
}

# Function to show configuration
show_configuration() {
    show_header "REPLICATION CONFIGURATION"
    
    echo -e "${YELLOW}WAL Level:${NC}"
    sudo -u postgres psql -c "SHOW wal_level;"
    echo
    
    echo -e "${YELLOW}Max WAL Senders:${NC}"
    sudo -u postgres psql -c "SHOW max_wal_senders;"
    echo
    
    echo -e "${YELLOW}Hot Standby:${NC}"
    sudo -u postgres psql -c "SHOW hot_standby;"
    echo
    
    echo -e "${YELLOW}WAL Keep Size:${NC}"
    sudo -u postgres psql -c "SHOW wal_keep_size;"
    echo
}

# Function to show help
show_help() {
    echo -e "${GREEN}PostgreSQL Replication Monitoring Script${NC}"
    echo
    echo "Usage: $0 [option]"
    echo
    echo "Options:"
    echo "  -p, --primary    Monitor primary server"
    echo "  -s, --standby    Monitor standby server"
    echo "  -i, --info       Show server information"
    echo "  -c, --config     Show replication configuration"
    echo "  -a, --all        Show all monitoring information"
    echo "  -w, --watch      Watch mode (continuous monitoring)"
    echo "  -h, --help       Show this help message"
    echo
}

# Function to run all monitoring
monitor_all() {
    # Check if PostgreSQL is running
    if ! systemctl is-active --quiet postgresql; then
        echo -e "${RED}PostgreSQL is not running!${NC}"
        exit 1
    fi
    
    # Show server information
    show_server_info
    
    # Show configuration
    show_configuration
    
    # Check server role and show appropriate monitoring
    if check_server_role > /dev/null 2>&1; then
        monitor_primary
    else
        monitor_standby
    fi
}

# Function for watch mode
watch_mode() {
    while true; do
        clear
        echo -e "${BLUE}PostgreSQL Replication Monitoring - $(date)${NC}"
        echo
        monitor_all
        echo
        echo -e "${YELLOW}Press Ctrl+C to exit watch mode${NC}"
        sleep 10
    done
}

# Main script logic
case "$1" in
    -p|--primary)
        monitor_primary
        ;;
    -s|--standby)
        monitor_standby
        ;;
    -i|--info)
        show_server_info
        ;;
    -c|--config)
        show_configuration
        ;;
    -a|--all)
        monitor_all
        ;;
    -w|--watch)
        watch_mode
        ;;
    -h|--help)
        show_help
        ;;
    *)
        echo -e "${GREEN}PostgreSQL Replication Monitoring${NC}"
        echo "Use -h or --help for usage information"
        echo
        monitor_all
        ;;
esac
