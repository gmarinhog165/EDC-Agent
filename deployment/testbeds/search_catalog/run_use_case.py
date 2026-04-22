#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    def load_dotenv(*_args, **_kwargs):
        return False

ASSET_PATTERN = re.compile(r"\btb-[a-z]+-\d+\b", re.IGNORECASE)
_LOG_ASSET_RE = re.compile(
    r"\[(PASS|FAIL|HUB\s*)\]\s+score=([0-9.]+)\s+z=(-?[0-9.]+)\s+(tb-[a-z]+-\d+)",
    re.IGNORECASE,
)
_LOG_CUTOFF_RE = re.compile(r"dynamic cutoff at position (\d+)")
_LOG_FALLBACK_RE = re.compile(r"fallback top-(\d+)")

DEFAULT_CASE_FILE = Path(__file__).with_name("use_cases.json")
DEFAULT_RESULTS_DIR = Path(__file__).with_name("results")
SEARCH_TOOL_LOGGER = "edc_agent.tools.definitions.search_catalog_tool"


class _CapturingHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(self.format(record))

    def flush_records(self) -> list[str]:
        captured, self.records = self.records, []
        return captured


@dataclass
class RunResult:
    run_index: int
    greeting: str
    response: str
    found_assets: list[str]
    passed: bool
    failures: list[str]
    latency_s: float = 0.0
    search_tool_logs: list[str] = field(default_factory=list)
    reciprocal_rank: float | None = None
    tool_returned_assets: list[str] = field(default_factory=list)
    retrieval_passed: bool = False
    retrieval_failures: list[str] = field(default_factory=list)
    retrieval_reciprocal_rank: float | None = None


@dataclass
class TestResult:
    use_case_id: str
    test_id: str
    query: str
    runs: list[RunResult]
    pass_rate: float
    passed: bool
    latency_mean_s: float = 0.0
    latency_min_s: float = 0.0
    latency_max_s: float = 0.0
    mrr: float | None = None
    retrieval_pass_rate: float = 0.0
    retrieval_passed: bool = False
    retrieval_mrr: float | None = None


def load_env_file(env_path: Path, override: bool = False) -> None:
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            value = value[1:-1]
        if override or key not in os.environ:
            os.environ[key] = value


def build_manager(model_name: str, temperature: int):
    from edc_agent.agents.agent import Agent
    from edc_agent.clients.ollama_client import OllamaClient
    from edc_agent.manager import PipelineManager
    from edc_agent.prompts.prompt_registry import get_prompt
    from edc_agent.tools.definitions import fetch_item_data_tool, search_catalog_tool

    llm_client = OllamaClient(model_name=model_name, temperature=temperature)
    router_agent = Agent(
        name="router",
        llm_client=llm_client,
        system_prompt=get_prompt(agent_name="router", model_name=model_name),
    )
    search_catalog_agent = Agent(
        name="search-catalog",
        llm_client=llm_client,
        system_prompt=get_prompt(agent_name="search-catalog", model_name=model_name),
        tools=[search_catalog_tool],
    )
    fetch_data_agent = Agent(
        name="fetch-data",
        llm_client=llm_client,
        system_prompt=get_prompt(agent_name="fetch-data", model_name=model_name),
        tools=[fetch_item_data_tool],
    )
    return PipelineManager(
        router_agent=router_agent,
        search_catalog_agent=search_catalog_agent,
        fetch_data_agent=fetch_data_agent,
    )


def load_use_cases(case_file: Path) -> list[dict[str, Any]]:
    payload = json.loads(case_file.read_text(encoding="utf-8"))
    use_cases = payload.get("use_cases", [])
    if not isinstance(use_cases, list) or not use_cases:
        raise ValueError(f"No use cases found in {case_file}")
    return use_cases


def select_use_cases(use_cases: list[dict[str, Any]], selected_id: str | None) -> list[dict[str, Any]]:
    if not selected_id or selected_id == "all":
        return use_cases
    selected = [case for case in use_cases if case.get("id") == selected_id]
    if not selected:
        available = ", ".join(case.get("id", "<missing>") for case in use_cases)
        raise ValueError(f"Unknown use case '{selected_id}'. Available: {available}")
    return selected


def extract_asset_ids(text: str) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for match in ASSET_PATTERN.findall(text or ""):
        asset_id = match.lower()
        if asset_id not in seen:
            seen.add(asset_id)
            ordered.append(asset_id)
    return ordered


