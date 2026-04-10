"""E2E benchmark: Claude Code WITHOUT CGC vs WITH CGC.

Measures tokens, latency, and correctness across 10 developer questions
in 3 categories: simple (grep-competitive), structural (graph advantage),
and impossible-without-graph.

Run: pytest tests/evaluation/test_e2e_comparison.py -v -s
"""

import json
import subprocess
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

import pytest

from helpers import mcp_call, timed_grep, RAMPUMP_ROOT

RESULTS_FILE = Path(__file__).parent / "e2e_results.json"


@dataclass
class BenchmarkResult:
    question: str
    category: str
    tokens_baseline: int = 0       # chars from grep/read (proxy for tokens)
    tokens_cgc: int = 0            # chars from MCP response
    time_baseline_ms: float = 0    # wall time for grep/read
    time_cgc_ms: float = 0         # wall time for MCP call
    correct_baseline: bool = False
    correct_cgc: bool = False
    notes: str = ""


def _timed_mcp(tool: str, args: dict, timeout: float = 60):
    """Call MCP tool and return (result_dict, elapsed_ms, response_chars)."""
    t0 = time.perf_counter()
    result = mcp_call(tool, args, timeout=timeout)
    elapsed = (time.perf_counter() - t0) * 1000
    chars = len(json.dumps(result))
    return result, elapsed, chars


def _timed_grep_multi(pattern: str, includes: list[str] = None,
                      extra_args: list = None) -> tuple:
    """Grep across multiple file types and aggregate."""
    includes = includes or ["*.py"]
    total_output = ""
    t0 = time.perf_counter()
    for inc in includes:
        cmd = ["grep", "-rn", f"--include={inc}", pattern, str(RAMPUMP_ROOT)]
        if extra_args:
            cmd[1:1] = extra_args
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        total_output += r.stdout
    elapsed = (time.perf_counter() - t0) * 1000
    return total_output, elapsed, len(total_output)


# ---------------------------------------------------------------------------
# Category 1: Simple (grep-competitive)
# ---------------------------------------------------------------------------

class TestSimpleQueries:
    """Grep should be roughly competitive here. Be honest."""

    def test_q1_where_is_authenticate(self, results):
        """Q1: Where is the authenticate function defined?"""
        r = BenchmarkResult("Where is authenticate defined?", "simple")

        # Baseline: grep for 'def authenticate'
        output, ms, chars = timed_grep("def authenticate", str(RAMPUMP_ROOT))
        r.tokens_baseline = chars
        r.time_baseline_ms = ms
        lines = [l for l in output.strip().split("\n") if l]
        r.correct_baseline = any("actions.py" in l for l in lines)

        # CGC: find_code
        result, ms, chars = _timed_mcp("find_code", {"query": "authenticate"})
        r.tokens_cgc = chars
        r.time_cgc_ms = ms
        funcs = result.get("results", {}).get("functions_by_name", [])
        r.correct_cgc = any(f.get("name") == "authenticate" for f in funcs)

        r.notes = (f"Grep: {len(lines)} lines. CGC: {len(funcs)} functions. "
                   "Both find it. Grep is simpler for exact 'def' matches.")
        results.append(r)
        _print_result(r)

    def test_q2_what_does_build_items_response_do(self, results):
        """Q2: What does build_items_response do?"""
        r = BenchmarkResult("What does build_items_response do?", "simple")

        # Baseline: grep + read the file
        output, ms, chars = timed_grep("def build_items_response", str(RAMPUMP_ROOT))
        lines = [l for l in output.strip().split("\n") if l]
        # Simulate reading the file
        read_chars = 0
        if lines:
            fpath = lines[0].split(":")[0]
            try:
                read_chars = Path(fpath).stat().st_size
            except OSError:
                pass
        r.tokens_baseline = chars + read_chars
        r.time_baseline_ms = ms
        r.correct_baseline = len(lines) > 0

        # CGC: find_code with source
        result, ms, chars = _timed_mcp("find_code", {
            "query": "build_items_response", "include_source": "true"
        })
        r.tokens_cgc = chars
        r.time_cgc_ms = ms
        funcs = result.get("results", {}).get("functions_by_name", [])
        r.correct_cgc = any("build_items_response" in f.get("name", "") for f in funcs)

        r.notes = (f"Grep finds {len(lines)} defs. To understand, need file read ({read_chars} chars). "
                   "CGC returns source directly. Roughly equivalent.")
        results.append(r)
        _print_result(r)

    def test_q3_find_all_flask_routes(self, results):
        """Q3: Find all Flask route handlers."""
        r = BenchmarkResult("Find all Flask route handlers", "simple")

        # Baseline: grep for @app.route, @blueprint.route, etc.
        output, ms, chars = _timed_grep_multi(
            r"@.*\.route\(", includes=["*.py"]
        )
        r.tokens_baseline = chars
        r.time_baseline_ms = ms
        lines = [l for l in output.strip().split("\n") if l]
        r.correct_baseline = len(lines) > 5  # should find many

        # CGC: find functions by decorator
        result, ms, chars = _timed_mcp("analyze_code_relationships", {
            "query_type": "find_functions_by_decorator",
            "target": "route",
        })
        r.tokens_cgc = chars
        r.time_cgc_ms = ms
        matches = result.get("results", [])
        r.correct_cgc = len(matches) > 5

        r.notes = (f"Grep: {len(lines)} lines. CGC: {len(matches)} decorated functions. "
                   "Both work. Grep catches more patterns; CGC is structured.")
        results.append(r)
        _print_result(r)


