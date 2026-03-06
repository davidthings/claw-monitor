import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/db";
import { estimateCost } from "@/lib/cost";

export async function GET(request: NextRequest) {
  const params = request.nextUrl.searchParams;
  const from = params.get("from") || String(Math.floor(Date.now() / 1000) - 86400);
  const to = params.get("to") || String(Math.floor(Date.now() / 1000));
  const groupBy = params.get("group_by") || "tool";

  const db = getDb();
  const validGroupBy = ["tool", "model", "session_id"];
  const col = validGroupBy.includes(groupBy) ? groupBy : "tool";

  const rows = db.prepare(
    `SELECT ${col}, model,
       SUM(tokens_in) as total_in,
       SUM(tokens_out) as total_out,
       COUNT(*) as call_count
     FROM token_events
     WHERE ts >= ? AND ts <= ?
     GROUP BY ${col}`
  ).all(Number(from), Number(to)) as Array<Record<string, unknown>>;

  const summary = rows.map((row) => ({
    ...row,
    est_cost_usd: estimateCost(
      String(row.model || ""),
      Number(row.total_in || 0),
      Number(row.total_out || 0)
    ),
  }));

  let totalIn = 0, totalOut = 0, totalCalls = 0, totalCost = 0;
  for (const s of summary) {
    totalIn += Number(s.total_in || 0);
    totalOut += Number(s.total_out || 0);
    totalCalls += Number(s.call_count || 0);
    totalCost += s.est_cost_usd;
  }

  return NextResponse.json({
    summary,
    totals: {
      tokens_in: totalIn,
      tokens_out: totalOut,
      calls: totalCalls,
      est_cost_usd: Math.round(totalCost * 100) / 100,
    },
  });
}
