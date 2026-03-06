import { vi, beforeEach, describe, it, expect } from "vitest";
import { testDb, makeRequest } from "./helpers";
import type Database from "better-sqlite3";

vi.mock("@/lib/db", () => ({
  getDb: vi.fn(),
}));

import { getDb } from "@/lib/db";
import { POST } from "@/app/api/tokens/route";

let db: Database.Database;

beforeEach(() => {
  db = testDb();
  (getDb as ReturnType<typeof vi.fn>).mockReturnValue(db);
});

describe("POST /api/tokens", () => {
  it("inserts valid token event", async () => {
    const req = makeRequest("POST", "/api/tokens", {
      tool: "claude-code",
      model: "claude-sonnet-4-6",
      tokens_in: 1000,
      tokens_out: 500,
    });
    const res = await POST(req);
    expect(res.status).toBe(201);
    const json = await res.json();
    expect(json.ok).toBe(true);
  });

  it("inserts with minimal fields (tool + model)", async () => {
    const req = makeRequest("POST", "/api/tokens", {
      tool: "claude-code",
      model: "claude-sonnet-4-6",
    });
    const res = await POST(req);
    expect(res.status).toBe(201);
    const row = db.prepare("SELECT tokens_in, tokens_out FROM token_events WHERE id = 1").get() as {
      tokens_in: number;
      tokens_out: number;
    };
    expect(row.tokens_in).toBe(0);
    expect(row.tokens_out).toBe(0);
  });

  it("accepts session_id", async () => {
    const req = makeRequest("POST", "/api/tokens", {
      tool: "claude-code",
      model: "claude-sonnet-4-6",
      session_id: "sess-abc",
    });
    const res = await POST(req);
    expect(res.status).toBe(201);
    const row = db.prepare("SELECT session_id FROM token_events WHERE id = 1").get() as {
      session_id: string;
    };
    expect(row.session_id).toBe("sess-abc");
  });

  it("returns 400 for missing tool", async () => {
    const req = makeRequest("POST", "/api/tokens", {
      model: "claude-sonnet-4-6",
    });
    const res = await POST(req);
    expect(res.status).toBe(400);
  });

  it("returns 400 for missing model", async () => {
    const req = makeRequest("POST", "/api/tokens", {
      tool: "claude-code",
    });
    const res = await POST(req);
    expect(res.status).toBe(400);
  });
});
