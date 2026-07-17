# Agent Compatibility

This page tracks whether a coding-agent runtime can operate this bundle's
[`AGENTS.md`](AGENTS.md) guide. It measures tool actions and repository state,
not model quality or agreement with another model.

No real-agent runtime is certified yet. The only current PASS is the scripted
validator fixture, which proves the compatibility harness itself.

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
| [TRAE Agent](https://docs.trae.ai/ide/agent-overview) | Verified native `AGENTS.md` discovery | TRAE CLI JSON command-event audit; guard integration remains unproven | `PARTIAL` | One synthetic smoke run passed AC1-AC6, but AC7 timed out and the project guard hook was not observed. |

The first implementation order is Claude Code, OpenCode, Codex CLI, Gemini
CLI, GitHub Copilot CLI, then TRAE Agent. This order uses existing adapters
first, then runtimes with documented instruction and hook surfaces.

## Tested Results

| Agent runtime | Profile | Model ID | Guide hash | Driver version | Scenarios | Status | What it proves |
|---|---|---|---|---|---|---|---|
| `scripted-fixture` | `scripted` | `n/a` | `b7e28e160875` | `scripted` | AC1-AC8 | `CERTIFIED` | The contract, scenarios, report schema, and validator catch the expected pass/fail/block cases. This is not a real-agent result. |
| `claude-code` | `not tested` | `not tested` | `not tested` | `not tested` | Not run | `PLANNED` | Nothing yet. |
| `opencode` | `not tested` | `not tested` | `not tested` | `not tested` | Not run | `PLANNED` | Nothing yet. |
| `codex-cli` | `not tested` | `not tested` | `not tested` | `not tested` | Not run | `PLANNED` | Nothing yet. |
| `gemini-cli` | `not tested` | `not tested` | `not tested` | `not tested` | Not run | `PLANNED` | Nothing yet. |
| `github-copilot-cli` | `not tested` | `not tested` | `not tested` | `not tested` | Not run | `PLANNED` | Nothing yet. |
| `trae-agent` | `native-hooks-smoke` | `GPT-5.6-Terra` | `b7e28e160875` | `temporary-traecli-native-hooks 0.1; TRAE CLI 0.200.18` | AC1-AC6 PASS; AC7-AC8 BLOCKED | `PARTIAL` | Native `AGENTS.md` injection and terminal-action auditing were observed. AC7 timed out twice before an agent/tool event, AC8 was not run, and isolated `PreToolUse` guard execution was not observed; this is not certification. |

A row is only a real-agent certification when `Agent runtime`, `Profile`,
`Model ID`, `Guide hash`, and `Driver version` identify a concrete runtime
configuration, the status is `CERTIFIED`, and `compat/status.json` points to a
current sanitized PASS report. The scripted row must not be used as evidence
that any LLM runtime follows `AGENTS.md`.

The TRAE Agent row is a local, single-run smoke result from 2026-07-16. Its raw
traces were deliberately retained only under `/private/tmp`; the sanitized
scenario outcomes and blockers are recorded in `compat/status.json`. It does
not satisfy the required three completed runs, complete AC1-AC8 coverage, or
guard-enforcement proof.

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

[`compat/status.json`](compat/status.json) contains the sanitized status catalog
for supported profiles. A real result includes the guide hash, bundle commit,
runtime and driver versions, scenario outcomes, and expiration time. Raw tool
traces remain temporary CI artifacts and are not committed.

A status becomes `STALE` whenever the guide, bundle, driver, runtime version,
model ID, or required capability changes. Re-certification requires three
completed synthetic runs. See
[the compatibility plan](.plan/260716-1547-plan-agent-guide-compat.md) for
the report schema, scenario matrix, and maintenance policy.

Deterministic local checks:

```sh
python3 compat/test_guide_contract.py
python3 compat/test_validator.py
python3 compat/run_agent_compat.py --profile scripted
```
