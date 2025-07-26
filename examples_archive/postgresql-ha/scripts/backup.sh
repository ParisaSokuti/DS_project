#!/bin/bash

# PostgreSQL HA Backup Script
# This script performs automated backups with WAL archiving integration

set -euo pipefail

# Configuration
BACKUP_TYPE="${1:-full}"  # full, incremental, or wal
BACKUP_DIR="${BACKUP_DIR:-/backup/postgresql}"
S3_BUCKET="${S3_BUCKET:-}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"
COMPRESSION="${COMPRESSION:-gzip}"
NOTIFICATION_WEBHOOK="${NOTIFICATION_WEBHOOK:-}"

# PostgreSQL connection settings
PGHOST="${PGHOST:-postgresql-primary}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-postgres}"
PGDATABASE="${PGDATABASE:-hokm_game}"

# Logging
LOG_FILE="/var/log/postgresql-backup.log"
exec 1> >(tee -a "$LOG_FILE")
exec 2> >(tee -a "$LOG_FILE" >&2)

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

# Notification function
notify() {
    local status="$1"
    local message="$2"
    
    if [[ -n "$NOTIFICATION_WEBHOOK" ]]; then
        curl -X POST "$NOTIFICATION_WEBHOOK" \
            -H "Content-Type: application/json" \
            -d "{\"status\": \"$status\", \"message\": \"$message\", \"timestamp\": \"$(date -Iseconds)\"}" \
            || log "WARNING: Failed to send notification"
    fi
}

# Cleanup old backups
cleanup_old_backups() {
    log "Cleaning up backups older than $RETENTION_DAYS days"
    
    find "$BACKUP_DIR" -type f -name "*.sql*" -mtime +$RETENTION_DAYS -delete || true
    find "$BACKUP_DIR" -type f -name "*.tar*" -mtime +$RETENTION_DAYS -delete || true
    find "$BACKUP_DIR/wal" -type f -name "*" -mtime +$RETENTION_DAYS -delete || true
    
    if [[ -n "$S3_BUCKET" ]]; then
        # Clean up S3 backups (requires AWS CLI)
        aws s3api list-objects-v2 --bucket "$S3_BUCKET" --prefix "postgresql-backup/" \
            --query "Contents[?LastModified<='$(date -d "$RETENTION_DAYS days ago" -Iseconds)'].Key" \
            --output text | xargs -r -n1 aws s3 rm "s3://$S3_BUCKET/"
    fi
}

# Full backup using pg_dump
full_backup() {
    local timestamp=$(date '+%Y%m%d_%H%M%S')
    local backup_file="$BACKUP_DIR/full_backup_${timestamp}.sql"
    
    log "Starting full backup to $backup_file"
    
    # Create backup directory
    mkdir -p "$BACKUP_DIR"
    
    # Perform backup
    pg_dump \
        --host="$PGHOST" \
        --port="$PGPORT" \
        --username="$PGUSER" \
        --dbname="$PGDATABASE" \
        --verbose \
        --no-password \
        --format=custom \
        --compress=9 \
        --file="$backup_file.custom" \
        || { log "ERROR: Full backup failed"; notify "error" "Full backup failed"; exit 1; }
    
    # Create SQL dump for easier restore
    pg_dump \
        --host="$PGHOST" \
        --port="$PGPORT" \
        --username="$PGUSER" \
        --dbname="$PGDATABASE" \
        --no-password \
        --file="$backup_file" \
        || { log "ERROR: SQL dump failed"; notify "error" "SQL dump failed"; exit 1; }
    
    # Compress SQL dump
    if [[ "$COMPRESSION" == "gzip" ]]; then
        gzip "$backup_file"
        backup_file="${backup_file}.gz"
    fi
    
    # Upload to S3 if configured
    if [[ -n "$S3_BUCKET" ]]; then
        log "Uploading backup to S3"
        aws s3 cp "$backup_file" "s3://$S3_BUCKET/postgresql-backup/full/" \
            || { log "WARNING: S3 upload failed"; notify "warning" "S3 upload failed"; }
        aws s3 cp "${backup_file}.custom" "s3://$S3_BUCKET/postgresql-backup/full/" \
            || { log "WARNING: S3 upload failed"; notify "warning" "S3 upload failed"; }
    fi
    
    local backup_size=$(du -h "$backup_file" | cut -f1)
    log "Full backup completed successfully. Size: $backup_size"
    notify "success" "Full backup completed successfully. Size: $backup_size"
}

