"""Sanity tests — production-critical behaviour across all handlers.

Covers gaps identified in the test audit (P0 and P1 priority):

  P0  _make_log_entry()    — log structure correctness
  P0  write_debug_log()    — debug file I/O
  P0  _write_offline()     — offline fallback file I/O
  P1  main() dispatch      — event routing + edge-case stdin
  P1  Stop filtering       — session event selection logic
"""

import importlib.util
import json
import os
import re
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Module setup
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).parent.parent
_LIB = _ROOT / "scripts" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

_spec = importlib.util.spec_from_file_location(
    "hook_handler", _ROOT / "scripts" / "hook-handler.py"
)
hh = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hh)


# ===========================================================================
# P0 — _make_log_entry() structure
# ===========================================================================

class TestMakeLogEntry:
    """Verify _make_log_entry() builds correctly-shaped audit log entries."""

    def test_adds_hook_event_name_to_event(self):
        entry = hh._make_log_entry("UserPromptSubmit", {"prompt": "hi"})
        assert entry["event"]["hook_event_name"] == "UserPromptSubmit"

    def test_preserves_all_payload_fields_in_event(self):
        payload = {"session_id": "s1", "prompt": "test", "model": "claude-sonnet-4-6"}
        entry = hh._make_log_entry("UserPromptSubmit", payload)
        assert entry["event"]["prompt"] == "test"
        assert entry["event"]["model"] == "claude-sonnet-4-6"
        assert entry["event"]["session_id"] == "s1"

    def test_extracts_session_id_to_top_level(self):
        entry = hh._make_log_entry("Stop", {"session_id": "abc-123"})
        assert entry["session_id"] == "abc-123"

    def test_missing_session_id_sets_none(self):
        entry = hh._make_log_entry("Stop", {})
        assert entry["session_id"] is None

    def test_timestamp_is_iso8601_with_trailing_z(self):
        entry = hh._make_log_entry("Stop", {})
        assert re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", entry["timestamp"])
        assert entry["timestamp"].endswith("Z")

    def test_works_for_all_event_types(self):
        for event in ("PreToolUse", "UserPromptSubmit", "PostToolUse", "Stop"):
            entry = hh._make_log_entry(event, {"session_id": "s"})
            assert entry["event"]["hook_event_name"] == event

    def test_does_not_mutate_original_payload(self):
        payload = {"session_id": "s", "prompt": "hi"}
        hh._make_log_entry("UserPromptSubmit", payload)
        assert "hook_event_name" not in payload  # original dict unchanged


# ===========================================================================
# P0 — write_debug_log() file I/O
# ===========================================================================

class TestWriteDebugLog:
    """Verify debug log is written to disk on every hook invocation."""

    def test_creates_debug_log_file(self, tmp_path):
        with patch.object(hh, "LOG_DIR", tmp_path), \
             patch.object(hh, "DEBUG_LOG", tmp_path / "debug.jsonl"):
            hh.write_debug_log("PreToolUse", {"tool_name": "Bash"})
        assert (tmp_path / "debug.jsonl").exists()

    def test_entry_contains_ts_event_and_stdin(self, tmp_path):
        debug_log = tmp_path / "debug.jsonl"
        with patch.object(hh, "LOG_DIR", tmp_path), \
             patch.object(hh, "DEBUG_LOG", debug_log):
            hh.write_debug_log("PostToolUse", {"key": "val"})
        entry = json.loads(debug_log.read_text().strip())
        assert "ts" in entry
        assert entry["event"] == "PostToolUse"
        assert entry["stdin"] == {"key": "val"}

    def test_appends_multiple_entries(self, tmp_path):
        debug_log = tmp_path / "debug.jsonl"
        with patch.object(hh, "LOG_DIR", tmp_path), \
             patch.object(hh, "DEBUG_LOG", debug_log):
            hh.write_debug_log("PreToolUse", {"n": 1})
            hh.write_debug_log("Stop", {"n": 2})
        lines = debug_log.read_text().strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0])["event"] == "PreToolUse"
        assert json.loads(lines[1])["event"] == "Stop"

    def test_creates_missing_parent_directories(self, tmp_path):
        nested = tmp_path / "a" / "b" / "c"
        with patch.object(hh, "LOG_DIR", nested), \
             patch.object(hh, "DEBUG_LOG", nested / "debug.jsonl"):
            hh.write_debug_log("Stop", {})
        assert (nested / "debug.jsonl").exists()


