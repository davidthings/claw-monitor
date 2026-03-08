# claw-monitor Auto-Tagger

*Status: Phase 1 implemented. Phase 1 context enrichment planned.*
*Added: 2026-03-08*

---

## Problem

claw-monitor tagging relies on the AI agent (clawbot) remembering to call `tag.sh` at session start and when work type changes. This is unreliable — the agent frequently skips the startup tag when diving into the first message. Tags are then missing or backdated imprecisely.

The auto-tagger solves this by running independently of the agent on a fixed schedule, observing what the agent has been doing, and tagging retroactively based on tool call patterns in the session history.

---

## Design Overview

A Python script (`scripts/auto-tag.sh` / `auto_tagger.py`) runs every 10 minutes via system cron. It:

1. Locates the active OpenClaw session file on disk
2. Reads tool calls from the last ~15 minutes of session history (window intentionally overlaps cron interval)
3. Applies heuristic rules to determine the dominant work type for that window
4. Checks the current claw-monitor tag to avoid redundant tagging
5. If the work type has changed (or no tag exists), fires a new tag — backdated to when the detected activity began

No LLM is involved. It is a pure Python script reading JSON files and making HTTP calls.

---

## Data Source: OpenClaw Session Files

OpenClaw stores session history as JSONL files:

```
~/.openclaw/agents/main/sessions/sessions.json       ← index: session key → JSONL path
~/.openclaw/agents/main/sessions/<uuid>.jsonl        ← message history
```

**Finding the session file:**
```python
import json

sessions_index = json.load(open(
    "~/.openclaw/agents/main/sessions/sessions.json"
))
session = sessions_index.get("agent:main:signal:direct:+15303386428", {})
jsonl_path = session.get("sessionFile")
```

**JSONL record structure (tool calls):**
```json
{
  "type": "message",
  "timestamp": "2026-03-08T13:15:28.000Z",
  "message": {
    "role": "assistant",
    "content": [
      {
        "type": "toolCall",
        "name": "web_search",
        "input": { "query": "..." }
      }
    ]
  }
}
```

Each message can contain multiple content blocks. Tool calls have `type: "toolCall"` and a `name` field.

**Extracting tool calls from the window:**
```python
from datetime import datetime, timezone, timedelta

def get_recent_tool_calls(jsonl_path, window_minutes=15):
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
    calls = []
    with open(jsonl_path) as f:
        for line in f:
            record = json.loads(line)
            ts_str = record.get("timestamp")
            if not ts_str:
                continue
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            if ts < cutoff:
                continue
            for block in record.get("message", {}).get("content", []):
                if block.get("type") == "toolCall":
                    calls.append({
                        "name": block["name"],
                        "ts": ts,
                        "input": block.get("input", {})
                    })
    return sorted(calls, key=lambda c: c["ts"])
```

---

## Heuristic Classification Rules

Tool calls are mapped to work-type categories in priority order. The first matching rule wins.

### Tool → Category Mapping

| Tool name(s) | Category | Notes |
|---|---|---|
| `sessions_spawn` | `agent` | Spawned a subagent |
| `web_search`, `web_fetch`, `browser` | `research` | Web research |
| `exec`, `Write`, `Edit`, `Read` | `coding` | File/shell work |
| `image`, `pdf` | `research` | Document/image analysis |
| `tts`, `message` | `conversation` | Output-only tools |
| `memory_search`, `memory_get` | `conversation` | Memory recall (context for reply) |
| `cron` | `other` | Cron management |
| Any tool call | `conversation` | Fallback — something was happening |

### Priority Order

When multiple categories appear in the window, highest priority wins:

```
agent > coding > research > conversation > other > idle
```

Rationale: `agent` and `coding` are the most resource-intensive and meaningful to capture. `research` is a distinct work mode. `conversation` is the default fallback.

### Special Cases

**Mixed window (coding + research):** Priority rule applies. If both `exec` and `web_search` appear, classify as `coding` (higher priority). A future LLM upgrade could split the window more precisely.

**Qwen running:** Check `~/.openclaw/workspace/qwen-state.json`. If it exists and `started` timestamp is within the last 4 hours, prepend a `qwen` tag at the Qwen start time (if not already tagged). Qwen calls themselves appear as `exec` tool calls in the session, so they'll be classified as `coding` by the heuristic — the separate Qwen state check is needed to correctly label Qwen sessions.

