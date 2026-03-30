import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  BackgroundVariant,
  Panel,
  useReactFlow,
  ReactFlowProvider,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useCallback, useEffect, useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  ArrowLeft, Search, Eye, EyeOff, LayoutTemplate,
  Folder, FolderOpen, ChevronRight, ChevronDown,
  PanelLeftClose, PanelLeftOpen, FileCode, Filter,
  Download, Maximize2
} from "lucide-react";
import { Button } from "@/components/ui/button";
import DagCodeNode from "./DagCodeNode";
import {
  buildDagreLayout,
  GraphData,
  NODE_COLORS,
  EDGE_COLORS,
  TYPE_RANK,
} from "@/lib/dagre-layout";

// ─── Constants ───────────────────────────────────────────────────────────────
const NODE_TYPES = { codeNode: DagCodeNode };
const ALL_NODE_TYPES = Object.keys(TYPE_RANK);

// How many nodes before we warn/cap
const LAYOUT_LIMIT = 800;

// ─── Tree ────────────────────────────────────────────────────────────────────
interface TreeNode { name: string; path: string; isDir: boolean; children: TreeNode[] }

function buildTree(files: string[]): TreeNode[] {
  const root: TreeNode[] = [];
  for (const fp of files) {
    const parts = fp.split("/").filter(Boolean);
    let cur = root;
    for (let i = 0; i < parts.length; i++) {
      const isLast = i === parts.length - 1;
      const nodePath = isLast ? fp : parts.slice(0, i + 1).join("/");
      let node = cur.find((n) => n.name === parts[i]);
      if (!node) { node = { name: parts[i], path: nodePath, isDir: !isLast, children: [] }; cur.push(node); }
      cur = node.children;
    }
  }
  const sort = (ns: TreeNode[]): TreeNode[] =>
    ns.sort((a, b) => (a.isDir !== b.isDir ? (a.isDir ? -1 : 1) : a.name.localeCompare(b.name)))
      .map((n) => ({ ...n, children: sort(n.children) }));
  return sort(root);
}

function TreeItem({ node, depth, selectedFile, onFileClick, searchQuery }: {
  node: TreeNode; depth: number; selectedFile: string | null;
  onFileClick: (p: string | null) => void; searchQuery: string;
}) {
  const [open, setOpen] = useState(depth < 2);
  useEffect(() => { if (searchQuery) setOpen(true); }, [searchQuery]);

  const match = (n: TreeNode): boolean =>
    n.name.toLowerCase().includes(searchQuery.toLowerCase()) || n.children.some(match);

  if (searchQuery && !match(node)) return null;

  const indent = depth * 12;
  const extColors: Record<string, string> = {
    py: "#ffca28", ts: "#42a5f5", tsx: "#42a5f5", js: "#f59e0b",
    jsx: "#f59e0b", rs: "#ef5350", go: "#26a69a", java: "#ef9a9a",
  };
  const ext = node.name.split(".").pop() ?? "";
  const dotColor = extColors[ext] || "#78909c";

  if (node.isDir) return (
    <div>
      <button onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center gap-1 py-[3px] px-2 rounded-lg text-gray-400 hover:text-white hover:bg-white/5 transition-colors"
        style={{ paddingLeft: `${indent + 8}px` }}>
        {open ? <ChevronDown className="w-3 h-3 text-gray-500" /> : <ChevronRight className="w-3 h-3 text-gray-500" />}
        {open ? <FolderOpen className="w-3.5 h-3.5 text-amber-400 ml-0.5" /> : <Folder className="w-3.5 h-3.5 text-amber-400 ml-0.5" />}
        <span className="text-[13px] text-gray-300 truncate font-medium ml-1">{node.name}</span>
      </button>
      {open && <div>{node.children.map((c) => <TreeItem key={c.path} node={c} depth={depth + 1} selectedFile={selectedFile} onFileClick={onFileClick} searchQuery={searchQuery} />)}</div>}
    </div>
  );

  const isSelected = selectedFile === node.path;
  return (
    <button onClick={() => onFileClick(node.path)}
      className={`w-full flex items-center gap-2 py-[3px] px-2 rounded-lg text-[13px] transition-all ${isSelected ? "bg-purple-500/20 text-purple-200 border border-purple-500/20" : "text-gray-400 hover:text-gray-200 hover:bg-white/5 border border-transparent"}`}
      style={{ paddingLeft: `${indent + 20}px` }}>
      <div className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ backgroundColor: dotColor }} />
      <span className="truncate font-medium">{node.name}</span>
    </button>
  );
}

