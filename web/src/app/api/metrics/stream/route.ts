import { NextResponse } from "next/server";
import { getDb } from "@/lib/db";

export const dynamic = "force-dynamic";

export async function GET() {
  const encoder = new TextEncoder();

  const stream = new ReadableStream({
    start(controller) {
      let lastTs = Math.floor(Date.now() / 1000);
      let pingCounter = 0;

      // Send an initial comment immediately so HTTP headers are flushed to the client
      controller.enqueue(encoder.encode(": connected\n\n"));

      const interval = setInterval(() => {
        try {
          pingCounter++;

          // Send ping every 30s (30 iterations of 1s)
          if (pingCounter % 30 === 0) {
            controller.enqueue(encoder.encode(": ping\n\n"));
          }

          // Check for new metrics every second
          const db = getDb();
          const rows = db.prepare(
            "SELECT * FROM metrics WHERE ts > ? ORDER BY ts LIMIT 50"
          ).all(lastTs) as Array<Record<string, unknown>>;

          if (rows.length > 0) {
            // Group by timestamp
            const byTs: Record<number, Record<string, unknown>> = {};
            for (const row of rows) {
              const ts = row.ts as number;
              if (!byTs[ts]) byTs[ts] = { ts, groups: {}, sample_interval_s: row.sample_interval_s };
              const grp = row.grp as string;
              if (grp === "net") {
                (byTs[ts] as Record<string, unknown>).net = {
                  in_kb: row.net_in_kb,
                  out_kb: row.net_out_kb,
                };
              } else if (grp === "gpu") {
                (byTs[ts] as Record<string, unknown>).gpu = {
                  util_pct: row.gpu_util_pct,
                  vram_used_mb: row.gpu_vram_used_mb,
                  power_w: row.gpu_power_w,
                };
              } else {
                ((byTs[ts] as Record<string, unknown>).groups as Record<string, unknown>)[grp] = {
                  cpu_pct: row.cpu_pct,
                  mem_rss_mb: row.mem_rss_mb,
                };
              }
              if (ts > lastTs) lastTs = ts;
            }

            for (const event of Object.values(byTs)) {
              controller.enqueue(
                encoder.encode(`data: ${JSON.stringify(event)}\n\n`)
              );
            }
          }
        } catch {
          // DB might be briefly locked; skip this tick
        }
      }, 1000);

      // Cleanup on close
      const checkClosed = setInterval(() => {
        try {
          controller.enqueue(encoder.encode(""));
        } catch {
          clearInterval(interval);
          clearInterval(checkClosed);
        }
      }, 5000);
    },
  });

  return new NextResponse(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    },
  });
}
