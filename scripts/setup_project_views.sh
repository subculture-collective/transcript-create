#!/usr/bin/env bash
set -euo pipefail

# This script creates saved views for Project 7: Priority and Milestone views.
# Requirements: gh >= 2.39, jq

OWNER=${OWNER:-onnwee}
PROJECT_NUMBER=${PROJECT_NUMBER:-7}

require() {
  command -v "$1" >/dev/null 2>&1 || { echo "Error: $1 is required" >&2; exit 1; }
}
require gh
require jq

echo "Looking up project $PROJECT_NUMBER for $OWNER..."
proj=$(gh api graphql -f query='query($owner: String!, $number: Int!) { user(login: $owner) { projectV2(number: $number) { id title views(first: 50) { nodes { id name } } } } }' -f variables="{\"owner\":\"$OWNER\",\"number\":$PROJECT_NUMBER}")
pid=$(echo "$proj" | jq -r '.data.user.projectV2.id')
ptitle=$(echo "$proj" | jq -r '.data.user.projectV2.title')
echo "Project: $ptitle ($pid)"

has_view() {
  local name=$1
  echo "$proj" | jq -e --arg n "$name" '.data.user.projectV2.views.nodes[]? | select(.name == $n) | .id' >/dev/null
}

create_view() {
  local name=$1
  local filter=$2
  echo "Ensuring view: $name ($filter)"
  if has_view "$name"; then
    echo "- View '$name' exists, skipping"
    return 0
  fi
  gh api graphql -f query='mutation($input: CreateProjectV2ViewInput!) { createProjectV2View(input: $input) { projectV2View { id name } } }' \
    -f variables="{\"input\":{\"ownerId\":null,\"projectId\":\"$pid\",\"name\":\"$name\",\"filter\":\"$filter\"}}" >/dev/null
  echo "- Created '$name'"
}

# Priority views
create_view "Priority: High" "label:'priority: high'"
create_view "Priority: Medium" "label:'priority: medium'"
create_view "Priority: Low" "label:'priority: low'"

# Milestone views (if milestones exist, these filters still work even if empty)
create_view "Milestone: Stabilization & Cleanup" "milestone:'Stabilization & Cleanup'"
create_view "Milestone: Feature Completion" "milestone:'Feature Completion'"
create_view "Milestone: Documentation & Testing" "milestone:'Documentation & Testing'"
create_view "Milestone: Optimization & Scalability" "milestone:'Optimization & Scalability'"
create_view "Milestone: Professional Release v1.0" "milestone:'Professional Release v1.0'"

echo "Done."
