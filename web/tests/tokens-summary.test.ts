import { vi, beforeEach, describe, it, expect } from "vitest";
import { testDb, makeRequest } from "./helpers";
import type Database from "better-sqlite3";

vi.mock("@/lib/db", () => ({
  getDb: vi.fn(),
}));
vi.mock("@/lib/cost", async (importOriginal) => {
  return await importOriginal();
});

import { getDb } from "@/lib/db";
import { GET } from "@/app/api/tokens/summary/route";

let db: Database.Database;

beforeEach(() => {
  db = testDb();
  (getDb as ReturnType<typeof vi.fn>).mockReturnValue(db);
});

function insertToken(
  ts: number,
  tool: string,
  model: string,
  tokensIn: number,
  tokensOut: number,
  sessionId?: string
) {
  db.prepare(
    "INSERT INTO token_events (ts, tool, model, tokens_in, tokens_out, session_id) VALUES (?, ?, ?, ?, ?, ?)"
  ).run(ts, tool, model, tokensIn, tokensOut, sessionId || null);
}

describe("GET /api/tokens/summary", () => {
  it("groups by tool", async () => {
    const now = Math.floor(Date.now() / 1000);
    insertToken(now - 100, "claude-code", "claude-sonnet-4-6", 1000, 500);
    insertToken(now - 50, "claude-code", "claude-sonnet-4-6", 2000, 1000);
    const req = makeRequest("GET", `/api/tokens/summary?from=${now - 200}&to=${now}&group_by=tool`);
    const res = await GET(req);
    const json = await res.json();
    expect(json.summary).toHaveLength(1);
    expect(json.summary[0].total_in).toBe(3000);
  });

  it("groups by model", async () => {
    const now = Math.floor(Date.now() / 1000);
    insertToken(now - 100, "tool-a", "claude-sonnet-4-6", 1000, 500);
    insertToken(now - 50, "tool-b", "claude-haiku-4-5", 2000, 1000);
    const req = makeRequest("GET", `/api/tokens/summary?from=${now - 200}&to=${now}&group_by=model`);
    const res = await GET(req);
    const json = await res.json();
    expect(json.summary).toHaveLength(2);
  });

  it("groups by session", async () => {
    const now = Math.floor(Date.now() / 1000);
    insertToken(now - 100, "tool", "model", 1000, 500, "sess-1");
    insertToken(now - 50, "tool", "model", 2000, 1000, "sess-2");
    const req = makeRequest(
      "GET",
      `/api/tokens/summary?from=${now - 200}&to=${now}&group_by=session_id`
    );
    const res = await GET(req);
    const json = await res.json();
    expect(json.summary).toHaveLength(2);
  });

  it("defaults to tool for invalid group_by", async () => {
    const now = Math.floor(Date.now() / 1000);
    insertToken(now - 100, "claude-code", "claude-sonnet-4-6", 1000, 500);
    const req = makeRequest(
      "GET",
      `/api/tokens/summary?from=${now - 200}&to=${now}&group_by=invalid`
    );
    const res = await GET(req);
    const json = await res.json();
    // Should not crash, should default to tool
    expect(json.summary).toBeDefined();
  });

  it("includes cost calculation", async () => {
    const now = Math.floor(Date.now() / 1000);
    insertToken(now - 100, "claude-code", "claude-sonnet-4-6", 1_000_000, 1_000_000);
    const req = makeRequest("GET", `/api/tokens/summary?from=${now - 200}&to=${now}`);
    const res = await GET(req);
    const json = await res.json();
    expect(json.summary[0].est_cost_usd).toBe(3.0 + 15.0);
  });

  it("returns zero cost for unknown model", async () => {
    const now = Math.floor(Date.now() / 1000);
    insertToken(now - 100, "tool", "unknown-model", 1000, 500);
    const req = makeRequest("GET", `/api/tokens/summary?from=${now - 200}&to=${now}`);
    const res = await GET(req);
    const json = await res.json();
    expect(json.summary[0].est_cost_usd).toBe(0);
  });

  it("includes totals", async () => {
    const now = Math.floor(Date.now() / 1000);
    insertToken(now - 100, "tool-a", "claude-sonnet-4-6", 1000, 500);
    insertToken(now - 50, "tool-b", "claude-sonnet-4-6", 2000, 1000);
    const req = makeRequest("GET", `/api/tokens/summary?from=${now - 200}&to=${now}`);
    const res = await GET(req);
    const json = await res.json();
    expect(json.totals.tokens_in).toBe(3000);
    expect(json.totals.tokens_out).toBe(1500);
    expect(json.totals.calls).toBe(2);
  });
});
