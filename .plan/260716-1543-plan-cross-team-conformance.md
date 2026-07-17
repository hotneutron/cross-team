# Cross-Team Bundle Conformance Plan

## Revision History

| Date | Change |
|---|---|
| 2026-07-16 | Initial plan for bundle-level consumer integration conformance. |
| 2026-07-16 | Make consumer config static; move sync cursors to private runtime state. |
| 2026-07-16 | Implement bundle runner and Git-private Parallax cursor state. |

## Goal

Prove that a consumer can adopt this bundle, copy `cross-team.default.json` to
`cross-team.json`, and use the pinned Parallax and Warrant tools through the
bundle wrappers. This plan covers bundle mechanics only. It does not duplicate
the upstream tools' own conformance suites.

## Scope And Boundaries

- Add root-level bundle conformance under `conformance/`.
- Use only Python standard library modules.
- Create all consumer and partner repositories in temporary directories.
- Exercise `bin/parallax` and `bin/warrant-check` as black-box entry points.
- Do not edit `artifact_types`, `parallax`, or `warrant` directly from this
  repository.
- Do not use the ignored `test-fixtures/` runtime remnants as test inputs.

## Test Matrix

| ID | Contract | Measurement |
|---|---|---|
| CT1 | Default config is a clean template. | Parse `cross-team.default.json`; require empty `parallax.partners`, no runtime pin/date fields, and artifact types that exist in the bundled registry. |
| CT2 | Bundle closure is complete. | Confirm the three dependency paths are initialized Git submodules and both wrapper scripts are executable. |
| CT3 | Consumer config discovery works. | Copy the template into a temporary consumer, fill fixture-only fields, and run each wrapper from the consumer root without `CROSS_TEAM_CONFIG`; repeat with an explicit config path from an unrelated cwd. |
| CT4 | Parallax consumes the unified config. | With no live `partners.json` or `tiers.json`, detect a committed partner `.plan/` artifact and assert the generated detect result names the configured partner and tier. |
| CT5 | Warrant resolves consumer-relative paths. | Validate a temporary consumer `.plan/` parent/child pair using the wrapper; assert the repo-relative parent and bundled registry resolve correctly. |
| CT6 | Sync state has the correct owner. | After an obligation, logged read, and `prepare --advance`, assert `cross-team.json` and the source template remain byte-identical; the pin/date updates exist only in Git-private Parallax state. |
| CT7 | Runtime artifacts do not dirty the consumer worktree. | Run `detect`, `read`, and pin advancement; assert consumer `git status --porcelain` is clean and static config remains unchanged. |
| CT8 | Failure paths do not mutate state. | Run with an unknown partner and with no discoverable config; require non-zero exit status and unchanged config/template hashes. |

## Harness Design

Create `conformance/test_bundle.py` with `unittest`, `tempfile`, `subprocess`,
and `json`. Each test constructs independent temporary Git repositories:

1. Create a consumer repository and a committed partner repository.
2. Expose the current bundle under `consumer/cross-team`.
3. Copy `cross-team/cross-team.default.json` to `consumer/cross-team.json`.
4. Modify only fixture identity, partner path, and test documents.
5. Run bundle wrappers, then assert exit codes, emitted JSON, file hashes, and
   Git worktree state.
6. Remove the temporary directory unconditionally.

Add `conformance/README.md` with the stable local command:

```sh
python3 conformance/test_bundle.py
```

The runner must not write verdicts, scratch files, or fixtures into this
repository.

## Upstream Prerequisite

CT6 and CT7 are expected to expose the current ownership defects: with
`CROSS_TEAM_CONFIG`, Parallax writes `_cross-team/` into the consumer root and
updates `last_pinned` and `last_sync` in the static consumer config. The
consumer does not inherit this bundle's `.gitignore`, and sync progress does
not belong in configuration. The permanent fix belongs in Parallax: use a
Git-private state path such as the result of
`git rev-parse --git-path cross-team`, including worktree-safe resolution.
Store per-partner cursors there, merge them with static partner descriptors at
read time, and write cursor advances only to that state.

Implement that fix in the Parallax repository with focused upstream
conformance, push it, then bump the `parallax` submodule pointer here. Do not
paper over the issue by writing consumer-specific ignore files.

## Release Gates

Run these independently before releasing a bundle update:

```sh
python3 conformance/test_bundle.py
(cd parallax && python3 conformance/run.py --daemon parallax.py)
(cd warrant && python3 conformance/test_check.py --engine reference/_check_frontmatter.py)
(cd warrant && python3 conformance/test_apply.py --engine reference/_apply_frontmatter.py)
git submodule status --recursive
```

The root runner verifies integration. The Parallax and Warrant commands remain
the authoritative behavioral conformance for their respective tool sources.

## Current Baseline

- Warrant checker conformance: 40/40 PASS.
- Warrant apply conformance: 10/10 PASS.
- Parallax conformance: 66/66 decided checks PASS; `S2` remains cross-run
  BLOCKED and `B12c` is BLOCKED on hosts without `inotifywait`.
- Bundle conformance: CT1-CT8 PASS.

## Execution Status

- Added `conformance/test_bundle.py` and `conformance/README.md`.
- Added Parallax B35/B36 regressions for static consumer config and
  Git-private cursor state.
- Fixed the Parallax S5 fixture so its valid independent claim uses a schema-
  compliant namespace and the test measures the intended constraint.
- Created upstream Parallax commit `126c12d5fb5d1802b1e5cc469484c6ca20335c92`
  (`fix: keep unified config state git-private`).
- The upstream commit is intentionally not yet pinned by a bundle commit: it
  must be pushed before this bundle can carry its submodule pointer for
  release.
