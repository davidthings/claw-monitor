"""Network I/O tracking from /proc/net/dev."""

import logging

log = logging.getLogger(__name__)


class NetTracker:
    def __init__(self):
        self.prev_rx = None
        self.prev_tx = None

    def read_net_dev(self):
        """Read /proc/net/dev, return total (rx_bytes, tx_bytes) excluding lo."""
        total_rx = 0
        total_tx = 0
        try:
            with open("/proc/net/dev") as f:
                for line in f:
                    line = line.strip()
                    if ":" not in line or line.startswith("Inter") or line.startswith("face"):
                        continue
                    iface, data = line.split(":", 1)
                    iface = iface.strip()
                    if iface == "lo":
                        continue
                    parts = data.split()
                    total_rx += int(parts[0])
                    total_tx += int(parts[8])
        except (FileNotFoundError, PermissionError, ValueError, IndexError):
            pass
        return total_rx, total_tx

    def get_delta(self):
        """Get network delta since last call, in KB. Returns (in_kb, out_kb) or None on first call."""
        rx, tx = self.read_net_dev()

        if self.prev_rx is None:
            self.prev_rx = rx
            self.prev_tx = tx
            return None

        delta_rx = max(0, rx - self.prev_rx) / 1024.0
        delta_tx = max(0, tx - self.prev_tx) / 1024.0
        self.prev_rx = rx
        self.prev_tx = tx
        return delta_rx, delta_tx
