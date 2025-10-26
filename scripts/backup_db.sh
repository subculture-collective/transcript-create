#!/usr/bin/env bash
# =============================================================================
# Database Backup Script for transcript-create
# =============================================================================
# Performs automated PostgreSQL backups with:
# - pg_dump full database dumps
# - gzip compression
# - Retention policy: 7 daily, 4 weekly, 12 monthly
# - Optional encryption with GPG
# - Backup verification with checksums
#
# Usage:
#   ./backup_db.sh [--encrypt] [--verify-only]
#
# Environment Variables:
#   DATABASE_URL          - PostgreSQL connection string (required)
#   BACKUP_DIR            - Backup storage directory (default: /backups)
#   BACKUP_ENCRYPT        - Enable GPG encryption (default: false)
#   BACKUP_GPG_RECIPIENT  - GPG recipient for encryption
#   BACKUP_RETENTION_DAILY   - Days to keep daily backups (default: 7)
#   BACKUP_RETENTION_WEEKLY  - Weeks to keep weekly backups (default: 4)
#   BACKUP_RETENTION_MONTHLY - Months to keep monthly backups (default: 12)
#   BACKUP_S3_BUCKET      - Optional S3 bucket for remote storage
#   BACKUP_GCS_BUCKET     - Optional GCS bucket for remote storage
#   BACKUP_AZURE_CONTAINER - Optional Azure container for remote storage
# =============================================================================

set -euo pipefail

# Configuration with defaults
BACKUP_DIR="${BACKUP_DIR:-/backups}"
BACKUP_ENCRYPT="${BACKUP_ENCRYPT:-false}"
BACKUP_GPG_RECIPIENT="${BACKUP_GPG_RECIPIENT:-}"
BACKUP_RETENTION_DAILY="${BACKUP_RETENTION_DAILY:-7}"
BACKUP_RETENTION_WEEKLY="${BACKUP_RETENTION_WEEKLY:-4}"
BACKUP_RETENTION_MONTHLY="${BACKUP_RETENTION_MONTHLY:-12}"
BACKUP_S3_BUCKET="${BACKUP_S3_BUCKET:-}"
BACKUP_GCS_BUCKET="${BACKUP_GCS_BUCKET:-}"
BACKUP_AZURE_CONTAINER="${BACKUP_AZURE_CONTAINER:-}"

# Parse command line arguments
VERIFY_ONLY=false
while [[ $# -gt 0 ]]; do
    case $1 in
        --encrypt)
            BACKUP_ENCRYPT=true
            shift
            ;;
        --verify-only)
            VERIFY_ONLY=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--encrypt] [--verify-only]"
            exit 1
            ;;
    esac
done

# Verify required environment variables
if [[ -z "${DATABASE_URL:-}" ]]; then
    echo "ERROR: DATABASE_URL environment variable is required"
    exit 1
fi

# Create backup directories
mkdir -p "${BACKUP_DIR}"/{daily,weekly,monthly,logs}

# Generate timestamp and backup filename
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DATE=$(date +%Y%m%d)
DAY_OF_WEEK=$(date +%u)  # 1=Monday, 7=Sunday
DAY_OF_MONTH=$(date +%d)

BACKUP_TYPE="daily"
if [[ "$DAY_OF_MONTH" == "01" ]]; then
    BACKUP_TYPE="monthly"
elif [[ "$DAY_OF_WEEK" == "7" ]]; then
    BACKUP_TYPE="weekly"
fi

BACKUP_FILENAME="transcripts_${BACKUP_TYPE}_${TIMESTAMP}.sql.gz"
BACKUP_PATH="${BACKUP_DIR}/${BACKUP_TYPE}/${BACKUP_FILENAME}"
CHECKSUM_FILE="${BACKUP_PATH}.sha256"
LOG_FILE="${BACKUP_DIR}/logs/backup_${DATE}.log"

# Logging function
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "${LOG_FILE}"
}

