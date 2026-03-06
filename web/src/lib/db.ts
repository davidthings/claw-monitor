import Database from "better-sqlite3";
import path from "path";
import os from "os";

let _db: Database.Database | null = null;

export function getDb(): Database.Database {
  if (!_db) {
    const dbPath = process.env.CM_DB_PATH ?? path.join(os.homedir(), ".openclaw", "claw-monitor", "metrics.db");
    _db = new Database(dbPath);
    _db.pragma("journal_mode = WAL");
    _db.pragma("busy_timeout = 5000");
  }
  return _db;
}
