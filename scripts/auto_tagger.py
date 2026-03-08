#!/usr/bin/env python3
"""
auto_tagger.py — Heuristic session auto-tagger for claw-monitor.

Reads the active OpenClaw Signal session JSONL, infers work type from
tool call patterns, and fires backdated tags to claw-monitor.

No LLM involved. Pure heuristic. Runs every 10 min via system cron.

Usage:
    python3 auto_tagger.py                    # normal run
    CM_PORT=7432 python3 auto_tagger.py       # explicit port
    python3 auto_tagger.py --dry-run          # print what would be tagged, don't POST

Cron entry:
    */10 * * * * /home/david/work/claw-monitor/scripts/auto_tagger.py >> /home/david/.openclaw/logs/auto-tagger.log 2>&1
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

WINDOW_MINUTES = 15          # how far back to look for tool calls
RETAG_AFTER_MINUTES = 20     # re-tag even if same category if this old
QWEN_MAX_AGE_HOURS = 4       # consider Qwen stale after this many hours

SESSION_KEY = "agent:main:signal:direct:+15303386428"
SESSIONS_INDEX = os.path.expanduser("~/.openclaw/agents/main/sessions/sessions.json")
QWEN_STATE = os.path.expanduser("~/.openclaw/workspace/qwen-state.json")

# Tool name → category mapping (checked in priority order)
# Priority: agent > coding > research > conversation > other > idle
TOOL_CATEGORY_MAP = {
    # agent
    "sessions_spawn": "agent",
    # coding
    "exec":           "coding",
    "Write":          "coding",
    "Edit":           "coding",
    "Read":           "coding",
    # research
    "web_search":     "research",
    "web_fetch":      "research",
    "browser":        "research",
    "image":          "research",
    "pdf":            "research",
    # conversation
    "tts":            "conversation",
    "message":        "conversation",
    "memory_search":  "conversation",
    "memory_get":     "conversation",
    # other
    "cron":           "other",
}

PRIORITY = ["agent", "coding", "research", "conversation", "other", "idle"]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [auto-tagger] %(levelname)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S"
)
log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# JSONL Parsing
# ─────────────────────────────────────────────────────────────────────────────

def get_recent_tool_calls(jsonl_path: str, window_minutes: int = WINDOW_MINUTES) -> list:
    """
    Read the session JSONL and return tool calls within the window.

    Returns list of dicts: {"name": str, "ts": datetime}
    Sorted by timestamp ascending. Empty list on any error.
    """
    path = Path(jsonl_path)
    if not path.exists():
        log.warning("Session file not found: %s", jsonl_path)
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
    calls = []

    try:
        with open(path) as f:
            for raw_line in f:
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                try:
                    record = json.loads(raw_line)
                except json.JSONDecodeError:
                    log.debug("Skipping malformed line: %s", raw_line[:80])
                    continue

                ts_str = record.get("timestamp")
                if not ts_str:
                    continue

                try:
                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                except ValueError:
                    log.debug("Skipping unparseable timestamp: %s", ts_str)
                    continue

                if ts < cutoff:
                    continue

                content = record.get("message", {}).get("content", [])
                for block in content:
                    if block.get("type") == "toolCall":
                        # OpenClaw uses "arguments" field (not "input")
                        args = block.get("arguments") or block.get("input") or {}
                        calls.append({
                            "name": block.get("name", "unknown"),
                            "ts": ts,
                            "input": args,
                        })

    except OSError as e:
        log.warning("Could not read session file: %s", e)
        return []

    return sorted(calls, key=lambda c: c["ts"])


def session_has_messages(jsonl_path: str, window_minutes: int = WINDOW_MINUTES) -> bool:
    """Return True if there are any messages (user or assistant) in the window."""
    path = Path(jsonl_path)
    if not path.exists():
        return False

    cutoff = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)

    try:
        with open(path) as f:
            for raw_line in f:
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                try:
                    record = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue

                if record.get("type") != "message":
                    continue

                ts_str = record.get("timestamp")
                if not ts_str:
                    continue
                try:
                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                except ValueError:
                    continue

                if ts >= cutoff:
                    return True
    except OSError:
        pass

    return False


# ─────────────────────────────────────────────────────────────────────────────
# Heuristic Classification
# ─────────────────────────────────────────────────────────────────────────────

def tool_to_category(tool_name: str) -> str:
    """Map a single tool name to its category. Unmapped tools → 'conversation'."""
    return TOOL_CATEGORY_MAP.get(tool_name, "conversation")


def classify(calls: list, has_messages: bool = True) -> str:
    """
    Given a list of tool call dicts (with 'name' key), return the dominant category.

    Priority order: agent > coding > research > conversation > other > idle
    """
    if not calls and not has_messages:
        return "idle"

    if not calls:
        return "conversation"

    categories_present = {tool_to_category(c["name"]) for c in calls}

    for category in PRIORITY:
        if category in categories_present:
            return category

    return "conversation"


# ─────────────────────────────────────────────────────────────────────────────
# Backdate Logic
# ─────────────────────────────────────────────────────────────────────────────

def get_backdate_ts(
    calls: list,
    category: str,
    last_tag_ts: datetime | None,
) -> datetime:
    """
    Return the timestamp to use for the new tag.

    Finds the earliest call of the winning category, clipped to after last_tag_ts.
    Falls back to now if no matching calls exist.
    """
    matching = [c for c in calls if tool_to_category(c["name"]) == category]

    if not matching:
        return datetime.now(timezone.utc)

    earliest = matching[0]["ts"]  # calls are sorted ascending

    if last_tag_ts is not None and earliest < last_tag_ts:
        earliest = last_tag_ts

    return earliest


# ─────────────────────────────────────────────────────────────────────────────
# Duplicate Suppression
# ─────────────────────────────────────────────────────────────────────────────

def should_tag(
    new_category: str,
    last_category: str | None,
    last_tag_ts: datetime | None,
    retag_after_minutes: int = RETAG_AFTER_MINUTES,
) -> bool:
    """
    Return True if a new tag should be fired.

    Rules:
    - No prior tag → always tag
    - Different category → always tag
    - Same category but last tag is stale (> retag_after_minutes) → tag
    - Same category and recent → suppress
    """
    if last_category is None or last_tag_ts is None:
        return True

    if new_category != last_category:
        return True

    age = datetime.now(timezone.utc) - last_tag_ts
    return age.total_seconds() > retag_after_minutes * 60


# ─────────────────────────────────────────────────────────────────────────────
# API Integration
# ─────────────────────────────────────────────────────────────────────────────

def get_last_tag(cm_port: int = 7432) -> tuple[str | None, datetime | None]:
    """
    Fetch the most recent tag from claw-monitor.

    Returns (category, ts) or (None, None) on any error.
    """
    try:
        resp = requests.get(
            f"http://localhost:{cm_port}/api/tags",
            params={"limit": 1},
            timeout=3
        )
        data = resp.json()
        tags = data.get("tags", [])
        if not tags:
            return None, None
        tag = tags[0]
        ts = datetime.fromtimestamp(tag["ts"], tz=timezone.utc)
        return tag["category"], ts
    except Exception as e:
        log.warning("Could not fetch last tag from claw-monitor: %s", e)
        return None, None


def post_tag(
    category: str,
    backdate_ts: datetime,
    tool_names: list = None,
    cm_port: int = 7432,
    dry_run: bool = False,
    tag_text: str = None,
) -> bool:
    """
    POST a new tag to claw-monitor.

    Returns True on success, False on any error.
    """
    if tag_text is None:
        tool_summary = ", ".join(sorted(set(tool_names or []))) or "none"
        text = f"auto-tagged: {category} (tools: {tool_summary})"
    else:
        text = tag_text

    payload = {
        "category": category,
        "text": text,
        "source": "auto",
        "ts": backdate_ts.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
    }

    if dry_run:
        log.info("[DRY RUN] Would POST tag: %s", json.dumps(payload))
        return True

    try:
        resp = requests.post(
            f"http://localhost:{cm_port}/api/tags",
            json=payload,
            timeout=3
        )
        if resp.status_code in (200, 201):
            log.info("Tagged: %s (backdated to %s)", category, backdate_ts.strftime("%H:%M:%S"))
            return True
        else:
            log.warning("Tag POST returned %d: %s", resp.status_code, resp.text[:200])
            return False
    except Exception as e:
        log.warning("Could not POST tag to claw-monitor: %s", e)
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Qwen State Check
# ─────────────────────────────────────────────────────────────────────────────

def is_qwen_running(qwen_state_path: str = QWEN_STATE) -> bool:
    """
    Return True if Qwen is currently running (started within QWEN_MAX_AGE_HOURS).
    """
    path = Path(qwen_state_path)
    if not path.exists():
        return False

    try:
        state = json.loads(path.read_text())
        started = state.get("started")
        if started is None:
            return False
        started_dt = datetime.fromtimestamp(float(started), tz=timezone.utc)
        age = datetime.now(timezone.utc) - started_dt
        return age.total_seconds() < QWEN_MAX_AGE_HOURS * 3600
    except Exception as e:
        log.debug("Could not read qwen-state: %s", e)
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Phase 1: Context Enrichment
# ─────────────────────────────────────────────────────────────────────────────

HOME = str(Path.home())

HEARTBEAT_TOOLS = {"exec", "memory_search", "memory_get", "web_fetch", "session_status", "cron"}
HEARTBEAT_MAX_CALLS = 8
FILE_TOOLS = {"Read", "Write", "Edit", "read", "write", "edit"}


def _path_to_project(path: str) -> str | None:
    """Map an absolute file path to a human-readable project name."""
    path = path.replace("~", HOME)

    workspace_prefix = f"{HOME}/.openclaw/workspace"
    if path.startswith(workspace_prefix):
        return "workspace"

    openclaw_prefix = f"{HOME}/.openclaw"
    if path.startswith(openclaw_prefix):
        return "openclaw"

    work_prefix = f"{HOME}/work/"
    if path.startswith(work_prefix):
        rest = path[len(work_prefix):]
        project = rest.split("/")[0]
        return project if project else None

    return None


def _extract_paths_from_exec(command: str) -> list[str]:
    """Extract file/directory paths from a shell command string."""
    import re
    # Match: ~/work/foo, ~/.openclaw/foo, /home/david/foo
    patterns = [
        r"~\/[\w./\-]+",
        rf"{re.escape(HOME)}\/[\w./\-]+",
    ]
    results = []
    for pattern in patterns:
        results.extend(re.findall(pattern, command))
    return results


def get_session_cwd(jsonl_path: str) -> str | None:
    """Read the cwd from the session header line (first 'type: session' record)."""
    try:
        with open(jsonl_path) as f:
            for raw_line in f:
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                try:
                    record = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue
                if record.get("type") == "session":
                    return record.get("cwd")
    except OSError:
        pass
    return None


def extract_project(calls: list, cwd: str | None) -> str | None:
    """
    Infer the project being worked on from file paths in tool inputs and cwd.
    Returns the most frequently referenced project name, or None.
    """
    from collections import Counter
    counts: Counter = Counter()

    for call in calls:
        inp = call.get("input", {})

        # File-editing tools: direct path
        if call["name"] in FILE_TOOLS:
            path = inp.get("path") or inp.get("file_path") or ""
            project = _path_to_project(path)
            if project:
                counts[project] += 1

        # Exec: extract paths from command string
        if call["name"] == "exec":
            command = inp.get("command", "")
            for path in _extract_paths_from_exec(command):
                project = _path_to_project(path)
                if project:
                    counts[project] += 1

    if counts:
        return counts.most_common(1)[0][0]

    # Fall back to cwd
    if cwd:
        return _path_to_project(cwd)

    return None


def extract_search_queries(calls: list) -> list[str]:
    """Extract and truncate web_search queries from tool call inputs."""
    queries = []
    for call in calls:
        if call["name"] == "web_search":
            q = call.get("input", {}).get("query", "")
            if q:
                queries.append(q[:40])
        if len(queries) >= 3:
            break
    return queries


def extract_exec_commands(calls: list) -> list[str]:
    """Extract meaningful (non-trivial) exec commands, truncated."""
    TRIVIAL = {"ls", "pwd", "echo", "sleep", "cat", "true", "false", "cd"}
    commands = []
    for call in calls:
        if call["name"] != "exec":
            continue
        cmd = call.get("input", {}).get("command", "").strip()
        if not cmd:
            continue
        first_word = cmd.split()[0].lstrip("./~").split("/")[-1] if cmd.split() else ""
        if first_word in TRIVIAL and len(cmd.split()) == 1:
            continue
        commands.append(cmd[:60])
        if len(commands) >= 2:
            break
    return commands


def is_heartbeat(calls: list) -> bool:
    """
    Return True if the tool call pattern looks like a routine heartbeat check.

    Heartbeat: small set of exec/memory/web_fetch calls, no file editing,
    no web_search, no sessions_spawn, ≤ HEARTBEAT_MAX_CALLS total.
    """
    if not calls:
        return False
    if len(calls) > HEARTBEAT_MAX_CALLS:
        return False
    for call in calls:
        name = call["name"]
        if name not in HEARTBEAT_TOOLS:
            return False
    return True


def apply_heartbeat_override(category: str, calls: list) -> str:
    """Override category to 'heartbeat' if the call pattern matches."""
    if is_heartbeat(calls):
        return "heartbeat"
    return category


def build_tag_text(category: str, calls: list, cwd: str | None) -> str:
    """
    Compose a human-readable tag text from category, project, and context.

    Examples:
      coding | claw-monitor | CombinedChart.tsx, page.tsx
      research | tailscale rename API, headscale tcd
      heartbeat
      conversation
    """
    if category in ("heartbeat", "idle", "conversation") and not calls:
        return category

    if category == "heartbeat":
        return "heartbeat"

    parts = [category]

    project = extract_project(calls, cwd)
    if project:
        parts.append(project)

    if category == "research":
        queries = extract_search_queries(calls)
        if queries:
            parts.append(", ".join(queries))
    elif category in ("coding", "agent"):
        # Collect unique file basenames
        filenames: list[str] = []
        seen: set[str] = set()
        for call in calls:
            if call["name"] in FILE_TOOLS:
                path = call.get("input", {}).get("path") or call.get("input", {}).get("file_path") or ""
                basename = Path(path).name
                if basename and basename not in seen:
                    seen.add(basename)
                    filenames.append(basename)
            if len(filenames) >= 3:
                break
        if filenames:
            parts.append(", ".join(filenames))

    return " | ".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# Main Run Logic
# ─────────────────────────────────────────────────────────────────────────────

def find_session_jsonl(sessions_index: str = SESSIONS_INDEX, session_key: str = SESSION_KEY) -> str | None:
    """Locate the JSONL session file for the active Signal session."""
    try:
        index = json.loads(Path(sessions_index).read_text())
        session = index.get(session_key, {})
        return session.get("sessionFile")
    except Exception as e:
        log.warning("Could not read sessions index: %s", e)
        return None


def run(
    jsonl_path: str | None = None,
    cm_port: int | None = None,
    dry_run: bool = False,
    has_messages: bool | None = None,
):
    """
    Main entry point. Can be called directly (for testing) or via __main__.
    """
    if cm_port is None:
        cm_port = int(os.getenv("CM_PORT", "7432"))

    if jsonl_path is None:
        jsonl_path = find_session_jsonl()

    if not jsonl_path:
        log.warning("No session file found — nothing to tag")
        return

    # Gather data
    calls = get_recent_tool_calls(jsonl_path, window_minutes=WINDOW_MINUTES)

    if has_messages is None:
        has_messages = session_has_messages(jsonl_path, window_minutes=WINDOW_MINUTES)

    # Classify
    category = classify(calls, has_messages=has_messages)

    # Apply heartbeat override
    category = apply_heartbeat_override(category, calls)

    # Get current claw-monitor state
    last_category, last_tag_ts = get_last_tag(cm_port=cm_port)

    # Get session cwd for context enrichment
    cwd = get_session_cwd(jsonl_path) if jsonl_path else None

    log.info(
        "Window: %d tool calls | classified: %s | last tag: %s (%s)",
        len(calls),
        category,
        last_category or "none",
        last_tag_ts.strftime("%H:%M:%S") if last_tag_ts else "never"
    )

    # Decide whether to tag
    if not should_tag(category, last_category, last_tag_ts):
        log.info("Suppressed — same category (%s), tag is recent", category)
        return

    # Compute backdate timestamp
    backdate_ts = get_backdate_ts(calls, category, last_tag_ts)

    # Build enriched tag text
    tag_text = build_tag_text(category, calls, cwd)

    # Fire the tag
    post_tag(category, backdate_ts, tag_text=tag_text, cm_port=cm_port, dry_run=dry_run)


# ─────────────────────────────────────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    run(dry_run=dry_run)
