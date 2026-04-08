from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from pathlib import Path
import uvicorn
import json
import os
import sys
from typing import Optional, List, Dict, Any

from ..core.database import DatabaseManager
from ..utils.debug_log import debug_log

app = FastAPI()

# Enable CORS for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global database manager (will be initialized when server starts)
db_manager: Optional[DatabaseManager] = None
# Path to static directory
_static_dir: Optional[str] = None

def set_db_manager(manager: DatabaseManager):
    global db_manager
    db_manager = manager

def _get_falkordb_graph():
    """Get a direct FalkorDB graph connection (bypasses wrapper caching issues)."""
    host = os.environ.get('FALKORDB_HOST', 'localhost')
    port = int(os.environ.get('FALKORDB_PORT', '6379'))
    graph_name = os.environ.get('FALKORDB_GRAPH_NAME', 'codegraph')
    try:
        from falkordb import FalkorDB
        db = FalkorDB(host=host, port=port)
        return db.select_graph(graph_name)
    except Exception:
        return None

@app.get("/api/graph")
async def get_graph(repo_path: Optional[str] = None, cypher_query: Optional[str] = None):
    if not db_manager:
        raise HTTPException(status_code=500, detail="Database not initialized")

    def get_eid(element):
        if element is None: return None
        if isinstance(element, (int, str)):
            return str(element)
        
        # If element is a dict (like Neo4j returned items or KuzuDB node/rel dicts)
        if isinstance(element, dict):
            # KuzuDB _src / _dst are directly {'offset': X, 'table': Y}
            if 'offset' in element and 'table' in element:
                return f"{element.get('table')}_{element.get('offset')}"
                
            for key in ['_id', 'id', 'element_id']:
                if key in element:
                    val = element[key]
                    if val is not None:
                        # KuzuDB returns dict IDs like {'offset': 1, 'table': 0} inside nodes
                        if isinstance(val, dict):
                            return f"{val.get('table', 0)}_{val.get('offset', 0)}"
                        return str(val)
            return str(id(element))
            
        # Try various ways to get ID (Neo4j, FalkorDB, etc. objects)
        for attr in ['element_id', 'id', '_id']:
            if hasattr(element, attr):
                val = getattr(element, attr)
                if val is not None: 
                    # KuzuDB objects if any
                    if isinstance(val, dict):
                        return f"{val.get('table', 0)}_{val.get('offset', 0)}"
                    return str(val)
        return str(id(element))

    try:
        nodes_dict = {}
        edges = []

        print(f"DEBUG: Starting get_graph with repo_path={repo_path}", file=sys.stderr, flush=True)

        # Try direct FalkorDB connection first (avoids wrapper caching issues)
        direct_graph = _get_falkordb_graph()
        use_direct = direct_graph is not None and not cypher_query and not repo_path

        if use_direct:
            print("DEBUG: Using direct FalkorDB connection", file=sys.stderr, flush=True)
            # Structural query: skip Variable/Parameter for a cleaner visualization
            query = "MATCH (n)-[rel]->(m) WHERE NOT (n:Variable OR n:Parameter) AND NOT (m:Variable OR m:Parameter) RETURN n, rel, m LIMIT 50000"
            raw_result = direct_graph.query(query)
            print(f"DEBUG: Direct query returned {len(raw_result.result_set)} records", file=sys.stderr, flush=True)

            for row in raw_result.result_set:
                n, rel, m = row[0], row[1], row[2]
                for node in [n, m]:
                    if node is None:
                        continue
                    eid = str(node.id)
                    if eid not in nodes_dict:
                        props = node.properties if hasattr(node, 'properties') else {}
                        labels = list(node.labels) if hasattr(node, 'labels') else []
                        display_name = str(props.get('name', props.get('label', props.get('path', 'Unknown'))))
                        nodes_dict[eid] = {
                            "id": eid,
                            "name": display_name,
                            "label": display_name,
                            "type": str(labels[0]).capitalize() if labels else "Other",
                            "file": str(props.get('path', props.get('file', ''))),
                            "val": 4 if (labels and labels[0] in ['Repository', 'Class', 'Interface', 'Trait']) else 2,
                            "properties": dict(props) if props else {}
                        }
                if rel is not None:
                    edges.append({
                        "id": str(rel.id),
                        "source": str(rel.src_node),
                        "target": str(rel.dest_node),
                        "type": str(rel.relation).upper()
                    })
        else:
            # Fallback: use the wrapper-based approach
            with db_manager.get_driver().session() as session:
                if cypher_query:
                    print(f"DEBUG: Executing custom query: {cypher_query}", file=sys.stderr, flush=True)
                    result = session.run(cypher_query)
                elif repo_path:
                    repo_path = str(Path(repo_path).resolve())
                    print(f"DEBUG: Fetching subgraph for: {repo_path}", file=sys.stderr, flush=True)
                    query = """
                    MATCH (r:Repository {path: $repo_path})
                    OPTIONAL MATCH (r)-[:CONTAINS*0..]->(n)
                    WITH DISTINCT n
                    WHERE n IS NOT NULL
                    OPTIONAL MATCH (n)-[rel]->(m)
                    RETURN n, rel, m
                    """
                    result = session.run(query, repo_path=repo_path)
                else:
                    query = "MATCH (n) OPTIONAL MATCH (n)-[rel]->(m) RETURN n, rel, m LIMIT 50000"
                    result = session.run(query)

            if not use_direct:
                record_count = 0
                for record in result:
                    record_count += 1
                    for key in ['n', 'm']:
                        try:
                            node = record.get(key)
                            if node:
                                eid = get_eid(node)
                                if eid and eid not in nodes_dict:
                                    labels = []
                                    if isinstance(node, dict):
                                        if '_label' in node: labels = [node['_label']]
                                        elif 'label' in node: labels = [node['label']]
                                    else:
                                        for label_attr in ['_labels', 'labels']:
                                            if hasattr(node, label_attr):
                                                attr_val = getattr(node, label_attr)
                                                if attr_val:
                                                    labels = list(attr_val)
                                                    break
                                    props = {}
                                    if isinstance(node, dict):
                                        props = {k: v for k, v in node.items() if not k.startswith('_')}
                                    else:
                                        for prop_attr in ['properties', '_properties']:
                                            if hasattr(node, prop_attr):
                                                attr_val = getattr(node, prop_attr)
                                                if attr_val:
                                                    props = dict(attr_val)
                                                    break
                                        if not props and hasattr(node, 'items'):
                                            try: props = dict(node.items())
                                            except: pass
                                    display_name = str(props.get('name', props.get('label', props.get('path', 'Unknown'))))
                                    nodes_dict[eid] = {
                                        "id": eid, "name": display_name, "label": display_name,
                                        "type": str(labels[0]).capitalize() if labels else "Other",
                                        "file": str(props.get('path', props.get('file', ''))),
                                        "val": 4 if (labels and labels[0] in ['Repository', 'Class', 'Interface', 'Trait']) else 2,
                                        "properties": props
                                    }
                        except Exception as e:
                            continue
                    try:
                        rel = record.get('rel')
                        if rel is not None:
                            if isinstance(rel, dict):
                                rid = get_eid(rel)
                                src = rel.get('_src', rel.get('src_node'))
                                dst = rel.get('_dst', rel.get('dest_node'))
                                source = get_eid(src) if src is not None else None
                                target = get_eid(dst) if dst is not None else None
                                rel_type = str(rel.get('_label', rel.get('relation', rel.get('type', 'RELATED')))).upper()
                            else:
                                rid = get_eid(rel)
                                start_node = end_node = None
                                for a in ['start_node', 'src_node', '_src_node']:
                                    if hasattr(rel, a): start_node = getattr(rel, a); break
                                for a in ['end_node', 'dest_node', '_dest_node']:
                                    if hasattr(rel, a): end_node = getattr(rel, a); break
                                source = get_eid(start_node) if start_node is not None else None
                                target = get_eid(end_node) if end_node is not None else None
                                rel_type = "RELATED"
                                for a in ['type', 'relation', '_relation']:
                                    if hasattr(rel, a): rel_type = str(getattr(rel, a)).upper(); break
                            if source and target:
                                edges.append({"id": rid, "source": source, "target": target, "type": rel_type})
                    except Exception:
                        pass
                print(f"DEBUG: Wrapper path: {record_count} records, {len(nodes_dict)} nodes, {len(edges)} edges", file=sys.stderr, flush=True)

        filtered_nodes = nodes_dict
        filtered_edges = edges

        # Build a list of unique file paths from File-type nodes for the tree
        file_paths = []
        for n in filtered_nodes.values():
            if n.get("file") and str(n.get("type", "")).lower() == "file":
                file_paths.append(str(n["file"]))
        file_paths = sorted(list(set(file_paths)))

        # Read file contents on demand via /api/file instead of bundling all at once
        file_contents: dict[str, str] = {}

        response_data = {
            "nodes": list(filtered_nodes.values()),
            "links": filtered_edges,
            "files": file_paths,
            "fileContents": file_contents,
        }

        print(f"API SUCCESS: Returning graph with {len(response_data['nodes'])} nodes and {len(response_data['links'])} links.", file=sys.stderr, flush=True)
        return response_data

    except Exception as e:
        debug_log(f"Error fetching graph: {str(e)}")
        import traceback
        traceback.print_exc()
        # Still return a valid structure so the frontend doesn't crash, but with 500 status if raised
        # Actually, let's just return a 500 error but with JSON body if possible
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/file")
async def get_file(path: str):
    file_path = Path(path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return {"content": f.read()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# SPA fallback handler
@app.get("/{full_path:path}")
async def spa_fallback(request: Request, full_path: str):
    global _static_dir
    if not _static_dir:
        return HTMLResponse("Static directory not configured", status_code=500)
    
    # Filesystem path
    file_path = Path(_static_dir) / full_path
    
    # If the file exists and is a file, serve it normally
    if file_path.exists() and file_path.is_file():
        return FileResponse(file_path)
    
    # Otherwise serve index.html (Standard SPA routing)
    index_path = Path(_static_dir) / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    
    return HTMLResponse("Not Found (Built UI not found in viz/dist)", status_code=404)

def run_server(host: str = "127.0.0.1", port: int = 47322, static_dir: Optional[str] = None):
    global _static_dir
    _static_dir = static_dir
    uvicorn.run(app, host=host, port=port)
