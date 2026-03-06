"""Tests for pid_tracker.py — Group 2 (§1.1)."""

import os
import sys
from unittest.mock import patch, mock_open, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pid_tracker


def test_read_proc_cmdline_returns_decoded_string(monkeypatch):
    data = b"openclaw-gateway\x00--port\x003000"
    monkeypatch.setattr("builtins.open", mock_open(read_data=data))
    result = pid_tracker.read_proc_cmdline(1234)
    assert "openclaw-gateway" in result
    assert "--port" in result


def test_read_proc_cmdline_missing_pid_returns_empty(monkeypatch):
    def raise_fnf(*args, **kwargs):
        raise FileNotFoundError()
    monkeypatch.setattr("builtins.open", raise_fnf)
    result = pid_tracker.read_proc_cmdline(99999)
    assert result == ""


def test_read_proc_comm_returns_stripped_name(monkeypatch):
    monkeypatch.setattr("builtins.open", mock_open(read_data="openclaw-gateway\n"))
    result = pid_tracker.read_proc_comm(1234)
    assert result == "openclaw-gateway"


def test_read_proc_stat_returns_utime_stime(monkeypatch):
    # /proc/<pid>/stat format: pid (comm) state ... field13=utime field14=stime
    stat_data = "1234 (test) S 1 1234 1234 0 -1 0 0 0 0 0 100 200 0 0 20 0 1 0 0 0 0 0 0 0 0 0 0 0 0 0 0"
    monkeypatch.setattr("builtins.open", mock_open(read_data=stat_data))
    utime, stime = pid_tracker.read_proc_stat(1234)
    assert utime == 100
    assert stime == 200


def test_read_proc_stat_missing_pid_returns_none_none(monkeypatch):
    def raise_fnf(*args, **kwargs):
        raise FileNotFoundError()
    monkeypatch.setattr("builtins.open", raise_fnf)
    utime, stime = pid_tracker.read_proc_stat(99999)
    assert utime is None
    assert stime is None


def test_read_proc_rss_parses_vmrss_in_mb(monkeypatch):
    status_data = "Name:\ttest\nVmPeak:\t10000 kB\nVmRSS:\t51200 kB\nVmSize:\t100000 kB\n"
    monkeypatch.setattr("builtins.open", mock_open(read_data=status_data))
    result = pid_tracker.read_proc_rss(1234)
    assert result == 51200 / 1024.0  # 50.0 MB


def test_read_proc_rss_missing_pid_returns_none(monkeypatch):
    def raise_fnf(*args, **kwargs):
        raise FileNotFoundError()
    monkeypatch.setattr("builtins.open", raise_fnf)
    result = pid_tracker.read_proc_rss(99999)
    assert result is None


def test_get_children_parses_children_file(monkeypatch):
    monkeypatch.setattr("builtins.open", mock_open(read_data="100 200 300"))
    result = pid_tracker.get_children(1)
    assert result == [100, 200, 300]


def test_get_children_no_children_returns_empty(monkeypatch):
    monkeypatch.setattr("builtins.open", mock_open(read_data=""))
    result = pid_tracker.get_children(1)
    assert result == []


def test_get_all_descendants_walks_tree(monkeypatch):
    # PID 1 -> children [10, 20], PID 10 -> children [100], PID 20 -> [], PID 100 -> []
    call_count = {"n": 0}
    children_map = {1: [10, 20], 10: [100], 20: [], 100: []}

    def mock_get_children(pid):
        return children_map.get(pid, [])

    monkeypatch.setattr(pid_tracker, "get_children", mock_get_children)
    result = pid_tracker.get_all_descendants(1)
    pids = [pid for pid, depth in result]
    assert set(pids) == {10, 20, 100}
    # Check depths
    depth_map = {pid: depth for pid, depth in result}
    assert depth_map[10] == 1
    assert depth_map[20] == 1
    assert depth_map[100] == 2


