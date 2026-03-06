"use client";

import { useEffect, useState, useCallback } from "react";
import TokenTable from "@/components/TokenTable";
import CostBadge from "@/components/CostBadge";

interface TokenSummary {
  tool?: string;
  model?: string;
  total_in: number;
  total_out: number;
  call_count: number;
  est_cost_usd: number;
}

interface Totals {
  tokens_in: number;
  tokens_out: number;
  calls: number;
  est_cost_usd: number;
}

export default function TokensPage() {
  const [summary, setSummary] = useState<TokenSummary[]>([]);
  const [totals, setTotals] = useState<Totals | null>(null);
  const [groupBy, setGroupBy] = useState("tool");
  const [range, setRange] = useState(86400);

  const fetchData = useCallback(async () => {
    const now = Math.floor(Date.now() / 1000);
    const from = now - range;
    const res = await fetch(`/api/tokens/summary?from=${from}&to=${now}&group_by=${groupBy}`);
    const data = await res.json();
    setSummary(data.summary || []);
    setTotals(data.totals || null);
  }, [groupBy, range]);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, [fetchData]);

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <h1 style={{ fontSize: 20, fontWeight: 700 }}>Token Usage</h1>
        <div style={{ display: "flex", gap: 8 }}>
          {[
            { label: "24h", val: 86400 },
            { label: "7d", val: 604800 },
            { label: "30d", val: 2592000 },
          ].map((r) => (
            <button
              key={r.val}
              onClick={() => setRange(r.val)}
              style={{
                padding: "4px 10px",
                background: range === r.val ? "#3b82f6" : "#1a1a2e",
                color: range === r.val ? "#fff" : "#94a3b8",
                border: "1px solid #333",
                borderRadius: 4,
                cursor: "pointer",
                fontSize: 12,
              }}
            >
              {r.label}
            </button>
          ))}
          <select
            value={groupBy}
            onChange={(e) => setGroupBy(e.target.value)}
            style={{ background: "#1a1a2e", color: "#e2e8f0", border: "1px solid #333", borderRadius: 4, padding: "4px 8px", fontSize: 12 }}
          >
            <option value="tool">By Tool</option>
            <option value="model">By Model</option>
            <option value="session_id">By Session</option>
          </select>
        </div>
      </div>

      {totals && (
        <div className="card" style={{ display: "flex", gap: 24 }}>
          <div>
            <div className="stat-label">Total Tokens</div>
            <div className="stat-value" style={{ fontSize: 18 }}>
              {(totals.tokens_in / 1000).toFixed(0)}K in / {(totals.tokens_out / 1000).toFixed(0)}K out
            </div>
          </div>
          <div>
            <div className="stat-label">Calls</div>
            <div className="stat-value" style={{ fontSize: 18 }}>{totals.calls}</div>
          </div>
          <div>
            <div className="stat-label">Est. Cost</div>
            <div className="stat-value" style={{ fontSize: 18 }}>
              <CostBadge cost={totals.est_cost_usd} />
            </div>
          </div>
        </div>
      )}

      <div className="card">
        <h2>Breakdown</h2>
        <TokenTable data={summary} />
      </div>
    </div>
  );
}
