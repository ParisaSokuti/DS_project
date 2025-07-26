#!/bin/bash

# PostgreSQL Standby Promotion Script
# Script to promote a standby server to primary during failover

set -e

# Configuration variables
POSTGRES_DATA_DIR="/var/lib/postgresql/data"
POSTGRES_CONFIG_DIR="/etc/postgresql"
PROMOTE_TRIGGER_FILE="/tmp/promote_trigger"
POSTGRES_VERSION="15"  # Adjust based on your PostgreSQL version

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== PostgreSQL Standby Promotion Script ===${NC}"
echo

# Check if PostgreSQL is running
if ! systemctl is-active --quiet postgresql; then
    echo -e "${RED}PostgreSQL is not running. Starting PostgreSQL...${NC}"
    sudo systemctl start postgresql
    sleep 5
fi

# Check if this is a standby server
if ! sudo -u postgres psql -c "SELECT pg_is_in_recovery();" | grep -q "t"; then
    echo -e "${RED}This server is not in recovery mode (not a standby server).${NC}"
    echo "Promotion can only be performed on a standby server."
    exit 1
fi

# Display current replication status
echo -e "${YELLOW}Current replication status:${NC}"
sudo -u postgres psql -c "SELECT * FROM pg_stat_wal_receiver;"

# Check replication lag
echo -e "${YELLOW}Current replication lag:${NC}"
sudo -u postgres psql -c "SELECT CASE WHEN pg_last_wal_receive_lsn() = pg_last_wal_replay_lsn() THEN 0 ELSE EXTRACT (EPOCH FROM now() - pg_last_xact_replay_timestamp()) END AS lag_seconds;"

# Ask for confirmation
echo
echo -e "${YELLOW}WARNING: This will promote this standby server to primary.${NC}"
echo -e "${YELLOW}Make sure the original primary is down before proceeding.${NC}"
echo
read -p "Are you sure you want to promote this standby to primary? (yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    echo -e "${YELLOW}Promotion cancelled.${NC}"
    exit 0
fi

# Method 1: Using pg_ctl promote (recommended for newer PostgreSQL versions)
echo -e "${YELLOW}Promoting standby server using pg_ctl promote...${NC}"
if sudo -u postgres /usr/lib/postgresql/${POSTGRES_VERSION}/bin/pg_ctl promote -D ${POSTGRES_DATA_DIR}; then
    echo -e "${GREEN}pg_ctl promote command successful!${NC}"
else
    echo -e "${YELLOW}pg_ctl promote failed, trying trigger file method...${NC}"
    
    # Method 2: Using trigger file (fallback method)
    echo -e "${YELLOW}Creating promote trigger file...${NC}"
    sudo -u postgres touch ${PROMOTE_TRIGGER_FILE}
fi

# Wait for promotion to complete
echo -e "${YELLOW}Waiting for promotion to complete...${NC}"
sleep 10

# Check if promotion was successful
if sudo -u postgres psql -c "SELECT pg_is_in_recovery();" | grep -q "f"; then
    echo -e "${GREEN}Promotion successful! Server is now primary.${NC}"
else
    echo -e "${RED}Promotion failed or still in progress.${NC}"
    exit 1
fi

# Clean up standby.signal file
if [ -f "${POSTGRES_DATA_DIR}/standby.signal" ]; then
    echo -e "${YELLOW}Removing standby.signal file...${NC}"
    sudo -u postgres rm -f ${POSTGRES_DATA_DIR}/standby.signal
fi

# Apply primary configuration
echo -e "${YELLOW}Applying primary server configuration...${NC}"
sudo cp ./config/postgresql/primary.conf ${POSTGRES_CONFIG_DIR}/postgresql.conf

# Set proper permissions
sudo chown postgres:postgres ${POSTGRES_CONFIG_DIR}/postgresql.conf
sudo chmod 600 ${POSTGRES_CONFIG_DIR}/postgresql.conf

# Reload configuration
echo -e "${YELLOW}Reloading PostgreSQL configuration...${NC}"
sudo systemctl reload postgresql

# Verify primary status
echo -e "${YELLOW}Verifying primary status...${NC}"
sudo -u postgres psql -c "SELECT pg_is_in_recovery();"
sudo -u postgres psql -c "SHOW wal_level;"
sudo -u postgres psql -c "SHOW max_wal_senders;"

# Display final status
echo
echo -e "${GREEN}=== Promotion Complete ===${NC}"
echo -e "${GREEN}This server is now the primary PostgreSQL server.${NC}"
echo
echo -e "${YELLOW}Next steps:${NC}"
echo "1. Update application connection strings to point to this server"
echo "2. Update any load balancer or HAProxy configuration"
echo "3. Set up new standby servers if needed"
echo "4. Monitor the new primary server"
echo
echo -e "${YELLOW}New primary server details:${NC}"
echo "  Host: $(hostname -I | awk '{print $1}')"
echo "  Port: 5432"
echo "  Database: hokm_db"
echo "  Status: Primary (Read/Write)"
echo

echo -e "${GREEN}Promotion completed successfully!${NC}"
