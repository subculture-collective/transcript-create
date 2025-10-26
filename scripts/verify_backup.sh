#!/usr/bin/env bash
# =============================================================================
# Backup Verification Script for transcript-create
# =============================================================================
# Verifies integrity of database and media backups
# - Checksums validation
# - Backup file integrity testing
# - Restore testing (in test environment)
# - Backup age monitoring
#
# Usage:
#   ./verify_backup.sh [--test-restore] [--max-age-hours <hours>]
#
# Exit codes:
#   0 - All verifications passed
#   1 - Verification failures detected
#   2 - Backups too old or missing
# =============================================================================

set -euo pipefail

# Configuration
BACKUP_DIR="${BACKUP_DIR:-/backups}"
MAX_BACKUP_AGE_HOURS="${MAX_BACKUP_AGE_HOURS:-26}"  # Slightly more than 24h for daily backups

# Parse arguments
TEST_RESTORE=false
CUSTOM_MAX_AGE=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --test-restore)
            TEST_RESTORE=true
            shift
            ;;
        --max-age-hours)
            CUSTOM_MAX_AGE="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --test-restore          Perform a test restore to verify backup"
            echo "  --max-age-hours <hrs>   Maximum backup age in hours (default: 26)"
            echo "  -h, --help              Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

if [[ -n "$CUSTOM_MAX_AGE" ]]; then
    MAX_BACKUP_AGE_HOURS="$CUSTOM_MAX_AGE"
fi

# Logging
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

# Track verification status
FAILURES=0
WARNINGS=0

log "=== Backup Verification Started ==="
log "Backup directory: ${BACKUP_DIR}"
log "Maximum backup age: ${MAX_BACKUP_AGE_HOURS} hours"
log ""

# Check if backup directory exists
if [[ ! -d "${BACKUP_DIR}" ]]; then
    log "ERROR: Backup directory not found: ${BACKUP_DIR}"
    exit 2
fi

# Verify database backups
log "--- Database Backup Verification ---"

DB_BACKUP_FOUND=false
LATEST_DB_BACKUP=""
LATEST_DB_BACKUP_TIME=0

for backup_type in daily weekly monthly; do
    backup_dir="${BACKUP_DIR}/${backup_type}"
    if [[ ! -d "${backup_dir}" ]]; then
        continue
    fi
    
    # Find backups (both compressed and encrypted)
    while IFS= read -r -d '' backup_file; do
        DB_BACKUP_FOUND=true
        
        # Get backup modification time
        backup_mtime=$(stat -c %Y "${backup_file}")
        
        if [[ $backup_mtime -gt $LATEST_DB_BACKUP_TIME ]]; then
            LATEST_DB_BACKUP_TIME=$backup_mtime
            LATEST_DB_BACKUP="${backup_file}"
        fi
        
        # Verify checksum
        checksum_file="${backup_file}.sha256"
        if [[ -f "${checksum_file}" ]]; then
            if (cd "$(dirname "${backup_file}")" && sha256sum -c "$(basename "${checksum_file}")" > /dev/null 2>&1); then
                log "✓ Checksum valid: ${backup_file}"
            else
                log "✗ Checksum FAILED: ${backup_file}"
                FAILURES=$((FAILURES + 1))
            fi
        else
            log "⚠ Missing checksum: ${backup_file}"
            WARNINGS=$((WARNINGS + 1))
        fi
        
        # Test gzip integrity (if not encrypted)
        if [[ "${backup_file}" != *.gpg ]]; then
            if gzip -t "${backup_file}" 2>/dev/null; then
                log "✓ Gzip integrity OK: ${backup_file}"
            else
                log "✗ Gzip integrity FAILED: ${backup_file}"
                FAILURES=$((FAILURES + 1))
            fi
        fi
        
    done < <(find "${backup_dir}" -type f \( -name "*.sql.gz" -o -name "*.sql.gz.gpg" \) -print0 2>/dev/null)
done

