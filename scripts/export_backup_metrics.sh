#!/usr/bin/env bash
# =============================================================================
# Backup Metrics Exporter for Prometheus
# =============================================================================
# Exports backup-related metrics for Prometheus monitoring.
# This script should be run periodically (e.g., every 5 minutes) to update
# metrics that can be scraped by Prometheus.
#
# Metrics exported:
# - backup_last_success_timestamp{type="database|media"} - Unix timestamp of last successful backup
# - backup_last_status{type="database|media"} - Exit status of last backup (0=success)
# - backup_size_bytes{type="database|media"} - Size of latest backup in bytes
# - backup_count{type="database|media",period="daily|weekly|monthly"} - Number of backups by type
# - backup_verification_failures - Number of failed backup verifications
# - wal_last_archive_timestamp - Unix timestamp of last WAL archive
# - wal_archive_count - Number of WAL archive files
#
# Usage:
#   ./export_backup_metrics.sh [--output-file <path>]
#
# For Prometheus node_exporter textfile collector:
#   ./export_backup_metrics.sh --output-file /var/lib/node_exporter/textfile_collector/backups.prom
# =============================================================================

set -euo pipefail

# Configuration
BACKUP_DIR="${BACKUP_DIR:-/backups}"
WAL_ARCHIVE_DIR="${WAL_ARCHIVE_DIR:-/backups/wal_archive}"
OUTPUT_FILE="${OUTPUT_FILE:-/tmp/backup_metrics.prom}"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --output-file)
            OUTPUT_FILE="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Create temporary file
TEMP_FILE=$(mktemp)

# Function to add metric
add_metric() {
    local metric_name=$1
    local metric_type=$2
    local metric_help=$3
    local metric_value=$4
    local labels=${5:-}
    
    # Add help and type only if not already added
    if ! grep -q "^# HELP ${metric_name}" "${TEMP_FILE}" 2>/dev/null; then
        echo "# HELP ${metric_name} ${metric_help}" >> "${TEMP_FILE}"
        echo "# TYPE ${metric_name} ${metric_type}" >> "${TEMP_FILE}"
    fi
    
    if [[ -n "$labels" ]]; then
        echo "${metric_name}{${labels}} ${metric_value}" >> "${TEMP_FILE}"
    else
        echo "${metric_name} ${metric_value}" >> "${TEMP_FILE}"
    fi
}

# Database backup metrics
if [[ -d "${BACKUP_DIR}/daily" ]]; then
    # Find latest database backup
    latest_db_backup=$(find "${BACKUP_DIR}/daily" "${BACKUP_DIR}/weekly" "${BACKUP_DIR}/monthly" -type f \( -name "*.sql.gz" -o -name "*.sql.gz.gpg" \) -print0 2>/dev/null | xargs -0 ls -t 2>/dev/null | head -1 || echo "")
    
    if [[ -n "$latest_db_backup" ]]; then
        # Get backup timestamp (modification time)
        backup_timestamp=$(stat -c %Y "${latest_db_backup}" 2>/dev/null || echo 0)
        add_metric "backup_last_success_timestamp" "gauge" "Unix timestamp of last successful backup" "${backup_timestamp}" 'type="database"'
        
        # Get backup size
        backup_size=$(stat -c %s "${latest_db_backup}" 2>/dev/null || echo 0)
        add_metric "backup_size_bytes" "gauge" "Size of latest backup in bytes" "${backup_size}" 'type="database"'
        
        # Check if backup has a corresponding log with success status
        backup_date=$(date -d "@${backup_timestamp}" +%Y%m%d 2>/dev/null || date +%Y%m%d)
        backup_log="${BACKUP_DIR}/logs/backup_${backup_date}.log"
        backup_status=0
        
        if [[ -f "${backup_log}" ]]; then
            if grep -q "ERROR" "${backup_log}"; then
                backup_status=1
            fi
        fi
        
        add_metric "backup_last_status" "gauge" "Exit status of last backup (0=success)" "${backup_status}" 'type="database"'
    else
        # No backups found - set error status
        add_metric "backup_last_success_timestamp" "gauge" "Unix timestamp of last successful backup" "0" 'type="database"'
        add_metric "backup_last_status" "gauge" "Exit status of last backup (0=success)" "1" 'type="database"'
        add_metric "backup_size_bytes" "gauge" "Size of latest backup in bytes" "0" 'type="database"'
    fi
    
    # Count backups by period
    for period in daily weekly monthly; do
        backup_count=$(find "${BACKUP_DIR}/${period}" -type f \( -name "*.sql.gz" -o -name "*.sql.gz.gpg" \) 2>/dev/null | wc -l || echo 0)
        add_metric "backup_count" "gauge" "Number of backups" "${backup_count}" "type=\"database\",period=\"${period}\""
    done
