#!/usr/bin/env python3
"""LLM-as-judge blind evaluation of E2E benchmark results.

Re-runs each baseline (grep) and CGC (MCP) query, captures actual output,
randomizes A/B assignment, sends to Claude CLI for blind scoring, then
de-blinds and tallies results.

Usage: python tests/evaluation/run_llm_judge.py
"""

import json
import random
import subprocess
import time
from pathlib import Path

REPO = "/Users/myang/git/RamPump"
MCP_URL = "http://localhost:47321/mcp"
RESULTS_FILE = Path(__file__).parent / "e2e_results.json"


def _grep(pattern, includes=None, extra=None):
    includes = includes or ["*.py"]
    total = ""
    for inc in includes:
        cmd = ["grep", "-rn", f"--include={inc}", pattern, REPO]
        if extra:
            cmd[1:1] = extra
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        total += r.stdout
    return total.strip()


def _mcp(tool, args, timeout=60):
    import urllib.request
    payload = json.dumps({
        "jsonrpc": "2.0", "method": "tools/call", "id": 1,
        "params": {"name": tool, "arguments": args}
    }).encode()
    req = urllib.request.Request(MCP_URL, data=payload,
                                headers={"Content-Type": "application/json"})
    resp = json.loads(urllib.request.urlopen(req, timeout=timeout).read())
    if "error" in resp and resp["error"]:
        return {"error": str(resp["error"])}
    text = resp["result"]["content"][0]["text"]
    return json.loads(text)


def _mcp_rel(qtype, target):
    """Call analyze_code_relationships and unwrap the double-nested results."""
    raw = _mcp("analyze_code_relationships", {"query_type": qtype, "target": target})
    # Response is {results: {query_type, target, results: [...], summary}}
    inner = raw.get("results", {})
    if isinstance(inner, dict):
        return inner.get("results", inner)
    return inner


def _truncate(text, max_chars=2000):
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n... [{len(text) - max_chars} chars truncated]"


def _ask_claude(prompt, timeout=60):
    result = subprocess.run(
        ["claude", "-p", prompt, "--output-format", "text"],
        capture_output=True, text=True, timeout=timeout,
    )
    text = result.stdout.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    return text


# ── Define all 25 questions with their query functions ──

