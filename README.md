# Unbound — Security & Governance for Claude Code

Real-time policy enforcement, DLP guardrails, and session analytics for [Claude Code](https://claude.ai/code) — powered by [Unbound AI](https://getunbound.ai).

## Why Unbound?

Engineering teams adopting Claude Code face real risks: sensitive data pasted into prompts, dangerous commands executed without oversight, and zero visibility into what's happening across sessions. Unbound solves this by sitting between your developers and Claude Code — enforcing security policies in real time and sending each conversation turn to a central dashboard. No workflow disruption, no developer friction.

## Quick Start

### Step 1 — Install the plugin

Inside Claude Code, run these two commands:

```
/plugin marketplace add websentry-ai/claude-code-plugin
/plugin install unbound@unbound-marketplace
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
| **Audit logging** | Records each tool call and sends it to the Unbound dashboard when Claude finishes responding |
| **Session analytics** | Sends the conversation exchange (prompt, tool calls, response) at the end of each turn |

## Data and Privacy

The plugin sends data only to the Unbound API at `https://api.getunbound.ai`, and only when `UNBOUND_CLAUDE_API_KEY` is set. Every request carries the key as a Bearer token. If you set `UNBOUND_GATEWAY_URL`, requests go to that URL instead (used for self-hosted Unbound deployments).

### What is sent

| Hook | Endpoint | Data sent |
|---|---|---|
| `UserPromptSubmit` | `POST /v1/hooks/pretool` | Session ID, model name (or `auto`), and the text of your prompt, for the DLP / NSFW / jailbreak check |
| `PreToolUse` | `POST /v1/hooks/pretool` | Session ID, model name (or `auto`), tool name, the full tool input (for example the shell command, file path, or URL), MCP server and tool name, your latest prompt, and the rest of the hook event that Claude Code passes to the plugin (working directory, transcript file path, permission mode, tool-use ID), for the policy check. If your prompt is not in the local audit log, the last user entry of the session transcript is sent instead, which can be a tool result |
| `PostToolUse` | none | Nothing is sent. The tool input and output are written to the local audit log |
| `Stop` | `POST /v1/hooks/claude` | Session ID, permission mode, your prompt, each tool call in the turn with its input and output, and Claude's response (read from the session transcript) |

Unbound uses this data to enforce your organization's policies and to show sessions on your Unbound dashboard. The plugin sends no other data and contacts no other service.

### What is stored on your machine

These files are written whether or not `UNBOUND_CLAUDE_API_KEY` is set.

| Path | Contents |
|---|---|
| `~/.unbound/logs/debug.jsonl` | The raw input of every hook event (prompts, tool inputs and outputs) and the timing of each API call. Not rotated; delete it at any time |
| `~/.claude/hooks/agent-audit.log` | Prompts and tool calls of the current session, used to build the exchange sent at `Stop`. When a key is set, entries are removed once sent, and the file is trimmed to one session when it passes 50 entries. Without a key it is not trimmed |
| `~/.unbound/logs/offline-events.jsonl` | Exchanges that could not be sent because the API was unreachable (only when a key is set). They are kept for inspection, are not resent automatically, and the file is not rotated |
| `~/.claude/hooks/error.log` | The last 25 API errors |

### What setup changes

`/unbound:setup` first removes any existing `export UNBOUND_CLAUDE_API_KEY=` line from your shell profile. It then opens your browser at `https://gateway.getunbound.ai` so you can sign in and create a key. A one-time server on `127.0.0.1` receives the key, and the script appends `export UNBOUND_CLAUDE_API_KEY=...` to your shell profile (`~/.zprofile`, `~/.bash_profile`, `~/.zshrc`, or `~/.bashrc`). On Windows it sets a user environment variable with `setx`. To check the key, setup then calls `GET https://api.getunbound.ai/v1/models` with it. Run the setup again and choose **Reconfigure** to replace the key, or remove the line from your shell profile to remove it.

## Fail-Open Design

The plugin never blocks your workflow if the Unbound API is unreachable or the key is missing. All hooks fail open: Claude Code continues working normally. When a key is set but the API is unreachable, exchanges that could not be sent are kept in `~/.unbound/logs/offline-events.jsonl`.

## Enterprise Deployment

### Without MDM (Claude Team and Enterprise)

An Owner of your Claude organization can install the plugin for every Claude Code user and stop users from disabling it. Paste this into **Organization settings > Claude Code > Managed settings** on claude.ai:

```json
{
  "extraKnownMarketplaces": {
    "unbound-marketplace": {
      "source": { "source": "github", "repo": "websentry-ai/claude-code-plugin" },
      "autoUpdate": true
    }
  },
  "enabledPlugins": {
    "unbound@unbound-marketplace": true
  }
}
```

Claude Code installs the plugin at the start of each user's next session. Each user still needs an API key: run `/unbound:setup`, or provision `UNBOUND_CLAUDE_API_KEY` on each device.

### With MDM

For fleet deployment where end users cannot disable the plugin, see the [enterprise deployment guide](enterprise/README.md). In short: drop a managed settings file via your MDM and provision `UNBOUND_CLAUDE_API_KEY` per device.

## Configuration

| Variable | Description |
|---|---|
| `UNBOUND_CLAUDE_API_KEY` | Bearer token for the Unbound API. Get one at [app.getunbound.ai](https://app.getunbound.ai) → Settings → API Keys |
| `UNBOUND_GATEWAY_URL` | Optional. Base URL of the Unbound API. Defaults to `https://api.getunbound.ai` |

Log file locations are listed under [What is stored on your machine](#what-is-stored-on-your-machine).

## Troubleshooting

**Plugin not loading**
Run `claude plugin list` and confirm `unbound` appears. If not, re-install with `/plugin marketplace add websentry-ai/claude-code-plugin` followed by `/plugin install unbound@unbound-marketplace`.

**API key not set**
Run `/unbound:setup` again — it will detect the missing key and guide you through setup. You can also set `UNBOUND_CLAUDE_API_KEY` manually in your shell profile.

**Command blocked unexpectedly**
Check your policy rules at [app.getunbound.ai](https://app.getunbound.ai). The block response includes a reason — review it to confirm the rule that triggered.

**Events not appearing on dashboard**
Verify your API key is valid and the Unbound API is reachable. Check `~/.claude/hooks/error.log` for details. Exchanges that could not be sent are kept in `~/.unbound/logs/offline-events.jsonl`; they are not resent automatically.

## Support

Questions or issues? Email [support@unboundsecurity.ai](mailto:support@unboundsecurity.ai).

## License

[MIT](LICENSE)
