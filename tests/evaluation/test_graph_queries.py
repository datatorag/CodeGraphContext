"""Test: Complex graph queries that grep can't do efficiently.

These tests demonstrate the graph's value for structural code analysis
that would require multiple grep passes + file reads + manual parsing.
"""

import subprocess
from pathlib import Path

import pytest
from helpers import (
    RAMPUMP_ROOT, Comparison, timed_cypher, timed_grep, file_chars,
)


class TestImpactAnalysis:
    """If I change function X, what else might break?"""

    def test_change_impact_authenticate(self):
        """Impact analysis: what breaks if we change 'authenticate'?

        Graph: one query gets all direct + transitive callers.
        Grep: needs iterative searches, can't distinguish callers from mentions.
        """
        cmp = Comparison("impact analysis: change 'authenticate'")

        # Graph: direct callers
        result, graph_ms, graph_chars = timed_cypher(
            "MATCH (caller)-[:CALLS]->(f:Function {name: 'authenticate'}) "
            "WHERE f.path CONTAINS 'services/user/actions.py' "
            "RETURN caller.name AS name, caller.path AS path, labels(caller)[0] AS type"
        )
        direct_callers = result.get("results", [])

        # Graph: transitive callers (who calls the callers?)
        result2, graph_ms2, graph_chars2 = timed_cypher(
            "MATCH (indirect)-[:CALLS]->(direct)-[:CALLS]->(f:Function {name: 'authenticate'}) "
            "WHERE f.path CONTAINS 'services/user/actions.py' "
            "RETURN DISTINCT indirect.name AS name, indirect.path AS path"
        )
        indirect_callers = result2.get("results", [])
        total_graph_ms = graph_ms + graph_ms2
        total_graph_chars = graph_chars + graph_chars2

        # Grep approach: find direct mentions
        grep_out, grep_ms, grep_chars = timed_grep(
            r"authenticate\(", include="*.py"
        )
        grep_lines = [l for l in grep_out.strip().split("\n") if l]
        # Agent would then need to read each file to understand context
        grep_file_set = set()
        for line in grep_lines:
            fpath = line.split(":")[0]
            grep_file_set.add(fpath)
        agent_read_chars = grep_chars + file_chars(list(grep_file_set))
        # For transitive analysis, agent would need to grep for each caller name
        # This multiplies the cost significantly
        estimated_transitive_chars = agent_read_chars * 3  # conservative

        cmp.add("Direct callers", len(direct_callers), len(grep_lines),
                lower_is_better=False)
        cmp.add("Indirect callers", len(indirect_callers), "requires N more greps",
                lower_is_better=False)
        cmp.add("Latency (ms)", round(total_graph_ms), round(grep_ms))
        cmp.add("Tokens (chars)", total_graph_chars, estimated_transitive_chars)
        cmp.print_table()

        assert len(direct_callers) >= 4, f"Expected >=4 direct callers"


