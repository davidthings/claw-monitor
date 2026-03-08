"use client";

import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from "recharts";

interface DataPoint {
  ts: number;
  size_mb: number;
}

function formatTime(ts: number) {
  return new Date(ts * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export default function DiskTimeChart({ data }: { data: DataPoint[] }) {
  return (
    <ResponsiveContainer width="100%" height={200}>
      <LineChart data={data}>
        <CartesianGrid strokeDasharray="3 3" stroke="#333" />
        <XAxis dataKey="ts" type="number" scale="time" domain={["auto", "auto"]} tickFormatter={formatTime} stroke="#888" />
        <YAxis unit=" MB" stroke="#888" />
        <Tooltip
          labelFormatter={(v) => formatTime(v as number)}
          contentStyle={{ background: "#1a1a2e", border: "1px solid #333" }}
        />
        <Line type="monotone" dataKey="size_mb" name="Size MB" stroke="#8b5cf6" dot={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}
