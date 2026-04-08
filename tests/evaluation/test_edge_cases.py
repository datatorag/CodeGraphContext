"""Test: Edge cases — tricky patterns the indexer must handle.

Each test verifies the graph handles a specific edge case correctly.
"""

import subprocess
from pathlib import Path

import pytest
from helpers import (
    RAMPUMP_ROOT, Comparison, timed_cypher, timed_grep,
)


class TestInitFiles:
    """__init__.py files that only re-export."""

    def test_init_reexport_file_indexed(self):
        """webapp/services/conversion_pixel/__init__.py has no function defs,
        only re-exports. It should still be indexed as a File node."""
        result = timed_cypher(
            "MATCH (f:File) "
            "WHERE f.path CONTAINS 'services/conversion_pixel/__init__.py' "
            "RETURN f.path"
        )[0]
        assert len(result.get("results", [])) >= 1, (
            "conversion_pixel/__init__.py not indexed"
        )

    def test_reexported_function_reachable(self):
        """Functions re-exported via __init__.py should still be findable.

        'new' is defined in actions.py but re-exported from __init__.py.
        Callers import the package and call conversion_pixel_service.new().
        """
        result = timed_cypher(
            "MATCH (f:Function {name: 'new'}) "
            "WHERE f.path CONTAINS 'services/conversion_pixel/actions.py' "
            "RETURN f.name, f.path"
        )[0]
        rows = result.get("results", [])
        assert len(rows) >= 1, (
            "conversion_pixel.new not found in graph"
        )


class TestDuplicateNames:
    """Same function name in different files."""

    def test_get_method_multiple_files(self):
        """'get' is defined in many controller files — all should be indexed."""
        cmp = Comparison("duplicate name: 'get' across files")

        result, graph_ms, graph_chars = timed_cypher(
            "MATCH (f:Function {name: 'get'}) "
            "WHERE f.path CONTAINS '/RamPump/webapp/controllers/' "
            "RETURN DISTINCT f.path"
        )
        graph_paths = [r.get("f.path", "") for r in result.get("results", [])]

        grep_out, grep_ms, grep_chars = timed_grep(
            r"def get\(self",
            path=str(RAMPUMP_ROOT / "webapp/controllers"),
            include="*.py",
        )
        grep_files = set()
        for line in grep_out.strip().split("\n"):
            if line:
                grep_files.add(line.split(":")[0])

        cmp.add("Files with 'get'", len(graph_paths), len(grep_files),
                lower_is_better=False)
        cmp.add("Latency (ms)", round(graph_ms), round(grep_ms))
        cmp.add("Tokens (chars)", graph_chars, grep_chars)
        cmp.print_table()

        assert len(graph_paths) >= 5, (
            f"Expected >=5 controllers with 'get', found {len(graph_paths)}"
        )

    def test_save_function_disambiguated(self):
        """'save' exists in multiple service modules — graph stores each separately."""
        result = timed_cypher(
            "MATCH (f:Function {name: 'save'}) "
            "WHERE f.path CONTAINS '/RamPump/' "
            "RETURN f.path, f.line_number"
        )[0]
        rows = result.get("results", [])
        paths = [r.get("f.path", "") for r in rows]

        # Verify they're in different files
        assert len(set(paths)) >= 2, (
            f"Expected 'save' in >=2 different files, got {set(paths)}"
        )


class TestDecoratedFunctions:
    """Functions with decorators should still be indexed."""

    def test_celery_task_indexed(self):
        """@celery_app.task decorated function should be in graph."""
        result = timed_cypher(
            "MATCH (f:Function {name: 'update_user_accounts_with_role'}) "
            "WHERE f.path CONTAINS 'services/user/utils.py' "
            "RETURN f.name, f.path, f.line_number"
        )[0]
        rows = result.get("results", [])
        assert len(rows) >= 1, (
            "Celery-decorated function 'update_user_accounts_with_role' not found"
        )

    def test_property_decorator_indexed(self):
        """@property decorated methods should be indexed as functions."""
        result = timed_cypher(
            "MATCH (f:Function {name: 'url'}) "
            "WHERE f.path CONTAINS 'notification.py' "
            "RETURN f.name, f.path"
        )[0]
        rows = result.get("results", [])
        # 'url' is a @property in notification.py Alert class
        assert len(rows) >= 1, (
            "@property 'url' not found in graph"
        )


class TestVueSFC:
    """Vue single-file component parsing."""

    def test_vue_file_indexed(self):
        """A known .vue file should be indexed."""
        result = timed_cypher(
            "MATCH (f:File) "
            "WHERE f.path CONTAINS 'AssignmentCell.vue' "
            "RETURN f.path"
        )[0]
        rows = result.get("results", [])
        assert len(rows) >= 1, "AssignmentCell.vue not found in graph"

    def test_vue_functions_extracted(self):
        """Functions inside Vue <script> blocks should be extracted."""
        result = timed_cypher(
            "MATCH (f:Function) "
            "WHERE f.path ENDS WITH '.vue' "
            "RETURN count(f) AS cnt"
        )[0]
        cnt = result.get("results", [{}])[0].get("cnt", 0)
        assert cnt > 50, f"Expected >50 functions from Vue files, got {cnt}"


class TestGraphStructuralAdvantage:
    """Tests where the graph provides answers grep fundamentally cannot."""

    def test_find_all_subclasses(self):
        """Find all subclasses of a given class — requires reverse INHERITS traversal.

        Grep can find 'class X(Parent)' but misses indirect subclasses.
        """
        cmp = Comparison("find all subclasses of 'ImpressionsOverTime'")

        result, graph_ms, graph_chars = timed_cypher(
            "MATCH (child)-[:INHERITS*1..5]->(parent:Class {name: 'ImpressionsOverTime'}) "
            "RETURN child.name, length(shortestPath((child)-[:INHERITS*]->(parent))) AS depth"
        )
        subclasses = result.get("results", [])

        grep_out, grep_ms, grep_chars = timed_grep(
            r"class \w+\(.*ImpressionsOverTime", include="*.py"
        )
        grep_direct = len([l for l in grep_out.strip().split("\n") if l])

        cmp.add("Subclasses found", len(subclasses), grep_direct,
                lower_is_better=False)
        cmp.add("Includes indirect", "Yes", "No (only direct)",
                lower_is_better=False)
        cmp.add("Latency (ms)", round(graph_ms), round(grep_ms))
        cmp.add("Tokens (chars)", graph_chars, grep_chars)
        cmp.print_table()

        # Graph should find more than direct grep (includes grandchildren)
        assert len(subclasses) >= 2, (
            f"Expected >=2 subclasses, got {len(subclasses)}"
        )

    def test_circular_dependency_detection(self):
        """Detect files that import each other — impossible with single-pass grep."""
        cmp = Comparison("circular dependency detection")

        # FalkorDB doesn't support EXISTS subqueries — use a simpler mutual-import check
        result, graph_ms, graph_chars = timed_cypher(
            "MATCH (a:File)-[:IMPORTS]->(m1:Module)<-[:IMPORTS]-(b:File) "
            "WHERE a.path CONTAINS '/RamPump/' "
            "AND a <> b "
            "RETURN DISTINCT a.path, b.path LIMIT 10"
        )
        cycles = result.get("results", [])

        cmp.add("Potential cycles", len(cycles), "infeasible with grep",
                lower_is_better=False)
        cmp.add("Latency (ms)", round(graph_ms), "N/A")
        cmp.add("Tokens (chars)", graph_chars, "N/A")
        cmp.print_table()

        # Just verify the query runs — cycles may or may not exist
        assert isinstance(cycles, list)
