"""Tests for disk_tracker.py — Group 5 (§1.4)."""

import os
import sys
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from disk_tracker import scan_directory, get_journald_size


def test_scan_directory_counts_files_and_bytes(tmp_path):
    f1 = tmp_path / "a.txt"
    f1.write_text("hello")
    f2 = tmp_path / "b.txt"
    f2.write_text("world!")
    size, count = scan_directory(str(tmp_path))
    assert count == 2
    assert size == len("hello") + len("world!")


def test_scan_directory_recursive(tmp_path):
    sub = tmp_path / "sub"
    sub.mkdir()
    (tmp_path / "a.txt").write_text("aaa")
    (sub / "b.txt").write_text("bbbbb")
    size, count = scan_directory(str(tmp_path))
    assert count == 2
    assert size == 3 + 5


def test_scan_directory_nonexistent_returns_zeros():
    size, count = scan_directory("/nonexistent/path/abc123")
    assert size == 0
    assert count == 0


def test_scan_directory_permission_error_partial(tmp_path):
    # Create a file we can read and one we can't
    f1 = tmp_path / "readable.txt"
    f1.write_text("data")
    f2 = tmp_path / "unreadable.txt"
    f2.write_text("secret")

    try:
        os.chmod(str(f2), 0o000)
        size, count = scan_directory(str(tmp_path))
        # Should at least count the readable file
        assert count >= 1
        assert size >= len("data")
    finally:
        os.chmod(str(f2), 0o644)


def test_get_journald_size_parses_megabytes():
    mock_result = MagicMock()
    mock_result.stdout = "Archived and active journals take up 24.5M in the file system."
    with patch("subprocess.run", return_value=mock_result):
        result = get_journald_size()
    assert result == 24.5


def test_get_journald_size_parses_gigabytes():
    mock_result = MagicMock()
    mock_result.stdout = "Archived and active journals take up 1.5G in the file system."
    with patch("subprocess.run", return_value=mock_result):
        result = get_journald_size()
    assert result == 1.5 * 1024


def test_get_journald_size_error_returns_none():
    with patch("subprocess.run", side_effect=Exception("command failed")):
        result = get_journald_size()
    assert result is None


def test_scan_configured_dirs_handles_nonexistent_gracefully():
    # Test that scan_directory can handle all config dirs without crashing
    from config import DISK_DIRS
    for dir_key, path in DISK_DIRS.items():
        size, count = scan_directory(path)
        assert isinstance(size, int)
        assert isinstance(count, int)
