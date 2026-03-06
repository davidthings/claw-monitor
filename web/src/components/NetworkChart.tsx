"use client";

import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from "recharts";

interface DataPoint {
  ts: number;
  net_in_kb?: number;
  net_out_kb?: number;
}

function formatTime(ts: number) {
  return new Date(ts * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export default function NetworkChart({ data }: { data: DataPoint[] }) {
  return (
    <ResponsiveContainer width="100%" height={200}>
      <LineChart data={data}>
        <CartesianGrid strokeDasharray="3 3" stroke="#333" />
        <XAxis dataKey="ts" type="number" scale="time" domain={["auto", "auto"]} tickFormatter={formatTime} stroke="#888" />
        <YAxis unit="KB" stroke="#888" />
        <Tooltip
          labelFormatter={(v) => formatTime(v as number)}
          contentStyle={{ background: "#1a1a2e", border: "1px solid #333" }}
        />
        <Legend />
        <Line type="monotone" dataKey="net_in_kb" name="In KB/s" stroke="#06b6d4" dot={false} />
        <Line type="monotone" dataKey="net_out_kb" name="Out KB/s" stroke="#f97316" dot={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}
