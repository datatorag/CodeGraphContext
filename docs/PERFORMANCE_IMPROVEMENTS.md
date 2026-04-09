# Indexing Performance & Accuracy

> CodeGraphContext graph indexing pipeline — performance benchmarks, accuracy validation, and call resolution design.

## Current Results (RamPump, 5,542 code files)

| Metric | Value |
|--------|-------|
| **Total indexing time** | ~12 min |
| **Nodes** | 148,793 |
| **CALLS edges** | ~29K |
| **IMPORTS edges** | 30,010 |
| **INHERITS edges** | 1,203 |
| **CALLS precision** | 95%+ (manual review of 20 random edges) |
| **CALLS strict precision** | 100% (automated, 4×150 edge samples) |
| **INHERITS precision** | 100% (50-edge random samples) |
| **False positive rate** | 0% automated, ~5% on LLM-assisted manual review |

### Indexing Phases

| Phase | Time | Details |
|-------|------|---------|
| Parsing | ~2 min | 5,542 code files via tree-sitter (vendor/minified excluded) |
| Node creation | ~5 min | 148K nodes via batched CREATE + thread pool |
| Relationship linking | ~5 min | CALLS + INHERITS + IMPORTS edges |

---

## CALLS Resolver Design

The CALLS resolver is precision-first: it only creates edges it's confident about. The graph is designed to supplement Claude Code — Claude can grep to fill recall gaps, but false positives send Claude down wrong paths and waste tokens.

### Resolution Rules

| Rule | Pattern | Resolution | Example |
|------|---------|------------|---------|
| 1 | `self.method()` | Same file | `self.authenticate()` → current file |
| 2 | `func()` where func is defined locally | Same file | `_helper()` → current file |
| 3 | `func()` where func is imported | Resolve via import path | `authenticate()` with `from X import authenticate` |
| 4 | `module.func()` where module is imported | Resolve func within module | `user_service.authenticate()` → `services/user/actions.py` |
| — | `obj.method()` where obj is NOT imported | **Skip** | `settings.get()`, `response.json()` |
| — | `a.b.c()` (chained, >1 dot) | **Skip** | `Model.query.options()`, `os.path.join()` |
| — | Builtins, <=2 char names | **Skip** | `len()`, `int()`, `a()` |

### Why Skip obj.method()?

Without type inference, we can't know what type `obj` is. `settings.get()` could be `dict.get` or a function named `get` in another file. `response.json()` could be `requests.Response.json` or a local function. Any resolution is a guess, and guesses create false positives that waste Claude's tokens.

Claude can grep for `\.method_name\(` in seconds — the graph doesn't need to duplicate that.

### Why Skip Chained Calls?

`MarketplaceAccess.query.options()` — `MarketplaceAccess` is imported, but `.query` returns a SQLAlchemy Query object, and `.options()` is a method on that object. The resolver only sees the first part (`MarketplaceAccess`) and the last part (`options`), missing the intermediate type transition. Single-dot calls (`module.func()`) are safe because modules expose functions directly.

### Co-Import Fix

`from X import (A, B, C)` was only capturing `A` — tree-sitter's `child_by_field_name('name')` returns the first match. Fixed to iterate all children of the import statement. This increased IMPORTS edges by 25% (23,942 → 30,010) and was the root cause of many missed CALLS edges.

### Import Path Resolution

`local_imports` now stores `full_import_name` (e.g. `nativo_mcp.tools.call_controller`) instead of bare `name` (`call_controller`). The resolver strips the function name to get the module path (`nativo_mcp/tools`) and matches against file paths (`nativo_mcp/tools/__init__.py`). This fixed cross-package call resolution.

---

## Accuracy Validation

### Level 1: Automated Eval Suite (36 tests)

| Category | Tests | Key Results |
|----------|-------|-------------|
| Data completeness | 7 | Python files: graph 2,538 vs disk 2,534 (100%) |
| Find callers | 2 | authenticate: 6/6 callers found, 100% precision |
| Find code | 4 | Cross-language search 1,518x faster than grep |
| Relationships | 6 | 8/8 known CALLS, 4/4 INHERITS, 0% FP rate |
| Edge cases | 7 | __init__ re-exports, decorators, Vue SFC all pass |
| Graph queries | 6 | Dead code, impact analysis, module coupling |

