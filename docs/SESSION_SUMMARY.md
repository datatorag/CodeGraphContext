# Session Summary — CodeGraphContext

## What Was Built

### 1. HTTP Transport for MCP Server
- `--transport http --port 47321` on `cgc mcp start`
- `POST /mcp` (JSON-RPC) + `GET /health` via FastAPI/uvicorn
- Server starts independently of database — auto-reconnects on first tool call

### 2. Mac Menu Bar App (Swift)
- `macos-app/` — SwiftUI menu bar app managing CGC lifecycle
- Starts FalkorDB (bundled redis-server + falkordb.so) as subprocess
- Starts MCP server + visualization server as subprocesses
- Health checks for all 3 services (FalkorDB, MCP, Viz) — detects external instances
- Status indicators, repo indexing via folder picker, settings

### 3. Bundled FalkorDB
- `scripts/bundle-falkordb.sh` downloads `redis-server` (2.7MB) + `falkordb.so` (30MB ARM64 macOS)
- Mac app manages redis-server directly via Swift Process
- Data at `~/Library/Application Support/CodeGraphContext/falkordb/`

### 4. Precision-First CALLS Resolver
- Resolves `self.method()`, direct calls, imported function calls, `module.func()` calls
- Skips `obj.method()` where obj is not an imported module (can't resolve without type inference)
- Skips chained calls `a.b.c()` (>1 dot) — intermediate type transitions are unknowable
- 95%+ precision on LLM-assisted manual review, 100% on automated strict validation

### 5. Co-Import Parser Fix
- `from X import (A, B, C)` now captures all names (was only capturing first)
- IMPORTS edges +25% (23,942 → 30,010), CALLS edges +42% over original

### 6. Evaluation Test Suite
- `tests/evaluation/` — 36 automated tests measuring accuracy, latency, token efficiency
- Level 2 strict validation: source-level verification of random CALLS/INHERITS samples
- Graph vs grep comparison benchmarks for every test category

### 7. Visualization Server
- Direct FalkorDB connection (bypasses wrapper caching issues)
- Read-only DB init (no schema creation that corrupts graph state)
- Filters Variable/Parameter nodes for manageable default view

## Current Numbers (RamPump, 5,542 code files)

| Metric | Value |
|--------|-------|
| Nodes | 148,793 |
| CALLS edges | ~29K |
| IMPORTS edges | 30,010 |
| INHERITS edges | 1,203 |
| CALLS precision | 95%+ (manual), 100% (automated) |
| Indexing time | ~12 min |

## Architecture

```
Mac App (Swift)
  ├── redis-server + falkordb.so  (port 6379, managed subprocess)
  ├── cgc mcp start --transport http --port 47321  (Python subprocess)
  │     └── connects to FalkorDB via TCP
  └── cgc visualize --port 47322  (Python subprocess)

Claude Code
  └── MCP client → http://localhost:47321/mcp
```

## Key Files

### Call Resolution & Parsing
- `tools/graph_builder.py` — `_resolve_function_call` (precision-first rules), `_create_all_function_calls`, batch writes
- `tools/languages/python.py` — `_find_imports` (co-import fix), `_find_calls`, `pre_scan_python`

### Server & Infrastructure
- `server.py` — HTTP transport, lazy DB reconnection
- `viz/server.py` — Direct FalkorDB connection, structural query
- `cli/cli_helpers.py` — Read-only DB init for viz (no GraphBuilder schema)

### Mac App
- `PythonManager.swift` — Health checks for FalkorDB/MCP/Viz, subprocess management
- `MenuBarManager.swift` — Status indicators for all 3 services
- `VisualizationWindow.swift` — Opens /explore with backend parameter

### Tests
- `tests/evaluation/` — 36 tests: completeness, callers, relationships, edge cases, graph queries
- `test_level2_validation.py` — Random sampling source verification
- `test_level2_strict.py` — Strict call syntax verification

## Known Limitations
- Chained calls `a.b.c()` are skipped — requires type inference
- `obj.method()` on local variables skipped — same reason
- Factory/decorator patterns (dynamic tool registration) not captured
- Vue parser only extracts first `<script>` block
