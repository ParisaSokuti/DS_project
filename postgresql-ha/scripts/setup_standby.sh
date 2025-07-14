#!/bin/bash

# PostgreSQL Streaming Replication Setup Script - Standby Server
# Script to configure a standby PostgreSQL server for streaming replication

set -e

# Configuration variables (adjust these for your environment)
PRIMARY_HOST="192.168.1.100"  # Change to your primary server IP
PRIMARY_PORT="5432"
POSTGRES_USER="postgres"
POSTGRES_DB="hokm_db"
REPLICATION_USER="replicator"
REPLICATION_PASSWORD="replicator_password_change_me"
POSTGRES_DATA_DIR="/var/lib/postgresql/data"
POSTGRES_CONFIG_DIR="/etc/postgresql"
POSTGRES_VERSION="15"  # Adjust based on your PostgreSQL version

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== PostgreSQL Streaming Replication Setup - Standby Server ===${NC}"
echo

# Check if user provided primary server IP
if [ "$1" != "" ]; then
    PRIMARY_HOST="$1"
fi

echo -e "${YELLOW}Primary server: ${PRIMARY_HOST}:${PRIMARY_PORT}${NC}"
echo

# Stop PostgreSQL if running
if systemctl is-active --quiet postgresql; then
    echo -e "${YELLOW}Stopping PostgreSQL...${NC}"
    sudo systemctl stop postgresql
fi

# Test connection to primary server
echo -e "${YELLOW}Testing connection to primary server...${NC}"
if pg_isready -h ${PRIMARY_HOST} -p ${PRIMARY_PORT} -U ${POSTGRES_USER}; then
    echo -e "${GREEN}Connection to primary server successful!${NC}"
else
    echo -e "${RED}Cannot connect to primary server. Please check:${NC}"
    echo "  - Primary server is running"
    echo "  - Network connectivity"
    echo "  - pg_hba.conf allows connections from this IP"
    exit 1
fi

# Backup existing data directory
if [ -d "${POSTGRES_DATA_DIR}" ]; then
    echo -e "${YELLOW}Backing up existing data directory...${NC}"
    sudo mv ${POSTGRES_DATA_DIR} ${POSTGRES_DATA_DIR}.backup.$(date +%Y%m%d_%H%M%S)
fi

# Create new data directory
echo -e "${YELLOW}Creating new data directory...${NC}"
sudo mkdir -p ${POSTGRES_DATA_DIR}
sudo chown postgres:postgres ${POSTGRES_DATA_DIR}
sudo chmod 700 ${POSTGRES_DATA_DIR}

# Run pg_basebackup to clone primary server
echo -e "${YELLOW}Running pg_basebackup to clone primary server...${NC}"
echo "This may take several minutes depending on database size..."

sudo -u postgres pg_basebackup \
    -h ${PRIMARY_HOST} \
    -p ${PRIMARY_PORT} \
    -U ${REPLICATION_USER} \
    -D ${POSTGRES_DATA_DIR} \
    -P \
    -v \
    -R \
    -W

if [ $? -eq 0 ]; then
    echo -e "${GREEN}pg_basebackup completed successfully!${NC}"
else
    echo -e "${RED}pg_basebackup failed!${NC}"
    exit 1
fi

# Apply standby-specific configuration
echo -e "${YELLOW}Applying standby configuration...${NC}"
sudo cp ./config/postgresql/standby.conf ${POSTGRES_CONFIG_DIR}/postgresql.conf
sudo cp ./config/postgresql/pg_hba_replication.conf ${POSTGRES_CONFIG_DIR}/pg_hba.conf

# Set proper permissions
sudo chown postgres:postgres ${POSTGRES_CONFIG_DIR}/postgresql.conf
sudo chown postgres:postgres ${POSTGRES_CONFIG_DIR}/pg_hba.conf
sudo chmod 600 ${POSTGRES_CONFIG_DIR}/postgresql.conf
sudo chmod 600 ${POSTGRES_CONFIG_DIR}/pg_hba.conf

# For PostgreSQL 12+, create standby.signal file
echo -e "${YELLOW}Creating standby.signal file...${NC}"
sudo -u postgres touch ${POSTGRES_DATA_DIR}/standby.signal

# Create or update postgresql.auto.conf for standby settings
echo -e "${YELLOW}Configuring standby connection settings...${NC}"
sudo -u postgres bash -c "cat > ${POSTGRES_DATA_DIR}/postgresql.auto.conf << EOF
# Standby server configuration
primary_conninfo = 'host=${PRIMARY_HOST} port=${PRIMARY_PORT} user=${REPLICATION_USER} password=${REPLICATION_PASSWORD} application_name=standby_$(hostname)'
primary_slot_name = 'replica_slot_1'
promote_trigger_file = '/tmp/promote_trigger'
EOF"

# Set proper permissions
sudo chown postgres:postgres ${POSTGRES_DATA_DIR}/postgresql.auto.conf
sudo chmod 600 ${POSTGRES_DATA_DIR}/postgresql.auto.conf

# Test configuration
echo -e "${YELLOW}Testing PostgreSQL configuration...${NC}"
if sudo -u postgres /usr/lib/postgresql/${POSTGRES_VERSION}/bin/postgres --config-file=${POSTGRES_CONFIG_DIR}/postgresql.conf --check; then
    echo -e "${GREEN}Configuration test passed!${NC}"
else
    echo -e "${RED}Configuration test failed!${NC}"
    exit 1
fi

# Start PostgreSQL
echo -e "${YELLOW}Starting PostgreSQL standby server...${NC}"
sudo systemctl start postgresql

# Wait for startup
sleep 10

# Verify standby status
echo -e "${YELLOW}Verifying standby status...${NC}"
if sudo -u postgres psql -c "SELECT pg_is_in_recovery();" | grep -q "t"; then
    echo -e "${GREEN}Standby server is in recovery mode - SUCCESS!${NC}"
else
    echo -e "${RED}Standby server is NOT in recovery mode - FAILED!${NC}"
    exit 1
fi

# Display replication lag
echo -e "${YELLOW}Checking replication lag...${NC}"
sudo -u postgres psql -c "SELECT CASE WHEN pg_last_wal_receive_lsn() = pg_last_wal_replay_lsn() THEN 0 ELSE EXTRACT (EPOCH FROM now() - pg_last_xact_replay_timestamp()) END AS lag_seconds;"

# Display connection information
echo
echo -e "${GREEN}=== Standby Server Configuration Complete ===${NC}"
echo -e "${YELLOW}Standby server is ready and receiving replication from primary.${NC}"
echo
echo -e "${YELLOW}Connection details:${NC}"
echo "  Standby Host: $(hostname -I | awk '{print $1}')"
echo "  Standby Port: 5432"
echo "  Primary Host: ${PRIMARY_HOST}"
echo "  Primary Port: ${PRIMARY_PORT}"
echo "  Application Name: standby_$(hostname)"
echo
echo -e "${YELLOW}Monitoring commands:${NC}"
echo "  Check replication status: sudo -u postgres psql -c \"SELECT * FROM pg_stat_wal_receiver;\""
echo "  Check lag: sudo -u postgres psql -c \"SELECT EXTRACT(EPOCH FROM now() - pg_last_xact_replay_timestamp()) AS lag_seconds;\""
echo "  Promote to primary: touch /tmp/promote_trigger"
echo

echo -e "${GREEN}Standby server setup completed successfully!${NC}"
