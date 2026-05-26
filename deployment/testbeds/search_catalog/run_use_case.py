#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
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

ASSET_PATTERN = re.compile(r"\b[a-z][a-z0-9]*(?:-[a-z][a-z0-9]*)*-\d+\b", re.IGNORECASE)
_LOG_ASSET_RE = re.compile(
    r"\[(PASS|FAIL|HUB\s*)\]\s+score=([0-9.]+)\s+z=(-?[0-9.]+)\s+([a-z][a-z0-9]*(?:-[a-z0-9]+)*-\d+)",
    re.IGNORECASE,
)
_LOG_CUTOFF_RE = re.compile(r"dynamic cutoff at position (\d+)")
_LOG_FALLBACK_RE = re.compile(r"fallback top-(\d+)")
_LOG_DIAGNOSTICS_RE = re.compile(r"search_catalog_diagnostics (\{.+\})\s*$")
_LOG_LINES_LIMIT = 100

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
    failures: list[dict[str, Any]]
    latency_s: float = 0.0
    search_tool_logs: list[str] = field(default_factory=list)
    reciprocal_rank: float | None = None
    tool_returned_assets: list[str] = field(default_factory=list)
    retrieval_passed: bool = False
    retrieval_failures: list[dict[str, Any]] = field(default_factory=list)
    retrieval_reciprocal_rank: float | None = None
    presentation_precision: float | None = None
    presentation_recall: float | None = None
    retrieval_precision: float | None = None
    retrieval_recall: float | None = None
    tool_diagnostics: dict | None = None


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
    latency_std_s: float = 0.0
    mrr: float | None = None
    retrieval_pass_rate: float = 0.0
    retrieval_passed: bool = False
    retrieval_mrr: float | None = None
    presentation_precision: float | None = None
    presentation_recall: float | None = None
    retrieval_precision: float | None = None
    retrieval_recall: float | None = None


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


