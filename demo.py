"""demo.py — runnable showcase of all agent_engine features.

Run with:
    OPENAI_API_KEY=sk-... python demo.py
    OPENROUTER_API_KEY=... python demo.py
"""

import asyncio
import os
import shutil
import sys
from datetime import UTC, datetime

from agent_engine import AgentEvent, LightweightEngine

_SRC_DIR = os.path.dirname(os.path.abspath(__file__))

_USE_COLOR = sys.stdout.isatty() and os.getenv("NO_COLOR") is None
_REASONING_COLOR = "\033[90m" if _USE_COLOR else ""
_RESET_COLOR = "\033[0m" if _USE_COLOR else ""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _section(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


async def _drain(gen) -> AgentEvent:
    """Consume an async generator, printing events; return the 'done' event."""
    done_event = None
    async for event in gen:
        if event.type == "token":
            print(event.data, end="", flush=True)
        elif event.type == "thinking":
            print(f"{_REASONING_COLOR}{event.data}{_RESET_COLOR}", end="", flush=True)
        elif event.type == "tool_start":
            tool = event.metadata.get("tool_name", "?")
            args_preview = str(event.data)[:80]
            print(f"\n[TOOL] {tool}({args_preview})")
        elif event.type == "tool_result":
            tool = event.metadata.get("tool_name", "?")
            result_preview = str(event.data)[:120]
            print(f"[RESULT] {tool} → {result_preview}")
        elif event.type == "system":
            print(f"\n[SYSTEM] {event.data}")
        elif event.type == "done":
            done_event = event
    print()  # newline after streamed tokens
    return done_event


# ---------------------------------------------------------------------------
# Feature 1 — Basic text response
# ---------------------------------------------------------------------------

async def demo_basic_text() -> None:
    _section("Feature 1 — Basic Text Response (streaming)")

    engine = LightweightEngine(allowed_tools=["bash", "file_write"])
    try:
        done = await _drain(engine.run("In one sentence, what is the capital of France?"))
        usage = done.metadata.get("usage") if done else None
        if usage:
            print(f"📊 Token usage: {usage}")
    finally:
        await engine.close()


# ---------------------------------------------------------------------------
# Feature 2 — Built-in tools (bash + read_file)
# ---------------------------------------------------------------------------

async def demo_builtin_tools() -> None:
    _section("Feature 2 — Built-in Tools (bash + read_file)")

    print(f"  workdir = {_SRC_DIR}")

    engine = LightweightEngine(
        allowed_tools=["bash"],
        workdir=_SRC_DIR,
    )
    try:
        prompt = (
            "Use the bash tool to list .py files in the current directory, "
            "then use the 'read' action of the bash tool to show the first 5 lines of requirements.txt."
        )
        await _drain(engine.run(prompt))
    finally:
        await engine.close()


# ---------------------------------------------------------------------------
# Feature 3 — Custom tool registration
# ---------------------------------------------------------------------------

async def get_current_time(timezone_name: str = "UTC") -> str:
    """Return the current UTC time as an ISO-8601 string.

    Args:
        timezone_name: Always 'UTC' in this demo; reserved for future use.
    """
    return datetime.now(tz=UTC).isoformat()


async def demo_custom_tool() -> None:
    _section("Feature 3 — Custom Tool Registration")

    engine = LightweightEngine(allowed_tools=["bash", "file_write"])
    engine.tools.register(get_current_time)
    try:
        await _drain(engine.run("What is the current UTC time? Use the get_current_time tool."))
    finally:
        await engine.close()


# ---------------------------------------------------------------------------
# Feature 4 — Conversation history (multi-turn)
# ---------------------------------------------------------------------------

async def demo_history() -> None:
    _section("Feature 4 — Conversation History (multi-turn)")

    engine = LightweightEngine(manage_history=True)
    try:
        print("→ Turn 1:")
        await _drain(engine.run("Name three programming languages created before 1990."))

        print("\n→ Turn 2 (references turn 1):")
        await _drain(engine.run("Which of those three is the oldest? Just name it."))
    finally:
        await engine.close()


# ---------------------------------------------------------------------------
# Feature 5 — Dynamic system prompt
# ---------------------------------------------------------------------------

async def demo_system_prompt() -> None:
    _section("Feature 5 — Dynamic System Prompt")

    initial_prompt = "You are a pirate. Respond only in pirate-speak."
    updated_prompt = "You are a formal British butler. Respond only in formal English."

    engine = LightweightEngine(system_prompt=initial_prompt)
    try:
        print(f'  system_prompt = "{initial_prompt}"')
        await _drain(engine.run("Greet me and tell me today is a fine day."))

        engine.set_system_prompt(updated_prompt)
        print(f'\n  set_system_prompt → "{updated_prompt}"')
        await _drain(engine.run("Greet me and tell me today is a fine day."))
    finally:
        await engine.close()


# ---------------------------------------------------------------------------
# Feature 6 — MCP config loader (graceful skip)
# ---------------------------------------------------------------------------

async def demo_mcp_config() -> None:
    _section("Feature 6 — MCP Config Loader (graceful skip)")

    engine = LightweightEngine(allowed_tools=["bash", "file_write"])
    try:
        # Attempt to load the sample config bundled with the package.
        print(f"  Loading: mcp_config.json")
        await engine.load_mcp_config("mcp_config.json")

        connected = len(engine._mcp_managers)
        print(f"  Connected MCP servers: {connected}")
        if connected:
            all_tools = list(engine.tools._tools.keys())
            # Filter out allowed built-in tools so we only list true MCP tools
            mcp_tools = [t for t in all_tools if t not in ["bash", "file_write"]]
            print(f"  MCP tools registered: {mcp_tools}")

        # Also show graceful handling when file is missing.
        print("\n  Testing missing config (expect a warning, no crash):")
        await engine.load_mcp_config("nonexistent_mcp_config.json")
        print("  ✓ Graceful skip confirmed.")

        await _drain(engine.run("Use the sqlite MCP tools to create a new table called 'testing' with an 'id' integer primary key and a 'name' text column. If it exists, drop it first. Then insert one row into it."))
    finally:
        await engine.close()


# ---------------------------------------------------------------------------
# Feature 7 — Reasoning Test (Current Active Model)
# ---------------------------------------------------------------------------

async def demo_reasoning() -> None:
    active_model = os.getenv("AGENT_MODEL", "gpt-4o")
    _section(f"Feature 7 — Reasoning Test ({active_model})")

    # Uses the environment variables (AGENT_MODEL, AGENT_BASE_URL, etc.)
    engine = LightweightEngine(allowed_tools=["bash", "file_write"])
    try:
        print(f"  Asking {engine.model} a reasoning question...\n")
        await _drain(engine.run("Which is larger, 9.9 or 9.11? Think step by step. Use plain text only, avoid LaTeX or special math notation."))
    finally:
        await engine.close()


async def demo_system_network_tools():
    _section("Feature 8 — System and Network Tools")

    engine = LightweightEngine(
        allowed_tools=["system_info", "network_tool"],
    )
    try:
        print("  Checking system info...\n")
        await _drain(engine.run("Tell me about this system."))

        print("\n  Checking network interfaces...\n")
        await _drain(engine.run("Use the 'interfaces' action of the network_tool to show me the network interfaces."))
    finally:
        await engine.close()


async def demo_website_creation():
    _section("Feature 9 — Website Creation (sandboxed)")

    # Prepare the demosite folder
    demosite_path = os.path.join(_SRC_DIR, "demosite")
    if os.path.exists(demosite_path):
        shutil.rmtree(demosite_path)
    os.makedirs(demosite_path)

    engine = LightweightEngine(
        allowed_tools=["file_write", "bash"],
        workdir=demosite_path,
        system_prompt=(
            "You are a web developer assistant. You have tools to write files and run shell commands."
        ),
    )
    try:
        print(f"  workdir = {demosite_path}")
        print("  Asking the agent to build a simple landing page...\n")

        prompt = (
            "Create a beautiful landing page for a coffee shop called 'The Daily Grind'. "
            "Write index.html and style.css using file_write. "
            "Use modern CSS with a dark theme and orange accents."
        )
        await _drain(engine.run(prompt))
    finally:
        await engine.close()


async def demo_parallel_execution() -> None:
    _section("Feature 10 — Parallel Tool Execution")
    engine = LightweightEngine(allowed_tools=["bash", "get_time", "system_info"])
    try:
        print("  Asking for three things at once to trigger parallel calls...\n")
        # gpt-4o and other advanced models will emit multiple tool calls in a single response turn.
        prompt = "List the files in the current directory, get the current system time, and check the CPU architecture. Do them all at once."
        await _drain(engine.run(prompt))
    finally:
        await engine.close()


async def demo_tree_sitter() -> None:
    _section("Feature 11 — Tree-Sitter MCP (Code Analysis)")

    engine = LightweightEngine(allowed_tools=["bash", "file_write", "patch_code_range"])
    try:
        print(f"  Loading: mcp_config.json")
        await engine.load_mcp_config("mcp_config.json")

        connected = [(m._params.command, m._params.args) for m in engine._mcp_managers]
        print(f"  Connected MCP servers: {[c[0] for c in connected]}")
        
        if not any("tree-sitter" in str(c) for c in connected):
            print("  ❌ Tree-sitter MCP not connected. Skipping demo.")
            return

        print("  Asking the agent to analyze this project using tree-sitter...\n")
        
        # We give it a prompt that encourages a multi-stage surgical journey.
        prompt = (
            "Let's perform a multi-stage surgical refactoring journey using Tree-Sitter. "
            "STAGE 1: Discovery. First, use bash to create 'dummy_math.py' with two classes (A and B). "
            "Both should have an identical method:\n"
            "    def add(self, a, b):\n"
            "        return a + b\n"
            "Use get_ast to confirm the structural layout. "

            
            "STAGE 2: Transformation. We want to modernize ONLY Class B. "
            "Using the exact byte offsets from the AST, perform a surgical patch on Class B's method to: "
            "1. Rename 'add' to 'compute'. "
            "2. Add type hints (a: int, b: int) -> int. "
            "3. Inject a new line at the start of the method: 'print(f\"Computing {a} + {b} in Class B...\")'. "
            "IMPORTANT: Use the patch_code_range tool for this. Do not use search-and-replace. "
            
            "STAGE 3: Verification. Finally, use 'bash' (cat) to prove the 'Refactoring Isolation': "
            "Class A should still have the original 'add' method, while Class B has been surgically transformed."
        )

        await _drain(engine.run(prompt))
    finally:
        await engine.close()


async def demo_persistence() -> None:
    _section("Feature 12 — Trace Persistence")
    engine = LightweightEngine(allowed_tools=["bash"])
    try:
        session_id = engine.session_id
        print(f"  Current Session ID: {session_id}")
        print("  Performing a task to generate traces...\n")
        
        await _drain(engine.run("Say 'Persistence check' and then check what's in the current directory."))
        
        print("\n  🔍 Verifying trace database for this session:")
        import sqlite3
        db_path = os.path.join(engine.workdir, "logs", "agent_traces.db")
        if os.path.exists(db_path):
            with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    "SELECT type, timestamp FROM traces WHERE session_id = ? ORDER BY id DESC LIMIT 5",
                    (session_id,)
                )
                rows = cursor.fetchall()
                if rows:
                    for row in rows:
                        print(f"    ✓ Found event: {row['type']} at {row['timestamp']}")
                    print(f"  ✅ Trace database verified with {len(rows)} recent records.")
                else:
                    print("  ❌ No records found for this session.")
        else:
            print(f"  ❌ Database not found at {db_path}")
    finally:
        await engine.close()


