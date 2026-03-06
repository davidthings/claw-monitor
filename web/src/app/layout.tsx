import "./globals.css";
import Link from "next/link";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Claw Monitor",
  description: "OpenClaw resource monitor",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <nav>
          <Link href="/" style={{ fontWeight: 700, color: "#e2e8f0" }}>
            CLAW MONITOR
          </Link>
          <Link href="/">Overview</Link>
          <Link href="/metrics">Metrics</Link>
          <Link href="/disk">Disk</Link>
          <Link href="/tokens">Tokens</Link>
          <Link href="/processes">Processes</Link>
          <Link href="/tags">Tags</Link>
        </nav>
        <main>{children}</main>
      </body>
    </html>
  );
}
