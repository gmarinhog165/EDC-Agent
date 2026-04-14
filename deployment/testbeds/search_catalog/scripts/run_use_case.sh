#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ROOT_DIR="$(cd "${BASE_DIR}/../../.." && pwd)"

if [ "$#" -lt 1 ]; then
  echo "Uso: $0 <use_case_id> [args adicionais para run_use_case.py]"
  exit 1
fi

USE_CASE="$1"
shift

cd "${ROOT_DIR}"
python3 "${BASE_DIR}/run_use_case.py" "${USE_CASE}" "$@"
