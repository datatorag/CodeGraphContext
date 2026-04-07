---
name: index-repo
description: Guide the user through indexing a repository into the CodeGraphContext graph database
---

# Index Repository

Use this skill when the user wants to index a new codebase or re-index an existing one.

## Steps

### 1. Check server health

Call the CGC MCP server health endpoint to verify it's running:

```
GET http://localhost:47321/health
```

If the server is not responding, tell the user:
> The CodeGraphContext Mac app doesn't appear to be running. Please start it from the menu bar and ensure the status shows "Server Running" (green dot).

### 2. Determine the repository path

If the user specified a path, use it directly. Otherwise:
- Check if the current working directory is a git repository
- If so, offer to index it: "Would you like me to index the current project at `{cwd}`?"
- If not, ask the user to provide a path

### 3. Check if already indexed

Use the `list_repos` tool to see if this repository is already in the graph:
- If indexed: ask "This repository is already indexed. Would you like to re-index it to pick up recent changes?"
- If not indexed: proceed

### 4. Start indexing

Use the `add_code_to_graph` tool with the repository path:

```json
{
  "repo_path": "/path/to/repository"
}
```

Let the user know this may take a few minutes for large repositories (thousands of files).

### 5. Verify completion

After indexing completes:
1. Use `get_graph_stats` to show what was indexed (number of files, functions, classes, relationships)
2. Use `list_repos` to confirm the repo appears in the list
3. Summarize: "Indexed {repo_name}: {N} files, {M} functions, {K} relationships found."

### 6. Suggest next steps

After successful indexing, suggest:
- "You can now ask me about code relationships, architecture, or dead code in this project."
- "Try: 'What are the main modules?' or 'Find dead code' or 'Who calls function X?'"
