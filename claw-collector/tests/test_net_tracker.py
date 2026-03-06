"""Tests for net_tracker.py — Group 3 (§1.2)."""

import os
import sys
from unittest.mock import mock_open

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from net_tracker import NetTracker

NET_DEV_HEADER = """\
Inter-|   Receive                                                |  Transmit
 face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets errs drop fifo colls carrier compressed
"""

NET_DEV_WITH_LO = NET_DEV_HEADER + """\
    lo: 1000       10    0    0    0     0          0         0     2000       20    0    0    0     0       0          0
  eth0: 5000       50    0    0    0     0          0         0     3000       30    0    0    0     0       0          0
"""


def test_get_delta_first_call_returns_none(monkeypatch):
    tracker = NetTracker()
    monkeypatch.setattr("builtins.open", mock_open(read_data=NET_DEV_WITH_LO))
    result = tracker.get_delta()
    assert result is None


def test_get_delta_second_call_returns_kb_diff(monkeypatch):
    tracker = NetTracker()

    # First call: baseline
    monkeypatch.setattr("builtins.open", mock_open(read_data=NET_DEV_WITH_LO))
    tracker.get_delta()

    # Second call: increased by 1024 bytes each
    updated = NET_DEV_HEADER + """\
    lo: 1000       10    0    0    0     0          0         0     2000       20    0    0    0     0       0          0
  eth0: 6024       51    0    0    0     0          0         0     4024       31    0    0    0     0       0          0
"""
    monkeypatch.setattr("builtins.open", mock_open(read_data=updated))
    result = tracker.get_delta()
    assert result is not None
    in_kb, out_kb = result
    assert abs(in_kb - 1.0) < 0.01  # 1024 bytes = 1 KB
    assert abs(out_kb - 1.0) < 0.01


def test_get_delta_counter_wrap_clamps_to_zero(monkeypatch):
    tracker = NetTracker()

    # First call with high values
    high = NET_DEV_HEADER + """\
  eth0: 100000       50    0    0    0     0          0         0     100000       30    0    0    0     0       0          0
"""
    monkeypatch.setattr("builtins.open", mock_open(read_data=high))
    tracker.get_delta()

    # Second call with lower values (counter wrap)
    low = NET_DEV_HEADER + """\
  eth0: 500       50    0    0    0     0          0         0     500       30    0    0    0     0       0          0
"""
    monkeypatch.setattr("builtins.open", mock_open(read_data=low))
    result = tracker.get_delta()
    assert result is not None
    in_kb, out_kb = result
    assert in_kb == 0.0
    assert out_kb == 0.0


def test_read_net_dev_excludes_loopback(monkeypatch):
    tracker = NetTracker()
    monkeypatch.setattr("builtins.open", mock_open(read_data=NET_DEV_WITH_LO))
    rx, tx = tracker.read_net_dev()
    # Should only include eth0 (5000 rx, 3000 tx), not lo
    assert rx == 5000
    assert tx == 3000


def test_read_net_dev_parses_multiple_interfaces(monkeypatch):
    tracker = NetTracker()
    data = NET_DEV_HEADER + """\
  eth0: 5000       50    0    0    0     0          0         0     3000       30    0    0    0     0       0          0
 wlan0: 2000       20    0    0    0     0          0         0     1000       10    0    0    0     0       0          0
"""
    monkeypatch.setattr("builtins.open", mock_open(read_data=data))
    rx, tx = tracker.read_net_dev()
    assert rx == 7000  # 5000 + 2000
    assert tx == 4000  # 3000 + 1000


def test_read_net_dev_skips_header_lines(monkeypatch):
    tracker = NetTracker()
    # Just headers, no interfaces
    monkeypatch.setattr("builtins.open", mock_open(read_data=NET_DEV_HEADER))
    rx, tx = tracker.read_net_dev()
    assert rx == 0
    assert tx == 0


def test_read_net_dev_missing_file_returns_zeros(monkeypatch):
    tracker = NetTracker()
    def raise_fnf(*args, **kwargs):
        raise FileNotFoundError()
    monkeypatch.setattr("builtins.open", raise_fnf)
    rx, tx = tracker.read_net_dev()
    assert rx == 0
    assert tx == 0
