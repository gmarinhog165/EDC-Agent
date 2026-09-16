#!/usr/bin/env bash
# Run the full Fetching Agent testbed (extraction + faithfulness) for one or more
# models and append a one-line summary per run to results/summary.csv.
#
# Usage:
#   ./run_all.sh                       # uses $LLM_MODEL (or qwen2.5:7b)
#   ./run_all.sh qwen2.5:7b llama3.1:8b
#   PROMPT_VERSION=v5 RUNS=5 ./run_all.sh qwen2.5:7b
#
# Env overrides:
#   RUNS            runs per test         (default 3)
#   PROMPT_VERSION  fetch prompt version  (default: flat / current)
#   TEMPERATURE     model temperature     (default 0)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNNER="$SCRIPT_DIR/run_fetch_case.py"
RESULTS_DIR="$SCRIPT_DIR/results"
SUMMARY_CSV="$RESULTS_DIR/summary.csv"

RUNS="${RUNS:-3}"
TEMPERATURE="${TEMPERATURE:-0}"
PROMPT_VERSION="${PROMPT_VERSION:-v4}"

mkdir -p "$RESULTS_DIR"

# Default model list: CLI args, else $LLM_MODEL, else qwen2.5:7b.
if [[ "$#" -gt 0 ]]; then
  MODELS=("$@")
else
  MODELS=("${LLM_MODEL:-qwen3.5:9b}")
fi

PV_ARGS=()
[[ -n "$PROMPT_VERSION" ]] && PV_ARGS=(--prompt-version "$PROMPT_VERSION")

# CSV header (written once).
if [[ ! -f "$SUMMARY_CSV" ]]; then
  echo "timestamp,git_sha,model,prompt_version,runs,extr_success,extr_precision,extr_recall,extr_single_call,faith_success,json_path" > "$SUMMARY_CSV"
fi

overall_rc=0
for model in "${MODELS[@]}"; do
  echo "=============================================================="
  echo ">> model=$model prompt=${PROMPT_VERSION:-flat} runs=$RUNS temp=$TEMPERATURE"
  echo "=============================================================="

  run_out="$(python3 "$RUNNER" all \
      --model "$model" \
      --runs "$RUNS" \
      --temperature "$TEMPERATURE" \
      "${PV_ARGS[@]}")" || overall_rc=$?

  echo "$run_out"

  json_path="$(printf '%s\n' "$run_out" | sed -n 's/^json_report: //p' | tail -1)"
  if [[ -z "$json_path" || ! -f "$json_path" ]]; then
    echo "WARN: could not locate JSON report for model=$model; skipping aggregation." >&2
    continue
  fi

  # Pull the summary numbers out of the run's JSON and append a ledger row.
  python3 - "$json_path" "$SUMMARY_CSV" <<'PY'
import json, sys
json_path, csv_path = sys.argv[1], sys.argv[2]
d = json.load(open(json_path))
e = d["summary"]["extraction"]
f = d["summary"]["faithfulness"]
row = [
    d.get("timestamp", ""),
    d.get("git_sha", ""),
    d.get("model", ""),
    d.get("prompt_version", ""),
    str(d.get("runs_per_test", "")),
    f'{e.get("success_rate", 0):.4f}',
    f'{e.get("id_precision", 0):.4f}',
    f'{e.get("id_recall", 0):.4f}',
    f'{e.get("single_call_rate", 0):.4f}',
    f'{f.get("success_rate", 0):.4f}',
    json_path,
]
with open(csv_path, "a", encoding="utf-8") as fh:
    fh.write(",".join(row) + "\n")
print(f"aggregated -> {csv_path}")
PY
done

echo
echo "Ledger: $SUMMARY_CSV"
column -s, -t "$SUMMARY_CSV" 2>/dev/null || cat "$SUMMARY_CSV"

exit "$overall_rc"
