"""
Auto-tagger test suite — test-first, all tests written before implementation.

Run: pytest tests/test_auto_tagger.py -v

Groups:
  1. JSONL Parsing
  2. Heuristic Classification
  3. Priority Rules (mixed windows)
  4. Backdate Logic
  5. Duplicate Suppression
  6. API Integration (mock HTTP)
  7. Qwen State Check
  8. End-to-End Integration
"""

import json
import os
import pytest
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

# --- Module under test (will fail until implemented) ---
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import auto_tagger as at


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def make_ts(minutes_ago=0):
    """Return a UTC datetime offset from now."""
    return datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)


def ts_str(dt):
    """Format datetime as OpenClaw JSONL timestamp string."""
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def make_tool_call_line(tool_name, minutes_ago=5, extra_content=None):
    """Return a JSONL line string representing an assistant message with a tool call."""
    content = [{"type": "toolCall", "name": tool_name, "input": {}}]
    if extra_content:
        content = extra_content + content
    record = {
        "type": "message",
        "id": "test-id",
        "parentId": None,
        "timestamp": ts_str(make_ts(minutes_ago)),
        "message": {
            "role": "assistant",
            "content": content
        }
    }
    return json.dumps(record)


def make_user_message_line(text="hello", minutes_ago=5):
    """Return a JSONL line for a user message (no tool calls)."""
    record = {
        "type": "message",
        "id": "test-user-id",
        "parentId": None,
        "timestamp": ts_str(make_ts(minutes_ago)),
        "message": {
            "role": "user",
            "content": [{"type": "text", "text": text}]
        }
    }
    return json.dumps(record)


def write_jsonl(tmp_path, lines):
    """Write lines to a temp JSONL file and return its path."""
    p = tmp_path / "session.jsonl"
    p.write_text("\n".join(lines) + "\n")
    return str(p)


# ─────────────────────────────────────────────────────────────────────────────
# Group 1: JSONL Parsing
# ─────────────────────────────────────────────────────────────────────────────

class TestJsonlParsing:

    def test_1_1_extract_tool_calls_in_window(self, tmp_path):
        """Tool calls within the window are returned in timestamp order."""
        lines = [
            make_tool_call_line("web_search", minutes_ago=10),
            make_tool_call_line("exec", minutes_ago=5),
        ]
        path = write_jsonl(tmp_path, lines)
        calls = at.get_recent_tool_calls(path, window_minutes=15)
        assert len(calls) == 2
        assert calls[0]["name"] == "web_search"
        assert calls[1]["name"] == "exec"

    def test_1_2_ignore_non_tool_call_content(self, tmp_path):
        """Text and thinking blocks are not returned."""
        record = {
            "type": "message",
            "timestamp": ts_str(make_ts(5)),
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "Here is my answer"},
                    {"type": "thinking", "thinking": "let me think"},
                ]
            }
        }
        path = write_jsonl(tmp_path, [json.dumps(record)])
        calls = at.get_recent_tool_calls(path, window_minutes=15)
        assert calls == []

    def test_1_3_empty_window_returns_empty_list(self, tmp_path):
        """Tool calls outside the window are excluded; empty result is not an error."""
        lines = [
            make_tool_call_line("exec", minutes_ago=20),  # outside 15-min window
        ]
        path = write_jsonl(tmp_path, lines)
        calls = at.get_recent_tool_calls(path, window_minutes=15)
        assert calls == []

    def test_1_4_missing_session_file_returns_empty(self):
        """Missing session file returns empty list without raising."""
        calls = at.get_recent_tool_calls("/nonexistent/path/session.jsonl", window_minutes=15)
        assert calls == []

    def test_1_5_malformed_lines_skipped(self, tmp_path):
        """Corrupt lines are skipped; valid lines are still processed."""
        lines = [
            "NOT VALID JSON {{{",
            make_tool_call_line("web_search", minutes_ago=5),
            "ALSO BAD",
        ]
        path = write_jsonl(tmp_path, lines)
        calls = at.get_recent_tool_calls(path, window_minutes=15)
        assert len(calls) == 1
        assert calls[0]["name"] == "web_search"

    def test_1_6_timestamp_parsing_utc_z_suffix(self, tmp_path):
        """ISO-8601 timestamp with Z suffix parses correctly to UTC datetime."""
        lines = [make_tool_call_line("exec", minutes_ago=3)]
        path = write_jsonl(tmp_path, lines)
        calls = at.get_recent_tool_calls(path, window_minutes=15)
        assert len(calls) == 1
        ts = calls[0]["ts"]
        assert ts.tzinfo is not None
        assert ts.tzinfo == timezone.utc or ts.utcoffset().total_seconds() == 0


