# CodeGraphContext Mac App + Claude Code Plugin

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Package CodeGraphContext as a native Mac menu bar app (Swift) that bundles FalkorDB Lite + the MCP server, with a Claude Code plugin for the Life360 marketplace.

**Architecture:** A Swift menu bar app manages the lifecycle of FalkorDB Lite (embedded) and the CGC MCP server (Python subprocess). It exposes the MCP server over HTTP on localhost for Claude Code to connect to. A WebView panel renders the existing React visualization. A lightweight Claude Code plugin provides the `.mcp.json` config and skills for the Life360 plugin marketplace.

**Tech Stack:** Swift/SwiftUI, WKWebView, FalkorDB Lite (embedded), Python (CGC MCP server), FastAPI (visualization), Claude Code plugin system

---

## Open Decisions

- [ ] **Business logic annotations (Phase 2):** AI-generated domain context stored as node/edge properties. Deferred to after core app works.
- [ ] **Neo4j remote option:** Allow connecting to a shared Neo4j instance for team use. Deferred to after FalkorDB Lite works locally.

---

## Phase 1: MCP Server HTTP Transport

CGC's MCP server currently uses stdio. The Mac app needs to connect to it as a long-running background process, and Claude Code needs to reach it over localhost. Add HTTP transport.

### Task 1: Add HTTP transport to MCP server

**Files:**
- Modify: `src/codegraphcontext/server.py`
- Modify: `src/codegraphcontext/cli/main.py` (add `mcp start --transport http --port 47321` flag)

**Step 1:** Add `--transport` and `--port` flags to the `mcp start` CLI command.

- `--transport stdio` (default, existing behavior)
- `--transport http` (new, starts an HTTP server on `--port 47321`)

**Step 2:** In `server.py`, add an HTTP transport mode alongside the existing stdio loop.

- Use the existing FastAPI from `viz/server.py` or a minimal new one
- Single endpoint: `POST /mcp` accepting JSON-RPC requests, returning JSON-RPC responses
- Reuse `handle_tool_call()` and all existing tool handlers
- Add `GET /health` endpoint returning `{"status": "ok", "version": "0.3.9"}`

**Step 3:** Test manually:
```bash
cgc mcp start --transport http --port 47321
# In another terminal:
curl -X POST http://localhost:47321/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/list","id":1}'
```

**Step 4:** Commit.
```bash
git add src/codegraphcontext/server.py src/codegraphcontext/cli/main.py
git commit -m "feat: add HTTP transport mode for MCP server"
```

---

## Phase 2: Mac App (Swift)

### Task 2: Xcode project scaffold

**Files:**
- Create: `macos-app/CodeGraphContext.xcodeproj`
- Create: `macos-app/CodeGraphContext/CodeGraphContextApp.swift` (entry point)
- Create: `macos-app/CodeGraphContext/MenuBarManager.swift`
- Create: `macos-app/CodeGraphContext/Info.plist`

**Step 1:** Create a new macOS app target in Xcode.

- App type: Menu bar app (no dock icon by default)
- Minimum deployment: macOS 14 (Sonnet)
- SwiftUI lifecycle

**Step 2:** Implement `MenuBarManager.swift`:

- Menu bar icon (graph icon or CGC logo)
- Menu items:
  - Status indicator (green dot = running, red = stopped)
  - "Open Visualization" (opens WebView window)
  - "Indexed Repositories" (submenu listing repos)
  - "Index Repository..." (folder picker)
  - Separator
  - "Settings..."
  - "Quit"

**Step 3:** Build and run. Verify menu bar icon appears with placeholder menu.

**Step 4:** Commit.

### Task 3: Bundle and manage Python + CGC subprocess

**Files:**
- Create: `macos-app/CodeGraphContext/PythonManager.swift`
- Create: `macos-app/scripts/bundle-python.sh` (build script)

**Step 1:** Create `bundle-python.sh` that:

- Creates a standalone Python environment (using `python3 -m venv` or `conda-pack`)
- Installs `codegraphcontext` + dependencies into it
- Copies the venv into the app bundle's `Resources/python/` directory

**Step 2:** Implement `PythonManager.swift`:

- Locate bundled Python in `Bundle.main.resourceURL`
- Start CGC MCP server as a subprocess: `python -m codegraphcontext.cli.main mcp start --transport http --port 47321`
- Monitor subprocess health (restart if crashes)
- Capture stdout/stderr for logging
- Graceful shutdown on app quit

**Step 3:** On app launch, start the Python subprocess. Verify `http://localhost:47321/health` returns OK.

**Step 4:** Commit.

### Task 4: Bundle FalkorDB Lite

**Files:**
- Modify: `macos-app/scripts/bundle-python.sh` (add FalkorDB Lite to pip install)
- Modify: `macos-app/CodeGraphContext/PythonManager.swift` (set env vars)

**Step 1:** Add `falkordb` to the bundled Python environment.

**Step 2:** Set environment variables before launching the CGC subprocess:
```
CGC_RUNTIME_DB_TYPE=falkordb
FALKORDB_PATH=~/Library/Application Support/CodeGraphContext/falkordb.db
```

**Step 3:** Verify FalkorDB Lite initializes on MCP server startup. Index a small test repo.

**Step 4:** Commit.

### Task 5: Visualization WebView

**Files:**
- Create: `macos-app/CodeGraphContext/VisualizationWindow.swift`
- Modify: `macos-app/CodeGraphContext/MenuBarManager.swift` (wire up "Open Visualization")

**Step 1:** Implement `VisualizationWindow.swift`:

