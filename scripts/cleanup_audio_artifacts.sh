#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/cleanup_audio_artifacts.sh [--delete] [--dry-run] [DIRECTORY]

Deletes temporary audio artifacts under DIRECTORY, recursively:
  - files named exactly raw.m4a
  - files named exactly chunk_0000.wav-style names with four digits

By default this script runs in dry-run mode and only prints matching files.
Pass --delete to remove them. Use only on inactive job directories after
reviewing the dry run; this utility does not coordinate with running workers.

Options:
  --delete   Delete matching files.
  --dry-run  Print matching files without deleting them. This is the default.
  -h, --help Show this help message.
USAGE
}

mode='dry-run'
target_dir='.'
target_set=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --delete)
      mode='delete'
      shift
      ;;
    --dry-run)
      mode='dry-run'
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      break
      ;;
    -*)
      printf 'Unknown option: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
    *)
      if [[ "$target_set" == true ]]; then
        printf 'Only one DIRECTORY may be provided. Unexpected argument: %s\n' "$1" >&2
        usage >&2
        exit 2
      fi
      target_dir=$1
      target_set=true
      shift
      ;;
  esac
done

if [[ $# -gt 0 ]]; then
  if [[ "$target_set" == true ]]; then
    printf 'Only one DIRECTORY may be provided. Unexpected argument: %s\n' "$1" >&2
    usage >&2
    exit 2
  fi
  target_dir=$1
  shift
  if [[ $# -gt 0 ]]; then
    printf 'Only one DIRECTORY may be provided.\n' >&2
    exit 2
  fi
fi

if [[ ! -d "$target_dir" ]]; then
  printf 'Directory not found: %s\n' "$target_dir" >&2
  exit 1
fi

# Absolute paths keep leading dashes out of find's expression parser.
# Complete discovery before deleting anything: process substitution would hide
# find failures and could otherwise produce a misleading success/partial cleanup.
target_dir=$(realpath -- "$target_dir")
manifest=$(mktemp)
trap 'rm -f -- "$manifest"' EXIT
find "$target_dir" -type f \( -name 'raw.m4a' -o -name 'chunk_[0-9][0-9][0-9][0-9].wav' \) -print0 > "$manifest"

count=0

if [[ "$mode" == 'dry-run' ]]; then
  while IFS= read -r -d '' file_path; do
    printf '%s\n' "$file_path"
    ((count += 1))
  done < "$manifest"

  printf 'Dry run: found %d matching file(s). Pass --delete to remove them.\n' "$count"
  exit 0
fi

while IFS= read -r -d '' file_path; do
  rm -- "$file_path"
  printf 'Deleted: %s\n' "$file_path"
  ((count += 1))
done < "$manifest"

printf 'Deleted %d matching file(s).\n' "$count"
