# Enterprise MDM Deployment

This directory contains the managed-settings template for enforcing the Unbound plugin across a fleet.

## What it does

`managed-settings.json` is read by Claude Code from a system-wide path that regular users cannot modify:

| OS | Path |
|---|---|
| macOS | `/Library/Application Support/ClaudeCode/managed-settings.json` |
| Linux | `/etc/claude-code/managed-settings.json` |
| Windows | `C:\Program Files\ClaudeCode\managed-settings.json` |

When `enabledPlugins` is set in managed settings, Claude Code installs the listed plugins automatically and **users cannot disable them**.

## Deployment steps

### 1. Deploy managed-settings.json

Copy `managed-settings.json.tmpl` to the system path for your target OS and rename it to `managed-settings.json`. No substitution needed — the file is valid JSON as-is.

macOS (run as root or via MDM):

```bash
mkdir -p "/Library/Application Support/ClaudeCode"
cp managed-settings.json.tmpl "/Library/Application Support/ClaudeCode/managed-settings.json"
```

Linux (run as root):

```bash
mkdir -p /etc/claude-code
cp managed-settings.json.tmpl /etc/claude-code/managed-settings.json
```

### 2. Set UNBOUND_CLAUDE_API_KEY for each user

The plugin reads `UNBOUND_CLAUDE_API_KEY` from the environment. This must be set per user (not in managed-settings.json, which does not support env vars).

**Option A — MDM-issued device API key (recommended)**

Use the Unbound MDM provisioning endpoint to fetch a per-device key at enrollment time:

```
GET https://api.getunbound.ai/api/v1/automations/mdm/get_application_api_key/
    ?serial_number=<DEVICE_SERIAL>
    &app_type=claude-code
```

Requires an Unbound MDM auth key. See your Unbound dashboard under Settings → MDM.

**Option B — Shared fleet key**

Set a single key for all users via a login script or MDM configuration profile:

```bash
# /etc/profile.d/unbound.sh  (Linux)
export UNBOUND_CLAUDE_API_KEY="<YOUR_KEY>"
```

macOS: deploy a Configuration Profile (`.mobileconfig`) that sets the env var, or add the export to `/etc/zshenv`.

### 3. Verify

On an enrolled machine, open Claude Code and run `/unbound:setup`. It should report:

```
✓ UNBOUND_CLAUDE_API_KEY saved ...
✓ API connectivity verified (HTTP 200)
✓ Unbound plugin is active
```
