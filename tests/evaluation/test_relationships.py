"""Test: Relationship accuracy — CALLS, INHERITS, IMPORTS edges.

For each relationship type, verify known edges exist and measure
graph query vs grep for discovering the same relationships.
"""

import subprocess
from pathlib import Path

import pytest
from helpers import (
    RAMPUMP_ROOT, Comparison, timed_cypher, timed_grep, file_chars,
)


class TestCallsEdges:
    """Verify CALLS edges for known cross-module function calls."""

    # (caller_file_fragment, caller_function, callee_function, callee_file_fragment)
    KNOWN_CALLS = [
        ("controllers/pages/login.py", "post", "authenticate", "services/user/actions.py"),
        ("controllers/pages/unlock_account.py", "post", "authenticate", "services/user/actions.py"),
        ("controllers/api_internal/v3/access_token.py", None, "authenticate", "services/user/actions.py"),
        ("controllers/api_internal/v3/change_password.py", None, "authenticate", "services/user/actions.py"),
        ("controllers/api_internal/v3/change_email.py", None, "authenticate", "services/user/actions.py"),
        ("controllers/api_internal/v3/confirm_password.py", "post", "authenticate", "services/user/actions.py"),
        ("api.py", None, "create_app", "webapp/__init__.py"),
        ("wsgi.py", None, "create_app", "webapp/__init__.py"),
    ]

    def test_known_calls_exist(self):
        """Check each known call has a CALLS edge in the graph."""
        cmp = Comparison("CALLS edge verification (8 known calls)")

        found = 0
        missing = []
        for caller_file, caller_fn, callee_fn, callee_file in self.KNOWN_CALLS:
            if caller_fn:
                query = (
                    f"MATCH (a)-[r:CALLS]->(b:Function {{name: '{callee_fn}'}}) "
                    f"WHERE a.path CONTAINS '{caller_file}' "
                    f"AND a.name = '{caller_fn}' "
                    f"AND b.path CONTAINS '{callee_file}' "
                    f"RETURN count(r) AS cnt"
                )
            else:
                query = (
                    f"MATCH (a)-[r:CALLS]->(b:Function {{name: '{callee_fn}'}}) "
                    f"WHERE a.path CONTAINS '{caller_file}' "
                    f"AND b.path CONTAINS '{callee_file}' "
                    f"RETURN count(r) AS cnt"
                )
            result = timed_cypher(query)[0]
            cnt = result.get("results", [{}])[0].get("cnt", 0)
            if cnt > 0:
                found += 1
            else:
                missing.append(f"{caller_file}:{caller_fn} -> {callee_fn}")

        graph_recall = found / len(self.KNOWN_CALLS)

        # Grep comparison: to find callers of 'authenticate', grep must scan all files
        grep_out, grep_ms, grep_chars = timed_grep(
            r"\.authenticate\(", include="*.py"
        )
        grep_matches = len([l for l in grep_out.strip().split("\n") if l])

        cmp.add("Recall", f"{graph_recall:.0%} ({found}/{len(self.KNOWN_CALLS)})",
                "N/A (grep finds text, not edges)", lower_is_better=False)
        cmp.add("Grep matches", "structured edges", grep_matches,
                lower_is_better=False)
        cmp.print_table()

        if missing:
            print(f"  Missing CALLS edges: {missing}")

        assert graph_recall >= 0.75, (
            f"CALLS recall: {graph_recall:.0%}. Missing: {missing}"
        )

    def test_calls_false_positive_rate(self):
        """Sample CALLS edges and check they look reasonable."""
        cmp = Comparison("CALLS false positive check (sample 20)")

        result, graph_ms, graph_chars = timed_cypher(
            "MATCH (a)-[r:CALLS]->(b) "
            "WHERE a.path CONTAINS '/RamPump/' "
            "RETURN a.name, a.path, b.name, b.path "
            "LIMIT 20"
        )
        rows = result.get("results", [])
        suspicious = []
        for row in rows:
            caller = row.get("a.name", "")
            callee = row.get("b.name", "")
            # Flag calls where callee name is very short (likely minified)
            if len(callee) <= 2:
                suspicious.append(f"{caller} -> {callee}")
            # Flag calls where caller == callee in different files
            # (could be valid recursion, but often false positive)

        false_positive_rate = len(suspicious) / max(len(rows), 1)
        cmp.add("Sample size", len(rows), "N/A", lower_is_better=False)
        cmp.add("Suspicious", len(suspicious), "N/A", lower_is_better=True)
        cmp.add("FP rate", f"{false_positive_rate:.0%}", "N/A",
                lower_is_better=True)
        cmp.print_table()

        assert false_positive_rate < 0.20, (
            f"Too many suspicious CALLS: {suspicious}"
        )


