# Getting Started with CodeGraphContext

## What is CodeGraphContext?

CodeGraphContext gives Claude Code structural understanding of your codebase. It parses your code into a graph database (functions, classes, imports, call relationships, inheritance), then exposes that graph via MCP tools. Claude can query "who calls this function?", "find dead code", or "what breaks if I change this class?" in milliseconds instead of grepping thousands of files.

## Installation (Mac)

### 1. Clone and build

```bash
git clone https://github.com/DataToRag/CodeGraphContext.git
cd CodeGraphContext

# Install the Python package
pip install -e .

# Build the Mac app
cd macos-app
swift build -c release
```

### 2. Download FalkorDB binaries

```bash
cd macos-app
bash scripts/bundle-falkordb.sh
```

This downloads `redis-server` and `falkordb.so` to `macos-app/build/falkordb/`.

### 3. Launch the Mac app

```bash
./macos-app/.build/release/CodeGraphContext
```

A menu bar icon appears (graph icon + colored dot):
- **Green dot** — all services running
- **Yellow dot** — indexing in progress
- **Red dot** — FalkorDB or MCP server down

The app starts three services automatically:
- FalkorDB on port 6379
- MCP server on port 47321
- Visualization on port 47322

## Index Your First Repo

1. Click the menu bar icon
2. Click **Index Repository...**
3. Select your project folder (must be a git repo)
4. Wait for indexing to complete (status shows in the menu)

Typical times:
- 1K files: ~2 minutes
- 5K files: ~13 minutes
- 10K+ files: ~25 minutes

Once done, your repo appears in the menu with a watch icon (auto-syncs as you edit files).

## Connect to Claude Code

### Option A: Plugin (recommended)

```bash
claude plugin install codegraphcontext
```

### Option B: Manual MCP config

Add to your project's `.mcp.json`:

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

Then restart Claude Code. It will discover the MCP tools automatically.

## Try It Out

Open Claude Code in your indexed project and try these prompts:

```
Who calls the authenticate function?
```
Returns structured caller list with file paths, line numbers, and call arguments.

```
Find dead code in this project
```
Finds functions with zero callers, scored by confidence (filters out framework callbacks, test fixtures, interface implementations).

```
What would break if I changed the User model?
```
Traces all callers and transitive dependents of the User class.

```
Show me circular dependencies
```
Detects import cycles via graph traversal — impossible with grep.

```
What are the most complex functions?
```
Ranks functions by cyclomatic complexity.

```
What are the most coupled modules?
```
Counts cross-module call edges to identify tightly-coupled pairs.

## How It Works

1. **Parse** — Tree-sitter parses each file into an AST, extracting functions, classes, parameters, imports, function calls, and inheritance relationships. Supports 16 languages (Python, JS/TS, Go, Java, Rust, Ruby, PHP, Swift, Kotlin, C/C++, C#, Dart, Perl, Elixir, Vue, Svelte).

2. **Graph** — Extracted data is stored in FalkorDB (a Redis-based graph database) as nodes (Function, Class, File, Module, Variable, Parameter) and edges (CALLS, INHERITS, IMPORTS, CONTAINS, HAS_PARAMETER).

3. **Query** — The MCP server exposes 21 tools that Claude Code can call: find_code, find_callers, find_callees, find_dead_code, class_hierarchy, module_deps, execute_cypher_query, and more.

4. **Watch** — After indexing, the file watcher monitors for changes and incrementally updates only the affected files and their callers/inheritors.

## Troubleshooting

### Menu bar icon shows red dot

Check which service is down:
- **FalkorDB** — Port 6379 may be in use. Run `lsof -i :6379` to check. Kill any existing redis-server and relaunch the app.
- **MCP Server** — Port 47321 conflict. Check with `curl http://localhost:47321/health`.
- **Visualization** — Port 47322 conflict. Non-critical — the other two services work without it.

### "Not a git repository" error

CodeGraphContext only indexes git repositories. Make sure you select a folder containing a `.git` directory.

### Indexing seems stuck

Check job status via the MCP server:
```bash
curl -s http://localhost:47321/mcp -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/call","id":1,"params":{"name":"list_jobs","arguments":{}}}' | python3 -m json.tool
```

### Claude Code doesn't see the MCP tools

1. Verify the MCP server is running: `curl http://localhost:47321/health`
2. Check `.mcp.json` is in your project root
3. Restart Claude Code after adding the config

### Port conflicts

Default ports can be changed in the Mac app Settings (gear icon):
- MCP: 47321
- Visualization: 47322
- FalkorDB: 6379 (fixed)

### CLI alternative (no Mac app)

You can run the MCP server directly without the Mac app:

```bash
# Start FalkorDB (if not already running)
redis-server --loadmodule /path/to/falkordb.so --port 6379

# Start the MCP server
CGC_RUNTIME_DB_TYPE=falkordb-remote FALKORDB_HOST=localhost FALKORDB_PORT=6379 \
  cgc mcp start --transport http --port 47321

# Index a repo
curl -X POST http://localhost:47321/mcp -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/call","id":1,"params":{"name":"add_code_to_graph","arguments":{"path":"/path/to/your/repo"}}}'
```
