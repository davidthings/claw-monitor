import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/db";

export async function GET(request: NextRequest) {
  const params = request.nextUrl.searchParams;
  const from = params.get("from");
  const to = params.get("to") || String(Math.floor(Date.now() / 1000));
  const group = params.get("group");
  const resolution = params.get("resolution") || "auto";

  if (!from) {
    return NextResponse.json({ error: "Missing required param: from" }, { status: 400 });
  }

  const fromTs = Number(from);
  const toTs = Number(to);
  const rangeS = toTs - fromTs;

  // Determine resolution
  let actualResolution = resolution;
  if (resolution === "auto") {
    if (rangeS < 6 * 3600) actualResolution = "raw";
    else if (rangeS < 3 * 86400) actualResolution = "hourly";
    else actualResolution = "daily";
  }

  const db = getDb();

  if (actualResolution === "daily") {
    const fromDate = new Date(fromTs * 1000).toISOString().slice(0, 10);
    const toDate = new Date(toTs * 1000).toISOString().slice(0, 10);
    let sql = "SELECT * FROM metrics_daily WHERE date >= ? AND date <= ?";
    const args: (string | number)[] = [fromDate, toDate];
    if (group) {
      sql += " AND grp = ?";
      args.push(group);
    }
    sql += " ORDER BY date";
    const data = db.prepare(sql).all(...args);
    return NextResponse.json({ data, count: data.length, resolution: "daily" });
  }

  // Raw or hourly
  let sql = "SELECT * FROM metrics WHERE ts >= ? AND ts <= ?";
  const args: (string | number)[] = [fromTs, toTs];
  if (group) {
    sql += " AND grp = ?";
    args.push(group);
  }
  sql += " ORDER BY ts";

  if (actualResolution === "hourly") {
    sql = `SELECT
      (ts / 3600) * 3600 as ts, grp,
      AVG(cpu_pct) as cpu_pct, AVG(mem_rss_mb) as mem_rss_mb,
      SUM(net_in_kb) as net_in_kb, SUM(net_out_kb) as net_out_kb,
      AVG(gpu_util_pct) as gpu_util_pct, AVG(gpu_vram_used_mb) as gpu_vram_used_mb,
      AVG(gpu_power_w) as gpu_power_w, AVG(sample_interval_s) as sample_interval_s
    FROM metrics WHERE ts >= ? AND ts <= ?`;
    const hArgs: (string | number)[] = [fromTs, toTs];
    if (group) {
      sql += " AND grp = ?";
      hArgs.push(group);
    }
    sql += " GROUP BY (ts / 3600), grp ORDER BY ts";
    const data = db.prepare(sql).all(...hArgs);
    return NextResponse.json({ data, count: data.length, resolution: "hourly" });
  }

  // Raw — limit to prevent huge responses
  sql += " LIMIT 10000";
  const data = db.prepare(sql).all(...args);
  return NextResponse.json({ data, count: data.length, resolution: "raw" });
}
