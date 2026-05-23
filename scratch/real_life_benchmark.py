import asyncio
import os
import shutil
import sys
import time
import subprocess
import json

# Ensure src path is in sys.path
_SRC_DIR = "/home/tobias/dev/Repo/aiengine/src"
sys.path.insert(0, _SRC_DIR)

from agent_engine import AgentEvent, LightweightEngine

_USE_COLOR = sys.stdout.isatty() and os.getenv("NO_COLOR") is None
_REASONING_COLOR = "\033[90m" if _USE_COLOR else ""
_GREEN = "\033[92m" if _USE_COLOR else ""
_RED = "\033[91m" if _USE_COLOR else ""
_YELLOW = "\033[93m" if _USE_COLOR else ""
_BLUE = "\033[94m" if _USE_COLOR else ""
_CYAN = "\033[96m" if _USE_COLOR else ""
_BOLD = "\033[1m" if _USE_COLOR else ""
_RESET_COLOR = "\033[0m" if _USE_COLOR else ""


def _section(title: str) -> None:
    print(f"\n{_BOLD}{'=' * 80}{_RESET_COLOR}")
    print(f"  {_BOLD}{_CYAN}{title}{_RESET_COLOR}")
    print(f"{_BOLD}{'=' * 80}{_RESET_COLOR}")


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


def setup_initial_app():
    """Create the initial challenge_workspace/real_life_app/ directory structure and code files."""
    workspace_dir = os.path.join(_SRC_DIR, "challenge_workspace")
    app_dir = os.path.join(workspace_dir, "real_life_app")
    
    if os.path.exists(app_dir):
        shutil.rmtree(app_dir)
    os.makedirs(app_dir, exist_ok=True)
    
    # 1. __init__.py
    with open(os.path.join(app_dir, "__init__.py"), "w") as f:
        f.write("# Real-Life E-Commerce App package\n")

    # 2. models.py (Standard model structure)
    with open(os.path.join(app_dir, "models.py"), "w", encoding="utf-8") as f:
        f.write("""from dataclasses import dataclass
from typing import Optional

@dataclass
class User:
    id: int
    username: str
    balance: float
    is_active: bool = True

@dataclass
class Item:
    id: int
    name: str
    price: float
    stock: int

@dataclass
class Order:
    id: Optional[int]
    user_id: int
    item_id: int
    quantity: int
    total_price: float
""")

    # 3. repository.py (Initial In-Memory repository)
    with open(os.path.join(app_dir, "repository.py"), "w", encoding="utf-8") as f:
        f.write("""import asyncio
from typing import Dict, List, Optional
from .models import User, Item, Order

class InMemoryRepository:
    def __init__(self):
        self._users: Dict[int, User] = {}
        self._items: Dict[int, Item] = {}
        self._orders: Dict[int, Order] = {}
        self._order_id_counter = 1

    async def init_db(self):
        # Setup initial items and users
        self._users[1] = User(id=1, username="alice", balance=100.0)
        self._users[2] = User(id=2, username="bob", balance=20.0)
        
        self._items[101] = Item(id=101, name="Coffee Maker", price=49.99, stock=5)
        self._items[102] = Item(id=102, name="Coffee Beans", price=12.50, stock=20)

    async def get_user(self, user_id: int) -> Optional[User]:
        return self._users.get(user_id)

    async def update_user_balance(self, user_id: int, new_balance: float) -> bool:
        if user_id in self._users:
            self._users[user_id].balance = new_balance
            return True
        return False

    async def get_item(self, item_id: int) -> Optional[Item]:
        return self._items.get(item_id)

    async def update_item_stock(self, item_id: int, new_stock: int) -> bool:
        if item_id in self._items:
            self._items[item_id].stock = new_stock
            return True
        return False

    async def create_order(self, order: Order) -> Order:
        order.id = self._order_id_counter
        self._orders[order.id] = order
        self._order_id_counter += 1
        return order

    async def get_orders_by_user(self, user_id: int) -> List[Order]:
        return [o for o in self._orders.values() if o.user_id == user_id]
""")

    # 4. auth.py (Starting basic authentication service)
    with open(os.path.join(app_dir, "auth.py"), "w", encoding="utf-8") as f:
        f.write("""from typing import Optional

class AuthenticationService:
    def __init__(self):
        self._tokens = {
            "token_alice": "alice",
            "token_bob": "bob"
        }

    async def authenticate(self, token: str) -> Optional[str]:
        return self._tokens.get(token)
""")

    # 5. service.py (Starting service with no transaction safety)
    with open(os.path.join(app_dir, "service.py"), "w", encoding="utf-8") as f:
        f.write("""from typing import Optional
from .models import Order

class ECommerceService:
    def __init__(self, repository):
        self.repository = repository

    async def place_order(self, user_id: int, item_id: int, quantity: int) -> Optional[Order]:
        user = await self.repository.get_user(user_id)
        item = await self.repository.get_item(item_id)
        
        if not user or not item:
            raise ValueError("User or Item not found")
            
        total_price = item.price * quantity
        
        if user.balance < total_price:
            raise ValueError("Insufficient balance")
            
        if item.stock < quantity:
            raise ValueError("Out of stock")
            
        # Deduct user balance
        await self.repository.update_user_balance(user_id, user.balance - total_price)
        
        # Decrement stock
        await self.repository.update_item_stock(item_id, item.stock - quantity)
        
        # Create order
        order = Order(id=None, user_id=user_id, item_id=item_id, quantity=quantity, total_price=total_price)
        created_order = await self.repository.create_order(order)
        
        return created_order
""")