class TestDeadCodeDetection:
    """Find functions that are never called — graph's unique strength."""

    def test_find_uncalled_functions(self):
        """Find functions with 0 incoming CALLS edges.

        Graph: single query.
        Grep: impossible without building a call graph (which IS the graph).
        """
        cmp = Comparison("dead code detection (uncalled functions)")

        # FalkorDB doesn't support EXISTS subqueries — use OPTIONAL MATCH + WHERE null
        result, graph_ms, graph_chars = timed_cypher(
            "MATCH (f:Function) "
            "WHERE f.path CONTAINS '/RamPump/webapp/' "
            "WITH f "
            "OPTIONAL MATCH (caller)-[:CALLS]->(f) "
            "WITH f, count(caller) AS caller_count "
            "WHERE caller_count = 0 "
            "RETURN f.name, f.path LIMIT 20"
        )
        uncalled = result.get("results", [])

        # Verify a sample: grep for one of the "dead" functions to see if it's
        # truly uncalled or just missed by the resolver
        if uncalled:
            sample = uncalled[0]
            sample_name = sample.get("f.name", "")
            grep_out, grep_ms, grep_chars = timed_grep(
                rf"\.{sample_name}\(|{sample_name}\(",
                include="*.py"
            )
            grep_mentions = len([l for l in grep_out.strip().split("\n")
                                 if l and "def " not in l and "import" not in l])
        else:
            grep_ms = 0
            grep_chars = 0
            grep_mentions = 0

        # For dead code detection via grep, an agent would need to:
        # 1. List all function definitions (~27K)
        # 2. For EACH, grep the entire codebase for calls
        # 3. Estimate: 27K × grep time per function
        estimated_grep_ms = 27000 * grep_ms if grep_ms > 0 else 27000 * 50
        estimated_grep_chars = 27000 * max(grep_chars, 100)

        cmp.add("Uncalled found", len(uncalled), "infeasible with grep",
                lower_is_better=False)
        cmp.add("Latency (ms)", round(graph_ms), f"~{estimated_grep_ms/1000:.0f}s",
                lower_is_better=True)
        cmp.add("Tokens (chars)", graph_chars, f"~{estimated_grep_chars:,}",
                lower_is_better=True)
        cmp.print_table()

        if uncalled:
            print(f"  Sample uncalled: {uncalled[0].get('f.name')} "
                  f"in {uncalled[0].get('f.path', '').split('/RamPump/')[-1]}")
            print(f"  Grep mentions (excluding def/import): {grep_mentions}")

        assert len(uncalled) > 0, "Expected some uncalled functions"


class TestDependencyGraph:
    """Map file dependencies — who imports what?"""

    def test_file_dependency_fan_out(self):
        """Which files have the most imports? (Complexity hotspots)

        Graph: single aggregation query.
        Grep: parse import statements in every file, resolve paths.
        """
        cmp = Comparison("file dependency fan-out (top importers)")

        result, graph_ms, graph_chars = timed_cypher(
            "MATCH (f:File)-[r:IMPORTS]->(m) "
            "WHERE f.path CONTAINS '/RamPump/' "
            "RETURN f.path, count(r) AS import_count "
            "ORDER BY import_count DESC LIMIT 10"
        )
        top_files = result.get("results", [])

        # Grep approach: count import lines per file
        grep_out, grep_ms, grep_chars = timed_grep(
            r"^from |^import ", include="*.py"
        )
        # Parse grep output to count imports per file
        file_import_counts = {}
        for line in grep_out.strip().split("\n"):
            if ":" in line:
                fpath = line.split(":")[0]
                file_import_counts[fpath] = file_import_counts.get(fpath, 0) + 1
        grep_top = sorted(file_import_counts.items(), key=lambda x: -x[1])[:10]

        cmp.add("Top file imports",
                top_files[0].get("import_count", 0) if top_files else 0,
                grep_top[0][1] if grep_top else 0,
                lower_is_better=False)
        cmp.add("Latency (ms)", round(graph_ms), round(grep_ms))
        cmp.add("Tokens (chars)", graph_chars, grep_chars)
        cmp.print_table()

        assert len(top_files) > 0

    def test_module_coupling(self):
        """Which modules are most tightly coupled via CALLS?

        This is impossible with grep — requires a full call graph.
        """
        cmp = Comparison("module coupling analysis")

        result, graph_ms, graph_chars = timed_cypher(
            "MATCH (a)-[:CALLS]->(b) "
            "WHERE a.path CONTAINS '/RamPump/' AND b.path CONTAINS '/RamPump/' "
            "AND a.path <> b.path "
            "WITH split(a.path, '/') AS a_parts, split(b.path, '/') AS b_parts "
            "RETURN a_parts[size(a_parts)-2] AS caller_dir, "
            "       b_parts[size(b_parts)-2] AS callee_dir, "
            "       count(*) AS calls "
            "ORDER BY calls DESC LIMIT 10"
        )
        couplings = result.get("results", [])

        cmp.add("Module pairs", len(couplings), "infeasible with grep",
                lower_is_better=False)
        cmp.add("Latency (ms)", round(graph_ms), "N/A")
        cmp.add("Tokens (chars)", graph_chars, "N/A")
        cmp.print_table()

        if couplings:
            for c in couplings[:5]:
                print(f"  {c.get('caller_dir', '?')} → {c.get('callee_dir', '?')}: "
                      f"{c.get('calls', 0)} calls")
