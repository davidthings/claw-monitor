"use client";

export default function CostBadge({ cost }: { cost: number }) {
  return (
    <span
      style={{
        background: "#1e3a5f",
        color: "#93c5fd",
        padding: "2px 8px",
        borderRadius: 4,
        fontSize: 12,
        fontWeight: 600,
      }}
    >
      ${cost.toFixed(2)}
    </span>
  );
}
