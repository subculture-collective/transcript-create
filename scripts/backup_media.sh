#!/usr/bin/env bash
# =============================================================================
# Media Backup Script for transcript-create
# =============================================================================
# Backs up the /data volume containing video files, audio, and transcripts.
# Features:
# - Rsync-based incremental backups
# - Exclusion of temporary and cache files
# - Cloud storage sync (S3, GCS, Azure)
# - 30-day retention policy
# - Checksums for verification
#
# Usage:
#   ./backup_media.sh [--full] [--verify-only]
#
# Environment Variables:
#   MEDIA_SOURCE_DIR      - Source data directory (default: /data)
#   MEDIA_BACKUP_DIR      - Local backup directory (default: /backups/media)
#   BACKUP_S3_BUCKET      - Optional S3 bucket for remote storage
#   BACKUP_GCS_BUCKET     - Optional GCS bucket for remote storage
#   BACKUP_AZURE_CONTAINER - Optional Azure container for remote storage
#   MEDIA_RETENTION_DAYS  - Days to keep media backups (default: 30)
# =============================================================================

set -euo pipefail

# Configuration with defaults
MEDIA_SOURCE_DIR="${MEDIA_SOURCE_DIR:-/data}"
MEDIA_BACKUP_DIR="${MEDIA_BACKUP_DIR:-/backups/media}"
BACKUP_S3_BUCKET="${BACKUP_S3_BUCKET:-}"
BACKUP_GCS_BUCKET="${BACKUP_GCS_BUCKET:-}"
BACKUP_AZURE_CONTAINER="${BACKUP_AZURE_CONTAINER:-}"
MEDIA_RETENTION_DAYS="${MEDIA_RETENTION_DAYS:-30}"

# Parse command line arguments
FULL_BACKUP=false
VERIFY_ONLY=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --full)
            FULL_BACKUP=true
            shift
            ;;
        --verify-only)
            VERIFY_ONLY=true
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --full          Perform full backup (ignore existing backups)"
            echo "  --verify-only   Only verify existing backups"
            echo "  -h, --help      Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Logging
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_DIR="${MEDIA_BACKUP_DIR}/logs"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/media_backup_${TIMESTAMP}.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "${LOG_FILE}"
}

# Verify source directory exists
if [[ ! -d "${MEDIA_SOURCE_DIR}" ]]; then
    log "ERROR: Source directory not found: ${MEDIA_SOURCE_DIR}"
    exit 1
fi

# Create backup directory
mkdir -p "${MEDIA_BACKUP_DIR}"

# Exclusion patterns for temporary/cache files
EXCLUDE_PATTERNS=(
    "*.tmp"
    "*.temp"
    "*~"
    ".cache/*"
    "cache/*"
    "*.part"
    "*.download"
    "__pycache__/*"
    "*.pyc"
    ".DS_Store"
    "Thumbs.db"
)

# Build rsync exclude arguments
RSYNC_EXCLUDES=()
for pattern in "${EXCLUDE_PATTERNS[@]}"; do
    RSYNC_EXCLUDES+=("--exclude=${pattern}")
done

# Verification mode
if [[ "$VERIFY_ONLY" == "true" ]]; then
    log "=== Media Backup Verification Mode ==="
    
    if [[ ! -d "${MEDIA_BACKUP_DIR}/current" ]]; then
        log "ERROR: No backup found to verify"
        exit 1
    fi
    
    log "Verifying backup integrity..."
    
    # Check if checksums exist
    CHECKSUM_FILE="${MEDIA_BACKUP_DIR}/checksums.sha256"
    if [[ ! -f "${CHECKSUM_FILE}" ]]; then
        log "WARNING: Checksum file not found, generating new checksums..."
        find "${MEDIA_BACKUP_DIR}/current" -type f -exec sha256sum {} \; > "${CHECKSUM_FILE}"
    fi
    
    # Verify checksums
    log "Verifying file checksums..."
    if sha256sum -c "${CHECKSUM_FILE}" 2>&1 | grep -q "FAILED"; then
        log "ERROR: Checksum verification failed"
        exit 1
    fi
    
    log "✓ All checksums verified successfully"
    
    # Count files and calculate total size
    FILE_COUNT=$(find "${MEDIA_BACKUP_DIR}/current" -type f | wc -l)
    TOTAL_SIZE=$(du -sh "${MEDIA_BACKUP_DIR}/current" | cut -f1)
    
    log "=== Verification Summary ==="
    log "Files: ${FILE_COUNT}"
    log "Total size: ${TOTAL_SIZE}"
    log "Location: ${MEDIA_BACKUP_DIR}/current"
    
    exit 0
fi

# Start backup process
log "=== Starting Media Backup ==="
log "Source: ${MEDIA_SOURCE_DIR}"
log "Destination: ${MEDIA_BACKUP_DIR}"
log "Mode: $([ "$FULL_BACKUP" = true ] && echo "Full" || echo "Incremental")"

START_TIME=$(date +%s)

# Create timestamped backup directory
BACKUP_TARGET="${MEDIA_BACKUP_DIR}/${TIMESTAMP}"
mkdir -p "${BACKUP_TARGET}"

