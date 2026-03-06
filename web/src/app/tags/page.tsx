"use client";

import { useEffect, useState, useCallback } from "react";
import TagLog from "@/components/TagLog";

interface Tag {
  id: number;
  ts: number;
  category: string;
  text: string;
  source: string;
}

const VALID_CATEGORIES = ["conversation", "coding", "research", "agent", "heartbeat", "qwen", "idle", "other"];

export default function TagsPage() {
  const [tags, setTags] = useState<Tag[]>([]);
  const [category, setCategory] = useState("");
  const [text, setText] = useState("");
  const [filter, setFilter] = useState("");
  const [status, setStatus] = useState("");

  const fetchData = useCallback(async () => {
    const now = Math.floor(Date.now() / 1000);
    const from = now - 86400;
    let url = `/api/tags?from=${from}&to=${now}`;
    if (filter) url += `&category=${filter}`;
    const res = await fetch(url);
    const data = await res.json();
    setTags(data.tags || []);
  }, [filter]);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 10000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!category || !text) return;
    setStatus("Sending...");
    const res = await fetch("/api/tags", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ category, text, source: "david" }),
    });
    if (res.ok) {
      setStatus("Tag added");
      setText("");
      fetchData();
    } else {
      const err = await res.json();
      setStatus(`Error: ${err.error}`);
    }
    setTimeout(() => setStatus(""), 3000);
  };

  return (
    <div>
      <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 16 }}>Tag Log</h1>

      <div className="card">
        <h2>Add Manual Tag</h2>
        <form onSubmit={handleSubmit} style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            style={{ background: "#1a1a2e", color: "#e2e8f0", border: "1px solid #333", borderRadius: 4, padding: "6px 8px", fontSize: 13 }}
          >
            <option value="">Category...</option>
            {VALID_CATEGORIES.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
          <input
            type="text"
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Description..."
            style={{
              flex: 1,
              background: "#1a1a2e",
              color: "#e2e8f0",
              border: "1px solid #333",
              borderRadius: 4,
              padding: "6px 8px",
              fontSize: 13,
            }}
          />
          <button
            type="submit"
            style={{
              padding: "6px 16px",
              background: "#3b82f6",
              color: "#fff",
              border: "none",
              borderRadius: 4,
              cursor: "pointer",
              fontSize: 13,
            }}
          >
            Tag
          </button>
        </form>
        {status && <p style={{ fontSize: 12, color: "#94a3b8", marginTop: 4 }}>{status}</p>}
      </div>

      <div className="card">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
          <h2 style={{ margin: 0 }}>Timeline (Last 24h)</h2>
          <select
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            style={{ background: "#1a1a2e", color: "#e2e8f0", border: "1px solid #333", borderRadius: 4, padding: "4px 8px", fontSize: 12 }}
          >
            <option value="">All categories</option>
            {VALID_CATEGORIES.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
        </div>
        <TagLog tags={tags} />
      </div>
    </div>
  );
}