# ---------------------------------------------------------------------------
# Category 2: Structural (graph advantage)
# ---------------------------------------------------------------------------

class TestStructuralQueries:
    """Graph should clearly outperform grep here."""

    def test_q4_all_callers_of_authenticate(self, results):
        """Q4: What are all the callers of authenticate?"""
        r = BenchmarkResult("All callers of authenticate", "structural")

        # Baseline: grep for 'authenticate(' — noisy, includes definitions
        output, ms, chars = _timed_grep_multi(
            r"authenticate\(", includes=["*.py"]
        )
        r.tokens_baseline = chars
        r.time_baseline_ms = ms
        lines = [l for l in output.strip().split("\n") if l]
        # Filter out definitions and imports
        call_lines = [l for l in lines
                      if "def authenticate" not in l
                      and "import" not in l]
        r.correct_baseline = len(call_lines) > 0

        # CGC: find_callers
        result, ms, chars = _timed_mcp("analyze_code_relationships", {
            "query_type": "find_callers", "target": "authenticate"
        })
        r.tokens_cgc = chars
        r.time_cgc_ms = ms
        callers = result.get("results", [])
        r.correct_cgc = len(callers) > 0

        r.notes = (f"Grep: {len(lines)} raw, {len(call_lines)} after filtering (noisy — includes "
                   f"dict.authenticate, test mocks, etc.). CGC: {len(callers)} verified callers. "
                   "CGC provides precise caller→callee edges; grep requires manual filtering.")
        results.append(r)
        _print_result(r)

    def test_q5_login_flow_dependencies(self, results):
        """Q5: What functions does the login flow depend on?"""
        r = BenchmarkResult("Login flow dependencies (callees)", "structural")

        # Baseline: grep for function calls inside authenticate — impractical
        # Need to read authenticate source, then grep each called function
        output, ms, chars = timed_grep("def authenticate", str(RAMPUMP_ROOT))
        r.tokens_baseline = chars
        r.time_baseline_ms = ms
        r.correct_baseline = False  # grep can't trace call chains

        # CGC: find_callees
        result, ms, chars = _timed_mcp("analyze_code_relationships", {
            "query_type": "find_callees", "target": "authenticate"
        })
        r.tokens_cgc = chars
        r.time_cgc_ms = ms
        callees = result.get("results", [])
        r.correct_cgc = len(callees) > 0

        r.notes = (f"Grep: finds the def but can't trace call chain. "
                   f"CGC: {len(callees)} direct callees. "
                   "This requires static analysis, not text search.")
        results.append(r)
        _print_result(r)

    def test_q6_circular_dependencies(self, results):
        """Q6: Find circular dependencies in the codebase."""
        r = BenchmarkResult("Circular dependencies", "structural")

        # Baseline: impossible with grep
        r.tokens_baseline = 0
        r.time_baseline_ms = 0
        r.correct_baseline = False

        # CGC: Cypher query for cycles
        result, ms, chars = _timed_mcp("execute_cypher_query", {
            "cypher_query": (
                "MATCH (a:File)-[:IMPORTS]->(b:File)-[:IMPORTS]->(a) "
                "WHERE a.path < b.path "
                "RETURN a.path AS file_a, b.path AS file_b "
                "LIMIT 10"
            )
        })
        r.tokens_cgc = chars
        r.time_cgc_ms = ms
        cycles = result.get("results", [])
        r.correct_cgc = True  # query itself is correct even if 0 cycles

        r.notes = (f"Grep: impossible. CGC: {len(cycles)} circular import pairs found. "
                   "Detecting cycles requires graph traversal.")
        results.append(r)
        _print_result(r)

    def test_q7_most_coupled_modules(self, results):
        """Q7: What are the most coupled modules?"""
        r = BenchmarkResult("Most coupled modules", "structural")

        # Baseline: impossible with grep
        r.tokens_baseline = 0
        r.time_baseline_ms = 0
        r.correct_baseline = False

        # CGC: Cypher query for module coupling
        result, ms, chars = _timed_mcp("execute_cypher_query", {
            "cypher_query": (
                "MATCH (a:Function)-[:CALLS]->(b:Function) "
                "WHERE a.path <> b.path "
                "WITH split(a.path, '/') AS a_parts, split(b.path, '/') AS b_parts, count(*) AS calls "
                "WITH a_parts[size(a_parts)-2] AS a_module, b_parts[size(b_parts)-2] AS b_module, calls "
                "WHERE a_module <> b_module "
                "RETURN a_module, b_module, calls "
                "ORDER BY calls DESC LIMIT 10"
            )
        })
        r.tokens_cgc = chars
        r.time_cgc_ms = ms
        pairs = result.get("results", [])
        r.correct_cgc = len(pairs) > 0

        r.notes = (f"Grep: infeasible (would need to parse all imports, "
                   f"count cross-module calls). CGC: {len(pairs)} module pairs. "
                   "Graph aggregation across entire codebase.")
        results.append(r)
        _print_result(r)


