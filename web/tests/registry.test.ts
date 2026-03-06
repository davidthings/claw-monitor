import { vi, beforeEach, describe, it, expect } from "vitest";
import { testDb, makeRequest } from "./helpers";
import type Database from "better-sqlite3";

vi.mock("@/lib/db", () => ({
  getDb: vi.fn(),
}));

import { getDb } from "@/lib/db";
import { POST } from "@/app/api/registry/process/route";
import { GET } from "@/app/api/registry/route";

let db: Database.Database;

beforeEach(() => {
  db = testDb();
  (getDb as ReturnType<typeof vi.fn>).mockReturnValue(db);
});

describe("POST /api/registry/process", () => {
  it("registers a valid process", async () => {
    const req = makeRequest("POST", "/api/registry/process", {
      pid: 1234,
      name: "test-proc",
      group: "openclaw-core",
    });
    const res = await POST(req);
    expect(res.status).toBe(201);
    const json = await res.json();
    expect(json.ok).toBe(true);
  });

  it("registers with description", async () => {
    const req = makeRequest("POST", "/api/registry/process", {
      pid: 1234,
      name: "test-proc",
      group: "openclaw-core",
      description: "test description",
    });
    const res = await POST(req);
    expect(res.status).toBe(201);
    const row = db.prepare("SELECT description FROM process_registry WHERE pid = 1234").get() as {
      description: string;
    };
    expect(row.description).toBe("test description");
  });

  it("returns 400 for missing pid", async () => {
    const req = makeRequest("POST", "/api/registry/process", {
      name: "test",
      group: "core",
    });
    const res = await POST(req);
    expect(res.status).toBe(400);
  });

  it("returns 400 for missing name", async () => {
    const req = makeRequest("POST", "/api/registry/process", {
      pid: 1234,
      group: "core",
    });
    const res = await POST(req);
    expect(res.status).toBe(400);
  });

  it("returns 400 for missing group", async () => {
    const req = makeRequest("POST", "/api/registry/process", {
      pid: 1234,
      name: "test",
    });
    const res = await POST(req);
    expect(res.status).toBe(400);
  });

  it("allows duplicate pid (inserts second row)", async () => {
    const req1 = makeRequest("POST", "/api/registry/process", {
      pid: 1234,
      name: "proc-a",
      group: "core",
    });
    const req2 = makeRequest("POST", "/api/registry/process", {
      pid: 1234,
      name: "proc-b",
      group: "browser",
    });
    await POST(req1);
    await POST(req2);
    const rows = db.prepare("SELECT * FROM process_registry WHERE pid = 1234").all();
    expect(rows).toHaveLength(2);
  });
});

describe("GET /api/registry", () => {
  it("returns registered processes", async () => {
    db.prepare(
      "INSERT INTO process_registry (pid, name, grp, registered) VALUES (100, 'test', 'core', ?)"
    ).run(Math.floor(Date.now() / 1000));
    const req = makeRequest("GET", "/api/registry");
    const res = await GET();
    const json = await res.json();
    expect(json.processes).toHaveLength(1);
    expect(json.processes[0].pid).toBe(100);
  });

  it("limits to 200 rows", async () => {
    const stmt = db.prepare(
      "INSERT INTO process_registry (pid, name, grp, registered) VALUES (?, 'test', 'core', ?)"
    );
    const now = Math.floor(Date.now() / 1000);
    for (let i = 0; i < 250; i++) {
      stmt.run(i, now);
    }
    const res = await GET();
    const json = await res.json();
    expect(json.processes.length).toBeLessThanOrEqual(200);
  });

  it("includes unregistered processes", async () => {
    const now = Math.floor(Date.now() / 1000);
    db.prepare(
      "INSERT INTO process_registry (pid, name, grp, registered, unregistered) VALUES (100, 'test', 'core', ?, ?)"
    ).run(now - 100, now);
    const res = await GET();
    const json = await res.json();
    expect(json.processes).toHaveLength(1);
    expect(json.processes[0].unregistered).not.toBeNull();
  });
});
