# Unbound Claude Code Plugin — Development Plan

> **Author:** Sumit Badsara | **Date:** February 24, 2026 | **Status:** Draft

---

## Development Phases

> Each phase = 1 PR. Hooks are implemented incrementally, one PR per hook, each with its own testing plan and unit tests.

---

### Phase 1: Plugin Skeleton (PR #1)

**Goal:** Bare-minimum manifest and plugin breadcrumbs. Plugin installs but does nothing.

| Task | Description | Verification |
|------|-------------|--------------|
| 1.1 | Create `websentry-ai/claude-code-plugin` repo (public) | Repo exists on GitHub |
| 1.2 | Write `.claude-plugin/plugin.json` (name, version, description, component paths) | Valid JSON |
| 1.3 | Write `.claude-plugin/marketplace.json` (self-referencing `source: "."`) | Valid JSON |
| 1.4 | Write `hooks/hooks.json` (all 4 events mapped to `hook-handler.py`) | Valid JSON |
| 1.5 | Write `skills/setup/SKILL.md` (placeholder — description only, no real logic) | File exists |
| 1.6 | Write `scripts/hook-handler.py` (no-op: reads stdin, exits 0, no output) | Script runs |
| 1.7 | Write `README.md` (basic structure) | File exists |
| 1.8 | Write `LICENSE` (MIT) | File exists |
| 1.9 | Run `claude plugin validate .` | Passes |
| 1.10 | Test local install via marketplace | Plugin appears in installed list |

**Files created:**
```
.claude-plugin/plugin.json
.claude-plugin/marketplace.json
hooks/hooks.json
skills/setup/SKILL.md
scripts/hook-handler.py
README.md
LICENSE
```

---

### Phase 2: Hooks with Default Allow (PR #2)

**Goal:** All 4 hooks fire and return "allow" by default. Debug logging captures exact stdin JSON from Claude Code. This phase answers all open validation questions.

| Task | Description | Verification |
|------|-------------|--------------|
| 2.1 | Update `hook-handler.py` to log stdin to `~/.unbound/logs/debug.jsonl` | Log file populates on every event |
| 2.2 | PreToolUse: return `{ hookSpecificOutput: { permissionDecision: "allow" } }` | Tool executes normally |
| 2.3 | UserPromptSubmit: return empty (allow) | Prompt accepted normally |
| 2.4 | PostToolUse: return empty (async, no decision) | No blocking behavior |
| 2.5 | Stop: return empty (async, no decision) | No blocking behavior |
| 2.6 | Document exact stdin JSON per event from debug logs | Captured in TDD |
| 2.7 | Test: does `source: "."` marketplace pattern work? | Document result |
| 2.8 | Test: what happens on hook timeout (sleep 15s)? | Document: fail open or closed |
| 2.9 | Test: can UserPromptSubmit return `{ decision: "block" }`? | Document result |
| 2.10 | Test: does `enabledPlugins` in managed-settings prevent disabling? | Document result |
| 2.11 | Test: dual-install with managed hooks — do events fire twice? | Document result |

**Open questions answered by this phase:** stdin format, blocking behavior, timeout handling, marketplace pattern, dual-install behavior

---

### Phase 3: PreToolUse Hook Implementation (PR #3)

**Goal:** PreToolUse calls Unbound API for command policy enforcement.

| Task | Description | Verification |
|------|-------------|--------------|
| 3.1 | Add git submodule `websentry-ai/setup` at `scripts/lib/` | Submodule clones correctly |
| 3.2 | Audit existing handler in submodule for importability | Document structure, identify `main()` entry point |
| 3.3 | Refactor submodule handler if needed (add `main()`, backward-compatible) | Existing managed hooks still work |
| 3.4 | Implement PreToolUse in `hook-handler.py`: stdin → API transform → `/v1/hooks/pretool` with `event_name: "pretool"` → response → `hookSpecificOutput` | Compiles, no errors |
| 3.5 | Add env var reading: `UNBOUND_DOMAIN`, `UNBOUND_API_KEY` | Handler reads env correctly |
| 3.6 | Add error handling: timeout → allow, API error → allow, missing env → allow | All error paths exit 0 |
| 3.7 | Unit tests: stdin → API payload transformation | Tests pass |
| 3.8 | Unit tests: API response → Claude Code stdout transformation | Tests pass |
| 3.9 | Unit tests: error paths (timeout, 500, missing env, malformed stdin) | Tests pass |

