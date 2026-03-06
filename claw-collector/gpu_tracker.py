"""GPU monitoring via pynvml."""

import logging

log = logging.getLogger(__name__)

_nvml_available = False
_handle = None


def init_gpu():
    """Initialize NVML. Returns True if GPU available."""
    global _nvml_available, _handle
    try:
        import pynvml
        pynvml.nvmlInit()
        _handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        name = pynvml.nvmlDeviceGetName(_handle)
        if isinstance(name, bytes):
            name = name.decode()
        log.info("GPU initialized: %s", name)
        _nvml_available = True
        return True
    except Exception as e:
        log.warning("GPU not available: %s", e)
        _nvml_available = False
        return False


def read_gpu():
    """Read GPU metrics. Returns dict or None if unavailable."""
    if not _nvml_available or _handle is None:
        return None
    try:
        import pynvml
        util = pynvml.nvmlDeviceGetUtilizationRates(_handle)
        mem = pynvml.nvmlDeviceGetMemoryInfo(_handle)
        try:
            power = pynvml.nvmlDeviceGetPowerUsage(_handle) / 1000.0  # mW to W
        except Exception:
            power = None
        return {
            "gpu_util_pct": float(util.gpu),
            "gpu_vram_used_mb": round(mem.used / (1024 * 1024), 1),
            "gpu_power_w": round(power, 1) if power else None,
        }
    except Exception as e:
        log.debug("GPU read error: %s", e)
        return None


def close_gpu():
    """Shutdown NVML."""
    global _nvml_available
    if _nvml_available:
        try:
            import pynvml
            pynvml.nvmlShutdown()
        except Exception:
            pass
        _nvml_available = False
