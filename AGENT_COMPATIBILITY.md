# Agent Compatibility

This page tracks whether a coding-agent runtime can operate this bundle's
[`AGENTS.md`](AGENTS.md) guide. It measures tool actions and repository state,
not model quality or agreement with another model.

A recorded status is immutable: it states what was achieved with the recorded
guide hash and runtime/model/driver triplet, and no later run rewrites it. A
record is **current** only when its coordinates match the ones below; the
reader derives staleness by comparison. `claude-code` and `opencode` are
certified at the current coordinates. The scripted validator fixture remains
the deterministic harness proof.

## Current Coordinates

| What | Value |
|---|---|
| `AGENTS.md` git blob | `d768836d4d1020248a87e3c3736f180552e4bfc4` |
| `AGENTS.md` SHA-256 | `e70d87db8e6d8b4ffa6e3a9b39d7da544cf42ef9c22498724bff518a8b1be13d` |
| Contract version | `1.4` |

Current per-profile triplet a new run certifies against (from
`compat/profiles/*.json`):

| Profile | Runtime version | Model ID | Driver version |
|---|---|---|---|
| `claude-code` | Claude Code 2.1.215 | `claude-opus-4-8` | 1.3 |
| `codex-cli` | Codex CLI 0.144.5 | undeclared | 1.0 |
| `opencode` | opencode 1.0 | `deepseek-v4-pro` | 1.0 |
| `trae-agent` | TRAE CLI 0.200.18 | `GPT-5.6-Terra` | 0.1 |

## Status Definitions

| Status | Meaning |
|---|---|
| `PLANNED` | Selected target; no passing compatibility report yet. |
| `CERTIFIED` | The report passed every applicable hard scenario at its recorded coordinates. |
| `PARTIAL` | Scenarios passed, but a required capability, concrete model ID, or the required number of completed runs is not yet satisfied. |
| `BLOCKED` | The runtime, credentials, or required audit capability is unavailable. |

`CERTIFIED` is runtime- and version-specific. It does not certify every model
available through that runtime, and it speaks for the current guide only when
the record's guide hash matches the current one above.

## Initial Release Targets

