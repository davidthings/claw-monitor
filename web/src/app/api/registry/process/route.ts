import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/db";

export async function POST(request: NextRequest) {
  const body = await request.json();
  const { pid, name, group, description } = body;

  if (!pid || !name || !group) {
    return NextResponse.json({ error: "Missing required fields: pid, name, group" }, { status: 400 });
  }

  const db = getDb();
  const registered = Math.floor(Date.now() / 1000);
  db.prepare(
    "INSERT INTO process_registry (pid, name, grp, description, registered) VALUES (?, ?, ?, ?, ?)"
  ).run(pid, name, group, description || null, registered);

  return NextResponse.json({ ok: true, registered }, { status: 201 });
}