# ===========================================================================
# P0 — _write_offline() file I/O
# ===========================================================================

class TestWriteOffline:
    """Verify the offline fallback log is written when the API is unreachable."""

    EXCHANGE = {"conversation_id": "s1", "messages": [], "model": "auto"}

    def test_creates_offline_events_file(self, tmp_path):
        offline = tmp_path / "offline-events.jsonl"
        with patch.object(hh, "LOG_DIR", tmp_path), \
             patch.object(hh, "OFFLINE_LOG", offline):
            hh._write_offline(self.EXCHANGE)
        assert offline.exists()

    def test_entry_preserves_exchange_data(self, tmp_path):
        offline = tmp_path / "offline-events.jsonl"
        with patch.object(hh, "LOG_DIR", tmp_path), \
             patch.object(hh, "OFFLINE_LOG", offline):
            hh._write_offline(self.EXCHANGE)
        entry = json.loads(offline.read_text().strip())
        assert entry["exchange"]["conversation_id"] == "s1"

    def test_entry_has_ts_field(self, tmp_path):
        offline = tmp_path / "offline-events.jsonl"
        with patch.object(hh, "LOG_DIR", tmp_path), \
             patch.object(hh, "OFFLINE_LOG", offline):
            hh._write_offline(self.EXCHANGE)
        entry = json.loads(offline.read_text().strip())
        assert "ts" in entry

    def test_appends_multiple_exchanges(self, tmp_path):
        offline = tmp_path / "offline-events.jsonl"
        with patch.object(hh, "LOG_DIR", tmp_path), \
             patch.object(hh, "OFFLINE_LOG", offline):
            hh._write_offline({"conversation_id": "s1"})
            hh._write_offline({"conversation_id": "s2"})
        lines = offline.read_text().strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0])["exchange"]["conversation_id"] == "s1"
        assert json.loads(lines[1])["exchange"]["conversation_id"] == "s2"

    def test_creates_missing_parent_directories(self, tmp_path):
        nested = tmp_path / "x" / "y"
        with patch.object(hh, "LOG_DIR", nested), \
             patch.object(hh, "OFFLINE_LOG", nested / "offline-events.jsonl"):
            hh._write_offline(self.EXCHANGE)
        assert (nested / "offline-events.jsonl").exists()


# ===========================================================================
# P1 — main() dispatch
# ===========================================================================

