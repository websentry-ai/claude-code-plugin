#!/usr/bin/env python3
"""Unbound AI hook handler for Claude Code.

Phase 2: All hooks fire and return "allow" by default.
         Debug logging captures exact stdin JSON from Claude Code.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path


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
    """PreToolUse: return explicit allow decision."""
    response = {
        "hookSpecificOutput": {
            "permissionDecision": "allow",
        }
    }
    print(json.dumps(response))


def handle_user_prompt_submit(payload: dict) -> None:
    """UserPromptSubmit: return empty → allow."""
    # Empty output = allow the prompt through
    pass


def handle_post_tool_use(payload: dict) -> None:
    """PostToolUse: async event, no decision needed."""
    # Empty output — Claude Code does not block on this event
    pass


def handle_stop(payload: dict) -> None:
    """Stop: async event, no decision needed."""
    # Empty output — Claude Code does not block on this event
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
