#!/usr/bin/env bash
# =============================================================================
# Build script for CUDA variant
# =============================================================================
# Builds the optimized multi-stage Docker image for NVIDIA CUDA GPU acceleration.
#
# Usage:
#   ./build-cuda.sh [cuda_version] [--no-cache] [--push]
#
# Arguments:
#   cuda_version - audited CUDA version (12.6 only), default: 12.6
#   --no-cache   - Build without using cache
#   --push       - Push to registry after build
#
# Examples:
#   ./build-cuda.sh                    # Build with CUDA 12.6 and cache
#   ./build-cuda.sh 12.6 --no-cache    # Build CUDA 12.6 without cache
#   ./build-cuda.sh 12.6 --push        # Scan, then push to registry
# =============================================================================

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Default values
CUDA_VERSION="${1:-12.6}"
NO_CACHE=""
PUSH_IMAGE=false
IMAGE_NAME="${IMAGE_NAME:-hasanara}"
IMAGE_TAG="${IMAGE_TAG:-cuda${CUDA_VERSION}}"

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

# Map CUDA version to PyTorch wheel index
case ${CUDA_VERSION} in
    12.6)
        CUDA_WHEEL_INDEX="https://download.pytorch.org/whl/cu126"
        ;;
    *)
        echo -e "${RED}Unsupported CUDA version: ${CUDA_VERSION}${NC}"
        echo "Supported version: 12.6"
        exit 1
        ;;
esac

echo -e "${GREEN}Building CUDA Docker image${NC}"
echo "  CUDA version: ${CUDA_VERSION}"
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
    --build-arg CUDA_WHEEL_INDEX="${CUDA_WHEEL_INDEX}" \
    --tag "${IMAGE_NAME}:${IMAGE_TAG}" \
    --tag "${IMAGE_NAME}:cuda" \
    --file Dockerfile.cuda \
    .

# Get image size
IMAGE_SIZE=$(docker images "${IMAGE_NAME}:${IMAGE_TAG}" --format "{{.Size}}")
echo -e "${GREEN}✓ Build complete${NC}"
echo "  Image size: ${IMAGE_SIZE}"

# Verify the build
echo ""
echo -e "${YELLOW}Verifying build...${NC}"
docker run --rm "${IMAGE_NAME}:${IMAGE_TAG}" python3 -c "import torch; print('✓ Torch version:', torch.__version__)"
"$(dirname "$0")/scan-container-image.sh" "${IMAGE_NAME}:${IMAGE_TAG}"

# Push if requested
if [ "${PUSH_IMAGE}" = true ]; then
    echo ""
    echo -e "${YELLOW}Pushing image...${NC}"
    docker push "${IMAGE_NAME}:${IMAGE_TAG}"
    docker push "${IMAGE_NAME}:cuda"
    echo -e "${GREEN}✓ Image pushed${NC}"
fi

echo ""
echo -e "${GREEN}==================================${NC}"
echo -e "${GREEN}Build successful!${NC}"
echo -e "${GREEN}==================================${NC}"
echo "To run the container:"
echo "  docker run --gpus all -p 8000:8000 ${IMAGE_NAME}:${IMAGE_TAG}"
