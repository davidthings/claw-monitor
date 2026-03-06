import { NextResponse } from "next/server";
import { getDb } from "@/lib/db";

export const dynamic = "force-dynamic";

export async function GET() {
  const db = getDb();
  const since = Math.floor(Date.now() / 1000) - 60;
  const row = db.prepare(
    "SELECT COALESCE(SUM(tokens_in + tokens_out), 0) as total FROM token_events WHERE ts >= ?"
  ).get(since) as { total: number };
  return NextResponse.json({ rate: row.total });
}