# ─────────────────────────────────────────────────────────────────────────────
# Group 2: Heuristic Classification
# ─────────────────────────────────────────────────────────────────────────────

class TestHeuristicClassification:

    def _classify(self, tool_names, has_messages=True):
        calls = [{"name": n, "ts": make_ts(5)} for n in tool_names]
        return at.classify(calls, has_messages=has_messages)

    def test_2_1_sessions_spawn_is_agent(self):
        assert self._classify(["sessions_spawn"]) == "agent"

    def test_2_2_exec_and_write_is_coding(self):
        assert self._classify(["exec", "Write"]) == "coding"

    def test_2_3_web_search_is_research(self):
        assert self._classify(["web_search"]) == "research"

    def test_2_4_web_fetch_is_research(self):
        assert self._classify(["web_fetch"]) == "research"

    def test_2_5_browser_is_research(self):
        assert self._classify(["browser"]) == "research"

    def test_2_6_tts_only_is_conversation(self):
        assert self._classify(["tts"]) == "conversation"

    def test_2_7_no_tool_calls_but_messages_is_conversation(self):
        assert self._classify([], has_messages=True) == "conversation"

    def test_2_8_no_activity_at_all_is_idle(self):
        assert self._classify([], has_messages=False) == "idle"

    def test_2_9_cron_only_is_other(self):
        assert self._classify(["cron"]) == "other"

    def test_2_10_read_only_is_coding(self):
        assert self._classify(["Read"]) == "coding"

    def test_2_11_edit_only_is_coding(self):
        assert self._classify(["Edit"]) == "coding"

    def test_2_12_memory_search_is_conversation(self):
        assert self._classify(["memory_search"]) == "conversation"

    def test_2_13_image_is_research(self):
        assert self._classify(["image"]) == "research"

    def test_2_14_pdf_is_research(self):
        assert self._classify(["pdf"]) == "research"


# ─────────────────────────────────────────────────────────────────────────────
# Group 3: Priority Rules (mixed windows)
# ─────────────────────────────────────────────────────────────────────────────

class TestPriorityRules:

    def _classify(self, tool_names):
        calls = [{"name": n, "ts": make_ts(5)} for n in tool_names]
        return at.classify(calls, has_messages=True)

    def test_3_1_agent_beats_coding(self):
        assert self._classify(["sessions_spawn", "exec"]) == "agent"

    def test_3_2_coding_beats_research(self):
        assert self._classify(["exec", "web_search"]) == "coding"

    def test_3_3_research_beats_conversation(self):
        assert self._classify(["web_search", "tts"]) == "research"

    def test_3_4_agent_beats_everything(self):
        assert self._classify(["sessions_spawn", "exec", "web_search", "tts"]) == "agent"

    def test_3_5_coding_beats_other(self):
        assert self._classify(["exec", "cron"]) == "coding"

    def test_3_6_research_beats_other(self):
        assert self._classify(["web_search", "cron"]) == "research"


# ─────────────────────────────────────────────────────────────────────────────
# Group 4: Backdate Logic
# ─────────────────────────────────────────────────────────────────────────────

class TestBackdateLogic:

    def test_4_1_backdate_to_earliest_matching_call(self):
        """Backdate to the earliest tool call of the winning category."""
        t1 = make_ts(10)
        t2 = make_ts(5)
        t3 = make_ts(2)
        calls = [
            {"name": "web_search", "ts": t1},
            {"name": "web_search", "ts": t2},
            {"name": "web_search", "ts": t3},
        ]
        ts = at.get_backdate_ts(calls, "research", last_tag_ts=None)
        assert ts == t1

    def test_4_2_backdate_clipped_to_last_tag(self):
        """Backdate cannot precede the last existing tag timestamp."""
        last_tag_ts = make_ts(10)
        calls = [
            {"name": "web_search", "ts": make_ts(20)},  # before last tag
            {"name": "web_search", "ts": make_ts(5)},   # after last tag
        ]
        ts = at.get_backdate_ts(calls, "research", last_tag_ts=last_tag_ts)
        assert ts >= last_tag_ts

    def test_4_3_no_prior_tag_backdate_to_earliest(self):
        """With no prior tag, backdate to the earliest call in window."""
        t_early = make_ts(12)
        calls = [
            {"name": "exec", "ts": t_early},
            {"name": "exec", "ts": make_ts(3)},
        ]
        ts = at.get_backdate_ts(calls, "coding", last_tag_ts=None)
        assert ts == t_early

    def test_4_4_no_matching_calls_backdate_to_now(self):
        """If no calls of the winning category, backdate to approximately now.
        Scenario: classify returned 'conversation' via has_messages fallback,
        no tool calls present at all."""
        calls = []  # empty — conversation won via has_messages, not tool calls
        before = datetime.now(timezone.utc)
        ts = at.get_backdate_ts(calls, "conversation", last_tag_ts=None)
        after = datetime.now(timezone.utc)
        assert before <= ts <= after


