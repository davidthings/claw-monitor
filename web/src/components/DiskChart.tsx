"use client";

import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from "recharts";

interface DataPoint {
  dir_key: string;
  size_mb: number;
}

const DIR_COLORS: Record<string, string> = {
  "openclaw-workspace": "#3b82f6",
  "openclaw-sessions": "#f59e0b",
  "openclaw-media": "#10b981",
  "openclaw-logs": "#ef4444",
  "monitor-db": "#a855f7",
};

export default function DiskChart({ data }: { data: DataPoint[] }) {
  return (
    <ResponsiveContainer width="100%" height={250}>
      <BarChart data={data}>
        <CartesianGrid strokeDasharray="3 3" stroke="#333" />
        <XAxis dataKey="dir_key" stroke="#888" />
        <YAxis unit="MB" stroke="#888" />
        <Tooltip contentStyle={{ background: "#1a1a2e", border: "1px solid #333" }} />
        <Legend />
        <Bar dataKey="size_mb" name="Size (MB)" fill="#3b82f6">
          {data.map((entry, index) => (
            <rect key={index} fill={DIR_COLORS[entry.dir_key] || "#888"} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
