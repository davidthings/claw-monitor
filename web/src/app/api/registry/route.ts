import { NextResponse } from "next/server";
import { getDb } from "@/lib/db";

export const dynamic = "force-dynamic";

export async function GET() {
  const db = getDb();
  const processes = db.prepare(
    "SELECT id, pid, name, grp, description, registered, unregistered FROM process_registry ORDER BY registered DESC LIMIT 200"
  ).all();
  return NextResponse.json({ processes });
}
