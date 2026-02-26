---
name: setup
description: Configure Unbound AI credentials and verify connectivity for the Claude Code plugin. Use when setting up for the first time, reconfiguring with a new API key, or diagnosing connectivity issues.
user-invocable: true
---

# Unbound Setup

You are helping the user configure the Unbound AI plugin for Claude Code. Follow these steps precisely and in order. Never display a full API key back to the user after they provide it — always mask it.

---

## Step 1 — Check current state

Run this command to check whether the API key is already configured:

```bash
echo "${UNBOUND_CLAUDE_API_KEY:0:8}..."
```

**If the variable is unset or empty**, proceed to Step 2.

**If the variable is already set**, tell the user the key is configured (show only the first 8 characters + `...`). Ask them to choose:
1. **Verify** — test connectivity with the existing key (jump to Step 4)
2. **Reconfigure** — replace with a new key (proceed to Step 2)
3. **Exit** — nothing to do

---

## Step 2 — Get an API key

Tell the user:

> To connect the plugin you need an Unbound API key.
> Get one at **https://app.getunbound.ai → Settings → API Keys → Create key**.
> Select scope: **Claude Code**.

Ask them to paste their API key. Accept it as plain text input. Do not echo it back in full.

---

## Step 3 — Persist the API key

Detect the correct shell rc file by running:

```bash
echo "$SHELL" && uname
```

Use this mapping:

| OS | Shell | File |
|---|---|---|
| macOS | zsh | `~/.zprofile` |
| macOS | bash | `~/.bash_profile` |
| Linux | zsh | `~/.zshrc` |
| Linux | bash | `~/.bashrc` |
| Windows | any | use `setx` (see below) |

**macOS / Linux** — write the export line to the rc file:

```bash
# Remove any existing UNBOUND_CLAUDE_API_KEY line first
sed -i'' -e '/^export UNBOUND_CLAUDE_API_KEY=/d' <RC_FILE>
# Append new value
echo 'export UNBOUND_CLAUDE_API_KEY="<KEY>"' >> <RC_FILE>
```

Replace `<RC_FILE>` with the detected path and `<KEY>` with the user's key.

**Windows** — run:

```powershell
setx UNBOUND_CLAUDE_API_KEY "<KEY>"
```

After writing, export the key into the current shell session so Step 4 works without a restart:

```bash
export UNBOUND_CLAUDE_API_KEY="<KEY>"
```

---

## Step 4 — Verify connectivity

Run:

```bash
curl -fsSL -o /dev/null -w "%{http_code}" \
  -H "Authorization: Bearer $UNBOUND_CLAUDE_API_KEY" \
  https://api.getunbound.ai/v1/models
```

Interpret the result:

| HTTP code | Meaning | Action |
|---|---|---|
| `200` | Key is valid and API is reachable | Proceed to Step 5 |
| `401` | Key is invalid or expired | Tell the user the key was rejected. Offer to retry from Step 2. |
| `403` | Key exists but lacks Claude Code scope | Tell the user to create a new key with Claude Code scope. |
| anything else / curl error | Network issue or API unreachable | Warn the user. The plugin will **fail open** (allow all) until connectivity is restored. Still proceed to Step 5. |

---

## Step 5 — Show success summary

Print a summary like this (adapt `<RC_FILE>` to the actual shell config path from Step 3):

```
✓ UNBOUND_CLAUDE_API_KEY saved to <RC_FILE>
✓ API connectivity verified (HTTP 200)
✓ Unbound plugin is active

⚠ IMPORTANT: You must restart this Claude Code session for hooks to use the new key.
  Claude Code hooks inherit the environment from the parent shell, so the key
  must be loaded BEFORE starting Claude.

  Run this single command to reload your shell config and restart Claude Code:

    source <RC_FILE> && claude

  (This sources the key into your terminal, then launches a new Claude session.)

What happens next:
  • Every tool use (Bash, Edit, Write…) is checked against your Unbound policies
  • User prompts are scanned for DLP / NSFW / jailbreak guardrails
  • Session data streams to your Unbound dashboard for analytics

To view your policies and guardrails: https://app.getunbound.ai
```

If connectivity failed, end with:

```
⚠️  API unreachable — plugin installed but running in fail-open mode.
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
- If the rc file is not writable, tell the user to run the export manually and add it to their shell config.
