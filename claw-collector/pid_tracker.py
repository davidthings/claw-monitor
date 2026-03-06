"""PID discovery and tracking via /proc."""

import os
import logging
from config import GATEWAY_CMDLINE_MATCH

log = logging.getLogger(__name__)


def read_proc_cmdline(pid):
    """Read /proc/<pid>/cmdline, return as string."""
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            return f.read().replace(b"\x00", b" ").decode("utf-8", errors="replace").strip()
    except (FileNotFoundError, PermissionError):
        return ""


def read_proc_comm(pid):
    """Read /proc/<pid>/comm."""
    try:
        with open(f"/proc/{pid}/comm") as f:
            return f.read().strip()
    except (FileNotFoundError, PermissionError):
        return ""


def read_proc_stat(pid):
    """Read /proc/<pid>/stat, return (utime, stime) in clock ticks."""
    try:
        with open(f"/proc/{pid}/stat") as f:
            parts = f.read().split()
            # Fields 14 and 15 (0-indexed 13,14) are utime and stime
            return int(parts[13]), int(parts[14])
    except (FileNotFoundError, PermissionError, IndexError, ValueError):
        return None, None


def read_proc_rss(pid):
    """Read VmRSS from /proc/<pid>/status in MB."""
    try:
        with open(f"/proc/{pid}/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024.0  # kB to MB
    except (FileNotFoundError, PermissionError, ValueError):
        pass
    return None


def get_children(pid):
    """Get child PIDs of a process."""
    try:
        with open(f"/proc/{pid}/task/{pid}/children") as f:
            return [int(p) for p in f.read().split() if p]
    except (FileNotFoundError, PermissionError, ValueError):
        return []


def get_all_descendants(pid):
    """Get all descendant PIDs recursively, with depth."""
    result = []
    queue = [(pid, 0)]
    while queue:
        p, depth = queue.pop(0)
        children = get_children(p)
        for child in children:
            result.append((child, depth + 1))
            queue.append((child, depth + 1))
    return result


def find_gateway_pid():
    """Scan /proc to find openclaw-gateway PID."""
    try:
        for entry in os.listdir("/proc"):
            if not entry.isdigit():
                continue
            pid = int(entry)
            cmdline = read_proc_cmdline(pid)
            if GATEWAY_CMDLINE_MATCH in cmdline:
                log.info("Found gateway PID %d: %s", pid, cmdline[:80])
                return pid
    except (FileNotFoundError, PermissionError):
        pass
    return None


def classify_process(pid, gateway_pid, depth):
    """Classify a process into a group based on its relationship to gateway."""
    cmdline = read_proc_cmdline(pid).lower()

    if pid == gateway_pid:
        return "openclaw-core"

    if depth == 1:
        # Direct child of gateway
        if "chrome" in cmdline or "chromium" in cmdline:
            return "openclaw-browser"
        return "openclaw-core"

    # Grandchild or deeper
    if "chrome" in cmdline or "chromium" in cmdline:
        return "openclaw-browser"
    return "openclaw-agent"


def discover_processes(gateway_pid):
    """Discover all OpenClaw processes and classify them."""
    if not gateway_pid:
        return []

    processes = [(gateway_pid, "openclaw-core", read_proc_comm(gateway_pid))]
    descendants = get_all_descendants(gateway_pid)

    for pid, depth in descendants:
        comm = read_proc_comm(pid)
        if not comm:
            continue
        grp = classify_process(pid, gateway_pid, depth)
        processes.append((pid, grp, comm))

    return processes


def verify_pid(pid, expected_comm):
    """Verify a PID still belongs to the expected process (PID reuse detection)."""
    if not os.path.exists(f"/proc/{pid}"):
        return False
    actual_comm = read_proc_comm(pid)
    return actual_comm == expected_comm