def run_tests() -> dict:
    """Execute pytest against the test file and parse results."""
    test_file = os.path.join(_SRC_DIR, "scratch", "test_real_life_app.py")
    
    # We run pytest outputting as JSON (using pytest-json-report or parsing stdout if missing,
    # let's run simple python integration to run tests directly or parse pytest console output)
    result = subprocess.run(
        ["pytest", test_file, "-v", "--tb=short"],
        capture_output=True,
        text=True
    )
    
    output = result.stdout
    success = (result.returncode == 0)
    
    tests_states = {
        "test_db_initialization": "FAILED",
        "test_db_crud_operations": "FAILED",
        "test_rate_limiter_limit": "FAILED",
        "test_rate_limiter_refill": "FAILED",
        "test_rate_limiter_isolation": "FAILED",
        "test_rate_limiter_capacity_cap": "FAILED",
        "test_order_placement_success": "FAILED",
        "test_order_placement_insufficient_balance": "FAILED",
        "test_order_placement_out_of_stock": "FAILED",
        "test_order_placement_db_error_rollback": "FAILED",
    }
    
    for line in output.splitlines():
        if "PASSED" in line or "FAILED" in line:
            for test_name in tests_states:
                if test_name in line:
                    tests_states[test_name] = "PASSED" if "PASSED" in line else "FAILED"
                    
    # Double check if any test wasn't captured, meaning pytest failed to import the code
    if "ImportError" in output or "SyntaxError" in output or "AttributeError" in output:
         print(f"{_RED}⚠️ Pytest encountered a fatal compilation / import error during validation:{_RESET_COLOR}")
         print(f"{_RED}{output}{_RESET_COLOR}")
         
    return {
        "success": success,
        "raw_output": output,
        "results": tests_states
    }


async def run_agent_ast(prompt: str) -> dict:
    _section("🚀 RUNNING AST-GUIDED PIPELINE...")
    
    engine = LightweightEngine(
        workdir="challenge_workspace",
        allowed_tools=[
            "bash", "read_file", "file_write", "file_edit", 
            "get_document_map", "batch_ast_query"
        ],
        max_iterations=20,
    )
    
    try:
        # Load MCP configuration to boot MCP servers
        await engine.load_mcp_config("mcp_config.json")
        
        # Load precision AST instruction guide
        skill_path = os.path.join(_SRC_DIR, ".agent_skills", "ultimate_software_dev.md")
        with open(skill_path, "r", encoding="utf-8") as f:
            skill_content = f.read()
        engine.set_system_prompt(skill_content)
        
        t0 = time.time()
        done = await _drain(engine.run(prompt))
        duration = time.time() - t0
        
        usage = done.metadata.get("session_usage") if done else {}
        if not usage:
             usage = done.metadata.get("usage") if done else {}
             
        return {
            "duration": duration,
            "usage": usage or {}
        }
    finally:
        await engine.close()


