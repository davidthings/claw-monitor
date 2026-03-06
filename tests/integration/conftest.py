"""Shared fixtures for integration tests."""

import os
import sys
import time
import socket
import sqlite3
import subprocess
import signal

import pytest
import requests as req_lib

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
COLLECTOR_DIR = os.path.join(PROJECT_ROOT, "claw-collector")
WEB_DIR = os.path.join(PROJECT_ROOT, "web")
SCHEMA_PATH = os.path.join(PROJECT_ROOT, "schema.sql")

sys.path.insert(0, COLLECTOR_DIR)


def find_free_port():
    """Find a free TCP port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def integration_db(tmp_path):
    """Create a fresh test DB with schema applied."""
    db_path = str(tmp_path / "integration.db")
    conn = sqlite3.connect(db_path)
    with open(SCHEMA_PATH) as f:
        conn.executescript(f.read())
    conn.close()
    return db_path


@pytest.fixture
def collector_process(integration_db, tmp_path):
    """Start the collector as a subprocess with test DB."""
    env = os.environ.copy()
    env["CM_DB_PATH"] = integration_db
    env["CM_SLOW_LOOP_INTERVAL_S"] = "1"
    env["CM_FAST_LOOP_INTERVAL_S"] = "1"

    proc = subprocess.Popen(
        [sys.executable, os.path.join(COLLECTOR_DIR, "collector.py")],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    time.sleep(2)  # Let collector initialize

    yield proc

    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture
def web_server(integration_db):
    """Start the Next.js standalone server with test DB, wait for HTTP readiness."""
    port = find_free_port()
    standalone_server = os.path.join(WEB_DIR, ".next", "standalone", "server.js")
    env = os.environ.copy()
    env["CM_DB_PATH"] = integration_db
    env["CM_PORT"] = str(port)
    env["PORT"] = str(port)
    env["HOSTNAME"] = "127.0.0.1"
    env["NODE_ENV"] = "production"

    proc = subprocess.Popen(
        ["node", standalone_server],
        cwd=WEB_DIR,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Wait for HTTP readiness — middleware allows 127.0.0.1
    ready_url = f"http://127.0.0.1:{port}/api/registry"
    for _ in range(30):
        try:
            r = req_lib.get(ready_url, timeout=1)
            if r.status_code == 200:
                break
        except Exception:
            pass
        time.sleep(1)
    else:
        stderr_output = proc.stderr.read(4096).decode("utf-8", errors="replace") if proc.stderr else ""
        proc.kill()
        pytest.fail(f"Next.js server failed to become ready within 30s. stderr: {stderr_output}")

    yield f"http://127.0.0.1:{port}", proc

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture
def base_url(web_server):
    """Just the base URL string from web_server."""
    url, _ = web_server
    yield url


@pytest.fixture
def requests_session():
    """A requests.Session for making HTTP calls."""
    with req_lib.Session() as s:
        yield s


@pytest.fixture
def live_stack(web_server, integration_db):
    """Combined fixture: (base_url, db_path) for tests that need both."""
    url, _ = web_server
    yield url, integration_db
