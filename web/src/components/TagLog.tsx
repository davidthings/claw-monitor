"use client";

interface Tag {
  id: number;
  ts: number;
  category: string;
  text: string;
  source: string;
}

const CATEGORY_COLORS: Record<string, string> = {
  conversation: "#3b82f6",
  coding: "#10b981",
  research: "#f59e0b",
  agent: "#a855f7",
  heartbeat: "#6b7280",
  qwen: "#ec4899",
  idle: "#9ca3af",
  other: "#64748b",
};

export default function TagLog({ tags }: { tags: Tag[] }) {
  return (
    <div style={{ maxHeight: 300, overflow: "auto" }}>
      {tags.length === 0 && <p style={{ color: "#888" }}>No tags yet</p>}
      {tags.map((tag) => (
        <div
          key={tag.id}
          style={{
            padding: "6px 10px",
            borderLeft: `3px solid ${CATEGORY_COLORS[tag.category] || "#888"}`,
            marginBottom: 4,
            fontSize: 13,
          }}
        >
          <span style={{ color: "#888" }}>
            {new Date(tag.ts * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
          </span>{" "}
          <span
            style={{
              background: CATEGORY_COLORS[tag.category] || "#888",
              color: "#fff",
              padding: "1px 6px",
              borderRadius: 3,
              fontSize: 11,
            }}
          >
            {tag.category}
          </span>{" "}
          {tag.text}
        </div>
      ))}
    </div>
  );
}