# Verify backups function
verify_backup() {
    local backup_file=$1
    local checksum_file="${backup_file}.sha256"
    
    if [[ ! -f "${backup_file}" ]]; then
        log "ERROR: Backup file not found: ${backup_file}"
        return 1
    fi
    
    if [[ ! -f "${checksum_file}" ]]; then
        log "WARNING: Checksum file not found for ${backup_file}"
        return 1
    fi
    
    log "Verifying backup: ${backup_file}"
    
    # Verify checksum
    if ! (cd "$(dirname "${backup_file}")" && sha256sum -c "$(basename "${checksum_file}")" > /dev/null 2>&1); then
        log "ERROR: Checksum verification failed for ${backup_file}"
        return 1
    fi
    
    # Test that the backup is a valid gzip file
    if ! gzip -t "${backup_file}" 2>/dev/null; then
        log "ERROR: Gzip integrity check failed for ${backup_file}"
        return 1
    fi
    
    log "✓ Backup verified successfully: ${backup_file}"
    return 0
}

# If verify-only mode, verify all backups and exit
if [[ "$VERIFY_ONLY" == "true" ]]; then
    log "=== Backup Verification Mode ==="
    failed=0
    total=0
    
    for backup_type in daily weekly monthly; do
        log "Verifying ${backup_type} backups..."
        for backup_file in "${BACKUP_DIR}/${backup_type}"/*.sql.gz 2>/dev/null; do
            [[ -e "$backup_file" ]] || continue
            total=$((total + 1))
            if ! verify_backup "${backup_file}"; then
                failed=$((failed + 1))
            fi
        done
    done
    
    log "=== Verification Summary ==="
    log "Total backups checked: ${total}"
    log "Failed verifications: ${failed}"
    log "Successful verifications: $((total - failed))"
    
    if [[ $failed -gt 0 ]]; then
        exit 1
    fi
    exit 0
fi

# Start backup process
log "=== Starting ${BACKUP_TYPE} backup ==="
log "Backup file: ${BACKUP_PATH}"
log "Database: ${DATABASE_URL%%@*}@***"  # Log without exposing credentials

# Extract connection parameters from DATABASE_URL
# Format: postgresql://user:pass@host:port/dbname or postgresql+psycopg://user:pass@host:port/dbname
DB_URL_CLEAN="${DATABASE_URL#*://}"
DB_URL_CLEAN="${DB_URL_CLEAN#*+psycopg://}"

# Parse database connection info
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

# Perform the backup
log "Running pg_dump..."
START_TIME=$(date +%s)

if ! pg_dump \
    --verbose \
    --format=plain \
    --no-owner \
    --no-acl \
    --clean \
    --if-exists \
    2>> "${LOG_FILE}" | gzip -9 > "${BACKUP_PATH}"; then
    log "ERROR: pg_dump failed"
    exit 1
fi

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))
BACKUP_SIZE=$(du -h "${BACKUP_PATH}" | cut -f1)

log "✓ Backup completed in ${DURATION} seconds"
log "Backup size: ${BACKUP_SIZE}"

# Generate checksum
log "Generating checksum..."
(cd "$(dirname "${BACKUP_PATH}")" && sha256sum "$(basename "${BACKUP_PATH}")" > "$(basename "${CHECKSUM_FILE}")")
log "✓ Checksum generated: ${CHECKSUM_FILE}"

# Encrypt backup if requested
if [[ "$BACKUP_ENCRYPT" == "true" ]]; then
    if [[ -z "$BACKUP_GPG_RECIPIENT" ]]; then
        log "ERROR: BACKUP_GPG_RECIPIENT must be set when encryption is enabled"
        exit 1
    fi
    
    log "Encrypting backup with GPG..."
    if gpg --encrypt --recipient "${BACKUP_GPG_RECIPIENT}" "${BACKUP_PATH}"; then
        log "✓ Backup encrypted: ${BACKUP_PATH}.gpg"
        # Remove unencrypted backup
        rm "${BACKUP_PATH}"
        BACKUP_PATH="${BACKUP_PATH}.gpg"
        # Update checksum for encrypted file
        (cd "$(dirname "${BACKUP_PATH}")" && sha256sum "$(basename "${BACKUP_PATH}")" > "$(basename "${CHECKSUM_FILE}")")
    else
        log "ERROR: GPG encryption failed"
        exit 1
    fi
fi

# Verify the backup
if ! verify_backup "${BACKUP_PATH}"; then
    log "ERROR: Backup verification failed"
    exit 1
fi

# Upload to cloud storage if configured
if [[ -n "$BACKUP_S3_BUCKET" ]]; then
    log "Uploading to S3: s3://${BACKUP_S3_BUCKET}/backups/postgres/${BACKUP_FILENAME}"
    if command -v aws &> /dev/null; then
        aws s3 cp "${BACKUP_PATH}" "s3://${BACKUP_S3_BUCKET}/backups/postgres/${BACKUP_FILENAME}"
        aws s3 cp "${CHECKSUM_FILE}" "s3://${BACKUP_S3_BUCKET}/backups/postgres/$(basename "${CHECKSUM_FILE}")"
        log "✓ Uploaded to S3"
    else
        log "WARNING: aws CLI not found, skipping S3 upload"
    fi
fi

if [[ -n "$BACKUP_GCS_BUCKET" ]]; then
    log "Uploading to GCS: gs://${BACKUP_GCS_BUCKET}/backups/postgres/${BACKUP_FILENAME}"
    if command -v gsutil &> /dev/null; then
        gsutil cp "${BACKUP_PATH}" "gs://${BACKUP_GCS_BUCKET}/backups/postgres/${BACKUP_FILENAME}"
        gsutil cp "${CHECKSUM_FILE}" "gs://${BACKUP_GCS_BUCKET}/backups/postgres/$(basename "${CHECKSUM_FILE}")"
        log "✓ Uploaded to GCS"
    else
        log "WARNING: gsutil not found, skipping GCS upload"
    fi
fi

if [[ -n "$BACKUP_AZURE_CONTAINER" ]]; then
    log "Uploading to Azure: ${BACKUP_AZURE_CONTAINER}/backups/postgres/${BACKUP_FILENAME}"
    if command -v az &> /dev/null; then
        az storage blob upload \
            --container-name "${BACKUP_AZURE_CONTAINER}" \
            --name "backups/postgres/${BACKUP_FILENAME}" \
            --file "${BACKUP_PATH}"
        az storage blob upload \
            --container-name "${BACKUP_AZURE_CONTAINER}" \
            --name "backups/postgres/$(basename "${CHECKSUM_FILE}")" \
            --file "${CHECKSUM_FILE}"
        log "✓ Uploaded to Azure"
    else
        log "WARNING: az CLI not found, skipping Azure upload"
    fi
fi

# Apply retention policy
log "=== Applying Retention Policy ==="

# Remove old daily backups (keep last N days)
log "Cleaning daily backups older than ${BACKUP_RETENTION_DAILY} days..."
find "${BACKUP_DIR}/daily" -name "*.sql.gz*" -type f -mtime +${BACKUP_RETENTION_DAILY} -delete
find "${BACKUP_DIR}/daily" -name "*.sql.gz.gpg*" -type f -mtime +${BACKUP_RETENTION_DAILY} -delete

# Remove old weekly backups (keep last N weeks)
WEEKLY_RETENTION_DAYS=$((BACKUP_RETENTION_WEEKLY * 7))
log "Cleaning weekly backups older than ${BACKUP_RETENTION_WEEKLY} weeks..."
find "${BACKUP_DIR}/weekly" -name "*.sql.gz*" -type f -mtime +${WEEKLY_RETENTION_DAYS} -delete
find "${BACKUP_DIR}/weekly" -name "*.sql.gz.gpg*" -type f -mtime +${WEEKLY_RETENTION_DAYS} -delete

# Remove old monthly backups (keep last N months)
MONTHLY_RETENTION_DAYS=$((BACKUP_RETENTION_MONTHLY * 30))
log "Cleaning monthly backups older than ${BACKUP_RETENTION_MONTHLY} months..."
find "${BACKUP_DIR}/monthly" -name "*.sql.gz*" -type f -mtime +${MONTHLY_RETENTION_DAYS} -delete
find "${BACKUP_DIR}/monthly" -name "*.sql.gz.gpg*" -type f -mtime +${MONTHLY_RETENTION_DAYS} -delete

# Remove old log files (keep last 30 days)
log "Cleaning old log files..."
find "${BACKUP_DIR}/logs" -name "*.log" -type f -mtime +30 -delete

# Summary
log "=== Backup Summary ==="
log "Daily backups: $(find "${BACKUP_DIR}/daily" -name "*.sql.gz*" -type f | wc -l)"
log "Weekly backups: $(find "${BACKUP_DIR}/weekly" -name "*.sql.gz*" -type f | wc -l)"
log "Monthly backups: $(find "${BACKUP_DIR}/monthly" -name "*.sql.gz*" -type f | wc -l)"
log "Total backup size: $(du -sh "${BACKUP_DIR}" | cut -f1)"

log "=== Backup Completed Successfully ==="
exit 0
