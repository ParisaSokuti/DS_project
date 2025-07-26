#!/bin/bash
# PostgreSQL Streaming Replication Setup Script
# Demonstrates fault tolerance for Hokm Game

echo "🏗️  Setting up PostgreSQL Streaming Replication for Fault Tolerance Demo"
echo "=================================================================="

# Variables
PRIMARY_DATA_DIR="/var/lib/postgresql/13/main"
STANDBY_DATA_DIR="/var/lib/postgresql/standby"
REPLICATION_USER="replicator"
REPLICATION_SLOT="standby_slot_1"

echo "📋 Step 1: Creating replication user on primary server"
sudo -u postgres psql -c "CREATE USER $REPLICATION_USER WITH REPLICATION ENCRYPTED PASSWORD 'repl_password123';"

echo "📋 Step 2: Creating replication slot on primary server"
sudo -u postgres psql -c "SELECT pg_create_physical_replication_slot('$REPLICATION_SLOT');"

echo "📋 Step 3: Creating base backup for standby server"
sudo -u postgres pg_basebackup -h localhost -D $STANDBY_DATA_DIR -U $REPLICATION_USER -v -P -W

echo "📋 Step 4: Setting up standby.signal file (PostgreSQL 12+)"
sudo -u postgres touch "$STANDBY_DATA_DIR/standby.signal"

echo "📋 Step 5: Creating recovery configuration"
cat > /tmp/recovery_settings.conf << EOF
# Recovery settings for standby server
primary_conninfo = 'host=127.0.0.1 port=5432 user=$REPLICATION_USER password=repl_password123 application_name=standby1'
primary_slot_name = '$REPLICATION_SLOT'
restore_command = ''
EOF

sudo -u postgres cp /tmp/recovery_settings.conf "$STANDBY_DATA_DIR/postgresql.auto.conf"

echo "📋 Step 6: Setting permissions"
sudo chown -R postgres:postgres $STANDBY_DATA_DIR

echo "✅ PostgreSQL Streaming Replication setup complete!"
echo ""
echo "🚀 To start the servers:"
echo "1. Primary:  sudo systemctl start postgresql"
echo "2. Standby:  sudo -u postgres pg_ctl start -D $STANDBY_DATA_DIR"
echo ""
echo "📊 To monitor replication:"
echo "   sudo -u postgres psql -c \"SELECT * FROM pg_stat_replication;\""
echo ""
echo "🔧 To promote standby to primary:"
echo "   sudo -u postgres pg_ctl promote -D $STANDBY_DATA_DIR"
