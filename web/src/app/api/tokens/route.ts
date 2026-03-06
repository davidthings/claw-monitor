import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/db";

export async function GET(request: NextRequest) {
  const params = request.nextUrl.searchParams;
  const from = params.get("from");
  const to = params.get("to") || String(Math.floor(Date.now() / 1000));

  if (!from) {
    return NextResponse.json({ error: "Missing required param: from" }, { status: 400 });
  }

  const db = getDb();
  const rows = db.prepare(
    "SELECT ts, tokens_in, tokens_out FROM token_events WHERE ts >= ? AND ts <= ? ORDER BY ts LIMIT 10000"
  ).all(Number(from), Number(to));
  return NextResponse.json({ events: rows });
}

export async function POST(request: NextRequest) {
  const body = await request.json();
  const { tool, model, tokens_in, tokens_out, session_id } = body;

  if (!tool || !model) {
    return NextResponse.json({ error: "Missing required fields: tool, model" }, { status: 400 });
  }

  const db = getDb();
  const ts = Math.floor(Date.now() / 1000);
  const result = db.prepare(
    "INSERT INTO token_events (ts, tool, model, tokens_in, tokens_out, session_id) VALUES (?, ?, ?, ?, ?, ?)"
  ).run(ts, tool, model, tokens_in || 0, tokens_out || 0, session_id || null);

  return NextResponse.json({ ok: true, id: result.lastInsertRowid }, { status: 201 });
}
