"""Shared fixtures for integration tests."""

import os
import sys
import time
import socket
import sqlite3
import subprocess
import signal

import pytest

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
    """Start the Next.js dev server with test DB."""
    port = find_free_port()
    env = os.environ.copy()
    env["CM_DB_PATH"] = integration_db
    env["CM_PORT"] = str(port)
    env["NODE_ENV"] = "development"

    proc = subprocess.Popen(
        ["npx", "next", "start", "-p", str(port)],
        cwd=WEB_DIR,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Wait for server to be ready
    for _ in range(30):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                break
        except (ConnectionRefusedError, OSError):
            time.sleep(1)

    yield f"http://127.0.0.1:{port}", proc

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
