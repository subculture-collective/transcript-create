#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
    echo "Usage: $0 <image-ref>" >&2
    exit 2
fi

IMAGE_REF="$1"
TRIVY_IMAGE="${TRIVY_IMAGE:-aquasec/trivy:0.72.0}"
TRIVY_CACHE_DIR="${TRIVY_CACHE_DIR:-${TMPDIR:-/tmp}/hasanara-trivy-cache}"
mkdir -p "${TRIVY_CACHE_DIR}"
repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)

docker run --rm --network none --cpus=2 --memory=4g \
    -v "$repo_root/scripts/check_lightning_patch.py:/check.py:ro" \
    --entrypoint python3 "$IMAGE_REF" /check.py

docker run --rm \
    -v /var/run/docker.sock:/var/run/docker.sock \
    -v "${TRIVY_CACHE_DIR}:/root/.cache/" \
    -v "$repo_root/security/lightning-2.6.6.vex.json:/lightning.vex.json:ro" \
    "${TRIVY_IMAGE}" image \
    --scanners vuln \
    --pkg-types library \
    --severity HIGH,CRITICAL \
    --vex /lightning.vex.json \
    --exit-code 1 \
    "${IMAGE_REF}"