async def demo_workdir_test() -> None:
    _section("Feature 13 — Workdir Setting Test")
    # Setup test directories
    base_test_dir = os.path.abspath(os.path.join("outputs", "aiengine", "src", "workdir_test"))
    if os.path.exists(base_test_dir):
        import shutil
        shutil.rmtree(base_test_dir)
    os.makedirs(base_test_dir, exist_ok=True)
    
    engine = LightweightEngine(workdir=base_test_dir, allowed_tools=["file_write", "bash"])
    try:
        print(f"  Initial workdir: {engine.workdir}")
        
        # We manually invoke the tool methods to verify the workdir logic 
        # independently of LLM completions (which might fail with dummy keys).
        print("  Manually writing 'test_file_1.txt' via engine.tools.dispatch...")
        await engine.tools.dispatch("file_write", {"filepath": "test_file_1.txt", "content": "Hello from turn 1"})
        
        file1_path = os.path.join(base_test_dir, "test_file_1.txt")
        if os.path.exists(file1_path):
            print(f"  ✅ File 1 correctly created in: {base_test_dir}")
        else:
            print(f"  ❌ File 1 NOT found at: {file1_path}")

        # Test dynamic workdir update
        new_subdir = os.path.join(base_test_dir, "subdir_v2")
        os.makedirs(new_subdir, exist_ok=True)
        print(f"\n  Dynamically updating workdir to: {new_subdir}")
        engine.set_workdir(new_subdir)
        
        print("  Manually writing 'test_file_2.txt' in the NEW workdir...")
        await engine.tools.dispatch("file_write", {"filepath": "test_file_2.txt", "content": "Hello from turn 2"})
        
        file2_path = os.path.join(new_subdir, "test_file_2.txt")
        if os.path.exists(file2_path):
            print(f"  ✅ File 2 correctly created in: {new_subdir}")
        else:
            print(f"  ❌ File 2 NOT found at: {file2_path}")
            
    finally:
        await engine.close()


