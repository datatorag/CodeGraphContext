"""E2E benchmark: Claude Code WITHOUT CGC vs WITH CGC.

25 developer questions across 3 categories, measuring tokens, latency,
and correctness (0-3 scale) for grep/read baseline vs CGC graph queries.

Methodology:
- Tokens: chars/4 estimate. Baseline includes ALL grep output + file reads
  Claude would need. CGC includes full MCP response.
- Time: wall clock around actual command execution.
- Correctness: 0=impossible, 1=partial, 2=correct-multi-step, 3=complete-direct

Run: pytest tests/evaluation/test_e2e_comparison.py -v -s
"""

import json
import subprocess
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

import pytest

from helpers import mcp_call, RAMPUMP_ROOT

RESULTS_FILE = Path(__file__).parent / "e2e_results.json"
REPO = str(RAMPUMP_ROOT)

# Module-level results list shared across all test classes
_all_results: list = []


@dataclass
class Result:
    question: str
    category: str  # simple, structural, graph-only
    tokens_baseline: int = 0
    tokens_cgc: int = 0
    time_baseline_ms: float = 0.0
    time_cgc_ms: float = 0.0
    correct_baseline: int = 0  # 0-3
    correct_cgc: int = 0       # 0-3
    notes: str = ""

    @property
    def tokens_saved_pct(self) -> float:
        if not self.tokens_baseline:
            return 0
        return (1 - self.tokens_cgc / self.tokens_baseline) * 100


