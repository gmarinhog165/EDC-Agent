import json
from pathlib import Path
import sys

from dotenv import load_dotenv

SRC_ROOT = Path(__file__).resolve().parents[2]
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(dotenv_path=PROJECT_ROOT / ".env")

from edc_agent.tools import list_langchain_tools


def main() -> None:
    if len(sys.argv) < 3:
        print('Usage: python src/edc_agent/tools/sandbox.py <tool_name> \'{"arg":"value"}\'')
        sys.exit(1)

    tool_name = sys.argv[1]
    raw_args = sys.argv[2]

    try:
        tool_args = json.loads(raw_args)
    except json.JSONDecodeError as exc:
        print(f"Invalid JSON args: {exc}")
        sys.exit(1)

    if not isinstance(tool_args, dict):
        print("Tool args must be a JSON object.")
        sys.exit(1)

    tools = {tool.name: tool for tool in list_langchain_tools()}
    tool = tools.get(tool_name)
    if tool is None:
        available = ", ".join(sorted(tools))
        print(f"Unknown tool '{tool_name}'. Available: {available}")
        sys.exit(1)

    try:
        result = tool.invoke(tool_args)
    except Exception as exc:  # pragma: no cover
        print(f"Tool '{tool_name}' failed: {exc}")
        sys.exit(1)

    print(result)


if __name__ == "__main__":
    main()