def build_manager(model_name: str, temperature: int, prompt_version: str | None = None):
    from edc_agent.agents.agent import Agent
    from edc_agent.clients.ollama_client import OllamaClient
    from edc_agent.manager import PipelineManager
    from edc_agent.prompts.prompt_registry import get_prompt
    from edc_agent.tools.definitions import fetch_item_data_tool, search_catalog_tool

    llm_client = OllamaClient(model_name=model_name, temperature=temperature)
    router_agent = Agent(
        name="router",
        llm_client=llm_client,
        system_prompt=get_prompt(agent_name="router", _model_name=model_name),
    )
    search_catalog_agent = Agent(
        name="search-catalog",
        llm_client=llm_client,
        system_prompt=get_prompt(
            agent_name="search-catalog",
            _model_name=model_name,
            version=prompt_version,
        ),
        tools=[search_catalog_tool],
    )
    fetch_data_agent = Agent(
        name="fetch-data",
        llm_client=llm_client,
        system_prompt=get_prompt(agent_name="fetch-data", _model_name=model_name),
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


def parse_tool_diagnostics(logs: list[str]) -> dict | None:
    """Extract structured diagnostics emitted by search_catalog_tool as a JSON log line."""
    for line in logs:
        m = _LOG_DIAGNOSTICS_RE.search(line)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                return None
    return None


def _assets_from_diagnostics(diag: dict) -> list[str]:
    """Reconstruct ordered tool-returned asset list from structured diagnostics."""
    scores = diag.get("per_asset_scores", [])
    cutoff = diag.get("cutoff") or {}
    passed = [(s["asset_id"].lower(), s["score"]) for s in scores if s.get("status") == "PASS"]
    passed.sort(key=lambda x: x[1], reverse=True)
    n = cutoff.get("position", len(passed))
    return [a for a, _ in passed[:n]]


def evaluate_assets(
    test: dict[str, Any],
    assets: list[str],
    response: str | None = None,
) -> tuple[bool, list[dict[str, Any]]]:
    """Evaluate an ordered asset list against test expectations.

    Rules:
    - expected_count: exact count match
    - expected_present: these assets must appear; any asset NOT in this set is also a failure (strict)
    - expected_pool: any returned asset must belong to this set (permissive — not all need to appear)
    - expected_order: used only for MRR, does not affect pass/fail

    ``response`` only applies to the presentation layer (LLM output); pass None
    when evaluating the retrieval layer.
    """
    failures: list[dict[str, Any]] = []
    found_set = set(assets)

    expected_present = [str(a).lower() for a in test.get("expected_present", [])]
    expected_pool = [str(a).lower() for a in test.get("expected_pool", [])]
    expected_count = test.get("expected_count")

    if expected_count is not None and len(assets) != int(expected_count):
        failures.append({"type": "expected_count", "expected": int(expected_count), "found": len(assets)})

    if response is not None and expected_count == 0 and "asset_id" in response.lower():
        failures.append({"type": "hallucinated_assets_in_response"})

    for asset_id in expected_present:
        if asset_id not in found_set:
            failures.append({"type": "missing", "asset_id": asset_id})

    if expected_present:
        expected_set = set(expected_present)
        for asset_id in assets:
            if asset_id not in expected_set:
                failures.append({"type": "unexpected", "asset_id": asset_id})

    if expected_pool:
        pool_set = set(expected_pool)
        for asset_id in assets:
            if asset_id not in pool_set:
                failures.append({"type": "out_of_pool", "asset_id": asset_id})

    return len(failures) == 0, failures


def _fmt_failure(f: dict[str, Any]) -> str:
    t = f.get("type", "?")
    if t == "expected_count":
        return f"expected_count={f['expected']},found={f['found']}"
    if t in ("missing", "unexpected", "out_of_pool"):
        return f"{t}={f.get('asset_id', '?')}"
    return t


def compute_reciprocal_rank(found_assets: list[str], relevant: list[str]) -> float | None:
    """Return 1/rank of the first relevant hit, or None if expected_order is not defined."""
    if not relevant:
        return None
    relevant_set = set(str(a).lower() for a in relevant)
    for rank, asset_id in enumerate(found_assets, start=1):
        if asset_id in relevant_set:
            return 1.0 / rank
    return 0.0


def compute_precision_recall(
    assets: list[str], relevant: list[str]
) -> tuple[float | None, float | None]:
    """Return (precision, recall) against a relevant set, or (None, None) when relevant is empty."""
    if not relevant:
        return None, None
    relevant_set = set(str(a).lower() for a in relevant)
    tp = sum(1 for a in assets if a in relevant_set)
    precision = tp / len(assets) if assets else 0.0
    recall = tp / len(relevant_set)
    return precision, recall


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
    expected_present = [str(a).lower() for a in test.get("expected_present", [])]
    rr = compute_reciprocal_rank(found_assets, expected_order)
    pres_precision, pres_recall = compute_precision_recall(found_assets, expected_present)

    tool_diagnostics = parse_tool_diagnostics(search_tool_logs)
    if tool_diagnostics is not None:
        tool_returned_assets = _assets_from_diagnostics(tool_diagnostics)
    else:
        tool_returned_assets = extract_tool_returned_assets(search_tool_logs)
    retrieval_passed, retrieval_failures = evaluate_assets(test, tool_returned_assets)
    retrieval_rr = compute_reciprocal_rank(tool_returned_assets, expected_order)
    retr_precision, retr_recall = compute_precision_recall(tool_returned_assets, expected_present)

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
        presentation_precision=pres_precision,
        presentation_recall=pres_recall,
        retrieval_precision=retr_precision,
        retrieval_recall=retr_recall,
        tool_diagnostics=tool_diagnostics,
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
    def _mean_or_none(vals: list[float | None]) -> float | None:
        xs = [v for v in vals if v is not None]
        return sum(xs) / len(xs) if xs else None

    pass_rate = sum(r.passed for r in runs) / n_runs
    retrieval_pass_rate = sum(r.retrieval_passed for r in runs) / n_runs
    latencies = [r.latency_s for r in runs]
    lat_mean = sum(latencies) / len(latencies)
    lat_std = (sum((l - lat_mean) ** 2 for l in latencies) / len(latencies)) ** 0.5
    mrr = _mean_or_none([r.reciprocal_rank for r in runs])
    retrieval_mrr = _mean_or_none([r.retrieval_reciprocal_rank for r in runs])
    return TestResult(
        use_case_id=use_case_id,
        test_id=str(test["id"]),
        query=str(test["query"]),
        runs=runs,
        pass_rate=pass_rate,
        passed=pass_rate == 1.0,
        latency_mean_s=lat_mean,
        latency_min_s=min(latencies),
        latency_max_s=max(latencies),
        latency_std_s=lat_std,
        mrr=mrr,
        retrieval_pass_rate=retrieval_pass_rate,
        retrieval_passed=retrieval_pass_rate == 1.0,
        retrieval_mrr=retrieval_mrr,
        presentation_precision=_mean_or_none([r.presentation_precision for r in runs]),
        presentation_recall=_mean_or_none([r.presentation_recall for r in runs]),
        retrieval_precision=_mean_or_none([r.retrieval_precision for r in runs]),
        retrieval_recall=_mean_or_none([r.retrieval_recall for r in runs]),
    )


def run_single_retrieval_only(
    search_tool,
    _use_case_id: str,
    test: dict[str, Any],
    capturing_handler: _CapturingHandler,
    run_index: int,
) -> RunResult:
    """Run a single test using the search tool directly, bypassing the LLM."""
    capturing_handler.flush_records()
    t0 = time.perf_counter()
    results = search_tool._run(queries=[test["query"]])
    latency_s = time.perf_counter() - t0
    search_tool_logs = capturing_handler.flush_records()

    tool_returned_assets = [r["asset_id"].lower() for r in results]
    expected_order = [str(a).lower() for a in test.get("expected_order", [])]
    expected_present = [str(a).lower() for a in test.get("expected_present", [])]
    tool_diagnostics = parse_tool_diagnostics(search_tool_logs)

    retrieval_passed, retrieval_failures = evaluate_assets(test, tool_returned_assets)
    retrieval_rr = compute_reciprocal_rank(tool_returned_assets, expected_order)
    retr_precision, retr_recall = compute_precision_recall(tool_returned_assets, expected_present)

    return RunResult(
        run_index=run_index,
        greeting="",
        response="",
        found_assets=tool_returned_assets,
        passed=retrieval_passed,
        failures=retrieval_failures,
        latency_s=latency_s,
        search_tool_logs=search_tool_logs,
        reciprocal_rank=retrieval_rr,
        tool_returned_assets=tool_returned_assets,
        retrieval_passed=retrieval_passed,
        retrieval_failures=retrieval_failures,
        retrieval_reciprocal_rank=retrieval_rr,
        retrieval_precision=retr_precision,
        retrieval_recall=retr_recall,
        tool_diagnostics=tool_diagnostics,
    )


def run_test_retrieval_only(
    search_tool,
    use_case_id: str,
    test: dict[str, Any],
    capturing_handler: _CapturingHandler,
    n_runs: int,
) -> TestResult:
    runs = [
        run_single_retrieval_only(search_tool, use_case_id, test, capturing_handler, i)
        for i in range(n_runs)
    ]

    def _mean_or_none(vals: list[float | None]) -> float | None:
        xs = [v for v in vals if v is not None]
        return sum(xs) / len(xs) if xs else None

    pass_rate = sum(r.passed for r in runs) / n_runs
    latencies = [r.latency_s for r in runs]
    lat_mean = sum(latencies) / len(latencies)
    lat_std = (sum((l - lat_mean) ** 2 for l in latencies) / len(latencies)) ** 0.5
    retrieval_mrr = _mean_or_none([r.retrieval_reciprocal_rank for r in runs])
    return TestResult(
        use_case_id=use_case_id,
        test_id=str(test["id"]),
        query=str(test["query"]),
        runs=runs,
        pass_rate=pass_rate,
        passed=pass_rate == 1.0,
        latency_mean_s=lat_mean,
        latency_min_s=min(latencies),
        latency_max_s=max(latencies),
        latency_std_s=lat_std,
        mrr=retrieval_mrr,
        retrieval_pass_rate=pass_rate,
        retrieval_passed=pass_rate == 1.0,
        retrieval_mrr=retrieval_mrr,
        retrieval_precision=_mean_or_none([r.retrieval_precision for r in runs]),
        retrieval_recall=_mean_or_none([r.retrieval_recall for r in runs]),
    )


def _get_git_sha() -> str:
    import subprocess
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
            cwd=str(ROOT),
            text=True,
        ).strip()
    except Exception:
        return "unknown"


