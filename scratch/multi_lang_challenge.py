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
        allowed_tools=["bash", "patch_code_range", "read_file"],
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
    _section("Feature 13 Challenge — Polyglot AST Precision Refactoring (HTML, JS, Python, C#, PHP, Java)")

    workspace_dir = os.path.join(_SRC_DIR, "challenge_workspace")
    if os.path.exists(workspace_dir):
        shutil.rmtree(workspace_dir)
    os.makedirs(workspace_dir)

    # 1. Create a project root marker
    with open(os.path.join(workspace_dir, "pyproject.toml"), "w") as f:
        f.write("# marker for tree-sitter mcp project root\n")

    # 2. Write HTML source
    index_html = """<!DOCTYPE html>
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
"""
    with open(os.path.join(workspace_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(index_html)

    # 3. Write JavaScript source
    app_js = """// Polyglot Challenge - JS
let tempCount = 0;

function increment() {
    tempCount += 1;
    console.log("Current count: " + tempCount);
}

function calculatePayout(amount, rate) {
    return amount * rate;
}

increment();
"""
    with open(os.path.join(workspace_dir, "app.js"), "w", encoding="utf-8") as f:
        f.write(app_js)

    # 4. Write Python source
    server_py = """# Polyglot Challenge - Python
class UserManager:
    def __init__(self, auth_key):
        self.auth_key = auth_key

    def fetch_user(self, user_id):
        # Initial basic fetch
        return {"id": user_id, "name": "User_" + str(user_id)}

manager = UserManager("super_secret_auth_key")
print(manager.fetch_user(42))
"""
    with open(os.path.join(workspace_dir, "server.py"), "w", encoding="utf-8") as f:
        f.write(server_py)

    # 5. Write C# source
    program_cs = """// Polyglot Challenge - C#
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
"""
    with open(os.path.join(workspace_dir, "Program.cs"), "w", encoding="utf-8") as f:
        f.write(program_cs)

    # 6. Write PHP source
    payout_php = """<?php
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
"""
    with open(os.path.join(workspace_dir, "payout.php"), "w", encoding="utf-8") as f:
        f.write(payout_php)

    # 7. Write Java source
    tracker_java = """// Polyglot Challenge - Java
public class Tracker {
    private String traceId;

    public Tracker(String traceId) {
        this.traceId = traceId;
    }

    public void logEvent(String name) {
        System.out.println("[" + this.traceId + "] Event: " + name);
    }
}
"""
    with open(os.path.join(workspace_dir, "Tracker.java"), "w", encoding="utf-8") as f:
        f.write(tracker_java)

    cumulative_usage = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "reasoning_tokens": 0,
    }

    # Phase 1: HTML Refactoring
    p1_prompt = (
        "TASK: Surgically refactor `index.html` (HTML).\n"
        "- Rely on the Ultimate protocol in your system prompt.\n"
        "- Sub-task A: Globally change the class name `old-button` to `btn-primary` in both CSS style rules and class attributes (Reverse-Order Patching with JIT coords).\n"
        "- Sub-task B: Structurally locate the entire `<div class=\"contact-card\">...</div>` block and rewrite it using coords/patching to add a Twitter/X social link: `<a class=\"social-link\" href=\"#x\">Twitter/X</a>`, and change the email support address to `hello@dailygrind.com`."
    )
    usage1 = await run_phase(1, "Surgically Refactor index.html (HTML)", p1_prompt)

    # Phase 2: JavaScript Refactoring
    p2_prompt = (
        "TASK: Surgically refactor `app.js` (JavaScript).\n"
        "- Rely on the Ultimate protocol in your system prompt.\n"
        "- Sub-task A: Globally change the identifier `tempCount` to `retryLimit` across all definitions and usage (Reverse-Order Patching with JIT coords).\n"
        "- Sub-task B: Structurally locate the entire `function calculatePayout(amount, rate)` block and rewrite it to include a 10% VAT tax: return `Math.round(amount * rate * 1.1)`."
    )
    usage2 = await run_phase(2, "Surgically Refactor app.js (JS)", p2_prompt)

    # Phase 3: Python Refactoring
    p3_prompt = (
        "TASK: Surgically refactor `server.py` (Python).\n"
        "- Rely on the Ultimate protocol in your system prompt.\n"
        "- Sub-task A: Globally change the identifier name `auth_key` to `api_token` across all definitions and usage (Reverse-Order Patching with JIT coords).\n"
        "- Sub-task B: Structurally locate the entire `def fetch_user(self, user_id)` method inside the 'UserManager' class and rewrite it to handle `UserNotFoundError` by catching it and returning a default dictionary: `{'id': user_id, 'name': 'Anonymous', 'role': 'guest'}`."
    )
    usage3 = await run_phase(3, "Surgically Refactor server.py (Python)", p3_prompt)

    # Phase 4: C# Refactoring
    p4_prompt = (
        "TASK: Surgically refactor `Program.cs` (C#).\n"
        "- Rely on the Ultimate protocol in your system prompt.\n"
        "- Sub-task A: Globally change the identifier `userId` to `memberId` across all definitions and usage (Reverse-Order Patching with JIT coords).\n"
        "- Sub-task B: Structurally locate the entire `public double GetDiscount(double amount)` method inside the 'DiscountCalculator' class and rewrite it to include a loyalty tier bonus: if amount is greater than 100, apply a 15% discount, otherwise apply a 5% discount."
    )
    usage4 = await run_phase(4, "Surgically Refactor Program.cs (C#)", p4_prompt)

    # Phase 5: PHP Refactoring
    p5_prompt = (
        "TASK: Surgically refactor `payout.php` (PHP).\n"
        "- Rely on the Ultimate protocol in your system prompt.\n"
        "- Sub-task A: Globally change the member variable name `baseRate` to `hourlyRate` (and its reference `$this->baseRate` to `$this->hourlyRate`) across all definitions and usage (Reverse-Order Patching with JIT coords).\n"
        "- Sub-task B: Structurally locate the entire `public function getPayment($hours)` method inside the 'PayoutCalculator' class and rewrite it to include a overtime bonus: if `$hours > 40`, apply a 1.5x overtime multiplier on hours exceeding 40."
    )
    usage5 = await run_phase(5, "Surgically Refactor payout.php (PHP)", p5_prompt)

    # Phase 6: Java Refactoring
    p6_prompt = (
        "TASK: Surgically refactor `Tracker.java` (Java).\n"
        "- Rely on the Ultimate protocol in your system prompt.\n"
        "- Sub-task A: Globally change the private field `traceId` to `correlationId` across all definitions and usage (Reverse-Order Patching with JIT coords).\n"
        "- Sub-task B: Structurally locate the entire `public void logEvent(String name)` method inside the 'Tracker' class and rewrite it to prepend a timestamp prefix in brackets before the ID: `System.out.println(\"[2026-05-19] [\" + this.correlationId + \"] Event: \" + name);`."
    )
    usage6 = await run_phase(6, "Surgically Refactor Tracker.java (Java)", p6_prompt)

    # Aggregate usages
    for u in [usage1, usage2, usage3, usage4, usage5, usage6]:
        for k in cumulative_usage:
            cumulative_usage[k] += u.get(k, 0)

    print(f"\n{'=' * 80}")
    print("  🏆 Polyglot Refactoring Lifecycle Execution Complete!")
    print(f"{'=' * 80}")
    print(f"📊 Cumulative Token Usage across all 6 phases: {cumulative_usage}\n")

if __name__ == "__main__":
    asyncio.run(main())
