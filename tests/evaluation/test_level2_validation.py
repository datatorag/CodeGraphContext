"""Level 2 Validation: Source-level verification of graph edges.

Samples random CALLS and INHERITS edges, reads the actual source files,
and verifies each edge against the code. This is the ground truth test —
if the source doesn't confirm the edge, it's a false positive.
"""

import re
from pathlib import Path

import pytest

from helpers import cypher_query, RAMPUMP_ROOT


def _read_lines(filepath: str, center_line: int, window: int = 10) -> str:
    """Read lines around center_line from a file. Returns empty string on failure."""
    try:
        p = Path(filepath)
        if not p.exists():
            return ""
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        start = max(0, center_line - 1 - window)
        end = min(len(lines), center_line - 1 + window + 1)
        return "\n".join(lines[start:end])
    except Exception:
        return ""


def _read_line(filepath: str, line_number: int) -> str:
    """Read a single line from a file."""
    try:
        lines = Path(filepath).read_text(encoding="utf-8", errors="replace").splitlines()
        if 0 < line_number <= len(lines):
            return lines[line_number - 1]
        return ""
    except Exception:
        return ""


class TestCallsValidation:
    """Sample 100 random CALLS edges and verify against source code."""

    def test_calls_source_verification(self):
        # Sample 100 random CALLS edges with line numbers
        result = cypher_query(
            "MATCH (caller)-[r:CALLS]->(callee) "
            "WHERE caller.path CONTAINS '/RamPump/' "
            "AND r.line_number IS NOT NULL "
            "AND r.line_number > 0 "
            "WITH caller, r, callee, rand() AS rnd "
            "ORDER BY rnd "
            "RETURN caller.name AS caller_name, "
            "       caller.path AS caller_path, "
            "       caller.line_number AS caller_line, "
            "       callee.name AS callee_name, "
            "       callee.path AS callee_path, "
            "       r.line_number AS call_line, "
            "       r.full_call_name AS full_call "
            "LIMIT 100",
            timeout=60,
        )
        rows = result.get("results", [])
        assert len(rows) > 0, "No CALLS edges returned"

        verified = 0
        false_positives = []
        unverifiable = []

        for row in rows:
            caller_name = row.get("caller_name", "")
            caller_path = row.get("caller_path", "")
            callee_name = row.get("callee_name", "")
            call_line = row.get("call_line", 0)
            full_call = row.get("full_call", "") or callee_name

            if not caller_path or not call_line or call_line <= 0:
                unverifiable.append({
                    "reason": "missing path or line",
                    "caller": caller_name,
                    "callee": callee_name,
                })
                continue

            if not Path(caller_path).exists():
                unverifiable.append({
                    "reason": "file not found",
                    "caller_path": caller_path,
                    "callee": callee_name,
                })
                continue

            # Read source around the call line (±10 lines to handle multi-line calls)
            context = _read_lines(caller_path, call_line, window=10)
            if not context:
                unverifiable.append({
                    "reason": "could not read file",
                    "caller_path": caller_path,
                    "call_line": call_line,
                    "callee": callee_name,
                })
                continue

            # Check if the callee name appears in the source context.
            # For dotted calls like "user_service.authenticate", check for
            # either the full call or just the function name.
            found = False

            # Direct name match
            if callee_name in context:
                found = True
            # Full call match (e.g. "module.func")
            elif full_call and full_call in context:
                found = True
            # For class instantiation, the class name IS the call
            elif re.search(rf'\b{re.escape(callee_name)}\s*\(', context):
                found = True

            if found:
                verified += 1
            else:
                rel_path = caller_path.split("/RamPump/")[-1] if "/RamPump/" in caller_path else caller_path
                actual_line = _read_line(caller_path, call_line).strip()
                false_positives.append({
                    "caller": f"{caller_name} in {rel_path}:{call_line}",
                    "callee": callee_name,
                    "full_call": full_call,
                    "actual_line": actual_line[:120],
                })

        total = len(rows)
        fp_count = len(false_positives)
        unv_count = len(unverifiable)
        precision = verified / max(total - unv_count, 1)

        # Print report
        print(f"\n{'='*70}")
        print(f"  CALLS Edge Validation Report")
        print(f"{'='*70}")
        print(f"  Total sampled:      {total}")
        print(f"  Verified correct:   {verified}")
        print(f"  False positives:    {fp_count}")
        print(f"  Unverifiable:       {unv_count}")
        print(f"  Precision:          {precision:.1%}")

        if false_positives:
            print(f"\n  --- False Positives ---")
            for fp in false_positives:
                print(f"  CALLER: {fp['caller']}")
                print(f"  CALLEE: {fp['callee']} (full: {fp['full_call']})")
                print(f"  ACTUAL: {fp['actual_line']}")
                print()

        if unverifiable:
            print(f"\n  --- Unverifiable ({unv_count}) ---")
            for u in unverifiable[:5]:
                print(f"  {u}")
            if unv_count > 5:
                print(f"  ... and {unv_count - 5} more")

        print()

        # Assertion: precision must be >= 95%
        assert precision >= 0.95, (
            f"CALLS precision {precision:.1%} is below 95%. "
            f"False positives: {fp_count}/{total - unv_count}"
        )


