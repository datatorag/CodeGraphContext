import { Handle, Position, NodeProps } from "@xyflow/react";
import { NODE_COLORS, NODE_BG } from "@/lib/dagre-layout";

const TYPE_ICONS: Record<string, string> = {
  Repository: "⬡",
  Module: "◈",
  File: "◻",
  Class: "⬢",
  Interface: "◇",
  Trait: "◆",
  Enum: "▣",
  Struct: "▤",
  Function: "ƒ",
  Variable: "x",
  Parameter: "p",
  Annotation: "@",
  Other: "•",
};

export default function DagCodeNode({ data, selected }: NodeProps) {
  const { label, nodeType, file } = data as {
    label: string;
    nodeType: string;
    file?: string;
    properties?: Record<string, unknown>;
  };

  const color = NODE_COLORS[nodeType] ?? "#78909c";
  const bg = NODE_BG[nodeType] ?? "#111827";
  const icon = TYPE_ICONS[nodeType] ?? "•";

  const isLarge = nodeType === "Repository" || nodeType === "Module";
  const fontSize = isLarge ? "11px" : "10px";

  return (
    <div
      style={{
        background: bg,
        border: `1px solid ${selected ? color : color + "55"}`,
        borderRadius: 8,
        padding: "6px 10px",
        minWidth: 120,
        maxWidth: 220,
        boxShadow: selected
          ? `0 0 0 2px ${color}66, 0 4px 24px ${color}33`
          : `0 2px 8px rgba(0,0,0,0.5)`,
        transition: "box-shadow 0.15s ease, border-color 0.15s ease",
        cursor: "default",
        userSelect: "none",
      }}
    >
      <Handle
        type="target"
        position={Position.Top}
        style={{ background: color, width: 6, height: 6, border: "none", opacity: 0.7 }}
      />

      {/* Header row */}
      <div style={{ display: "flex", alignItems: "center", gap: 5, marginBottom: 2 }}>
        <span
          style={{
            color,
            fontSize: isLarge ? "13px" : "11px",
            fontWeight: 700,
            lineHeight: 1,
            flexShrink: 0,
          }}
        >
          {icon}
        </span>
        <span
          style={{
            color: "#9ca3af",
            fontSize: "9px",
            fontWeight: 700,
            textTransform: "uppercase",
            letterSpacing: "0.08em",
            flexShrink: 0,
          }}
        >
          {nodeType}
        </span>
      </div>

      {/* Name */}
      <div
        style={{
          color: "#f1f5f9",
          fontSize,
          fontWeight: 600,
          fontFamily: "'JetBrains Mono', 'Fira Code', 'Consolas', monospace",
          whiteSpace: "nowrap",
          overflow: "hidden",
          textOverflow: "ellipsis",
          maxWidth: 196,
          lineHeight: 1.3,
        }}
        title={label}
      >
        {label}
      </div>

      {/* File path (for functions/classes) */}
      {file && nodeType !== "File" && nodeType !== "Repository" && (
        <div
          style={{
            color: "#4b5563",
            fontSize: "8px",
            marginTop: 2,
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
            maxWidth: 196,
          }}
          title={file}
        >
          {file.split("/").slice(-2).join("/")}
        </div>
      )}

      <Handle
        type="source"
        position={Position.Bottom}
        style={{ background: color, width: 6, height: 6, border: "none", opacity: 0.7 }}
      />
    </div>
  );
}
