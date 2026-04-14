#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
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
except ModuleNotFoundError:  # optional dependency
    def load_dotenv(*args, **kwargs):
        return False

ASSET_PATTERN = re.compile(r"\btb-[a-z]+-\d+\b", re.IGNORECASE)
DEFAULT_CASE_FILE = Path(__file__).with_name("use_cases.json")
DEFAULT_RESULTS_DIR = Path(__file__).with_name("results")


@dataclass
class TestResult:
    use_case_id: str
    test_id: str
    query: str
    greeting: str
    response: str
    found_assets: list[str]
    passed: bool
    failures: list[str]


def load_env_file(env_path: Path, override: bool = False) -> None:
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

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
        if asset_id in seen:
            continue
        seen.add(asset_id)
        ordered.append(asset_id)
    return ordered


def evaluate_expectations(test: dict[str, Any], found_assets: list[str]) -> tuple[bool, list[str]]:
    failures: list[str] = []
    found_set = set(found_assets)
    expected_present = [str(asset_id).lower() for asset_id in test.get("expected_present", [])]
    expected_absent = [str(asset_id).lower() for asset_id in test.get("expected_absent", [])]
    allow_additional_assets = bool(test.get("allow_additional_assets", False))

    expected_count = test.get("expected_count")
    if expected_count is not None and len(found_assets) != int(expected_count):
        failures.append(
            f"expected_count={expected_count}, found_count={len(found_assets)}"
        )

    for asset_id in expected_present:
        if asset_id not in found_set:
            failures.append(f"missing_expected_asset={asset_id}")

    for asset_id in expected_absent:
        if asset_id in found_set:
            failures.append(f"unexpected_asset={asset_id}")

    # Strict mode by default: if expectations are provided, do not allow assets
    # outside the explicit expected_present list unless explicitly enabled.
    if not allow_additional_assets and (expected_present or expected_absent):
        expected_present_set = set(expected_present)
        extras = [asset_id for asset_id in found_assets if asset_id not in expected_present_set]
        for asset_id in extras:
            failures.append(f"unexpected_extra_asset={asset_id}")

    return (len(failures) == 0), failures


def run_test(manager, use_case_id: str, test: dict[str, Any]) -> TestResult:
    manager.reset_history()
    greeting, _ = manager.start_conversation()
    process_result = manager.process(str(test["query"]))
    if isinstance(process_result, tuple):
        if len(process_result) >= 1:
            response = str(process_result[0])
        else:
            response = ""
    else:
        response = str(process_result)
    found_assets = extract_asset_ids(response)
    passed, failures = evaluate_expectations(test, found_assets)
    return TestResult(
        use_case_id=use_case_id,
        test_id=str(test["id"]),
        query=str(test["query"]),
        greeting=greeting,
        response=response,
        found_assets=found_assets,
        passed=passed,
        failures=failures,
    )


def render_text_report(results: list[TestResult], model: str, selected_id: str) -> str:
    now = datetime.now().isoformat(timespec="seconds")
    total = len(results)
    passed = sum(1 for item in results if item.passed)
    failed = total - passed

    lines = [
        f"timestamp: {now}",
        f"model: {model}",
        f"selection: {selected_id}",
        f"summary: passed={passed} failed={failed} total={total}",
        "",
    ]

    current_case = None
    for result in results:
        if result.use_case_id != current_case:
            current_case = result.use_case_id
            lines.append(f"## use_case: {current_case}")
        lines.extend(
            [
                f"- test_id: {result.test_id}",
                f"  status: {'PASS' if result.passed else 'FAIL'}",
                f"  input: {result.query}",
                f"  greeting: {result.greeting}",
                f"  output: {result.response}",
                f"  parsed_asset_ids: {', '.join(result.found_assets) if result.found_assets else '[none]'}",
                f"  checks: {', '.join(result.failures) if result.failures else 'ok'}",
                "",
            ]
        )

    return "\n".join(lines).rstrip() + "\n"


def render_json_report(results: list[TestResult], model: str, selected_id: str) -> str:
    payload = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "model": model,
        "selection": selected_id,
        "summary": {
            "passed": sum(1 for item in results if item.passed),
            "failed": sum(1 for item in results if not item.passed),
            "total": len(results),
        },
        "results": [
            {
                "use_case_id": item.use_case_id,
                "test_id": item.test_id,
                "query": item.query,
                "greeting": item.greeting,
                "response": item.response,
                "found_assets": item.found_assets,
                "passed": item.passed,
                "failures": item.failures,
            }
            for item in results
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

    results: list[TestResult] = []
    for use_case in selected_cases:
        for test in use_case.get("tests", []):
            results.append(run_test(manager, str(use_case["id"]), test))

    selection = args.use_case or "all"
    text_report = render_text_report(results, args.model, selection)
    json_report = render_json_report(results, args.model, selection)

    text_output = Path(args.output).resolve() if args.output else build_output_path(results_dir, selection, "log")
    json_output = Path(args.json_output).resolve() if args.json_output else build_output_path(results_dir, selection, "json")

    text_output.write_text(text_report, encoding="utf-8")
    json_output.write_text(json_report, encoding="utf-8")

    print(text_report, end="")
    print(f"text_report: {text_output}")
    print(f"json_report: {json_output}")

    return 0 if all(item.passed for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