class TestMainDispatch:
    """Verify main() routes events to the correct handler and handles edge cases.

    HANDLERS is a module-level dict built at import time, so we must use
    patch.dict(hh.HANDLERS, ...) rather than patch.object(hh, "handle_*")
    to ensure main()'s dict lookup sees the mock.
    """

    def _run(self, argv, stdin_data="{}"):
        with patch.object(sys, "argv", argv), \
             patch.object(sys, "stdin", StringIO(stdin_data)), \
             patch.object(hh, "write_debug_log"), \
             pytest.raises(SystemExit) as exc:
            hh.main()
        return exc.value.code

    def test_exits_with_code_0(self):
        m = MagicMock()
        with patch.dict(hh.HANDLERS, {"PreToolUse": m}):
            assert self._run(["hook-handler.py", "PreToolUse"]) == 0

    def test_routes_pretooluse(self):
        m = MagicMock()
        with patch.dict(hh.HANDLERS, {"PreToolUse": m}):
            self._run(["hook-handler.py", "PreToolUse"], '{"tool_name":"Bash"}')
        m.assert_called_once_with({"tool_name": "Bash"})

    def test_routes_userpromptsubmit(self):
        m = MagicMock()
        with patch.dict(hh.HANDLERS, {"UserPromptSubmit": m}):
            self._run(["hook-handler.py", "UserPromptSubmit"], '{"prompt":"hi"}')
        m.assert_called_once_with({"prompt": "hi"})

    def test_routes_posttooluse(self):
        m = MagicMock()
        with patch.dict(hh.HANDLERS, {"PostToolUse": m}):
            self._run(["hook-handler.py", "PostToolUse"], '{"tool_name":"Bash"}')
        m.assert_called_once_with({"tool_name": "Bash"})

    def test_routes_stop(self):
        m = MagicMock()
        with patch.dict(hh.HANDLERS, {"Stop": m}):
            self._run(["hook-handler.py", "Stop"], '{"session_id":"s"}')
        m.assert_called_once_with({"session_id": "s"})

    def test_unknown_event_calls_no_handler(self):
        # No mock injected for "UnknownEvent" — verify none of the real handlers fire
        called = []
        sentinel = MagicMock(side_effect=lambda p: called.append(p))
        with patch.dict(hh.HANDLERS, {"PreToolUse": sentinel, "Stop": sentinel}):
            self._run(["hook-handler.py", "UnknownEvent"])
        assert called == []

    def test_empty_stdin_passes_empty_dict(self):
        m = MagicMock()
        with patch.dict(hh.HANDLERS, {"Stop": m}):
            self._run(["hook-handler.py", "Stop"], "")
        m.assert_called_once_with({})

    def test_malformed_json_passes_raw_dict(self):
        m = MagicMock()
        with patch.dict(hh.HANDLERS, {"Stop": m}):
            self._run(["hook-handler.py", "Stop"], "{{bad json}}")
        assert "raw" in m.call_args[0][0]

    def test_debug_log_written_before_handler(self):
        order = []
        stop_mock = MagicMock(side_effect=lambda *a: order.append("handler"))
        with patch.object(hh, "write_debug_log", side_effect=lambda *a: order.append("log")), \
             patch.dict(hh.HANDLERS, {"Stop": stop_mock}), \
             patch.object(sys, "argv", ["hook-handler.py", "Stop"]), \
             patch.object(sys, "stdin", StringIO("{}")), \
             pytest.raises(SystemExit):
            hh.main()
        assert order == ["log", "handler"]


# ===========================================================================
# P1 — Stop session event filtering
# ===========================================================================

