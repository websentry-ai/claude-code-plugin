#!/usr/bin/env python3
"""Unbound AI hook handler for Claude Code.

Phase 3: PreToolUse  — calls Unbound API for command policy enforcement.
Phase 4: UserPromptSubmit — calls Unbound API for guardrail checks (DLP/NSFW/Jailbreak).
Phase 5: PostToolUse + Stop — audit logging + async exchange submission to Unbound API.

Environment variables:
    UNBOUND_API_KEY  Bearer token for the Unbound API.
                            If unset, all hooks fail open (allow / no-op).
"""

import json
import os
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

from unbound import (  # noqa: E402
    append_to_audit_log as _audit_log,
    build_llm_exchange as _build_exchange,
    cleanup_old_logs as _cleanup_logs,
    load_existing_logs as _load_logs,
    parse_transcript_file as _parse_transcript,
    process_pre_tool_use as _call_pretool_api,
    process_user_prompt_submit as _call_user_prompt_api,
    save_logs as _save_logs,
    send_to_api as _send_exchange,
)


LOG_DIR = Path.home() / ".unbound" / "logs"
DEBUG_LOG = LOG_DIR / "debug.jsonl"
OFFLINE_LOG = LOG_DIR / "offline-events.jsonl"


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


def _write_offline(exchange: dict) -> None:
    """Write a failed exchange to ~/.unbound/logs/offline-events.jsonl."""
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "exchange": exchange,
        }
        with OFFLINE_LOG.open("a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass  # Fail open: offline logging failure should never break hooks


def _make_log_entry(hook_event_name: str, payload: dict) -> dict:
    """Build a timestamped audit log entry, ensuring hook_event_name is present."""
    return {
        "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
        "session_id": payload.get("session_id"),
        "event": {**payload, "hook_event_name": hook_event_name},
    }


# ---------------------------------------------------------------------------
# Phase 3 — PreToolUse
# ---------------------------------------------------------------------------

def handle_pre_tool_use(payload: dict) -> None:
    """PreToolUse: call Unbound API for policy enforcement.

    Decision matrix:
      - No API key configured  → allow (fail open)
      - API returns deny/ask   → forward decision to Claude Code
      - API error / timeout    → allow (fail open)
      - Any unexpected error   → allow (fail open)
    """
    _ALLOW = {"hookSpecificOutput": {"permissionDecision": "allow"}, "suppressOutput": True}

    api_key = os.getenv("UNBOUND_API_KEY")
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


# ---------------------------------------------------------------------------
# Phase 4 — UserPromptSubmit
# ---------------------------------------------------------------------------

def handle_user_prompt_submit(payload: dict) -> None:
    """UserPromptSubmit: check prompt against Unbound guardrails.

    - If blocked (deny)  → output { decision: "block", reason: "..." } and return.
                           The prompt is NOT logged (blocked prompts leave no trace).
    - If allowed         → log to audit log so Stop can include it in the exchange.
    - No API key         → skip policy check, log, fail open.
    - API error/timeout  → skip policy check, log, fail open.
    """
    api_key = os.getenv("UNBOUND_API_KEY")

    if api_key:
        try:
            result = _call_user_prompt_api(payload, api_key)
        except Exception:
            result = {}

        if result.get("decision") == "block":
            result["suppressOutput"] = True
            print(json.dumps(result))
            return  # Do not log blocked prompts

    # Allowed — log so Stop can reconstruct the full exchange
    _audit_log(_make_log_entry("UserPromptSubmit", payload))


# ---------------------------------------------------------------------------
# Phase 5 — PostToolUse
# ---------------------------------------------------------------------------

def handle_post_tool_use(payload: dict) -> None:
    """PostToolUse: append tool use to audit log for aggregation on Stop."""
    _audit_log(_make_log_entry("PostToolUse", payload))


# ---------------------------------------------------------------------------
# Phase 5 — Stop
# ---------------------------------------------------------------------------

def handle_stop(payload: dict) -> None:
    """Stop: build the full LLM exchange for this session and send to Unbound API.

    On success  → clean up session entries from the audit log.
    On failure  → write the exchange to ~/.unbound/logs/offline-events.jsonl
                  so data is preserved for later retry.
    No API key  → skip API call (audit log entries remain for manual inspection).
    """
    _audit_log(_make_log_entry("Stop", payload))

    api_key = os.getenv("UNBOUND_API_KEY")
    if not api_key:
        return

    try:
        session_id = payload.get("session_id")
        transcript_path = payload.get("transcript_path")

        logs = _load_logs()
        session_events = []
        started = False
        user_prompt_ts = None

        for log in logs:
            sid = log.get("session_id") or log.get("event", {}).get("session_id")
            if sid != session_id:
                continue
            ev_name = (
                log.get("event", {}).get("hook_event_name")
                if "event" in log
                else log.get("hook_event_name")
            )
            if ev_name == "UserPromptSubmit":
                session_events = [log]
                started = True
                user_prompt_ts = log.get("timestamp")
            elif started:
                session_events.append(log)

        transcript_data = None
        if transcript_path and transcript_path != "undefined":
            transcript_data = _parse_transcript(transcript_path, user_prompt_ts)

        exchange = _build_exchange(session_events, transcript_data)

        if exchange:
            sent = _send_exchange(exchange, api_key)
            if sent:
                remaining = [
                    log for log in logs
                    if log.get("session_id") != session_id
                    and (
                        not log.get("event")
                        or log.get("event", {}).get("session_id") != session_id
                    )
                ]
                _save_logs(remaining)
            else:
                _write_offline(exchange)

        _cleanup_logs()

    except Exception:
        pass


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

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
