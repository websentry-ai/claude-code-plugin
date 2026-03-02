# Unbound Claude Code Plugin

Security, governance, and analytics for [Claude Code](https://claude.ai/code) — powered by [Unbound AI](https://getunbound.ai).

## What it does

This plugin connects Claude Code to the Unbound AI platform, enabling:

- **Command policy enforcement** — Block or warn on dangerous tool invocations (PreToolUse)
- **Guardrail checks** — DLP, NSFW, and jailbreak detection on user prompts (UserPromptSubmit)
- **Analytics streaming** — Send tool usage and session data to the Unbound dashboard (PostToolUse, Stop)

## Project structure

```
.claude-plugin/
  plugin.json          # Plugin manifest
  marketplace.json     # Marketplace catalog
hooks/
  hooks.json           # Hook event configuration
skills/
  setup/
    SKILL.md           # /unbound:setup skill (placeholder)
scripts/
  hook-handler.py      # Central hook handler
```

## Installation

> Full installation instructions will be added in a later phase.

### From marketplace

```bash
claude plugin install unbound@unbound-marketplace
```

### Local development

```bash
claude plugin install --path /path/to/claude-code-plugin
```

## License

[MIT](LICENSE)
