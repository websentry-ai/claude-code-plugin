#!/usr/bin/env python3
"""Unbound AI hook handler for Claude Code.

Phase 1: No-op — reads stdin and exits 0 with no output.
"""

import sys


def main():
    # Read and discard stdin to avoid broken-pipe errors
    sys.stdin.read()
    # Exit cleanly with no output — allows all actions to proceed
    sys.exit(0)


if __name__ == "__main__":
    main()