if [[ "$DB_BACKUP_FOUND" != "true" ]]; then
    log "✗ No database backups found"
    FAILURES=$((FAILURES + 1))
else
    log ""
    log "Latest database backup: ${LATEST_DB_BACKUP}"
    
    # Check backup age
    current_time=$(date +%s)
    backup_age_seconds=$((current_time - LATEST_DB_BACKUP_TIME))
    backup_age_hours=$((backup_age_seconds / 3600))
    
    log "Backup age: ${backup_age_hours} hours"
    
    if [[ $backup_age_hours -gt $MAX_BACKUP_AGE_HOURS ]]; then
        log "✗ Latest backup is too old (>${MAX_BACKUP_AGE_HOURS} hours)"
        FAILURES=$((FAILURES + 1))
    else
        log "✓ Backup age acceptable"
    fi
fi

log ""

# Verify media backups
log "--- Media Backup Verification ---"

MEDIA_BACKUP_DIR="${BACKUP_DIR}/media"
if [[ -d "${MEDIA_BACKUP_DIR}/current" ]]; then
    log "✓ Media backup directory found"
    
    # Check for checksums
    latest_checksum=$(find "${MEDIA_BACKUP_DIR}" -name "checksums_*.sha256" -type f -print0 2>/dev/null | xargs -0 ls -t | head -1)
    if [[ -n "${latest_checksum}" ]]; then
        log "Found checksum file: ${latest_checksum}"
        
        # Sample verification - check a few random files
        log "Sampling checksum verification (10 random files)..."
        temp_sample=$(mktemp)
        shuf -n 10 "${latest_checksum}" > "${temp_sample}" 2>/dev/null || true
        
        if [[ -s "${temp_sample}" ]]; then
            if (cd "$(dirname "${MEDIA_BACKUP_DIR}/current")" && sha256sum -c "${temp_sample}" > /dev/null 2>&1); then
                log "✓ Media backup sample checksums valid"
            else
                log "✗ Media backup sample checksums FAILED"
                FAILURES=$((FAILURES + 1))
            fi
        fi
        rm -f "${temp_sample}"
    else
        log "⚠ No checksum file found for media backups"
        WARNINGS=$((WARNINGS + 1))
    fi
    
    # Check media backup age
    if [[ -L "${MEDIA_BACKUP_DIR}/current" ]]; then
        media_backup_time=$(stat -c %Y "${MEDIA_BACKUP_DIR}/current")
        media_age_seconds=$((current_time - media_backup_time))
        media_age_hours=$((media_age_seconds / 3600))
        
        log "Media backup age: ${media_age_hours} hours"
        
        if [[ $media_age_hours -gt $MAX_BACKUP_AGE_HOURS ]]; then
            log "⚠ Media backup is older than ${MAX_BACKUP_AGE_HOURS} hours"
            WARNINGS=$((WARNINGS + 1))
        else
            log "✓ Media backup age acceptable"
        fi
    fi
    
    # Calculate backup size
    backup_size=$(du -sh "${MEDIA_BACKUP_DIR}/current" 2>/dev/null | cut -f1 || echo "unknown")
    log "Media backup size: ${backup_size}"
else
    log "⚠ No media backup found at ${MEDIA_BACKUP_DIR}/current"
    WARNINGS=$((WARNINGS + 1))
fi

log ""

