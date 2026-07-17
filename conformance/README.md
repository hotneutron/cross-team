# Bundle Conformance

This suite tests the consumer adoption boundary, not Parallax or Warrant
internals. It creates temporary consumer and partner Git repositories, invokes
only `bin/parallax` and `bin/warrant-check`, and removes all fixtures afterward.

Run it from the bundle root:

```sh
python3 conformance/test_bundle.py
```

The checks cover the static default configuration, initialized submodules,
wrapper discovery, unified Parallax configuration, Warrant consumer-root
resolution, Git-private sync cursor state, clean consumer worktrees, and
non-mutating failure paths. It also verifies that an optional configured
Parallax ledger remains consumer-owned rather than becoming private runtime
state.
