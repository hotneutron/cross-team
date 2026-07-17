# Agent Compatibility

This page tracks whether a coding-agent runtime can operate this bundle's
[`AGENTS.md`](AGENTS.md) guide. It measures tool actions and repository state,
not model quality or agreement with another model.

No runtime is certified yet. The statuses below are release targets, not
compatibility claims.

## Status Definitions

| Status | Meaning |
|---|---|
| `PLANNED` | Selected target; no passing compatibility report yet. |
| `CERTIFIED` | A current report passed every applicable hard scenario. |
| `PARTIAL` | Some scenarios passed, but a required capability is unavailable. |
| `BLOCKED` | The runtime, credentials, or required audit capability is unavailable. |
| `STALE` | A previously certified report was invalidated by a guide, bundle, driver, CLI, or model change. |

`CERTIFIED` is runtime- and version-specific. It does not certify every model
available through that runtime.

## Initial Release Targets

| Agent runtime | Guide delivery target | Audit and guard target | Current status | Why included |
|---|---|---|---|---|
| [Claude Code](https://docs.anthropic.com/en/docs/claude-code/hooks) | Native discovery or recorded injection | `PreToolUse` and `PostToolUse` driver | `PLANNED` | Existing Parallax adapter documentation; lifecycle hooks can audit and block tool calls. |
| [OpenAI Codex CLI](https://developers.openai.com/codex/guides/agents-md) | Native `AGENTS.md` discovery | Driver must emit normalized tool events and prove guard installation | `PLANNED` | Terminal-first coding agent with an `AGENTS.md` guide surface. |
| [Gemini CLI](https://geminicli.com/docs/hooks/) | Recorded injection or `GEMINI.md` bridge | `BeforeTool` and `AfterTool` driver | `PLANNED` | Terminal agent with documented tool hooks and JSON hook I/O. |
| [GitHub Copilot CLI](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/use-hooks) | Native `AGENTS.md` discovery or recorded injection | `preToolUse` and `postToolUse` driver | `PLANNED` | Terminal agent with documented lifecycle hooks that can audit and deny tool actions. |
| [OpenCode](https://opencode.ai/docs/agents/) | Recorded injection | Poll-based watcher driver and normalized tool-event audit | `PLANNED` | Existing Parallax adapter documentation uses its file-poll model. |
| [TRAE Agent](https://docs.trae.ai/ide/agent-overview) | Injected into a custom-agent prompt or verified native discovery | Driver must capture terminal/read/edit actions and prove guard integration | `PLANNED` | Widely used IDE agent with custom agents and terminal tooling. |

The first implementation order is Claude Code, OpenCode, Codex CLI, Gemini
CLI, GitHub Copilot CLI, then TRAE Agent. This order uses existing adapters
first, then runtimes with documented instruction and hook surfaces.

## Deferred Popular Runtimes

Cursor, Cline, Roo Code, and Aider are relevant candidates but are not in the
first certification set. Add one only after its driver can deliver the guide,
capture complete tool events, and participate in the required synthetic
scenario suite. A runtime without auditable partner access can be `PARTIAL`;
it cannot be `CERTIFIED`.

## What Certification Tests

The compatibility suite verifies the operational rules in `AGENTS.md`:

- Consumer-owned `cross-team.json` is static and remains unchanged by sync;
  cursors and scratch are Git-private Parallax runtime state.
- `detect` happens before a partner read, and partner content is read only by
  `parallax read`.
- A zero-obligation cycle does not advance a runtime pin, commit, or relay.
- Dirty relay and Warrant parent-path failures block forward progress.
- Consumer tasks do not edit tool submodules or push without explicit user
  authorization.
- A supported watcher mechanism surfaces an inbox event without committing or
  relaying.

The suite does not certify semantic quality of an agent's reaction, autonomous
operation, or independent convergence.

## Reports And Freshness

The planned `compat/status.json` will contain the latest sanitized result for
each profile. A real result includes the guide hash, bundle commit, runtime and
driver versions, scenario outcomes, and expiration time. Raw tool traces remain
temporary CI artifacts and are not committed.

A status becomes `STALE` whenever the guide, bundle, driver, runtime version,
model ID, or required capability changes. Re-certification requires three
completed synthetic runs. See
[the compatibility plan](.plan/260716-1547-plan-agent-guide-compat.md) for
the report schema, scenario matrix, and maintenance policy.
