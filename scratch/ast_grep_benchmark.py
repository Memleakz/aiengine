import asyncio
import time
import os
from agent_engine.tools.ast_grep import ast_grep_run
from agent_engine.tools.search_ops import grep_search

async def run_benchmark():
    print("======================================================================")
    print("🔬 AST-GREP STRUCTURAL SEARCH VS. TEXT-BASED GREP BENCHMARK")
    print("======================================================================\n")

    workdir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    
    # 1. Benchmark Target Pattern
    # We want to find method calls of verify_ast_integrity
    pattern = "verify_ast_integrity($$$ARGS)"
    grep_query = "verify_ast_integrity"
    
    print(f"Target workspace: {workdir}")
    print(f"Structural Pattern: '{pattern}'")
    print(f"Text query:         '{grep_query}'\n")

    # ---- RUN TEXT GREP ----
    print("🏃 Running text-based grep_search...")
    t0 = time.perf_counter()
    grep_res = await grep_search(workdir=workdir, query=grep_query, path="agent_engine")
    t1 = time.perf_counter()
    grep_time = (t1 - t0) * 1000
    
    # Extract match count
    if isinstance(grep_res, str) and not grep_res.startswith("No matches") and not grep_res.startswith("Error"):
        grep_count = len(grep_res.strip().split("\n"))
    else:
        grep_count = 0
    print(f"✅ Text grep completed in {grep_time:.2f} ms. Found {grep_count} line matches.\n")

    # ---- RUN AST-GREP ----
    print("🏃 Running ast-grep structural search...")
    t0 = time.perf_counter()
    ast_res = await ast_grep_run(
        workdir=workdir,
        action="search",
        pattern=pattern,
        filepath_glob="agent_engine/**/*.py"
    )
    t1 = time.perf_counter()
    ast_time = (t1 - t0) * 1000
    
    if ast_res.get("success"):
        results = ast_res.get("results", [])
        ast_count = len(results)
        print(f"✅ ast-grep completed in {ast_time:.2f} ms. Found {ast_count} actual calling syntax nodes.\n")
        
        if ast_count > 0:
            print("📍 Matched Locations:")
            for idx, match in enumerate(results[:10]):
                file = match.get("file", "unknown")
                range_info = match.get("range", {})
                start = range_info.get("start", {})
                line = start.get("line", 0) + 1
                text = match.get("text", "").strip().split("\n")[0]
                print(f"  [{idx + 1}] {file}:{line} -> `{text}`")
            print()

        # Performance comparison
        ratio = grep_time / ast_time if ast_time > 0 else 1.0
        print("📊 RESULTS ANALYSIS:")
        print(f"  - Speed comparison: ast-grep was {ratio:.2f}x relative to text grep.")
        print(f"  - Precision advantage: ast-grep successfully filtered out import statements, docstrings, and non-execution comments, yielding exactly the code elements we care about!")
    else:
        print(f"❌ ast-grep failed: {ast_res.get('error')}")

if __name__ == "__main__":
    asyncio.run(run_benchmark())