def _pop_std(vals: list[float | None]) -> float | None:
    xs = [v for v in vals if v is not None]
    if len(xs) < 2:
        return None
    mean = sum(xs) / len(xs)
    return round((sum((x - mean) ** 2 for x in xs) / len(xs)) ** 0.5, 4)


def render_text_report(results: list[TestResult], model: str, selected_id: str, n_runs: int, retrieval_only: bool = False, prompt_version: str | None = None, temperature: int = 0) -> str:
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

    def _smean(vals: list[float | None]) -> float | None:
        xs = [v for v in vals if v is not None]
        return sum(xs) / len(xs) if xs else None

    pres_prec = _smean([r.presentation_precision for r in results])
    pres_rec = _smean([r.presentation_recall for r in results])
    retr_prec = _smean([r.retrieval_precision for r in results])
    retr_rec = _smean([r.retrieval_recall for r in results])
    pres_pr_str = (
        f"  precision={pres_prec:.4f}  recall={pres_rec:.4f}"
        if pres_prec is not None else ""
    )
    retr_pr_str = (
        f"  precision={retr_prec:.4f}  recall={retr_rec:.4f}"
        if retr_prec is not None else ""
    )

    header_lines = [
        f"timestamp: {now}",
        f"git_sha: {_get_git_sha()}",
        f"model: {model or '(retrieval-only)'}",
        f"embedding_model: {os.getenv('EMBEDDING_MODEL', '')}",
        f"temperature: {temperature}",
        f"prompt_version: {prompt_version or 'flat'}",
        f"selection: {selected_id}",
        f"runs_per_test: {n_runs}",
    ]
    if retrieval_only:
        header_lines.append(
            f"retrieval:    passed={retrieval_passed} failed={total - retrieval_passed} total={total} success_rate={retrieval_success_rate:.1%}{retrieval_mrr_str}{retr_pr_str}"
        )
    else:
        header_lines.append(
            f"presentation: passed={passed} failed={total - passed} total={total} success_rate={success_rate:.1%}{mrr_str}{pres_pr_str}"
        )
        header_lines.append(
            f"retrieval:    passed={retrieval_passed} failed={total - retrieval_passed} total={total} success_rate={retrieval_success_rate:.1%}{retrieval_mrr_str}{retr_pr_str}"
        )
    header_lines.append(f"latency: mean={lat_mean:.2f}s min={lat_min:.2f}s max={lat_max:.2f}s")

    groups: dict[str, list[TestResult]] = {}
    for r in results:
        groups.setdefault(r.use_case_id, []).append(r)
    header_lines.append("by_group:")
    for gid, grp in groups.items():
        gtotal = len(grp)
        gpassed = sum(1 for r in grp if r.passed)
        gretr = sum(1 for r in grp if r.retrieval_passed)
        gmrr = [r.retrieval_mrr for r in grp if r.retrieval_mrr is not None]
        gmrr_str = f"  retr_mrr={sum(gmrr)/len(gmrr):.3f}" if gmrr else ""
        if retrieval_only:
            header_lines.append(f"  {gid:<28} retr={gretr}/{gtotal}={gretr/gtotal:.0%}{gmrr_str}")
        else:
            gpres_mrr = [r.mrr for r in grp if r.mrr is not None]
            gpres_mrr_str = f"  pres_mrr={sum(gpres_mrr)/len(gpres_mrr):.3f}" if gpres_mrr else ""
            header_lines.append(f"  {gid:<28} pres={gpassed}/{gtotal}={gpassed/gtotal:.0%}  retr={gretr}/{gtotal}={gretr/gtotal:.0%}{gpres_mrr_str}{gmrr_str}")

    header_lines.append("")
    lines = header_lines

    current_case = None
    for result in results:
        if result.use_case_id != current_case:
            current_case = result.use_case_id
            lines.append(f"## use_case: {current_case}")

        ok = sum(r.passed for r in result.runs)
        retrieval_ok = sum(r.retrieval_passed for r in result.runs)
        mrr_tag = f"  mrr={result.mrr:.4f}" if result.mrr is not None else ""
        retrieval_mrr_tag = f"  mrr={result.retrieval_mrr:.4f}" if result.retrieval_mrr is not None else ""
        pres_pr_tag = (
            f"  precision={result.presentation_precision:.4f}  recall={result.presentation_recall:.4f}"
            if result.presentation_precision is not None else ""
        )
        retr_pr_tag = (
            f"  precision={result.retrieval_precision:.4f}  recall={result.retrieval_recall:.4f}"
            if result.retrieval_precision is not None else ""
        )
        lines.append(f"- test_id: {result.test_id}")
        if not retrieval_only:
            lines.append(f"  presentation: {'PASS' if result.passed else 'FAIL'} ({ok}/{n_runs}) success_rate={result.pass_rate:.1%}{mrr_tag}{pres_pr_tag}")
        lines.append(f"  retrieval:    {'PASS' if result.retrieval_passed else 'FAIL'} ({retrieval_ok}/{n_runs}) success_rate={result.retrieval_pass_rate:.1%}{retrieval_mrr_tag}{retr_pr_tag}")
        lines.append(f"  latency: mean={result.latency_mean_s:.2f}s min={result.latency_min_s:.2f}s max={result.latency_max_s:.2f}s")
        lines.append(f"  input: {result.query}")

        for run in result.runs:
            tag = "PASS" if run.passed else f"FAIL[{','.join(_fmt_failure(f) for f in run.failures)}]"
            retrieval_tag = "PASS" if run.retrieval_passed else f"FAIL[{','.join(_fmt_failure(f) for f in run.retrieval_failures)}]"
            rr_tag = f"  rr={run.reciprocal_rank:.4f}" if run.reciprocal_rank is not None else ""
            retrieval_rr_tag = (
                f"  rr={run.retrieval_reciprocal_rank:.4f}"
                if run.retrieval_reciprocal_rank is not None
                else ""
            )
            if retrieval_only:
                lines.append(f"  [run {run.run_index}] retrieval={retrieval_tag} latency={run.latency_s:.2f}s{retrieval_rr_tag}")
                lines.append(f"    tool_returned_assets: {', '.join(run.tool_returned_assets) or '[none]'}")
            else:
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