**No tool calls in window, but messages exist:** `conversation` — the agent was reading and replying without using tools.

**No activity at all (no messages in window):** `idle`.

### Determining the Tag Start Time (Backdating)

The tag timestamp is set to the **earliest tool call** of the winning category in the window — but not earlier than the timestamp of the last existing claw-monitor tag. This ensures:
- Tags don't overlap or precede existing tags
- The tagged period reflects when the work actually started, not when the script ran

```python
def get_backdate_ts(calls, category, last_tag_ts):
    matching = [c for c in calls if tool_to_category(c["name"]) == category]
    if not matching:
        return datetime.now(timezone.utc)
    earliest = matching[0]["ts"]
    if last_tag_ts and earliest < last_tag_ts:
        earliest = last_tag_ts
    return earliest
```

---

## Integration: System Cron

The auto-tagger runs via **system cron** (not OpenClaw cron) — it is a deterministic script, not an agent turn. No LLM is involved.

**Install:**
```bash
crontab -e
```

**Entry (every 10 minutes):**
```
*/10 * * * * /home/david/work/claw-monitor/scripts/auto_tagger.py >> /home/david/.openclaw/logs/auto-tagger.log 2>&1
```

**Why system cron, not OpenClaw cron:**
- OpenClaw cron `agentTurn` jobs invoke the LLM — this task needs no LLM
- OpenClaw cron `systemEvent` jobs inject into the main session — we don't want to interrupt it
- System cron runs the script directly: deterministic, cheap, no token cost, always fires

---

## Script: `scripts/auto_tagger.py`

```
~/work/claw-monitor/scripts/auto_tagger.py
```

**Inputs:**
- `~/.openclaw/agents/main/sessions/sessions.json` — session index
- `<sessionFile>.jsonl` — session history (read-only, tail of file)
- `http://localhost:7432/api/tags?limit=1` — last claw-monitor tag
- `~/.openclaw/workspace/qwen-state.json` — Qwen running state (optional)
- `CM_PORT` env var (default 7432)

**Outputs:**
- `POST http://localhost:7432/api/tags` (fire-and-forget, only if tag changed)
- Log line to stdout (captured by cron to log file)

