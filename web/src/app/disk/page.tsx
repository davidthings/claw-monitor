"use client";

import { useEffect, useState, useCallback } from "react";

interface DiskRow {
  ts: number;
  dir_key: string;
  size_bytes: number;
  file_count: number;
}

export default function DiskPage() {
  const [data, setData] = useState<DiskRow[]>([]);

  const fetchData = useCallback(async () => {
    const now = Math.floor(Date.now() / 1000);
    const from = now - 86400;
    const res = await fetch(`/api/disk?from=${from}&to=${now}`);
    const json = await res.json();
    setData(json.data || []);
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 60000);
    return () => clearInterval(interval);
  }, [fetchData]);

  // Get latest per dir_key
  const latest: Record<string, DiskRow> = {};
  for (const r of data) {
    if (!latest[r.dir_key] || r.ts > latest[r.dir_key].ts) {
      latest[r.dir_key] = r;
    }
  }

  return (
    <div>
      <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 16 }}>Storage Detail</h1>

      <div className="card">
        <h2>Current Disk Usage</h2>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ borderBottom: "1px solid #333" }}>
              <th style={{ textAlign: "left", padding: 6 }}>Directory</th>
              <th style={{ textAlign: "right", padding: 6 }}>Size</th>
              <th style={{ textAlign: "right", padding: 6 }}>Files</th>
              <th style={{ textAlign: "right", padding: 6 }}>Last Updated</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(latest)
              .sort(([, a], [, b]) => b.size_bytes - a.size_bytes)
              .map(([key, row]) => (
                <tr key={key} style={{ borderBottom: "1px solid #222" }}>
                  <td style={{ padding: 6 }}>{key}</td>
                  <td style={{ textAlign: "right", padding: 6 }}>
                    {row.size_bytes > 1024 * 1024 * 1024
                      ? `${(row.size_bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`
                      : `${(row.size_bytes / (1024 * 1024)).toFixed(1)} MB`}
                  </td>
                  <td style={{ textAlign: "right", padding: 6 }}>{(row.file_count || 0).toLocaleString()}</td>
                  <td style={{ textAlign: "right", padding: 6 }}>
                    {new Date(row.ts * 1000).toLocaleTimeString()}
                  </td>
                </tr>
              ))}
            {Object.keys(latest).length === 0 && (
              <tr>
                <td colSpan={4} style={{ padding: 12, color: "#888", textAlign: "center" }}>
                  No disk data yet — collector may not have run a slow loop cycle
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
