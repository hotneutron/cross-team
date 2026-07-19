# TRAE Agent compatibility driver

`run_agent_compat.py` is the bundle-owned certification driver for TRAE CLI.
It builds synthetic consumer/partner repositories, verifies native
`AGENTS.md` delivery through TRAE's project-doc loading, captures TRAE JSON
tool events, and emits the root validator's `trace.jsonl` and `state.json`.

Run from the bundle root:

```sh
python3 compat/run_agent_compat.py \
  --profile trae-agent \
  --driver "$PWD/compat/drivers/trae-agent/run_agent_compat.py" \
  --runs 3
```

The driver is explicit and non-default. It requires an authenticated `traecli`
and reports `BLOCKED` when the runtime, credentials, audit stream, or model
turn availability prevents a complete synthetic run.
