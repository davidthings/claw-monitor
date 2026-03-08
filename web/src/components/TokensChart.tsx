"use client";

import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from "recharts";

interface DataPoint {
  ts: number;
  tok_per_min: number;
}

function formatTime(ts: number) {
  return new Date(ts * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export default function TokensChart({ data }: { data: DataPoint[] }) {
  return (
    <ResponsiveContainer width="100%" height={200}>
      <LineChart data={data}>
        <CartesianGrid strokeDasharray="3 3" stroke="#333" />
        <XAxis dataKey="ts" type="number" scale="time" domain={["auto", "auto"]} tickFormatter={formatTime} stroke="#888" />
        <YAxis unit=" tok/min" stroke="#888" />
        <Tooltip
          labelFormatter={(v) => formatTime(v as number)}
          contentStyle={{ background: "#1a1a2e", border: "1px solid #333" }}
        />
        <Line type="monotone" dataKey="tok_per_min" name="Tokens/min" stroke="#f59e0b" dot={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}
