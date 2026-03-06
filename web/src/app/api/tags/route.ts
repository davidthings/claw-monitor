import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/db";

const VALID_CATEGORIES = new Set([
  "conversation", "coding", "research", "agent", "heartbeat", "qwen", "idle", "other",
]);
const VALID_SOURCES = new Set(["clawbot", "user", "system", "auto", "openclaw", "david"]); // legacy values kept for backcompat

/**
 * Parse an optional `ts` field from the request body.
 *
 * Accepts:
 *   - Omitted / null           → now
 *   - Unix timestamp (number)  → used directly
 *   - ISO-8601 string          → parsed as absolute time
 *   - "-Nm" / "-Ns" / "-Nh"   → relative delta: N minutes/seconds/hours ago
 *   - "10 minutes ago"  etc.   → natural relative (minutes/seconds/hours only)
 *
 * Returns unix timestamp (seconds) or null if unparseable.
 */
function resolveTs(raw: unknown): number | null {
  const now = Math.floor(Date.now() / 1000);
  if (raw == null) return now;

  // Numeric unix timestamp
  if (typeof raw === "number") return Math.floor(raw);

  if (typeof raw !== "string") return null;
  const s = raw.trim();

  // Relative: -10m, -30s, -2h  (leading minus optional)
  const relMatch = s.match(/^-?(\d+(?:\.\d+)?)\s*(m|min|minutes?|s|sec|seconds?|h|hr|hours?)$/i);
  if (relMatch) {
    const n = parseFloat(relMatch[1]);
    const unit = relMatch[2].toLowerCase();
    const secs = unit.startsWith("h") ? n * 3600 : unit.startsWith("m") ? n * 60 : n;
    return Math.floor(now - secs);
  }

  // Natural: "10 minutes ago", "30 seconds ago", "2 hours ago"
  const naturalMatch = s.match(/^(\d+(?:\.\d+)?)\s*(m|min|minutes?|s|sec|seconds?|h|hr|hours?)\s+ago$/i);
  if (naturalMatch) {
    const n = parseFloat(naturalMatch[1]);
    const unit = naturalMatch[2].toLowerCase();
    const secs = unit.startsWith("h") ? n * 3600 : unit.startsWith("m") ? n * 60 : n;
    return Math.floor(now - secs);
  }

  // Absolute: ISO-8601 or any Date-parseable string
  const parsed = Date.parse(s);
  if (!isNaN(parsed)) return Math.floor(parsed / 1000);

  return null;
}

export async function POST(request: NextRequest) {
  const body = await request.json();
  const { category, text, source, session_id, ts: rawTs } = body;

  if (!category || !text || !source) {
    return NextResponse.json({ error: "Missing required fields: category, text, source" }, { status: 400 });
  }
  if (!VALID_CATEGORIES.has(category)) {
    return NextResponse.json({ error: `Invalid category. Valid: ${[...VALID_CATEGORIES].join(", ")}` }, { status: 400 });
  }
  if (!VALID_SOURCES.has(source)) {
    return NextResponse.json({ error: `Invalid source. Valid: ${[...VALID_SOURCES].join(", ")}` }, { status: 400 });
  }

  const ts = resolveTs(rawTs);
  if (ts === null) {
    return NextResponse.json({ error: `Cannot parse ts: "${rawTs}". Use unix timestamp, ISO-8601, "-10m", or "10 minutes ago".` }, { status: 400 });
  }
  const recordedAt = Math.floor(Date.now() / 1000); // always wall-clock now

  const db = getDb();
  const result = db.prepare(
    "INSERT INTO tags (ts, recorded_at, category, text, source, session_id) VALUES (?, ?, ?, ?, ?, ?)"
  ).run(ts, recordedAt, category, text, source, session_id || null);

  return NextResponse.json({ ok: true, id: result.lastInsertRowid }, { status: 201 });
}

export async function GET(request: NextRequest) {
  const params = request.nextUrl.searchParams;
  const from = params.get("from");
  const to = params.get("to") || String(Math.floor(Date.now() / 1000));
  const category = params.get("category");
  const source = params.get("source");

  const db = getDb();
  let sql = "SELECT id, ts, recorded_at, category, text, source, session_id FROM tags WHERE 1=1";
  const args: (string | number)[] = [];

  if (from) {
    sql += " AND ts >= ?";
    args.push(Number(from));
  }
  sql += " AND ts <= ?";
  args.push(Number(to));

  if (category) {
    sql += " AND category = ?";
    args.push(category);
  }
  if (source) {
    sql += " AND source = ?";
    args.push(source);
  }

  sql += " ORDER BY ts DESC LIMIT 500";
  const tags = db.prepare(sql).all(...args);
  return NextResponse.json({ tags });
}
