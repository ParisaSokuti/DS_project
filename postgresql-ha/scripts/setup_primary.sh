#!/bin/bash

# PostgreSQL Streaming Replication Setup Script - Primary Server
# Script to configure the primary PostgreSQL server for streaming replication

set -e

# Configuration variables
POSTGRES_USER="postgres"
POSTGRES_DB="hokm_db"
REPLICATION_USER="replicator"
REPLICATION_PASSWORD="replicator_password_change_me"
POSTGRES_DATA_DIR="/var/lib/postgresql/data"
POSTGRES_CONFIG_DIR="/etc/postgresql"
WAL_ARCHIVE_DIR="/var/lib/postgresql/wal_archive"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== PostgreSQL Streaming Replication Setup - Primary Server ===${NC}"
echo

# Check if PostgreSQL is running
if ! systemctl is-active --quiet postgresql; then
    echo -e "${RED}PostgreSQL is not running. Starting PostgreSQL...${NC}"
    sudo systemctl start postgresql
    sleep 5
fi

# Create replication user
echo -e "${YELLOW}Creating replication user...${NC}"
sudo -u postgres psql -c "CREATE USER ${REPLICATION_USER} WITH REPLICATION ENCRYPTED PASSWORD '${REPLICATION_PASSWORD}';" || true

# Create WAL archive directory
echo -e "${YELLOW}Creating WAL archive directory...${NC}"
sudo mkdir -p ${WAL_ARCHIVE_DIR}
sudo chown postgres:postgres ${WAL_ARCHIVE_DIR}
sudo chmod 700 ${WAL_ARCHIVE_DIR}

# Backup original configuration files
echo -e "${YELLOW}Backing up original configuration files...${NC}"
sudo cp ${POSTGRES_CONFIG_DIR}/postgresql.conf ${POSTGRES_CONFIG_DIR}/postgresql.conf.backup.$(date +%Y%m%d_%H%M%S) || true
sudo cp ${POSTGRES_CONFIG_DIR}/pg_hba.conf ${POSTGRES_CONFIG_DIR}/pg_hba.conf.backup.$(date +%Y%m%d_%H%M%S) || true

# Copy replication configuration
echo -e "${YELLOW}Applying replication configuration...${NC}"
sudo cp ./config/postgresql/primary.conf ${POSTGRES_CONFIG_DIR}/postgresql.conf
sudo cp ./config/postgresql/pg_hba_replication.conf ${POSTGRES_CONFIG_DIR}/pg_hba.conf

# Set proper permissions
sudo chown postgres:postgres ${POSTGRES_CONFIG_DIR}/postgresql.conf
sudo chown postgres:postgres ${POSTGRES_CONFIG_DIR}/pg_hba.conf
sudo chmod 600 ${POSTGRES_CONFIG_DIR}/postgresql.conf
sudo chmod 600 ${POSTGRES_CONFIG_DIR}/pg_hba.conf

# Create replication slot
echo -e "${YELLOW}Creating replication slot...${NC}"
sudo -u postgres psql -c "SELECT pg_create_physical_replication_slot('replica_slot_1');" || true

# Test configuration
echo -e "${YELLOW}Testing PostgreSQL configuration...${NC}"
if sudo -u postgres /usr/lib/postgresql/*/bin/postgres --config-file=${POSTGRES_CONFIG_DIR}/postgresql.conf --check; then
    echo -e "${GREEN}Configuration test passed!${NC}"
else
    echo -e "${RED}Configuration test failed!${NC}"
    exit 1
fi

# Reload PostgreSQL configuration
echo -e "${YELLOW}Reloading PostgreSQL configuration...${NC}"
sudo systemctl reload postgresql

# Verify replication settings
echo -e "${YELLOW}Verifying replication settings...${NC}"
sudo -u postgres psql -c "SHOW wal_level;"
sudo -u postgres psql -c "SHOW max_wal_senders;"
sudo -u postgres psql -c "SHOW hot_standby;"
sudo -u postgres psql -c "SELECT slot_name, active, restart_lsn FROM pg_replication_slots;"

# Display connection information
echo
echo -e "${GREEN}=== Primary Server Configuration Complete ===${NC}"
echo -e "${YELLOW}Primary server is ready for replication.${NC}"
echo
echo -e "${YELLOW}Connection details for standby servers:${NC}"
echo "  Host: $(hostname -I | awk '{print $1}')"
echo "  Port: 5432"
echo "  Replication User: ${REPLICATION_USER}"
echo "  Replication Password: ${REPLICATION_PASSWORD}"
echo "  Database: ${POSTGRES_DB}"
echo
echo -e "${YELLOW}Next steps:${NC}"
echo "1. Run setup_standby.sh on each standby server"
echo "2. Monitor replication status with: sudo -u postgres psql -c \"SELECT * FROM pg_stat_replication;\""
echo "3. Test failover procedures"
echo

echo -e "${GREEN}Primary server setup completed successfully!${NC}"
