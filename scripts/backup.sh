#!/bin/bash
# PostgreSQL backup script for Hokm Game Server

set -e

# Configuration
POSTGRES_DB=${POSTGRES_DB:-hokm_game}
POSTGRES_USER=${POSTGRES_USER:-hokm_admin}
POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-hokm_secure_2024!}
POSTGRES_HOST=${POSTGRES_HOST:-postgres-primary}
BACKUP_DIR=/backups
BACKUP_RETENTION_DAYS=${BACKUP_RETENTION_DAYS:-7}

# Create backup directory if it doesn't exist
mkdir -p $BACKUP_DIR

# Generate backup filename with timestamp
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="hokm_game_backup_${TIMESTAMP}.sql"
BACKUP_PATH="${BACKUP_DIR}/${BACKUP_FILE}"

echo "Starting PostgreSQL backup at $(date)"
echo "Database: $POSTGRES_DB"
echo "Host: $POSTGRES_HOST"
echo "Backup file: $BACKUP_PATH"

# Perform the backup
PGPASSWORD=$POSTGRES_PASSWORD pg_dump \
    -h $POSTGRES_HOST \
    -U $POSTGRES_USER \
    -d $POSTGRES_DB \
    --verbose \
    --clean \
    --if-exists \
    --create \
    --format=plain \
    --no-owner \
    --no-privileges \
    > $BACKUP_PATH

# Compress the backup
gzip $BACKUP_PATH
COMPRESSED_BACKUP="${BACKUP_PATH}.gz"

echo "Backup completed: $COMPRESSED_BACKUP"
echo "Backup size: $(du -h $COMPRESSED_BACKUP | cut -f1)"

# Clean up old backups
echo "Cleaning up backups older than $BACKUP_RETENTION_DAYS days..."
find $BACKUP_DIR -name "hokm_game_backup_*.sql.gz" -type f -mtime +$BACKUP_RETENTION_DAYS -delete

# List remaining backups
echo "Current backups:"
ls -lah $BACKUP_DIR/hokm_game_backup_*.sql.gz 2>/dev/null || echo "No backups found"

echo "Backup process completed at $(date)"