**Behaviour:**
- Reads last 15 minutes of tool calls from the active Signal session JSONL
- Classifies dominant work type via heuristics
- Gets last claw-monitor tag via API
- If category changed OR last tag was more than 20 minutes ago: fires new tag with backdated timestamp
- If category unchanged AND last tag was recent: exits silently (no duplicate tags)
- Always exits 0 — failure is silent (claw-monitor may be down; that's fine)

**Config (top of script, editable):**
```python
WINDOW_MINUTES = 15          # how far back to look for tool calls
SESSION_KEY = "agent:main:signal:direct:+15303386428"
CM_PORT = int(os.getenv("CM_PORT", "7432"))
RETAG_AFTER_MINUTES = 20     # re-tag even if same category if it's been this long
```

---

## Failure Modes

| Scenario | Behaviour |
|---|---|
| claw-monitor not running | HTTP call fails silently; script exits 0; no harm |
| Session file not found | Log warning, exit 0 |
| Session file unreadable (locked/corrupt) | Catch exception, log, exit 0 |
| No activity in window | Tags `idle` (or extends existing tag silently if already idle) |
| Ambiguous category (close call) | Priority rule picks deterministically; accuracy ≈ 80% |
| Cron not firing | System cron failure; unrelated to OpenClaw; check `crontab -l` |

---

## Phase 1 Enhancement: Context Enrichment (no LLM)

The current tag text is nearly useless: `auto-tagged: coding (tools: edit, exec, read, write)`. It tells you *what kind* of work but not *what* you were working on. This enhancement extracts richer context from tool call inputs — which are already in the JSONL — without any LLM.

### What tool inputs contain

| Tool | Input field | Value |
|------|-------------|-------|
| `Read` | `path` / `file_path` | Absolute file path |
| `Write` | `path` / `file_path` | Absolute file path |
| `Edit` | `path` / `file_path` | Absolute file path |
| `exec` | `command` | Shell command string |
| `web_search` | `query` | Search query string |
| `web_fetch` | `url` | URL |

Session header (first JSONL line) also contains `cwd` — the working directory at session start.

### New functions

**`extract_project(calls, cwd)`** → `str | None`

Maps file paths to a human-readable project name:
- `~/.openclaw/workspace/...` → `workspace`
- `~/work/<name>/...` → `<name>` (e.g. `claw-monitor`, `symtrack`, `tailscale-funname`)
- `~/work/research/...` → `research`
- No paths, has cwd → derive from cwd using same rules
- Nothing → `None`

When multiple projects appear in one window, the most frequently referenced wins.

**`extract_search_queries(calls)`** → `list[str]`

Collects query strings from `web_search` tool inputs. Truncated to 40 chars each. Up to 3 returned.

**`extract_exec_commands(calls)`** → `list[str]`

Collects meaningful exec commands — skips trivial ones (`ls`, `pwd`, `echo`, `sleep`, `cat` single-word). Truncated to 60 chars each. Up to 2 returned.

**`is_heartbeat(calls)`** → `bool`

Returns True if the tool call pattern looks like a routine heartbeat check rather than real work:
- All tool names are in: `{exec, memory_search, memory_get, web_fetch, session_status, cron}`
- No file-editing tools: no `Write`, `Edit`, `Read`
- No `web_search`
- No `sessions_spawn`
- ≤ 8 tool calls total

If `is_heartbeat` is True, the category is overridden to `heartbeat` regardless of what `classify()` returned.

**`build_tag_text(category, calls, cwd)`** → `str`

Composes the human-readable tag text from the above:

| Category | Example output |
|----------|---------------|
| `coding` | `coding \| claw-monitor \| CombinedChart.tsx, page.tsx` |
| `research` | `research \| tailscale rename API, headscale tcd source` |
| `agent` | `agent \| claw-monitor` |
| `heartbeat` | `heartbeat` |
| `conversation` | `conversation` |
| `idle` | `idle` |

Rules:
- Always include category
- Append `| <project>` if project detected
- For `coding`/`agent`: append `| <filenames>` (basenames only, up to 3, deduped)
- For `research`: append `| <queries>` instead of files
- Never include full paths (too long for the tag log)

### Tag text examples

```
coding | claw-monitor | CombinedChart.tsx, page.tsx
research | tailscale rename API, headscale tcd source code
coding | workspace | auto_tagger.py, MEMORY.md
agent | claw-monitor
heartbeat
conversation | workspace
```

### Heartbeat gating

The cron currently fires even during heartbeat cycles (a handful of `exec` + `memory_search` calls, no real work). This produces noise. With `is_heartbeat()`:
- If detected as heartbeat: tag as `heartbeat` (not `coding` or `conversation`)
- Heartbeat tags are still suppressed by the duplicate suppression logic if the last tag was also `heartbeat` within 20 minutes

---

## Future: LLM-Assisted Classification

The heuristic approach has known limitations:
- Mixed-mode sessions (coding + research) get whichever category has higher priority, not the dominant one by time
- Tool names don't capture nuance (e.g. `exec` for Qwen vs. `exec` for git operations)
- Short tool-free conversations are always `conversation` regardless of topic

**Future upgrade path:**

Phase 1 (current): pure heuristics — tool name → category, priority rules.

Phase 2 (future): heuristic pre-filter + LLM refinement when ambiguity is detected.

```
heuristic → confident? → tag and done
         ↓ ambiguous?
         → summarise recent messages (last 5 user/assistant pairs)
         → ask Qwen (if already running): "classify this work: [summary]"
         → use LLM classification only if Qwen is already running (zero added cost)
         → fall back to heuristic if Qwen not running
```

The key constraint: **never start Qwen just to classify a tag**. LLM upgrade only activates when Qwen is already running for other reasons. No added token cost, no added latency on cold paths.

Phase 3 (future): rolling window analysis — instead of a single category per window, detect transitions within the window and emit multiple backdated tags (e.g. `research` 13:10→13:20, `coding` 13:20→13:30).

---

## Test-First Development Plan

Tests are written before implementation. No code ships without a passing test. This follows the TDD mandate established in `TEST_PLAN.md §0.4`.

### Test file location

```
~/work/claw-monitor/tests/test_auto_tagger.py   ← unit tests (pytest)
```

Run with:
```bash
cd ~/work/claw-monitor
pytest tests/test_auto_tagger.py -v
```

---

### Test Group 1: JSONL Parsing

**1.1 — Extract tool calls from window**
- Given: a JSONL file with tool calls at known timestamps
- When: `get_recent_tool_calls(path, window_minutes=15)` is called
- Then: returns only tool calls within the window, in timestamp order

**1.2 — Ignore non-toolCall content blocks**
- Given: JSONL with messages containing text blocks and thinking blocks (not tool calls)
- When: parsed
- Then: only `type: "toolCall"` blocks are returned; others are ignored

**1.3 — Handle empty JSONL / no tool calls in window**
- Given: JSONL with no tool calls in the last 15 minutes
- When: parsed
- Then: returns empty list (not an error)

**1.4 — Handle missing or nonexistent session file**
- Given: sessionFile path that does not exist
- When: called
- Then: returns empty list, logs warning, exits 0

**1.5 — Handle malformed JSONL lines**
- Given: JSONL with one corrupt line among valid lines
- When: parsed
- Then: corrupt line is skipped, valid lines are processed, no exception raised

**1.6 — Timestamp parsing: UTC ISO-8601 with Z suffix**
- Given: timestamp string `"2026-03-08T13:15:28.000Z"`
- When: parsed
- Then: returns correct UTC datetime

---

### Test Group 2: Heuristic Classification

**2.1 — `sessions_spawn` → `agent`**
- Given: window contains a `sessions_spawn` tool call
- When: classified
- Then: category is `agent`

**2.2 — `exec` + `Write` → `coding`**
- Given: window contains `exec` and `Write` tool calls, no web calls
- When: classified
- Then: category is `coding`

**2.3 — `web_search` → `research`**
- Given: window contains only `web_search` calls
- When: classified
- Then: category is `research`

**2.4 — `web_fetch` → `research`**
- As above with `web_fetch`

**2.5 — `browser` → `research`**
- As above with `browser`

**2.6 — `tts` only → `conversation`**
- Given: window contains only `tts` calls
- When: classified
- Then: category is `conversation`

**2.7 — No tool calls, but messages exist → `conversation`**
- Given: window has messages but no tool calls
- When: classified
- Then: category is `conversation`

**2.8 — No activity → `idle`**
- Given: empty window (no messages, no tool calls)
- When: classified
- Then: category is `idle`

**2.9 — `cron` only → `other`**
- Given: window contains only `cron` tool calls
- When: classified
- Then: category is `other`

---

### Test Group 3: Priority Rules (Mixed Windows)

**3.1 — `agent` beats `coding`**
- Given: window contains both `sessions_spawn` and `exec` calls
- When: classified
- Then: category is `agent`

**3.2 — `coding` beats `research`**
- Given: window contains both `exec` and `web_search` calls
- When: classified
- Then: category is `coding`

**3.3 — `research` beats `conversation`**
- Given: window contains both `web_search` and `tts` calls
- When: classified
- Then: category is `research`

**3.4 — `agent` beats everything**
- Given: window contains `sessions_spawn`, `exec`, `web_search`, `tts`
- When: classified
- Then: category is `agent`

---

### Test Group 4: Backdate Logic

**4.1 — Backdate to earliest matching tool call**
- Given: three `web_search` calls at T+2m, T+5m, T+8m
- When: category is `research`, no prior tag exists
- Then: backdate timestamp is T+2m (earliest)

**4.2 — Backdate clipped to last tag timestamp**
- Given: tool calls starting at T-20m, last claw-monitor tag at T-10m
- When: backdate calculated
- Then: backdate timestamp is T-10m (not T-20m — cannot precede existing tag)

**4.3 — No prior tag: backdate to earliest call in window**
- Given: no prior claw-monitor tag exists at all
- When: backdate calculated
- Then: backdate to earliest tool call in window

**4.4 — No tool calls of winning category: backdate to now**
- Given: category is `conversation` (fallback), but no `conversation`-category tools triggered it
- When: backdate calculated
- Then: backdate to `now` (safe fallback)

---

### Test Group 5: Duplicate Suppression

**5.1 — Same category, recent tag → no new tag**
- Given: last claw-monitor tag is `research`, 5 minutes ago; current window also classifies as `research`
- When: decide whether to tag
- Then: no tag fired (suppress duplicate)

**5.2 — Same category, stale tag → re-tag**
- Given: last claw-monitor tag is `research`, 25 minutes ago (> `RETAG_AFTER_MINUTES=20`); current window also classifies as `research`
- When: decide whether to tag
- Then: new tag fired (extend the period)

**5.3 — Different category → always tag**
- Given: last claw-monitor tag is `conversation`, 2 minutes ago; current window classifies as `coding`
- When: decide whether to tag
- Then: new tag fired regardless of recency

**5.4 — No prior tag → always tag**
- Given: no prior tag exists in claw-monitor
- When: decide whether to tag
- Then: tag fired

---

### Test Group 6: API Integration (mock HTTP)

**6.1 — GET last tag: parses response correctly**
- Given: mock `/api/tags` returns `[{"category": "research", "ts": 1741200000}]`
- When: fetched
- Then: returns `("research", datetime(...))`

**6.2 — GET last tag: handles empty response (no tags yet)**
- Given: mock `/api/tags` returns `[]`
- When: fetched
- Then: returns `(None, None)` without error

**6.3 — GET last tag: handles claw-monitor down (connection refused)**
- Given: no server on CM_PORT
- When: fetched
- Then: returns `(None, None)`, logs warning, does not raise

**6.4 — POST new tag: constructs correct payload**
- Given: category `coding`, backdate ts `2026-03-08T13:20:00Z`
- When: posted
- Then: request body contains correct `category`, `ts` (ISO format), `source: "auto"`, `text` mentioning tool names seen

**6.5 — POST new tag: handles claw-monitor down gracefully**
- Given: no server on CM_PORT
- When: posted
- Then: logs warning, exits 0, no exception raised

---

### Test Group 7: Qwen State Check

**7.1 — Qwen running: detected correctly**
- Given: `qwen-state.json` exists with `started` timestamp within 4 hours
- When: checked
- Then: returns `True`

**7.2 — Qwen not running: state file absent**
- Given: `qwen-state.json` does not exist
- When: checked
- Then: returns `False` without error

**7.3 — Qwen state stale: started > 4 hours ago**
- Given: `qwen-state.json` exists but `started` is 5 hours ago
- When: checked
- Then: returns `False`

---

### Test Group 8: End-to-End (Integration)

**8.1 — Full run: active session, changed category, tag fires**
- Given: real JSONL fixture with `web_search` calls in last 15 min; claw-monitor running on test port with last tag `conversation`
- When: `auto_tagger.py` runs
- Then: new `research` tag appears in claw-monitor DB, backdated to first web_search call

**8.2 — Full run: no activity, idle tag fires**
- Given: JSONL fixture with no activity in last 15 min; last tag was `conversation` 25 min ago
- When: runs
- Then: `idle` tag fires

**8.3 — Full run: same category, recent tag, no tag fires**
- Given: JSONL fixture with `exec` calls; last tag is `coding` 5 min ago
- When: runs
- Then: no new tag in DB

**8.4 — Full run: claw-monitor down, script exits 0**
- Given: no claw-monitor running
- When: runs
- Then: exits 0, no exception, log message written

---

## Implementation Order (Test-First)

1. Write all tests in `tests/test_auto_tagger.py` (they all fail — file doesn't exist yet) ✅
2. Implement `scripts/auto_tagger.py` function by function until tests pass
3. Run full test suite: `pytest tests/test_auto_tagger.py -v`
4. Integration test against live claw-monitor on test port (Group 8)
5. Install system cron entry
6. Monitor claw-monitor dashboard to confirm tags appear correctly
7. Document in INSTRUCTIONS.md under "Automatic Tagging"

## Implementation Checklist

**Phase 0 — Core tagger**
- [x] Test file written (`tests/test_auto_tagger.py`) — Groups 1–8
- [x] All tests confirmed failing (red)
- [x] `scripts/auto_tagger.py` implemented (green)
- [x] All 42 unit tests passing
- [x] Integration tests skipped (pending CM_TEST_PORT)
- [x] System cron entry installed
- [x] First live run confirmed 08:30 PST 2026-03-08
- [x] INSTRUCTIONS.md updated

**Phase 1 — Context enrichment (no LLM)**
- [ ] Tests written for Group 9 (context enrichment) — red
- [ ] `extract_project()` implemented
- [ ] `extract_search_queries()` implemented
- [ ] `extract_exec_commands()` implemented
- [ ] `is_heartbeat()` implemented
- [ ] `build_tag_text()` implemented
- [ ] `get_session_cwd()` implemented (reads cwd from session JSONL header)
- [ ] All Group 9 tests passing
- [ ] Live run verified: tag text contains project and context info

**Phase 2 — LLM-assisted (future)**
- [ ] Qwen integration for ambiguous windows
- [ ] Rate limiting (once per 30 min max)
- [ ] Graceful fallback to Phase 1 text
