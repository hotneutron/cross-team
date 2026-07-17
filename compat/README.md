# Agent Guide Compatibility

This directory implements the deterministic part of the agent-guide
compatibility plan. It validates observed tool-event traces and final repository
state against the hard operational rules in `AGENTS.md`.

The suite does not run a real LLM by default and does not certify model quality.
It proves the contract and validator first with a scripted profile.

## Run

```sh
python3 compat/test_guide_contract.py
python3 compat/test_validator.py
python3 compat/run_agent_compat.py --profile scripted
```

## Files

| Path | Purpose |
|---|---|
| `drivers/<agent-id>/` | Bundle-owned real-agent certification drivers. |
| `guide_contract.json` | Rule ID to scenario/capability mapping. |
| `scenarios/*.json` | Synthetic compatibility scenarios AC1-AC8. |
| `profiles/scripted.json` | Deterministic profile used by CI. |
| `profiles/codex-cli.json` | Codex CLI capability declaration. |
| `profiles/trae-agent.json` | TRAE Agent capability declaration. |
| `drivers/codex.py` | Explicit, opt-in Codex CLI guide-compatibility driver. |
| `drivers/trae-agent/` | Explicit, opt-in TRAE Agent guide-compatibility driver. |
| `test_codex_driver.py` | Platform-independent tests for the Codex driver. |
| `run_agent_compat.py` | Trace validator and report generator. |
| `report.schema.json` | Versioned report shape. |
| `examples/report.example.json` | Non-evidence example report. |
| `status.json` | Sanitized profile status catalog. |

Real-agent certification drivers belong in this directory because they build
synthetic consumer/partner fixtures, deliver or verify this bundle's
`AGENTS.md`, emit the root validator's trace/state format, and feed the
bundle-owned compatibility catalog. Parallax adapters only own Parallax
watcher/poll integration notes or smoke tests.