async def run_agent_basic(prompt: str) -> dict:
    _section("🏃 RUNNING BASIC TOOLING PIPELINE...")
    
    engine = LightweightEngine(
        workdir="challenge_workspace",
        allowed_tools=["bash", "read_file", "file_write", "file_edit", "glob_search", "grep_search"],
        max_iterations=20,
    )
    
    try:
        system_instructions = (
            "You are a general-purpose programming assistant with standard shell/file access. Your goal is to modify code files by reading and writing them.\n"
            "You do not have access to custom AST parsing or Tree-Sitter tools. Solve the database migration, rate limiter, and transaction tasks using standard file editing.\n"
            "CRITICAL: Limit your planning/reasoning content to a maximum of 2-3 sentences per turn. Immediately execute your tool calls. Do not write long explanations, checklists, or summaries. Speed is highly prioritized.\n"
            "Self-Verification & Test Loop: You are highly encouraged to run the test suite using `pytest scratch/test_real_life_app.py` in a `bash` tool call after editing files. If any tests fail, inspect the tracebacks, surgically edit the code to fix any typos or logic errors, and rerun the tests until everything passes perfectly before exiting."
        )
        engine.set_system_prompt(system_instructions)
        
        t0 = time.time()
        done = await _drain(engine.run(prompt))
        duration = time.time() - t0
        
        usage = done.metadata.get("session_usage") if done else {}
        if not usage:
             usage = done.metadata.get("usage") if done else {}
             
        return {
            "duration": duration,
            "usage": usage or {}
        }
    finally:
        await engine.close()


