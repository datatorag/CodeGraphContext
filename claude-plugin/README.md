# CodeGraphContext — Claude Code Plugin

Code graph analysis powered by FalkorDB. Index repositories into a graph database, query relationships between functions/classes/modules, detect dead code, and analyze architecture.

## Prerequisites

1. **CodeGraphContext Mac app** running (menu bar icon with green dot), OR the MCP server running manually on port 47321
2. At least one repository indexed

See [GETTING_STARTED.md](../GETTING_STARTED.md) for full setup instructions.

## Installation

Install from the Claude Code plugin marketplace:

```bash
claude plugin install codegraphcontext
```

Or add manually to your project's `.mcp.json`:

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

## Available Tools

### Code Search
- **find_code** — Search for functions, classes, or variables by name. Returns compact summaries by default; use `include_source=true` for full source.

### Relationship Analysis
- **analyze_code_relationships** — The main analysis tool. Supports these query types:
  - `find_callers` / `find_callees` — Direct callers or callees of a function
  - `find_all_callers` / `find_all_callees` — Transitive (multi-hop) callers/callees
  - `find_importers` — Files that import a module
  - `class_hierarchy` — Inheritance tree for a class
  - `module_deps` — Module dependency analysis
  - `call_chain` — Trace call paths between functions
  - `find_functions_by_decorator` / `find_functions_by_argument` — Search by metadata
  - `find_complexity` — Cyclomatic complexity for a function

### Architecture & Quality
- **find_dead_code** — Detect unused functions with confidence scoring (high/medium/low). Automatically filters framework callbacks, test fixtures, and interface overrides.
- **calculate_cyclomatic_complexity** — Complexity metric for a specific function
- **find_most_complex_functions** — Top N most complex functions in the codebase

### Indexing & Management
- **add_code_to_graph** — Index a git repository
- **list_indexed_repositories** — List all indexed repos
- **delete_repository** — Remove a repo from the graph
- **watch_directory** / **unwatch_directory** — Live file watching for auto-sync
- **get_repository_stats** — Node/edge count breakdown
- **check_job_status** — Monitor indexing progress

### Graph Queries
- **execute_cypher_query** — Run raw Cypher queries against the graph

## Example Prompts

```
Who calls the authenticate function and what arguments do they pass?
```

```
Find dead code in the Python backend
```

```
What would break if I changed the BaseSchema class?
```

```
What are the most coupled module pairs in this project?
```

```
Show me the full inheritance hierarchy for Schema classes
```

```
Find all functions called from 3+ different modules
```

```
What's the blast radius of removing the queries module?
```
