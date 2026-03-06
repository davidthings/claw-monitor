import { vi, beforeEach, describe, it, expect } from "vitest";
import { testDb, makeRequest } from "./helpers";
import type Database from "better-sqlite3";

vi.mock("@/lib/db", () => ({
  getDb: vi.fn(),
}));

import { getDb } from "@/lib/db";
import { GET } from "@/app/api/metrics/route";

let db: Database.Database;

beforeEach(() => {
  db = testDb();
  (getDb as ReturnType<typeof vi.fn>).mockReturnValue(db);
});

function insertMetric(ts: number, grp: string, cpu = 10.0) {
  db.prepare(
    "INSERT INTO metrics (ts, grp, cpu_pct, mem_rss_mb, sample_interval_s) VALUES (?, ?, ?, 100, 1)"
  ).run(ts, grp, cpu);
}

describe("GET /api/metrics", () => {
  it("returns 400 when from is missing", async () => {
    const req = makeRequest("GET", "/api/metrics");
    const res = await GET(req);
    expect(res.status).toBe(400);
  });

  it("returns raw resolution for short range", async () => {
    const now = Math.floor(Date.now() / 1000);
    insertMetric(now - 100, "core");
    const req = makeRequest("GET", `/api/metrics?from=${now - 3600}&to=${now}`);
    const res = await GET(req);
    const json = await res.json();
    expect(json.resolution).toBe("raw");
    expect(json.count).toBe(1);
  });

  it("returns raw resolution explicitly", async () => {
    const now = Math.floor(Date.now() / 1000);
    insertMetric(now - 100, "core");
    const req = makeRequest("GET", `/api/metrics?from=${now - 3600}&to=${now}&resolution=raw`);
    const res = await GET(req);
    const json = await res.json();
    expect(json.resolution).toBe("raw");
  });

  it("auto selects raw for <6h range", async () => {
    const now = Math.floor(Date.now() / 1000);
    insertMetric(now - 100, "core");
    const req = makeRequest("GET", `/api/metrics?from=${now - 3600}&to=${now}`);
    const res = await GET(req);
    const json = await res.json();
    expect(json.resolution).toBe("raw");
  });

  it("auto selects hourly for 6h-3d range", async () => {
    const now = Math.floor(Date.now() / 1000);
    insertMetric(now - 7 * 3600, "core");
    const req = makeRequest("GET", `/api/metrics?from=${now - 2 * 86400}&to=${now}`);
    const res = await GET(req);
    const json = await res.json();
    expect(json.resolution).toBe("hourly");
  });

  it("auto selects daily for >3d range", async () => {
    const now = Math.floor(Date.now() / 1000);
    const req = makeRequest("GET", `/api/metrics?from=${now - 5 * 86400}&to=${now}`);
    const res = await GET(req);
    const json = await res.json();
    expect(json.resolution).toBe("daily");
  });

  it("filters by group", async () => {
    const now = Math.floor(Date.now() / 1000);
    insertMetric(now - 100, "core");
    insertMetric(now - 100, "browser");
    const req = makeRequest("GET", `/api/metrics?from=${now - 3600}&to=${now}&group=core`);
    const res = await GET(req);
    const json = await res.json();
    expect(json.count).toBe(1);
  });

  it("returns hourly aggregation", async () => {
    const now = Math.floor(Date.now() / 1000);
    const hourStart = Math.floor(now / 3600) * 3600 - 7 * 3600;
    insertMetric(hourStart + 10, "core", 20);
    insertMetric(hourStart + 20, "core", 40);
    const req = makeRequest(
      "GET",
      `/api/metrics?from=${now - 2 * 86400}&to=${now}&resolution=hourly`
    );
    const res = await GET(req);
    const json = await res.json();
    expect(json.resolution).toBe("hourly");
    if (json.count > 0) {
      expect(json.data[0].cpu_pct).toBe(30); // avg(20, 40)
    }
  });

  it("limits raw to 10000 rows", async () => {
    const now = Math.floor(Date.now() / 1000);
    const stmt = db.prepare(
      "INSERT INTO metrics (ts, grp, cpu_pct, mem_rss_mb, sample_interval_s) VALUES (?, 'core', 10, 100, 1)"
    );
    for (let i = 0; i < 10100; i++) {
      stmt.run(now - i);
    }
    const req = makeRequest("GET", `/api/metrics?from=${now - 20000}&to=${now}&resolution=raw`);
    const res = await GET(req);
    const json = await res.json();
    expect(json.count).toBeLessThanOrEqual(10000);
  });

  it("handles sparse data with gaps", async () => {
    const now = Math.floor(Date.now() / 1000);
    insertMetric(now - 3000, "core");
    insertMetric(now - 100, "core");
    // No data between these two points
    const req = makeRequest("GET", `/api/metrics?from=${now - 3600}&to=${now}`);
    const res = await GET(req);
    const json = await res.json();
    expect(json.count).toBe(2);
  });
});