def render_json_report(results: list[TestResult], model: str, selected_id: str, n_runs: int, retrieval_only: bool = False, prompt_version: str | None = None, temperature: int = 0) -> str:
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    retrieval_passed = sum(1 for r in results if r.retrieval_passed)
    all_latencies = [r.latency_s for result in results for r in result.runs]
    lat_mean = sum(all_latencies) / len(all_latencies) if all_latencies else 0.0

    def _mean_r(vals: list[float | None]) -> float | None:
        xs = [v for v in vals if v is not None]
        return round(sum(xs) / len(xs), 4) if xs else None

    mrr_values = [r.mrr for r in results if r.mrr is not None]
    mean_mrr = round(sum(mrr_values) / len(mrr_values), 4) if mrr_values else None
    retrieval_mrr_values = [r.retrieval_mrr for r in results if r.retrieval_mrr is not None]
    retrieval_mean_mrr = (
        round(sum(retrieval_mrr_values) / len(retrieval_mrr_values), 4)
        if retrieval_mrr_values
        else None
    )

    try:
        from edc_agent.tools.definitions.search_catalog_tool import TOOL_CONFIG
        tool_config: dict | None = TOOL_CONFIG
    except Exception:
        tool_config = None

    catalog_size: int | None = None
    catalog_fingerprint: str | None = None
    for tr in results:
        for run in tr.runs:
            if run.tool_diagnostics and "catalog_size" in run.tool_diagnostics:
                catalog_size = run.tool_diagnostics["catalog_size"]
                scores = run.tool_diagnostics.get("per_asset_scores", [])
                if scores:
                    sorted_ids = sorted(s["asset_id"] for s in scores)
                    catalog_fingerprint = hashlib.sha256(",".join(sorted_ids).encode()).hexdigest()[:12]
                break
        if catalog_size is not None:
            break

    groups: dict[str, list[TestResult]] = {}
    for r in results:
        groups.setdefault(r.use_case_id, []).append(r)
    by_group = []
    for gid, grp in groups.items():
        gtotal = len(grp)
        gpassed = sum(1 for r in grp if r.passed)
        gretr_passed = sum(1 for r in grp if r.retrieval_passed)
        gpres_mrr_vals = [r.mrr for r in grp if r.mrr is not None]
        gretr_mrr_vals = [r.retrieval_mrr for r in grp if r.retrieval_mrr is not None]
        entry: dict[str, Any] = {
            "use_case_id": gid,
            "total": gtotal,
            "retrieval": {
                "passed": gretr_passed,
                "success_rate": round(gretr_passed / gtotal, 4) if gtotal else 0.0,
                "mrr": round(sum(gretr_mrr_vals) / len(gretr_mrr_vals), 4) if gretr_mrr_vals else None,
                "precision": _mean_r([r.retrieval_precision for r in grp]),
                "recall": _mean_r([r.retrieval_recall for r in grp]),
            },
        }
        if not retrieval_only:
            entry["presentation"] = {
                "passed": gpassed,
                "success_rate": round(gpassed / gtotal, 4) if gtotal else 0.0,
                "mrr": round(sum(gpres_mrr_vals) / len(gpres_mrr_vals), 4) if gpres_mrr_vals else None,
                "precision": _mean_r([r.presentation_precision for r in grp]),
                "recall": _mean_r([r.presentation_recall for r in grp]),
            }
        by_group.append(entry)

    payload = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "git_sha": _get_git_sha(),
        "model": model or "(retrieval-only)",
        "embedding_model": os.getenv("EMBEDDING_MODEL", ""),
        "temperature": temperature,
        "prompt_version": prompt_version or "flat",
        "tool_config": tool_config,
        "catalog_size": catalog_size,
        "catalog_fingerprint": catalog_fingerprint,
        "selection": selected_id,
        "runs_per_test": n_runs,
        "retrieval_only": retrieval_only,
        "summary": {
            **(
                {}
                if retrieval_only
                else {
                    "presentation": {
                        "passed": passed,
                        "failed": total - passed,
                        "total": total,
                        "success_rate": round(passed / total, 4) if total else 0.0,
                        "success_rate_std": _pop_std([r.pass_rate for r in results]),
                        "mrr": mean_mrr,
                        "mrr_std": _pop_std([r.mrr for r in results]),
                        "precision": _mean_r([r.presentation_precision for r in results]),
                        "precision_std": _pop_std([r.presentation_precision for r in results]),
                        "recall": _mean_r([r.presentation_recall for r in results]),
                        "recall_std": _pop_std([r.presentation_recall for r in results]),
                    },
                }
            ),
            "retrieval": {
                "passed": retrieval_passed,
                "failed": total - retrieval_passed,
                "total": total,
                "success_rate": round(retrieval_passed / total, 4) if total else 0.0,
                "success_rate_std": _pop_std([r.retrieval_pass_rate for r in results]),
                "mrr": retrieval_mean_mrr,
                "mrr_std": _pop_std([r.retrieval_mrr for r in results]),
                "precision": _mean_r([r.retrieval_precision for r in results]),
                "precision_std": _pop_std([r.retrieval_precision for r in results]),
                "recall": _mean_r([r.retrieval_recall for r in results]),
                "recall_std": _pop_std([r.retrieval_recall for r in results]),
            },
            "latency_mean_s": round(lat_mean, 3),
            "latency_min_s": round(min(all_latencies), 3) if all_latencies else 0.0,
            "latency_max_s": round(max(all_latencies), 3) if all_latencies else 0.0,
            "by_group": by_group,
        },
        "results": [
            {
                "use_case_id": result.use_case_id,
                "test_id": result.test_id,
                "query": result.query,
                "presentation_passed": result.passed,
                "presentation_pass_rate": result.pass_rate,
                "presentation_mrr": round(result.mrr, 4) if result.mrr is not None else None,
                "presentation_precision": round(result.presentation_precision, 4) if result.presentation_precision is not None else None,
                "presentation_recall": round(result.presentation_recall, 4) if result.presentation_recall is not None else None,
                "retrieval_passed": result.retrieval_passed,
                "retrieval_pass_rate": result.retrieval_pass_rate,
                "retrieval_mrr": round(result.retrieval_mrr, 4) if result.retrieval_mrr is not None else None,
                "retrieval_precision": round(result.retrieval_precision, 4) if result.retrieval_precision is not None else None,
                "retrieval_recall": round(result.retrieval_recall, 4) if result.retrieval_recall is not None else None,
                "latency_mean_s": round(result.latency_mean_s, 3),
                "latency_min_s": round(result.latency_min_s, 3),
                "latency_max_s": round(result.latency_max_s, 3),
                "latency_std_s": round(result.latency_std_s, 3),
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
                        "presentation_precision": round(run.presentation_precision, 4) if run.presentation_precision is not None else None,
                        "presentation_recall": round(run.presentation_recall, 4) if run.presentation_recall is not None else None,
                        "retrieval_passed": run.retrieval_passed,
                        "retrieval_failures": run.retrieval_failures,
                        "retrieval_reciprocal_rank": run.retrieval_reciprocal_rank,
                        "retrieval_precision": round(run.retrieval_precision, 4) if run.retrieval_precision is not None else None,
                        "retrieval_recall": round(run.retrieval_recall, 4) if run.retrieval_recall is not None else None,
                        "latency_s": round(run.latency_s, 3),
                        "phase_latency_s": run.tool_diagnostics.get("phase_latency_s") if run.tool_diagnostics else None,
                        "tool_diagnostics": run.tool_diagnostics,
                        "search_tool_logs": run.search_tool_logs[:_LOG_LINES_LIMIT],
                        "search_tool_logs_truncated": len(run.search_tool_logs) > _LOG_LINES_LIMIT,
                    }
                    for run in result.runs
                ],
            }
            for result in results
        ],
    }
    return json.dumps(payload, ensure_ascii=True, indent=2) + "\n"


