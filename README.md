# cross-team

Portable bundle for the cross-team methodology tools.

This repository is an adoption boundary. A consumer project adds one submodule,
then owns one static config file outside the submodule.

## Layout

| Path | Purpose |
|---|---|
| `artifact_types/` | Shared artifact vocabulary registry. |
| `parallax/` | Cross-team sync daemon. |
| `warrant/` | Frontmatter authority checker. |
| `cross-team.default.json` | Neutral default config copied by consumers. |
| `AGENTS.md` | Agent rules for bundle mechanics only. |
| `AGENT_COMPATIBILITY.md` | Agent guide compatibility states and release targets. |

## Adopt in a Consumer

```bash
git submodule add https://github.com/hotneutron/cross-team cross-team
git -C cross-team submodule update --init --recursive
cp cross-team/cross-team.default.json cross-team.json
```

Edit and commit static `cross-team.json` settings in the consumer repo. Do not
put consumer config inside `cross-team/`.

## Run

```bash
CROSS_TEAM_CONFIG=cross-team.json cross-team/bin/parallax detect <partner>
CROSS_TEAM_CONFIG=cross-team.json cross-team/bin/warrant-check
```

Both tools read the same versioned consumer config. They do not require
`partners.json`, `tiers.json`, or `policy.json` live files.

## Agent Compatibility

See [AGENT_COMPATIBILITY.md](AGENT_COMPATIBILITY.md) for the current agent
compatibility states, initial release targets, and certification criteria.

## Release Gates

- `python3 conformance/test_bundle.py` passes.
- `parallax` and `warrant` consume `CROSS_TEAM_CONFIG` directly.
- Warrant resolves `parent_artifacts` via `consumer_root`.
- No nested `artifact_types` submodule exists under `parallax/` or `warrant/`.
- No shipped default/doc text leaks consumer names.
- `.plan/` appears only in `cross-team.default.json` or tests, not runtime code.