class TestInheritsValidation:
    """Sample 50 random INHERITS edges and verify against source code."""

    def test_inherits_source_verification(self):
        result = cypher_query(
            "MATCH (child:Class)-[:INHERITS]->(parent:Class) "
            "WHERE child.path CONTAINS '/RamPump/' "
            "AND child.line_number IS NOT NULL "
            "AND child.line_number > 0 "
            "WITH child, parent, rand() AS rnd "
            "ORDER BY rnd "
            "RETURN child.name AS child_name, "
            "       child.path AS child_path, "
            "       child.line_number AS child_line, "
            "       parent.name AS parent_name, "
            "       parent.path AS parent_path "
            "LIMIT 50",
            timeout=60,
        )
        rows = result.get("results", [])
        assert len(rows) > 0, "No INHERITS edges returned"

        verified = 0
        false_positives = []
        unverifiable = []

        for row in rows:
            child_name = row.get("child_name", "")
            child_path = row.get("child_path", "")
            child_line = row.get("child_line", 0)
            parent_name = row.get("parent_name", "")

            if not child_path or not child_line or child_line <= 0:
                unverifiable.append({
                    "reason": "missing path or line",
                    "child": child_name,
                    "parent": parent_name,
                })
                continue

            if not Path(child_path).exists():
                unverifiable.append({
                    "reason": "file not found",
                    "child_path": child_path,
                    "parent": parent_name,
                })
                continue

            # Read the class definition line and a few lines around it
            # (class definitions can span multiple lines with long base lists)
            context = _read_lines(child_path, child_line, window=5)
            if not context:
                unverifiable.append({
                    "reason": "could not read file",
                    "child_path": child_path,
                    "child_line": child_line,
                    "parent": parent_name,
                })
                continue

            # Check if the class definition mentions the parent class.
            # Patterns:
            #   class Child(Parent):
            #   class Child(module.Parent):
            #   class Child(Parent, OtherMixin):
            found = False

            # Check for "class ChildName(" followed by parent name somewhere
            # in the base class list (may span lines)
            if re.search(rf'class\s+{re.escape(child_name)}\s*\(', context):
                # Parent name should appear in the parenthesized base list
                if parent_name in context:
                    found = True

            if found:
                verified += 1
            else:
                rel_path = child_path.split("/RamPump/")[-1] if "/RamPump/" in child_path else child_path
                actual_line = _read_line(child_path, child_line).strip()
                false_positives.append({
                    "child": f"{child_name} in {rel_path}:{child_line}",
                    "parent": parent_name,
                    "actual_line": actual_line[:120],
                })

        total = len(rows)
        fp_count = len(false_positives)
        unv_count = len(unverifiable)
        precision = verified / max(total - unv_count, 1)

        print(f"\n{'='*70}")
        print(f"  INHERITS Edge Validation Report")
        print(f"{'='*70}")
        print(f"  Total sampled:      {total}")
        print(f"  Verified correct:   {verified}")
        print(f"  False positives:    {fp_count}")
        print(f"  Unverifiable:       {unv_count}")
        print(f"  Precision:          {precision:.1%}")

        if false_positives:
            print(f"\n  --- False Positives ---")
            for fp in false_positives:
                print(f"  CHILD:  {fp['child']}")
                print(f"  PARENT: {fp['parent']}")
                print(f"  ACTUAL: {fp['actual_line']}")
                print()

        if unverifiable:
            print(f"\n  --- Unverifiable ({unv_count}) ---")
            for u in unverifiable[:5]:
                print(f"  {u}")
            if unv_count > 5:
                print(f"  ... and {unv_count - 5} more")

        print()

        assert precision >= 0.95, (
            f"INHERITS precision {precision:.1%} is below 95%. "
            f"False positives: {fp_count}/{total - unv_count}"
        )
