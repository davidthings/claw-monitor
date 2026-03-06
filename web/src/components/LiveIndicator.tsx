"use client";

import { useEffect, useState } from "react";

export default function LiveIndicator() {
  const [connected, setConnected] = useState(false);
  const [lastUpdate, setLastUpdate] = useState<number | null>(null);

  useEffect(() => {
    const es = new EventSource("/api/metrics/stream");
    es.onopen = () => setConnected(true);
    es.onmessage = () => setLastUpdate(Date.now());
    es.onerror = () => setConnected(false);
    return () => es.close();
  }, []);

  const ago = lastUpdate ? Math.floor((Date.now() - lastUpdate) / 1000) : null;

  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
      <span
        style={{
          width: 8,
          height: 8,
          borderRadius: "50%",
          background: connected ? "#22c55e" : "#ef4444",
          display: "inline-block",
        }}
      />
      {connected ? "Live" : "Disconnected"}
      {ago !== null && ` (${ago}s ago)`}
    </span>
  );
}
