import Dagre from "@dagrejs/dagre";
import { Node, Edge } from "@xyflow/react";

/** Rank order for node types — defines vertical layer in TB layout */
const TYPE_RANK: Record<string, number> = {
  Repository: 0,
  Module: 1,
  File: 2,
  Class: 3,
  Interface: 3,
  Trait: 3,
  Enum: 3,
  Struct: 3,
  Function: 4,
  Variable: 5,
  Parameter: 5,
  Annotation: 4,
  Other: 4,
};

export interface RawNode {
  id: string;
  name: string;
  type: string;
  file?: string;
  properties?: Record<string, unknown>;
  val?: number;
}

export interface RawEdge {
  id: string;
  source: string;
  target: string;
  type: string;
}

export interface GraphData {
  nodes: RawNode[];
  links: RawEdge[];
  files?: string[];
}

/** Node dimensions keyed by type */
const NODE_DIMS: Record<string, { width: number; height: number }> = {
  Repository: { width: 200, height: 52 },
  File: { width: 180, height: 44 },
  Module: { width: 180, height: 44 },
  Class: { width: 170, height: 40 },
  Interface: { width: 170, height: 40 },
  Trait: { width: 170, height: 40 },
  Enum: { width: 160, height: 38 },
  Struct: { width: 160, height: 38 },
  Function: { width: 160, height: 36 },
  Variable: { width: 150, height: 32 },
  Parameter: { width: 150, height: 32 },
  Annotation: { width: 160, height: 36 },
  Other: { width: 160, height: 36 },
};

function getDims(type: string) {
  return NODE_DIMS[type] ?? { width: 160, height: 36 };
}

/**
 * Converts raw API graph data to React Flow nodes + edges
 * with Dagre layout applied.
 */
export function buildDagreLayout(
  data: GraphData,
  direction: "TB" | "LR" = "TB",
  visibleTypes: Set<string> = new Set(Object.keys(TYPE_RANK))
): { nodes: Node[]; edges: Edge[] } {
  const g = new Dagre.graphlib.Graph({ multigraph: true });
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({
    rankdir: direction,
    nodesep: 40,
    ranksep: 80,
    edgesep: 20,
    ranker: "network-simplex",
    align: "UL",
  });

  // Filter nodes
  const visibleNodes = data.nodes.filter((n) => visibleTypes.has(n.type));
  const visibleIds = new Set(visibleNodes.map((n) => n.id));

  // Add nodes to dagre
  visibleNodes.forEach((n) => {
    const dims = getDims(n.type);
    g.setNode(n.id, { width: dims.width, height: dims.height, rank: TYPE_RANK[n.type] ?? 4 });
  });

  // Add edges, skip invisible nodes
  const visibleEdges = data.links.filter(
    (e) => visibleIds.has(e.source) && visibleIds.has(e.target) && e.source !== e.target
  );

  visibleEdges.forEach((e, i) => {
    g.setEdge(e.source, e.target, { label: e.type }, `${e.id}-${i}`);
  });

  // Run layout
  Dagre.layout(g);

  // Map to React Flow nodes
  const rfNodes: Node[] = visibleNodes.map((n) => {
    const gNode = g.node(n.id);
    const dims = getDims(n.type);
    return {
      id: n.id,
      type: "codeNode",
      position: {
        x: (gNode?.x ?? 0) - dims.width / 2,
        y: (gNode?.y ?? 0) - dims.height / 2,
      },
      data: {
        label: n.name,
        nodeType: n.type,
        file: n.file,
        properties: n.properties,
      },
      width: dims.width,
      height: dims.height,
    };
  });

  // Map to React Flow edges
  const rfEdges: Edge[] = visibleEdges.map((e, i) => ({
    id: `${e.id}-${i}`,
    source: e.source,
    target: e.target,
    type: "smoothstep",
    animated: e.type === "CALLS",
    label: e.type,
    labelStyle: { fontSize: 9, fill: "#6b7280" },
    labelBgStyle: { fill: "transparent" },
    data: { edgeType: e.type },
    style: {
      stroke: EDGE_COLORS[e.type] ?? "#374151",
      strokeWidth: e.type === "CALLS" ? 1.5 : 1,
      opacity: 0.7,
    },
    markerEnd: {
      type: "arrowclosed" as any,
      color: EDGE_COLORS[e.type] ?? "#374151",
      width: 12,
      height: 12,
    },
  }));

  return { nodes: rfNodes, edges: rfEdges };
}

export const NODE_COLORS: Record<string, string> = {
  Repository: "#e0e7ff",
  Module: "#fbbf24",
  File: "#60a5fa",
  Class: "#4ade80",
  Interface: "#2dd4bf",
  Trait: "#86efac",
  Enum: "#c084fc",
  Struct: "#818cf8",
  Function: "#fde68a",
  Variable: "#fca5a1",
  Parameter: "#94a3b8",
  Annotation: "#f472b6",
  Other: "#78909c",
};

export const NODE_BG: Record<string, string> = {
  Repository: "#1e1b4b",
  Module: "#1c1400",
  File: "#0c1a2e",
  Class: "#052e16",
  Interface: "#042f2e",
  Trait: "#052e16",
  Enum: "#2e1065",
  Struct: "#1e1b4b",
  Function: "#1c1400",
  Variable: "#1c0a0a",
  Parameter: "#0f172a",
  Annotation: "#1f0b17",
  Other: "#111827",
};

export const EDGE_COLORS: Record<string, string> = {
  CONTAINS: "#374151",
  CALLS: "#a855f7",
  IMPORTS: "#3b82f6",
  INHERITS: "#22c55e",
  HAS_PARAMETER: "#f59e0b",
  RELATED: "#4b5563",
};

export { TYPE_RANK };
