import { describe, it, expect } from "vitest";
import { GET } from "@/app/api/metrics/stream/route";

describe("GET /api/metrics/stream", () => {
  it("returns event-stream content type", async () => {
    const res = await GET();
    expect(res.headers.get("content-type")).toBe("text/event-stream");
    expect(res.headers.get("cache-control")).toBe("no-cache");
  });

  it.skip("sends ping every 30s — SSE integration test, requires running server", () => {});
  it.skip("receives new data when metrics are inserted — SSE integration test", () => {});
});