async def main() -> None:
    _section("🔬 REAL-LIFE PRODUCTION ENGINEERING BENCHMARK RUNNER (COMPARATIVE)")
    
    specification_prompt = (
        "TASK: Transform `real_life_app/` to async SQLite.\n"
        "1. `repository.py`: Replace `InMemoryRepository` with `SQLiteRepository(db_path='ecommerce.db')`.\n"
        "   - CRITICAL: Connect to SQLite directly in `__init__` using `self.connection = sqlite3.connect(db_path, check_same_thread=False)` and set `self.connection.row_factory = sqlite3.Row`. Do not initialize connection as None or use async connect.\n"
        "   - `async def init_db(self)`: create `users`(id INTEGER PRIMARY KEY, username TEXT, balance REAL, is_active BOOLEAN DEFAULT 1), `items`(id INTEGER PRIMARY KEY, name TEXT, price REAL, stock INTEGER), `orders`(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, item_id INTEGER, quantity INTEGER, total_price REAL, FOREIGN KEY(user_id) REFERENCES users(id), FOREIGN KEY(item_id) REFERENCES items(id)).\n"
        "   - Seed users exactly: (1, 'alice', 100.0), (2, 'bob', 20.0). Items exactly: (101, 'Coffee Maker', 49.99, 5), (102, 'Coffee Beans', 12.50, 20).\n"
        "   - Async CRUD using `sqlite3` inside `asyncio.to_thread`:\n"
        "     * `get_user`, `update_user_balance`, `get_item`, `update_item_stock`.\n"
        "     * `create_order` (inserts, sets generated id, returns updated Order).\n"
        "     * `get_orders_by_user`.\n"
        "2. `auth.py`: `TokenBucketRateLimiter(capacity, refill_rate)` with `async def acquire(client_id)`. Time-based refill (no loops), cap at capacity.\n"
        "3. `service.py`: Refactor `place_order`. Stock/balance checks (check stock before balance!), deduction, decrement, and order creation must run in one SQLite transaction context. Roll back if any step fails.\n"
        "   - ARCHITECTURAL HINT: To ensure all DB updates in `place_order` share a single connection/transaction, SQLiteRepository can share a single connection (e.g. self.connection = sqlite3.connect(db_path, check_same_thread=False)) and support a transaction context manager (e.g., self.connection.execute('BEGIN'), committing or rolling back in __aexit__), allowing service.py to do: `async with repo.transaction(): ...`.\n"
        "CRITICAL: You MUST make tool calls in every step. No text-only plans, or the session ends! Edit real_life_app/ and exit when done."
    )
    
    # ==========================================================================
    # RUN A: AST-Guided Pipeline
    # ==========================================================================
    print(f"\n{_BOLD}{_BLUE}=== [1/2] RUNNING AST-GUIDED AGENT PIPELINE ==={_RESET_COLOR}")
    setup_initial_app()
    ast_stats = await run_agent_ast(specification_prompt)
    print(f"Running verification tests for AST Pipeline...")
    ast_test_res = run_tests()
    
    # ==========================================================================
    # RUN B: Basic Tooling Pipeline
    # ==========================================================================
    print(f"\n{_BOLD}{_YELLOW}=== [2/2] RUNNING BASIC TOOLING AGENT PIPELINE ==={_RESET_COLOR}")
    setup_initial_app()
    basic_stats = await run_agent_basic(specification_prompt)
    print(f"Running verification tests for Basic Tooling Pipeline...")
    basic_test_res = run_tests()
    
    # ==========================================================================
    # COMPARATIVE SUMMARY SCORECARD
    # ==========================================================================
    _section("🏆 REAL-LIFE ENGINEERING BENCHMARK SCORECARD: AST VS BASIC")
    
    ast_res = ast_test_res["results"]
    basic_res = basic_test_res["results"]
    
    all_tests = [
        ("test_db_initialization", "1. SQLite Database Schema Init"),
        ("test_db_crud_operations", "1. SQLite Async CRUD Operations"),
        ("test_rate_limiter_limit", "2. Rate Limiting Enforced"),
        ("test_rate_limiter_refill", "2. Dynamic Token Refill"),
        ("test_rate_limiter_isolation", "2. Client Isolation Check"),
        ("test_rate_limiter_capacity_cap", "2. Max Capacity Bounds"),
        ("test_order_placement_success", "3. Atomic Order Placement Success"),
        ("test_order_placement_insufficient_balance", "3. Insufficient Balance Rollback"),
        ("test_order_placement_out_of_stock", "3. Out of Stock Rollback"),
        ("test_order_placement_db_error_rollback", "3. DB Malformation Write Rollback"),
    ]
    
    def fmt(status):
        return f"{_GREEN}PASSED{_RESET_COLOR}" if status == "PASSED" else f"{_RED}FAILED{_RESET_COLOR}"
        
    print(f"{_BOLD}{'Sub-Task / Test Case':<45} {'AST Pipeline':<15} {'Basic Tooling':<15}{_RESET_COLOR}")
    print("-" * 80)
    for test_key, test_lbl in all_tests:
        print(f"{test_lbl:<45} {fmt(ast_res.get(test_key)):<15} {fmt(basic_res.get(test_key)):<15}")
    print("-" * 80)
    
    ast_passed = sum(1 for t, _ in all_tests if ast_res.get(t) == "PASSED")
    basic_passed = sum(1 for t, _ in all_tests if basic_res.get(t) == "PASSED")
    print(f"{_BOLD}{'TOTAL SUB-TASKS PASSED':<45} {ast_passed}/10{'':<11} {basic_passed}/10{_RESET_COLOR}\n")
    
    # Resource metrics comparison
    ast_u = ast_stats["usage"]
    basic_u = basic_stats["usage"]
    ast_dur = ast_stats["duration"]
    basic_dur = basic_stats["duration"]
    
    print(f"{_BOLD}📊 DEVELOPMENT METRICS & RESOURCE CONSUMPTION:{_RESET_COLOR}")
    print(f"   - Completion Time:   AST: {_GREEN}{ast_dur:.2f}s{_RESET_COLOR} | Basic: {_YELLOW}{basic_dur:.2f}s{_RESET_COLOR}")
    print(f"   - Prompt Tokens:     AST: {ast_u.get('prompt_tokens', 0):<8} | Basic: {basic_u.get('prompt_tokens', 0)}")
    print(f"   - Completion Tokens: AST: {ast_u.get('completion_tokens', 0):<8} | Basic: {basic_u.get('completion_tokens', 0)}")
    print(f"   - Reasoning Tokens:  AST: {ast_u.get('reasoning_tokens', 0):<8} | Basic: {basic_u.get('reasoning_tokens', 0)}")
    print(f"   - Total Tokens:      AST: {ast_u.get('total_tokens', 0):<8} | Basic: {basic_u.get('total_tokens', 0)}")
    
    # Save a report
    report_file = os.path.join(_SRC_DIR, "scratch", "real_life_benchmark_report.json")
    report = {
         "timestamp": time.time(),
         "ast": {
              "total_passed": ast_passed,
              "individual_results": ast_res,
              "metrics": {
                   "duration": ast_dur,
                   "prompt_tokens": ast_u.get('prompt_tokens', 0),
                   "completion_tokens": ast_u.get('completion_tokens', 0),
                   "reasoning_tokens": ast_u.get('reasoning_tokens', 0),
                   "total_tokens": ast_u.get('total_tokens', 0)
              }
         },
         "basic": {
              "total_passed": basic_passed,
              "individual_results": basic_res,
              "metrics": {
                   "duration": basic_dur,
                   "prompt_tokens": basic_u.get('prompt_tokens', 0),
                   "completion_tokens": basic_u.get('completion_tokens', 0),
                   "reasoning_tokens": basic_u.get('reasoning_tokens', 0),
                   "total_tokens": basic_u.get('total_tokens', 0)
              }
         }
    }
    with open(report_file, "w") as f:
         json.dump(report, f, indent=4)
    print(f"\n{_GREEN}✓ Benchmark report saved to {report_file}{_RESET_COLOR}\n")



if __name__ == "__main__":
    asyncio.run(main())