def parse_search_logs(logs: list[str]) -> list[dict[str, Any]]:
    """Parse search tool logs into per-asset score details (informational only)."""
    asset_details: list[dict[str, Any]] = []
    for line in logs:
        m = _LOG_ASSET_RE.search(line)
        if m:
            asset_details.append({
                "asset_id": m.group(4).lower(),
                "score": float(m.group(2)),
                "z_score": float(m.group(3)),
                "status": m.group(1).strip().upper(),
            })
    return asset_details


def extract_tool_returned_assets(logs: list[str]) -> list[str]:
    """Reconstruct the ordered asset list the tool returned to the LLM.

    PASS entries sorted by score descending, truncated at the dynamic cutoff
    position (or the fallback top-N when no significant gap is detected).
    Returns [] when no tool call was logged.
    """
    passes: list[tuple[str, float]] = []
    cut: int | None = None
    tool_called = False
    for line in logs:
        if "cosine scores" in line:
            tool_called = True
        m = _LOG_ASSET_RE.search(line)
        if m and m.group(1).strip().upper() == "PASS":
            passes.append((m.group(4).lower(), float(m.group(2))))
            continue
        m = _LOG_CUTOFF_RE.search(line)
        if m:
            cut = int(m.group(1))
            continue
        m = _LOG_FALLBACK_RE.search(line)
        if m:
            cut = int(m.group(1))
            continue
    if not tool_called:
        return []
    passes.sort(key=lambda x: x[1], reverse=True)
    if cut is not None:
        passes = passes[:cut]
    return [asset_id for asset_id, _ in passes]


def evaluate_assets(
    test: dict[str, Any],
    assets: list[str],
    response: str | None = None,
) -> tuple[bool, list[str]]:
    """Evaluate an ordered asset list against test expectations.

    Rules:
    - expected_count: exact count match
    - expected_present: these assets must appear; any asset NOT in this set is also a failure (strict)
    - expected_pool: any returned asset must belong to this set (permissive — not all need to appear)
    - expected_order: used only for MRR, does not affect pass/fail

    ``response`` only applies to the presentation layer (LLM output); pass None
    when evaluating the retrieval layer.
    """
    failures: list[str] = []
    found_set = set(assets)

    expected_present = [str(a).lower() for a in test.get("expected_present", [])]
    expected_pool = [str(a).lower() for a in test.get("expected_pool", [])]
    expected_count = test.get("expected_count")

    if expected_count is not None and len(assets) != int(expected_count):
        failures.append(f"expected_count={expected_count}, found_count={len(assets)}")

    if response is not None and expected_count == 0 and "asset_id" in response.lower():
        failures.append("hallucinated_assets_in_response")

    for asset_id in expected_present:
        if asset_id not in found_set:
            failures.append(f"missing={asset_id}")

    if expected_present:
        expected_set = set(expected_present)
        for asset_id in assets:
            if asset_id not in expected_set:
                failures.append(f"unexpected={asset_id}")

    if expected_pool:
        pool_set = set(expected_pool)
        for asset_id in assets:
            if asset_id not in pool_set:
                failures.append(f"out_of_pool={asset_id}")

    return len(failures) == 0, failures


def compute_reciprocal_rank(found_assets: list[str], relevant: list[str]) -> float | None:
    """Return 1/rank of the first relevant hit, or None if expected_order is not defined."""
    if not relevant:
        return None
    relevant_set = set(str(a).lower() for a in relevant)
    for rank, asset_id in enumerate(found_assets, start=1):
        if asset_id in relevant_set:
            return 1.0 / rank
    return 0.0


