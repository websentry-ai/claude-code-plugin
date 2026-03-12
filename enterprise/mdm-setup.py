#!/usr/bin/env python3

import os
import sys
import platform
import subprocess
import json
import pwd
from pathlib import Path
from typing import Tuple, List

DEBUG = False


def debug_print(message: str) -> None:
    """Print message only if DEBUG mode is enabled."""
    if DEBUG:
        print(f"[DEBUG] {message}")


def get_managed_settings_dir() -> Path:
    """Get the system-wide managed settings directory based on OS."""
    system = platform.system().lower()

    if system == "darwin":
        return Path("/Library/Application Support/ClaudeCode")
    elif system == "linux":
        return Path("/etc/claude-code")
    elif system == "windows":
        return Path("C:/Program Files/ClaudeCode")
    else:
        raise OSError(f"Unsupported operating system: {system}")


def check_admin_privileges() -> bool:
    """Check if the script is running with admin/root privileges."""
    system = platform.system().lower()

    try:
        if system in ["darwin", "linux"]:
            return os.geteuid() == 0
        elif system == "windows":
            import ctypes
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        return False
    except Exception as e:
        debug_print(f"Failed to check privileges: {e}")
        return False


def get_mac_serial_number() -> str:
    """Get the Mac serial number using system_profiler."""
    try:
        result = subprocess.run(
            ["system_profiler", "SPHardwareDataType"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode != 0:
            return None

        for line in result.stdout.split('\n'):
            if 'Serial Number' in line:
                parts = line.split(': ')
                if len(parts) >= 2:
                    return parts[1].strip()
        return None
    except Exception as e:
        debug_print(f"Failed to get serial number: {e}")
        return None


def get_shell_rc_file() -> Path:
    system = platform.system().lower()
    shell = os.environ.get("SHELL", "").lower()

    if system == "darwin":
        return Path.home() / ".zprofile" if "zsh" in shell else Path.home() / ".bash_profile"
    elif system == "linux":
        return Path.home() / ".zshrc" if "zsh" in shell else Path.home() / ".bashrc"
    elif system == "windows":
        return None
    else:
        raise OSError(f"Unsupported operating system: {system}")


def check_env_var_exists(rc_file: Path, var_name: str, value: str) -> bool:
    if not rc_file.exists():
        return False
    try:
        with open(rc_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        export_line = f'export {var_name}="{value}"'
        return any(l.rstrip() == export_line for l in lines)
    except Exception:
        return False


def append_to_file(file_path: Path, line: str, var_name: str = None) -> bool:
    try:
        file_path.touch(exist_ok=True)

        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        if var_name:
            export_prefix = f"export {var_name}="
            lines = [l for l in lines if not l.strip().startswith(export_prefix)]

        if line + "\n" not in lines and line not in [l.rstrip() for l in lines]:
            lines.append(f"{line}\n")

            with open(file_path, "w", encoding="utf-8") as f:
                f.writelines(lines)
            return True

        if var_name:
            with open(file_path, "w", encoding="utf-8") as f:
                f.writelines(lines)
            return True

        return True
    except Exception as e:
        print(f"Failed to modify {file_path}: {e}")
        return False


def set_env_var_windows(var_name: str, value: str) -> bool:
    try:
        subprocess.run(["setx", var_name, value], check=True, capture_output=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"Failed to set {var_name} on Windows: {e}")
        return False


def get_all_user_homes() -> List[Tuple[str, Path]]:
    """Get all real user home directories on the system (excluding system accounts)."""
    user_homes = []

    try:
        for user in pwd.getpwall():
            uid = user.pw_uid
            username = user.pw_name
            home_dir = Path(user.pw_dir)

            # Filter out system accounts (UID < 500 on macOS)
            if uid >= 500 and home_dir.exists() and home_dir.is_dir():
                if str(home_dir).startswith('/Users/') and username not in ['Shared', 'Guest']:
                    user_homes.append((username, home_dir))
                    debug_print(f"Found user: {username} -> {home_dir}")

        return user_homes
    except Exception as e:
        debug_print(f"Error enumerating users: {e}")
        return []


def set_env_var_system_wide_macos(var_name: str, value: str) -> Tuple[bool, bool]:
    """Set environment variable for all users on macOS by updating each user's shell rc file.
    Returns: (success, changed)"""
    try:
        user_homes = get_all_user_homes()

        if not user_homes:
            print("No user home directories found")
            return False, False

        success_count = 0
        changed_count = 0
        export_line = f'export {var_name}="{value}"'

        for username, home_dir in user_homes:
            debug_print(f"Setting env var for user: {username}")

            try:
                user_info = pwd.getpwnam(username)
                uid = user_info.pw_uid
                gid = user_info.pw_gid
            except KeyError:
                debug_print(f"Could not get UID/GID for {username}")
                continue

            rc_files = [
                home_dir / ".zprofile",
                home_dir / ".bash_profile"
            ]
            debug_print(f"Writing to shell files: {[str(f) for f in rc_files]}")

            user_success = False
            user_changed = False
            for rc_file in rc_files:
                try:
                    exists_already = check_env_var_exists(rc_file, var_name, value)
                    if append_to_file(rc_file, export_line, var_name):
                        os.chown(rc_file, uid, gid)
                        debug_print(f"Updated {rc_file} for {username}")
                        user_success = True
                        if not exists_already:
                            user_changed = True
                except Exception as e:
                    debug_print(f"Failed to update {rc_file}: {e}")

            if user_success:
                success_count += 1
            if user_changed:
                changed_count += 1

        if success_count > 0:
            print(f"   Set for {success_count} user(s)")
            return True, changed_count > 0
        else:
            print("Failed to set environment variable for any users")
            return False, False

    except Exception as e:
        print(f"Failed to set system-wide environment variable: {e}")
        return False, False


def remove_env_var_from_user(username: str, home_dir: Path, var_name: str) -> bool:
    """Remove environment variable from a user's shell rc files."""
    try:
        rc_files = [
            home_dir / ".zprofile",
            home_dir / ".bash_profile"
        ]

        success = False
        export_prefix = f"export {var_name}="

        for rc_file in rc_files:
            if not rc_file.exists():
                continue

            try:
                with open(rc_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()

                new_lines = [l for l in lines if not l.strip().startswith(export_prefix)]

                if len(new_lines) < len(lines):
                    with open(rc_file, 'w', encoding='utf-8') as f:
                        f.writelines(new_lines)

                    user_info = pwd.getpwnam(username)
                    os.chown(rc_file, user_info.pw_uid, user_info.pw_gid)

                    debug_print(f"Removed {var_name} from {rc_file}")
                    success = True
            except Exception as e:
                debug_print(f"Failed to update {rc_file}: {e}")

        return success
    except Exception as e:
        debug_print(f"Error removing env var for {username}: {e}")
        return False


def set_env_var_unix(var_name: str, value: str) -> Tuple[bool, bool]:
    if platform.system().lower() == "darwin" and os.geteuid() == 0:
        return set_env_var_system_wide_macos(var_name, value)

    rc_file = get_shell_rc_file()
    if rc_file is None:
        return False, False

    exists_already = check_env_var_exists(rc_file, var_name, value)
    export_line = f'export {var_name}="{value}"'
    success = append_to_file(rc_file, export_line, var_name)
    return success, success and not exists_already


def set_env_var(var_name: str, value: str) -> Tuple[bool, bool, str]:
    system = platform.system().lower()

    if system == "windows":
        success = set_env_var_windows(var_name, value)
        if success:
            debug_print(f"Environment variable {var_name} set on Windows")
        msg = "Set for new terminals" if success else "Failed"
        return (success, True, msg)
    elif system in ["darwin", "linux"]:
        success, changed = set_env_var_unix(var_name, value)
        if success:
            if system == "darwin" and os.geteuid() == 0:
                debug_print(f"Environment variable {var_name} set system-wide")
                return True, changed, "Set system-wide for all users"
            else:
                debug_print(f"Environment variable {var_name} added to shell rc file")
                shell_name = "zsh" if "zsh" in os.environ.get("SHELL", "") else "bash"
                return True, changed, f"Run 'source ~/.{shell_name}rc' or restart terminal"
        return False, False, "Failed"
    else:
        return False, False, f"Unsupported OS: {system}"


def deploy_managed_settings() -> bool:
    """Deploy managed-settings.json to the system-wide Claude Code path."""
    settings_dir = get_managed_settings_dir()
    settings_file = settings_dir / "managed-settings.json"

    managed_settings = {
        "enabledPlugins": [
            "websentry-ai/claude-code-plugin/unbound-claude-code"
        ]
    }

    try:
        settings_dir.mkdir(parents=True, exist_ok=True)
        with open(settings_file, 'w', encoding='utf-8') as f:
            json.dump(managed_settings, f, indent=2)
            f.write('\n')
        debug_print(f"Deployed managed-settings.json to {settings_file}")
        return True
    except Exception as e:
        print(f"Failed to deploy managed-settings.json: {e}")
        return False


def remove_managed_settings() -> bool:
    """Remove managed-settings.json from the system-wide Claude Code path."""
    settings_dir = get_managed_settings_dir()
    settings_file = settings_dir / "managed-settings.json"

    if not settings_file.exists():
        print(f"   {settings_file} does not exist")
        return True

    try:
        settings_file.unlink()
        print(f"   Removed {settings_file}")
        return True
    except Exception as e:
        print(f"Failed to remove {settings_file}: {e}")
        return False


def fetch_api_key_from_mdm(base_url: str, app_name: str, auth_api_key: str, serial_number: str) -> str:
    """Fetch API key from MDM endpoint."""
    params = f"serial_number={serial_number}&app_type=claude-code"
    if app_name:
        params = f"app_name={app_name}&{params}"
    url = f"{base_url.rstrip('/')}/api/v1/automations/mdm/get_application_api_key/?{params}"

    debug_print(f"Fetching API key from: {url}")

    try:
        result = subprocess.run(
            ["curl", "-fsSL", "-w", "\n%{http_code}", "-H", f"Authorization: Bearer {auth_api_key}", url],
            capture_output=True,
            text=True,
            timeout=30
        )

        output_lines = result.stdout.strip().split('\n')
        if len(output_lines) < 2:
            print("Invalid response from server")
            return None

        http_code = output_lines[-1]
        response_body = '\n'.join(output_lines[:-1])

        debug_print(f"HTTP status: {http_code}")
        debug_print(f"Response: {response_body}")

        if http_code != "200":
            print(f"API request failed with status {http_code}")
            return None

        try:
            data = json.loads(response_body)
            api_key = data.get("api_key")
            if not api_key:
                print("No api_key in response")
                return None
            user_email = data.get("email")
            first_name = data.get("first_name")
            last_name = data.get("last_name")
            print(f"   User email: {user_email}")
            print(f"   Name: {first_name} {last_name}")
            return api_key
        except json.JSONDecodeError:
            print("Invalid JSON response from server")
            return None

    except subprocess.TimeoutExpired:
        print("Request timed out")
        return None
    except Exception as e:
        debug_print(f"Request failed: {e}")
        print("Failed to fetch API key")
        return None


def clear_setup():
    """Remove managed settings and environment variables set by the setup script."""
    print("=" * 60)
    print("Unbound Claude Code - Clearing MDM Setup")
    print("=" * 60)

    if not check_admin_privileges():
        print("This script requires administrator/root privileges")
        print("   Please run with: sudo python3 mdm-setup.py --clear")
        return

    # Remove managed-settings.json
    print("\nRemoving managed settings...")
    remove_managed_settings()

    # Remove environment variable from all users
    print("\nRemoving environment variables...")
    user_homes = get_all_user_homes()

    if not user_homes:
        print("   No user home directories found")
    else:
        removed_count = 0
        for username, home_dir in user_homes:
            if remove_env_var_from_user(username, home_dir, "UNBOUND_CLAUDE_API_KEY"):
                removed_count += 1

        if removed_count > 0:
            print(f"   Removed environment variable from {removed_count} user(s)")
        else:
            print("   No environment variables found to remove")

    print("\n" + "=" * 60)
    print("Clear Complete!")
    print("=" * 60)
    print("\nNote: Restart your terminal or log out/in for env var changes to take effect")


def main():
    global DEBUG

    clear_mode = "--clear" in sys.argv

    debug_mode = "--debug" in sys.argv
    if debug_mode:
        DEBUG = True
        debug_print("Debug mode enabled")

    if clear_mode:
        clear_setup()
        return

    print("=" * 60)
    print("Unbound Claude Code - MDM Setup")
    print("=" * 60)

    # Check platform
    if platform.system().lower() != "darwin":
        print("This script only supports macOS")
        return

    # Check admin privileges
    if not check_admin_privileges():
        print("This script requires administrator/root privileges")
        print("   Please run with: sudo python3 mdm-setup.py --url <base_url> --api_key <api_key>")
        return

    # Parse arguments
    base_url = None
    app_name = None
    auth_api_key = None

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--url" and i + 1 < len(args):
            base_url = args[i + 1]
            i += 2
        elif args[i] == "--app_name" and i + 1 < len(args):
            app_name = args[i + 1]
            i += 2
        elif args[i] == "--api_key" and i + 1 < len(args):
            auth_api_key = args[i + 1]
            i += 2
        elif args[i] == "--debug":
            i += 1
        else:
            i += 1

    if not base_url or not auth_api_key:
        print("\nMissing required arguments")
        print("Usage: sudo python3 mdm-setup.py --url <base_url> --api_key <api_key> [--app_name <app_name>] [--debug]")
        print("   Or: sudo python3 mdm-setup.py --clear [--debug]")
        return

    # Get serial number
    print("\nGetting device serial number...")
    serial_number = get_mac_serial_number()
    if not serial_number:
        print("Failed to get device serial number")
        return
    debug_print(f"Serial number: {serial_number}")
    print("   Serial number retrieved")

    # Fetch API key from MDM endpoint
    print("\nFetching API key from MDM...")
    api_key = fetch_api_key_from_mdm(base_url, app_name, auth_api_key, serial_number)
    if not api_key:
        return
    print("   API key received")

    # Set environment variable for all users
    print("\nSetting UNBOUND_CLAUDE_API_KEY...")
    success, env_changed, message = set_env_var("UNBOUND_CLAUDE_API_KEY", api_key)
    if not success:
        print(f"Failed to set environment variable: {message}")
        return
    print(f"   Environment variable set ({message})")

    # Deploy managed-settings.json
    print("\nDeploying managed-settings.json...")
    if not deploy_managed_settings():
        print("Failed to deploy managed settings")
        return
    settings_dir = get_managed_settings_dir()
    print(f"   Deployed to {settings_dir / 'managed-settings.json'}")

    # Verify connectivity
    print("\nVerifying API connectivity...")
    try:
        result = subprocess.run(
            ["curl", "-fsSL", "-o", "/dev/null", "-w", "%{http_code}",
             "-H", f"Authorization: Bearer {api_key}",
             "https://api.getunbound.ai/v1/models"],
            capture_output=True,
            text=True,
            timeout=10
        )
        http_code = result.stdout.strip()
        if http_code == "200":
            print("   API connectivity verified (HTTP 200)")
        else:
            print(f"   API returned HTTP {http_code} — plugin will run in fail-open mode")
    except Exception:
        print("   Could not verify connectivity — plugin will run in fail-open mode")

    print("\n" + "=" * 60)
    print("Setup Complete!")
    print("=" * 60)
    print("\nNote: Users must restart their terminal for the environment variable to take effect.")
    print("The Unbound plugin will be automatically enforced for all Claude Code sessions.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nSetup cancelled.")
    except Exception as e:
        print(f"\nError: {e}")
        exit(1)
