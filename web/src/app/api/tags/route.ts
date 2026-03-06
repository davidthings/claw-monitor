import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/db";

const VALID_CATEGORIES = new Set([
  "conversation", "coding", "research", "agent", "heartbeat", "qwen", "idle", "other",
]);
const VALID_SOURCES = new Set(["openclaw", "david", "system", "auto"]);

export async function POST(request: NextRequest) {
  const body = await request.json();
  const { category, text, source, session_id } = body;

  if (!category || !text || !source) {
    return NextResponse.json({ error: "Missing required fields: category, text, source" }, { status: 400 });
  }
  if (!VALID_CATEGORIES.has(category)) {
    return NextResponse.json({ error: `Invalid category. Valid: ${[...VALID_CATEGORIES].join(", ")}` }, { status: 400 });
  }
  if (!VALID_SOURCES.has(source)) {
    return NextResponse.json({ error: `Invalid source. Valid: ${[...VALID_SOURCES].join(", ")}` }, { status: 400 });
  }

  const db = getDb();
  const ts = Math.floor(Date.now() / 1000);
  const result = db.prepare(
    "INSERT INTO tags (ts, category, text, source, session_id) VALUES (?, ?, ?, ?, ?)"
  ).run(ts, category, text, source, session_id || null);

  return NextResponse.json({ ok: true, id: result.lastInsertRowid }, { status: 201 });
}

export async function GET(request: NextRequest) {
  const params = request.nextUrl.searchParams;
  const from = params.get("from");
  const to = params.get("to") || String(Math.floor(Date.now() / 1000));
  const category = params.get("category");
  const source = params.get("source");

  const db = getDb();
  let sql = "SELECT id, ts, category, text, source, session_id FROM tags WHERE 1=1";
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
