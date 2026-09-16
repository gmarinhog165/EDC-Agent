#!/usr/bin/env python3
"""Fetching Agent testbed.

Evaluates the LLM layer of the fetch-data agent on two dimensions, with the EDC
tool fully mocked (no real connector / S3 needed). Cases are organized into
groups of 3 (mirroring the search_catalog testbed); each group declares the
family that drives its evaluation:

  family=extraction   — given a natural-language request, does the agent extract
                        the right asset_id tokens and pass them in a single
                        batched call, without normalizing/correcting them?
  family=faithfulness — given a scripted tool result, does the agent relay it
                        back correctly (per-asset status, ids, contract/transfer
                        ids, error explanations, summary) without hallucinating?

Metrics are aggregated per-group, per-family, and overall.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import unicodedata
from dataclasses import dataclass
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

from pydantic import BaseModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.tools import BaseTool

DEFAULT_CASE_FILE = Path(__file__).with_name("fetch_cases.json")
DEFAULT_RESULTS_DIR = Path(__file__).with_name("results")
FAMILIES = ("extraction", "faithfulness")

# Shared state the mock tool reads/writes (BaseTool is a pydantic model, so we
# keep mutable per-run state outside the instance).
_MOCK_STATE: dict[str, Any] = {"scripted_output": None, "calls": []}


def _build_mock_tool() -> BaseTool:
    from edc_agent.tools.definitions.fetch_item_data_tool import FetchItemDataArgs

    class MockFetchItemDataTool(BaseTool):
        name: str = "fetch_item_data"
        description: str = (
            "Fetch data for one or more asset IDs. Each ID is processed independently "
            "(best-effort): individual failures are reported per-asset and do not stop "
            "the others. Returns {results: [...per-asset...], summary: {...}}."
        )
        args_schema: type[BaseModel] = FetchItemDataArgs

        def _run(self, item_ids: list[str]) -> dict[str, Any]:
            _MOCK_STATE["calls"].append(list(item_ids))
            scripted = _MOCK_STATE["scripted_output"]
            if scripted is not None:
                return scripted
            # Extraction cases have no script: return trivial success so the
            # agent can finish its turn. The result content is not evaluated.
            results = [
                {"status": "success", "item_id": i, "contract_id": f"ctr-{i}",
                 "transfer_id": f"trf-{i}", "message": "ok"}
                for i in item_ids
            ]
            return {"results": results,
                    "summary": {"total": len(results), "succeeded": len(results), "failed": 0}}

    return MockFetchItemDataTool()


def build_agent(model_name: str, temperature: int, prompt_version: str | None, mock_tool: BaseTool):
    from edc_agent.agents.agent import Agent
    from edc_agent.clients.ollama_client import OllamaClient
    from edc_agent.prompts.prompt_registry import get_prompt

    llm_client = OllamaClient(model_name=model_name, temperature=temperature)
    return Agent(
        name="fetch-data",
        llm_client=llm_client,
        system_prompt=get_prompt(agent_name="fetch-data", _model_name=model_name, version=prompt_version),
        tools=[mock_tool],
    )


# ---------------------------------------------------------------------------
# text matching helpers
# ---------------------------------------------------------------------------

def _norm(text: str) -> str:
    """Lowercase + strip accents, for accent-insensitive substring matching."""
    nfkd = unicodedata.normalize("NFKD", text or "")
    no_accents = "".join(c for c in nfkd if not unicodedata.combining(c))
    return no_accents.lower()


def _contains(haystack_norm: str, needle: str) -> bool:
    return _norm(needle) in haystack_norm


# ---------------------------------------------------------------------------
# extraction (dimension 1)
# ---------------------------------------------------------------------------

@dataclass
class ExtractionRun:
    run_index: int
    response: str
    captured_calls: list
    captured_ids: list
    call_count: int
    exact_match: bool
    call_count_ok: bool
    precision: float | None
    recall: float | None
    passed: bool
    failures: list
    latency_s: float


def _ids_from_messages(execution_messages: list) -> list:
    """Pull item_ids out of every fetch_item_data tool call the LLM emitted."""
    calls: list = []
    for msg in execution_messages:
        if isinstance(msg, AIMessage):
            for tc in (msg.tool_calls or []):
                if tc.get("name") == "fetch_item_data":
                    ids = tc.get("args", {}).get("item_ids", []) or []
                    calls.append([str(i).strip() for i in ids if str(i).strip()])
    return calls


def eval_extraction(test: dict, response: str, calls: list, latency_s: float, run_index: int) -> ExtractionRun:
    # case_sensitive cases assert the agent did NOT normalize letter case
    # (e.g. user wrote "TB-SOLAR-1"); otherwise we compare case-insensitively.
    case_sensitive = bool(test.get("case_sensitive", False))
    fold = (lambda s: s) if case_sensitive else (lambda s: s.lower())
    expected = [fold(str(i).strip()) for i in test.get("expected_item_ids", [])]
    expected_calls = int(test.get("expected_call_count", 1))

    flat = [fold(i) for call in calls for i in call]
    seen: set = set()
    captured: list = []
    for i in flat:
        if i not in seen:
            seen.add(i)
            captured.append(i)

    failures: list = []
    call_count_ok = len(calls) == expected_calls
    if not call_count_ok:
        failures.append(f"call_count expected={expected_calls} got={len(calls)}")

    exact_match = sorted(captured) == sorted(expected)
    if not exact_match:
        missing = [i for i in expected if i not in captured]
        extra = [i for i in captured if i not in expected]
        if missing:
            failures.append("missing=" + ",".join(missing))
        if extra:
            failures.append("unexpected=" + ",".join(extra))

    if expected:
        tp = sum(1 for i in captured if i in set(expected))
        precision = tp / len(captured) if captured else 0.0
        recall = tp / len(expected)
    else:
        precision = recall = None

    passed = exact_match and call_count_ok
    return ExtractionRun(
        run_index=run_index, response=response, captured_calls=calls,
        captured_ids=captured, call_count=len(calls), exact_match=exact_match,
        call_count_ok=call_count_ok, precision=precision, recall=recall,
        passed=passed, failures=failures, latency_s=latency_s,
    )


# ---------------------------------------------------------------------------
# faithfulness (dimension 2)
# ---------------------------------------------------------------------------

@dataclass
class FaithfulnessRun:
    run_index: int
    response: str
    passed: bool
    failures: list
    latency_s: float


def eval_faithfulness(test: dict, response: str, latency_s: float, run_index: int) -> FaithfulnessRun:
    a = test.get("assertions", {})
    h = _norm(response)
    failures: list = []

    for asset_id in a.get("must_mention_ids", []):
        if not _contains(h, asset_id):
            failures.append(f"missing_id={asset_id}")
    for needle in a.get("must_contain", []):
        if not _contains(h, needle):
            failures.append(f"missing={needle!r}")
    for group in a.get("must_contain_any", []):
        if not any(_contains(h, opt) for opt in group):
            failures.append("missing_any=" + "|".join(group))
    for needle in a.get("must_not_contain", []):
        if _contains(h, needle):
            failures.append(f"forbidden={needle!r}")

    return FaithfulnessRun(
        run_index=run_index, response=response,
        passed=not failures, failures=failures, latency_s=latency_s,
    )


# ---------------------------------------------------------------------------
# run orchestration
# ---------------------------------------------------------------------------

@dataclass
class CaseResult:
    group_id: str
    family: str
    case_id: str
    query: str
    runs: list
    pass_rate: float
    passed: bool
    latency_mean_s: float


def _build_history(test: dict) -> list[BaseMessage]:
    """Turn an optional `chat_history` field into prior conversation turns.

    Used for anaphoric cases ("transfere o primeiro que mencionaste") where the
    asset ids live in a previous agent turn rather than the current query.
    """
    history: list[BaseMessage] = []
    for turn in test.get("chat_history", []):
        role = str(turn.get("role", "")).lower()
        content = str(turn.get("content", ""))
        if role in ("ai", "assistant"):
            history.append(AIMessage(content=content))
        else:
            history.append(HumanMessage(content=content))
    return history


def run_case(agent, group_id: str, family: str, test: dict, n_runs: int) -> CaseResult:
    runs: list = []
    history = _build_history(test)
    for i in range(n_runs):
        _MOCK_STATE["calls"] = []
        _MOCK_STATE["scripted_output"] = test.get("tool_output") if family == "faithfulness" else None
        t0 = time.perf_counter()
        response, _is_done, exec_msgs = agent.generate_response(str(test["query"]), list(history))
        latency_s = time.perf_counter() - t0

        if family == "extraction":
            calls = _ids_from_messages(exec_msgs) or _MOCK_STATE["calls"]
            runs.append(eval_extraction(test, response, calls, latency_s, i))
        else:
            runs.append(eval_faithfulness(test, response, latency_s, i))

    pass_rate = sum(1 for r in runs if r.passed) / n_runs
    lat_mean = sum(r.latency_s for r in runs) / n_runs
    return CaseResult(
        group_id=group_id, family=family, case_id=str(test["id"]),
        query=str(test["query"]), runs=runs, pass_rate=pass_rate,
        passed=pass_rate == 1.0, latency_mean_s=lat_mean,
    )


def _mean_or_none(vals: list) -> float | None:
    xs = [v for v in vals if v is not None]
    return sum(xs) / len(xs) if xs else None


def _get_git_sha() -> str:
    import subprocess
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], stderr=subprocess.DEVNULL, cwd=str(ROOT), text=True
        ).strip()
    except Exception:
        return "unknown"


# ---------------------------------------------------------------------------
# aggregation
# ---------------------------------------------------------------------------

def _family_metrics(cases: list[CaseResult], family: str) -> dict:
    fam = [c for c in cases if c.family == family]
    total = len(fam)
    passed = sum(1 for c in fam if c.passed)
    all_runs = [run for c in fam for run in c.runs]
    lat = [run.latency_s for run in all_runs]
    out: dict[str, Any] = {
        "total": total,
        "passed": passed,
        "success_rate": round(passed / total, 4) if total else 0.0,
        "run_success_rate": round(sum(1 for run in all_runs if run.passed) / len(all_runs), 4) if all_runs else 0.0,
        "latency_mean_s": round(sum(lat) / len(lat), 3) if lat else 0.0,
    }
    if family == "extraction":
        out["id_precision"] = round(_mean_or_none([run.precision for run in all_runs]) or 0.0, 4)
        out["id_recall"] = round(_mean_or_none([run.recall for run in all_runs]) or 0.0, 4)
        ccok = [run.call_count_ok for run in all_runs]
        out["single_call_rate"] = round(sum(ccok) / len(ccok), 4) if ccok else 0.0
    return out


def _group_metrics(cases: list[CaseResult], group_id: str, family: str) -> dict:
    grp = [c for c in cases if c.group_id == group_id]
    total = len(grp)
    passed = sum(1 for c in grp if c.passed)
    all_runs = [run for c in grp for run in c.runs]
    out: dict[str, Any] = {
        "group_id": group_id,
        "family": family,
        "total": total,
        "passed": passed,
        "success_rate": round(passed / total, 4) if total else 0.0,
        "run_success_rate": round(sum(1 for run in all_runs if run.passed) / len(all_runs), 4) if all_runs else 0.0,
    }
    if family == "extraction":
        out["id_precision"] = round(_mean_or_none([run.precision for run in all_runs]) or 0.0, 4)
        out["id_recall"] = round(_mean_or_none([run.recall for run in all_runs]) or 0.0, 4)
        ccok = [run.call_count_ok for run in all_runs]
        out["single_call_rate"] = round(sum(ccok) / len(ccok), 4) if ccok else 0.0
    return out


# ---------------------------------------------------------------------------
# reporting
# ---------------------------------------------------------------------------

def render_text_report(cases: list[CaseResult], group_order: list, model: str, n_runs: int,
                       prompt_version: str | None, temperature: int) -> str:
    lines: list[str] = []
    lines.append(f"timestamp: {datetime.now().isoformat(timespec='seconds')}")
    lines.append(f"git_sha: {_get_git_sha()}")
    lines.append(f"model: {model}")
    lines.append(f"temperature: {temperature}")
    lines.append(f"prompt_version: {prompt_version or 'flat'}")
    lines.append(f"runs_per_test: {n_runs}")

    present_families = [f for f in FAMILIES if any(c.family == f for c in cases)]
    for family in present_families:
        m = _family_metrics(cases, family)
        extra = ""
        if family == "extraction":
            extra = (f"  id_precision={m['id_precision']:.3f}  id_recall={m['id_recall']:.3f}"
                     f"  single_call_rate={m['single_call_rate']:.1%}")
        lines.append(
            f"{family}: passed={m['passed']}/{m['total']} success_rate={m['success_rate']:.1%}"
            f"  run_success_rate={m['run_success_rate']:.1%}  latency_mean={m['latency_mean_s']:.2f}s{extra}"
        )

    lines.append("by_group:")
    for group_id, family in group_order:
        m = _group_metrics(cases, group_id, family)
        extra = ""
        if family == "extraction":
            extra = f"  id_p={m['id_precision']:.2f}  id_r={m['id_recall']:.2f}  single_call={m['single_call_rate']:.0%}"
        lines.append(
            f"  {group_id:<26} [{family[:4]}] {m['passed']}/{m['total']}={m['success_rate']:.0%}"
            f"  run={m['run_success_rate']:.0%}{extra}"
        )

    lines.append("")
    current_group = None
    for c in cases:
        if c.group_id != current_group:
            current_group = c.group_id
            lines.append(f"## group: {c.group_id} [{c.family}]")
        ok = sum(1 for run in c.runs if run.passed)
        lines.append(f"- {c.case_id}: {'PASS' if c.passed else 'FAIL'} ({ok}/{n_runs}) latency_mean={c.latency_mean_s:.2f}s")
        lines.append(f"  input: {c.query}")
        for run in c.runs:
            tag = "PASS" if run.passed else f"FAIL[{'; '.join(run.failures)}]"
            if c.family == "extraction":
                lines.append(f"  [run {run.run_index}] {tag}  calls={run.captured_calls}  latency={run.latency_s:.2f}s")
            else:
                lines.append(f"  [run {run.run_index}] {tag}  latency={run.latency_s:.2f}s")
                lines.append(f"    response: {run.response}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_json_report(cases: list[CaseResult], group_order: list, model: str, n_runs: int,
                       prompt_version: str | None, temperature: int) -> str:
    def serialize_run(family: str, run: Any) -> dict:
        if family == "extraction":
            return {
                "run_index": run.run_index, "passed": run.passed, "failures": run.failures,
                "captured_calls": run.captured_calls, "captured_ids": run.captured_ids,
                "call_count": run.call_count, "exact_match": run.exact_match,
                "call_count_ok": run.call_count_ok, "precision": run.precision, "recall": run.recall,
                "latency_s": round(run.latency_s, 3), "response": run.response,
            }
        return {
            "run_index": run.run_index, "passed": run.passed, "failures": run.failures,
            "latency_s": round(run.latency_s, 3), "response": run.response,
        }

    summary: dict[str, Any] = {}
    for family in FAMILIES:
        if any(c.family == family for c in cases):
            summary[family] = _family_metrics(cases, family)
    summary["by_group"] = [_group_metrics(cases, gid, fam) for gid, fam in group_order]

    payload = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "git_sha": _get_git_sha(),
        "model": model,
        "temperature": temperature,
        "prompt_version": prompt_version or "flat",
        "runs_per_test": n_runs,
        "summary": summary,
        "results": [
            {
                "group_id": c.group_id, "family": c.family, "case_id": c.case_id, "query": c.query,
                "passed": c.passed, "pass_rate": c.pass_rate, "latency_mean_s": round(c.latency_mean_s, 3),
                "runs": [serialize_run(c.family, run) for run in c.runs],
            }
            for c in cases
        ],
    }
    return json.dumps(payload, ensure_ascii=True, indent=2) + "\n"


def _slug(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]", "-", s).strip("-") if s else ""


def build_output_path(results_dir: Path, sel: str, ext: str, model: str, prompt_version: str | None) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    pv = f"p{_slug(prompt_version)}" if prompt_version else "pflat"
    return results_dir / f"fetch_{_slug(sel)}_{_slug(model) or 'nomodel'}_{pv}_{timestamp}.{ext}"


def load_env_file(env_path: Path, override: bool = False) -> None:
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        if override or key not in os.environ:
            os.environ[key] = value


def select_groups(groups: list, selection: str) -> list:
    if not selection or selection == "all":
        return groups
    if selection in FAMILIES:
        return [g for g in groups if g.get("family") == selection]
    chosen = [g for g in groups if g.get("id") == selection]
    if not chosen:
        ids = ", ".join(g.get("id", "?") for g in groups)
        raise ValueError(f"Unknown selection '{selection}'. Use 'all', a family ({'/'.join(FAMILIES)}), or a group id: {ids}")
    return chosen


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run Fetching Agent grouped testbed (extraction + faithfulness).")
    p.add_argument("selection", nargs="?", default="all",
                   help="'all', a family (extraction/faithfulness), or a group id.")
    p.add_argument("--case-file", default=str(DEFAULT_CASE_FILE))
    p.add_argument("--results-dir", default=str(DEFAULT_RESULTS_DIR))
    p.add_argument("--model", default=os.getenv("LLM_MODEL", ""), help="Ollama chat model.")
    p.add_argument("--temperature", type=int, default=0)
    p.add_argument("--runs", type=int, default=3, help="Runs per test (default: 3).")
    p.add_argument("--prompt-version", default=None,
                   help="Load fetch_data_prompt.py from versions/<version>/ (e.g. 'v5').")
    p.add_argument("--list", action="store_true", help="List groups and case ids, then exit.")
    return p.parse_args()


def main() -> int:
    load_dotenv()
    load_env_file(ROOT / ".env")
    args = parse_args()

    payload = json.loads(Path(args.case_file).resolve().read_text(encoding="utf-8"))
    groups = payload.get("groups", [])
    if not groups:
        print(f"No groups found in {args.case_file}.")
        return 2

    if args.list:
        for g in groups:
            print(f"{g['id']} [{g.get('family')}] — {g.get('focus', '')}")
            for t in g.get("tests", []):
                print(f"    {t['id']}")
        return 0

    if not args.model:
        print("LLM_MODEL is not configured. Set it in .env or pass --model <name:tag>.")
        return 2

    selected = select_groups(groups, args.selection)
    results_dir = Path(args.results_dir).resolve()
    results_dir.mkdir(parents=True, exist_ok=True)

    mock_tool = _build_mock_tool()
    try:
        agent = build_agent(args.model, args.temperature, args.prompt_version, mock_tool)
    except ModuleNotFoundError as exc:
        print(f"Missing dependency: {getattr(exc, 'name', exc)}. Run: pip install -e .")
        return 2

    cases: list[CaseResult] = []
    group_order: list = []
    for g in selected:
        family = g.get("family")
        group_order.append((g["id"], family))
        for t in g.get("tests", []):
            cases.append(run_case(agent, g["id"], family, t, args.runs))

    text_report = render_text_report(cases, group_order, args.model, args.runs, args.prompt_version, args.temperature)
    json_report = render_json_report(cases, group_order, args.model, args.runs, args.prompt_version, args.temperature)

    text_out = build_output_path(results_dir, args.selection, "log", args.model, args.prompt_version)
    json_out = build_output_path(results_dir, args.selection, "json", args.model, args.prompt_version)
    text_out.write_text(text_report, encoding="utf-8")
    json_out.write_text(json_report, encoding="utf-8")

    print(text_report, end="")
    print(f"text_report: {text_out}")
    print(f"json_report: {json_out}")
    return 0 if all(c.passed for c in cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())
