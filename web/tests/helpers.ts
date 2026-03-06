import Database from "better-sqlite3";
import fs from "fs";
import path from "path";
import { NextRequest } from "next/server";

export function testDb(): Database.Database {
  const schemaPath = path.resolve(__dirname, "../../schema.sql");
  const schema = fs.readFileSync(schemaPath, "utf-8");
  const db = new Database(":memory:");
  db.exec(schema);
  return db;
}

export function makeRequest(method: string, url: string, body?: unknown): NextRequest {
  const fullUrl = url.startsWith("http") ? url : `http://localhost${url}`;
  return new NextRequest(fullUrl, {
    method,
    body: body ? JSON.stringify(body) : undefined,
    headers: body ? { "content-type": "application/json" } : {},
  });
}