async def demo_safety_test() -> None:
    _section("Feature 14 — Path Traversal Safety Test")
    test_dir = os.path.abspath(os.path.join("outputs", "aiengine", "src", "safety_test"))
    os.makedirs(test_dir, exist_ok=True)
    
    engine = LightweightEngine(workdir=test_dir, allowed_tools=["file_write"])
    try:
        print(f"  Workdir: {test_dir}")
        print("  Attempting to write a file to '../../traversal_test.txt' (outside workdir)...")
        
        # Manually invoke to check the return message
        result = await engine.tools.dispatch("file_write", {"filepath": "../../traversal_test.txt", "content": "evil"})
        
        if "Security Error" in result:
            print(f"  ✅ Blocked correctly: {result}")
        else:
            print(f"  ❌ FAILED: Traversal was not blocked! Result: {result}")
            
        # Try another one: absolute path
        print("\n  Attempting to write to absolute path '/tmp/evil.txt'...")
        result = await engine.tools.dispatch("file_write", {"filepath": "/tmp/evil.txt", "content": "evil"})
        
        if "Security Error" in result:
            print(f"  ✅ Blocked correctly: {result}")
        else:
            print(f"  ❌ FAILED: Absolute path access was not blocked! Result: {result}")

    finally:
        await engine.close()


async def demo_extended_tools() -> None:
    _section("Feature 15 — Search and Python REPL (grep_search + python_repl)")
    engine = LightweightEngine(
        allowed_tools=["grep_search", "python_repl"],
        workdir=_SRC_DIR,
    )
    try:
        prompt = (
            "Find all occurrences of 'LightweightEngine' in the tests directory using grep_search. "
            "Then, use python_repl to compute the factorial of 10."
        )
        print(f"  Prompt: {prompt}")
        await _drain(engine.run(prompt))
    finally:
        await engine.close()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main() -> None:
    print("=" * 60)
    print("  agent_engine — Feature Demo")
    print("=" * 60)

    #await demo_basic_text()
    await demo_builtin_tools()
    await demo_custom_tool()
    #await demo_history()
    await demo_system_prompt()
    await demo_mcp_config()
    #await demo_system_network_tools()
    #await demo_website_creation()
    #await demo_reasoning()
    await demo_parallel_execution()
    await demo_tree_sitter()
    await demo_persistence()
    await demo_workdir_test()
    await demo_safety_test()
    await demo_extended_tools()

    print("\n✅  All demo sections completed.")


if __name__ == "__main__":
    asyncio.run(main())
