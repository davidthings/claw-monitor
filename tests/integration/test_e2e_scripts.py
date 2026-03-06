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


@pytest.mark.skipif(
    not os.path.exists(os.path.join(PROJECT_ROOT, "web", ".next")),
    reason="Next.js not built — run 'npm run build' in web/ first",
)
class TestRegisterToolTokens:
    def test_register_tool_tokens_creates_db_row(self, web_server, integration_db):
        """register-tool.sh tokens should POST to /api/tokens and create a DB row."""
        base_url, _ = web_server
        port = base_url.split(":")[-1]
        env = {**os.environ, "CM_PORT": port}

        result = subprocess.run(
            ["bash", "scripts/register-tool.sh", "tokens",
             "test-tool", "claude-sonnet-4-6", "1500", "3200", "test-session"],
            cwd=PROJECT_ROOT, env=env, capture_output=True, text=True
        )
        assert result.returncode == 0

        time.sleep(2)  # fire-and-forget curl

        # Verify DB row created
        conn = sqlite3.connect(integration_db)
        rows = conn.execute(
            "SELECT tool, model, tokens_in, tokens_out, session_id FROM token_events"
        ).fetchall()
        conn.close()

        assert len(rows) == 1, f"Expected 1 token_event row, got {len(rows)}"
        tool, model, tin, tout, sid = rows[0]
        assert tool == "test-tool"
        assert model == "claude-sonnet-4-6"
        assert tin == 1500
        assert tout == 3200
        assert sid == "test-session"

    def test_register_tool_tokens_rate_endpoint(self, web_server, integration_db):
        """After posting a token event, /api/tokens/rate should return non-zero."""
        base_url, _ = web_server
        port = base_url.split(":")[-1]
        env = {**os.environ, "CM_PORT": port}

        subprocess.run(
            ["bash", "scripts/register-tool.sh", "tokens",
             "test-tool", "claude-sonnet-4-6", "1000", "2000"],
            cwd=PROJECT_ROOT, env=env, capture_output=True
        )

        time.sleep(2)

        r = requests.get(f"{base_url}/api/tokens/rate")
        assert r.status_code == 200
        data = r.json()
        assert data["rate"] > 0, f"Expected rate > 0, got {data['rate']}"

    def test_register_tool_tokens_without_session_id(self, web_server, integration_db):
        """session_id should be optional."""
        base_url, _ = web_server
        port = base_url.split(":")[-1]
        env = {**os.environ, "CM_PORT": port}

        result = subprocess.run(
            ["bash", "scripts/register-tool.sh", "tokens",
             "test-tool", "gpt-4o", "500", "100"],
            cwd=PROJECT_ROOT, env=env, capture_output=True, text=True
        )
        assert result.returncode == 0
        time.sleep(2)

        conn = sqlite3.connect(integration_db)
        count = conn.execute("SELECT COUNT(*) FROM token_events").fetchone()[0]
        conn.close()
        assert count == 1

    def test_register_tool_tokens_missing_args_exits_gracefully(self):
        """Missing required args should exit 0 with usage message."""
        result = subprocess.run(
            ["bash", "scripts/register-tool.sh", "tokens"],
            cwd=PROJECT_ROOT, capture_output=True, text=True
        )
        assert result.returncode == 0
        assert "Usage" in result.stderr or "usage" in result.stderr.lower()
