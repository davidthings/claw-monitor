import { describe, it, expect } from "vitest";
import { NextRequest } from "next/server";
import { middleware } from "@/middleware";

function makeMiddlewareRequest(headers: Record<string, string> = {}) {
  return new NextRequest("http://localhost/", { headers });
}

describe("middleware IP guard", () => {
  it("allows localhost ipv4", () => {
    const req = makeMiddlewareRequest({ "x-forwarded-for": "127.0.0.1" });
    const res = middleware(req);
    expect(res.status).not.toBe(403);
  });

  it("allows localhost ipv6", () => {
    const req = makeMiddlewareRequest({ "x-forwarded-for": "::1" });
    const res = middleware(req);
    expect(res.status).not.toBe(403);
  });

  it("allows tailscale CGNAT low boundary", () => {
    const req = makeMiddlewareRequest({ "x-forwarded-for": "100.64.0.1" });
    const res = middleware(req);
    expect(res.status).not.toBe(403);
  });

  it("allows tailscale CGNAT mid range", () => {
    const req = makeMiddlewareRequest({ "x-forwarded-for": "100.100.50.25" });
    const res = middleware(req);
    expect(res.status).not.toBe(403);
  });

  it("allows tailscale CGNAT high boundary", () => {
    const req = makeMiddlewareRequest({ "x-forwarded-for": "100.127.255.255" });
    const res = middleware(req);
    expect(res.status).not.toBe(403);
  });

  it("rejects tailscale boundary below (100.63.x.x)", () => {
    const req = makeMiddlewareRequest({ "x-forwarded-for": "100.63.255.255" });
    const res = middleware(req);
    expect(res.status).toBe(403);
  });

  it("rejects tailscale boundary above (100.128.x.x)", () => {
    const req = makeMiddlewareRequest({ "x-forwarded-for": "100.128.0.1" });
    const res = middleware(req);
    expect(res.status).toBe(403);
  });

  it("rejects public IP", () => {
    const req = makeMiddlewareRequest({ "x-forwarded-for": "8.8.8.8" });
    const res = middleware(req);
    expect(res.status).toBe(403);
  });

  it("uses first forwarded IP", () => {
    const req = makeMiddlewareRequest({
      "x-forwarded-for": "100.100.1.1, 8.8.8.8",
    });
    const res = middleware(req);
    expect(res.status).not.toBe(403);
  });

  it("falls back to x-real-ip", () => {
    const req = makeMiddlewareRequest({ "x-real-ip": "100.100.1.1" });
    const res = middleware(req);
    expect(res.status).not.toBe(403);
  });

  it("defaults to localhost when no headers", () => {
    const req = makeMiddlewareRequest({});
    const res = middleware(req);
    expect(res.status).not.toBe(403);
  });
});