def run_single(
    manager,
    _use_case_id: str,
    test: dict[str, Any],
    capturing_handler: _CapturingHandler,
    run_index: int,
) -> RunResult:
    capturing_handler.flush_records()
    manager.reset_history()
    greeting, _ = manager.start_conversation()
    t0 = time.perf_counter()
    process_result = manager.process(str(test["query"]))
    latency_s = time.perf_counter() - t0
    response = str(process_result[0]) if isinstance(process_result, tuple) else str(process_result)
    search_tool_logs = capturing_handler.flush_records()

    found_assets = extract_asset_ids(response)
    passed, failures = evaluate_assets(test, found_assets, response=response)
    expected_order = [str(a).lower() for a in test.get("expected_order", [])]
    rr = compute_reciprocal_rank(found_assets, expected_order)

    tool_returned_assets = extract_tool_returned_assets(search_tool_logs)
    retrieval_passed, retrieval_failures = evaluate_assets(test, tool_returned_assets)
    retrieval_rr = compute_reciprocal_rank(tool_returned_assets, expected_order)

    return RunResult(
        run_index=run_index,
        greeting=greeting,
        response=response,
        found_assets=found_assets,
        passed=passed,
        failures=failures,
        latency_s=latency_s,
        search_tool_logs=search_tool_logs,
        reciprocal_rank=rr,
        tool_returned_assets=tool_returned_assets,
        retrieval_passed=retrieval_passed,
        retrieval_failures=retrieval_failures,
        retrieval_reciprocal_rank=retrieval_rr,
    )


def run_test(
    manager,
    use_case_id: str,
    test: dict[str, Any],
    capturing_handler: _CapturingHandler,
    n_runs: int,
) -> TestResult:
    runs = [
        run_single(manager, use_case_id, test, capturing_handler, i)
        for i in range(n_runs)
    ]
    pass_rate = sum(r.passed for r in runs) / n_runs
    retrieval_pass_rate = sum(r.retrieval_passed for r in runs) / n_runs
    latencies = [r.latency_s for r in runs]
    rr_values = [r.reciprocal_rank for r in runs if r.reciprocal_rank is not None]
    mrr = sum(rr_values) / len(rr_values) if rr_values else None
    retrieval_rr_values = [
        r.retrieval_reciprocal_rank for r in runs if r.retrieval_reciprocal_rank is not None
    ]
    retrieval_mrr = (
        sum(retrieval_rr_values) / len(retrieval_rr_values) if retrieval_rr_values else None
    )
    return TestResult(
        use_case_id=use_case_id,
        test_id=str(test["id"]),
        query=str(test["query"]),
        runs=runs,
        pass_rate=pass_rate,
        passed=pass_rate == 1.0,
        latency_mean_s=sum(latencies) / len(latencies),
        latency_min_s=min(latencies),
        latency_max_s=max(latencies),
        mrr=mrr,
        retrieval_pass_rate=retrieval_pass_rate,
        retrieval_passed=retrieval_pass_rate == 1.0,
        retrieval_mrr=retrieval_mrr,
    )


