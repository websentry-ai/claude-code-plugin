"""Regression tests for the ARG_MAX fix in scripts/lib/unbound.py.

The bug: send_to_api and send_to_hook_api previously passed the JSON body
as a -d <data> CLI argument to curl. Once the conversation/transcript
payload exceeded the OS ARG_MAX limit (~256KB on macOS, ~2MB on Linux),
subprocess.run raised OSError: [Errno 7] Argument list too long.

The fix: switch to --data-binary @- + input=data.encode("utf-8", ...) so
the body travels via a stdin pipe instead of argv.

These tests pin the wire-level invariants that the next refactor must
preserve. If any of them fail, the original Sentry regression
(HookError:api_call, 4 events, regression after ai-gateway PR #503)
is at risk of recurring.
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

_ROOT = Path(__file__).parent.parent
_LIB = _ROOT / "scripts" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from unbound import send_to_api, send_to_hook_api


def _argv_invariants(call_args):
    """Argv must not carry the body; --data-binary @- must read stdin."""
    argv = call_args[0][0]
    assert "-d" not in argv, "regression: body must not be passed via -d"
    assert "--data" not in argv, "regression: body must not be passed via --data"
    assert "--data-binary" in argv, "expected --data-binary @- transport"
    idx = argv.index("--data-binary")
    assert argv[idx + 1] == "@-", "expected stdin sentinel '@-'"


def _input_invariants(call_args, expected_body):
    """input= kwarg must carry bytes that round-trip to the original JSON body."""
    kwargs = call_args[1]
    assert "input" in kwargs, "regression: body must be passed via input= kwarg"
    payload = kwargs["input"]
    assert isinstance(payload, bytes), "input= must be bytes, not str"
    assert json.loads(payload.decode("utf-8")) == expected_body


class TestSendToApiArgmaxRegression:

    @patch("subprocess.run")
    def test_body_travels_via_stdin_not_argv(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout=b"", stderr=b"")
        exchange = {"messages": [{"role": "user", "content": "hi"}]}

        assert send_to_api(exchange, "key") is True

        _argv_invariants(mock_run.call_args)
        _input_invariants(mock_run.call_args, exchange)

    @patch("subprocess.run")
    def test_multi_megabyte_body_does_not_touch_argv(self, mock_run):
        """Payload above macOS ARG_MAX (~256KB) must still go through stdin."""
        mock_run.return_value = MagicMock(returncode=0, stdout=b"", stderr=b"")
        # 3 MB of content — comfortably above every common ARG_MAX
        huge = {"messages": [{"role": "user", "content": "x" * 3_000_000}]}

        assert send_to_api(huge, "key") is True

        _argv_invariants(mock_run.call_args)
        argv = mock_run.call_args[0][0]
        joined_argv_size = sum(len(a) for a in argv)
        assert joined_argv_size < 10_000, (
            "regression: argv unexpectedly large — body may be leaking back into args"
        )
        _input_invariants(mock_run.call_args, huge)

    @patch("subprocess.run")
    def test_lone_surrogate_in_payload_does_not_raise(self, mock_run):
        """errors='replace' on encode() guards against UnicodeEncodeError on
        malformed unicode in tool output (e.g., a lone surrogate)."""
        mock_run.return_value = MagicMock(returncode=0, stdout=b"", stderr=b"")
        # json.dumps with default ensure_ascii=True will escape these, but if a
        # caller ever passes ensure_ascii=False through, encode() must not crash.
        bad = {"messages": [{"role": "user", "content": "ok\ud800tail"}]}

        # Should not raise; fail-open semantics are preserved.
        assert send_to_api(bad, "key") is True
        kwargs = mock_run.call_args[1]
        assert isinstance(kwargs["input"], bytes)


class TestSendToHookApiArgmaxRegression:

    @patch("subprocess.run")
    def test_body_travels_via_stdin_not_argv(self, mock_run):
        body_bytes = json.dumps({"decision": "allow"}).encode()
        mock_run.return_value = MagicMock(returncode=0, stdout=body_bytes, stderr=b"")
        request = {"event_name": "tool_use", "conversation_id": "s1"}

        result = send_to_hook_api(request, "key")
        assert result == {"decision": "allow"}

        _argv_invariants(mock_run.call_args)
        _input_invariants(mock_run.call_args, request)

    @patch("subprocess.run")
    def test_multi_megabyte_body_does_not_touch_argv(self, mock_run):
        body_bytes = json.dumps({"decision": "allow"}).encode()
        mock_run.return_value = MagicMock(returncode=0, stdout=body_bytes, stderr=b"")
        huge = {
            "event_name": "tool_use",
            "conversation_id": "s1",
            "pre_tool_use_data": {"tool_name": "Bash", "command": "x" * 3_000_000},
        }

        assert send_to_hook_api(huge, "key") == {"decision": "allow"}

        _argv_invariants(mock_run.call_args)
        argv = mock_run.call_args[0][0]
        joined_argv_size = sum(len(a) for a in argv)
        assert joined_argv_size < 10_000
        _input_invariants(mock_run.call_args, huge)
