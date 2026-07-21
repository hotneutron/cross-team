# cross-team — independent cross-checking across repositories

**Measured disagreement between independent agents — packaged for adoption.**

One coding agent gives you a flat, confident view of a problem. A second
opinion is only worth something if it is independent — and in most multi-agent
setups it isn't: the reviewer shares context with the author, or reads its
uncommitted work, so the "second view" is an echo and agreement means nothing.

A parallax is one object seen from two vantage points; the displacement
between the views is the signal. Here, two or more AI teams independently
brainstorm the same problem in separate repos, then cross-check and
corroborate their work through a controlled cross-repository exchange — and
the independence that makes their divergence meaningful is *machine-enforced*,
not trusted. The full pitch and protocol live in
[`parallax/`](parallax/README.md).

This repository is the adoption boundary that makes parallax usable: a
consumer project adds **one submodule**, then owns **one static config file**
outside the submodule.

## Layout

| Path | Purpose |
|---|---|
| `parallax/` | The cross-team sync daemon — enforces independence, measures divergence. |
| `warrant/` | Frontmatter authority checker — is a doc's declared authority warranted? |
| `artifact_types/` | Shared artifact vocabulary registry both tools are written against. |
| `compat/` | Agent guide compatibility contract and scripted validator. |
| `cross-team.default.json` | Neutral default config copied by consumers. |
| `AGENTS.md` | Agent rules for bundle mechanics only. |
| `AGENT_COMPATIBILITY.md` | Agent guide compatibility states and release targets. |

## Core Tools

**Parallax** enables two or more AI teams to collaborate through independent
brainstorming, cross-checking, and corroboration. The difference between teams'
views is the signal, so it preserves independence with committed-only,
manifest-logged partner reads; a read guard against out-of-band access; embargo
redaction for in-flight verdicts; and a commit-before-relay gate. It reveals
what needs review without leaking a conclusion before the other team has
completed its own work.

**Warrant** asks whether an artifact's claimed authority is justified by its
provenance—"no rant without a warrant." It validates frontmatter authority
tiers and `parent_artifacts` against consumer policy, so a document cannot
present specificity or confidence as correctness without supporting lineage.

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

A cross-check is apples-to-apples only when each agent runtime demonstrably
operates the same guide contract. [AGENT_COMPATIBILITY.md](AGENT_COMPATIBILITY.md)
records which runtimes are certified — with pinned guide hashes and
runtime/model/driver coordinates — plus current release targets and the
certification criteria, including the gaps that remain open.

## Release Gates

- `python3 conformance/test_bundle.py` passes.
- `parallax` and `warrant` consume `CROSS_TEAM_CONFIG` directly.
- Warrant resolves `parent_artifacts` via `consumer_root`.
- No nested `artifact_types` submodule exists under `parallax/` or `warrant/`.
- No shipped default/doc text leaks consumer names.
- `.plan/` appears only in `cross-team.default.json` or tests, not runtime code.
