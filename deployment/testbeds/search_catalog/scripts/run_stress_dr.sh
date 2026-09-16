#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
exec "${SCRIPT_DIR}/run_use_case.sh" "stress_dr" \
  --case-file "${BASE_DIR}/stress_use_cases.json" \
  "$@"