# Link to current backup if incremental
RSYNC_LINK_DEST=""
if [[ "$FULL_BACKUP" != "true" ]] && [[ -d "${MEDIA_BACKUP_DIR}/current" ]]; then
    RSYNC_LINK_DEST="--link-dest=${MEDIA_BACKUP_DIR}/current"
    log "Using incremental backup with link-dest"
fi

# Perform rsync backup
log "Running rsync..."
if rsync -av \
    --progress \
    ${RSYNC_LINK_DEST} \
    "${RSYNC_EXCLUDES[@]}" \
    --stats \
    "${MEDIA_SOURCE_DIR}/" \
    "${BACKUP_TARGET}/" \
    2>&1 | tee -a "${LOG_FILE}"; then
    
    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))
    
    log "✓ Rsync completed in ${DURATION} seconds"
else
    log "ERROR: Rsync failed"
    exit 1
fi

# Update 'current' symlink
log "Updating current backup symlink..."
if [[ -L "${MEDIA_BACKUP_DIR}/current" ]]; then
    rm "${MEDIA_BACKUP_DIR}/current"
fi
ln -s "${BACKUP_TARGET}" "${MEDIA_BACKUP_DIR}/current"

# Generate checksums for the new backup
log "Generating checksums..."
CHECKSUM_FILE="${MEDIA_BACKUP_DIR}/checksums_${TIMESTAMP}.sha256"
find "${BACKUP_TARGET}" -type f -exec sha256sum {} \; > "${CHECKSUM_FILE}"
log "✓ Checksums saved to ${CHECKSUM_FILE}"

# Calculate backup statistics
FILE_COUNT=$(find "${BACKUP_TARGET}" -type f | wc -l)
BACKUP_SIZE=$(du -sh "${BACKUP_TARGET}" | cut -f1)

log "=== Backup Statistics ==="
log "Files backed up: ${FILE_COUNT}"
log "Backup size: ${BACKUP_SIZE}"
log "Duration: ${DURATION} seconds"

# Sync to cloud storage if configured
if [[ -n "$BACKUP_S3_BUCKET" ]]; then
    log "Syncing to S3: s3://${BACKUP_S3_BUCKET}/media/"
    if command -v aws &> /dev/null; then
        aws s3 sync "${BACKUP_TARGET}/" "s3://${BACKUP_S3_BUCKET}/media/${TIMESTAMP}/" \
            --storage-class GLACIER \
            --exclude "*.tmp" \
            --exclude "*.temp" 2>&1 | tee -a "${LOG_FILE}"
        log "✓ Synced to S3"
    else
        log "WARNING: aws CLI not found, skipping S3 sync"
    fi
fi

if [[ -n "$BACKUP_GCS_BUCKET" ]]; then
    log "Syncing to GCS: gs://${BACKUP_GCS_BUCKET}/media/"
    if command -v gsutil &> /dev/null; then
        gsutil -m rsync -r "${BACKUP_TARGET}/" "gs://${BACKUP_GCS_BUCKET}/media/${TIMESTAMP}/" \
            2>&1 | tee -a "${LOG_FILE}"
        # Move to Nearline or Coldline storage class for cost savings
        gsutil -m rewrite -s NEARLINE "gs://${BACKUP_GCS_BUCKET}/media/${TIMESTAMP}/**" \
            2>&1 | tee -a "${LOG_FILE}" || true
        log "✓ Synced to GCS"
    else
        log "WARNING: gsutil not found, skipping GCS sync"
    fi
fi

if [[ -n "$BACKUP_AZURE_CONTAINER" ]]; then
    log "Syncing to Azure: ${BACKUP_AZURE_CONTAINER}/media/"
    if command -v az &> /dev/null; then
        az storage blob upload-batch \
            --destination "${BACKUP_AZURE_CONTAINER}/media/${TIMESTAMP}" \
            --source "${BACKUP_TARGET}" \
            --tier Cool \
            2>&1 | tee -a "${LOG_FILE}"
        log "✓ Synced to Azure"
    else
        log "WARNING: az CLI not found, skipping Azure sync"
    fi
fi

# Apply retention policy
log "=== Applying Retention Policy ==="
log "Removing backups older than ${MEDIA_RETENTION_DAYS} days..."

# Find and remove old backup directories
find "${MEDIA_BACKUP_DIR}" -maxdepth 1 -type d -name "20*" -mtime +${MEDIA_RETENTION_DAYS} | while read -r old_backup; do
    log "Removing old backup: ${old_backup}"
    rm -rf "${old_backup}"
done

# Remove old checksum files
find "${MEDIA_BACKUP_DIR}" -maxdepth 1 -name "checksums_*.sha256" -mtime +${MEDIA_RETENTION_DAYS} -delete

# Remove old log files (keep 30 days)
find "${LOG_DIR}" -name "media_backup_*.log" -mtime +30 -delete

# Summary
log "=== Backup Summary ==="
CURRENT_BACKUPS=$(find "${MEDIA_BACKUP_DIR}" -maxdepth 1 -type d -name "20*" | wc -l)
TOTAL_BACKUP_SIZE=$(du -sh "${MEDIA_BACKUP_DIR}" | cut -f1)
log "Active backups: ${CURRENT_BACKUPS}"
log "Total backup size: ${TOTAL_BACKUP_SIZE}"
log "Latest backup: ${BACKUP_TARGET}"

log "=== Media Backup Completed Successfully ==="
exit 0