QUESTIONS = [
    # Simple (8)
    {
        "question": "Where is authenticate() defined?",
        "category": "simple",
        "baseline": lambda: _grep("def authenticate"),
        "cgc": lambda: json.dumps(_mcp("find_code", {"query": "authenticate"})
                                  .get("results", {}).get("functions_by_name", []), indent=2),
        "ground_truth": "authenticate() is defined in webapp/services/user/actions.py around line 65.",
    },
    {
        "question": "What does build_items_response() do?",
        "category": "simple",
        "baseline": lambda: _grep("def build_items_response"),
        "cgc": lambda: json.dumps(_mcp("find_code", {"query": "build_items_response", "include_source": "true"})
                                  .get("results", {}).get("functions_by_name", [])[:3], indent=2),
        "ground_truth": "build_items_response() is a method defined in multiple controller classes that builds the API response for list endpoints, typically formatting items with pagination.",
    },
    {
        "question": "Find all files that import 'flask'",
        "category": "simple",
        "baseline": lambda: _grep("import flask\\|from flask"),
        "cgc": lambda: json.dumps(_mcp_rel("find_importers", "flask"), indent=2),
        "ground_truth": "Multiple files import flask — primarily in webapp/ directory. Both import styles should be found.",
    },
    {
        "question": "What classes inherit from BaseSchema?",
        "category": "simple",
        "baseline": lambda: _grep(r"class \w.*BaseSchema"),
        "cgc": lambda: json.dumps(_mcp_rel("class_hierarchy", "BaseSchema"), indent=2),
        "ground_truth": "BaseSchema has many direct subclasses in webapp/schemas/. A complete answer includes both direct and indirect inheritance.",
    },
    {
        "question": "Find all functions starting with 'test_'",
        "category": "simple",
        "baseline": lambda: f"{len([l for l in _grep('def test_').split(chr(10)) if l])} matches found via grep",
        "cgc": lambda: json.dumps(_mcp("execute_cypher_query", {
            "cypher_query": "MATCH (f:Function) WHERE f.name STARTS WITH 'test_' RETURN count(f) AS cnt"
        }).get("results", []), indent=2),
        "ground_truth": "There are approximately 5,000+ test functions across the test directories.",
    },
    {
        "question": "What are the parameters of authenticate()?",
        "category": "simple",
        "baseline": lambda: _grep("def authenticate"),
        "cgc": lambda: json.dumps(_mcp("execute_cypher_query", {
            "cypher_query": "MATCH (f:Function {name: 'authenticate'})-[:HAS_PARAMETER]->(p) RETURN f.path AS path, p.name AS param"
        }).get("results", []), indent=2),
        "ground_truth": "authenticate() takes two parameters: email and password.",
    },
    {
        "question": "Find all TODO/FIXME comments",
        "category": "simple",
        "baseline": lambda: f"{len([l for l in _grep('TODO\\|FIXME', includes=['*.py', '*.js', '*.ts', '*.vue']).split(chr(10)) if l])} TODO/FIXME comments found",
        "cgc": lambda: "CGC does not index comments. Unable to search for TODO/FIXME.",
        "ground_truth": "There are thousands of TODO/FIXME comments. This requires text search of comments, not code structure.",
    },
    {
        "question": "What decorators are used on LoginPageController?",
        "category": "simple",
        "baseline": lambda: _grep("class LoginPageController"),
        "cgc": lambda: json.dumps(_mcp("find_code", {"query": "LoginPageController", "include_source": "true"})
                                  .get("results", {}).get("classes_by_name", [])[:2], indent=2),
        "ground_truth": "LoginPageController is a class in webapp/controllers/. Its source shows any applied decorators.",
    },
    # Structural (10)
    {
        "question": "Who calls authenticate() and from where?",
        "category": "structural",
        "baseline": lambda: _grep(r"authenticate(", includes=["*.py"]),
        "cgc": lambda: json.dumps(_mcp_rel("find_callers", "authenticate"), indent=2),
        "ground_truth": "authenticate() is called from several controller files: access_token.py, change_password.py, change_email.py, confirm_password.py, and unlock_account.py.",
    },
    {
        "question": "Full call chain from authenticate to its callees",
        "category": "structural",
        "baseline": lambda: _grep("def authenticate"),
        "cgc": lambda: json.dumps(_mcp_rel("find_all_callees", "authenticate"), indent=2),
        "ground_truth": "authenticate() calls into user query functions (by_email), password hashing, and account validation. A complete answer traces the full call tree.",
    },
    {
        "question": "If I change UserSchema, what code would be affected?",
        "category": "structural",
        "baseline": lambda: _grep("UserSchema", includes=["*.py"]),
        "cgc": lambda: json.dumps(_mcp_rel("find_callers", "UserSchema"), indent=2),
        "ground_truth": "UserSchema is referenced in controllers, services, and tests. A structural answer identifies which functions actually use it, not just text mentions.",
    },
    {
        "question": "Which modules have the highest fan-out?",
        "category": "structural",
        "baseline": lambda: "(grep would require parsing all files and aggregating call counts — hours of scripting)",
        "cgc": lambda: json.dumps(_mcp("execute_cypher_query", {
            "cypher_query": "MATCH (a:Function)-[:CALLS]->(b:Function) WHERE a.path <> b.path WITH split(a.path, '/') AS parts, count(DISTINCT b.path) AS fan_out WITH parts[size(parts)-2] AS module, fan_out RETURN module, sum(fan_out) AS total_fan_out ORDER BY total_fan_out DESC LIMIT 10"
        }).get("results", []), indent=2),
        "ground_truth": "Fan-out measures how many other modules a module calls into. Requires counting cross-module CALLS edges.",
    },
    {
        "question": "Dependency graph of the services/ directory",
        "category": "structural",
        "baseline": lambda: f"{len([l for l in _grep('^from\\|^import', includes=['*.py'], extra=['-l']).split(chr(10)) if '/services/' in l])} service files with imports",
        "cgc": lambda: json.dumps(_mcp("execute_cypher_query", {
            "cypher_query": "MATCH (a:Function)-[:CALLS]->(b:Function) WHERE a.path CONTAINS '/services/' AND b.path CONTAINS '/services/' AND a.path <> b.path RETURN DISTINCT split(a.path, '/')[-2] AS from_svc, split(b.path, '/')[-2] AS to_svc, count(*) AS calls ORDER BY calls DESC LIMIT 15"
        }).get("results", []), indent=2),
        "ground_truth": "The services/ directory has internal dependencies. A complete answer shows which service modules call which other service modules.",
    },
    {
        "question": "Functions called from 3+ different modules",
        "category": "structural",
        "baseline": lambda: "(grep would need to grep each function name then count unique calling directories)",
        "cgc": lambda: json.dumps(_mcp("execute_cypher_query", {
            "cypher_query": "MATCH (caller:Function)-[:CALLS]->(target:Function) WHERE caller.path <> target.path WITH target, count(DISTINCT split(caller.path, '/')[-2]) AS caller_modules WHERE caller_modules >= 3 RETURN target.name AS name, target.path AS path, caller_modules ORDER BY caller_modules DESC LIMIT 15"
        }).get("results", []), indent=2),
        "ground_truth": "Widely-called functions are used across 3+ different directory modules. These are core utilities or shared abstractions.",
    },
    {
        "question": "Shared utilities used across all controllers",
        "category": "structural",
        "baseline": lambda: "(grep would need to cross-reference all controller imports — many hours for 5K+ files)",
        "cgc": lambda: json.dumps(_mcp("execute_cypher_query", {
            "cypher_query": "MATCH (caller:Function)-[:CALLS]->(util:Function) WHERE caller.path CONTAINS '/controllers/' AND NOT util.path CONTAINS '/controllers/' WITH util, count(DISTINCT split(caller.path, '/')[-1]) AS controller_count WHERE controller_count >= 5 RETURN util.name AS utility, util.path AS path, controller_count ORDER BY controller_count DESC LIMIT 15"
        }).get("results", []), indent=2),
        "ground_truth": "Shared utilities are non-controller functions called by 5+ different controller files.",
    },
    {
        "question": "Map the inheritance hierarchy for Schema classes",
        "category": "structural",
        "baseline": lambda: _truncate(_grep(r"class \w.*Schema.*:", includes=["*.py"]), 1500),
        "cgc": lambda: json.dumps(_mcp("execute_cypher_query", {
            "cypher_query": "MATCH (child:Class)-[:INHERITS]->(parent:Class) WHERE child.name CONTAINS 'Schema' OR parent.name CONTAINS 'Schema' RETURN child.name AS child, parent.name AS parent ORDER BY parent.name, child.name LIMIT 50"
        }).get("results", []), indent=2),
        "ground_truth": "Schema classes form a hierarchy with BaseSchema at the root and many domain-specific schemas inheriting from it. A complete answer shows parent→child edges.",
    },
    {
        "question": "What are the most coupled module pairs?",
        "category": "structural",
        "baseline": lambda: "(grep would need to parse all imports and count cross-module calls — hours of scripting)",
        "cgc": lambda: json.dumps(_mcp("execute_cypher_query", {
            "cypher_query": "MATCH (a:Function)-[:CALLS]->(b:Function) WHERE a.path <> b.path WITH split(a.path, '/') AS ap, split(b.path, '/') AS bp WITH ap[size(ap)-2] AS a_mod, bp[size(bp)-2] AS b_mod WHERE a_mod <> b_mod WITH a_mod, b_mod, count(*) AS calls RETURN a_mod + ' -> ' + b_mod AS pair, calls ORDER BY calls DESC LIMIT 10"
        }).get("results", []), indent=2),
        "ground_truth": "Module coupling is measured by cross-module CALLS edges. The most coupled pairs have hundreds of calls between them.",
    },
    {
        "question": "Who calls hash_password and what does it call?",
        "category": "structural",
        "baseline": lambda: _grep(r"hash_password(", includes=["*.py"]),
        "cgc": lambda: json.dumps({
            "callers": _mcp_rel("find_callers", "hash_password"),
            "callees": _mcp_rel("find_callees", "hash_password"),
        }, indent=2),
        "ground_truth": "hash_password has specific callers (user creation/update code) and calls into hashing libraries. A complete answer shows both directions.",
    },
    # Graph-only (7)
    {
        "question": "Find all dead code (unused functions)",
        "category": "graph-only",
        "baseline": lambda: "(requires checking each of ~27K functions for callers — hours of grep)",
        "cgc": lambda: json.dumps(_mcp("find_dead_code", {"repo_path": REPO})
                                  .get("results", {}).get("potentially_unused_functions", [])[:10], indent=2),
        "ground_truth": "Dead code = functions with zero incoming CALLS edges (excluding test functions, entry points, and framework-registered handlers). Requires graph analysis.",
    },
    {
        "question": "Find circular import dependencies",
        "category": "graph-only",
        "baseline": lambda: "(grep could cross-reference imports but slow and error-prone for 5K+ files)",
        "cgc": lambda: json.dumps(_mcp("execute_cypher_query", {
            "cypher_query": "MATCH (a:Function)-[:CALLS]->(b:Function) WHERE a.path <> b.path WITH a.path AS fa, b.path AS fb MATCH (c:Function)-[:CALLS]->(d:Function) WHERE c.path = fb AND d.path = fa AND c.path < d.path RETURN DISTINCT c.path AS file_a, d.path AS file_b LIMIT 10"
        }).get("results", []), indent=2),
        "ground_truth": "Circular dependencies are file pairs where functions in A call functions in B and vice versa. Requires graph cycle detection.",
    },
    {
        "question": "What is the most coupled module pair?",
        "category": "graph-only",
        "baseline": lambda: "(grep would need same aggregation as fan-out question)",
        "cgc": lambda: json.dumps(_mcp("execute_cypher_query", {
            "cypher_query": "MATCH (a:Function)-[:CALLS]->(b:Function) WHERE a.path <> b.path WITH split(a.path, '/') AS ap, split(b.path, '/') AS bp WITH ap[size(ap)-2] AS a_mod, bp[size(bp)-2] AS b_mod WHERE a_mod <> b_mod WITH a_mod, b_mod, count(*) AS calls RETURN a_mod + ' <-> ' + b_mod AS pair, calls ORDER BY calls DESC LIMIT 1"
        }).get("results", []), indent=2),
        "ground_truth": "The most coupled pair has the highest number of cross-module CALLS edges.",
    },
    {
        "question": "Functions with highest cyclomatic complexity",
        "category": "graph-only",
        "baseline": lambda: "(requires AST parsing — tools like radon/pylint can do this, but not grep)",
        "cgc": lambda: json.dumps(_mcp("find_most_complex_functions", {"limit": "10"}).get("results", [])[:5], indent=2),
        "ground_truth": "Cyclomatic complexity counts independent code paths. High complexity = hard to test and maintain.",
    },
    {
        "question": "Blast radius of removing the 'queries' module",
        "category": "graph-only",
        "baseline": lambda: "(grep would need recursive caller tracing — many hops, many grep calls)",
        "cgc": lambda: json.dumps(_mcp("execute_cypher_query", {
            "cypher_query": "MATCH (caller:Function)-[:CALLS]->(target:Function) WHERE target.path CONTAINS '/queries.' RETURN count(DISTINCT caller) AS affected_functions, count(DISTINCT split(caller.path, '/')[-1]) AS affected_files"
        }).get("results", []), indent=2),
        "ground_truth": "Blast radius = all functions that directly or transitively call into the queries module. Requires traversing CALLS edges.",
    },
    {
        "question": "Find code paths between create_app and authenticate",
        "category": "graph-only",
        "baseline": lambda: "(grep would need to read each file in the chain sequentially)",
        "cgc": lambda: json.dumps(_mcp_rel("call_chain", "authenticate"), indent=2),
        "ground_truth": "A call chain traces the path from one function to another through intermediate CALLS edges.",
    },
    {
        "question": "Identify loosely-coupled services (extraction candidates)",
        "category": "graph-only",
        "baseline": lambda: "(grep would need to parse imports + count external calls per service — hours)",
        "cgc": lambda: json.dumps(_mcp("execute_cypher_query", {
            "cypher_query": "MATCH (a:Function)-[:CALLS]->(b:Function) WHERE a.path CONTAINS '/services/' AND NOT b.path CONTAINS '/services/' WITH split(a.path, '/') AS ap, count(*) AS external_calls WITH ap[size(ap)-2] AS svc, external_calls RETURN svc, external_calls ORDER BY external_calls ASC LIMIT 10"
        }).get("results", []), indent=2),
        "ground_truth": "Services with few external calls are loosely coupled and good candidates for extraction into separate packages.",
    },
]