# ─────────────────────────────────────────────────────────────────────────────
# Group 5: Duplicate Suppression
# ─────────────────────────────────────────────────────────────────────────────

class TestDuplicateSuppression:

    def test_5_1_same_category_recent_tag_suppressed(self):
        """No tag fired if same category and last tag is recent."""
        last_tag_ts = make_ts(5)  # 5 min ago — within RETAG_AFTER_MINUTES
        should_tag = at.should_tag("research", "research", last_tag_ts, retag_after_minutes=20)
        assert should_tag is False

    def test_5_2_same_category_stale_tag_fires(self):
        """Tag fires if same category but last tag is older than retag threshold."""
        last_tag_ts = make_ts(25)  # 25 min ago — beyond RETAG_AFTER_MINUTES=20
        should_tag = at.should_tag("research", "research", last_tag_ts, retag_after_minutes=20)
        assert should_tag is True

    def test_5_3_different_category_always_fires(self):
        """Tag fires when category changes, regardless of recency."""
        last_tag_ts = make_ts(2)  # very recent
        should_tag = at.should_tag("coding", "conversation", last_tag_ts, retag_after_minutes=20)
        assert should_tag is True

    def test_5_4_no_prior_tag_always_fires(self):
        """Tag fires when there is no prior tag at all."""
        should_tag = at.should_tag("conversation", None, None, retag_after_minutes=20)
        assert should_tag is True


# ─────────────────────────────────────────────────────────────────────────────
# Group 6: API Integration (mock HTTP)
# ─────────────────────────────────────────────────────────────────────────────

class TestApiIntegration:

    def test_6_1_get_last_tag_parses_response(self):
        """Correctly parses category and ts from /api/tags response."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "tags": [{"category": "research", "ts": 1741200000, "text": "test"}]
        }
        with patch("auto_tagger.requests.get", return_value=mock_response):
            category, ts = at.get_last_tag(cm_port=7432)
        assert category == "research"
        assert isinstance(ts, datetime)

    def test_6_2_get_last_tag_empty_response(self):
        """Empty tags list returns (None, None) without error."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"tags": []}
        with patch("auto_tagger.requests.get", return_value=mock_response):
            category, ts = at.get_last_tag(cm_port=7432)
        assert category is None
        assert ts is None

    def test_6_3_get_last_tag_connection_refused(self):
        """Connection refused returns (None, None) without raising."""
        import requests as req
        with patch("auto_tagger.requests.get", side_effect=req.exceptions.ConnectionError):
            category, ts = at.get_last_tag(cm_port=7432)
        assert category is None
        assert ts is None

    def test_6_4_post_tag_correct_payload(self):
        """POST constructs correct payload with category, ts, source=auto."""
        mock_response = MagicMock()
        mock_response.status_code = 201
        backdate_ts = datetime(2026, 3, 8, 13, 20, 0, tzinfo=timezone.utc)

        with patch("auto_tagger.requests.post", return_value=mock_response) as mock_post:
            at.post_tag("coding", backdate_ts, tool_names=["exec", "Write"], cm_port=7432)

        assert mock_post.called
        payload = mock_post.call_args[1]["json"]
        assert payload["category"] == "coding"
        assert payload["source"] == "auto"
        assert "ts" in payload
        # ts should be ISO format string or unix timestamp
        assert payload["ts"] is not None

    def test_6_5_post_tag_connection_refused_exits_gracefully(self):
        """POST failure (connection refused) exits gracefully without raising."""
        import requests as req
        backdate_ts = datetime.now(timezone.utc)
        with patch("auto_tagger.requests.post", side_effect=req.exceptions.ConnectionError):
            # Should not raise
            at.post_tag("coding", backdate_ts, tool_names=["exec"], cm_port=7432)


# ─────────────────────────────────────────────────────────────────────────────
# Group 7: Qwen State Check
# ─────────────────────────────────────────────────────────────────────────────

