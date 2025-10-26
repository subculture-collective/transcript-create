#!/usr/bin/env bash
# =============================================================================
# Database Restore Script for transcript-create
# =============================================================================
# Restores PostgreSQL database from backup files created by backup_db.sh
# Supports:
# - Full database restore from compressed dumps
# - Encrypted backup restore (GPG)
# - Checksum verification before restore
# - Point-in-time recovery (PITR) with WAL archives
#
# Usage:
#   ./restore_db.sh --backup-file <path>           # Full restore from backup
#   ./restore_db.sh --list-backups                 # List available backups
#   ./restore_db.sh --pitr --target-time <time>    # Point-in-time recovery
#
# Environment Variables:
#   DATABASE_URL       - PostgreSQL connection string (required)
#   BACKUP_DIR         - Backup storage directory (default: /backups)
#   WAL_ARCHIVE_DIR    - WAL archive directory for PITR (default: /backups/wal_archive)
# =============================================================================

set -euo pipefail

# Configuration
BACKUP_DIR="${BACKUP_DIR:-/backups}"
WAL_ARCHIVE_DIR="${WAL_ARCHIVE_DIR:-/backups/wal_archive}"

# Parse command line arguments
BACKUP_FILE=""
LIST_BACKUPS=false
PITR_MODE=false
TARGET_TIME=""
FORCE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --backup-file)
            BACKUP_FILE="$2"
            shift 2
            ;;
        --list-backups)
            LIST_BACKUPS=true
            shift
            ;;
        --pitr)
            PITR_MODE=true
            shift
            ;;
        --target-time)
            TARGET_TIME="$2"
            shift 2
            ;;
        --force)
            FORCE=true
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --backup-file <path>      Path to backup file to restore"
            echo "  --list-backups            List all available backups"
            echo "  --pitr                    Enable Point-in-Time Recovery mode"
            echo "  --target-time <time>      Target timestamp for PITR (ISO 8601 format)"
            echo "  --force                   Skip confirmation prompts"
            echo "  -h, --help                Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0 --list-backups"
            echo "  $0 --backup-file /backups/daily/transcripts_daily_20241026_020000.sql.gz"
            echo "  $0 --pitr --target-time '2024-10-26 01:30:00'"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Logging function
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

