# Unbound Claude Code Plugin

Security, governance, and analytics for [Claude Code](https://claude.ai/code) — powered by [Unbound AI](https://getunbound.ai).

## What it does

This plugin connects Claude Code to the Unbound AI platform:

| Hook | What it enforces |
|---|---|
| **PreToolUse** | Command policy — block or warn on dangerous tool invocations |
| **UserPromptSubmit** | Guardrails — DLP, NSFW, and jailbreak detection on user prompts |
| **PostToolUse** | Audit logging — streams tool usage to the Unbound dashboard |
| **Stop** | Session analytics — sends the full conversation exchange on session end |

All hooks **fail open**: if the API is unreachable or the key is missing, Claude Code continues normally.

---

## Self-serve install

### Step 1 — Install the plugin

```bash
claude plugin install unbound@unbound-marketplace
```

Or from a local clone:

```bash
claude plugin install --path /path/to/claude-code-plugin
```

### Step 2 — Run setup

Open Claude Code and run:

```
/unbound:setup
```

The skill guides you through getting an API key, persisting it to your shell profile, and verifying connectivity. Takes under 5 minutes.

### Step 3 — Verify

After setup, any tool invocation is checked against your Unbound policies. Test with:

- **Block policy**: create a BLOCK rule in your Unbound dashboard → try running `rm -rf /` → should be blocked
- **DLP guardrail**: enable DLP → type a prompt containing an SSN → should be blocked
- **Analytics**: run any command → check your Unbound dashboard for the event

---

## Enterprise (MDM) install

For fleet deployment where users cannot disable the plugin, see [`enterprise/README.md`](enterprise/README.md).

The short version:

1. Copy `enterprise/managed-settings.json.tmpl` to the system-wide Claude Code path as `managed-settings.json`
2. Provision `UNBOUND_API_KEY` per device via your MDM

---

## Configuration

The plugin reads one environment variable:

| Variable | Description |
|---|---|
| `UNBOUND_API_KEY` | Bearer token for the Unbound API. Get one at https://app.getunbound.ai → Settings → API Keys |

---

## Logs

| Path | Contents |
|---|---|
| `~/.unbound/logs/debug.jsonl` | Raw stdin from every hook event (for debugging) |
| `~/.claude/hooks/agent-audit.log` | Per-session audit trail (UserPromptSubmit, PostToolUse) |
| `~/.claude/hooks/error.log` | API errors (last 25 entries) |
| `~/.unbound/logs/offline-events.jsonl` | Exchanges that failed to send (replayed on reconnect) |

---

## Project structure

```
.claude-plugin/
  plugin.json              Plugin manifest
  marketplace.json         Marketplace catalog
hooks/
  hooks.json               Hook event configuration
scripts/
  hook-handler.py          Central hook dispatcher (Phases 3–5)
  lib/
    unbound.py             Unbound API helpers (copied from websentry-ai/setup)
skills/
  setup/
    SKILL.md               /unbound:setup self-serve onboarding skill
enterprise/
  managed-settings.json.tmpl   MDM template for fleet enforcement
  README.md                    Enterprise deployment guide
tests/
  test_pretool.py          Phase 3 unit tests
  test_phase4_5.py         Phase 4+5 unit tests
  test_sanity.py           Production readiness tests (P0/P1 coverage)
  requirements.txt         pytest
```

---

## Development

```bash
# Run all tests
pip install pytest
python3 -m pytest tests/ -v

# Validate plugin
claude plugin validate .

# Install locally
claude plugin install --path .
```

---

## License

[MIT](LICENSE)