def render_text_report(results: list[TestResult], model: str, selected_id: str, n_runs: int) -> str:
    now = datetime.now().isoformat(timespec="seconds")
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    retrieval_passed = sum(1 for r in results if r.retrieval_passed)
    success_rate = passed / total if total else 0.0
    retrieval_success_rate = retrieval_passed / total if total else 0.0
    all_latencies = [r.latency_s for result in results for r in result.runs]
    lat_mean = sum(all_latencies) / len(all_latencies) if all_latencies else 0.0
    lat_min = min(all_latencies) if all_latencies else 0.0
    lat_max = max(all_latencies) if all_latencies else 0.0

    mrr_values = [r.mrr for r in results if r.mrr is not None]
    mean_mrr = sum(mrr_values) / len(mrr_values) if mrr_values else None
    mrr_str = f"  mrr={mean_mrr:.4f} (n={len(mrr_values)})" if mean_mrr is not None else ""

    retrieval_mrr_values = [r.retrieval_mrr for r in results if r.retrieval_mrr is not None]
    retrieval_mean_mrr = (
        sum(retrieval_mrr_values) / len(retrieval_mrr_values) if retrieval_mrr_values else None
    )
    retrieval_mrr_str = (
        f"  mrr={retrieval_mean_mrr:.4f} (n={len(retrieval_mrr_values)})"
        if retrieval_mean_mrr is not None
        else ""
    )

    lines = [
        f"timestamp: {now}",
        f"model: {model}",
        f"selection: {selected_id}",
        f"runs_per_test: {n_runs}",
        f"presentation: passed={passed} failed={total - passed} total={total} success_rate={success_rate:.1%}{mrr_str}",
        f"retrieval:    passed={retrieval_passed} failed={total - retrieval_passed} total={total} success_rate={retrieval_success_rate:.1%}{retrieval_mrr_str}",
        f"latency: mean={lat_mean:.2f}s min={lat_min:.2f}s max={lat_max:.2f}s",
        "",
    ]

    current_case = None
    for result in results:
        if result.use_case_id != current_case:
            current_case = result.use_case_id
            lines.append(f"## use_case: {current_case}")

        ok = sum(r.passed for r in result.runs)
        retrieval_ok = sum(r.retrieval_passed for r in result.runs)
        mrr_tag = f"  mrr={result.mrr:.4f}" if result.mrr is not None else ""
        retrieval_mrr_tag = f"  mrr={result.retrieval_mrr:.4f}" if result.retrieval_mrr is not None else ""
        lines.append(f"- test_id: {result.test_id}")
        lines.append(f"  presentation: {'PASS' if result.passed else 'FAIL'} ({ok}/{n_runs}) success_rate={result.pass_rate:.1%}{mrr_tag}")
        lines.append(f"  retrieval:    {'PASS' if result.retrieval_passed else 'FAIL'} ({retrieval_ok}/{n_runs}) success_rate={result.retrieval_pass_rate:.1%}{retrieval_mrr_tag}")
        lines.append(f"  latency: mean={result.latency_mean_s:.2f}s min={result.latency_min_s:.2f}s max={result.latency_max_s:.2f}s")
        lines.append(f"  input: {result.query}")

        for run in result.runs:
            tag = "PASS" if run.passed else f"FAIL[{','.join(run.failures)}]"
            retrieval_tag = "PASS" if run.retrieval_passed else f"FAIL[{','.join(run.retrieval_failures)}]"
            rr_tag = f"  rr={run.reciprocal_rank:.4f}" if run.reciprocal_rank is not None else ""
            retrieval_rr_tag = (
                f"  rr={run.retrieval_reciprocal_rank:.4f}"
                if run.retrieval_reciprocal_rank is not None
                else ""
            )
            lines.append(f"  [run {run.run_index}] presentation={tag} latency={run.latency_s:.2f}s{rr_tag}")
            lines.append(f"             retrieval={retrieval_tag}{retrieval_rr_tag}")
            lines.append(f"    response: {run.response}")
            lines.append(f"    found_assets:         {', '.join(run.found_assets) or '[none]'}")
            lines.append(f"    tool_returned_assets: {', '.join(run.tool_returned_assets) or '[none]'}")

        first_logs = result.runs[0].search_tool_logs if result.runs else []
        if first_logs:
            lines.append("  search_tool_logs (run 0):")
            for log_line in first_logs:
                lines.append(f"    {log_line}")
        else:
            lines.append("  search_tool_logs (run 0): [none]")

        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def render_json_report(results: list[TestResult], model: str, selected_id: str, n_runs: int) -> str:
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    retrieval_passed = sum(1 for r in results if r.retrieval_passed)
    all_latencies = [r.latency_s for result in results for r in result.runs]
    lat_mean = sum(all_latencies) / len(all_latencies) if all_latencies else 0.0
    mrr_values = [r.mrr for r in results if r.mrr is not None]
    mean_mrr = round(sum(mrr_values) / len(mrr_values), 4) if mrr_values else None
    retrieval_mrr_values = [r.retrieval_mrr for r in results if r.retrieval_mrr is not None]
    retrieval_mean_mrr = (
        round(sum(retrieval_mrr_values) / len(retrieval_mrr_values), 4)
        if retrieval_mrr_values
        else None
    )
    payload = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "model": model,
        "selection": selected_id,
        "runs_per_test": n_runs,
        "summary": {
            "presentation": {
                "passed": passed,
                "failed": total - passed,
                "total": total,
                "success_rate": round(passed / total, 4) if total else 0.0,
                "mrr": mean_mrr,
            },
            "retrieval": {
                "passed": retrieval_passed,
                "failed": total - retrieval_passed,
                "total": total,
                "success_rate": round(retrieval_passed / total, 4) if total else 0.0,
                "mrr": retrieval_mean_mrr,
            },
            "latency_mean_s": round(lat_mean, 3),
            "latency_min_s": round(min(all_latencies), 3) if all_latencies else 0.0,
            "latency_max_s": round(max(all_latencies), 3) if all_latencies else 0.0,
        },
        "results": [
            {
                "use_case_id": result.use_case_id,
                "test_id": result.test_id,
                "query": result.query,
                "presentation_passed": result.passed,
                "presentation_pass_rate": result.pass_rate,
                "presentation_mrr": round(result.mrr, 4) if result.mrr is not None else None,
                "retrieval_passed": result.retrieval_passed,
                "retrieval_pass_rate": result.retrieval_pass_rate,
                "retrieval_mrr": round(result.retrieval_mrr, 4) if result.retrieval_mrr is not None else None,
                "latency_mean_s": round(result.latency_mean_s, 3),
                "latency_min_s": round(result.latency_min_s, 3),
                "latency_max_s": round(result.latency_max_s, 3),
                "runs": [
                    {
                        "run_index": run.run_index,
                        "greeting": run.greeting,
                        "response": run.response,
                        "found_assets": run.found_assets,
                        "tool_returned_assets": run.tool_returned_assets,
                        "presentation_passed": run.passed,
                        "presentation_failures": run.failures,
                        "presentation_reciprocal_rank": run.reciprocal_rank,
                        "retrieval_passed": run.retrieval_passed,
                        "retrieval_failures": run.retrieval_failures,
                        "retrieval_reciprocal_rank": run.retrieval_reciprocal_rank,
                        "latency_s": round(run.latency_s, 3),
                        "search_tool_logs": run.search_tool_logs,
                    }
                    for run in result.runs
                ],
            }
            for result in results
        ],
    }
    return json.dumps(payload, ensure_ascii=True, indent=2) + "\n"