fi

# Media backup metrics
if [[ -d "${BACKUP_DIR}/media" ]]; then
    if [[ -L "${BACKUP_DIR}/media/current" ]]; then
        # Get media backup timestamp
        media_timestamp=$(stat -c %Y "${BACKUP_DIR}/media/current" 2>/dev/null || echo 0)
        add_metric "backup_last_success_timestamp" "gauge" "Unix timestamp of last successful backup" "${media_timestamp}" 'type="media"'
        
        # Get media backup size
        media_size=$(du -sb "${BACKUP_DIR}/media/current" 2>/dev/null | cut -f1 || echo 0)
        add_metric "backup_size_bytes" "gauge" "Size of latest backup in bytes" "${media_size}" 'type="media"'
        
        # Check media backup status from logs
        latest_media_log=$(find "${BACKUP_DIR}/media/logs" -name "media_backup_*.log" -type f -print0 2>/dev/null | xargs -0 ls -t 2>/dev/null | head -1 || echo "")
        media_status=0
        
        if [[ -n "$latest_media_log" ]]; then
            if grep -q "ERROR" "${latest_media_log}"; then
                media_status=1
            fi
        fi
        
        add_metric "backup_last_status" "gauge" "Exit status of last backup (0=success)" "${media_status}" 'type="media"'
        
        # Count media backups
        media_backup_count=$(find "${BACKUP_DIR}/media" -maxdepth 1 -type d -name "20*" 2>/dev/null | wc -l || echo 0)
        add_metric "backup_count" "gauge" "Number of backups" "${media_backup_count}" 'type="media",period="all"'
    else
        add_metric "backup_last_success_timestamp" "gauge" "Unix timestamp of last successful backup" "0" 'type="media"'
        add_metric "backup_last_status" "gauge" "Exit status of last backup (0=success)" "1" 'type="media"'
        add_metric "backup_size_bytes" "gauge" "Size of latest backup in bytes" "0" 'type="media"'
    fi
fi

# WAL archive metrics
if [[ -d "${WAL_ARCHIVE_DIR}" ]]; then
    # Count WAL archives
    wal_count=$(find "${WAL_ARCHIVE_DIR}" -type f -name "*.gz" 2>/dev/null | wc -l || echo 0)
    add_metric "wal_archive_count" "gauge" "Number of WAL archive files" "${wal_count}"
    
    # Get latest WAL archive timestamp
    latest_wal=$(find "${WAL_ARCHIVE_DIR}" -type f -name "*.gz" -print0 2>/dev/null | xargs -0 ls -t 2>/dev/null | head -1 || echo "")
    if [[ -n "$latest_wal" ]]; then
        wal_timestamp=$(stat -c %Y "${latest_wal}" 2>/dev/null || echo 0)
        add_metric "wal_last_archive_timestamp" "gauge" "Unix timestamp of last WAL archive" "${wal_timestamp}"
    else
        add_metric "wal_last_archive_timestamp" "gauge" "Unix timestamp of last WAL archive" "0"
    fi
fi

# Backup verification metrics
# Check for recent verification failures
verification_failures=0
if [[ -d "${BACKUP_DIR}/logs" ]]; then
    # Look for verification errors in recent logs
    recent_logs=$(find "${BACKUP_DIR}/logs" -name "*.log" -type f -mtime -1 2>/dev/null || echo "")
    if [[ -n "$recent_logs" ]]; then
        verification_failures=$(grep -c "Checksum verification failed\|Gzip integrity check failed\|Checksum FAILED" ${recent_logs} 2>/dev/null || echo 0)
    fi
fi
add_metric "backup_verification_failures" "gauge" "Number of failed backup verifications" "${verification_failures}"

# Total backup storage metrics
if [[ -d "${BACKUP_DIR}" ]]; then
    total_backup_size=$(du -sb "${BACKUP_DIR}" 2>/dev/null | cut -f1 || echo 0)
    add_metric "backup_total_size_bytes" "gauge" "Total size of all backups in bytes" "${total_backup_size}"
fi

# Move temporary file to output location atomically
mv "${TEMP_FILE}" "${OUTPUT_FILE}"

# Optional: print metrics to stdout for debugging
if [[ "${DEBUG:-false}" == "true" ]]; then
    cat "${OUTPUT_FILE}"
fi

exit 0