def test_find_gateway_pid_finds_matching_process(monkeypatch):
    monkeypatch.setattr("os.listdir", lambda path: ["1", "1234", "5678", "abc"])
    def mock_cmdline(pid):
        if pid == 1234:
            return "openclaw-gateway --port 3000"
        return "bash"
    monkeypatch.setattr(pid_tracker, "read_proc_cmdline", mock_cmdline)
    result = pid_tracker.find_gateway_pid()
    assert result == 1234


def test_find_gateway_pid_returns_none_when_absent(monkeypatch):
    monkeypatch.setattr("os.listdir", lambda path: ["1", "2", "3"])
    monkeypatch.setattr(pid_tracker, "read_proc_cmdline", lambda pid: "bash")
    result = pid_tracker.find_gateway_pid()
    assert result is None


def test_classify_process_gateway_is_core(monkeypatch):
    monkeypatch.setattr(pid_tracker, "read_proc_cmdline", lambda pid: "openclaw-gateway")
    result = pid_tracker.classify_process(100, 100, 0)
    assert result == "openclaw-core"


def test_classify_process_direct_child_chrome_is_browser(monkeypatch):
    monkeypatch.setattr(pid_tracker, "read_proc_cmdline", lambda pid: "/usr/bin/chrome --some-flag")
    result = pid_tracker.classify_process(200, 100, 1)
    assert result == "openclaw-browser"


def test_classify_process_direct_child_non_chrome_is_core(monkeypatch):
    monkeypatch.setattr(pid_tracker, "read_proc_cmdline", lambda pid: "node server.js")
    result = pid_tracker.classify_process(200, 100, 1)
    assert result == "openclaw-core"


def test_classify_process_grandchild_chrome_is_browser(monkeypatch):
    monkeypatch.setattr(pid_tracker, "read_proc_cmdline", lambda pid: "chromium --renderer")
    result = pid_tracker.classify_process(300, 100, 2)
    assert result == "openclaw-browser"


def test_classify_process_grandchild_non_chrome_is_agent(monkeypatch):
    monkeypatch.setattr(pid_tracker, "read_proc_cmdline", lambda pid: "python3 agent.py")
    result = pid_tracker.classify_process(300, 100, 2)
    assert result == "openclaw-agent"


def test_discover_processes_returns_gateway_and_descendants(monkeypatch):
    monkeypatch.setattr(pid_tracker, "read_proc_comm", lambda pid: {
        100: "openclaw-gw", 200: "chrome", 300: "node"
    }.get(pid, ""))
    monkeypatch.setattr(pid_tracker, "get_all_descendants", lambda pid: [(200, 1), (300, 2)])
    monkeypatch.setattr(pid_tracker, "classify_process", lambda pid, gw, depth: {
        200: "openclaw-browser", 300: "openclaw-agent"
    }.get(pid, "openclaw-core"))

    result = pid_tracker.discover_processes(100)
    assert len(result) == 3
    # First entry is the gateway
    assert result[0] == (100, "openclaw-core", "openclaw-gw")
    pids = [p[0] for p in result]
    assert 200 in pids
    assert 300 in pids


def test_discover_processes_no_gateway_returns_empty(monkeypatch):
    result = pid_tracker.discover_processes(None)
    assert result == []


def test_verify_pid_valid_process(monkeypatch):
    monkeypatch.setattr("os.path.exists", lambda path: True)
    monkeypatch.setattr(pid_tracker, "read_proc_comm", lambda pid: "test-proc")
    assert pid_tracker.verify_pid(1234, "test-proc") is True


def test_verify_pid_comm_mismatch_detects_reuse(monkeypatch):
    monkeypatch.setattr("os.path.exists", lambda path: True)
    monkeypatch.setattr(pid_tracker, "read_proc_comm", lambda pid: "different-proc")
    assert pid_tracker.verify_pid(1234, "test-proc") is False


def test_verify_pid_gone_process(monkeypatch):
    monkeypatch.setattr("os.path.exists", lambda path: False)
    assert pid_tracker.verify_pid(1234, "test-proc") is False
