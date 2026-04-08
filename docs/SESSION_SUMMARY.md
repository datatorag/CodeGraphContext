# Session Summary — CodeGraphContext Mac App + Performance

## What Was Built

### 1. HTTP Transport for MCP Server
- Added `--transport http --port 47321` to `cgc mcp start`
- `POST /mcp` (JSON-RPC) + `GET /health` endpoints via FastAPI/uvicorn
- Server starts independently of database — auto-reconnects on first tool call

### 2. Mac Menu Bar App (Swift)
- `macos-app/` — SwiftUI menu bar app managing CGC lifecycle
- Starts FalkorDB (bundled redis-server + falkordb.so) as subprocess
- Starts CGC MCP server (`cgc mcp start --transport http --port 47321`)
- Status indicator (green/red), repo indexing via folder picker, settings
- No external dependencies

### 3. Claude Code Plugin
- `claude-plugin/` — `.mcp.json` pointing to `http://localhost:47321/mcp`
- Skills for `index-repo` and `explore-code`

### 4. Bundled FalkorDB
- `scripts/bundle-falkordb.sh` downloads `redis-server` (2.7MB) + `falkordb.so` (30MB ARM64 macOS)
- Mac app manages redis-server directly via Swift Process — no redislite wrapper
- Data at `~/Library/Application Support/CodeGraphContext/falkordb/`
- CGC connects via `falkordb-remote` (TCP localhost:6379)

### 5. Vue SFC Parser
- `.vue` files parsed by extracting `<script>` content → JavaScript parser
- 1,315 Vue files in RamPump now indexed

## Performance Optimizations

### Indexing Pipeline (graph_builder.py)
| Optimization | Impact |
|-------------|--------|
| Batch directory hierarchy | Per-file O(depth) queries → 5 total |
| Cross-file batch writes (`add_files_to_graph_batch`) | Per-file 6 queries → ~10 total per type |
| Parse-all-then-write-all | Clear phase separation, single batch |
| CREATE instead of MERGE | Skip existence check for fresh repos |
| 5K UNWIND chunks + combined queries | 84 queries → ~10 |
| Concurrent thread pool | Parallel node type writes |
| Skip vendor/minified files | 7,744 → 5,542 files (*.min.js, vendor/, bower/) |
| Strict call resolver | 600K → 28K CALLS edges |
| Skip <=2 char function names | Filter minified JS artifacts |

### RamPump Results (5,542 code files)
- **9m 15s** standalone, **13m 25s** via Mac app
- 148,793 nodes + 211,503 edges
- 28,229 CALLS (was 600K+ before resolver fix)
- Phases: parsing ~2m, node creation ~3.5m, relationship linking ~3.5m

### Server Improvements
- Non-blocking HTTP: indexing runs in background thread, server stays responsive
- Progress tracking: phase, nodes_created, avg_ms_per_file, ETA
- Lazy DB reconnection: MCP starts without DB, connects on demand

## Key Files Changed

### Python (src/codegraphcontext/)
- `server.py` — HTTP transport (`run_http`), lazy DB reconnection, non-blocking tool calls
- `tools/graph_builder.py` — `add_files_to_graph_batch`, `_create_directory_hierarchy_batch`, `_normalize_batch`, `build_graph_from_path_sync`, Vue parser, strict call resolver, vendor/minified filtering
- `tools/handlers/indexing_handlers.py` — threading.Thread instead of asyncio
- `tools/handlers/management_handlers.py` — richer check_job_status
- `core/jobs.py` — phase, nodes_created, edges_created, avg_ms_per_file
- `core/database_falkordb.py` — connection retry loop
- `core/database_kuzu.py` — coalesce() regex fix
- `cli/main.py` — --transport and --port flags

### Swift (macos-app/)
- `PythonManager.swift` — FalkorDB process management, MCP/viz subprocess lifecycle, PATH fixes
- `AppState.swift` — auto-start on init
- `CodeGraphContextApp.swift` — menu bar setup
- `SettingsView.swift` — port/DB config UI
- `scripts/bundle-falkordb.sh` — download ARM64 binaries
- `scripts/bundle-python.sh` — Python venv bundling

### Config
- `claude-plugin/.claude-plugin/.mcp.json` — plugin config
- `docs/plans/2026-04-06-mac-app-plugin.md` — implementation plan
- `docs/PERFORMANCE_IMPROVEMENTS.md` — detailed optimization log

## Current Architecture

```
Mac App (Swift)
  ├── redis-server + falkordb.so  (port 6379, managed subprocess)
  ├── cgc mcp start --transport http --port 47321  (Python subprocess)
  │     └── connects to FalkorDB via falkordb-remote (TCP)
  └── cgc visualize --port 47322  (Python subprocess)

Claude Code Plugin
  └── .mcp.json → http://localhost:47321/mcp
```

## Database
- **Backend**: Standalone FalkorDB (redis-server + falkordb.so, ARM64 macOS)
- **Connection**: falkordb-remote via TCP localhost:6379
- **Persistence**: `~/Library/Application Support/CodeGraphContext/falkordb/dump.rdb`
- **Default ports**: MCP 47321, Viz 47322, FalkorDB 6379

## Known Issues
- FalkorDB Lite (redislite wrapper) crashes under heavy writes — use standalone binary instead
- Call resolver still generates some false positives for common JS function names
- Variables/Parameters are 76% of node count — could defer to second pass for faster initial index
- Vue parser only extracts first `<script>` block (misses `<script setup>` if both present)