def build_output_path(
    results_dir: Path,
    selection: str,
    extension: str,
    model: str = "",
    prompt_version: str | None = None,
    embedding_model: str = "",
) -> Path:
    def _slug(s: str) -> str:
        return re.sub(r"[^a-zA-Z0-9._-]", "-", s).strip("-") if s else ""

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    model_slug = _slug(model) or "retrieval-only"
    pv_slug = f"p{_slug(prompt_version)}" if prompt_version else "pflat"
    emb_slug = f"e{_slug(embedding_model)}" if embedding_model else "enone"
    name = f"{selection}_{model_slug}_{pv_slug}_{emb_slug}_{timestamp}.{extension}"
    return results_dir / name


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run search catalog use case evaluations.")
    parser.add_argument("use_case", nargs="?", default="all", help="Use case id or 'all'.")
    parser.add_argument("--case-file", default=str(DEFAULT_CASE_FILE), help="Path to use case JSON file.")
    parser.add_argument("--output", default=None, help="Optional explicit text output file path.")
    parser.add_argument("--json-output", default=None, help="Optional explicit JSON output file path.")
    parser.add_argument("--results-dir", default=str(DEFAULT_RESULTS_DIR), help="Directory for generated reports.")
    parser.add_argument("--model", default=os.getenv("LLM_MODEL", ""), help="Ollama chat model.")
    parser.add_argument("--temperature", type=int, default=0, help="Model temperature.")
    parser.add_argument("--runs", type=int, default=3, help="Number of runs per test (default: 3).")
    parser.add_argument("--list", action="store_true", help="List available use case ids and exit.")
    parser.add_argument(
        "--retrieval-only",
        action="store_true",
        help="Skip LLM entirely; call search_catalog_tool directly with the raw query.",
    )
    parser.add_argument(
        "--prompt-version",
        default=None,
        help=(
            "Search-catalog prompt version to load from src/edc_agent/prompts/versions/<version>/ "
            "(e.g. 'v3'). When omitted, the flat src/edc_agent/prompts/search_catalog_prompt.py is used."
        ),
    )
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

    retrieval_only: bool = args.retrieval_only

    if not retrieval_only and not args.model:
        print("LLM_MODEL is not configured. Set it in .env or pass --model <name:tag>.")
        return 2

    selected_cases = select_use_cases(use_cases, args.use_case)

    capturing_handler = _CapturingHandler()
    capturing_handler.setLevel(logging.INFO)
    capturing_handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    tool_logger = logging.getLogger(SEARCH_TOOL_LOGGER)
    tool_logger.setLevel(logging.DEBUG)
    tool_logger.addHandler(capturing_handler)

    results: list[TestResult] = []
    if retrieval_only:
        from edc_agent.tools.definitions.search_catalog_tool import SearchCatalogTool
        search_tool = SearchCatalogTool()
        for use_case in selected_cases:
            for test in use_case.get("tests", []):
                results.append(
                    run_test_retrieval_only(search_tool, str(use_case["id"]), test, capturing_handler, args.runs)
                )
    else:
        try:
            manager = build_manager(
                model_name=args.model,
                temperature=args.temperature,
                prompt_version=args.prompt_version,
            )
        except ModuleNotFoundError as exc:
            missing = getattr(exc, "name", "dependency")
            print(
                f"Missing Python dependency: {missing}. "
                "Install project dependencies first with: pip install -e ."
            )
            return 2
        for use_case in selected_cases:
            for test in use_case.get("tests", []):
                results.append(run_test(manager, str(use_case["id"]), test, capturing_handler, args.runs))

    tool_logger.removeHandler(capturing_handler)

    selection = args.use_case or "all"
    prompt_version = None if retrieval_only else args.prompt_version
    text_report = render_text_report(results, args.model, selection, args.runs, retrieval_only=retrieval_only, prompt_version=prompt_version, temperature=args.temperature)
    json_report = render_json_report(results, args.model, selection, args.runs, retrieval_only=retrieval_only, prompt_version=prompt_version, temperature=args.temperature)

    embedding_model = os.getenv("EMBEDDING_MODEL", "")
    text_output = Path(args.output).resolve() if args.output else build_output_path(
        results_dir, selection, "log",
        model=args.model, prompt_version=prompt_version, embedding_model=embedding_model,
    )
    json_output = Path(args.json_output).resolve() if args.json_output else build_output_path(
        results_dir, selection, "json",
        model=args.model, prompt_version=prompt_version, embedding_model=embedding_model,
    )

    text_output.write_text(text_report, encoding="utf-8")
    json_output.write_text(json_report, encoding="utf-8")

    print(text_report, end="")
    print(f"text_report: {text_output}")
    print(f"json_report: {json_output}")

    return 0 if all(r.passed for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
