import asyncio
import os
import shutil
import sys
from datetime import UTC, datetime

sys.path.insert(0, "/home/tobias/dev/Repo/aiengine/src")
from agent_engine import AgentEvent, LightweightEngine

_SRC_DIR = "/home/tobias/dev/Repo/aiengine/src"
_USE_COLOR = sys.stdout.isatty() and os.getenv("NO_COLOR") is None
_REASONING_COLOR = "\033[90m" if _USE_COLOR else ""
_RESET_COLOR = "\033[0m" if _USE_COLOR else ""

def _section(title: str) -> None:
    print(f"\n{'=' * 80}")
    print(f"  {title}")
    print(f"{'=' * 80}")

async def _drain(gen) -> AgentEvent:
    done_event = None
    async for event in gen:
        if event.type == "token":
            print(event.data, end="", flush=True)
        elif event.type == "thinking":
            print(f"{_REASONING_COLOR}{event.data}{_RESET_COLOR}", end="", flush=True)
        elif event.type == "tool_start":
            tool = event.metadata.get("tool_name", "?")
            args_preview = str(event.data)[:100]
            print(f"\n[TOOL] {tool}({args_preview})")
        elif event.type == "tool_result":
            tool = event.metadata.get("tool_name", "?")
            result_preview = str(event.data)[:150]
            print(f"[RESULT] {tool} → {result_preview}")
        elif event.type == "system":
            print(f"\n[SYSTEM] {event.data}")
        elif event.type == "done":
            done_event = event
    print()
    return done_event

async def run_phase(phase_num: int, phase_name: str, prompt: str) -> dict:
    _section(f"PHASE {phase_num}: {phase_name}")
    engine = LightweightEngine(
        workdir="challenge_workspace",
        allowed_tools=["bash", "patch_code_range", "file_write", "read_file"],
        max_iterations=15,
        extra_completion_kwargs={
            "extra_body": {
                "options": {
                    "num_ctx": 16384
                }
            }
        }
    )
    try:
        await engine.load_mcp_config("mcp_config.json")
        skill_path = os.path.join(_SRC_DIR, ".agent_skills", "ultimate_software_dev.md")
        with open(skill_path, "r", encoding="utf-8") as f:
            skill_content = f.read()
        engine.set_system_prompt(skill_content)
        
        done = await _drain(engine.run(prompt))
        usage = done.metadata.get("session_usage") if done else {}
        return usage
    finally:
        await engine.close()

async def main() -> None:
    _section("Feature 13 Challenge 2 — AST-Driven Precision Creation & Modification")

    workspace_dir = os.path.join(_SRC_DIR, "challenge_workspace")
    if os.path.exists(workspace_dir):
        shutil.rmtree(workspace_dir)
    os.makedirs(workspace_dir)

    # 1. Create project root marker
    with open(os.path.join(workspace_dir, "pyproject.toml"), "w") as f:
        f.write("# marker for tree-sitter mcp project root\n")

    cumulative_usage = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "reasoning_tokens": 0,
    }

    # Phase 1: File Creation
    p1_prompt = (
        "TASK 1: Create a brand new Python file `analytics.py` using the `file_write` tool, containing exactly the following initial class content:\n"
        "```python\n"
        "class MetricsTracker:\n"
        "    def __init__(self, app_id):\n"
        "        self.app_id = app_id\n"
        "        self.events_log = []\n"
        "\n"
        "    def track_event(self, event_name, payload):\n"
        "        self.events_log.append({\"name\": event_name, \"data\": payload})\n"
        "\n"
        "    def count_events(self):\n"
        "        return len(self.events_log)\n"
        "```"
    )
    usage1 = await run_phase(1, "Create Initial analytics.py File", p1_prompt)
    
    # Phase 2: Inject New Method
    p2_prompt = (
        "TASK 2: Surgically inject a new method `get_events_by_type(self, event_type)` into the end of `MetricsTracker` class in `analytics.py`.\n"
        "- Rely on the Ultimate protocol in your system prompt.\n"
        "- Use `patch_code_range` with `start_byte: -1`, `end_byte: -1`, and `override_base_indent: 4` to append it directly to EOF.\n"
        "- The new method must filter event dictionaries in `self.events_log` matching `event_type` and return a list of their data payloads.\n"
        "- Make sure the method is beautifully indented at exactly 4 spaces (standard python class method indentation)."
    )
    usage2 = await run_phase(2, "Inject get_events_by_type Method", p2_prompt)

    # Phase 3: Global Identifier Rename
    p3_prompt = (
        "TASK 3: Perform a global identifier rename from `events_log` to `event_records` in `analytics.py`.\n"
        "- Rely on the Ultimate protocol in your system prompt.\n"
        "- Locate all occurrences of `events_log` using coords.\n"
        "- Patch the occurrences from the bottom of the file up to the top (reverse-order patching) using `patch_code_range` to avoid coordinate shifts.\n"
        "- You must re-query `bash(action=\"coords\")` immediately before applying each patch to ensure 100% precision."
    )
    usage3 = await run_phase(3, "Perform Global Variable Renaming", p3_prompt)

    # Phase 4: Add Type Hints
    p4_prompt = (
        "TASK 4: Add type hints to all methods of `MetricsTracker` class inside `analytics.py`.\n"
        "- Locate each method signature precisely using coords.\n"
        "- Surgically update the method signatures to add appropriate type hints (e.g., `__init__(self, app_id: str)`, `track_event(self, event_name: str, payload: dict)`, `count_events(self) -> int`, `get_events_by_type(self, event_type: str) -> list[dict]`)."
    )
    usage4 = await run_phase(4, "Add Type Hints to All Methods", p4_prompt)

    # Phase 5: AST Syntax Verification
    p5_prompt = (
        "TASK 5: Perform AST Syntax Verification on the finalized `analytics.py`.\n"
        "- Rely on the Ultimate protocol in your system prompt.\n"
        "- Get the AST using `get_ast` and verify that there are no parse errors, invalid syntax, or missing nodes."
    )
    usage5 = await run_phase(5, "Execute AST Syntax Verification", p5_prompt)

    # Aggregate usages
    for u in [usage1, usage2, usage3, usage4, usage5]:
        for k in cumulative_usage:
            cumulative_usage[k] += u.get(k, 0)

    print(f"\n{'=' * 80}")
    print("  🏆 Refactoring Lifecycle Execution Complete!")
    print(f"{'=' * 80}")
    print(f"📊 Cumulative Token Usage across all 5 phases: {cumulative_usage}\n")

if __name__ == "__main__":
    asyncio.run(main())
