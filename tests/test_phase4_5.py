"""Unit tests for Phase 4 (UserPromptSubmit) and Phase 5 (PostToolUse + Stop).

Covers:
  Phase 4 — Task 4.4/4.5/4.6
    - stdin → API payload transformation for UserPromptSubmit
    - API response → Claude Code stdout (block or empty)
    - Error paths (timeout, 500, missing env, malformed stdin)

  Phase 5 — Task 5.5/5.6/5.7
    - PostToolUse appends to audit log
    - Stop builds exchange and sends to API
    - Offline fallback when API is unreachable
"""

import importlib.util
import json
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

# ---------------------------------------------------------------------------
# Path setup — import lib functions and hook-handler module
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).parent.parent
_LIB = _ROOT / "scripts" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from unbound import transform_response_for_claude_prompt

# Load hook-handler.py via importlib (filename has a hyphen)
_spec = importlib.util.spec_from_file_location(
    "hook_handler", _ROOT / "scripts" / "hook-handler.py"
)
hh = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hh)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _api_ok(decision: str, reason: str = "") -> MagicMock:
    body = json.dumps({"decision": decision, "reason": reason}).encode()
    return MagicMock(returncode=0, stdout=body)


def _api_fail() -> MagicMock:
    return MagicMock(returncode=1, stdout=b"", stderr=b"500 error")


# ===========================================================================
# Phase 4 — UserPromptSubmit
# ===========================================================================

class TestUserPromptTransformation:
    """Task 4.4 — stdin → API payload transformation."""

    @patch("subprocess.run")
    def test_prompt_sent_as_user_message(self, mock_run):
        mock_run.return_value = _api_ok("allow")
        with patch.object(hh, "_audit_log"):
            with patch.dict("os.environ", {"UNBOUND_CLAUDE_API_KEY": "key"}):
                hh.handle_user_prompt_submit(
                    {"session_id": "s1", "prompt": "hello world"}
                )
        payload = json.loads(mock_run.call_args[1]["input"].decode())
        assert payload["event_name"] == "user_prompt"
        assert payload["messages"][0] == {"role": "user", "content": "hello world"}

    @patch("subprocess.run")
    def test_session_id_as_conversation_id(self, mock_run):
        mock_run.return_value = _api_ok("allow")
        with patch.object(hh, "_audit_log"):
            with patch.dict("os.environ", {"UNBOUND_CLAUDE_API_KEY": "key"}):
                hh.handle_user_prompt_submit(
                    {"session_id": "my-session", "prompt": "test"}
                )
        payload = json.loads(mock_run.call_args[1]["input"].decode())
        assert payload["conversation_id"] == "my-session"
        assert payload["unbound_app_label"] == "claude-code"


class TestUserPromptResponse:
    """Task 4.5 — API response → Claude Code stdout."""

    @patch("subprocess.run")
    def test_deny_outputs_block_decision(self, mock_run, capsys):
        mock_run.return_value = _api_ok("deny", "PII detected")
        with patch.dict("os.environ", {"UNBOUND_CLAUDE_API_KEY": "key"}):
            hh.handle_user_prompt_submit({"session_id": "s", "prompt": "my SSN is 123"})
        out = json.loads(capsys.readouterr().out)
        assert out["decision"] == "block"
        assert out["reason"] == "PII detected"
        assert out["suppressOutput"] is True

    @patch("subprocess.run")
    def test_allow_produces_no_output(self, mock_run, capsys):
        mock_run.return_value = _api_ok("allow")
        with patch.object(hh, "_audit_log"):
            with patch.dict("os.environ", {"UNBOUND_CLAUDE_API_KEY": "key"}):
                hh.handle_user_prompt_submit({"session_id": "s", "prompt": "clean prompt"})
        assert capsys.readouterr().out == ""

    @patch("subprocess.run")
    def test_blocked_prompt_is_not_logged(self, mock_run):
        mock_run.return_value = _api_ok("deny", "blocked")
        with patch.object(hh, "_audit_log") as mock_log:
            with patch.dict("os.environ", {"UNBOUND_CLAUDE_API_KEY": "key"}):
                hh.handle_user_prompt_submit({"session_id": "s", "prompt": "bad prompt"})
        mock_log.assert_not_called()

    @patch("subprocess.run")
    def test_allowed_prompt_is_logged(self, mock_run):
        mock_run.return_value = _api_ok("allow")
        with patch.object(hh, "_audit_log") as mock_log:
            with patch.dict("os.environ", {"UNBOUND_CLAUDE_API_KEY": "key"}):
                hh.handle_user_prompt_submit({"session_id": "s", "prompt": "good prompt"})
        mock_log.assert_called_once()
        log_entry = mock_log.call_args[0][0]
        assert log_entry["event"]["hook_event_name"] == "UserPromptSubmit"
        assert log_entry["event"]["prompt"] == "good prompt"


