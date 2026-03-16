# Enterprise MDM Deployment

This directory contains the tools for enforcing the Unbound plugin across a fleet of devices.

## What it does

The MDM setup script (`mdm-setup.py`) automates the full enterprise deployment in a single command:

1. Fetches a per-device API key from the Unbound MDM endpoint using the device serial number
2. Sets `UNBOUND_CLAUDE_API_KEY` for all users on the machine
3. Deploys `managed-settings.json` so Claude Code auto-installs the plugin and users cannot disable it

## Quick start

```bash
sudo python3 mdm-setup.py --url https://api.getunbound.ai --api_key <MDM_AUTH_KEY>
```

The script auto-detects the device serial number, fetches the API key, and configures everything.

## Requirements

- macOS and Linux (Windows support planned)
- Root/admin privileges (`sudo`)
- An MDM auth key from your Unbound dashboard (Settings → MDM)
- Python 3 (pre-installed on macOS)

## Usage

### Setup

```bash
# Basic — auto-detect serial, fetch key, deploy settings
sudo python3 mdm-setup.py --url https://api.getunbound.ai --api_key <MDM_AUTH_KEY>

# With app name (for multi-team setups)
sudo python3 mdm-setup.py --url https://api.getunbound.ai --api_key <MDM_AUTH_KEY> --app_name "engineering"

# Debug mode
sudo python3 mdm-setup.py --url https://api.getunbound.ai --api_key <MDM_AUTH_KEY> --debug
```

### Uninstall

```bash
sudo python3 mdm-setup.py --clear
```

This removes `managed-settings.json` and `UNBOUND_CLAUDE_API_KEY` from all users.

## What the script does

### 1. Gets device serial number

Uses `system_profiler SPHardwareDataType` to get the Mac serial number automatically.

### 2. Fetches API key from MDM endpoint

```
GET {base_url}/api/v1/automations/mdm/get_application_api_key/
    ?serial_number=<SERIAL>&app_type=claude-code[&app_name=<NAME>]
Authorization: Bearer <MDM_AUTH_KEY>
```

Returns:
```json
{
  "api_key": "...",
  "email": "user@example.com",
  "first_name": "...",
  "last_name": "..."
}
```

### 3. Sets environment variable for all users

Writes `export UNBOUND_CLAUDE_API_KEY="<key>"` to both `~/.zprofile` and `~/.bash_profile` for every real user account on the machine. Sets correct file ownership via `chown`.

### 4. Deploys managed-settings.json

Copies `managed-settings.json` to the system-wide Claude Code path:

| OS | Path |
|---|---|
| macOS | `/Library/Application Support/ClaudeCode/managed-settings.json` |
| Linux | `/etc/claude-code/managed-settings.json` |
| Windows | `C:\Program Files\ClaudeCode\managed-settings.json` |

When `enabledPlugins` is set in managed settings, Claude Code installs the listed plugins automatically and **users cannot disable them**.

### 5. Verifies connectivity

Checks that the API key works by hitting `https://api.getunbound.ai/v1/models`. If unreachable, the plugin runs in fail-open mode.

## Jamf / MDM integration

Add `mdm-setup.py` as a script in your MDM tool. Example Jamf policy:

```bash
#!/bin/bash
python3 /path/to/mdm-setup.py --url https://api.getunbound.ai --api_key "$MDM_AUTH_KEY"
```

Pass the MDM auth key as a Jamf script parameter or via a secure configuration profile.

## Manual alternative

If you prefer not to use the automated script:

1. Deploy `managed-settings.json.tmpl` to the system path (see table above) as `managed-settings.json`
2. Set `UNBOUND_CLAUDE_API_KEY` for each user via a login script or MDM configuration profile

## Verify

On an enrolled machine, open Claude Code and run `/unbound-claude-code:setup`. It should detect the existing key and confirm connectivity.
