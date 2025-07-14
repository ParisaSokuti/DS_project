#!/bin/bash

# PostgreSQL Standby Server Initialization Script
# This script is run during container startup to initialize the standby server

set -e

echo "Initializing standby server..."

# Wait for primary server to be ready
echo "Waiting for primary server to be ready..."
while ! pg_isready -h postgres-primary -p 5432 -U hokm_user; do
    echo "Primary server not ready, waiting..."
    sleep 5
done

echo "Primary server is ready!"

# Check if this is the first run
if [ ! -f /var/lib/postgresql/data/pgdata/PG_VERSION ]; then
    echo "First run detected, creating base backup..."
    
    # Create base backup from primary
    pg_basebackup -h postgres-primary -p 5432 -U replicator -D /var/lib/postgresql/data/pgdata -P -v -R
    
    # Create standby.signal file
    touch /var/lib/postgresql/data/pgdata/standby.signal
    
    # Configure connection to primary
    cat >> /var/lib/postgresql/data/pgdata/postgresql.auto.conf << EOF
# Standby server configuration
primary_conninfo = 'host=postgres-primary port=5432 user=replicator password=replicator_password application_name=standby'
primary_slot_name = 'replica_slot_1'
promote_trigger_file = '/tmp/promote_trigger'
EOF
    
    # Set proper permissions
    chown -R postgres:postgres /var/lib/postgresql/data/pgdata
    chmod 700 /var/lib/postgresql/data/pgdata
    
    echo "Base backup completed successfully!"
else
    echo "Data directory already exists, skipping base backup..."
fi

echo "Standby server initialization completed!"
