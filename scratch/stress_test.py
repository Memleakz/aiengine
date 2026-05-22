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

def generate_monolithic_file():
    workspace_dir = os.path.join(_SRC_DIR, "challenge_workspace")
    if not os.path.exists(workspace_dir):
        os.makedirs(workspace_dir)
    
    file_path = os.path.join(workspace_dir, "monolith.py")
    
    classes_code = []
    # Write 10 large, highly realistic classes to reach 1,000+ lines of Python!
    for i in range(1, 11):
        class_name = f"ServiceClass{i}"
        methods = []
        for m in range(1, 10):
            # Introduce dozens of duplicate variable names (config, state, logger, client)
            # across all methods in all classes to challenge search-and-replace specificity!
            methods.append(f"""    def process_data_stage_{m}(self, raw_input):
        logger = "Class{i}_stage{m}_logger"
        config = "Class{i}_stage{m}_config"
        state = "Class{i}_stage{m}_state"
        client = "Class{i}_stage{m}_client"
        
        # Simulated heavy enterprise workload
        data_packet = {{
            "stage": {m},
            "owner": "{class_name}",
            "config": config,
            "state": state,
            "logger": logger,
            "raw": raw_input
        }}
        
        # Deep nesting level to trigger coordinate and indentation shifts
        if raw_input is not None:
            for item in [raw_input]:
                if isinstance(item, dict):
                    inner_config = item.get("config")
                    if inner_config:
                        config = inner_config
                        logger = "overridden_logger"
        
        return data_packet
""")
        
        # The 10th class will have a deeply nested final line to trigger the indentation inheritance defect!
        if i == 10:
            methods.append("""    def start_scheduler_service(self, config_payload):
        logger = "Class10_scheduler_logger"
        state = "initialized"
        
        def run_nested_loop():
            # Deep helper loop
            for x in range(3):
                if x == 2:
                    # The last line of the class has 20 spaces of indentation!
                    return "loop_completed_successfully"
            return "failed"
            
        return run_nested_loop()
""")
        
        class_code = f"class {class_name}:\n    def __init__(self, config):\n        self.config = config\n        self.logger = 'init_logger'\n        self.state = 'active'\n\n" + "\n".join(methods)
        classes_code.append(class_code)
        
    full_monolithic_code = "# Monolithic Enterprise Service monolith.py\n# " + "="*40 + "\n\n" + "\n\n".join(classes_code)
    
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(full_monolithic_code)

def validate_stress_results(workspace_dir: str) -> dict:
    results = {}
    file_path = os.path.join(workspace_dir, "monolith.py")
    if not os.path.exists(file_path):
        return {"rename_success": False, "isolation_maintained": False, "sibling_indent_correct": False}
        
    with open(file_path, "r") as f:
        code = f.read()
        
    # Check 1: Did we rename config -> config_payload in class 5 process_data_stage_3?
    # Class 5 process_data_stage_3 original line: config = "Class5_stage3_config"
    results["rename_success"] = 'config_payload = "Class5_stage3_config"' in code
    
    # Check 2: Global isolation check. Did we accidentally rename 'config' in other classes?
    # e.g. Class 1 stage 3 should still have 'config = "Class1_stage3_config"'
    results["isolation_maintained"] = 'config = "Class1_stage3_config"' in code and 'config = "Class9_stage3_config"' in code
    
    # Check 3: Indentation checking for the newly injected validate_scheduler_state method at EOF
    # The new method should start with EXACTLY 4 spaces of indentation.
    lines = code.splitlines()
    method_lines = [l for l in lines if "def validate_scheduler_state" in l]
    if method_lines:
        target_line = method_lines[0]
        # Exact check: must start with 4 spaces!
        results["sibling_indent_correct"] = target_line.startswith("    def") and not target_line.startswith("        ")
    else:
        results["sibling_indent_correct"] = False
        
    return results