# Test restore (if requested)
if [[ "$TEST_RESTORE" == "true" ]]; then
    log "--- Test Restore ---"
    
    if [[ -z "$LATEST_DB_BACKUP" ]]; then
        log "✗ Cannot test restore: no database backup found"
        FAILURES=$((FAILURES + 1))
    else
        log "Testing restore from: ${LATEST_DB_BACKUP}"
        
        # Create temporary database for testing
        TEST_DB="transcripts_test_restore_$$"
        log "Creating test database: ${TEST_DB}"
        
        # Extract connection info from DATABASE_URL if available
        if [[ -n "${DATABASE_URL:-}" ]]; then
            DB_URL_CLEAN="${DATABASE_URL#*://}"
            DB_URL_CLEAN="${DB_URL_CLEAN#*+psycopg://}"
            
            if [[ "$DB_URL_CLEAN" =~ ([^:]+):([^@]+)@([^:/]+):?([0-9]*)/(.+)(\?.*)?$ ]]; then
                export PGUSER="${BASH_REMATCH[1]}"
                export PGPASSWORD="${BASH_REMATCH[2]}"
                export PGHOST="${BASH_REMATCH[3]}"
                export PGPORT="${BASH_REMATCH[4]:-5432}"
                
                # Create test database
                if psql -d postgres -c "CREATE DATABASE ${TEST_DB};" > /dev/null 2>&1; then
                    log "✓ Test database created"
                    
                    # Attempt restore
                    if [[ "${LATEST_DB_BACKUP}" == *.gpg ]]; then
                        log "Skipping encrypted backup test (GPG key required)"
                        WARNINGS=$((WARNINGS + 1))
                    else
                        log "Restoring to test database..."
                        if gunzip -c "${LATEST_DB_BACKUP}" | psql -d "${TEST_DB}" > /dev/null 2>&1; then
                            log "✓ Test restore successful"
                            
                            # Verify some data
                            table_count=$(psql -d "${TEST_DB}" -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';" | xargs)
                            log "✓ Test database has ${table_count} tables"
                        else
                            log "✗ Test restore FAILED"
                            FAILURES=$((FAILURES + 1))
                        fi
                    fi
                    
                    # Cleanup test database
                    log "Cleaning up test database..."
                    psql -d postgres -c "DROP DATABASE IF EXISTS ${TEST_DB};" > /dev/null 2>&1
                else
                    log "⚠ Could not create test database"
                    WARNINGS=$((WARNINGS + 1))
                fi
            else
                log "⚠ Could not parse DATABASE_URL for test restore"
                WARNINGS=$((WARNINGS + 1))
            fi
        else
            log "⚠ DATABASE_URL not set, skipping test restore"
            WARNINGS=$((WARNINGS + 1))
        fi
    fi
    
    log ""
fi

# Check WAL archive if configured
log "--- WAL Archive Verification ---"

WAL_ARCHIVE_DIR="${WAL_ARCHIVE_DIR:-${BACKUP_DIR}/wal_archive}"
if [[ -d "${WAL_ARCHIVE_DIR}" ]]; then
    wal_count=$(find "${WAL_ARCHIVE_DIR}" -type f -name "*.gz" 2>/dev/null | wc -l)
    if [[ $wal_count -gt 0 ]]; then
        log "✓ WAL archive found with ${wal_count} files"
        
        # Check for recent WAL files (within last hour for active systems)
        recent_wals=$(find "${WAL_ARCHIVE_DIR}" -type f -name "*.gz" -mmin -60 2>/dev/null | wc -l)
        if [[ $recent_wals -gt 0 ]]; then
            log "✓ WAL archiving active (${recent_wals} files in last hour)"
        else
            log "⚠ No recent WAL files (system may be idle or archiving not configured)"
            WARNINGS=$((WARNINGS + 1))
        fi
    else
        log "⚠ WAL archive directory exists but contains no files"
        WARNINGS=$((WARNINGS + 1))
    fi
else
    log "⚠ WAL archive directory not found: ${WAL_ARCHIVE_DIR}"
    log "  PITR may not be available. Configure WAL archiving for point-in-time recovery."
    WARNINGS=$((WARNINGS + 1))
fi

log ""

# Summary
log "=== Verification Summary ==="
log "Failures: ${FAILURES}"
log "Warnings: ${WARNINGS}"

if [[ $FAILURES -eq 0 ]]; then
    if [[ $WARNINGS -eq 0 ]]; then
        log "✓ All verifications passed"
        exit 0
    else
        log "⚠ Verifications passed with ${WARNINGS} warning(s)"
        exit 0
    fi
else
    log "✗ Verification FAILED with ${FAILURES} error(s)"
    exit 1
fi
