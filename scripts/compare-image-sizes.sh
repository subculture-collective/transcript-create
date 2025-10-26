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
        docker images "$image" --format "{{.Size}}" | sed 's/GB/*1073741824/;s/MB/*1048576/;s/KB/*1024/' | bc 2>/dev/null || echo "0"
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
        SAVINGS_GB=$(echo "scale=2; $SAVINGS / 1073741824" | bc)
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