**Testing plan:**
- Create BLOCK policy in dashboard → run matching `rm -rf /` command → **blocked**
- Create WARN policy → run matching command → **user prompted (ask)**
- Run non-matching command → **allowed**
- Disconnect network → **allowed (fail open)**
- Remove `UNBOUND_API_KEY` env var → **allowed (fail open)**
- Send malformed stdin → **allowed (fail open)**

**Key transformation:**
```
Claude Code stdin:                    Unbound API request:
{ session_id, tool_name,       →     { conversation_id, event_name: "pretool",
  tool_input: { command } }            pre_tool_use_data: { tool_name, command },
                                       messages, unbound_app_label: "claude-code" }

Unbound API response:                Claude Code stdout:
{ decision: "deny",           →     { hookSpecificOutput:
  reason: "Blocked" }                  { permissionDecision: "deny",
                                        permissionDecisionReason: "Blocked" } }
```

---

### Phase 4: UserPromptSubmit Hook Implementation (PR #4)

**Goal:** UserPromptSubmit calls Unbound API for guardrail checks (DLP, NSFW, Jailbreak).

| Task | Description | Verification |
|------|-------------|--------------|
| 4.1 | Implement UserPromptSubmit in `hook-handler.py`: stdin → `/v1/hooks/pretool` with `event_name: "user_prompt"` | Compiles, no errors |
| 4.2 | Map `prompt` field → `messages[0].content` in API request | Correct payload |
| 4.3 | Map API `deny` → Claude Code `{ decision: "block" }` | Correct output format |
| 4.4 | Unit tests: stdin → API payload transformation | Tests pass |
| 4.5 | Unit tests: API response → Claude Code stdout | Tests pass |
| 4.6 | Unit tests: error paths | Tests pass |

**Testing plan:**
- Enable DLP guardrail in dashboard → type prompt with SSN → **blocked**
- Enable NSFW guardrail → type inappropriate prompt → **blocked**
- Type clean prompt → **allowed**
- Disconnect network → **allowed (fail open)**

**Key transformation:**
```
Claude Code stdin:                    Unbound API request:
{ session_id,                  →     { conversation_id, event_name: "user_prompt",
  prompt: "text with SSN" }            pre_tool_use_data: { tool_name: "", command: "" },
                                       messages: [{ role: "user", content: "text" }],
                                       unbound_app_label: "claude-code" }

Unbound API response:                Claude Code stdout:
{ decision: "deny",           →     { decision: "block",
  reason: "PII detected" }            reason: "PII detected" }
```

---

### Phase 5: PostToolUse + Stop Hooks Implementation (PR #5)

**Goal:** Async logging hooks send conversation data to Unbound for analytics.

| Task | Description | Verification |
|------|-------------|--------------|
| 5.1 | Implement PostToolUse: stdin → `/v1/hooks/claude` (async fire-and-forget) | Events logged |
| 5.2 | Implement Stop: stdin → `/v1/hooks/claude` (async fire-and-forget) | Session logged |
| 5.3 | Build `messages` array from stdin fields (heaviest transformation) | Correct format |
| 5.4 | Add offline fallback: write to `~/.unbound/logs/offline-events.jsonl` if API unreachable | JSONL file populates |
| 5.5 | Unit tests: PostToolUse stdin → API payload | Tests pass |
| 5.6 | Unit tests: Stop stdin → API payload | Tests pass |
| 5.7 | Unit tests: offline fallback | Tests pass |

