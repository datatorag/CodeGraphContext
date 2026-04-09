"""Level 3 LLM-Assisted Validation: Claude reviews graph edges against source code.

Samples random CALLS and INHERITS edges, reads the actual source files,
and asks Claude to verify whether the relationship is real. This catches
semantic false positives that regex-based checks miss (e.g., dict.get()
resolved to a controller's get() method).

Requires: `claude` CLI installed and authenticated.
Run with: pytest tests/evaluation/test_llm_validation.py -v -s
"""

import json
import subprocess
from pathlib import Path

import pytest

from helpers import cypher_query, RAMPUMP_ROOT


def _read_context(filepath: str, center_line: int, window: int = 15) -> str:
    """Read lines around center_line with line numbers."""
    try:
        lines = Path(filepath).read_text(encoding="utf-8", errors="replace").splitlines()
        start = max(0, center_line - 1 - window)
        end = min(len(lines), center_line - 1 + window + 1)
        result = []
        for i in range(start, end):
            marker = ">>>" if i == center_line - 1 else "   "
            result.append(f"{marker} {i+1:4d} | {lines[i]}")
        return "\n".join(result)
    except Exception:
        return "(could not read file)"


def _ask_claude(prompt: str, timeout: int = 30) -> str:
    """Ask Claude a question via the CLI and return the response."""
    result = subprocess.run(
        ["claude", "-p", prompt, "--output-format", "text"],
        capture_output=True, text=True, timeout=timeout,
    )
    return result.stdout.strip()


def _verify_calls_edge(caller_name, caller_path, callee_name, callee_path,
                       call_line, full_call) -> dict:
    """Ask Claude to verify a single CALLS edge."""
    rel_caller = caller_path.split("/RamPump/")[-1] if "/RamPump/" in caller_path else caller_path
    rel_callee = callee_path.split("/RamPump/")[-1] if "/RamPump/" in callee_path else callee_path

    source_context = _read_context(caller_path, call_line)

    prompt = f"""You are verifying a code graph edge. Answer ONLY with a JSON object, no other text.

EDGE: Function "{caller_name}" in {rel_caller} CALLS function "{callee_name}" in {rel_callee}
Full call expression: {full_call}
Reported call at line {call_line}.

Source code around line {call_line} of {rel_caller}:
```
{source_context}
```

Verify:
1. Does the source at/near line {call_line} actually call "{callee_name}" (or a dotted variant like module.{callee_name})?
2. Is the target file ({rel_callee}) a plausible location for the called function? (e.g., if the call is datetime.now(), the target should NOT be a random user file)

Respond with ONLY this JSON (no markdown, no explanation):
{{"verdict": "correct" or "false_positive" or "uncertain", "reason": "one sentence"}}"""

    try:
        response = _ask_claude(prompt, timeout=30)
        # Parse JSON from response (handle markdown wrapping)
        response = response.strip()
        if response.startswith("```"):
            response = response.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        return json.loads(response)
    except (json.JSONDecodeError, subprocess.TimeoutExpired) as e:
        return {"verdict": "error", "reason": str(e)}


def _verify_inherits_edge(child_name, child_path, child_line, parent_name) -> dict:
    """Ask Claude to verify a single INHERITS edge."""
    rel_path = child_path.split("/RamPump/")[-1] if "/RamPump/" in child_path else child_path
    source_context = _read_context(child_path, child_line)

    prompt = f"""You are verifying a code graph edge. Answer ONLY with a JSON object, no other text.

EDGE: Class "{child_name}" in {rel_path} INHERITS from class "{parent_name}"
Class defined at line {child_line}.

Source code around line {child_line}:
```
{source_context}
```

Verify: Does the class definition for "{child_name}" actually list "{parent_name}" as a base class / parent class?

Respond with ONLY this JSON (no markdown, no explanation):
{{"verdict": "correct" or "false_positive" or "uncertain", "reason": "one sentence"}}"""

    try:
        response = _ask_claude(prompt, timeout=30)
        response = response.strip()
        if response.startswith("```"):
            response = response.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        return json.loads(response)
    except (json.JSONDecodeError, subprocess.TimeoutExpired) as e:
        return {"verdict": "error", "reason": str(e)}


