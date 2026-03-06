"use client";

interface Process {
  id: number;
  pid: number;
  name: string;
  grp: string;
  description: string | null;
  registered: number;
  unregistered: number | null;
}

export default function ProcessTable({ processes }: { processes: Process[] }) {
  return (
    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
      <thead>
        <tr style={{ borderBottom: "1px solid #333" }}>
          <th style={{ textAlign: "left", padding: 6 }}>PID</th>
          <th style={{ textAlign: "left", padding: 6 }}>Name</th>
          <th style={{ textAlign: "left", padding: 6 }}>Group</th>
          <th style={{ textAlign: "left", padding: 6 }}>Status</th>
          <th style={{ textAlign: "left", padding: 6 }}>Registered</th>
        </tr>
      </thead>
      <tbody>
        {processes.map((p) => (
          <tr key={p.id} style={{ borderBottom: "1px solid #222" }}>
            <td style={{ padding: 6 }}>{p.pid}</td>
            <td style={{ padding: 6 }}>{p.name}</td>
            <td style={{ padding: 6 }}>{p.grp}</td>
            <td style={{ padding: 6 }}>
              <span
                style={{
                  color: p.unregistered ? "#ef4444" : "#22c55e",
                  fontWeight: 600,
                }}
              >
                {p.unregistered ? "Dead" : "Alive"}
              </span>
            </td>
            <td style={{ padding: 6 }}>
              {new Date(p.registered * 1000).toLocaleString()}
            </td>
          </tr>
        ))}
        {processes.length === 0 && (
          <tr>
            <td colSpan={5} style={{ padding: 12, color: "#888", textAlign: "center" }}>
              No processes registered
            </td>
          </tr>
        )}
      </tbody>
    </table>
  );
}