class TestQwenStateCheck:

    def test_7_1_qwen_running_detected(self, tmp_path):
        """qwen-state.json with recent started timestamp → True."""
        state = {"started": make_ts(1).timestamp(), "model": "35b"}
        p = tmp_path / "qwen-state.json"
        p.write_text(json.dumps(state))
        assert at.is_qwen_running(str(p)) is True

    def test_7_2_qwen_state_absent(self, tmp_path):
        """Missing qwen-state.json → False without error."""
        assert at.is_qwen_running(str(tmp_path / "qwen-state.json")) is False

    def test_7_3_qwen_state_stale(self, tmp_path):
        """qwen-state.json with started > 4 hours ago → False."""
        state = {"started": make_ts(300).timestamp()}  # 300 min = 5 hours
        p = tmp_path / "qwen-state.json"
        p.write_text(json.dumps(state))
        assert at.is_qwen_running(str(p)) is False


# ─────────────────────────────────────────────────────────────────────────────
# Group 8: End-to-End Integration
# ─────────────────────────────────────────────────────────────────────────────

class TestEndToEnd:
    """
    These tests require a running claw-monitor instance on a test port.
    They use real HTTP calls and real DB operations.

    Skip if CM_TEST_PORT env var not set.
    """

    @pytest.fixture(autouse=True)
    def skip_without_test_port(self):
        if not os.getenv("CM_TEST_PORT"):
            pytest.skip("CM_TEST_PORT not set — skipping integration tests")

    @property
    def port(self):
        return int(os.environ["CM_TEST_PORT"])

    def test_8_1_active_session_changed_category_tag_fires(self, tmp_path):
        """Full run: web_search calls in window, last tag=conversation → research tag fires."""
        lines = [
            make_tool_call_line("web_search", minutes_ago=8),
            make_tool_call_line("web_search", minutes_ago=4),
        ]
        jsonl_path = write_jsonl(tmp_path, lines)

        # Post a prior conversation tag
        import requests
        requests.post(f"http://localhost:{self.port}/api/tags", json={
            "category": "conversation", "text": "prior", "source": "test"
        })

        at.run(jsonl_path=jsonl_path, cm_port=self.port)

        resp = requests.get(f"http://localhost:{self.port}/api/tags?limit=1")
        latest = resp.json()["tags"][0]
        assert latest["category"] == "research"
        assert latest["source"] == "auto"

    def test_8_2_no_activity_idle_tag_fires(self, tmp_path):
        """Full run: no tool calls, last tag was >20 min ago → idle fires."""
        # Empty session — just a session header line
        header = json.dumps({"type": "session", "timestamp": ts_str(make_ts(60))})
        jsonl_path = write_jsonl(tmp_path, [header])

        import requests
        # Seed a stale tag
        stale_ts = make_ts(25)
        requests.post(f"http://localhost:{self.port}/api/tags", json={
            "category": "conversation", "text": "stale", "source": "test",
            "ts": stale_ts.isoformat()
        })

        at.run(jsonl_path=jsonl_path, cm_port=self.port, has_messages=False)

        resp = requests.get(f"http://localhost:{self.port}/api/tags?limit=1")
        latest = resp.json()["tags"][0]
        assert latest["category"] == "idle"

    def test_8_3_same_category_recent_no_tag_fires(self, tmp_path):
        """Full run: exec calls, last tag=coding 5min ago → no new tag."""
        lines = [make_tool_call_line("exec", minutes_ago=3)]
        jsonl_path = write_jsonl(tmp_path, lines)

        import requests
        requests.post(f"http://localhost:{self.port}/api/tags", json={
            "category": "coding", "text": "recent", "source": "test"
        })

        resp_before = requests.get(f"http://localhost:{self.port}/api/tags?limit=1")
        tag_id_before = resp_before.json()["tags"][0]["id"]

        at.run(jsonl_path=jsonl_path, cm_port=self.port)

        resp_after = requests.get(f"http://localhost:{self.port}/api/tags?limit=1")
        tag_id_after = resp_after.json()["tags"][0]["id"]
        assert tag_id_before == tag_id_after  # no new tag

    def test_8_4_claw_monitor_down_exits_zero(self, tmp_path):
        """Full run with claw-monitor on wrong port exits 0 — no crash."""
        lines = [make_tool_call_line("exec", minutes_ago=3)]
        jsonl_path = write_jsonl(tmp_path, lines)
        # Use a port nothing is listening on
        at.run(jsonl_path=jsonl_path, cm_port=19999)
        # If we get here without exception, test passes