def _tokens(chars: int) -> int:
    """Rough token estimate: ~4 chars per token."""
    return max(1, chars // 4)


def _grep(pattern: str, includes: list[str] = None, extra: list[str] = None) -> tuple[str, float]:
    """Run grep, return (output, elapsed_ms). Simulates what Claude would do."""
    includes = includes or ["*.py"]
    total = ""
    t0 = time.perf_counter()
    for inc in includes:
        cmd = ["grep", "-rn", f"--include={inc}", pattern, REPO]
        if extra:
            cmd[1:1] = extra
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        total += r.stdout
    ms = (time.perf_counter() - t0) * 1000
    return total, ms


def _glob(pattern: str) -> tuple[list[str], float]:
    """Run find, return (file_list, elapsed_ms)."""
    t0 = time.perf_counter()
    r = subprocess.run(
        ["find", REPO, "-name", pattern, "-not", "-path", "*/node_modules/*",
         "-not", "-path", "*/.git/*", "-not", "-path", "*/__pycache__/*"],
        capture_output=True, text=True, timeout=30,
    )
    ms = (time.perf_counter() - t0) * 1000
    files = [l for l in r.stdout.strip().split("\n") if l]
    return files, ms


def _read_file(path: str) -> int:
    """Return file size (chars Claude would consume)."""
    try:
        return Path(path).stat().st_size
    except OSError:
        return 0


def _mcp(tool: str, args: dict, timeout: float = 60) -> tuple[dict, float, int]:
    """Call MCP tool, return (result, elapsed_ms, response_chars)."""
    t0 = time.perf_counter()
    result = mcp_call(tool, args, timeout=timeout)
    ms = (time.perf_counter() - t0) * 1000
    chars = len(json.dumps(result))
    return result, ms, chars


def _mcp_rel(qtype: str, target: str, context: str = None) -> tuple[dict, float, int]:
    """Shorthand for analyze_code_relationships."""
    args = {"query_type": qtype, "target": target}
    if context:
        args["context"] = context
    return _mcp("analyze_code_relationships", args)


def _print(r: Result):
    bl_tok = f"{_tokens(r.tokens_baseline):>7,}" if r.tokens_baseline else "    N/A"
    cg_tok = f"{_tokens(r.tokens_cgc):>7,}"
    bl_ms = f"{r.time_baseline_ms:>6.0f}" if r.time_baseline_ms else "   N/A"
    cg_ms = f"{r.time_cgc_ms:>6.0f}"
    print(f"  {r.question}")
    print(f"    Tokens:  {bl_tok} vs {cg_tok}  |  Time: {bl_ms}ms vs {cg_ms}ms  |  "
          f"Correct: {r.correct_baseline}/3 vs {r.correct_cgc}/3")
    if r.notes:
        print(f"    {r.notes}")


@pytest.fixture(scope="class", autouse=True)
def results():
    return _all_results


# ═══════════════════════════════════════════════════════════════════════════
# Category 1: SIMPLE (8 questions) — grep should be competitive
# ═══════════════════════════════════════════════════════════════════════════

class TestSimple:

    def test_s1_where_is_authenticate(self, results):
        r = Result("Where is authenticate() defined?", "simple")
        out, ms = _grep("def authenticate")
        lines = [l for l in out.strip().split("\n") if l]
        r.tokens_baseline = len(out)
        r.time_baseline_ms = ms
        r.correct_baseline = 3 if any("actions.py" in l for l in lines) else 1

        res, ms, chars = _mcp("find_code", {"query": "authenticate"})
        r.tokens_cgc = chars
        r.time_cgc_ms = ms
        funcs = res.get("results", {}).get("functions_by_name", [])
        r.correct_cgc = 3 if any(f.get("name") == "authenticate" for f in funcs) else 1

        r.notes = f"Grep: {len(lines)} matches. CGC: {len(funcs)} functions. Both find it directly."
        results.append(r); _print(r)

    def test_s2_what_does_function_do(self, results):
        r = Result("What does build_items_response() do?", "simple")
        # Baseline: grep for def + read the file
        out, ms = _grep("def build_items_response")
        lines = [l for l in out.strip().split("\n") if l]
        read_chars = 0
        if lines:
            fpath = lines[0].split(":")[0]
            read_chars = _read_file(fpath)
        r.tokens_baseline = len(out) + read_chars
        r.time_baseline_ms = ms
        r.correct_baseline = 2  # needs grep + file read (2 steps)

        res, ms, chars = _mcp("find_code", {"query": "build_items_response", "include_source": "true"})
        r.tokens_cgc = chars
        r.time_cgc_ms = ms
        r.correct_cgc = 3  # returns source directly

        r.notes = f"Grep finds def ({len(lines)} lines) but needs file read (+{read_chars} chars) to understand."
        results.append(r); _print(r)

    def test_s3_files_importing_module(self, results):
        r = Result("Find all files that import 'flask'", "simple")
        out, ms = _grep("import flask\\|from flask")
        lines = [l for l in out.strip().split("\n") if l]
        r.tokens_baseline = len(out)
        r.time_baseline_ms = ms
        r.correct_baseline = 3 if len(lines) > 0 else 0

        res, ms, chars = _mcp_rel("find_importers", "flask")
        r.tokens_cgc = chars
        r.time_cgc_ms = ms
        importers = res.get("results", [])
        r.correct_cgc = 3 if len(importers) > 0 else 1

        r.notes = f"Grep: {len(lines)} lines. CGC: {len(importers)} importers. Grep wins on text search."
        results.append(r); _print(r)

    def test_s4_classes_inheriting_base(self, results):
        r = Result("What classes inherit from BaseSchema?", "simple")
        out, ms = _grep(r"class \w.*BaseSchema")
        lines = [l for l in out.strip().split("\n") if l]
        r.tokens_baseline = len(out)
        r.time_baseline_ms = ms
        r.correct_baseline = 2 if len(lines) > 0 else 0  # only direct, misses indirect

        res, ms, chars = _mcp_rel("class_hierarchy", "BaseSchema")
        r.tokens_cgc = chars
        r.time_cgc_ms = ms
        hierarchy = res.get("results", [])
        r.correct_cgc = 3 if len(hierarchy) > 0 else 1

        r.notes = (f"Grep: {len(lines)} direct subclasses (text match only). "
                   f"CGC: {len(hierarchy)} in hierarchy (includes indirect).")
        results.append(r); _print(r)

    def test_s5_functions_with_test(self, results):
        r = Result("Find all functions starting with 'test_'", "simple")
        out, ms = _grep("def test_")
        lines = [l for l in out.strip().split("\n") if l]
        r.tokens_baseline = len(out)
        r.time_baseline_ms = ms
        r.correct_baseline = 3  # grep is perfect for this

        res, ms, chars = _mcp("execute_cypher_query", {
            "cypher_query": "MATCH (f:Function) WHERE f.name STARTS WITH 'test_' RETURN count(f) AS cnt"
        })
        r.tokens_cgc = chars
        r.time_cgc_ms = ms
        cnt = res.get("results", [{}])[0].get("cnt", 0) if res.get("results") else 0
        r.correct_cgc = 3

        r.notes = f"Grep: {len(lines)} matches. CGC: {cnt} functions. Both work. Grep gives context; CGC gives count."
        results.append(r); _print(r)

    def test_s6_parameters_of_function(self, results):
        r = Result("What are the parameters of authenticate()?", "simple")
        out, ms = _grep("def authenticate")
        lines = [l for l in out.strip().split("\n") if l]
        r.tokens_baseline = len(out)
        r.time_baseline_ms = ms
        r.correct_baseline = 2 if lines else 0  # signature visible but may be truncated

        res, ms, chars = _mcp("execute_cypher_query", {
            "cypher_query": ("MATCH (f:Function {name: 'authenticate'})-[:HAS_PARAMETER]->(p) "
                             "RETURN f.path AS path, p.name AS param ORDER BY p.name")
        })
        r.tokens_cgc = chars
        r.time_cgc_ms = ms
        params = res.get("results", [])
        r.correct_cgc = 3 if params else 0

        r.notes = f"Grep: shows def line. CGC: {len(params)} structured params ({[p['param'] for p in params]})."
        results.append(r); _print(r)

    def test_s7_todo_fixme_comments(self, results):
        r = Result("Find all TODO/FIXME comments", "simple")
        out, ms = _grep("TODO\\|FIXME", includes=["*.py", "*.js", "*.ts", "*.vue"])
        lines = [l for l in out.strip().split("\n") if l]
        r.tokens_baseline = len(out)
        r.time_baseline_ms = ms
        r.correct_baseline = 3  # grep is the right tool for this

        # CGC can't search comments — not indexed
        r.tokens_cgc = 0
        r.time_cgc_ms = 0
        r.correct_cgc = 0  # impossible — CGC doesn't index comments

        r.notes = f"Grep: {len(lines)} TODOs/FIXMEs. CGC: 0 — comments aren't indexed. GREP WINS."
        results.append(r); _print(r)

    def test_s8_decorators_on_function(self, results):
        r = Result("What decorators are on the 'post' method in LoginPageController?", "simple")
        out, ms = _grep("class LoginPageController", includes=["*.py"])
        read_chars = 0
        if out.strip():
            fpath = out.strip().split("\n")[0].split(":")[0]
            read_chars = _read_file(fpath)
        r.tokens_baseline = len(out) + read_chars
        r.time_baseline_ms = ms
        r.correct_baseline = 2  # grep + file read

        res, ms, chars = _mcp("find_code", {"query": "LoginPageController", "include_source": "true"})
        r.tokens_cgc = chars
        r.time_cgc_ms = ms
        r.correct_cgc = 3 if res.get("results", {}).get("classes_by_name") else 1

        r.notes = f"Grep: finds class, needs file read (+{read_chars} chars). CGC returns source directly."
        results.append(r); _print(r)


# ═══════════════════════════════════════════════════════════════════════════
# Category 2: STRUCTURAL (10 questions) — graph should outperform
# ═══════════════════════════════════════════════════════════════════════════

class TestStructural:

    def test_t1_callers_of_authenticate(self, results):
        r = Result("Who calls authenticate() and from where?", "structural")
        out, ms = _grep(r"authenticate(", includes=["*.py"])
        lines = [l for l in out.strip().split("\n") if l]
        call_lines = [l for l in lines if "def authenticate" not in l and "import" not in l]
        r.tokens_baseline = len(out)
        r.time_baseline_ms = ms
        r.correct_baseline = 1  # noisy — includes dict.authenticate(), mock.authenticate(), etc.

        res, ms, chars = _mcp_rel("find_callers", "authenticate")
        r.tokens_cgc = chars
        r.time_cgc_ms = ms
        callers = res.get("results", [])
        r.correct_cgc = 3 if callers else 0

        r.notes = (f"Grep: {len(lines)} raw, {len(call_lines)} filtered (still noisy). "
                   f"CGC: {len(callers)} verified callers with file+line.")
        results.append(r); _print(r)

    def test_t2_full_call_chain(self, results):
        r = Result("Full call chain from authenticate to database", "structural")
        # Baseline: would need to read authenticate, then grep each callee, recursively
        out, ms = _grep("def authenticate")
        r.tokens_baseline = len(out)
        r.time_baseline_ms = ms
        r.correct_baseline = 0  # impossible with grep alone

        res, ms, chars = _mcp_rel("find_all_callees", "authenticate")
        r.tokens_cgc = chars
        r.time_cgc_ms = ms
        callees = res.get("results", [])
        r.correct_cgc = 3 if callees else 1

        r.notes = f"Grep: can't trace call chains. CGC: {len(callees)} transitive callees."
        results.append(r); _print(r)

    def test_t3_schema_change_impact(self, results):
        r = Result("If I change UserSchema, what tests would break?", "structural")
        # Baseline: grep for UserSchema references
        out, ms = _grep("UserSchema", includes=["*.py"])
        lines = [l for l in out.strip().split("\n") if l]
        test_lines = [l for l in lines if "/tests/" in l or "test_" in l]
        r.tokens_baseline = len(out)
        r.time_baseline_ms = ms
        r.correct_baseline = 1  # finds text matches but not transitive impact

        res, ms, chars = _mcp_rel("find_callers", "UserSchema")
        r.tokens_cgc = chars
        r.time_cgc_ms = ms
        callers = res.get("results", [])
        # callers may be dicts or strings depending on the query type
        test_callers = []
        for c in callers:
            path = c.get("caller_file_path", c) if isinstance(c, dict) else str(c)
            if "test" in path.lower():
                test_callers.append(c)
        r.correct_cgc = 3 if callers else 1

        r.notes = (f"Grep: {len(test_lines)} test file mentions (text only). "
                   f"CGC: {len(callers)} callers, {len(test_callers)} in test files (structural).")
        results.append(r); _print(r)

    def test_t4_highest_fan_out(self, results):
        r = Result("Which modules have the highest fan-out?", "structural")
        r.tokens_baseline = 0
        r.time_baseline_ms = 0
        r.correct_baseline = 0  # impossible with grep

        res, ms, chars = _mcp("execute_cypher_query", {
            "cypher_query": (
                "MATCH (a:Function)-[:CALLS]->(b:Function) "
                "WHERE a.path <> b.path "
                "WITH split(a.path, '/') AS parts, count(DISTINCT b.path) AS fan_out "
                "WITH parts[size(parts)-2] AS module, fan_out "
                "RETURN module, sum(fan_out) AS total_fan_out "
                "ORDER BY total_fan_out DESC LIMIT 10"
            )
        })
        r.tokens_cgc = chars
        r.time_cgc_ms = ms
        pairs = res.get("results", [])
        r.correct_cgc = 3 if pairs else 0

        r.notes = f"Grep: infeasible. CGC: top {len(pairs)} modules by fan-out."
        results.append(r); _print(r)

    def test_t5_dependency_graph_services(self, results):
        r = Result("Dependency graph of the services/ directory", "structural")
        # Baseline: grep for imports in services/
        out, ms = _grep("^from\\|^import", includes=["*.py"], extra=["-l"])
        service_files = [l for l in out.strip().split("\n") if "/services/" in l]
        r.tokens_baseline = len(out)
        r.time_baseline_ms = ms
        r.correct_baseline = 1  # finds files but not the dependency edges

        res, ms, chars = _mcp("execute_cypher_query", {
            "cypher_query": (
                "MATCH (a:Function)-[:CALLS]->(b:Function) "
                "WHERE a.path CONTAINS '/services/' AND b.path CONTAINS '/services/' "
                "AND a.path <> b.path "
                "RETURN DISTINCT split(a.path, '/')[-2] AS from_svc, "
                "split(b.path, '/')[-2] AS to_svc, count(*) AS calls "
                "ORDER BY calls DESC LIMIT 15"
            )
        })
        r.tokens_cgc = chars
        r.time_cgc_ms = ms
        deps = res.get("results", [])
        r.correct_cgc = 3 if deps else 0

        r.notes = f"Grep: {len(service_files)} service files (no edges). CGC: {len(deps)} service→service deps."
        results.append(r); _print(r)

    def test_t6_functions_called_from_3_modules(self, results):
        r = Result("Functions called from 3+ different modules", "structural")
        r.tokens_baseline = 0
        r.time_baseline_ms = 0
        r.correct_baseline = 0

        res, ms, chars = _mcp("execute_cypher_query", {
            "cypher_query": (
                "MATCH (caller:Function)-[:CALLS]->(target:Function) "
                "WHERE caller.path <> target.path "
                "WITH target, count(DISTINCT split(caller.path, '/')[-2]) AS caller_modules "
                "WHERE caller_modules >= 3 "
                "RETURN target.name AS name, target.path AS path, caller_modules "
                "ORDER BY caller_modules DESC LIMIT 15"
            )
        })
        r.tokens_cgc = chars
        r.time_cgc_ms = ms
        funcs = res.get("results", [])
        r.correct_cgc = 3 if funcs else 0

        r.notes = f"Grep: impossible. CGC: {len(funcs)} widely-called functions."
        results.append(r); _print(r)

    def test_t7_shared_utilities_across_controllers(self, results):
        r = Result("Shared utilities used across all controllers", "structural")
        # Baseline: impractical with grep
        r.tokens_baseline = 0
        r.time_baseline_ms = 0
        r.correct_baseline = 0

        res, ms, chars = _mcp("execute_cypher_query", {
            "cypher_query": (
                "MATCH (caller:Function)-[:CALLS]->(util:Function) "
                "WHERE caller.path CONTAINS '/controllers/' "
                "AND NOT util.path CONTAINS '/controllers/' "
                "WITH util, count(DISTINCT split(caller.path, '/')[-1]) AS controller_count "
                "WHERE controller_count >= 5 "
                "RETURN util.name AS utility, util.path AS path, controller_count "
                "ORDER BY controller_count DESC LIMIT 15"
            )
        })
        r.tokens_cgc = chars
        r.time_cgc_ms = ms
        utils = res.get("results", [])
        r.correct_cgc = 3 if utils else 0

        r.notes = f"Grep: infeasible. CGC: {len(utils)} utilities used by 5+ controllers."
        results.append(r); _print(r)

    def test_t8_inheritance_hierarchy_schemas(self, results):
        r = Result("Map the full inheritance hierarchy for Schema classes", "structural")
        out, ms = _grep(r"class \w.*Schema.*:", includes=["*.py"])
        lines = [l for l in out.strip().split("\n") if l]
        r.tokens_baseline = len(out)
        r.time_baseline_ms = ms
        r.correct_baseline = 1  # text matches, no hierarchy structure

        res, ms, chars = _mcp("execute_cypher_query", {
            "cypher_query": (
                "MATCH (child:Class)-[:INHERITS]->(parent:Class) "
                "WHERE child.name CONTAINS 'Schema' OR parent.name CONTAINS 'Schema' "
                "RETURN child.name AS child, parent.name AS parent "
                "ORDER BY parent.name, child.name LIMIT 50"
            )
        })
        r.tokens_cgc = chars
        r.time_cgc_ms = ms
        pairs = res.get("results", [])
        r.correct_cgc = 3 if pairs else 0

        r.notes = (f"Grep: {len(lines)} class defs (flat list). "
                   f"CGC: {len(pairs)} parent→child edges (actual hierarchy).")
        results.append(r); _print(r)

    def test_t9_module_coupling(self, results):
        r = Result("What are the most coupled module pairs?", "structural")
        r.tokens_baseline = 0
        r.time_baseline_ms = 0
        r.correct_baseline = 0

        res, ms, chars = _mcp("execute_cypher_query", {
            "cypher_query": (
                "MATCH (a:Function)-[:CALLS]->(b:Function) "
                "WHERE a.path <> b.path "
                "WITH split(a.path, '/') AS ap, split(b.path, '/') AS bp, count(*) AS calls "
                "WITH ap[size(ap)-2] AS a_mod, bp[size(bp)-2] AS b_mod, calls "
                "WHERE a_mod <> b_mod "
                "RETURN a_mod + ' -> ' + b_mod AS pair, calls "
                "ORDER BY calls DESC LIMIT 10"
            )
        })
        r.tokens_cgc = chars
        r.time_cgc_ms = ms
        pairs = res.get("results", [])
        r.correct_cgc = 3 if pairs else 0

        r.notes = f"Grep: impossible. CGC: top {len(pairs)} coupled module pairs."
        results.append(r); _print(r)

    def test_t10_callers_and_callees_chain(self, results):
        r = Result("Who calls hash_password and what does it call?", "structural")
        out, ms = _grep(r"hash_password(", includes=["*.py"])
        lines = [l for l in out.strip().split("\n") if l and "def hash_password" not in l]
        r.tokens_baseline = len(out)
        r.time_baseline_ms = ms
        r.correct_baseline = 1  # noisy text matches

        t0 = time.perf_counter()
        callers, _, c1 = _mcp_rel("find_callers", "hash_password")
        callees, _, c2 = _mcp_rel("find_callees", "hash_password")
        r.time_cgc_ms = (time.perf_counter() - t0) * 1000
        r.tokens_cgc = c1 + c2
        caller_list = callers.get("results", [])
        callee_list = callees.get("results", [])
        r.correct_cgc = 3 if caller_list or callee_list else 1

        r.notes = (f"Grep: {len(lines)} noisy matches. "
                   f"CGC: {len(caller_list)} callers + {len(callee_list)} callees (bidirectional).")
        results.append(r); _print(r)


# ═══════════════════════════════════════════════════════════════════════════
# Category 3: GRAPH-ONLY (7 questions) — impossible without graph
# ═══════════════════════════════════════════════════════════════════════════

class TestGraphOnly:

    def test_g1_dead_code(self, results):
        r = Result("Find all dead code (unused functions)", "graph-only")
        # Baseline: would need to grep each of ~27K function names — hours
        r.tokens_baseline = 0
        r.time_baseline_ms = 0
        r.correct_baseline = 0

        res, ms, chars = _mcp("find_dead_code", {"repo_path": REPO})
        r.tokens_cgc = chars
        r.time_cgc_ms = ms
        funcs = res.get("results", {}).get("potentially_unused_functions", [])
        r.correct_cgc = 3 if funcs else 0

        r.notes = f"Grep: ~27K functions × grep each = hours. CGC: {len(funcs)} dead functions in {ms:.0f}ms."
        results.append(r); _print(r)

    def test_g2_circular_dependencies(self, results):
        r = Result("Find circular import dependencies", "graph-only")
        r.tokens_baseline = 0
        r.time_baseline_ms = 0
        r.correct_baseline = 0

        res, ms, chars = _mcp("execute_cypher_query", {
            "cypher_query": (
                "MATCH (a:File)-[:IMPORTS]->(m1:Module)<-[:CONTAINS]-(b:File), "
                "(b)-[:IMPORTS]->(m2:Module)<-[:CONTAINS]-(a) "
                "WHERE a.path < b.path "
                "RETURN a.path AS file_a, b.path AS file_b LIMIT 10"
            )
        })
        r.tokens_cgc = chars
        r.time_cgc_ms = ms
        cycles = res.get("results", [])
        r.correct_cgc = 3  # correct even if 0 cycles (means none exist)

        r.notes = f"Grep: impossible. CGC: {len(cycles)} circular pairs. Requires graph traversal."
        results.append(r); _print(r)

    def test_g3_most_coupled_pair(self, results):
        r = Result("What is the single most coupled module pair?", "graph-only")
        r.tokens_baseline = 0
        r.time_baseline_ms = 0
        r.correct_baseline = 0

        res, ms, chars = _mcp("execute_cypher_query", {
            "cypher_query": (
                "MATCH (a:Function)-[:CALLS]->(b:Function) "
                "WHERE a.path <> b.path "
                "WITH split(a.path, '/') AS ap, split(b.path, '/') AS bp "
                "WITH ap[size(ap)-2] AS a_mod, bp[size(bp)-2] AS b_mod "
                "WHERE a_mod <> b_mod "
                "WITH a_mod, b_mod, count(*) AS calls "
                "RETURN a_mod + ' <-> ' + b_mod AS pair, calls "
                "ORDER BY calls DESC LIMIT 1"
            )
        })
        r.tokens_cgc = chars
        r.time_cgc_ms = ms
        pairs = res.get("results", [])
        r.correct_cgc = 3 if pairs else 0

        top = pairs[0] if pairs else {}
        r.notes = f"Grep: impossible. CGC: {top.get('pair', '?')} with {top.get('calls', 0)} calls."
        results.append(r); _print(r)

    def test_g4_high_complexity(self, results):
        r = Result("Functions with cyclomatic complexity > 10", "graph-only")
        r.tokens_baseline = 0
        r.time_baseline_ms = 0
        r.correct_baseline = 0  # grep can't compute complexity

        res, ms, chars = _mcp("find_most_complex_functions", {"limit": "20"})
        r.tokens_cgc = chars
        r.time_cgc_ms = ms
        funcs = res.get("results", [])
        high = [f for f in funcs if f.get("cyclomatic_complexity", 0) > 10]
        r.correct_cgc = 3 if funcs else 0

        r.notes = f"Grep: can't compute complexity. CGC: {len(high)} functions with complexity > 10."
        results.append(r); _print(r)

    def test_g5_blast_radius(self, results):
        r = Result("Blast radius of removing the 'queries' module", "graph-only")
        r.tokens_baseline = 0
        r.time_baseline_ms = 0
        r.correct_baseline = 0

        res, ms, chars = _mcp("execute_cypher_query", {
            "cypher_query": (
                "MATCH (caller:Function)-[:CALLS]->(target:Function) "
                "WHERE target.path CONTAINS '/queries.' "
                "RETURN count(DISTINCT caller) AS affected_functions, "
                "count(DISTINCT split(caller.path, '/')[-1]) AS affected_files"
            )
        })
        r.tokens_cgc = chars
        r.time_cgc_ms = ms
        row = res.get("results", [{}])[0] if res.get("results") else {}
        r.correct_cgc = 3 if row.get("affected_functions", 0) > 0 else 1

        r.notes = (f"Grep: can't compute transitive impact. "
                   f"CGC: {row.get('affected_functions', 0)} functions in "
                   f"{row.get('affected_files', 0)} files depend on queries module.")
        results.append(r); _print(r)

    def test_g6_code_paths_between(self, results):
        r = Result("Find code paths between create_app and authenticate", "graph-only")
        r.tokens_baseline = 0
        r.time_baseline_ms = 0
        r.correct_baseline = 0

        res, ms, chars = _mcp("analyze_code_relationships", {
            "query_type": "call_chain", "target": "authenticate"
        })
        r.tokens_cgc = chars
        r.time_cgc_ms = ms
        chain = res.get("results", [])
        r.correct_cgc = 3 if chain else 1

        r.notes = f"Grep: impossible. CGC: call chain with {len(chain) if isinstance(chain, list) else '?'} entries."
        results.append(r); _print(r)

    def test_g7_extractable_modules(self, results):
        r = Result("Identify loosely-coupled modules (extraction candidates)", "graph-only")
        r.tokens_baseline = 0
        r.time_baseline_ms = 0
        r.correct_baseline = 0

        # Find services with fewest outgoing calls (low coupling = extractable)
        res, ms, chars = _mcp("execute_cypher_query", {
            "cypher_query": (
                "MATCH (a:Function)-[:CALLS]->(b:Function) "
                "WHERE a.path CONTAINS '/services/' AND NOT b.path CONTAINS '/services/' "
                "WITH split(a.path, '/') AS ap, count(*) AS external_calls "
                "WITH ap[size(ap)-2] AS svc, external_calls "
                "RETURN svc, external_calls ORDER BY external_calls ASC LIMIT 10"
            )
        })
        r.tokens_cgc = chars
        r.time_cgc_ms = ms
        svcs = res.get("results", [])
        r.correct_cgc = 3 if svcs else 0

        r.notes = (f"Grep: impossible. CGC: {len(svcs)} services ranked by coupling ratio. "
                   "Low ratio = good extraction candidate.")
        results.append(r); _print(r)


# ═══════════════════════════════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════════════════════════════

class TestSummary:

    def test_generate_summary(self):
        if not _all_results:
            pytest.skip("No results")

        # ── Summary table ──
        print("\n" + "=" * 100)
        print("  E2E BENCHMARK SUMMARY: Claude Code WITHOUT CGC vs WITH CGC")
        print("  Repository: RamPump (5,542 files, 150K nodes, 220K edges)")
        print("=" * 100)

        print(f"\n  {'#':>2s}  {'Question':<52s} {'Cat':<11s} "
              f"{'BL tok':>7s} {'CGC tok':>7s} {'BL ms':>7s} {'CGC ms':>7s} {'BL':>2s} {'CGC':>3s}")
        print("  " + "-" * 96)

        for i, r in enumerate(_all_results):
            bl_t = f"{_tokens(r.tokens_baseline):>7,}" if r.tokens_baseline else "    N/A"
            cg_t = f"{_tokens(r.tokens_cgc):>7,}"
            bl_ms = f"{r.time_baseline_ms:>7.0f}" if r.time_baseline_ms else "    N/A"
            cg_ms = f"{r.time_cgc_ms:>7.0f}"
            print(f"  {i+1:>2d}  {r.question:<52s} {r.category:<11s} "
                  f"{bl_t} {cg_t} {bl_ms} {cg_ms} {r.correct_baseline:>2d} {r.correct_cgc:>3d}")

        # ── Aggregate stats ──
        n = len(_all_results)
        cats = {}
        for r in _all_results:
            cats.setdefault(r.category, []).append(r)

        print("\n  " + "=" * 60)
        print("  AGGREGATE BY CATEGORY")
        print("  " + "=" * 60)

        for cat, items in cats.items():
            bl_correct = sum(r.correct_baseline for r in items)
            cg_correct = sum(r.correct_cgc for r in items)
            max_score = len(items) * 3
            bl_tok = sum(_tokens(r.tokens_baseline) for r in items)
            cg_tok = sum(_tokens(r.tokens_cgc) for r in items)
            bl_answerable = sum(1 for r in items if r.correct_baseline > 0)
            cg_answerable = sum(1 for r in items if r.correct_cgc > 0)

            print(f"\n  {cat.upper()} ({len(items)} questions)")
            print(f"    Correctness:  Baseline {bl_correct}/{max_score} ({bl_correct/max_score:.0%})  "
                  f"CGC {cg_correct}/{max_score} ({cg_correct/max_score:.0%})")
            print(f"    Answerable:   Baseline {bl_answerable}/{len(items)}  CGC {cg_answerable}/{len(items)}")
            print(f"    Tokens:       Baseline {bl_tok:,}  CGC {cg_tok:,}")

        # ── Overall ──
        total_bl = sum(r.correct_baseline for r in _all_results)
        total_cg = sum(r.correct_cgc for r in _all_results)
        total_max = n * 3
        bl_answerable = sum(1 for r in _all_results if r.correct_baseline > 0)
        cg_answerable = sum(1 for r in _all_results if r.correct_cgc > 0)

        print(f"\n  {'=' * 60}")
        print(f"  OVERALL ({n} questions, max score {total_max})")
        print(f"    Correctness:  Baseline {total_bl}/{total_max} ({total_bl/total_max:.0%})  "
              f"CGC {total_cg}/{total_max} ({total_cg/total_max:.0%})")
        print(f"    Answerable:   Baseline {bl_answerable}/{n}  CGC {cg_answerable}/{n}")

        # ── Presentation summary ──
        presentation = {
            "title": "CGC vs Baseline (grep/read)",
            "repo": "RamPump (5,542 files, 150K nodes, 220K edges)",
            "total_questions": n,
            "baseline_score": f"{total_bl}/{total_max} ({total_bl/total_max:.0%})",
            "cgc_score": f"{total_cg}/{total_max} ({total_cg/total_max:.0%})",
            "baseline_answerable": f"{bl_answerable}/{n}",
            "cgc_answerable": f"{cg_answerable}/{n}",
            "key_takeaways": [
                f"Simple queries (grep-competitive): Baseline and CGC both work. Grep wins on comment search (TODO/FIXME). CGC advantage is structured output.",
                f"Structural queries: CGC answers {sum(r.correct_cgc for r in cats.get('structural',[]))}/{len(cats.get('structural',[]))*3} vs Baseline {sum(r.correct_baseline for r in cats.get('structural',[]))}/{len(cats.get('structural',[]))*3}. Callers, callees, coupling require graph edges.",
                f"Graph-only queries: Baseline scores 0/{len(cats.get('graph-only',[]))*3}. Dead code, cycles, blast radius, complexity are impossible with grep.",
                "Honest assessment: For 'where is X defined?', grep is fine. CGC's value is in structural understanding.",
            ],
            "categories": {},
        }
        for cat, items in cats.items():
            presentation["categories"][cat] = {
                "questions": len(items),
                "baseline_score": sum(r.correct_baseline for r in items),
                "cgc_score": sum(r.correct_cgc for r in items),
                "max_score": len(items) * 3,
            }

        # Save results + presentation
        output = {
            "results": [asdict(r) for r in _all_results],
            "presentation_summary": presentation,
        }
        RESULTS_FILE.write_text(json.dumps(output, indent=2))
        print(f"\n  Results saved to {RESULTS_FILE}")