class TestUserPromptErrorPaths:
    """Task 4.6 — error paths all fail open."""

    def test_no_api_key_logs_and_produces_no_output(self, capsys):
        with patch.object(hh, "_audit_log") as mock_log:
            with patch.dict("os.environ", {}, clear=True):
                # Ensure key is absent
                os.environ.pop("UNBOUND_CLAUDE_API_KEY", None)
                hh.handle_user_prompt_submit({"session_id": "s", "prompt": "hi"})
        assert capsys.readouterr().out == ""
        mock_log.assert_called_once()  # still logs the prompt

    @patch("subprocess.run")
    def test_api_500_allows_and_logs(self, mock_run, capsys):
        mock_run.return_value = _api_fail()
        with patch.object(hh, "_audit_log") as mock_log:
            with patch.dict("os.environ", {"UNBOUND_CLAUDE_API_KEY": "key"}):
                hh.handle_user_prompt_submit({"session_id": "s", "prompt": "hi"})
        assert capsys.readouterr().out == ""
        mock_log.assert_called_once()

    @patch("subprocess.run", side_effect=Exception("timeout"))
    def test_timeout_allows_and_logs(self, mock_run, capsys):
        with patch.object(hh, "_audit_log") as mock_log:
            with patch.dict("os.environ", {"UNBOUND_CLAUDE_API_KEY": "key"}):
                hh.handle_user_prompt_submit({"session_id": "s", "prompt": "hi"})
        assert capsys.readouterr().out == ""
        mock_log.assert_called_once()

    @patch("subprocess.run")
    def test_malformed_api_json_allows_and_logs(self, mock_run, capsys):
        mock_run.return_value = MagicMock(returncode=0, stdout=b"{{not json}}")
        with patch.object(hh, "_audit_log") as mock_log:
            with patch.dict("os.environ", {"UNBOUND_CLAUDE_API_KEY": "key"}):
                hh.handle_user_prompt_submit({"session_id": "s", "prompt": "hi"})
        assert capsys.readouterr().out == ""
        mock_log.assert_called_once()


# Also test the lib transformer directly
class TestTransformResponseForClaudePrompt:

    def test_deny_maps_to_block(self):
        result = transform_response_for_claude_prompt({"decision": "deny", "reason": "PII"})
        assert result == {"decision": "block", "reason": "PII"}

    def test_allow_returns_empty(self):
        result = transform_response_for_claude_prompt({"decision": "allow", "reason": ""})
        assert result == {}

    def test_empty_response_returns_empty(self):
        assert transform_response_for_claude_prompt({}) == {}


# ===========================================================================
# Phase 5 — PostToolUse
# ===========================================================================

class TestPostToolUse:
    """Tasks 5.5 — PostToolUse appends to audit log, produces no output."""

    def test_appends_to_audit_log(self):
        payload = {
            "session_id": "s1",
            "tool_name": "Bash",
            "tool_input": {"command": "ls"},
            "tool_response": {"stdout": "file.txt"},
        }
        with patch.object(hh, "_audit_log") as mock_log:
            hh.handle_post_tool_use(payload)
        mock_log.assert_called_once()
        entry = mock_log.call_args[0][0]
        assert entry["session_id"] == "s1"
        assert entry["event"]["hook_event_name"] == "PostToolUse"
        assert entry["event"]["tool_name"] == "Bash"

    def test_produces_no_output(self, capsys):
        with patch.object(hh, "_audit_log"):
            hh.handle_post_tool_use({"session_id": "s", "tool_name": "Bash"})
        assert capsys.readouterr().out == ""


# ===========================================================================
# Phase 5 — Stop
# ===========================================================================