# WAL archiving backup
wal_backup() {
    local wal_file="$1"
    local wal_backup_dir="$BACKUP_DIR/wal"
    
    mkdir -p "$wal_backup_dir"
    
    # Copy WAL file
    cp "$wal_file" "$wal_backup_dir/" || {
        log "ERROR: Failed to copy WAL file $wal_file"
        exit 1
    }
    
    # Upload to S3 if configured
    if [[ -n "$S3_BUCKET" ]]; then
        aws s3 cp "$wal_file" "s3://$S3_BUCKET/postgresql-backup/wal/" \
            || log "WARNING: WAL S3 upload failed"
    fi
    
    log "WAL file $(basename "$wal_file") archived successfully"
}

# Incremental backup using WAL-E or similar
incremental_backup() {
    log "Incremental backups require WAL-E or similar tool"
    log "This is a placeholder for incremental backup implementation"
    
    # Example with WAL-E (requires configuration)
    # wal-e backup-push /var/lib/postgresql/data
    
    notify "info" "Incremental backup placeholder executed"
}

# Base backup for replicas
base_backup() {
    local timestamp=$(date '+%Y%m%d_%H%M%S')
    local backup_dir="$BACKUP_DIR/base_backup_${timestamp}"
    
    log "Starting base backup to $backup_dir"
    
    mkdir -p "$backup_dir"
    
    pg_basebackup \
        --host="$PGHOST" \
        --port="$PGPORT" \
        --username="replicator" \
        --pgdata="$backup_dir" \
        --format=tar \
        --compress=9 \
        --checkpoint=fast \
        --label="hokm_base_backup_${timestamp}" \
        --progress \
        --verbose \
        || { log "ERROR: Base backup failed"; notify "error" "Base backup failed"; exit 1; }
    
    # Upload to S3 if configured
    if [[ -n "$S3_BUCKET" ]]; then
        log "Uploading base backup to S3"
        aws s3 sync "$backup_dir" "s3://$S3_BUCKET/postgresql-backup/base/" \
            || { log "WARNING: Base backup S3 upload failed"; notify "warning" "Base backup S3 upload failed"; }
    fi
    
    local backup_size=$(du -sh "$backup_dir" | cut -f1)
    log "Base backup completed successfully. Size: $backup_size"
    notify "success" "Base backup completed successfully. Size: $backup_size"
}

# Verify backup integrity
verify_backup() {
    local backup_file="$1"
    
    log "Verifying backup integrity: $backup_file"
    
    if [[ "$backup_file" == *.custom ]]; then
        # Verify custom format backup
        pg_restore --list "$backup_file" > /dev/null || {
            log "ERROR: Backup verification failed for $backup_file"
            notify "error" "Backup verification failed"
            return 1
        }
    elif [[ "$backup_file" == *.sql* ]]; then
        # Basic SQL file check
        head -n 10 "$backup_file" | grep -q "PostgreSQL database dump" || {
            log "ERROR: SQL backup verification failed for $backup_file"
            notify "error" "SQL backup verification failed"
            return 1
        }
    fi
    
    log "Backup verification successful for $backup_file"
    return 0
}

# Main execution
main() {
    log "Starting PostgreSQL backup - Type: $BACKUP_TYPE"
    
    case "$BACKUP_TYPE" in
        "full")
            full_backup
            ;;
        "incremental")
            incremental_backup
            ;;
        "wal")
            if [[ $# -gt 1 ]]; then
                wal_backup "$2"
            else
                log "ERROR: WAL file path required for WAL backup"
                exit 1
            fi
            ;;
        "base")
            base_backup
            ;;
        *)
            log "ERROR: Unknown backup type: $BACKUP_TYPE"
            log "Usage: $0 {full|incremental|wal|base} [wal_file_path]"
            exit 1
            ;;
    esac
    
    # Cleanup old backups
    cleanup_old_backups
    
    log "Backup process completed successfully"
}

# Trap for cleanup on exit
trap 'log "Backup script interrupted"' INT TERM

# Execute main function
main "$@"
