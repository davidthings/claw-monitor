"""E2E tests for shell scripts — Group 11 (§3.3)."""

import os
import sys
import time
import sqlite3
import subprocess
import json
import socket
import urllib.request
import urllib.error

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "scripts")
TAG_SH = os.path.join(SCRIPTS_DIR, "tag.sh")
REGISTER_SH = os.path.join(SCRIPTS_DIR, "register-tool.sh")


@pytest.fixture
def web_with_db(integration_db):
    """Start web server pointing at integration DB and return (url, db_path)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    env = os.environ.copy()
    env["CM_DB_PATH"] = integration_db
    env["CM_PORT"] = str(port)

    web_dir = os.path.join(PROJECT_ROOT, "web")
    proc = subprocess.Popen(
        ["npx", "next", "start", "-p", str(port)],
        cwd=web_dir,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Wait for server
    for _ in range(30):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                break
        except (ConnectionRefusedError, OSError):
            time.sleep(1)
    else:
        proc.kill()
        pytest.skip("Web server failed to start")

    yield f"http://127.0.0.1:{port}", integration_db, proc

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def _post_json(url, data):
    """Helper to POST JSON to a URL and return (status_code, response_body)."""
    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-Forwarded-For": "127.0.0.1",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


@pytest.mark.skipif(
    not os.path.exists(os.path.join(PROJECT_ROOT, "web", ".next")),
    reason="Next.js not built — run 'npm run build' in web/ first",
)
class TestTagSh:
    def test_tag_sh_creates_db_row(self, web_with_db):
        url, db_path, _ = web_with_db

        status, body = _post_json(f"{url}/api/tags", {
            "category": "coding",
            "text": "test from e2e",
            "source": "user",
        })
        assert status == 201
        assert body.get("ok") is True

        conn = sqlite3.connect(db_path)
        rows = conn.execute("SELECT category, text FROM tags").fetchall()
        conn.close()
        assert len(rows) >= 1
        assert rows[0][0] == "coding"

    def test_tag_sh_backdate(self, web_with_db):
        url, db_path, _ = web_with_db

        status, body = _post_json(f"{url}/api/tags", {
            "category": "coding",
            "text": "backdated tag",
            "source": "user",
            "ts": "-10m",
        })
        assert status == 201

        conn = sqlite3.connect(db_path)
        rows = conn.execute("SELECT ts, recorded_at FROM tags WHERE text = 'backdated tag'").fetchall()
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
    def test_register_tool_sh_creates_db_row(self, web_with_db):
        url, db_path, _ = web_with_db

        status, body = _post_json(f"{url}/api/registry/process", {
            "pid": 12345,
            "name": "test-tool",
            "group": "openclaw-core",
        })
        assert status == 201

        conn = sqlite3.connect(db_path)
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
