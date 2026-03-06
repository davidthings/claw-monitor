"""Tests for gpu_tracker.py — Group 4 (§1.3)."""

import os
import sys
import importlib
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def _fresh_gpu_tracker():
    """Re-import gpu_tracker with fresh module state."""
    import gpu_tracker
    gpu_tracker._nvml_available = False
    gpu_tracker._handle = None
    return gpu_tracker


def test_init_gpu_success():
    mock_pynvml = MagicMock()
    mock_pynvml.nvmlDeviceGetName.return_value = "NVIDIA RTX 4090"
    gt = _fresh_gpu_tracker()

    with patch.dict("sys.modules", {"pynvml": mock_pynvml}):
        result = gt.init_gpu()

    assert result is True
    mock_pynvml.nvmlInit.assert_called_once()
    mock_pynvml.nvmlDeviceGetHandleByIndex.assert_called_once_with(0)


def test_init_gpu_no_nvidia_returns_false():
    gt = _fresh_gpu_tracker()

    mock_pynvml = MagicMock()
    mock_pynvml.nvmlInit.side_effect = Exception("NVML not found")

    with patch.dict("sys.modules", {"pynvml": mock_pynvml}):
        result = gt.init_gpu()

    assert result is False


def test_read_gpu_returns_dict():
    mock_pynvml = MagicMock()
    mock_handle = MagicMock()

    util = MagicMock()
    util.gpu = 75
    mock_pynvml.nvmlDeviceGetUtilizationRates.return_value = util

    mem = MagicMock()
    mem.used = 4 * 1024 * 1024 * 1024  # 4 GB
    mock_pynvml.nvmlDeviceGetMemoryInfo.return_value = mem

    mock_pynvml.nvmlDeviceGetPowerUsage.return_value = 250000  # 250W in mW

    gt = _fresh_gpu_tracker()
    gt._nvml_available = True
    gt._handle = mock_handle

    with patch.dict("sys.modules", {"pynvml": mock_pynvml}):
        result = gt.read_gpu()

    assert result is not None
    assert result["gpu_util_pct"] == 75.0
    assert result["gpu_vram_used_mb"] == 4096.0
    assert result["gpu_power_w"] == 250.0


def test_read_gpu_power_error_returns_none_power():
    mock_pynvml = MagicMock()
    mock_handle = MagicMock()

    util = MagicMock()
    util.gpu = 50
    mock_pynvml.nvmlDeviceGetUtilizationRates.return_value = util

    mem = MagicMock()
    mem.used = 2 * 1024 * 1024 * 1024
    mock_pynvml.nvmlDeviceGetMemoryInfo.return_value = mem

    mock_pynvml.nvmlDeviceGetPowerUsage.side_effect = Exception("power not supported")

    gt = _fresh_gpu_tracker()
    gt._nvml_available = True
    gt._handle = mock_handle

    with patch.dict("sys.modules", {"pynvml": mock_pynvml}):
        result = gt.read_gpu()

    assert result is not None
    assert result["gpu_util_pct"] == 50.0
    assert result["gpu_power_w"] is None


def test_read_gpu_when_unavailable_returns_none():
    gt = _fresh_gpu_tracker()
    gt._nvml_available = False
    gt._handle = None
    result = gt.read_gpu()
    assert result is None


def test_close_gpu_calls_shutdown():
    mock_pynvml = MagicMock()
    gt = _fresh_gpu_tracker()
    gt._nvml_available = True

    with patch.dict("sys.modules", {"pynvml": mock_pynvml}):
        gt.close_gpu()

    mock_pynvml.nvmlShutdown.assert_called_once()
    assert gt._nvml_available is False