async def run_stress_ast(prompt: str) -> dict:
    _section("STRESS TEST: RUNNING OPTIMIZED AST PIPELINE...")
    engine = LightweightEngine(
        workdir="challenge_workspace",
        allowed_tools=["bash", "patch_code_range", "read_file", "find_text", "get_ast", "run_query"],
        max_iterations=15,
        extra_completion_kwargs={
            "extra_body": {
                "options": {
                    "num_ctx": 32768  # 32k context for handling the 1,000-line file
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

async def run_stress_basic(prompt: str) -> dict:
    _section("STRESS TEST: RUNNING BASIC TOOLING PIPELINE...")
    engine = LightweightEngine(
        workdir="challenge_workspace",
        allowed_tools=["bash", "read_file", "file_write", "file_edit", "glob_search", "grep_search"],
        max_iterations=15,
        extra_completion_kwargs={
            "extra_body": {
                "options": {
                    "num_ctx": 32768
                }
            }
        }
    )
    try:
        plain_prompt = (
            "You are a general-purpose programming assistant with standard shell/file access. Your goal is to modify code files by reading and writing them. "
            "Solve the refactoring task using standard file editing."
        )
        engine.set_system_prompt(plain_prompt)
        
        done = await _drain(engine.run(prompt))
        usage = done.metadata.get("session_usage") if done else {}
        return usage
    finally:
        await engine.close()

async def run_stress_playbook_basic(prompt: str) -> dict:
    _section("STRESS TEST: RUNNING PLAYBOOK-GUIDED BASIC TOOLING PIPELINE...")
    engine = LightweightEngine(
        workdir="challenge_workspace",
        allowed_tools=["bash", "read_file", "file_write", "file_edit", "glob_search", "grep_search"],
        max_iterations=15,
        extra_completion_kwargs={
            "extra_body": {
                "options": {
                    "num_ctx": 32768
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

async def run_stress_budget_ast(prompt: str) -> dict:
    _section("STRESS TEST: RUNNING BUDGET AST PIPELINE...")
    engine = LightweightEngine(
        workdir="challenge_workspace",
        allowed_tools=["bash", "patch_code_range", "read_file", "find_text", "get_ast", "run_query"],
        max_iterations=6,  # Tight loop limit to prevent runaway costs
        extra_completion_kwargs={
            "extra_body": {
                "options": {
                    "num_ctx": 32768
                }
            }
        }
    )
    try:
        await engine.load_mcp_config("mcp_config.json")
        skill_path = os.path.join(_SRC_DIR, ".agent_skills", "budget_software_dev.md")
        with open(skill_path, "r", encoding="utf-8") as f:
            skill_content = f.read()
        engine.set_system_prompt(skill_content)
        
        done = await _drain(engine.run(prompt))
        usage = done.metadata.get("session_usage") if done else {}
        return usage
    finally:
        await engine.close()

async def main() -> None:
    _section("🔥 THE ULTIMATE 1,000-LINE ENTERPRISE STRESS TEST 🔥")

    stress_prompt = (
        "We want to refactor the monolithic enterprise service `monolith.py` (which is over 1,000 lines long with 10 classes).\n"
        "Please complete the following two critical modifications:\n\n"
        "1. **Isolated Renaming Challenge:** Inside the 'ServiceClass5' class, locate the method `process_data_stage_3` and rename the LOCAL variable "
        "name `config` (the variable assignment `config = ...` and its usage in the dictionary return) to `config_payload`.\n"
        "   - CRITICAL LAW: You must ONLY rename it inside this specific method. Do not touch or rename the variable `config` in any other method or class!\n\n"
        "2. **EOF Sibling Method Injection:** Inject a new sibling method `validate_scheduler_state(self)` at the end of the 'ServiceClass10' class.\n"
        "   - The new method should simply print a status check and return True.\n"
        "   - CRITICAL LAW: Make sure it is perfectly siblinged to the other methods of ServiceClass10 (indented at exactly 4 spaces). Do not nest it inside helper functions at EOF!"
    )

    # ==========================================================================
    # RUN A: AST Setup Stress Test
    # ==========================================================================
    _section("🚀 RUNNING AST SETUP...")
    generate_monolithic_file()
    
    # Verify line count
    with open(os.path.join(_SRC_DIR, "challenge_workspace", "monolith.py"), "r") as f:
        lines_count = len(f.readlines())
    print(f"Created monolith.py with {lines_count} lines of enterprise code.")
    
    ast_usage = await run_stress_ast(stress_prompt)
    ast_validation = validate_stress_results(os.path.join(_SRC_DIR, "challenge_workspace"))

    # ==========================================================================
    # RUN B: Budget AST Setup Stress Test
    # ==========================================================================
    _section("🚀 RUNNING BUDGET AST...")
    generate_monolithic_file()
    
    budget_ast_usage = await run_stress_budget_ast(stress_prompt)
    budget_ast_validation = validate_stress_results(os.path.join(_SRC_DIR, "challenge_workspace"))

    # ==========================================================================
    # RUN C: Playbook-Guided Basic Tooling Stress Test
    # ==========================================================================
    _section("🚀 RUNNING PLAYBOOK-GUIDED BASIC TOOLING...")
    generate_monolithic_file()
    
    playbook_basic_usage = await run_stress_playbook_basic(stress_prompt)
    playbook_basic_validation = validate_stress_results(os.path.join(_SRC_DIR, "challenge_workspace"))

    # ==========================================================================
    # RUN D: Plain Basic Tooling Stress Test (Baseline)
    # ==========================================================================
    _section("🚀 RUNNING PLAIN BASIC TOOLING...")
    generate_monolithic_file()
    
    basic_usage = await run_stress_basic(stress_prompt)
    basic_validation = validate_stress_results(os.path.join(_SRC_DIR, "challenge_workspace"))

    # ==========================================================================
    # FINAL STRESS TEST COMPARISON SCORECARD
    # ==========================================================================
    _section("🏆 THE ULTIMATE MONOLITHIC STRESS TEST SCORECARD")
    
    print("\n📊 STRESS TEST ACCURACY:")
    print("  1. Isolated Rename (Class 5):")
    print(f"     - AST Setup:           {'✅ Success' if ast_validation['rename_success'] else '❌ FAILED'}")
    print(f"     - Budget AST:          {'✅ Success' if budget_ast_validation['rename_success'] else '❌ FAILED'}")
    print(f"     - Playbook Basic:      {'✅ Success' if playbook_basic_validation['rename_success'] else '❌ FAILED'}")
    print(f"     - Plain Basic Tooling: {'✅ Success' if basic_validation['rename_success'] else '❌ FAILED'}")
    
    print("  2. Isolation Kept (Other Classes untouched):")
    print(f"     - AST Setup:           {'✅ Success' if ast_validation['isolation_maintained'] else '❌ FAILED (Global Regression)'}")
    print(f"     - Budget AST:          {'✅ Success' if budget_ast_validation['isolation_maintained'] else '❌ FAILED (Global Regression)'}")
    print(f"     - Playbook Basic:      {'✅ Success' if playbook_basic_validation['isolation_maintained'] else '❌ FAILED (Global Regression)'}")
    print(f"     - Plain Basic Tooling: {'✅ Success' if basic_validation['isolation_maintained'] else '❌ FAILED (Global Regression)'}")
    
    print("  3. EOF Sibling Indentation (4 spaces):")
    print(f"     - AST Setup:           {'✅ Success' if ast_validation['sibling_indent_correct'] else '❌ FAILED (Nested at EOF)'}")
    print(f"     - Budget AST:          {'✅ Success' if budget_ast_validation['sibling_indent_correct'] else '❌ FAILED (Nested at EOF)'}")
    print(f"     - Playbook Basic:      {'✅ Success' if playbook_basic_validation['sibling_indent_correct'] else '❌ FAILED (Nested at EOF)'}")
    print(f"     - Plain Basic Tooling: {'✅ Success' if basic_validation['sibling_indent_correct'] else '❌ FAILED (Nested at EOF)'}")

    print("\n📊 RESOURCE UTILITY SCORECARD:")
    print("  AST Pipeline Totals:")
    print(f"     - Prompt Tokens:     {ast_usage.get('prompt_tokens', 0)}")
    print(f"     - Completion Tokens: {ast_usage.get('completion_tokens', 0)}")
    print(f"     - Total Tokens:      {ast_usage.get('total_tokens', 0)}")
    
    print("  Budget AST Totals:")
    print(f"     - Prompt Tokens:     {budget_ast_usage.get('prompt_tokens', 0)}")
    print(f"     - Completion Tokens: {budget_ast_usage.get('completion_tokens', 0)}")
    print(f"     - Total Tokens:      {budget_ast_usage.get('total_tokens', 0)}")
    
    print("  Playbook Basic Totals:")
    print(f"     - Prompt Tokens:     {playbook_basic_usage.get('prompt_tokens', 0)}")
    print(f"     - Completion Tokens: {playbook_basic_usage.get('completion_tokens', 0)}")
    print(f"     - Total Tokens:      {playbook_basic_usage.get('total_tokens', 0)}")
    
    print("  Plain Basic Tooling Totals:")
    print(f"     - Prompt Tokens:     {basic_usage.get('prompt_tokens', 0)}")
    print(f"     - Completion Tokens: {basic_usage.get('completion_tokens', 0)}")
    print(f"     - Total Tokens:      {basic_usage.get('total_tokens', 0)}")

if __name__ == "__main__":
    asyncio.run(main())
