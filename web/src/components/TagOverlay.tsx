"use client";

import { ReferenceArea } from "recharts";

interface Tag {
  ts: number;
  category: string;
}

const CATEGORY_COLORS: Record<string, string> = {
  conversation: "rgba(59,130,246,0.1)",
  coding: "rgba(16,185,129,0.1)",
  research: "rgba(245,158,11,0.1)",
  agent: "rgba(168,85,247,0.1)",
  qwen: "rgba(236,72,153,0.1)",
  idle: "rgba(156,163,175,0.05)",
};

export function getTagOverlays(tags: Tag[], endTs: number) {
  const overlays = [];
  for (let i = 0; i < tags.length; i++) {
    const start = tags[i].ts;
    const end = i + 1 < tags.length ? tags[i + 1].ts : endTs;
    const fill = CATEGORY_COLORS[tags[i].category] || "rgba(100,116,139,0.05)";
    overlays.push(
      <ReferenceArea key={i} x1={start} x2={end} fill={fill} fillOpacity={1} />
    );
  }
  return overlays;
}