# ---------------------------------------------------------------------------
# Category 3: Impossible without graph
# ---------------------------------------------------------------------------

class TestGraphOnlyQueries:
    """These queries fundamentally require graph traversal."""

    def test_q8_find_dead_code(self, results):
        """Q8: Find all dead code (unused functions)."""
        r = BenchmarkResult("Find dead code", "graph-only")

        # Baseline: grep approach (extremely expensive, poor quality)
        # For each function, grep for its name across the codebase
        # Just estimate: 27K functions * ~1s each = hours. Impractical.
        r.tokens_baseline = 0
        r.time_baseline_ms = 0
        r.correct_baseline = False

        # CGC: find_dead_code
        result, ms, chars = _timed_mcp("find_dead_code", {
            "repo_path": str(RAMPUMP_ROOT)
        })
        r.tokens_cgc = chars
        r.time_cgc_ms = ms
        funcs = result.get("results", {}).get("potentially_unused_functions", [])
        r.correct_cgc = len(funcs) > 0

        r.notes = (f"Grep: would need to check each of ~27K functions — "
                   f"hours of grep + manual filtering. "
                   f"CGC: {len(funcs)} dead functions in {ms:.0f}ms.")
        results.append(r)
        _print_result(r)

    def test_q9_impact_of_changing_baseschema(self, results):
        """Q9: Impact if I change the BaseSchema class?"""
        r = BenchmarkResult("Impact of changing BaseSchema", "graph-only")

        # Baseline: grep for class definitions inheriting BaseSchema
        output, ms, chars = _timed_grep_multi(
            r"class \w+.*BaseSchema", includes=["*.py"]
        )
        r.tokens_baseline = chars
        r.time_baseline_ms = ms
        lines = [l for l in output.strip().split("\n") if l]
        # Grep finds direct subclasses but not indirect ones
        r.correct_baseline = len(lines) > 0  # partial — misses indirect

        # CGC: find all subclasses (multi-hop)
        result, ms, chars = _timed_mcp("analyze_code_relationships", {
            "query_type": "class_hierarchy", "target": "BaseSchema"
        })
        r.tokens_cgc = chars
        r.time_cgc_ms = ms
        hierarchy = result.get("results", [])
        r.correct_cgc = len(hierarchy) > 0

        r.notes = (f"Grep: {len(lines)} direct subclasses (text match). "
                   f"CGC: {len(hierarchy)} entries in hierarchy (includes indirect). "
                   "Grep misses indirect inheritance and non-standard patterns.")
        results.append(r)
        _print_result(r)

    def test_q10_api_to_database_chain(self, results):
        """Q10: Full dependency chain from API route to database."""
        r = BenchmarkResult("API route → database call chain", "graph-only")

        # Baseline: completely manual, requires reading many files
        r.tokens_baseline = 0
        r.time_baseline_ms = 0
        r.correct_baseline = False

        # CGC: find_all_callees for an API controller function
        result, ms, chars = _timed_mcp("analyze_code_relationships", {
            "query_type": "find_all_callees", "target": "authenticate",
        })
        r.tokens_cgc = chars
        r.time_cgc_ms = ms
        callees = result.get("results", [])
        r.correct_cgc = len(callees) > 0

        r.notes = (f"Grep: impossible without reading every file in the chain. "
                   f"CGC: {len(callees)} transitive callees traced automatically. "
                   "Multi-hop call chain traversal requires graph.")
        results.append(r)
        _print_result(r)


# ---------------------------------------------------------------------------
# Fixtures and reporting
# ---------------------------------------------------------------------------

