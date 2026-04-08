"""Shared utilities for evaluation tests.

NOT a conftest — imported directly by test files.
"""

import json
import os
import subprocess
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

MCP_URL = "http://localhost:47321/mcp"
RAMPUMP_ROOT = Path("/Users/myang/git/RamPump")

CODE_EXTENSIONS = {
    ".py", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".go",
    ".cpp", ".h", ".hpp", ".hh", ".rs", ".c", ".java", ".rb",
    ".cs", ".php", ".kt", ".scala", ".sc", ".swift", ".hs",
    ".dart", ".pl", ".pm", ".ex", ".exs", ".vue",
}

IGNORE_DIRS = {
    "node_modules", "__pycache__", ".git", ".tox", ".mypy_cache",
    ".pytest_cache", "dist", "build", ".egg-info", "venv", ".venv",
    "env", ".env", ".idea", ".vscode", "coverage", ".coverage",
    ".next", ".nuxt",
}


def _is_ignored(path: Path) -> bool:
    parts = path.parts
    for d in IGNORE_DIRS:
        if d in parts:
            return True
    s = str(path)
    if "vendor/" in s or "bower/" in s or "bower_components/" in s:
        return True
    if path.name.endswith(".min.js") or path.name.endswith(".bundle.js"):
        return True
    return False


def mcp_call(tool_name: str, arguments: dict, timeout: float = 30) -> dict:
    payload = json.dumps({
        "jsonrpc": "2.0", "method": "tools/call", "id": 1,
        "params": {"name": tool_name, "arguments": arguments},
    }).encode()
    req = urllib.request.Request(MCP_URL, data=payload,
                                headers={"Content-Type": "application/json"})
    resp = urllib.request.urlopen(req, timeout=timeout)
    data = json.loads(resp.read())
    if "error" in data:
        raise RuntimeError(f"MCP error: {data['error']}")
    text = data["result"]["content"][0]["text"]
    return json.loads(text)


def cypher_query(query: str, timeout: float = 60) -> dict:
    return mcp_call("execute_cypher_query", {"cypher_query": query}, timeout=timeout)


def timed_cypher(query: str, timeout: float = 60):
    """Returns (result_dict, elapsed_ms, response_chars)."""
    t0 = time.perf_counter()
    result = cypher_query(query, timeout=timeout)
    elapsed = (time.perf_counter() - t0) * 1000
    chars = len(json.dumps(result))
    return result, elapsed, chars


def timed_grep(pattern: str, path: str = str(RAMPUMP_ROOT),
               include: str = "*.py", extra_args: list = None,
               timeout: float = 30):
    """Run grep and return (stdout, elapsed_ms, output_chars)."""
    cmd = ["grep", "-rn", f"--include={include}", pattern, path]
    if extra_args:
        cmd[1:1] = extra_args
    t0 = time.perf_counter()
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    elapsed = (time.perf_counter() - t0) * 1000
    output = result.stdout
    return output, elapsed, len(output)


def file_chars(paths: list) -> int:
    """Count total chars an agent would consume reading these files."""
    total = 0
    for p in paths:
        try:
            total += Path(p).stat().st_size
        except OSError:
            pass
    return total


@dataclass
class ComparisonRow:
    metric: str
    graph_value: str
    grep_value: str
    winner: str


@dataclass
class Comparison:
    test_name: str
    rows: list = field(default_factory=list)

    def add(self, metric: str, graph_val, grep_val, lower_is_better: bool = True):
        gv_str = f"{graph_val:.1f}" if isinstance(graph_val, float) else str(graph_val)
        rv_str = f"{grep_val:.1f}" if isinstance(grep_val, float) else str(grep_val)

        try:
            gv_num = float(str(graph_val).rstrip('%'))
            rv_num = float(str(grep_val).rstrip('%'))
            if lower_is_better:
                winner = "Graph" if gv_num < rv_num else ("Grep" if rv_num < gv_num else "Tie")
            else:
                winner = "Graph" if gv_num > rv_num else ("Grep" if rv_num > gv_num else "Tie")
        except (ValueError, TypeError):
            winner = "—"

        self.rows.append(ComparisonRow(metric, gv_str, rv_str, winner))

    def print_table(self):
        print(f"\n{'='*70}")
        print(f"  {self.test_name}")
        print(f"{'='*70}")
        print(f"  {'Metric':<22} {'Graph':<18} {'Grep/Read':<18} {'Winner':<10}")
        print(f"  {'-'*22} {'-'*18} {'-'*18} {'-'*10}")
        for r in self.rows:
            print(f"  {r.metric:<22} {r.graph_value:<18} {r.grep_value:<18} {r.winner:<10}")
        print()