class TestStop:
    """Tasks 5.6/5.7 — Stop sends exchange to API; offline fallback on failure."""

    _PAYLOAD = {"session_id": "sess-xyz", "transcript_path": "undefined"}

    def test_stop_logs_event_to_audit_log(self):
        with patch.object(hh, "_audit_log") as mock_log, \
             patch.object(hh, "_load_logs", return_value=[]), \
             patch.dict("os.environ", {}, clear=True):
            os.environ.pop("UNBOUND_CLAUDE_API_KEY", None)
            hh.handle_stop(self._PAYLOAD)
        mock_log.assert_called_once()
        entry = mock_log.call_args[0][0]
        assert entry["event"]["hook_event_name"] == "Stop"

    def test_no_api_key_skips_exchange(self):
        with patch.object(hh, "_audit_log"), \
             patch.object(hh, "_send_exchange") as mock_send, \
             patch.dict("os.environ", {}, clear=True):
            os.environ.pop("UNBOUND_CLAUDE_API_KEY", None)
            hh.handle_stop(self._PAYLOAD)
        mock_send.assert_not_called()

    def test_successful_send_cleans_up_session_logs(self):
        session_log = {
            "session_id": "sess-xyz",
            "timestamp": "2026-01-01T00:00:00Z",
            "event": {"hook_event_name": "UserPromptSubmit", "session_id": "sess-xyz", "prompt": "hi"},
        }
        other_log = {
            "session_id": "other-session",
            "timestamp": "2026-01-01T00:00:01Z",
            "event": {"hook_event_name": "UserPromptSubmit", "session_id": "other-session", "prompt": "yo"},
        }
        exchange = {"conversation_id": "sess-xyz", "messages": [{"role": "user", "content": "hi"}], "model": "auto", "permission_mode": "default"}

        with patch.object(hh, "_audit_log"), \
             patch.object(hh, "_load_logs", return_value=[session_log, other_log]), \
             patch.object(hh, "_build_exchange", return_value=exchange), \
             patch.object(hh, "_send_exchange", return_value=True) as mock_send, \
             patch.object(hh, "_save_logs") as mock_save, \
             patch.object(hh, "_cleanup_logs"), \
             patch.dict("os.environ", {"UNBOUND_CLAUDE_API_KEY": "key"}):
            hh.handle_stop(self._PAYLOAD)

        mock_send.assert_called_once_with(exchange, "key")
        saved = mock_save.call_args[0][0]
        assert len(saved) == 1
        assert saved[0]["session_id"] == "other-session"

    def test_failed_send_writes_offline_log(self, tmp_path):
        exchange = {"conversation_id": "sess-xyz", "messages": [], "model": "auto", "permission_mode": "default"}

        offline_file = tmp_path / "offline-events.jsonl"
        with patch.object(hh, "_audit_log"), \
             patch.object(hh, "_load_logs", return_value=[]), \
             patch.object(hh, "_build_exchange", return_value=exchange), \
             patch.object(hh, "_send_exchange", return_value=False), \
             patch.object(hh, "_save_logs"), \
             patch.object(hh, "_cleanup_logs"), \
             patch.object(hh, "OFFLINE_LOG", offline_file), \
             patch.object(hh, "LOG_DIR", tmp_path), \
             patch.dict("os.environ", {"UNBOUND_CLAUDE_API_KEY": "key"}):
            hh.handle_stop(self._PAYLOAD)

        assert offline_file.exists()
        entry = json.loads(offline_file.read_text().strip())
        assert entry["exchange"]["conversation_id"] == "sess-xyz"

    def test_no_exchange_built_skips_send(self):
        with patch.object(hh, "_audit_log"), \
             patch.object(hh, "_load_logs", return_value=[]), \
             patch.object(hh, "_build_exchange", return_value=None), \
             patch.object(hh, "_send_exchange") as mock_send, \
             patch.object(hh, "_cleanup_logs"), \
             patch.dict("os.environ", {"UNBOUND_CLAUDE_API_KEY": "key"}):
            hh.handle_stop(self._PAYLOAD)
        mock_send.assert_not_called()

    def test_exception_in_stop_does_not_propagate(self):
        """Stop must never raise — it's a non-blocking async hook."""
        with patch.object(hh, "_audit_log"), \
             patch.object(hh, "_load_logs", side_effect=RuntimeError("disk full")), \
             patch.dict("os.environ", {"UNBOUND_CLAUDE_API_KEY": "key"}):
            hh.handle_stop(self._PAYLOAD)  # should not raise


import os  # needed for os.environ.pop in tests
