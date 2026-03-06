"use client";

import { useEffect, useState, useCallback } from "react";
import ProcessTable from "@/components/ProcessTable";

interface Process {
  id: number;
  pid: number;
  name: string;
  grp: string;
  description: string | null;
  registered: number;
  unregistered: number | null;
}

export default function ProcessesPage() {
  const [processes, setProcesses] = useState<Process[]>([]);
  const [showAll, setShowAll] = useState(false);

  const fetchData = useCallback(async () => {
    const res = await fetch("/api/registry");
    const data = await res.json();
    setProcesses(data.processes || []);
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 10000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const filtered = showAll ? processes : processes.filter((p) => !p.unregistered);

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <h1 style={{ fontSize: 20, fontWeight: 700 }}>Process Registry</h1>
        <label style={{ fontSize: 12, color: "#94a3b8", cursor: "pointer" }}>
          <input
            type="checkbox"
            checked={showAll}
            onChange={(e) => setShowAll(e.target.checked)}
            style={{ marginRight: 4 }}
          />
          Show dead processes
        </label>
      </div>

      <div className="card">
        <ProcessTable processes={filtered} />
      </div>

      <p style={{ color: "#94a3b8", fontSize: 12, marginTop: 8 }}>
        {processes.filter((p) => !p.unregistered).length} alive / {processes.length} total
      </p>
    </div>
  );
}
