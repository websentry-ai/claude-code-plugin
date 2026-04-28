# Unbound — Security & Governance for Claude Code

Real-time policy enforcement, DLP guardrails, and session analytics for [Claude Code](https://claude.ai/code) — powered by [Unbound AI](https://getunbound.ai).

## Why Unbound?

Engineering teams adopting Claude Code face real risks: sensitive data pasted into prompts, dangerous commands executed without oversight, and zero visibility into what's happening across sessions. Unbound solves this by sitting between your developers and Claude Code — enforcing security policies in real time and streaming every session to a central dashboard. No workflow disruption, no developer friction.

## Quick Start

### Step 1 — Install the plugin

Inside Claude Code, run these two commands:

```
/plugin marketplace add websentry-ai/claude-code-plugin
/plugin install unbound@websentry-ai/claude-code-plugin
```

### Step 2 — Run setup

Open Claude Code and run:

```
/unbound:setup
```

The setup skill walks you through getting an API key, persisting it to your shell profile, and verifying connectivity. Takes under 5 minutes.

### Step 3 — Verify on your dashboard

After setup, every tool invocation is checked against your Unbound policies. Test with:

- **Command policy**: create a BLOCK rule in your Unbound dashboard, then try running the blocked command — it should be rejected
- **DLP guardrail**: enable DLP, then type a prompt containing an SSN — it should be blocked
- **Analytics**: run any command, then check your Unbound dashboard for the event

## What Gets Enforced

| Capability | What it does |
|---|---|
| **Command policies** | Block or warn on dangerous tool invocations before they execute |
| **Prompt guardrails** | DLP, NSFW, and jailbreak detection on every user prompt |
| **Audit logging** | Streams tool usage to the Unbound dashboard in real time |
| **Session analytics** | Sends the full conversation exchange when a session ends |

## Fail-Open Design

The plugin never blocks your workflow if the Unbound API is unreachable or the key is missing. All hooks fail open — Claude Code continues working normally, and queued events are replayed when connectivity resumes.

## Enterprise Deployment

For fleet deployment where end users cannot disable the plugin, see the [enterprise deployment guide](enterprise/README.md). In short: drop a managed settings file via your MDM and provision `UNBOUND_CLAUDE_API_KEY` per device.

## Configuration

| Variable | Description |
|---|---|
| `UNBOUND_CLAUDE_API_KEY` | Bearer token for the Unbound API. Get one at [app.getunbound.ai](https://app.getunbound.ai) → Settings → API Keys |

## Logs

| Path | Contents |
|---|---|
| `~/.unbound/logs/debug.jsonl` | Raw stdin from every hook event (for debugging) |
| `~/.claude/hooks/agent-audit.log` | Per-session audit trail |
| `~/.unbound/logs/offline-events.jsonl` | Events that failed to send (replayed on reconnect) |
| `~/.claude/hooks/error.log` | API errors (last 25 entries) |

## Troubleshooting

**Plugin not loading**
Run `claude plugin list` and confirm `unbound` appears. If not, re-install with `/plugin marketplace add websentry-ai/claude-code-plugin` followed by `/plugin install unbound@websentry-ai/claude-code-plugin`.

**API key not set**
Run `/unbound:setup` again — it will detect the missing key and guide you through setup. You can also set `UNBOUND_CLAUDE_API_KEY` manually in your shell profile.

**Command blocked unexpectedly**
Check your policy rules at [app.getunbound.ai](https://app.getunbound.ai). The block response includes a reason — review it to confirm the rule that triggered.

**Events not appearing on dashboard**
Verify your API key is valid and the Unbound API is reachable. Check `~/.claude/hooks/error.log` for details. Offline events are stored in `~/.unbound/logs/offline-events.jsonl` and replayed automatically.

## License

[MIT](LICENSE)
