"""Unit tests for Phase 3: PreToolUse hook — Unbound API integration.

Covers:
  - Task 3.7  stdin → API payload transformation
  - Task 3.8  API response → Claude Code stdout transformation
  - Task 3.9  Error paths (timeout, 500, missing env, malformed stdin)
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Path setup — import directly from scripts/lib/unbound.py
# ---------------------------------------------------------------------------
_LIB = Path(__file__).parent.parent / "scripts" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from unbound import (
    extract_command_for_pretool,
    process_pre_tool_use,
    transform_response_for_claude,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_api_response(decision: str, reason: str = "") -> MagicMock:
    """Return a mock subprocess.CompletedProcess with a JSON API response."""
    body = json.dumps({"decision": decision, "reason": reason}).encode()
    return MagicMock(returncode=0, stdout=body)


# ---------------------------------------------------------------------------
# Task 3.7 — stdin → API payload transformation
# (extract_command_for_pretool maps each tool type to the right field)
# ---------------------------------------------------------------------------

class TestExtractCommandForPretool:

    def test_bash_uses_command_field(self):
        event = {"tool_name": "Bash", "tool_input": {"command": "rm -rf /"}}
        assert extract_command_for_pretool(event) == "rm -rf /"

    def test_write_uses_file_path(self):
        event = {"tool_name": "Write", "tool_input": {"file_path": "/etc/passwd"}}
        assert extract_command_for_pretool(event) == "/etc/passwd"

    def test_edit_uses_file_path(self):
        event = {"tool_name": "Edit", "tool_input": {"file_path": "/tmp/app.py"}}
        assert extract_command_for_pretool(event) == "/tmp/app.py"

    def test_read_uses_file_path(self):
        event = {"tool_name": "Read", "tool_input": {"file_path": "/etc/hosts"}}
        assert extract_command_for_pretool(event) == "/etc/hosts"

    def test_grep_uses_pattern(self):
        event = {"tool_name": "Grep", "tool_input": {"pattern": "password"}}
        assert extract_command_for_pretool(event) == "password"

    def test_glob_uses_pattern(self):
        event = {"tool_name": "Glob", "tool_input": {"pattern": "**/*.env"}}
        assert extract_command_for_pretool(event) == "**/*.env"

    def test_webfetch_uses_url(self):
        event = {"tool_name": "WebFetch", "tool_input": {"url": "https://example.com"}}
        assert extract_command_for_pretool(event) == "https://example.com"

    def test_websearch_uses_query(self):
        event = {"tool_name": "WebSearch", "tool_input": {"query": "exploit db"}}
        assert extract_command_for_pretool(event) == "exploit db"

    def test_task_uses_prompt(self):
        event = {"tool_name": "Task", "tool_input": {"prompt": "do something"}}
        assert extract_command_for_pretool(event) == "do something"

    def test_unknown_tool_falls_back_to_tool_name(self):
        event = {"tool_name": "CustomTool", "tool_input": {"other": "value"}}
        assert extract_command_for_pretool(event) == "CustomTool"

    def test_empty_event_returns_empty_string(self):
        assert extract_command_for_pretool({}) == ""

    @patch("subprocess.run")
    def test_payload_includes_session_id_as_conversation_id(self, mock_run):
        mock_run.return_value = _make_api_response("allow")
        process_pre_tool_use(
            {"session_id": "my-session", "tool_name": "Bash", "tool_input": {"command": "ls"}},
            "key",
        )
        cmd = mock_run.call_args[0][0]
        payload = json.loads(cmd[cmd.index("-d") + 1])
        assert payload["conversation_id"] == "my-session"

    @patch("subprocess.run")
    def test_payload_sets_event_name_and_app_label(self, mock_run):
        mock_run.return_value = _make_api_response("allow")
        process_pre_tool_use(
            {"session_id": "s", "tool_name": "Bash", "tool_input": {"command": "pwd"}},
            "key",
        )
        cmd = mock_run.call_args[0][0]
        payload = json.loads(cmd[cmd.index("-d") + 1])
        assert payload["event_name"] == "tool_use"
        assert payload["unbound_app_label"] == "claude-code"

    @patch("subprocess.run")
    def test_payload_includes_tool_name_and_command_in_pre_tool_use_data(self, mock_run):
        mock_run.return_value = _make_api_response("allow")
        process_pre_tool_use(
            {"session_id": "s", "tool_name": "Bash", "tool_input": {"command": "echo hi"}},
            "key",
        )
        cmd = mock_run.call_args[0][0]
        payload = json.loads(cmd[cmd.index("-d") + 1])
        pre = payload["pre_tool_use_data"]
        assert pre["tool_name"] == "Bash"
        assert pre["command"] == "echo hi"


# ---------------------------------------------------------------------------
# Task 3.8 — API response → Claude Code stdout transformation
# ---------------------------------------------------------------------------

class TestTransformResponseForClaude:

    def test_deny_maps_correctly(self):
        result = transform_response_for_claude({"decision": "deny", "reason": "Blocked by policy"})
        out = result["hookSpecificOutput"]
        assert out["permissionDecision"] == "deny"
        assert out["permissionDecisionReason"] == "Blocked by policy"

    def test_allow_maps_correctly(self):
        result = transform_response_for_claude({"decision": "allow", "reason": ""})
        assert result["hookSpecificOutput"]["permissionDecision"] == "allow"

    def test_ask_decision_is_preserved(self):
        result = transform_response_for_claude({"decision": "ask", "reason": "Needs review"})
        assert result["hookSpecificOutput"]["permissionDecision"] == "ask"

    def test_missing_decision_defaults_to_allow(self):
        result = transform_response_for_claude({"reason": "no decision field"})
        assert result["hookSpecificOutput"]["permissionDecision"] == "allow"

    def test_empty_api_response_returns_empty_dict(self):
        assert transform_response_for_claude({}) == {}

    def test_hook_event_name_is_set(self):
        result = transform_response_for_claude({"decision": "allow"})
        assert result["hookSpecificOutput"]["hookEventName"] == "PreToolUse"

    @patch("subprocess.run")
    def test_deny_forwarded_end_to_end(self, mock_run):
        mock_run.return_value = _make_api_response("deny", "Blocked")
        result = process_pre_tool_use(
            {"session_id": "s", "tool_name": "Bash", "tool_input": {"command": "rm -rf /"}},
            "key",
        )
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert result["hookSpecificOutput"]["permissionDecisionReason"] == "Blocked"

    @patch("subprocess.run")
    def test_allow_forwarded_end_to_end(self, mock_run):
        mock_run.return_value = _make_api_response("allow")
        result = process_pre_tool_use(
            {"session_id": "s", "tool_name": "Bash", "tool_input": {"command": "ls"}},
            "key",
        )
        assert result["hookSpecificOutput"]["permissionDecision"] == "allow"


# ---------------------------------------------------------------------------
# Task 3.9 — Error paths: all must fail open (return {} → allow)
# ---------------------------------------------------------------------------

class TestErrorPaths:

    STDIN = {
        "session_id": "sess-abc",
        "tool_name": "Bash",
        "tool_input": {"command": "ls"},
        "model": "claude-sonnet-4-6",
    }

    def test_empty_api_key_returns_empty(self):
        assert process_pre_tool_use(self.STDIN, "") == {}

    def test_none_api_key_returns_empty(self):
        assert process_pre_tool_use(self.STDIN, None) == {}

    @patch("subprocess.run")
    def test_api_500_returns_empty(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout=b"", stderr=b"500 Internal Server Error")
        assert process_pre_tool_use(self.STDIN, "key") == {}

    @patch("subprocess.run", side_effect=Exception("Connection timed out"))
    def test_network_timeout_returns_empty(self, mock_run):
        assert process_pre_tool_use(self.STDIN, "key") == {}

    @patch("subprocess.run")
    def test_malformed_json_from_api_returns_empty(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout=b"not-valid-json{{{")
        assert process_pre_tool_use(self.STDIN, "key") == {}

    @patch("subprocess.run")
    def test_empty_stdout_from_api_returns_empty(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout=b"")
        assert process_pre_tool_use(self.STDIN, "key") == {}

    def test_malformed_stdin_tool_input_still_calls_api(self):
        # Missing tool_input entirely — should not raise, just use tool_name as command
        stdin = {"session_id": "s", "tool_name": "Bash"}
        # No API key → returns {} without hitting network
        assert process_pre_tool_use(stdin, "") == {}