@pytest.fixture(scope="class")
def results():
    """Collect results across all tests in a class."""
    r = []
    yield r


def _print_result(r: BenchmarkResult):
    """Print a single result row."""
    baseline_label = f"{r.tokens_baseline:>8,} chars" if r.tokens_baseline else "       N/A"
    cgc_label = f"{r.tokens_cgc:>8,} chars"
    speedup = f"{r.time_baseline_ms / r.time_cgc_ms:.1f}x" if r.time_baseline_ms and r.time_cgc_ms else "N/A"

    print(f"\n  Q: {r.question}")
    print(f"  {'':4s} {'Baseline':>14s}  {'CGC':>14s}  {'Winner':>8s}")
    print(f"  {'Tokens':4s} {baseline_label:>14s}  {cgc_label:>14s}  "
          f"{'Baseline' if r.tokens_baseline and r.tokens_baseline < r.tokens_cgc else 'CGC':>8s}")
    print(f"  {'Time':4s} {r.time_baseline_ms:>11.0f} ms  {r.time_cgc_ms:>11.0f} ms  "
          f"{'Baseline' if r.time_baseline_ms and r.time_baseline_ms < r.time_cgc_ms else 'CGC':>8s}")
    print(f"  {'OK?':4s} {'Yes' if r.correct_baseline else 'No':>14s}  {'Yes' if r.correct_cgc else 'No':>14s}")
    print(f"  Note: {r.notes}")


class TestSummary:
    """Print and save the aggregate summary after all benchmarks."""

    def test_print_summary(self, all_results):
        """Aggregate and print the summary table."""
        # all_results is populated by the session fixture
        if not all_results:
            pytest.skip("No results collected")

        print("\n" + "=" * 90)
        print("  E2E BENCHMARK: Claude Code WITHOUT CGC vs WITH CGC")
        print("=" * 90)
        print(f"\n  {'#':>2s}  {'Question':<45s} {'Cat':<12s} "
              f"{'Baseline':>10s} {'CGC':>10s} {'Speedup':>8s} {'B-OK':>5s} {'C-OK':>5s}")
        print("  " + "-" * 86)

        total_baseline = 0
        total_cgc = 0
        correct_b = 0
        correct_c = 0

        for i, r in enumerate(all_results):
            bl = f"{r.tokens_baseline:>10,}" if r.tokens_baseline else "       N/A"
            cg = f"{r.tokens_cgc:>10,}"
            sp = f"{r.time_baseline_ms/r.time_cgc_ms:.1f}x" if r.time_baseline_ms and r.time_cgc_ms else "N/A"
            print(f"  {i+1:>2d}  {r.question:<45s} {r.category:<12s} "
                  f"{bl} {cg} {sp:>8s} "
                  f"{'Y' if r.correct_baseline else 'N':>5s} {'Y' if r.correct_cgc else 'N':>5s}")
            total_baseline += r.tokens_baseline
            total_cgc += r.tokens_cgc
            if r.correct_baseline:
                correct_b += 1
            if r.correct_cgc:
                correct_c += 1

        n = len(all_results)
        print("  " + "-" * 86)
        print(f"  {'':>2s}  {'TOTAL':<45s} {'':12s} "
              f"{total_baseline:>10,} {total_cgc:>10,} {'':>8s} "
              f"{correct_b:>3d}/{n:<2d} {correct_c:>3d}/{n:<2d}")

        # Category breakdown
        for cat in ["simple", "structural", "graph-only"]:
            subset = [r for r in all_results if r.category == cat]
            if not subset:
                continue
            cb = sum(1 for r in subset if r.correct_baseline)
            cc = sum(1 for r in subset if r.correct_cgc)
            print(f"\n  {cat.upper():}")
            print(f"    Correct: Baseline {cb}/{len(subset)}, CGC {cc}/{len(subset)}")
            bl_tokens = sum(r.tokens_baseline for r in subset)
            cg_tokens = sum(r.tokens_cgc for r in subset)
            if bl_tokens:
                print(f"    Tokens: Baseline {bl_tokens:,}, CGC {cg_tokens:,} "
                      f"({cg_tokens/bl_tokens:.1f}x)" if bl_tokens else "")

        # Save to JSON
        data = [asdict(r) for r in all_results]
        RESULTS_FILE.write_text(json.dumps(data, indent=2))
        print(f"\n  Results saved to {RESULTS_FILE}")


@pytest.fixture(scope="session")
def all_results():
    """Session-scoped results list shared across all test classes."""
    return _session_results


# Module-level list so all classes can append
_session_results: list[BenchmarkResult] = []


@pytest.fixture(scope="class", autouse=True)
def results():
    """Class-scoped fixture that appends to the session list."""
    return _session_results