- SwiftUI window with `WKWebView`
- Points to `http://localhost:47322` (the existing FastAPI viz server)
- Window title: "CodeGraphContext - [repo name]"
- Standard window controls (resize, minimize, close)

**Step 2:** Modify `PythonManager.swift` to also start the visualization server:
```
cgc visualize --port 47322 --no-browser
```
Or serve it from the same process if the MCP server can host both.

**Step 3:** Click "Open Visualization" in menu bar. Verify the React graph UI loads in the WebView.

**Step 4:** Commit.

### Task 6: Repository indexing UI

**Files:**
- Create: `macos-app/CodeGraphContext/IndexingManager.swift`
- Modify: `macos-app/CodeGraphContext/MenuBarManager.swift`

**Step 1:** Implement "Index Repository..." menu action:

- Opens a folder picker (`NSOpenPanel`)
- Sends an index request to the MCP server: `POST /mcp` with `add_code_to_graph` tool call
- Shows progress in the menu bar (spinning indicator or progress text)

**Step 2:** Implement "Indexed Repositories" submenu:

- Queries the MCP server for `list_repos`
- Shows repo names with status (indexed, watching, etc.)

**Step 3:** Index RamPump via the UI. Verify it completes and shows in the submenu.

**Step 4:** Commit.

### Task 7: Settings and auto-launch

**Files:**
- Create: `macos-app/CodeGraphContext/SettingsView.swift`
- Modify: `macos-app/CodeGraphContext/Info.plist` (LSUIElement for menu-bar-only)

**Step 1:** Implement `SettingsView.swift` (SwiftUI):

- MCP server port (default 47321)
- Visualization port (default 8000)
- Auto-launch on login toggle (uses `SMAppService`)
- Database path display
- Repos to auto-index on launch

**Step 2:** Set `LSUIElement = YES` in Info.plist (hides from dock, menu-bar-only app).

**Step 3:** Commit.

---

## Phase 3: Claude Code Plugin

### Task 8: Plugin scaffold

**Files:**
- Create: `claude-plugin/.claude-plugin/plugin.json`
- Create: `claude-plugin/.claude-plugin/.mcp.json`
- Create: `claude-plugin/README.md`

**Step 1:** Create `plugin.json`:
```json
{
  "name": "codegraphcontext",
  "description": "Code graph analysis for large codebases. Index repos into a graph, query relationships, find dead code, visualize architecture.",
  "version": "1.0.0",
  "author": {
    "name": "CodeGraphContext"
  }
}
```

**Step 2:** Create `.mcp.json`:
```json
{
  "mcpServers": {
    "codegraphcontext": {
      "type": "http",
      "url": "http://localhost:47321/mcp"
    }
  }
}
```

**Step 3:** Create README with:
- What it does
- Prerequisites (CodeGraphContext Mac app running)
- Available tools (20+ from CGC)
- Example usage in Claude Code

**Step 4:** Commit.

### Task 9: Skills for common operations

**Files:**
- Create: `claude-plugin/skills/index-repo/SKILL.md`
- Create: `claude-plugin/skills/explore-code/SKILL.md`

**Step 1:** Create `index-repo` skill:
- Guides Claude through indexing a new repo
- Checks if CGC server is running (health endpoint)
- Calls `add_code_to_graph` with the project path
- Waits for indexing to complete

**Step 2:** Create `explore-code` skill:
- For when user says "explain this codebase" or "how does X work"
- Uses `find_code`, `analyze_code_relationships`, `who_calls_function` tools
- Builds a structured understanding of the code

**Step 3:** Commit.

### Task 10: Marketplace listing

**Files:**
- Modify: Life360 plugin marketplace repo (add CodeGraphContext entry)

**Step 1:** Add entry to the Life360 plugin marketplace `marketplace.json`:
```json
{
  "name": "codegraphcontext",
  "source": {
    "source": "url",
    "url": "https://github.com/CodeGraphContext/CodeGraphContext.git",
    "path": "claude-plugin"
  },
  "version": "1.0.0",
  "description": "Code graph analysis powered by FalkorDB. Index, query, and visualize code relationships.",
  "category": "developer-tools",
  "keywords": ["code-analysis", "graph-database", "architecture"]
}
```

**Step 2:** Commit and push to marketplace repo.

---

## Phase 4: Validation

### Task 11: End-to-end test with RamPump

**Steps:**
1. Launch the Mac app
2. Index `/Users/myang/git/RamPump` via the menu bar
3. Open visualization, verify the graph renders
4. Install the Claude Code plugin from the marketplace
5. In Claude Code, ask: "What calls the main entry point in RamPump?"
6. Verify Claude uses the CGC tools to answer with actual call chain data
7. Ask: "Find dead code in the Python backend"
8. Verify dead code detection returns results

### Task 12: Performance check

**Steps:**
1. Monitor memory usage after indexing RamPump (6,424 files)
2. Target: <1GB RAM for FalkorDB Lite
3. Measure query response time for common operations
4. Target: <500ms for relationship queries
5. If memory exceeds targets, investigate FalkorDB tuning or consider adding Memgraph as future option

---

## Summary

| Phase | Tasks | What it delivers |
|-------|-------|-----------------|
| Phase 1 | Task 1 | MCP server works over HTTP (prerequisite for everything) |
| Phase 2 | Tasks 2-7 | Mac menu bar app with FalkorDB, visualization, indexing |
| Phase 3 | Tasks 8-10 | Claude Code plugin on Life360 marketplace |
| Phase 4 | Tasks 11-12 | Validated on RamPump, performance confirmed |
