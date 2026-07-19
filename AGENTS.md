Cross-team agent guide. Keep this file operational.

## Authority

- This repo governs bundle mechanics only.
- The consumer repo's `AGENTS.md` remains authoritative for local behavior,
  domain rules, and commit/push policy.
- Tool source lives in submodules; bundle defaults and adoption docs live here.
- [AG01] Consumer static config lives outside this repo as `cross-team.json`,
  committed by the consumer; sync never writes a cursor to the config, this
  repo, or any non-Git-private path.

## Setup

- Copy `cross-team/cross-team.default.json` to `<consumer>/cross-team.json`.
- Edit only consumer identity, partner paths, document roots, and
  `parallax.ledger_path` in `<consumer>/cross-team.json`. Do not store sync
  cursors there.
- Do not put consumer config inside this repo.
- [AG02] Run bundle tools with `CROSS_TEAM_CONFIG=<consumer>/cross-team.json`,
  or from a consumer root where `cross-team.json` is discoverable.

## Parallax

- [AG03] Run `detect <partner>` before any partner-sync action.
- [AG04] Read partner artifacts only via `parallax read <partner> <path>`.
- [AG05] Relay only committed-clean local artifacts.
- Keep sync cursors and scratch in Parallax's Git-private runtime state, never
  in `cross-team.json`.
- [AG06] Only for a sync: append a ledger entry, optionally advance the pin
  to speed the next detect.
- [AG11] Closing a sync requires the ledger: append one entry (partner HEAD,
  reads, responding artifacts, open obligations) to the committed ledger at
  `parallax.ledger_path`. No entry, no closure.
- Pin advance: `parallax prepare <partner> --advance` writes the Git-private
  cursor `detect` reads. It never closes a sync.

## Warrant

- [AG07] Warrant resolves docs and `parent_artifacts` relative to the consumer
  repo root.
- [AG08] Parent path errors are blocking unless a failing regression fixture
  confirms a genuine tool regression.

## Submodules

- [AG09] Do not edit `artifact_types`, `parallax`, or `warrant` from a
  consumer task.
- Upstream tool changes require a focused commit in the tool repo, conformance
  where behavior changes, then a bundle submodule bump.
- Never pin this bundle to an unpushed tool commit for release.

## Commit Rules

- Commit `cross-team.json` in the consumer repo only when its static settings
  change.
- Do not commit generated runtime scratch, inboxes, or detect logs.
- [AG10] Push only on explicit user signal; the consumer repo's `AGENTS.md` may
  override.