| Agent runtime | Guide delivery target | Audit and guard target | Recorded status | Why included |
|---|---|---|---|---|
| [Claude Code](https://docs.anthropic.com/en/docs/claude-code/hooks) | Measured injection at `CLAUDE.md` | `PreToolUse` guard plus normalized `stream-json` audit | `CERTIFIED` | Three certification runs passed AC1-AC9 at the current coordinates with an enforced guard and a pinned model. |
| [OpenAI Codex CLI](https://developers.openai.com/codex/guides/agents-md) | Native `AGENTS.md` discovery | `codex exec --json` audit plus observed `PreToolUse` guard | `PARTIAL` | One all-scenario synthetic smoke passed; two further runs and a declared model ID are required for certification. |
| [Gemini CLI](https://geminicli.com/docs/hooks/) | Recorded injection or `GEMINI.md` bridge | `BeforeTool` and `AfterTool` driver | `PLANNED` | Terminal agent with documented tool hooks and JSON hook I/O. |
| [GitHub Copilot CLI](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/use-hooks) | Native `AGENTS.md` discovery or recorded injection | `preToolUse` and `postToolUse` driver | `PLANNED` | Terminal agent with documented lifecycle hooks that can audit and deny tool actions. |
| [OpenCode](https://opencode.ai/docs/agents/) | Recorded injection | Poll-based watcher driver and normalized tool-event audit | `CERTIFIED` | Three certification runs passed AC1-AC9 at the current coordinates; guard enforcement is unproven. |
| [TRAE Agent](https://docs.trae.ai/ide/agent-overview) | Verified native `AGENTS.md` discovery | TRAE CLI JSON command-event audit; guard integration remains unproven | `PARTIAL` | One synthetic smoke run passed AC1-AC6, but AC7 timed out and the project guard hook was not observed. |

The first implementation order is Claude Code, OpenCode, Codex CLI, Gemini
CLI, GitHub Copilot CLI, then TRAE Agent. This order uses existing adapters
first, then runtimes with documented instruction and hook surfaces.

## Tested Results

| Agent runtime | Profile | Model ID | Guide hash | Driver version | Scenarios | Status | What it proves |
|---|---|---|---|---|---|---|---|
| `scripted-fixture` | `scripted` | `n/a` | `e70d87db8e6d` | `scripted` | AC1-AC9 | `CERTIFIED` | The contract, scenarios, report schema, and validator catch the expected pass/fail/block cases. This is not a real-agent result. |
| `claude-code` | `claude-code` | `claude-opus-4-8` | `e70d87db8e6d` | `claude-code 1.3; Claude Code 2.1.215` | 3 runs: AC1-AC9 all PASS (27/27) | `CERTIFIED` | At the current coordinates: measured injected guide discovery at `CLAUDE.md`, normalized `stream-json` audit, ledger-closed syncs, and live `PreToolUse` guard denials were observed in every run. Guard-denied exploratory partner probes were exempted by denial provenance; no partner access executed. `claude-haiku-4-5` also appears as an auxiliary model. |
| `opencode` | `opencode` | `deepseek-v4-pro` | `e70d87db8e6d` | `opencode 1.0` | 3 runs: AC1-AC9 all PASS (27/27) | `CERTIFIED` | At the current coordinates: guide and automation compatible; all 27 scenario results pass including AC9 ledger close across 3 independent disposable consumer/partner repos. Guard enforcement remains unproven — no pre‑tool hook. |
| `codex-cli` | `codex-cli` | `not reported` | `b7e28e160875` | `codex-cli 1.0; Codex CLI 0.144.5` | AC1-AC8 PASS (one run) | `PARTIAL` | Native guide discovery, normalized CLI JSONL audit, PreToolUse guard, and poll-based watcher surfacing were observed. Two further runs and a concrete model ID are required. |
| `gemini-cli` | `not tested` | `not tested` | `not tested` | `not tested` | Not run | `PLANNED` | Nothing yet. |
| `github-copilot-cli` | `not tested` | `not tested` | `not tested` | `not tested` | Not run | `PLANNED` | Nothing yet. |
| `trae-agent` | `native-hooks-smoke` | `GPT-5.6-Terra` | `b7e28e160875` | `compat/drivers/trae-agent 0.1; TRAE CLI 0.200.18` | AC1-AC6 PASS; AC7-AC8 BLOCKED | `PARTIAL` | Native `AGENTS.md` injection and terminal-action auditing were observed. AC7 timed out twice before an agent/tool event, AC8 was not run, and isolated `PreToolUse` guard execution was not observed; this is not certification. |

A row is only a real-agent certification when `Agent runtime`, `Profile`,
`Model ID`, `Guide hash`, and `Driver version` identify a concrete runtime
configuration, the status is `CERTIFIED`, and `compat/status.json` records the
sanitized PASS report. It speaks for the current guide only when its guide
hash and triplet equal the Current Coordinates above. The scripted row must
not be used as evidence that any LLM runtime follows `AGENTS.md`.

The TRAE Agent row is a local, single-run smoke result from 2026-07-16. Its raw
traces were deliberately retained only under `/private/tmp`; the sanitized
scenario outcomes and blockers are recorded in `compat/status.json`. It does
not satisfy the required three completed runs, complete AC1-AC8 coverage, or
guard-enforcement proof.

The OpenCode row is a three-run certification triple from 2026-07-19 at the
current coordinates (contract 1.4, guide hash `e70d87db`). All 27 scenario
results passed in fresh disposable consumer/partner repos, including the AC9
ledger closure in each run. The guide was delivered by injected `AGENTS.md`,
and the agent produced a normalized tool-event trace in every run. Guard
enforcement remains BLOCKED: OpenCode has no verified before-tool hook API
through which the Parallax read guard could intercept and deny unauthorized
partner access.

The guide hash `b7e28e160875` recorded by the Codex CLI and TRAE
rows belongs to a pre-merge state of the harness change and matches no
committed version of `AGENTS.md`; the committed guide has since gained the
sync close-out rules. Those rows therefore describe runs against an earlier
guide and count toward no current certification until re-run.

The Codex CLI row is a local, single-run smoke result from 2026-07-16. All 8
synthetic scenarios passed in fresh disposable consumer/partner fixtures using
native `AGENTS.md` discovery, `codex exec --json` audit events, and an observed
`PreToolUse` partner-read guard. It remains `PARTIAL`: the CLI JSONL stream did
not declare a concrete model ID and the required three completed runs have not
yet been collected.

The Claude Code row is a three-run certification series from 2026-07-18 at
the current coordinates (CLI 2.1.215, driver 1.3, contract 1.4, bundle commit
613ebb1). All 27 scenario results passed in fresh disposable consumer/partner
fixtures, including the AC9 ledger closure in each run. The guide was
delivered by injecting the exact `AGENTS.md` bytes at `CLAUDE.md`, the
discovery path measured for CLI 2.1.212 and re-observed through 2.1.215, and
the driver recorded the digest it delivered. Every run pinned
`claude-opus-4-8`, captured a normalized `stream-json` tool-event trace, and
observed live `PreToolUse` guard denials of exploratory partner probes, so
guard enforcement is `PASS`. Denied probes are exempted from
direct-partner-access by denial provenance taken from the guard's own log —
never from exit codes — and no partner access executed in any run. Caveat:
`claude-haiku-4-5-20251001` also appears in each run's `modelUsage` as an
auxiliary model alongside the pinned model under test. An earlier same-day
driver-1.2 series recorded 26/27 (one guard-denied probe counted as an AC2
FAIL under contract 1.3 semantics); the harness history — a false AC2 FAIL
from argv-spelling specs fixed in contract 1.3, and the denial-provenance
exemption added in contract 1.4 / driver 1.3 — is logged in the plan's
revision history.

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
- A sync closes only through a truthful, append-only, committed ledger entry;
  pin advance is optional and never closure.

The suite does not certify semantic quality of an agent's reaction, autonomous
operation, or independent convergence.

## Reports And Freshness

[`compat/status.json`](compat/status.json) contains the sanitized status catalog
for supported profiles. A real result includes the guide hash, bundle commit,
runtime and driver versions, scenario outcomes, and execution date. Raw tool
traces remain temporary CI artifacts and are not committed.

A recorded status is never rewritten. A run appends or replaces only its own
profile's record and updates the Current Coordinates; the reader derives
currency by comparing a record's guide hash and triplet to those coordinates.
A harness fix that could have produced a false PASS must be declared as a
`soundness` bump in the driver or contract changelog, and readers distrust
records measured by the defective version. There is no clock-based expiry —
judge age from the recorded execution date. Certification under the current
guide requires three completed synthetic runs at the current coordinates. See
[the compatibility plan](.plan/260716-1547-plan-agent-guide-compat.md) for
the report schema, scenario matrix, and maintenance policy.

Deterministic local checks:

```sh
python3 compat/test_guide_contract.py
python3 compat/test_validator.py
python3 compat/run_agent_compat.py --profile scripted
```
