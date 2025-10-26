#!/usr/bin/env bash
# =============================================================================
# Docker Image Size Comparison Script
# =============================================================================
# Compares image sizes for all variants and the original Dockerfile.
#
# Usage:
#   ./compare-image-sizes.sh
# =============================================================================

set -euo pipefail

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}==================================${NC}"
echo -e "${BLUE}Docker Image Size Comparison${NC}"
echo -e "${BLUE}==================================${NC}"
echo ""

# Function to get image size
get_size() {
    local image=$1
    if docker images "$image" --format "{{.Size}}" 2>/dev/null | grep -q .; then
        docker images "$image" --format "{{.Size}}"
    else
        echo "N/A"
    fi
}

# Function to get size in bytes for comparison
get_size_bytes() {
    local image=$1
    if docker images "$image" --format "{{.Size}}" 2>/dev/null | grep -q .; then
        local size=$(docker images "$image" --format "{{.Size}}")
        # Convert to bytes using awk (more portable than bc)
        echo "$size" | awk '{
            # Split value and unit
            if (NF == 1) {
                # Format like "123MB" - need to separate
                match($0, /^[0-9.]+/);
                val = substr($0, RSTART, RLENGTH);
                unit = substr($0, RLENGTH + 1);
            } else {
                # Format like "123 MB"
                val = $1;
                unit = $2;
            }
            # Convert to bytes
            if (unit == "GB") printf "%.0f", val * 1073741824;
            else if (unit == "MB") printf "%.0f", val * 1048576;
            else if (unit == "KB") printf "%.0f", val * 1024;
            else if (unit == "B") printf "%.0f", val;
            else print 0;
        }'
    else
        echo "0"
    fi
}

# Check if images exist
echo -e "${YELLOW}Checking for existing images...${NC}"
echo ""

# Get sizes
ROCM_SIZE=$(get_size "transcript-create:rocm")
ROCM_BYTES=$(get_size_bytes "transcript-create:rocm")
CPU_SIZE=$(get_size "transcript-create:cpu")
CPU_BYTES=$(get_size_bytes "transcript-create:cpu")
CUDA_SIZE=$(get_size "transcript-create:cuda")
CUDA_BYTES=$(get_size_bytes "transcript-create:cuda")
OLD_SIZE=$(get_size "transcript-create:old")
OLD_BYTES=$(get_size_bytes "transcript-create:old")

# Display results in table format
echo -e "${GREEN}Image Size Comparison:${NC}"
echo ""
printf "%-30s %-15s %-15s\n" "Variant" "Size" "Target"
printf "%-30s %-15s %-15s\n" "$(printf '%.0s-' {1..30})" "$(printf '%.0s-' {1..15})" "$(printf '%.0s-' {1..15})"

# ROCm
if [ "$ROCM_SIZE" != "N/A" ]; then
    TARGET_MET=""
    if [ "$ROCM_BYTES" -lt 2684354560 ]; then  # 2.5GB in bytes
        TARGET_MET="${GREEN}✓${NC}"
    else
        TARGET_MET="${RED}✗${NC}"
    fi
    printf "%-30s %-15s %-15s %b\n" "ROCm (optimized)" "$ROCM_SIZE" "<2.5GB" "$TARGET_MET"
else
    printf "%-30s %-15s %-15s\n" "ROCm (optimized)" "Not built" "<2.5GB"
fi

# CPU
if [ "$CPU_SIZE" != "N/A" ]; then
    TARGET_MET=""
    if [ "$CPU_BYTES" -lt 1073741824 ]; then  # 1GB in bytes
        TARGET_MET="${GREEN}✓${NC}"
    else
        TARGET_MET="${RED}✗${NC}"
    fi
    printf "%-30s %-15s %-15s %b\n" "CPU-only (optimized)" "$CPU_SIZE" "<1GB" "$TARGET_MET"
else
    printf "%-30s %-15s %-15s\n" "CPU-only (optimized)" "Not built" "<1GB"
fi

# CUDA
if [ "$CUDA_SIZE" != "N/A" ]; then
    TARGET_MET=""
    if [ "$CUDA_BYTES" -lt 2684354560 ]; then  # 2.5GB in bytes
        TARGET_MET="${GREEN}✓${NC}"
    else
        TARGET_MET="${RED}✗${NC}"
    fi
    printf "%-30s %-15s %-15s %b\n" "CUDA (optimized)" "$CUDA_SIZE" "<2.5GB" "$TARGET_MET"
else
    printf "%-30s %-15s %-15s\n" "CUDA (optimized)" "Not built" "<2.5GB"
fi

# Original
if [ "$OLD_SIZE" != "N/A" ]; then
    printf "%-30s %-15s %-15s\n" "Original (for comparison)" "$OLD_SIZE" "~3GB"
fi

echo ""

# Calculate savings if both old and new exist
if [ "$ROCM_SIZE" != "N/A" ] && [ "$OLD_SIZE" != "N/A" ] && [ "$ROCM_BYTES" -gt 0 ] && [ "$OLD_BYTES" -gt 0 ]; then
    SAVINGS=$((OLD_BYTES - ROCM_BYTES))
    SAVINGS_PERCENT=$((SAVINGS * 100 / OLD_BYTES))
    if [ "$SAVINGS" -gt 0 ]; then
        # Use awk for floating point division
        SAVINGS_GB=$(echo "$SAVINGS" | awk '{printf "%.2f", $1 / 1073741824}')
        echo -e "${GREEN}Space saved (ROCm vs Original): ${SAVINGS_GB}GB (${SAVINGS_PERCENT}%)${NC}"
    fi
fi

echo ""
echo -e "${YELLOW}Notes:${NC}"
echo "- Multi-stage builds improve layer caching and build speed"
echo "- BuildKit cache mounts reduce rebuild time significantly"
echo "- Image sizes depend on installed dependencies from requirements.txt"
echo "- For smaller CPU images, consider creating minimal requirements file"
echo "- ROCm and CUDA images include GPU libraries which increase size"
echo ""

# Show layer breakdown for built images
if [ "$ROCM_SIZE" != "N/A" ]; then
    echo -e "${YELLOW}Layer breakdown for ROCm variant:${NC}"
    docker history transcript-create:rocm --human=true --format "table {{.Size}}\t{{.CreatedSince}}\t{{.CreatedBy}}" | head -10
    echo ""
fi
