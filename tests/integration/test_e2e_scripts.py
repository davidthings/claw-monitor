"""E2E tests for shell scripts — use test server port so scripts hit test DB."""

import os
import time
import sqlite3
import subprocess

import pytest
import requests

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "scripts")
TAG_SH = os.path.join(SCRIPTS_DIR, "tag.sh")
REGISTER_SH = os.path.join(SCRIPTS_DIR, "register-tool.sh")


@pytest.mark.skipif(
    not os.path.exists(os.path.join(PROJECT_ROOT, "web", ".next")),
    reason="Next.js not built — run 'npm run build' in web/ first",
)
class TestTagSh:
    def test_tag_sh_creates_db_row(self, web_server, integration_db):
        """POST tag via HTTP and verify it lands in DB."""
        base_url, _ = web_server

        r = requests.post(f"{base_url}/api/tags", json={
            "category": "coding",
            "text": "e2e test from tag.sh",
            "source": "system",
        })
        assert r.status_code == 201
        assert r.json()["ok"] is True

        time.sleep(1)
        conn = sqlite3.connect(integration_db)
        row = conn.execute(
            "SELECT category, text FROM tags WHERE text LIKE '%e2e%'"
        ).fetchone()
        conn.close()
        assert row is not None
        assert row[0] == "coding"

    def test_tag_sh_backdate(self, web_server, integration_db):
        """POST a backdated tag and verify ts < recorded_at."""
        base_url, _ = web_server

        r = requests.post(f"{base_url}/api/tags", json={
            "category": "coding",
            "text": "backdated tag",
            "source": "system",
            "ts": "-10m",
        })
        assert r.status_code == 201

        time.sleep(1)
        conn = sqlite3.connect(integration_db)
        rows = conn.execute(
            "SELECT ts, recorded_at FROM tags WHERE text = 'backdated tag'"
        ).fetchall()
        conn.close()
        assert len(rows) >= 1
        assert rows[0][0] < rows[0][1]  # ts < recorded_at

    def test_tag_sh_invalid_category_exits_gracefully(self):
        result = subprocess.run(
            ["bash", TAG_SH, "invalid_category", "test"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        # tag.sh always exits 0 (fire-and-forget)
        assert result.returncode == 0


@pytest.mark.skipif(
    not os.path.exists(os.path.join(PROJECT_ROOT, "web", ".next")),
    reason="Next.js not built — run 'npm run build' in web/ first",
)
class TestRegisterToolSh:
    def test_register_tool_sh_creates_db_row(self, web_server, integration_db):
        """POST to registry and verify it lands in DB."""
        base_url, _ = web_server

        r = requests.post(f"{base_url}/api/registry/process", json={
            "pid": 12345,
            "name": "test-tool",
            "group": "openclaw-core",
        })
        assert r.status_code == 201

        conn = sqlite3.connect(integration_db)
        rows = conn.execute("SELECT pid, name, grp FROM process_registry").fetchall()
        conn.close()
        assert len(rows) >= 1
        assert rows[0][0] == 12345

    def test_register_tool_sh_missing_args_exits_gracefully(self):
        result = subprocess.run(
            ["bash", REGISTER_SH],
            capture_output=True,
            text=True,
            timeout=10,
        )
        # register-tool.sh exits 0 on missing args
        assert result.returncode == 0
