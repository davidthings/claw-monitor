import pytest
import sqlite3
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


@pytest.fixture
def test_db(tmp_path, monkeypatch):
    import config
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(config, "DB_PATH", db_path)
    from db import open_db, init_schema
    conn = open_db()
    init_schema(conn)
    yield conn
    conn.close()