def build_output_path(results_dir: Path, selection: str, extension: str) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return results_dir / f"{selection}_{timestamp}.{extension}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run search catalog use case evaluations.")
    parser.add_argument("use_case", nargs="?", default="all", help="Use case id or 'all'.")
    parser.add_argument("--case-file", default=str(DEFAULT_CASE_FILE), help="Path to use case JSON file.")
    parser.add_argument("--output", default=None, help="Optional explicit text output file path.")
    parser.add_argument("--json-output", default=None, help="Optional explicit JSON output file path.")
    parser.add_argument("--results-dir", default=str(DEFAULT_RESULTS_DIR), help="Directory for generated reports.")
    parser.add_argument("--model", default=os.getenv("LLM_MODEL", ""), help="Ollama chat model.")
    parser.add_argument("--temperature", type=int, default=0, help="Model temperature.")
    parser.add_argument("--runs", type=int, default=1, help="Number of runs per test.")
    parser.add_argument("--list", action="store_true", help="List available use case ids and exit.")
    return parser.parse_args()


def main() -> int:
    load_dotenv()
    load_env_file(ROOT / ".env")
    args = parse_args()

    case_file = Path(args.case_file).resolve()
    results_dir = Path(args.results_dir).resolve()
    results_dir.mkdir(parents=True, exist_ok=True)

    use_cases = load_use_cases(case_file)
    if args.list:
        for case in use_cases:
            print(f"{case.get('id')}: {case.get('title', '')}")
        return 0

    if not args.model:
        print("LLM_MODEL is not configured. Set it in .env or pass --model <name:tag>.")
        return 2

    selected_cases = select_use_cases(use_cases, args.use_case)
    try:
        manager = build_manager(model_name=args.model, temperature=args.temperature)
    except ModuleNotFoundError as exc:
        missing = getattr(exc, "name", "dependency")
        print(
            f"Missing Python dependency: {missing}. "
            "Install project dependencies first with: pip install -e ."
        )
        return 2

    capturing_handler = _CapturingHandler()
    capturing_handler.setLevel(logging.INFO)
    capturing_handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    tool_logger = logging.getLogger(SEARCH_TOOL_LOGGER)
    tool_logger.setLevel(logging.DEBUG)
    tool_logger.addHandler(capturing_handler)

    results: list[TestResult] = []
    for use_case in selected_cases:
        for test in use_case.get("tests", []):
            results.append(run_test(manager, str(use_case["id"]), test, capturing_handler, args.runs))

    tool_logger.removeHandler(capturing_handler)

    selection = args.use_case or "all"
    text_report = render_text_report(results, args.model, selection, args.runs)
    json_report = render_json_report(results, args.model, selection, args.runs)

    text_output = Path(args.output).resolve() if args.output else build_output_path(results_dir, selection, "log")
    json_output = Path(args.json_output).resolve() if args.json_output else build_output_path(results_dir, selection, "json")

    text_output.write_text(text_report, encoding="utf-8")
    json_output.write_text(json_report, encoding="utf-8")

    print(text_report, end="")
    print(f"text_report: {text_output}")
    print(f"json_report: {json_output}")

    return 0 if all(r.passed for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