**Testing plan:**
- Run any tool → check Unbound dashboard → **event appears in analytics**
- End Claude Code session → check dashboard → **session logged**
- Disconnect network → run tools → check `~/.unbound/logs/offline-events.jsonl` → **events captured locally**
- Reconnect → verify no blocking occurred during offline period

**Key transformation (PostToolUse):**
```
Claude Code stdin:                    Unbound API request:
{ session_id, tool_name,       →     { conversation_id,
  tool_input: { command },             messages: [
  tool_response: { stdout } }            { role: "user", content: "..." },
                                          { role: "assistant", tool_use: [{
                                              tool_name, tool_input, tool_response }] }
                                        ],
                                        permission_mode: "default" }
```

---

### Phase 6: `/unbound:setup` Skill + Enterprise + Docs (PR #6)

**Goal:** Self-serve onboarding flow, enterprise MDM template, and documentation updates.

| Task | Description | Verification |
|------|-------------|--------------|
| 6.1 | Write full `skills/setup/SKILL.md` (guided credential config) | `/unbound:setup` appears in `/` menu |
| 6.2 | Test fresh install flow (no env vars → full setup → hooks work) | Completes in under 5 min |
| 6.3 | Test re-setup flow (existing config → prompt before overwrite) | No accidental overwrite |
| 6.4 | Test failed connectivity (wrong domain/key → actionable error) | Clear error message |
| 6.5 | Create `managed-settings.json.tmpl` for enterprise MDM | Template is correct JSON |
| 6.6 | Update `unbound-fe/.../claude-code.json` with Method 3: Plugin | Dashboard shows new method |
| 6.7 | Update `docs/integrations/claude-code-integration.mdx` | Docs site renders correctly |
| 6.8 | Finalize `README.md` (self-serve + enterprise install instructions) | New developer can follow |

**Files modified (in other repos):**
- `unbound-fe/components/ai-gateway-applications/setup-instructions/claude-code.json`
- `docs/integrations/claude-code-integration.mdx`

---

### Phase 7: Release (PR #7 — version bump + tag)

**Goal:** v1.0.0 tagged, marketplace install verified, all validation checks pass.

| Task | Description | Verification |
|------|-------------|--------------|
| 7.1 | E2E: self-serve flow on fresh machine (macOS) | All 4 hooks fire correctly |
| 7.2 | E2E: self-serve flow on fresh machine (Linux) | All 4 hooks fire correctly |
| 7.3 | E2E: enterprise flow (MDM simulation) | Plugin enforced, cannot be disabled |
| 7.4 | Latency testing | PreToolUse p95 < 3s |
| 7.5 | Offline resilience testing (10 min disconnect) | No interruption |
| 7.6 | Tag v1.0.0, create GitHub release | `claude plugin install unbound@unbound-marketplace` succeeds |

---

## Validation Checklist

- [ ] `claude plugin validate .` passes in plugin repo
- [ ] Fresh marketplace install works on macOS and Linux
- [ ] `/unbound:setup` completes in under 5 minutes
- [ ] PreToolUse blocks a command matching a BLOCK policy
- [ ] PreToolUse warns (ASK) for a command matching a WARN policy
- [ ] UserPromptSubmit blocks a prompt triggering DLP guardrails
- [ ] PostToolUse events appear in Unbound dashboard analytics
- [ ] Stop events log session completion
- [ ] Offline: hooks fail open, events logged to `~/.unbound/logs/`
- [ ] Enterprise: managed-settings.json auto-installs and enforces plugin
- [ ] Enterprise: user cannot disable plugin when `enabledPlugins` is set
- [ ] No regression: existing managed hooks customers unaffected
- [ ] Submodule update propagates changes without breaking plugin
- [ ] No backend changes required (confirmed)
