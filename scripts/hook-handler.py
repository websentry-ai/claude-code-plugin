#!/usr/bin/env python3
"""Unbound AI hook handler for Claude Code.

Phase 3: PreToolUse calls Unbound API for command policy enforcement.
         All other hooks remain default-allow from Phase 2.

Environment variables:
    UNBOUND_CLAUDE_API_KEY  Bearer token for the Unbound API.
                            If unset, PreToolUse fails open (allow).
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Import shared Unbound API helpers from scripts/lib/unbound.py.
# That file is a verbatim copy of websentry-ai/setup/claude-code/hooks/unbound.py
# kept here so the plugin stays self-contained (no submodule, no pip dep).
# ---------------------------------------------------------------------------
_LIB = Path(__file__).parent / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from unbound import process_pre_tool_use as _call_pretool_api  # noqa: E402


LOG_DIR = Path.home() / ".unbound" / "logs"
DEBUG_LOG = LOG_DIR / "debug.jsonl"


def write_debug_log(event: str, payload: dict) -> None:
    """Append a debug entry to ~/.unbound/logs/debug.jsonl."""
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "stdin": payload,
        }
        with DEBUG_LOG.open("a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass  # Fail open: logging failure should never break hooks


def handle_pre_tool_use(payload: dict) -> None:
    """PreToolUse: call Unbound API for policy enforcement.

    Decision matrix:
      - No API key configured  → allow (fail open)
      - API returns deny/ask   → forward decision to Claude Code
      - API error / timeout    → allow (fail open)
      - Any unexpected error   → allow (fail open)
    """
    _ALLOW = {"hookSpecificOutput": {"permissionDecision": "allow"}, "suppressOutput": True}

    api_key = os.getenv("UNBOUND_CLAUDE_API_KEY")
    if not api_key:
        print(json.dumps(_ALLOW))
        return

    try:
        result = _call_pretool_api(payload, api_key)
    except Exception:
        result = {}

    if result:
        result["suppressOutput"] = True
        print(json.dumps(result))
    else:
        print(json.dumps(_ALLOW))


def handle_user_prompt_submit(payload: dict) -> None:
    """UserPromptSubmit: return empty → allow."""
    pass


def handle_post_tool_use(payload: dict) -> None:
    """PostToolUse: async event, no decision needed."""
    pass


def handle_stop(payload: dict) -> None:
    """Stop: async event, no decision needed."""
    pass


HANDLERS = {
    "PreToolUse": handle_pre_tool_use,
    "UserPromptSubmit": handle_user_prompt_submit,
    "PostToolUse": handle_post_tool_use,
    "Stop": handle_stop,
}


def main() -> None:
    event = sys.argv[1] if len(sys.argv) > 1 else "Unknown"

    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        payload = {"raw": raw}

    write_debug_log(event, payload)

    handler = HANDLERS.get(event)
    if handler:
        handler(payload)

    sys.exit(0)


if __name__ == "__main__":
    main()
