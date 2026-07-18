Cross-team agent guide. Keep this file operational.

## Authority

- This repo governs bundle mechanics only.
- The consumer repo's `AGENTS.md` remains authoritative for local behavior,
  domain rules, and commit/push policy.
- Tool source lives in submodules; bundle defaults and adoption docs live here.
- Consumer static config lives outside this submodule as `cross-team.json` and is
  committed by the consumer repo.

## Setup

- Copy `cross-team/cross-team.default.json` to `<consumer>/cross-team.json`.
- Edit only consumer identity, partner paths, and document roots in
  `<consumer>/cross-team.json`. Do not store sync cursors there.
- Do not put consumer config inside `cross-team/`.

## Parallax

- Use `CROSS_TEAM_CONFIG=<consumer>/cross-team.json`.
- Run `detect <partner>` before partner sync.
- Read partner artifacts only via `parallax read <partner> <path>`.
- Relay only committed-clean local artifacts.
- Keep sync cursors and scratch in Parallax's Git-private runtime state, never
  in `cross-team.json`.
- Close a real sync with two steps, together: advance the pin, then the ledger.
- Advance the pin: `parallax prepare <partner> --advance` — writes the
  Git-private cursor `detect` reads.
- Update the ledger: append one entry (partner HEAD, reads, responding
  artifacts, open obligations) to the committed ledger at `parallax.ledger_path`.

## Warrant

- Use `CROSS_TEAM_CONFIG=<consumer>/cross-team.json`.
- `consumer_root` must resolve docs and `parent_artifacts` relative to the
  consumer repo.
- Parent path errors are blocking unless confirmed by a failing regression
  fixture.

## Submodules

- Do not edit `artifact_types`, `parallax`, or `warrant` from a consumer task.
- Upstream tool changes require a focused commit in the tool repo, conformance
  where behavior changes, then a bundle submodule bump.
- Never pin this bundle to an unpushed tool commit for release.

## Commit Rules

- Commit `cross-team.json` in the consumer repo only when its static settings
  change.
- Do not commit generated runtime scratch, inboxes, or detect logs.
- Push only on explicit user signal.
