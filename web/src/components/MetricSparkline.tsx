"use client";

import { LineChart, Line, ResponsiveContainer } from "recharts";

interface Props {
  data: { ts: number; value: number }[];
  color?: string;
}

export default function MetricSparkline({ data, color = "#3b82f6" }: Props) {
  return (
    <ResponsiveContainer width="100%" height={40}>
      <LineChart data={data}>
        <Line type="monotone" dataKey="value" stroke={color} dot={false} strokeWidth={1.5} />
      </LineChart>
    </ResponsiveContainer>
  );
}