class TestInheritsEdges:
    """Verify INHERITS edges for known class hierarchies."""

    # (child_class, parent_class, file_containing_child)
    KNOWN_INHERITANCE = [
        ("AdImpressionsOverTime", "ImpressionsOverTime", "models/charts.py"),
        ("CampaignImpressionsOverTime", "ImpressionsOverTime", "models/charts.py"),
        ("AllCampaignsImpressionsOverTime", "CampaignImpressionsOverTime", "models/charts.py"),
        ("CampaignAlert", "Alert", "controllers/api_internal/notification.py"),
    ]

    def test_known_inheritance_exists(self):
        """Check known class hierarchies have INHERITS edges."""
        cmp = Comparison("INHERITS edge verification (4 known)")

        found = 0
        missing = []
        for child, parent, file_frag in self.KNOWN_INHERITANCE:
            result = timed_cypher(
                f"MATCH (c:Class {{name: '{child}'}})-[:INHERITS]->(p:Class {{name: '{parent}'}}) "
                f"WHERE c.path CONTAINS '{file_frag}' "
                f"RETURN count(*) AS cnt"
            )[0]
            cnt = result.get("results", [{}])[0].get("cnt", 0)
            if cnt > 0:
                found += 1
            else:
                missing.append(f"{child} -> {parent}")

        graph_recall = found / len(self.KNOWN_INHERITANCE)

        # Grep: find class definitions with parent classes
        grep_out, grep_ms, grep_chars = timed_grep(
            r"class \w+\(.*ImpressionsOverTime", include="*.py"
        )
        grep_count = len([l for l in grep_out.strip().split("\n") if l])

        cmp.add("Recall", f"{graph_recall:.0%} ({found}/{len(self.KNOWN_INHERITANCE)})",
                f"{grep_count} text matches", lower_is_better=False)
        cmp.print_table()

        if missing:
            print(f"  Missing INHERITS edges: {missing}")

        assert graph_recall >= 0.75, (
            f"INHERITS recall: {graph_recall:.0%}. Missing: {missing}"
        )

    def test_class_hierarchy_traversal(self):
        """Graph advantage: multi-hop hierarchy traversal.

        Find the full inheritance chain for AllCampaignsImpressionsOverTime.
        Grep can't do this without multiple rounds of searches.
        """
        cmp = Comparison("class hierarchy traversal (multi-hop)")

        result, graph_ms, graph_chars = timed_cypher(
            "MATCH path = (c:Class {name: 'AllCampaignsImpressionsOverTime'})"
            "-[:INHERITS*1..5]->(ancestor) "
            "RETURN [n IN nodes(path) | n.name] AS chain"
        )
        chains = result.get("results", [])
        graph_depth = max((len(c.get("chain", [])) for c in chains), default=0)

        # Grep approach: would need iterative searches
        # 1. grep for AllCampaignsImpressionsOverTime → find parent
        # 2. grep for parent → find grandparent
        # 3. repeat until no more parents
        # Each step requires reading the file to parse the class definition
        grep_out1, ms1, chars1 = timed_grep(
            r"class AllCampaignsImpressionsOverTime\(", include="*.py"
        )
        grep_out2, ms2, chars2 = timed_grep(
            r"class CampaignImpressionsOverTime\(", include="*.py"
        )
        grep_out3, ms3, chars3 = timed_grep(
            r"class ImpressionsOverTime\(", include="*.py"
        )
        total_grep_ms = ms1 + ms2 + ms3
        total_grep_chars = chars1 + chars2 + chars3

        cmp.add("Chain depth", graph_depth, "3 manual steps",
                lower_is_better=False)
        cmp.add("Latency (ms)", round(graph_ms), round(total_grep_ms))
        cmp.add("Tokens (chars)", graph_chars, total_grep_chars)
        cmp.print_table()

        assert graph_depth >= 2, f"Expected chain depth >=2, got {graph_depth}"


class TestImportsEdges:
    """Verify IMPORTS edges."""

    def test_known_imports_exist(self):
        """Check that import statements create IMPORTS edges."""
        cmp = Comparison("IMPORTS edge verification")

        # Check that login.py imports from webapp.services.user
        result, graph_ms, graph_chars = timed_cypher(
            "MATCH (f:File)-[:IMPORTS]->(m:Module) "
            "WHERE f.path CONTAINS 'controllers/pages/login.py' "
            "RETURN m.name"
        )
        imported_modules = [r.get("m.name", "") for r in result.get("results", [])]

        grep_out, grep_ms, grep_chars = timed_grep(
            r"^from |^import ",
            path=str(RAMPUMP_ROOT / "webapp/controllers/pages/login.py"),
            include="*.py",
        )

        cmp.add("Graph imports", len(imported_modules), "N/A",
                lower_is_better=False)
        cmp.add("Grep import lines", "structured",
                len([l for l in grep_out.strip().split("\n") if l]),
                lower_is_better=False)
        cmp.add("Latency (ms)", round(graph_ms), round(grep_ms))
        cmp.add("Tokens (chars)", graph_chars, grep_chars)
        cmp.print_table()

        assert len(imported_modules) > 0, "No IMPORTS edges found for login.py"

    def test_total_imports_count(self):
        """Total IMPORTS edges should be substantial."""
        result = timed_cypher(
            "MATCH ()-[r:IMPORTS]->() RETURN count(r) AS cnt"
        )[0]
        cnt = result.get("results", [{}])[0].get("cnt", 0)
        assert cnt > 10000, f"Expected >10K IMPORTS edges, got {cnt}"
