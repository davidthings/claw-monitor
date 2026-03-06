"use client";

interface Tag {
  id: number;
  ts: number;
  recorded_at?: number;
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

/** A tag is considered backdated if its effective ts differs from recorded_at by >5s */
function isBackdated(tag: Tag): boolean {
  if (tag.recorded_at == null) return false;
  return Math.abs(tag.recorded_at - tag.ts) > 5;
}

export default function TagLog({ tags }: { tags: Tag[] }) {
  return (
    <div style={{ maxHeight: 300, overflow: "auto" }}>
      {tags.length === 0 && <p style={{ color: "#888" }}>No tags yet</p>}
      {tags.map((tag) => {
        const backdated = isBackdated(tag);
        return (
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
            </span>
            {backdated && (
              <span
                title={`Backdated — recorded at ${new Date((tag.recorded_at!) * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`}
                style={{ color: "#94a3b8", fontSize: 10, marginLeft: 3, verticalAlign: "super", cursor: "default" }}
              >
                ↩
              </span>
            )}{" "}
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
        );
      })}
    </div>
  );
}