def run_judge():
    print(f"Running LLM-as-judge blind evaluation on {len(QUESTIONS)} questions...")
    print(f"Each question takes ~15-20s (Claude CLI call)\n")

    verdicts = []

    for i, q in enumerate(QUESTIONS):
        print(f"[{i+1:2d}/{len(QUESTIONS)}] {q['question'][:60]}...", end=" ", flush=True)

        # Get actual outputs
        try:
            baseline_output = _truncate(q["baseline"](), 1500)
        except Exception as e:
            baseline_output = f"(error: {e})"

        try:
            cgc_output = _truncate(q["cgc"](), 1500)
        except Exception as e:
            cgc_output = f"(error: {e})"

        # Randomize A/B assignment
        cgc_is_a = random.choice([True, False])
        if cgc_is_a:
            answer_a, answer_b = cgc_output, baseline_output
        else:
            answer_a, answer_b = baseline_output, cgc_output

        prompt = f"""You are a code analysis expert judging two approaches to answering a developer question about a large Python/JS codebase (5,500+ files).

QUESTION: {q['question']}

GROUND TRUTH: {q['ground_truth']}

ANSWER A:
{answer_a}

ANSWER B:
{answer_b}

Score each answer on a 0-3 scale:
  0 = wrong, impossible, or no useful answer
  1 = partial — found something but missed important results
  2 = correct but incomplete or required interpretation
  3 = complete, accurate, and directly answers the question

Respond with ONLY this JSON (no markdown, no explanation):
{{"score_a": <0-3>, "score_b": <0-3>, "reasoning_a": "<one sentence>", "reasoning_b": "<one sentence>", "winner": "a" or "b" or "tie"}}"""

        try:
            response = _ask_claude(prompt, timeout=45)
            verdict = json.loads(response)
        except (json.JSONDecodeError, subprocess.TimeoutExpired) as e:
            verdict = {"score_a": -1, "score_b": -1, "reasoning_a": f"parse error: {e}",
                       "reasoning_b": "", "winner": "error"}

        # De-blind
        if cgc_is_a:
            score_cgc = verdict.get("score_a", -1)
            score_baseline = verdict.get("score_b", -1)
            reasoning_cgc = verdict.get("reasoning_a", "")
            reasoning_baseline = verdict.get("reasoning_b", "")
        else:
            score_cgc = verdict.get("score_b", -1)
            score_baseline = verdict.get("score_a", -1)
            reasoning_cgc = verdict.get("reasoning_b", "")
            reasoning_baseline = verdict.get("reasoning_a", "")

        winner_raw = verdict.get("winner", "error")
        if winner_raw == "a":
            winner = "cgc" if cgc_is_a else "baseline"
        elif winner_raw == "b":
            winner = "baseline" if cgc_is_a else "cgc"
        else:
            winner = winner_raw

        entry = {
            "question": q["question"],
            "category": q["category"],
            "score_baseline": score_baseline,
            "score_cgc": score_cgc,
            "reasoning_baseline": reasoning_baseline,
            "reasoning_cgc": reasoning_cgc,
            "winner": winner,
            "blinded_as": "A=cgc,B=baseline" if cgc_is_a else "A=baseline,B=cgc",
        }
        verdicts.append(entry)

        sym = {"cgc": "CGC", "baseline": "BL", "tie": "TIE", "error": "ERR"}.get(winner, "?")
        print(f"BL:{score_baseline} CGC:{score_cgc} -> {sym}")

    # ── Summary ──
    print("\n" + "=" * 80)
    print("  LLM-AS-JUDGE BLIND EVALUATION SUMMARY")
    print("=" * 80)

    total_bl = sum(v["score_baseline"] for v in verdicts if v["score_baseline"] >= 0)
    total_cgc = sum(v["score_cgc"] for v in verdicts if v["score_cgc"] >= 0)
    valid = sum(1 for v in verdicts if v["score_baseline"] >= 0)
    max_score = valid * 3

    cgc_wins = sum(1 for v in verdicts if v["winner"] == "cgc")
    bl_wins = sum(1 for v in verdicts if v["winner"] == "baseline")
    ties = sum(1 for v in verdicts if v["winner"] == "tie")

    print(f"\n  Overall:  Baseline {total_bl}/{max_score}  CGC {total_cgc}/{max_score}")
    print(f"  Wins:     Baseline {bl_wins}  CGC {cgc_wins}  Ties {ties}")

    for cat in ["simple", "structural", "graph-only"]:
        subset = [v for v in verdicts if v["category"] == cat and v["score_baseline"] >= 0]
        if not subset:
            continue
        bl = sum(v["score_baseline"] for v in subset)
        cg = sum(v["score_cgc"] for v in subset)
        mx = len(subset) * 3
        cw = sum(1 for v in subset if v["winner"] == "cgc")
        bw = sum(1 for v in subset if v["winner"] == "baseline")
        ti = sum(1 for v in subset if v["winner"] == "tie")
        print(f"\n  {cat.upper()} ({len(subset)} questions)")
        print(f"    Scores: Baseline {bl}/{mx} ({bl/mx:.0%})  CGC {cg}/{mx} ({cg/mx:.0%})")
        print(f"    Wins:   Baseline {bw}  CGC {cw}  Ties {ti}")

    # ── Save to results JSON ──
    existing = json.loads(RESULTS_FILE.read_text())
    existing["llm_judge_verdicts"] = verdicts
    existing["llm_judge_summary"] = {
        "total_baseline": total_bl,
        "total_cgc": total_cgc,
        "max_score": max_score,
        "cgc_wins": cgc_wins,
        "baseline_wins": bl_wins,
        "ties": ties,
    }
    RESULTS_FILE.write_text(json.dumps(existing, indent=2))
    print(f"\n  Verdicts saved to {RESULTS_FILE}")


if __name__ == "__main__":
    run_judge()
