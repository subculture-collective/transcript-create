#!/usr/bin/env bash
# =============================================================================
# Build script for ROCm variant
# =============================================================================
# Builds the optimized multi-stage Docker image for ROCm GPU acceleration.
#
# Usage:
#   ./build-rocm.sh [rocm_version] [--no-cache] [--push]
#
# Arguments:
#   rocm_version - ROCm version (6.0, 6.1, 6.2), default: 6.0
#   --no-cache   - Build without using cache
#   --push       - Push to registry after build
#
# Examples:
#   ./build-rocm.sh                    # Build with ROCm 6.0 and cache
#   ./build-rocm.sh 6.1 --no-cache     # Build ROCm 6.1 without cache
#   ./build-rocm.sh 6.0 --push         # Build and push to registry
# =============================================================================

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Default values
ROCM_VERSION="${1:-6.0}"
NO_CACHE=""
PUSH_IMAGE=false
IMAGE_NAME="${IMAGE_NAME:-transcript-create}"
IMAGE_TAG="${IMAGE_TAG:-rocm${ROCM_VERSION}}"

# Parse arguments
shift || true
while [[ $# -gt 0 ]]; do
    case $1 in
        --no-cache)
            NO_CACHE="--no-cache"
            shift
            ;;
        --push)
            PUSH_IMAGE=true
            shift
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

echo -e "${GREEN}Building ROCm Docker image${NC}"
echo "  ROCm version: ${ROCM_VERSION}"
echo "  Image name:   ${IMAGE_NAME}:${IMAGE_TAG}"
echo "  No cache:     ${NO_CACHE:-false}"
echo "  Push:         ${PUSH_IMAGE}"
echo ""

# Enable BuildKit for better caching and performance
export DOCKER_BUILDKIT=1

# Build the image
echo -e "${YELLOW}Building image...${NC}"
docker build \
    ${NO_CACHE} \
    --target app \
    --build-arg ROCM_WHEEL_INDEX=https://download.pytorch.org/whl/rocm${ROCM_VERSION} \
    --tag "${IMAGE_NAME}:${IMAGE_TAG}" \
    --tag "${IMAGE_NAME}:latest" \
    --file Dockerfile \
    .

# Get image size
IMAGE_SIZE=$(docker images "${IMAGE_NAME}:${IMAGE_TAG}" --format "{{.Size}}")
echo -e "${GREEN}✓ Build complete${NC}"
echo "  Image size: ${IMAGE_SIZE}"

# Verify the build
echo ""
echo -e "${YELLOW}Verifying build...${NC}"
docker run --rm "${IMAGE_NAME}:${IMAGE_TAG}" python3 -c "import torch; print('✓ Torch version:', torch.__version__)"

# Push if requested
if [ "${PUSH_IMAGE}" = true ]; then
    echo ""
    echo -e "${YELLOW}Pushing image...${NC}"
    docker push "${IMAGE_NAME}:${IMAGE_TAG}"
    docker push "${IMAGE_NAME}:latest"
    echo -e "${GREEN}✓ Image pushed${NC}"
fi

echo ""
echo -e "${GREEN}==================================${NC}"
echo -e "${GREEN}Build successful!${NC}"
echo -e "${GREEN}==================================${NC}"
echo "To run the container:"
echo "  docker run -p 8000:8000 ${IMAGE_NAME}:${IMAGE_TAG}"
