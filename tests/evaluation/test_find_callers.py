"""Test: find_callers — who calls a given function?

Ground truth: manually verified callers of 'authenticate' in RamPump.
Graph should find callers via CALLS edges; grep must scan all files.
"""

import re
import subprocess
from pathlib import Path

import pytest
from helpers import (
    RAMPUMP_ROOT, Comparison, timed_cypher, timed_grep, file_chars,
)

# Ground truth: manually verified callers of authenticate()
# (calling user_service.authenticate / user_svc.authenticate / authenticate)
AUTHENTICATE_CALLERS = {
    "webapp/controllers/pages/login.py",
    "webapp/controllers/pages/unlock_account.py",
    "webapp/controllers/api_internal/v3/access_token.py",
    "webapp/controllers/api_internal/v3/change_password.py",
    "webapp/controllers/api_internal/v3/change_email.py",
    "webapp/controllers/api_internal/v3/confirm_password.py",
}


class TestFindCallers:

    def test_authenticate_callers(self):
        """find_callers for 'authenticate' — graph vs grep, 3 metrics."""
        cmp = Comparison("find_callers('authenticate')")

        # --- Graph ---
        result, graph_ms, graph_chars = timed_cypher(
            "MATCH (caller)-[r:CALLS]->(f:Function {name: 'authenticate'}) "
            "WHERE f.path CONTAINS 'services/user/actions.py' "
            "RETURN DISTINCT caller.path AS caller_path, caller.name AS caller_name"
        )
        graph_files = set()
        for row in result.get("results", []):
            p = row.get("caller_path", "")
            # Normalize to relative path
            if "/RamPump/" in p:
                graph_files.add(p.split("/RamPump/")[1])

        graph_correct = len(graph_files & AUTHENTICATE_CALLERS)
        graph_total = len(graph_files)
        graph_precision = graph_correct / max(graph_total, 1)
        graph_recall = graph_correct / len(AUTHENTICATE_CALLERS)

        # --- Grep ---
        grep_out, grep_ms, grep_chars = timed_grep(
            r"\.authenticate\(", include="*.py"
        )
        grep_files = set()
        for line in grep_out.strip().split("\n"):
            if not line:
                continue
            fpath = line.split(":")[0]
            if "/RamPump/" in fpath:
                rel = fpath.split("/RamPump/")[1]
                # Exclude the definition file and __init__.py re-exports
                if "services/user/actions.py" not in rel and "__init__.py" not in rel:
                    grep_files.add(rel)

        grep_correct = len(grep_files & AUTHENTICATE_CALLERS)
        grep_total = len(grep_files)
        grep_precision = grep_correct / max(grep_total, 1)
        grep_recall = grep_correct / len(AUTHENTICATE_CALLERS)

        # To actually answer "who calls authenticate", an agent using grep
        # would also need to read the import statements in each file to
        # confirm the call target. Estimate: read the top 30 lines of each
        # matching file.
        grep_files_to_read = [
            str(RAMPUMP_ROOT / f) for f in grep_files
        ]
        agent_read_chars = grep_chars + file_chars(grep_files_to_read)

        # --- Table ---
        cmp.add("Precision", f"{graph_precision:.0%}", f"{grep_precision:.0%}",
                lower_is_better=False)
        cmp.add("Recall", f"{graph_recall:.0%}", f"{grep_recall:.0%}",
                lower_is_better=False)
        cmp.add("Latency (ms)", round(graph_ms), round(grep_ms))
        cmp.add("Tokens (chars)", graph_chars, agent_read_chars)
        cmp.print_table()

        # Assertions
        assert graph_recall >= 0.80, (
            f"Graph recall too low: {graph_recall:.0%} "
            f"(found {graph_files}, expected {AUTHENTICATE_CALLERS})"
        )
        assert graph_precision >= 0.80, (
            f"Graph precision too low: {graph_precision:.0%} "
            f"(false positives: {graph_files - AUTHENTICATE_CALLERS})"
        )

    def test_hash_password_callers(self):
        """find_callers for 'hash_password' — heavily-used utility."""
        cmp = Comparison("find_callers('hash_password')")

        # Ground truth from grep
        HASH_PASSWORD_CALLERS = {
            "webapp/services/user/actions.py",
            "webapp/services/user/utils.py",
        }

        result, graph_ms, graph_chars = timed_cypher(
            "MATCH (caller)-[r:CALLS]->(f:Function {name: 'hash_password'}) "
            "RETURN DISTINCT caller.path AS p, caller.name AS n"
        )
        graph_files = set()
        for row in result.get("results", []):
            p = row.get("p", "")
            if "/RamPump/" in p:
                graph_files.add(p.split("/RamPump/")[1])

        graph_correct = len(graph_files & HASH_PASSWORD_CALLERS)
        graph_recall = graph_correct / len(HASH_PASSWORD_CALLERS)

        grep_out, grep_ms, grep_chars = timed_grep(
            r"hash_password\(", include="*.py"
        )
        grep_files = set()
        for line in grep_out.strip().split("\n"):
            if not line:
                continue
            fpath = line.split(":")[0]
            if "/RamPump/" in fpath:
                rel = fpath.split("/RamPump/")[1]
                if "def hash_password" not in line and "import" not in line:
                    grep_files.add(rel)

        grep_correct = len(grep_files & HASH_PASSWORD_CALLERS)
        grep_recall = grep_correct / len(HASH_PASSWORD_CALLERS)

        cmp.add("Recall", f"{graph_recall:.0%}", f"{grep_recall:.0%}",
                lower_is_better=False)
        cmp.add("Latency (ms)", round(graph_ms), round(grep_ms))
        cmp.add("Tokens (chars)", graph_chars, grep_chars)
        cmp.print_table()

        assert graph_recall >= 0.50, f"Graph recall: {graph_recall:.0%}"