// ─── Export Mermaid ───────────────────────────────────────────────────────────
function exportMermaid(nodes: any[], edges: any[]) {
  const lines = ["flowchart TB"];
  const nodeById = new Map(nodes.map((n: any) => [n.id, n]));
  const seen = new Set<string>();

  nodes.forEach((n: any) => {
    const d = n.data as any;
    const safe = n.id.replace(/[^a-zA-Z0-9_]/g, "_");
    const lbl = (d.label as string).replace(/"/g, "'");
    lines.push(`  ${safe}["${lbl}"]:::${d.nodeType}`);
    seen.add(safe);
  });

  edges.forEach((e: any) => {
    const s = e.source.replace(/[^a-zA-Z0-9_]/g, "_");
    const t = e.target.replace(/[^a-zA-Z0-9_]/g, "_");
    if (seen.has(s) && seen.has(t)) {
      lines.push(`  ${s} -->|${e.data?.edgeType ?? ""}| ${t}`);
    }
  });

  // Add classDef
  Object.entries(NODE_COLORS).forEach(([type, color]) => {
    lines.push(`  classDef ${type} fill:${color}22,stroke:${color},color:#fff`);
  });

  return lines.join("\n");
}

// ─── Inner component (needs ReactFlowProvider context) ─────────────────────
function DagViewerInner({ data, onClose }: { data: GraphData; onClose: () => void }) {
  const { fitView } = useReactFlow();

  const [direction, setDirection] = useState<"TB" | "LR">("TB");
  const [visibleTypes, setVisibleTypes] = useState<Set<string>>(
    () => new Set(ALL_NODE_TYPES.filter((t) => t !== "Variable" && t !== "Parameter"))
  );
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [collapsed, setSidebarCollapsed] = useState(false);
  const [showFilters, setShowFilters] = useState(false);
  const [copied, setCopied] = useState(false);

  // Subset data by selected file
  const filteredRaw = useMemo<GraphData>(() => {
    if (!selectedFile) {
      // Cap at limit
      const nodes = data.nodes.filter((n) => visibleTypes.has(n.type)).slice(0, LAYOUT_LIMIT);
      const ids = new Set(nodes.map((n) => n.id));
      const links = data.links.filter((e) => ids.has(e.source) && ids.has(e.target));
      return { nodes, links, files: data.files };
    }

    // Focus: file node + its immediate neighbors
    const fileNode = data.nodes.find((n) => n.file === selectedFile && n.type === "File");
    if (!fileNode) return { nodes: [], links: [], files: data.files };

    const neighborIds = new Set<string>([fileNode.id]);
    data.links.forEach((e) => {
      if (e.source === fileNode.id) neighborIds.add(e.target);
      if (e.target === fileNode.id) neighborIds.add(e.source);
    });

    const nodes = data.nodes.filter((n) => neighborIds.has(n.id) && visibleTypes.has(n.type));
    const ids = new Set(nodes.map((n) => n.id));
    const links = data.links.filter((e) => ids.has(e.source) && ids.has(e.target));
    return { nodes, links, files: data.files };
  }, [data, selectedFile, visibleTypes]);

  // Run dagre layout
  const { nodes: layoutNodes, edges: layoutEdges } = useMemo(
    () => buildDagreLayout(filteredRaw, direction, visibleTypes),
    [filteredRaw, direction, visibleTypes]
  );

  const [nodes, setNodes, onNodesChange] = useNodesState(layoutNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(layoutEdges);

  // Re-apply layout when it changes
  useEffect(() => {
    setNodes(layoutNodes);
    setEdges(layoutEdges);
    setTimeout(() => fitView({ padding: 0.15, duration: 600 }), 50);
  }, [layoutNodes, layoutEdges, fitView]);

  const fileTree = useMemo(() => buildTree(data.files ?? []), [data.files]);

  const toggleType = (t: string) => {
    const next = new Set(visibleTypes);
    if (next.has(t)) next.delete(t); else next.add(t);
    setVisibleTypes(next);
  };

  const handleExportMermaid = () => {
    const mmd = exportMermaid(nodes, edges);
    navigator.clipboard.writeText(mmd).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  const isCapped = !selectedFile && data.nodes.filter((n) => visibleTypes.has(n.type)).length > LAYOUT_LIMIT;

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex bg-[#050507] font-sans overflow-hidden"
    >
      {/* ── SIDEBAR ── */}
      <AnimatePresence>
        {!collapsed && (
          <motion.div
            key="sidebar"
            initial={{ x: -320, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: -320, opacity: 0 }}
            transition={{ duration: 0.2, ease: "easeOut" }}
            className="flex flex-col w-[300px] flex-shrink-0 bg-[#0a0a0f] border-r border-white/[0.06] z-[70] shadow-2xl overflow-hidden"
          >
            {/* Header */}
            <div className="px-4 pt-4 pb-3 flex-shrink-0 border-b border-white/[0.05]">
              <Button
                onClick={onClose}
                variant="ghost"
                className="w-full justify-start text-gray-400 hover:text-white hover:bg-white/5 mb-3 rounded-xl border border-white/5 text-sm"
              >
                <ArrowLeft className="w-4 h-4 mr-2" /> Back to Dashboard
              </Button>

              {/* Title */}
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-sm font-bold text-white flex items-center gap-2 tracking-tight uppercase">
                  <LayoutTemplate className="w-4 h-4 text-purple-400" />
                  DAG Explorer
                </h2>
                <div className="flex items-center gap-1">
                  <button
                    onClick={() => setShowFilters((f) => !f)}
                    title="Filters"
                    className={`p-1.5 rounded-lg transition-colors ${showFilters ? "bg-purple-500/20 text-purple-400" : "text-gray-500 hover:text-white hover:bg-white/5"}`}
                  >
                    <Filter className="w-4 h-4" />
                  </button>
                  <button onClick={() => setSidebarCollapsed(true)} title="Collapse"
                    className="p-1.5 rounded-lg text-gray-500 hover:text-white hover:bg-white/5 transition-colors">
                    <PanelLeftClose className="w-4 h-4" />
                  </button>
                </div>
              </div>

              {/* Direction toggle */}
              <div className="flex gap-2 mb-3">
                {(["TB", "LR"] as const).map((d) => (
                  <button key={d} onClick={() => setDirection(d)}
                    className={`flex-1 text-[11px] font-bold uppercase tracking-widest py-1.5 rounded-lg transition-all border ${direction === d ? "bg-purple-500/20 border-purple-500/40 text-purple-300" : "border-white/5 text-gray-500 hover:text-gray-300 hover:bg-white/5"}`}>
                    {d === "TB" ? "↓ Top→Bottom" : "→ Left→Right"}
                  </button>
                ))}
              </div>

              {/* Search */}
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-500" />
                <input type="text" placeholder="Filter files..." value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full bg-white/5 border border-white/8 rounded-lg py-1.5 pl-9 pr-3 text-[13px] text-white placeholder:text-gray-600 focus:outline-none focus:ring-1 focus:ring-purple-500/50 transition-all" />
              </div>
            </div>

            {/* Content: filters OR file tree */}
            <div className="flex-1 overflow-y-auto px-2 py-2">
              {showFilters ? (
                <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="p-2 space-y-1">
                  <p className="text-[10px] font-bold text-gray-500 uppercase tracking-widest mb-3 px-1">Node Types</p>
                  {ALL_NODE_TYPES.map((type) => (
                    <button key={type} onClick={() => toggleType(type)}
                      className="w-full flex items-center gap-3 py-1.5 px-2 rounded-lg hover:bg-white/5 transition-colors">
                      <div className={`p-0.5 rounded transition-colors ${visibleTypes.has(type) ? "text-purple-400" : "text-gray-600"}`}>
                        {visibleTypes.has(type) ? <Eye className="w-3.5 h-3.5" /> : <EyeOff className="w-3.5 h-3.5" />}
                      </div>
                      <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: NODE_COLORS[type] ?? "#78909c" }} />
                      <span className={`text-sm ${visibleTypes.has(type) ? "text-gray-200" : "text-gray-600"}`}>{type}</span>
                    </button>
                  ))}

                  <p className="text-[10px] font-bold text-gray-500 uppercase tracking-widest mt-5 mb-2 px-1">Edge Legend</p>
                  {Object.entries(EDGE_COLORS).map(([type, color]) => (
                    <div key={type} className="flex items-center gap-3 py-1 px-2">
                      <div className="w-8 h-px" style={{ backgroundColor: color }} />
                      <span className="text-[11px] text-gray-400">{type}</span>
                    </div>
                  ))}
                </motion.div>
              ) : (
                <div className="py-1">
                  {selectedFile && (
                    <button onClick={() => setSelectedFile(null)}
                      className="w-full text-[11px] text-amber-400 hover:text-amber-300 bg-amber-500/10 hover:bg-amber-500/20 border border-amber-500/20 rounded-lg py-1.5 mb-3 transition-all font-bold uppercase tracking-widest">
                      ✕ Clear File Focus
                    </button>
                  )}
                  <div className="px-1 mb-2 flex items-center gap-2">
                    <FileCode className="w-3.5 h-3.5 text-blue-400" />
                    <span className="text-[11px] font-bold text-gray-500 uppercase tracking-widest">Project Files</span>
                  </div>
                  {fileTree.map((node) => (
                    <TreeItem key={node.path} node={node} depth={0}
                      selectedFile={selectedFile} onFileClick={setSelectedFile} searchQuery={searchQuery} />
                  ))}
                </div>
              )}
            </div>

            {/* Footer stats */}
            <div className="px-4 py-3 border-t border-white/5 bg-black/40 flex-shrink-0 space-y-2">
              {isCapped && (
                <p className="text-[10px] text-amber-400/80 bg-amber-400/10 border border-amber-400/20 rounded-lg px-2 py-1 text-center">
                  ⚠️ Showing first {LAYOUT_LIMIT} nodes — select a file to focus
                </p>
              )}
              <div className="text-[10px] text-gray-500 flex justify-between uppercase tracking-widest font-black">
                <span>{nodes.length} Nodes</span>
                <span>{edges.length} Edges</span>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Expand button */}
      {collapsed && (
        <button onClick={() => setSidebarCollapsed(false)}
          className="absolute left-0 top-1/2 -translate-y-1/2 z-[80] bg-[#0a0a0f] border border-white/10 hover:border-purple-500/40 text-gray-400 hover:text-white transition-all rounded-r-xl p-2 shadow-2xl">
          <PanelLeftOpen className="w-4 h-4" />
        </button>
      )}

      {/* ── REACT FLOW CANVAS ── */}
      <div className="flex-1 relative">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          nodeTypes={NODE_TYPES}
          fitView
          fitViewOptions={{ padding: 0.15 }}
          minZoom={0.02}
          maxZoom={4}
          proOptions={{ hideAttribution: true }}
        >
          <Background
            variant={BackgroundVariant.Dots}
            gap={24}
            size={1}
            color="#1f2937"
          />
          <Controls
            className="!bg-black/60 !border-white/10 !rounded-xl !shadow-2xl backdrop-blur-xl"
            showInteractive={false}
          />
          <MiniMap
            nodeColor={(n) => NODE_COLORS[(n.data as any)?.nodeType] ?? "#374151"}
            maskColor="rgba(0,0,0,0.7)"
            className="!bg-black/60 !border-white/10 !rounded-xl !shadow-2xl"
            style={{ width: 140, height: 90 }}
          />

          {/* Top bar */}
          <Panel position="top-right">
            <div className="flex items-center gap-2">
              {/* Export Mermaid */}
              <button onClick={handleExportMermaid}
                className={`flex items-center gap-2 text-[11px] font-bold uppercase tracking-widest px-4 py-2 rounded-full border backdrop-blur-xl shadow-2xl transition-all ${copied ? "bg-green-500/20 border-green-500/40 text-green-400" : "bg-black/40 hover:bg-white/10 border-white/10 text-white"}`}>
                <Download className="w-3.5 h-3.5" />
                {copied ? "Copied!" : "Copy Mermaid"}
              </button>

              <button onClick={() => fitView({ padding: 0.15, duration: 600 })}
                className="flex items-center gap-2 bg-black/40 hover:bg-white/10 text-white text-[11px] uppercase tracking-widest font-bold px-4 py-2 border border-white/10 rounded-full transition-all backdrop-blur-xl shadow-2xl">
                <Maximize2 className="w-3.5 h-3.5" />
                Fit View
              </button>
            </div>
          </Panel>

          {/* Info badge */}
          <Panel position="top-left" style={{ marginLeft: collapsed ? 12 : 0 }}>
            <div className="flex flex-col gap-2">
              {selectedFile && (
                <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }}
                  className="bg-purple-500/20 border border-purple-500/30 text-purple-300 text-[11px] font-bold uppercase tracking-widest px-4 py-2 rounded-full backdrop-blur-xl shadow-2xl max-w-xs truncate">
                  📁 {selectedFile.split("/").slice(-2).join("/")}
                </motion.div>
              )}
            </div>
          </Panel>
        </ReactFlow>
      </div>
    </motion.div>
  );
}

// ─── Public export (wraps in provider) ───────────────────────────────────────
export default function DagViewer({ data, onClose }: { data: GraphData; onClose: () => void }) {
  return (
    <ReactFlowProvider>
      <DagViewerInner data={data} onClose={onClose} />
    </ReactFlowProvider>
  );
}