class TestLLMCallsValidation:
    """Sample 50 random CALLS edges and have Claude verify each one."""

    def test_calls_llm_review(self):
        result = cypher_query(
            "MATCH (caller)-[r:CALLS]->(callee) "
            "WHERE caller.path CONTAINS '/RamPump/' "
            "AND r.line_number IS NOT NULL AND r.line_number > 0 "
            "WITH caller, r, callee, rand() AS rnd ORDER BY rnd "
            "RETURN caller.name AS caller_name, "
            "       caller.path AS caller_path, "
            "       callee.name AS callee_name, "
            "       callee.path AS callee_path, "
            "       r.line_number AS call_line, "
            "       r.full_call_name AS full_call "
            "LIMIT 50",
            timeout=60,
        )
        rows = result.get("results", [])
        assert len(rows) > 0, "No CALLS edges returned"

        correct = 0
        false_positives = []
        uncertain = []
        errors = []

        for i, row in enumerate(rows):
            verdict = _verify_calls_edge(
                row["caller_name"], row["caller_path"],
                row["callee_name"], row["callee_path"],
                row["call_line"], row.get("full_call", row["callee_name"]),
            )

            rel_caller = row["caller_path"].split("/RamPump/")[-1]
            label = f"{row['caller_name']} → {row['callee_name']} ({rel_caller}:{row['call_line']})"

            v = verdict.get("verdict", "error")
            reason = verdict.get("reason", "")

            if v == "correct":
                correct += 1
                print(f"  {i+1:2d}. OK  {label}")
            elif v == "false_positive":
                false_positives.append({"edge": label, "reason": reason})
                print(f"  {i+1:2d}. FP  {label} — {reason}")
            elif v == "uncertain":
                uncertain.append({"edge": label, "reason": reason})
                print(f"  {i+1:2d}. ??  {label} — {reason}")
            else:
                errors.append({"edge": label, "reason": reason})
                print(f"  {i+1:2d}. ERR {label} — {reason}")

        total = len(rows)
        checkable = total - len(errors)
        precision = correct / max(checkable, 1)

        print(f"\n{'='*60}")
        print(f"  CALLS LLM Validation ({total} edges)")
        print(f"{'='*60}")
        print(f"  Correct:        {correct}")
        print(f"  False positive: {len(false_positives)}")
        print(f"  Uncertain:      {len(uncertain)}")
        print(f"  Errors:         {len(errors)}")
        print(f"  Precision:      {precision:.0%}")

        if false_positives:
            print(f"\n  --- False Positives ---")
            for fp in false_positives:
                print(f"  {fp['edge']}")
                print(f"    Reason: {fp['reason']}")

        # Target: >=90% precision on 50 samples (≤5 FPs)
        assert len(false_positives) <= 5, (
            f"Too many FPs: {len(false_positives)}/{checkable}. "
            f"Details: {[fp['edge'] for fp in false_positives]}"
        )


class TestLLMInheritsValidation:
    """Sample 50 random INHERITS edges and have Claude verify each one."""

    def test_inherits_llm_review(self):
        result = cypher_query(
            "MATCH (child:Class)-[:INHERITS]->(parent:Class) "
            "WHERE child.path CONTAINS '/RamPump/' "
            "AND child.line_number IS NOT NULL AND child.line_number > 0 "
            "WITH child, parent, rand() AS rnd ORDER BY rnd "
            "RETURN child.name AS child_name, "
            "       child.path AS child_path, "
            "       child.line_number AS child_line, "
            "       parent.name AS parent_name "
            "LIMIT 50",
            timeout=60,
        )
        rows = result.get("results", [])
        assert len(rows) > 0, "No INHERITS edges returned"

        correct = 0
        false_positives = []
        errors = []

        for i, row in enumerate(rows):
            verdict = _verify_inherits_edge(
                row["child_name"], row["child_path"],
                row["child_line"], row["parent_name"],
            )

            rel_path = row["child_path"].split("/RamPump/")[-1]
            label = f"{row['child_name']} → {row['parent_name']} ({rel_path}:{row['child_line']})"

            v = verdict.get("verdict", "error")
            reason = verdict.get("reason", "")

            if v == "correct":
                correct += 1
                print(f"  {i+1:2d}. OK  {label}")
            elif v == "false_positive":
                false_positives.append({"edge": label, "reason": reason})
                print(f"  {i+1:2d}. FP  {label} — {reason}")
            else:
                errors.append({"edge": label, "reason": reason})
                print(f"  {i+1:2d}. ERR {label} — {reason}")

        total = len(rows)
        checkable = total - len(errors)
        precision = correct / max(checkable, 1)

        print(f"\n{'='*60}")
        print(f"  INHERITS LLM Validation ({total} edges)")
        print(f"{'='*60}")
        print(f"  Correct:        {correct}")
        print(f"  False positive: {len(false_positives)}")
        print(f"  Errors:         {len(errors)}")
        print(f"  Precision:      {precision:.0%}")

        assert len(false_positives) == 0, (
            f"INHERITS FPs: {[fp['edge'] for fp in false_positives]}"
        )
