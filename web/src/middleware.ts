import { NextRequest, NextResponse } from "next/server";

function isTailscaleOrLocal(ip: string): boolean {
  if (ip === "127.0.0.1" || ip === "::1" || ip === "localhost") return true;
  // Tailscale CGNAT range: 100.64.0.0/10 (100.64.0.0 - 100.127.255.255)
  const parts = ip.split(".");
  if (parts.length === 4) {
    const a = parseInt(parts[0], 10);
    const b = parseInt(parts[1], 10);
    if (a === 100 && b >= 64 && b <= 127) return true;
  }
  return false;
}

export function middleware(request: NextRequest) {
  const forwarded = request.headers.get("x-forwarded-for");
  const ip = forwarded?.split(",")[0]?.trim() || request.headers.get("x-real-ip") || "127.0.0.1";

  if (!isTailscaleOrLocal(ip)) {
    return new NextResponse("Forbidden", { status: 403 });
  }

  return NextResponse.next();
}

export const config = {
  matcher: "/(.*)",
};
