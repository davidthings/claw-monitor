"use client";

interface TokenSummary {
  tool?: string;
  model?: string;
  total_in: number;
  total_out: number;
  call_count: number;
  est_cost_usd: number;
}

export default function TokenTable({ data }: { data: TokenSummary[] }) {
  return (
    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
      <thead>
        <tr style={{ borderBottom: "1px solid #333" }}>
          <th style={{ textAlign: "left", padding: 6 }}>Tool/Model</th>
          <th style={{ textAlign: "right", padding: 6 }}>Tokens In</th>
          <th style={{ textAlign: "right", padding: 6 }}>Tokens Out</th>
          <th style={{ textAlign: "right", padding: 6 }}>Calls</th>
          <th style={{ textAlign: "right", padding: 6 }}>Est. Cost</th>
        </tr>
      </thead>
      <tbody>
        {data.map((row, i) => (
          <tr key={i} style={{ borderBottom: "1px solid #222" }}>
            <td style={{ padding: 6 }}>{row.tool || row.model || "—"}</td>
            <td style={{ textAlign: "right", padding: 6 }}>{(row.total_in || 0).toLocaleString()}</td>
            <td style={{ textAlign: "right", padding: 6 }}>{(row.total_out || 0).toLocaleString()}</td>
            <td style={{ textAlign: "right", padding: 6 }}>{row.call_count}</td>
            <td style={{ textAlign: "right", padding: 6 }}>${row.est_cost_usd.toFixed(2)}</td>
          </tr>
        ))}
        {data.length === 0 && (
          <tr>
            <td colSpan={5} style={{ padding: 12, color: "#888", textAlign: "center" }}>
              No token events yet
            </td>
          </tr>
        )}
      </tbody>
    </table>
  );
}
