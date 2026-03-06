"""Disk usage tracking via os.walk()."""

import os
import subprocess
import logging

log = logging.getLogger(__name__)


def scan_directory(path):
    """Scan a directory, return (total_bytes, file_count)."""
    total_bytes = 0
    file_count = 0
    path = os.path.expanduser(path)

    if not os.path.isdir(path):
        return 0, 0

    try:
        for dirpath, dirnames, filenames in os.walk(path):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                try:
                    total_bytes += os.path.getsize(fp)
                    file_count += 1
                except (OSError, FileNotFoundError):
                    pass
    except (OSError, PermissionError) as e:
        log.debug("Error scanning %s: %s", path, e)

    return total_bytes, file_count


def get_journald_size():
    """Get journald disk usage in MB for openclaw services."""
    try:
        result = subprocess.run(
            ["journalctl", "--user", "--disk-usage"],
            capture_output=True, text=True, timeout=10,
        )
        # Output like: "Archived and active journals take up 24.5M in the file system."
        for word in result.stdout.split():
            if word.endswith("M"):
                try:
                    return float(word[:-1])
                except ValueError:
                    pass
            elif word.endswith("G"):
                try:
                    return float(word[:-1]) * 1024
                except ValueError:
                    pass
    except Exception as e:
        log.debug("journalctl error: %s", e)
    return None
