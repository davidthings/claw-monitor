import { vi, beforeEach, describe, it, expect } from "vitest";
import { testDb, makeRequest } from "./helpers";
import type Database from "better-sqlite3";

vi.mock("@/lib/db", () => ({
  getDb: vi.fn(),
}));

import { getDb } from "@/lib/db";
import { GET } from "@/app/api/disk/route";

let db: Database.Database;

beforeEach(() => {
  db = testDb();
  (getDb as ReturnType<typeof vi.fn>).mockReturnValue(db);
});

function insertDisk(ts: number, dirKey: string, sizeBytes = 1024, fileCount = 10) {
  db.prepare(
    "INSERT INTO disk_snapshots (ts, dir_key, size_bytes, file_count) VALUES (?, ?, ?, ?)"
  ).run(ts, dirKey, sizeBytes, fileCount);
}

describe("GET /api/disk", () => {
  it("returns data with default range (last 24h)", async () => {
    const now = Math.floor(Date.now() / 1000);
    insertDisk(now - 100, "monitor-db");
    insertDisk(now - 100000, "monitor-db"); // outside 24h
    const req = makeRequest("GET", "/api/disk");
    const res = await GET(req);
    const json = await res.json();
    expect(json.data).toHaveLength(1);
  });

  it("returns data with custom range", async () => {
    const now = Math.floor(Date.now() / 1000);
    insertDisk(now - 100, "monitor-db");
    insertDisk(now - 200, "monitor-db");
    const req = makeRequest("GET", `/api/disk?from=${now - 300}&to=${now}`);
    const res = await GET(req);
    const json = await res.json();
    expect(json.data).toHaveLength(2);
  });

  it("filters by dir_key", async () => {
    const now = Math.floor(Date.now() / 1000);
    insertDisk(now - 100, "monitor-db");
    insertDisk(now - 100, "openclaw-total");
    const req = makeRequest("GET", `/api/disk?from=${now - 300}&to=${now}&dir_key=monitor-db`);
    const res = await GET(req);
    const json = await res.json();
    expect(json.data).toHaveLength(1);
  });

  it("limits to 5000 rows", async () => {
    const now = Math.floor(Date.now() / 1000);
    const stmt = db.prepare(
      "INSERT INTO disk_snapshots (ts, dir_key, size_bytes, file_count) VALUES (?, 'test', 1024, 10)"
    );
    for (let i = 0; i < 5100; i++) {
      stmt.run(now - i);
    }
    const req = makeRequest("GET", `/api/disk?from=${now - 10000}&to=${now}`);
    const res = await GET(req);
    const json = await res.json();
    expect(json.data.length).toBeLessThanOrEqual(5000);
  });

  it("returns results in DESC order", async () => {
    const now = Math.floor(Date.now() / 1000);
    insertDisk(now - 200, "test");
    insertDisk(now - 100, "test");
    const req = makeRequest("GET", `/api/disk?from=${now - 300}&to=${now}`);
    const res = await GET(req);
    const json = await res.json();
    expect(json.data[0].ts).toBeGreaterThan(json.data[1].ts);
  });
});
