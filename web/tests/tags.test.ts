import { vi, beforeEach, describe, it, expect } from "vitest";
import { testDb, makeRequest } from "./helpers";
import type Database from "better-sqlite3";

vi.mock("@/lib/db", () => ({
  getDb: vi.fn(),
}));

import { getDb } from "@/lib/db";
import { POST, GET } from "@/app/api/tags/route";

let db: Database.Database;

beforeEach(() => {
  db = testDb();
  (getDb as ReturnType<typeof vi.fn>).mockReturnValue(db);
});

describe("POST /api/tags", () => {
  it("creates a tag with minimal valid fields", async () => {
    const req = makeRequest("POST", "/api/tags", {
      category: "coding",
      text: "working on tests",
      source: "user",
    });
    const res = await POST(req);
    expect(res.status).toBe(201);
    const json = await res.json();
    expect(json.ok).toBe(true);
    expect(json.id).toBeDefined();
  });

  it("returns 400 for missing category", async () => {
    const req = makeRequest("POST", "/api/tags", {
      text: "test",
      source: "user",
    });
    const res = await POST(req);
    expect(res.status).toBe(400);
  });

  it("returns 400 for missing text", async () => {
    const req = makeRequest("POST", "/api/tags", {
      category: "coding",
      source: "user",
    });
    const res = await POST(req);
    expect(res.status).toBe(400);
  });

  it("returns 400 for missing source", async () => {
    const req = makeRequest("POST", "/api/tags", {
      category: "coding",
      text: "test",
    });
    const res = await POST(req);
    expect(res.status).toBe(400);
  });

  it("returns 400 for invalid category", async () => {
    const req = makeRequest("POST", "/api/tags", {
      category: "invalid-cat",
      text: "test",
      source: "user",
    });
    const res = await POST(req);
    expect(res.status).toBe(400);
  });

  it("returns 400 for invalid source", async () => {
    const req = makeRequest("POST", "/api/tags", {
      category: "coding",
      text: "test",
      source: "invalid-source",
    });
    const res = await POST(req);
    expect(res.status).toBe(400);
  });

  it("accepts backdate with unix timestamp", async () => {
    const ts = 1700000000;
    const req = makeRequest("POST", "/api/tags", {
      category: "coding",
      text: "backdated",
      source: "user",
      ts,
    });
    const res = await POST(req);
    expect(res.status).toBe(201);
    const row = db.prepare("SELECT ts FROM tags WHERE id = 1").get() as { ts: number };
    expect(row.ts).toBe(ts);
  });

  it("accepts backdate with relative minutes", async () => {
    const before = Math.floor(Date.now() / 1000);
    const req = makeRequest("POST", "/api/tags", {
      category: "coding",
      text: "relative",
      source: "user",
      ts: "-10m",
    });
    const res = await POST(req);
    expect(res.status).toBe(201);
    const row = db.prepare("SELECT ts FROM tags WHERE id = 1").get() as { ts: number };
    expect(row.ts).toBeLessThan(before);
    expect(row.ts).toBeGreaterThan(before - 700); // ~10min ago with some slack
  });

  it("accepts backdate with relative seconds", async () => {
    const before = Math.floor(Date.now() / 1000);
    const req = makeRequest("POST", "/api/tags", {
      category: "coding",
      text: "relative-sec",
      source: "user",
      ts: "-30s",
    });
    const res = await POST(req);
    expect(res.status).toBe(201);
    const row = db.prepare("SELECT ts FROM tags WHERE id = 1").get() as { ts: number };
    expect(row.ts).toBeGreaterThan(before - 40);
  });

  it("accepts backdate with relative hours", async () => {
    const before = Math.floor(Date.now() / 1000);
    const req = makeRequest("POST", "/api/tags", {
      category: "coding",
      text: "relative-hr",
      source: "user",
      ts: "-2h",
    });
    const res = await POST(req);
    expect(res.status).toBe(201);
    const row = db.prepare("SELECT ts FROM tags WHERE id = 1").get() as { ts: number };
    expect(row.ts).toBeLessThan(before - 7000);
  });

  it("accepts backdate with natural language", async () => {
    const before = Math.floor(Date.now() / 1000);
    const req = makeRequest("POST", "/api/tags", {
      category: "coding",
      text: "natural",
      source: "user",
      ts: "10 minutes ago",
    });
    const res = await POST(req);
    expect(res.status).toBe(201);
    const row = db.prepare("SELECT ts FROM tags WHERE id = 1").get() as { ts: number };
    expect(row.ts).toBeLessThan(before);
  });

  it("accepts backdate with ISO-8601", async () => {
    const req = makeRequest("POST", "/api/tags", {
      category: "coding",
      text: "iso",
      source: "user",
      ts: "2026-03-06T08:00:00Z",
    });
    const res = await POST(req);
    expect(res.status).toBe(201);
    const row = db.prepare("SELECT ts FROM tags WHERE id = 1").get() as { ts: number };
    expect(row.ts).toBe(Math.floor(Date.parse("2026-03-06T08:00:00Z") / 1000));
  });

  it("returns 400 for unparseable ts", async () => {
    const req = makeRequest("POST", "/api/tags", {
      category: "coding",
      text: "bad ts",
      source: "user",
      ts: "not-a-time",
    });
    const res = await POST(req);
    expect(res.status).toBe(400);
  });

  it("uses now when ts is null", async () => {
    const before = Math.floor(Date.now() / 1000);
    const req = makeRequest("POST", "/api/tags", {
      category: "coding",
      text: "null ts",
      source: "user",
      ts: null,
    });
    const res = await POST(req);
    expect(res.status).toBe(201);
    const row = db.prepare("SELECT ts FROM tags WHERE id = 1").get() as { ts: number };
    expect(row.ts).toBeGreaterThanOrEqual(before);
    expect(row.ts).toBeLessThanOrEqual(before + 2);
  });

  it("uses now when ts is omitted", async () => {
    const before = Math.floor(Date.now() / 1000);
    const req = makeRequest("POST", "/api/tags", {
      category: "coding",
      text: "no ts",
      source: "user",
    });
    const res = await POST(req);
    expect(res.status).toBe(201);
    const row = db.prepare("SELECT ts FROM tags WHERE id = 1").get() as { ts: number };
    expect(row.ts).toBeGreaterThanOrEqual(before);
  });

  it("accepts session_id", async () => {
    const req = makeRequest("POST", "/api/tags", {
      category: "coding",
      text: "with session",
      source: "user",
      session_id: "sess-123",
    });
    const res = await POST(req);
    expect(res.status).toBe(201);
    const row = db.prepare("SELECT session_id FROM tags WHERE id = 1").get() as {
      session_id: string;
    };
    expect(row.session_id).toBe("sess-123");
  });
});