# List backups function
list_backups() {
    log "=== Available Backups ==="
    
    for backup_type in daily weekly monthly; do
        backup_dir="${BACKUP_DIR}/${backup_type}"
        if [[ ! -d "$backup_dir" ]]; then
            continue
        fi
        
        echo ""
        echo "${backup_type^} Backups:"
        echo "----------------------------------------"
        
        backups=()
        while IFS= read -r -d '' backup_file; do
            backups+=("$backup_file")
        done < <(find "${backup_dir}" -name "*.sql.gz" -o -name "*.sql.gz.gpg" -print0 2>/dev/null | sort -z)
        
        if [[ ${#backups[@]} -eq 0 ]]; then
            echo "  No backups found"
            continue
        fi
        
        for backup_file in "${backups[@]}"; do
            size=$(du -h "${backup_file}" | cut -f1)
            timestamp=$(stat -c %y "${backup_file}" | cut -d'.' -f1)
            checksum_exists="✗"
            if [[ -f "${backup_file}.sha256" ]]; then
                checksum_exists="✓"
            fi
            echo "  ${backup_file}"
            echo "    Size: ${size} | Date: ${timestamp} | Checksum: ${checksum_exists}"
        done
    done
    
    echo ""
}

# Verify required environment variables
if [[ -z "${DATABASE_URL:-}" ]]; then
    echo "ERROR: DATABASE_URL environment variable is required"
    exit 1
fi

# Extract connection parameters from DATABASE_URL
DB_URL_CLEAN="${DATABASE_URL#*://}"
DB_URL_CLEAN="${DB_URL_CLEAN#*+psycopg://}"

if [[ "$DB_URL_CLEAN" =~ ([^:]+):([^@]+)@([^:/]+):?([0-9]*)/(.+)(\?.*)?$ ]]; then
    export PGUSER="${BASH_REMATCH[1]}"
    export PGPASSWORD="${BASH_REMATCH[2]}"
    export PGHOST="${BASH_REMATCH[3]}"
    export PGPORT="${BASH_REMATCH[4]:-5432}"
    export PGDATABASE="${BASH_REMATCH[5]%%\?*}"
else
    log "ERROR: Failed to parse DATABASE_URL"
    exit 1
fi

# List backups mode
if [[ "$LIST_BACKUPS" == "true" ]]; then
    list_backups
    exit 0
fi

# PITR mode
if [[ "$PITR_MODE" == "true" ]]; then
    if [[ -z "$TARGET_TIME" ]]; then
        log "ERROR: --target-time is required for PITR mode"
        echo "Example: --target-time '2024-10-26 01:30:00'"
        exit 1
    fi
    
    log "=== Point-in-Time Recovery Mode ==="
    log "Target time: ${TARGET_TIME}"
    log ""
    log "PITR requires:"
    log "1. A base backup taken before the target time"
    log "2. WAL archives from base backup to target time"
    log "3. PostgreSQL stopped and data directory accessible"
    log ""
    log "This script provides guidance for PITR. For actual recovery:"
    log "1. Stop PostgreSQL"
    log "2. Restore base backup to data directory"
    log "3. Create recovery.conf or recovery.signal with:"
    log "   restore_command = 'cp ${WAL_ARCHIVE_DIR}/%f %p'"
    log "   recovery_target_time = '${TARGET_TIME}'"
    log "4. Start PostgreSQL to begin recovery"
    log ""
    log "See: https://www.postgresql.org/docs/current/continuous-archiving.html"
    exit 0
fi

# Full restore mode - require backup file
if [[ -z "$BACKUP_FILE" ]]; then
    log "ERROR: --backup-file is required for restore"
    echo ""
    echo "List available backups with: $0 --list-backups"
    exit 1
fi

# Verify backup file exists
if [[ ! -f "$BACKUP_FILE" ]]; then
    log "ERROR: Backup file not found: ${BACKUP_FILE}"
    exit 1
fi

log "=== Database Restore ==="
log "Backup file: ${BACKUP_FILE}"
log "Target database: ${PGHOST}:${PGPORT}/${PGDATABASE}"
log ""

# Verify checksum if available
CHECKSUM_FILE="${BACKUP_FILE}.sha256"
if [[ -f "$CHECKSUM_FILE" ]]; then
    log "Verifying backup checksum..."
    if ! (cd "$(dirname "${BACKUP_FILE}")" && sha256sum -c "$(basename "${CHECKSUM_FILE}")" > /dev/null 2>&1); then
        log "ERROR: Checksum verification failed"
        log "The backup file may be corrupted. Restore aborted."
        exit 1
    fi
    log "✓ Checksum verified"
else
    log "WARNING: Checksum file not found, skipping verification"
fi

# Check if backup is encrypted
IS_ENCRYPTED=false
if [[ "$BACKUP_FILE" == *.gpg ]]; then
    IS_ENCRYPTED=true
    log "Backup is encrypted (GPG)"
fi

# Confirm before proceeding
if [[ "$FORCE" != "true" ]]; then
    echo ""
    echo "WARNING: This will DROP and recreate the database!"
    echo "All existing data in '${PGDATABASE}' will be lost."
    echo ""
    read -p "Are you sure you want to proceed? (yes/no): " confirm
    if [[ "$confirm" != "yes" ]]; then
        log "Restore cancelled by user"
        exit 0
    fi
fi

log ""
log "Starting restore process..."
START_TIME=$(date +%s)

# Prepare restore command based on encryption
if [[ "$IS_ENCRYPTED" == "true" ]]; then
    log "Decrypting and restoring backup..."
    RESTORE_CMD="gpg --decrypt ${BACKUP_FILE} | gunzip | psql"
else
    log "Restoring backup..."
    RESTORE_CMD="gunzip -c ${BACKUP_FILE} | psql"
fi

# Execute restore
log "Running restore (this may take several minutes)..."
if eval "${RESTORE_CMD}" > /dev/null 2>&1; then
    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))
    
    log "✓ Restore completed successfully in ${DURATION} seconds"
    
    # Verify restore by checking if we can connect and query
    log "Verifying database connection..."
    if psql -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';" > /dev/null 2>&1; then
        TABLE_COUNT=$(psql -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';" | xargs)
        log "✓ Database connection verified (${TABLE_COUNT} tables found)"
    else
        log "WARNING: Could not verify database connection"
    fi
    
    log ""
    log "=== Restore Summary ==="
    log "Backup: ${BACKUP_FILE}"
    log "Duration: ${DURATION} seconds"
    log "Status: SUCCESS"
    log ""
    log "Next steps:"
    log "1. Verify data integrity in the restored database"
    log "2. Test application functionality"
    log "3. Review restore logs for any warnings"
    
    exit 0
else
    log "ERROR: Restore failed"
    log "Check PostgreSQL logs for details"
    exit 1
fi
