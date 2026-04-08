"""Test 1: Data Completeness — does the graph capture what's on disk?

Each test compares graph results against filesystem ground truth.
Measures: accuracy, latency (ms), token efficiency (chars).
"""

import subprocess
from pathlib import Path

import pytest

from helpers import (
    RAMPUMP_ROOT, CODE_EXTENSIONS, _is_ignored,
    cypher_query, timed_cypher, timed_grep, Comparison,
)


def _count_disk_files(extension: str) -> int:
    """Count files with given extension on disk, excluding ignored dirs."""
    count = 0
    for p in RAMPUMP_ROOT.rglob(f"*{extension}"):
        if p.is_file() and not _is_ignored(p):
            count += 1
    return count


class TestFileCompleteness:

    def test_python_file_count(self):
        """Graph Python files vs disk count."""
        cmp = Comparison("Python file count: graph vs disk")

        disk_py = _count_disk_files(".py")

        result, graph_ms, graph_chars = timed_cypher(
            "MATCH (f:File) WHERE f.path ENDS WITH '.py' "
            "AND f.path CONTAINS '/RamPump/' RETURN count(f) AS cnt"
        )
        graph_py = result.get("results", [{}])[0].get("cnt", 0)

        _, grep_ms, grep_chars = timed_grep(
            ".", include="*.py", extra_args=["-l"]
        )

        cmp.add("Files found", graph_py, disk_py, lower_is_better=False)
        cmp.add("Accuracy", f"{graph_py/max(disk_py,1):.0%}", "100%",
                lower_is_better=False)
        cmp.add("Latency (ms)", round(graph_ms), round(grep_ms))
        cmp.add("Tokens (chars)", graph_chars, grep_chars)
        cmp.print_table()

        ratio = graph_py / max(disk_py, 1)
        assert ratio >= 0.90, f"Graph has {graph_py} .py files, disk has {disk_py}"

    def test_vue_file_count(self):
        cmp = Comparison("Vue file count: graph vs disk")

        disk_vue = _count_disk_files(".vue")

        result, graph_ms, graph_chars = timed_cypher(
            "MATCH (f:File) WHERE f.path ENDS WITH '.vue' "
            "AND f.path CONTAINS '/RamPump/' RETURN count(f) AS cnt"
        )
        graph_vue = result.get("results", [{}])[0].get("cnt", 0)

        _, grep_ms, grep_chars = timed_grep(".", include="*.vue", extra_args=["-l"])

        cmp.add("Files found", graph_vue, disk_vue, lower_is_better=False)
        cmp.add("Latency (ms)", round(graph_ms), round(grep_ms))
        cmp.add("Tokens (chars)", graph_chars, grep_chars)
        cmp.print_table()

        assert graph_vue > 1000, f"Expected >1000 .vue files, got {graph_vue}"


class TestFunctionExtraction:

    def test_known_function_exists(self):
        """Verify 'authenticate' is in the graph with correct metadata."""
        result = timed_cypher(
            "MATCH (f:Function {name: 'authenticate'}) "
            "WHERE f.path CONTAINS 'services/user/actions.py' "
            "RETURN f.name, f.path, f.line_number"
        )[0]
        rows = result.get("results", [])
        assert len(rows) >= 1, "authenticate not found in graph"
        assert rows[0]["f.line_number"] > 0, "Missing line number"

    def test_function_count_graph_vs_grep(self):
        """Function discovery: graph structured count vs grep 'def ' count."""
        cmp = Comparison("Python function count: graph vs grep")

        result, graph_ms, graph_chars = timed_cypher(
            "MATCH (f:Function) WHERE f.path CONTAINS '/RamPump/' "
            "AND f.path ENDS WITH '.py' RETURN count(f) AS cnt"
        )
        graph_count = result.get("results", [{}])[0].get("cnt", 0)

        grep_out, grep_ms, grep_chars = timed_grep(r"^\s*def \w+\(", include="*.py")
        grep_count = len([l for l in grep_out.strip().split("\n") if l])

        cmp.add("Functions found", graph_count, grep_count, lower_is_better=False)
        cmp.add("Structured", "Yes (name,file,line)", "No (raw text)",
                lower_is_better=False)
        cmp.add("Latency (ms)", round(graph_ms), round(grep_ms))
        cmp.add("Tokens (chars)", graph_chars, grep_chars)
        cmp.print_table()

        assert graph_count > 5000, f"Expected >5K Python functions, got {graph_count}"

    def test_class_count_graph_vs_grep(self):
        cmp = Comparison("Python class count: graph vs grep")

        result, graph_ms, graph_chars = timed_cypher(
            "MATCH (c:Class) WHERE c.path CONTAINS '/RamPump/' "
            "AND c.path ENDS WITH '.py' RETURN count(c) AS cnt"
        )
        graph_count = result.get("results", [{}])[0].get("cnt", 0)

        grep_out, grep_ms, grep_chars = timed_grep(r"^class \w+", include="*.py")
        grep_count = len([l for l in grep_out.strip().split("\n") if l])

        cmp.add("Classes found", graph_count, grep_count, lower_is_better=False)
        cmp.add("Latency (ms)", round(graph_ms), round(grep_ms))
        cmp.add("Tokens (chars)", graph_chars, grep_chars)
        cmp.print_table()

        assert graph_count > 1000, f"Expected >1K Python classes, got {graph_count}"

    def test_vue_functions_extracted(self):
        result = timed_cypher(
            "MATCH (f:Function) WHERE f.path ENDS WITH '.vue' "
            "AND f.path CONTAINS '/RamPump/' RETURN count(f) AS cnt"
        )[0]
        cnt = result.get("results", [{}])[0].get("cnt", 0)
        assert cnt > 50, f"Expected >50 functions from .vue files, got {cnt}"