describe("GET /api/tags", () => {
  function insertTag(ts: number, category: string, source: string, text = "test") {
    db.prepare(
      "INSERT INTO tags (ts, recorded_at, category, text, source) VALUES (?, ?, ?, ?, ?)"
    ).run(ts, ts, category, text, source);
  }

  it("returns all tags in range", async () => {
    const now = Math.floor(Date.now() / 1000);
    insertTag(now - 100, "coding", "user");
    insertTag(now - 50, "research", "user");
    const req = makeRequest("GET", `/api/tags?from=${now - 200}&to=${now}`);
    const res = await GET(req);
    const json = await res.json();
    expect(json.tags).toHaveLength(2);
  });

  it("filters by category", async () => {
    const now = Math.floor(Date.now() / 1000);
    insertTag(now - 100, "coding", "user");
    insertTag(now - 50, "research", "user");
    const req = makeRequest(
      "GET",
      `/api/tags?from=${now - 200}&to=${now}&category=coding`
    );
    const res = await GET(req);
    const json = await res.json();
    expect(json.tags).toHaveLength(1);
    expect((json.tags[0] as { category: string }).category).toBe("coding");
  });

  it("filters by source", async () => {
    const now = Math.floor(Date.now() / 1000);
    insertTag(now - 100, "coding", "user");
    insertTag(now - 50, "coding", "system");
    const req = makeRequest(
      "GET",
      `/api/tags?from=${now - 200}&to=${now}&source=system`
    );
    const res = await GET(req);
    const json = await res.json();
    expect(json.tags).toHaveLength(1);
  });

  it("limits to 500 rows", async () => {
    const now = Math.floor(Date.now() / 1000);
    for (let i = 0; i < 600; i++) {
      insertTag(now - i, "coding", "user", `tag-${i}`);
    }
    const req = makeRequest("GET", `/api/tags?from=${now - 1000}&to=${now}`);
    const res = await GET(req);
    const json = await res.json();
    expect(json.tags).toHaveLength(500);
  });

  it("includes recorded_at field", async () => {
    const now = Math.floor(Date.now() / 1000);
    insertTag(now - 100, "coding", "user");
    const req = makeRequest("GET", `/api/tags?from=${now - 200}&to=${now}`);
    const res = await GET(req);
    const json = await res.json();
    expect(json.tags[0]).toHaveProperty("recorded_at");
  });
});
