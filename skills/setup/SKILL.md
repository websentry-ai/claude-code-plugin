---
name: setup
description: Configure Unbound AI credentials and verify connectivity for the Claude Code plugin. Use when setting up for the first time, reconfiguring with a new API key, or diagnosing connectivity issues.
user-invocable: true
---

# Unbound Setup

You are helping the user configure the Unbound AI plugin for Claude Code. Follow these steps precisely and in order. The API key is handled entirely by the setup script — you never see, store, or echo it.

---

## Step 1 — Check current state

Run this command to check whether the API key is already configured:

```bash
echo "${UNBOUND_API_KEY:0:8}..."
```

**If the variable is unset or empty**, proceed to Step 2.

**If the variable is already set**, tell the user the key is configured (show only the first 8 characters + `...`). Ask them to choose:
1. **Verify** — test connectivity with the existing key (jump to Step 3)
2. **Reconfigure** — replace with a new key (proceed to Step 2)
3. **Exit** — nothing to do

---

## Step 2 — Authenticate via browser

Run the setup script — it handles everything (local callback server, browser auth, key persistence to RC files, Claude Code apiKeyHelper configuration):

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/setup.py" --domain gateway.getunbound.ai
```

The script prints progress messages to stdout. Check the exit code:

- **Exit code 0**: Setup succeeded. The script has persisted the key to the user's shell RC file and configured `~/.claude/anthropic_key.sh` + `apiKeyHelper` in `~/.claude/settings.json`.
- **Non-zero exit code**: Setup failed. Show the script's output to the user and offer to retry.

**Security property:** The API key never appears in chat, bash commands, or terminal output. It exists only inside the setup script's process memory, the RC file on disk, and `~/.claude/anthropic_key.sh`.

---

## Step 3 — Verify connectivity

Run:

```bash
curl -fsSL -o /dev/null -w "%{http_code}" \
  -H "Authorization: Bearer $UNBOUND_API_KEY" \
  https://api.getunbound.ai/v1/models
```

Interpret the result:

| HTTP code | Meaning | Action |
|---|---|---|
| `200` | Key is valid and API is reachable | Proceed to Step 4 |
| `401` | Key is invalid or expired | Tell the user the key was rejected. Offer to retry from Step 2. |
| `403` | Key exists but lacks Claude Code scope | Tell the user to create a new key with Claude Code scope. |
| anything else / curl error | Network issue or API unreachable | Warn the user. The plugin will **fail open** (allow all) until connectivity is restored. Still proceed to Step 4. |

---

## Step 4 — Show success summary

Print a summary like this (adapt `<RC_FILE>` to the actual RC file for the user's shell):

```
UNBOUND_API_KEY saved to <RC_FILE>
API connectivity verified (HTTP 200)
Unbound plugin is active

IMPORTANT: You must restart this Claude Code session for hooks to use the new key.
  Claude Code hooks inherit the environment from the parent shell, so the key
  must be loaded BEFORE starting Claude.

  Run this single command to reload your shell config and restart Claude Code:

    source <RC_FILE> && claude

  (This sources the key into your terminal, then launches a new Claude session.)

What happens next:
  - Every tool use (Bash, Edit, Write...) is checked against your Unbound policies
  - User prompts are scanned for DLP / NSFW / jailbreak guardrails
  - Session data streams to your Unbound dashboard for analytics

To view your policies and guardrails: https://app.getunbound.ai
```

On Windows, replace the restart instruction with:

```
IMPORTANT: Close and reopen your terminal, then run `claude` again.
  The UNBOUND_API_KEY environment variable was set via setx and
  will only be available in new terminal sessions.
```

If connectivity failed, end with:

```
API unreachable — plugin installed but running in fail-open mode.
    All tool uses will be allowed until connectivity is restored.
    Check your API key and network, then run /unbound:setup again.
```

---

## Re-setup guard

If the user chose **Reconfigure** in Step 1, confirm before overwriting:

> "This will replace your existing Unbound API key. Continue? (yes/no)"

Only proceed if they confirm. If they say no, exit gracefully.

---

## Error handling

- If any shell command fails, show the exact error and suggest a manual fix.
- Never exit silently — always tell the user what happened and what to do next.
- If the setup script fails, show the output and offer to retry.