class TestStopSessionFiltering:
    """Verify handle_stop() correctly selects and filters session audit log entries."""

    _PAYLOAD = {"session_id": "s1", "transcript_path": "undefined"}

    def _log(self, session_id, event_name, extra=None):
        event = {"hook_event_name": event_name, "session_id": session_id}
        if extra:
            event.update(extra)
        return {"session_id": session_id, "timestamp": "2026-01-01T00:00:00Z", "event": event}

    def test_only_includes_logs_after_user_prompt_submit(self):
        logs = [
            self._log("s1", "PostToolUse"),                           # before UPS — excluded
            self._log("s1", "UserPromptSubmit", {"prompt": "hi"}),    # anchor
            self._log("s1", "PostToolUse"),                           # after UPS — included
        ]
        with patch.object(hh, "_audit_log"), \
             patch.object(hh, "_load_logs", return_value=logs), \
             patch.object(hh, "_build_exchange") as mock_build, \
             patch.object(hh, "_send_exchange", return_value=True), \
             patch.object(hh, "_save_logs"), \
             patch.object(hh, "_cleanup_logs"), \
             patch.dict(os.environ, {"UNBOUND_API_KEY": "key"}):
            hh.handle_stop(self._PAYLOAD)
        events = mock_build.call_args[0][0]
        assert len(events) == 2
        assert events[0]["event"]["hook_event_name"] == "UserPromptSubmit"
        assert events[1]["event"]["hook_event_name"] == "PostToolUse"

    def test_filters_out_other_session_logs(self):
        logs = [
            self._log("s1", "UserPromptSubmit", {"prompt": "s1_msg"}),
            self._log("s2", "UserPromptSubmit", {"prompt": "s2_msg"}),
        ]
        with patch.object(hh, "_audit_log"), \
             patch.object(hh, "_load_logs", return_value=logs), \
             patch.object(hh, "_build_exchange") as mock_build, \
             patch.object(hh, "_send_exchange", return_value=True), \
             patch.object(hh, "_save_logs"), \
             patch.object(hh, "_cleanup_logs"), \
             patch.dict(os.environ, {"UNBOUND_API_KEY": "key"}):
            hh.handle_stop(self._PAYLOAD)
        events = mock_build.call_args[0][0]
        assert all(e["session_id"] == "s1" for e in events)

    def test_no_user_prompt_submit_means_no_send(self):
        logs = [self._log("s1", "PostToolUse")]
        with patch.object(hh, "_audit_log"), \
             patch.object(hh, "_load_logs", return_value=logs), \
             patch.object(hh, "_send_exchange") as mock_send, \
             patch.object(hh, "_cleanup_logs"), \
             patch.dict(os.environ, {"UNBOUND_API_KEY": "key"}):
            hh.handle_stop(self._PAYLOAD)
        mock_send.assert_not_called()

    def test_skips_transcript_parse_when_path_is_undefined(self):
        logs = [self._log("s1", "UserPromptSubmit", {"prompt": "hi"})]
        with patch.object(hh, "_audit_log"), \
             patch.object(hh, "_load_logs", return_value=logs), \
             patch.object(hh, "_parse_transcript") as mock_parse, \
             patch.object(hh, "_build_exchange", return_value=None), \
             patch.object(hh, "_cleanup_logs"), \
             patch.dict(os.environ, {"UNBOUND_API_KEY": "key"}):
            hh.handle_stop({"session_id": "s1", "transcript_path": "undefined"})
        mock_parse.assert_not_called()

    def test_parses_transcript_when_path_is_a_real_file(self, tmp_path):
        transcript = tmp_path / "t.jsonl"
        transcript.write_text("")
        logs = [self._log("s1", "UserPromptSubmit", {"prompt": "hi"})]
        with patch.object(hh, "_audit_log"), \
             patch.object(hh, "_load_logs", return_value=logs), \
             patch.object(hh, "_parse_transcript", return_value={}) as mock_parse, \
             patch.object(hh, "_build_exchange", return_value=None), \
             patch.object(hh, "_cleanup_logs"), \
             patch.dict(os.environ, {"UNBOUND_API_KEY": "key"}):
            hh.handle_stop({"session_id": "s1", "transcript_path": str(transcript)})
        mock_parse.assert_called_once()

    def test_successful_send_removes_only_matching_session(self):
        exchange = {"conversation_id": "s1", "messages": [{"role": "user", "content": "hi"}],
                    "model": "auto", "permission_mode": "default"}
        logs = [
            self._log("s1", "UserPromptSubmit", {"prompt": "hi"}),
            self._log("other", "UserPromptSubmit", {"prompt": "yo"}),
        ]
        with patch.object(hh, "_audit_log"), \
             patch.object(hh, "_load_logs", return_value=logs), \
             patch.object(hh, "_build_exchange", return_value=exchange), \
             patch.object(hh, "_send_exchange", return_value=True), \
             patch.object(hh, "_save_logs") as mock_save, \
             patch.object(hh, "_cleanup_logs"), \
             patch.dict(os.environ, {"UNBOUND_API_KEY": "key"}):
            hh.handle_stop(self._PAYLOAD)
        remaining = mock_save.call_args[0][0]
        assert len(remaining) == 1
        assert remaining[0]["session_id"] == "other"