### Level 2: Source-Level Verification

Random sampling with `rand() ORDER BY` — each run is independent.

| Test | Method | Samples | Precision |
|------|--------|---------|-----------|
| CALLS (automated) | Regex: `name(` near reported line | 4×100 | 100% |
| CALLS (strict) | Excludes comments, strings, imports, defs | 4×100 | 100% |
| CALLS (LLM review) | Manual inspection of source context | 20 | 95% |
| INHERITS (automated) | `class Child(Parent)` at reported line | 4×50 | 100% |

The 5% gap between automated and LLM review is from chained calls (`Model.query.options()`) which the automated checker can't distinguish from valid `module.func()` calls. The chained-call fix eliminates this category.

### Graph vs Grep Comparison

| Query | Graph | Grep | Graph Advantage |
|-------|-------|------|-----------------|
| Python file count | 24ms, 175 chars | 1,776ms, 172K chars | 74x faster, 988x fewer tokens |
| Find callers of authenticate | 8ms, structured | 5ms, raw text | Precise targets vs text mentions |
| Class hierarchy (multi-hop) | 4ms, full chain | 3× sequential greps | Single query vs iterative |
| Dead code detection | 25ms | ~263 seconds | Infeasible with grep |
| Cross-language search | 9ms | 13,663ms | 1,518x faster |

**Key insight**: The graph's value isn't replacing grep — it's making Claude's first pass accurate. Instead of grep → read → grep → read (3-4 iterations), one graph query returns precise answers with file paths and line numbers. The token savings compound across iterations.

---

## Indexing Pipeline Optimizations

### Summary (76-file benchmark)

| Version | DB Write/File | Total | Round Trips | Key Change |
|---------|--------------|-------|-------------|------------|
| v0 (baseline) | 43.1 ms | 6.37s | ~456 | Per-file MERGE |
| v1 (dir batch) | 30.9 ms | 4.64s | ~380 | Batch directory hierarchy |
| v2 (cross-file batch) | 25.2 ms | 4.11s | ~12 | Accumulate across files |
| v3 (parse-then-write) | 26.1 ms | 4.29s | ~12 | Clear phase separation |
| v4 (chunks + combined) | 4.5 ms | 2.72s | ~6 | 50K chunks, CREATE+CONTAINS |

**Overall: 6.37s → 2.72s (57% faster), round trips: 456 → 6 (99% reduction)**

### Key Optimizations

- **Batch directory hierarchy**: Per-file O(depth) → 5 total queries
- **Cross-file batch writes**: Per-file 6 queries → ~10 total per type
- **CREATE instead of MERGE**: Skip existence check for fresh repos
- **5K UNWIND chunks + combined queries**: 84 queries → ~10
- **Thread pool**: Parallel node type writes
- **Skip vendor/minified**: 7,744 → 5,542 files

---

## Architecture

```
[Parse Phase]
  files → tree-sitter → file_data[]  (CPU-bound, ~12ms/file)

[Write Phase]
  file_data[] → add_files_to_graph_batch()
    → UNWIND File nodes      (1 query)
    → UNWIND Function nodes  (1 query, all files)
    → UNWIND Class nodes     (1 query)
    → UNWIND Parameters      (1 query)
    → UNWIND Imports          (1 query)
    → Directory hierarchy    (~5 queries)
  Total: ~10 queries regardless of file count

[Relationship Phase]
  → _create_all_inheritance_links()  (batched at 1000)
  → _create_all_function_calls()    (precision-first resolver, label-specific)
```

## Database

**Standalone FalkorDB** — bundled `redis-server` + `falkordb.so` (ARM64 macOS), managed directly by the Mac app as a subprocess.

- `redis-server` (2.7MB) + `falkordb.so` (30MB) via `scripts/bundle-falkordb.sh`
- Data: `~/Library/Application Support/CodeGraphContext/falkordb/`
- MCP server connects via TCP localhost:6379
- MCP server starts independently — auto-reconnects when FalkorDB becomes available
