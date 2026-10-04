#!/usr/bin/env bash
# Regenerate the OpenAPI document and fail if the committed copy differs.
set -Eeuo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
COMMITTED="${ROOT}/docs/api/openapi.json"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT

cd "${ROOT}"
"${PYTHON_BIN}" scripts/generate_openapi.py "${TMP_DIR}/openapi.json"

if ! cmp --silent "${TMP_DIR}/openapi.json" "${COMMITTED}"; then
  echo "docs/api/openapi.json is out of date with the API. Run 'make openapi' and commit the result." >&2
  diff -u "${COMMITTED}" "${TMP_DIR}/openapi.json" | head -n 40 >&2 || true
  exit 1
fi
echo 'OpenAPI contract matches docs/api/openapi.json.'
