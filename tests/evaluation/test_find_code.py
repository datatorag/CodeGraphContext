"""Test: find_code — search for functions/classes by name.

Graph returns structured results (name, file, line, type).
Grep returns raw text matches that need parsing.
"""

import subprocess
from pathlib import Path

import pytest
from helpers import (
    RAMPUMP_ROOT, Comparison, timed_cypher, timed_grep, file_chars,
)


class TestFindCode:

    def test_find_function_by_name(self):
        """Search for 'create_app' — graph structured query vs grep."""
        cmp = Comparison("find_code('create_app')")

        # Ground truth
        KNOWN_FILES = {"webapp/__init__.py"}

        # --- Graph ---
        result, graph_ms, graph_chars = timed_cypher(
            "MATCH (f:Function {name: 'create_app'}) "
            "RETURN f.name, f.path, f.line_number"
        )
        graph_files = set()
        for row in result.get("results", []):
            p = row.get("f.path", "")
            if "/RamPump/" in p:
                graph_files.add(p.split("/RamPump/")[1])

        graph_correct = len(graph_files & KNOWN_FILES)
        graph_recall = graph_correct / len(KNOWN_FILES)

        # --- Grep ---
        grep_out, grep_ms, grep_chars = timed_grep(
            r"def create_app\b", include="*.py"
        )
        grep_files = set()
        for line in grep_out.strip().split("\n"):
            if not line:
                continue
            fpath = line.split(":")[0]
            if "/RamPump/" in fpath:
                grep_files.add(fpath.split("/RamPump/")[1])

        grep_correct = len(grep_files & KNOWN_FILES)
        grep_recall = grep_correct / len(KNOWN_FILES)

        cmp.add("Recall", f"{graph_recall:.0%}", f"{grep_recall:.0%}",
                lower_is_better=False)
        cmp.add("Results", len(graph_files), len(grep_files), lower_is_better=False)
        cmp.add("Latency (ms)", round(graph_ms), round(grep_ms))
        cmp.add("Tokens (chars)", graph_chars, grep_chars)
        cmp.print_table()

        assert graph_recall >= 1.0, f"Graph didn't find create_app: {graph_files}"

    def test_find_class_by_name(self):
        """Search for 'LoginPageController' — single known class."""
        cmp = Comparison("find_code('LoginPageController')")

        KNOWN_FILE = "webapp/controllers/pages/login.py"

        result, graph_ms, graph_chars = timed_cypher(
            "MATCH (c:Class {name: 'LoginPageController'}) "
            "RETURN c.name, c.path, c.line_number"
        )
        graph_found = False
        for row in result.get("results", []):
            if KNOWN_FILE in row.get("c.path", ""):
                graph_found = True

        grep_out, grep_ms, grep_chars = timed_grep(
            r"class LoginPageController\b", include="*.py"
        )
        grep_found = KNOWN_FILE in grep_out

        cmp.add("Found", "Yes" if graph_found else "No",
                "Yes" if grep_found else "No", lower_is_better=False)
        cmp.add("Latency (ms)", round(graph_ms), round(grep_ms))
        cmp.add("Tokens (chars)", graph_chars, grep_chars)
        cmp.print_table()

        assert graph_found, "Graph didn't find LoginPageController"

    def test_find_ambiguous_name(self):
        """Search for 'get' — common method name, many files.

        Graph advantage: returns structured results with file+line+type.
        Grep: returns raw text requiring agent to parse and deduplicate.
        """
        cmp = Comparison("find_code('get') — ambiguous name")

        result, graph_ms, graph_chars = timed_cypher(
            "MATCH (f:Function {name: 'get'}) "
            "WHERE f.path CONTAINS '/RamPump/' "
            "RETURN f.path, f.line_number LIMIT 50"
        )
        graph_count = len(result.get("results", []))

        grep_out, grep_ms, grep_chars = timed_grep(
            r"def get\(self", include="*.py"
        )
        grep_count = len([l for l in grep_out.strip().split("\n") if l])

        # For ambiguous names, the agent would need to read surrounding context
        # to understand each match. Estimate: 50 lines per match.
        agent_context_chars = grep_count * 50 * 80  # 50 lines × 80 chars

        cmp.add("Matches", graph_count, grep_count, lower_is_better=False)
        cmp.add("Latency (ms)", round(graph_ms), round(grep_ms))
        cmp.add("Tokens (chars)", graph_chars, grep_chars + agent_context_chars)
        cmp.print_table()

        assert graph_count > 5, f"Expected many 'get' functions, got {graph_count}"

    def test_cross_language_search(self):
        """Search for a name across Python + JS + Vue — graph's strength.

        Grep needs separate patterns per language; graph searches all at once.
        """
        cmp = Comparison("cross-language search('render')")

        result, graph_ms, graph_chars = timed_cypher(
            "MATCH (f:Function {name: 'render'}) "
            "WHERE f.path CONTAINS '/RamPump/' "
            "RETURN f.path, f.lang LIMIT 100"
        )
        graph_results = result.get("results", [])
        graph_langs = set(r.get("f.lang", "?") for r in graph_results)

        # Grep: needs multiple passes for different languages
        total_grep_ms = 0
        total_grep_chars = 0
        total_grep_count = 0
        for pattern, inc in [
            (r"def render\b", "*.py"),
            (r"function render\b", "*.js"),
            (r"render\s*\(", "*.vue"),
        ]:
            out, ms, chars = timed_grep(pattern, include=inc)
            total_grep_ms += ms
            total_grep_chars += chars
            total_grep_count += len([l for l in out.strip().split("\n") if l])

        cmp.add("Results", len(graph_results), total_grep_count,
                lower_is_better=False)
        cmp.add("Languages", len(graph_langs), "manual", lower_is_better=False)
        cmp.add("Latency (ms)", round(graph_ms), round(total_grep_ms))
        cmp.add("Tokens (chars)", graph_chars, total_grep_chars)
        cmp.print_table()

        assert len(graph_results) > 0
