import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/db";

export async function GET(request: NextRequest) {
  const params = request.nextUrl.searchParams;
  const from = params.get("from") || String(Math.floor(Date.now() / 1000) - 86400);
  const to = params.get("to") || String(Math.floor(Date.now() / 1000));
  const dirKey = params.get("dir_key");

  const db = getDb();
  let sql = "SELECT ts, dir_key, size_bytes, file_count, journald_mb FROM disk_snapshots WHERE ts >= ? AND ts <= ?";
  const args: (string | number)[] = [Number(from), Number(to)];

  if (dirKey) {
    sql += " AND dir_key = ?";
    args.push(dirKey);
  }
  sql += " ORDER BY ts DESC LIMIT 5000";

  const data = db.prepare(sql).all(...args);
  return NextResponse.json({ data });
}
