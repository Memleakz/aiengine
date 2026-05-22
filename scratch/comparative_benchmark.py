import asyncio
import os
import time
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

def setup_initial_files():
    workspace_dir = os.path.join(_SRC_DIR, "challenge_workspace")
    if os.path.exists(workspace_dir):
        shutil.rmtree(workspace_dir)
    os.makedirs(workspace_dir)
    
    # 1. pyproject.toml
    with open(os.path.join(workspace_dir, "pyproject.toml"), "w") as f:
        f.write("# marker for tree-sitter mcp project root\n")

    # 2. index.html
    with open(os.path.join(workspace_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write("""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Polyglot Challenge</title>
    <style>
        .old-button { padding: 10px 20px; color: #fff; background: #007bff; }
    </style>
</head>
<body>
    <button class="old-button" id="submitBtn">Submit</button>
    <div class="contact-card">
        <h3>Contact Support</h3>
        <p>Email: support@dailygrind.com</p>
    </div>
</body>
</html>
""")

    # 3. app.js
    with open(os.path.join(workspace_dir, "app.js"), "w", encoding="utf-8") as f:
        f.write("""// Polyglot Challenge - JS
let tempCount = 0;

function increment() {
    tempCount += 1;
    console.log("Current count: " + tempCount);
}

function calculatePayout(amount, rate) {
    return amount * rate;
}

increment();
""")

    # 4. server.py
    with open(os.path.join(workspace_dir, "server.py"), "w", encoding="utf-8") as f:
        f.write("""# Polyglot Challenge - Python
class UserManager:
    def __init__(self, auth_key):
        self.auth_key = auth_key

    def fetch_user(self, user_id):
        # Initial basic fetch
        return {"id": user_id, "name": "User_" + str(user_id)}

manager = UserManager("super_secret_auth_key")
print(manager.fetch_user(42))
""")

    # 5. Program.cs
    with open(os.path.join(workspace_dir, "Program.cs"), "w", encoding="utf-8") as f:
        f.write("""// Polyglot Challenge - C#
using System;

public class DiscountCalculator
{
    private string userId;

    public DiscountCalculator(string userId)
    {
        this.userId = userId;
    }

    public double GetDiscount(double amount)
    {
        return amount * 0.05;
    }
}

class Program
{
    static void Main()
    {
        var calculator = new DiscountCalculator("user_123");
        Console.WriteLine(calculator.GetDiscount(150.0));
    }
}
""")

    # 6. payout.php
    with open(os.path.join(workspace_dir, "payout.php"), "w", encoding="utf-8") as f:
        f.write("""<?php
// Polyglot Challenge - PHP
class PayoutCalculator {
    private $baseRate;

    public function __construct($baseRate) {
        $this->baseRate = $baseRate;
    }

    public function getPayment($hours) {
        return $hours * $this->baseRate;
    }
}

$calc = new PayoutCalculator(25.0);
echo $calc->getPayment(40);
""")

    # 7. Tracker.java
    with open(os.path.join(workspace_dir, "Tracker.java"), "w", encoding="utf-8") as f:
        f.write("""// Polyglot Challenge - Java
public class Tracker {
    private String traceId;

    public Tracker(String traceId) {
        this.traceId = traceId;
    }

    public void logEvent(String name) {
        System.out.println("[" + this.traceId + "] Event: " + name);
    }
}
""")

def validate_results(workspace_dir: str) -> dict:
    results = {}
    
    # 1. HTML
    html_path = os.path.join(workspace_dir, "index.html")
    if os.path.exists(html_path):
        with open(html_path, "r") as f:
            code = f.read()
        results["html_rename"] = "old-button" not in code and "btn-primary" in code
        results["html_social"] = "hello@dailygrind.com" in code and "Twitter/X" in code
    else:
        results["html_rename"] = False
        results["html_social"] = False

    # 2. JS
    js_path = os.path.join(workspace_dir, "app.js")
    if os.path.exists(js_path):
        with open(js_path, "r") as f:
            code = f.read()
        results["js_rename"] = "tempCount" not in code and "retryLimit" in code
        results["js_vat"] = "Math.round" in code and "1.1" in code
    else:
        results["js_rename"] = False
        results["js_vat"] = False

    # 3. Python
    py_path = os.path.join(workspace_dir, "server.py")
    if os.path.exists(py_path):
        with open(py_path, "r") as f:
            code = f.read()
        results["py_rename"] = "auth_key" not in code and "api_token" in code
        results["py_except"] = "UserNotFoundError" in code
    else:
        results["py_rename"] = False
        results["py_except"] = False

    # 4. C#
    cs_path = os.path.join(workspace_dir, "Program.cs")
    if os.path.exists(cs_path):
        with open(cs_path, "r") as f:
            code = f.read()
        results["cs_rename"] = "userId" not in code and "memberId" in code
        results["cs_discount"] = "0.15" in code or "15%" in code or "0.85" in code
    else:
        results["cs_rename"] = False
        results["cs_discount"] = False

    # 5. PHP
    php_path = os.path.join(workspace_dir, "payout.php")
    if os.path.exists(php_path):
        with open(php_path, "r") as f:
            code = f.read()
        results["php_rename"] = "baseRate" not in code and "hourlyRate" in code
        results["php_overtime"] = "40" in code and "1.5" in code
    else:
        results["php_rename"] = False
        results["php_overtime"] = False

    # 6. Java
    java_path = os.path.join(workspace_dir, "Tracker.java")
    if os.path.exists(java_path):
        with open(java_path, "r") as f:
            code = f.read()
        results["java_rename"] = "traceId" not in code and "correlationId" in code
        results["java_timestamp"] = "2026-05-19" in code
    else:
        results["java_rename"] = False
        results["java_timestamp"] = False

    return results

async def run_phase_ast(phase_num: int, phase_name: str, prompt: str) -> dict:
    _section(f"AST PIPELINE - PHASE {phase_num}: {phase_name}")
    engine = LightweightEngine(
        workdir="challenge_workspace",
        allowed_tools=["bash", "patch_code_range", "read_file", "get_document_map", "get_entity_coordinates", "get_references", "get_html_attribute_bytes", "verify_ast_integrity", "batch_ast_query"],
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
        skill_path = os.path.join(_SRC_DIR, ".agent_skills", "ultimate_software_dev.md")
        with open(skill_path, "r", encoding="utf-8") as f:
            skill_content = f.read()
        engine.set_system_prompt(skill_content)
        
        done = await _drain(engine.run(prompt))
        usage = done.metadata.get("session_usage") if done else {}
        return usage
    finally:
        await engine.close()

async def run_phase_basic(phase_num: int, phase_name: str, prompt: str) -> dict:
    _section(f"BASIC TOOLING PIPELINE - PHASE {phase_num}: {phase_name}")
    engine = LightweightEngine(
        workdir="challenge_workspace",
        allowed_tools=["bash", "read_file", "file_write", "file_edit", "glob_search", "grep_search"],
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
        plain_prompt = (
            "You are a general-purpose programming assistant with standard shell/file access. Your goal is to modify code files by reading and writing them. "
            "You do not have access to custom AST parsing or Tree-Sitter tools. Solve the refactoring task using standard file editing."
        )
        engine.set_system_prompt(plain_prompt)
        
        done = await _drain(engine.run(prompt))
        usage = done.metadata.get("session_usage") if done else {}
        return usage
    finally:
        await engine.close()

async def main() -> None:
    _section("🚀 ULTIMATE COMPARATIVE BENCHMARK: AST SETUP VS BASIC TOOLING")

    # Define prompts for all 6 languages
    p1_html = (
        "TASK: Surgically refactor `index.html` (HTML).\n"
        "- Sub-task A: Globally change the class name `old-button` to `btn-primary` in both CSS style rules and class attributes.\n"
        "- Sub-task B: Structurally locate the entire `<div class=\"contact-card\">...</div>` block and rewrite it to add a Twitter/X social link: `<a class=\"social-link\" href=\"#x\">Twitter/X</a>`, and change the email support address to `hello@dailygrind.com`."
    )
    p2_js = (
        "TASK: Surgically refactor `app.js` (JavaScript).\n"
        "- Sub-task A: Globally change the identifier `tempCount` to `retryLimit` across all definitions and usage.\n"
        "- Sub-task B: Structurally locate the entire `function calculatePayout(amount, rate)` block and rewrite it to include a 10% VAT tax: return `Math.round(amount * rate * 1.1)`."
    )
    p3_py = (
        "TASK: Surgically refactor `server.py` (Python).\n"
        "- Sub-task A: Globally change the identifier name `auth_key` to `api_token` across all definitions and usage.\n"
        "- Sub-task B: Structurally locate the entire `def fetch_user(self, user_id)` method inside the 'UserManager' class and rewrite it to handle `UserNotFoundError` by catching it and returning a default dictionary: `{'id': user_id, 'name': 'Anonymous', 'role': 'guest'}`."
    )
    p4_cs = (
        "TASK: Surgically refactor `Program.cs` (C#).\n"
        "- Sub-task A: Globally change the identifier `userId` to `memberId` across all definitions and usage.\n"
        "- Sub-task B: Structurally locate the entire `public double GetDiscount(double amount)` method inside the 'DiscountCalculator' class and rewrite it to include a loyalty tier bonus: if amount is greater than 100, apply a 15% discount, otherwise apply a 5% discount."
    )
    p5_php = (
        "TASK: Surgically refactor `payout.php` (PHP).\n"
        "- Sub-task A: Globally change the member variable name `baseRate` to `hourlyRate` (and its reference `$this->baseRate` to `$this->hourlyRate`) across all definitions and usage.\n"
        "- Sub-task B: Structurally locate the entire `public function getPayment($hours)` method inside the 'PayoutCalculator' class and rewrite it to include a overtime bonus: if `$hours > 40`, apply a 1.5x overtime multiplier on hours exceeding 40."
    )
    p6_java = (
        "TASK: Surgically refactor `Tracker.java` (Java).\n"
        "- Sub-task A: Globally change the private field `traceId` to `correlationId` across all definitions and usage.\n"
        "- Sub-task B: Structurally locate the entire `public void logEvent(String name)` method inside the 'Tracker' class and rewrite it to prepend a timestamp prefix in brackets before the ID: `System.out.println(\"[2026-05-19] [\" + this.correlationId + \"] Event: \" + name);`.\n"
        "IMPORTANT: You must write EXACTLY the literal string \"[2026-05-19]\" in your Java code output. Do NOT use \"[Timestamp]\", dynamic dates, or any other placeholders, otherwise the test suite will fail!"
    )

    prompts = [p1_html, p2_js, p3_py, p4_cs]
    names = ["HTML", "JavaScript", "Python", "C#"]

    # ==========================================================================
    # RUN A: AST Pipeline (4 files)
    # ==========================================================================
    _section("🚀 RUNNING AST PIPELINE RUNS...")
    setup_initial_files()
    
    ast_usages = []
    ast_durations = []
    for i, (name, prompt) in enumerate(zip(names, prompts)):
        t0 = time.time()
        usage = await run_phase_ast(i+1, f"Surgically Refactor {name}", prompt)
        duration = time.time() - t0
        ast_usages.append(usage)
        ast_durations.append(duration)

    ast_validation = validate_results(os.path.join(_SRC_DIR, "challenge_workspace"))

    # ==========================================================================
    # RUN B: Basic Tooling Pipeline (4 files)
    # ==========================================================================
    _section("🚀 RUNNING BASIC TOOLING PIPELINE RUNS...")
    setup_initial_files()
    
    basic_usages = []
    basic_durations = []
    for i, (name, prompt) in enumerate(zip(names, prompts)):
        t0 = time.time()
        usage = await run_phase_basic(i+1, f"Surgically Refactor {name}", prompt)
        duration = time.time() - t0
        basic_usages.append(usage)
        basic_durations.append(duration)

    basic_validation = validate_results(os.path.join(_SRC_DIR, "challenge_workspace"))

    # ==========================================================================
    # COMPARATIVE SUMMARY REPORT
    # ==========================================================================
    _section("🏆 ULTIMATE POLYGLOT BENCHMARK SCORECARD")

    ast_totals = {"prompt": 0, "completion": 0, "total": 0, "reasoning": 0}
    basic_totals = {"prompt": 0, "completion": 0, "total": 0, "reasoning": 0}

    for u in ast_usages:
        ast_totals["prompt"] += u.get("prompt_tokens", 0)
        ast_totals["completion"] += u.get("completion_tokens", 0)
        ast_totals["total"] += u.get("total_tokens", 0)
        ast_totals["reasoning"] += u.get("reasoning_tokens", 0)

    for u in basic_usages:
        basic_totals["prompt"] += u.get("prompt_tokens", 0)
        basic_totals["completion"] += u.get("completion_tokens", 0)
        basic_totals["total"] += u.get("total_tokens", 0)
        basic_totals["reasoning"] += u.get("reasoning_tokens", 0)

    ast_total_time = sum(ast_durations)
    basic_total_time = sum(basic_durations)

    print("\n📊 AST PIPELINE TOTALS:")
    print(f"  Prompt Tokens:     {ast_totals['prompt']}")
    print(f"  Completion Tokens: {ast_totals['completion']}")
    print(f"  Total Tokens:      {ast_totals['total']}")
    print(f"  Reasoning Tokens:  {ast_totals['reasoning']}")
    print(f"  Execution Time:    {ast_total_time:.2f} seconds")

    print("\n📊 BASIC TOOLING PIPELINE TOTALS:")
    print(f"  Prompt Tokens:     {basic_totals['prompt']}")
    print(f"  Completion Tokens: {basic_totals['completion']}")
    print(f"  Total Tokens:      {basic_totals['total']}")
    print(f"  Reasoning Tokens:  {basic_totals['reasoning']}")
    print(f"  Execution Time:    {basic_total_time:.2f} seconds")

    # Calculate success rates
    ast_success_count = sum(1 for v in ast_validation.values() if v)
    basic_success_count = sum(1 for v in basic_validation.values() if v)

    print(f"\n⭐ Success Score Card:")
    print(f"  AST Pipeline:      {ast_success_count}/12 sub-tasks successfully passed!")
    for k, v in ast_validation.items():
        print(f"    - {k}: {'PASSED' if v else 'FAILED'}")
    print(f"  Basic Tooling:     {basic_success_count}/12 sub-tasks successfully passed!")
    for k, v in basic_validation.items():
        print(f"    - {k}: {'PASSED' if v else 'FAILED'}")

if __name__ == "__main__":
    asyncio.run(main())
