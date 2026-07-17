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
| `guide_contract.json` | Rule ID to scenario/capability mapping. |
| `scenarios/*.json` | Synthetic compatibility scenarios AC1-AC8. |
| `profiles/scripted.json` | Deterministic profile used by CI. |
| `run_agent_compat.py` | Trace validator and report generator. |
| `report.schema.json` | Versioned report shape. |
| `examples/report.example.json` | Non-evidence example report. |
| `status.json` | Sanitized profile status catalog. |

Real-agent drivers belong with the relevant Parallax adapter. They should
produce normalized JSONL traces and state JSON for this validator to consume.
