#!/usr/bin/env python3
"""Black-box conformance for the cross-team adoption bundle."""
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path


BUNDLE_ROOT = Path(__file__).resolve().parents[1]


def run(argv, cwd, env=None, check=True):
    result = subprocess.run(
        [str(a) for a in argv],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )
    if check and result.returncode != 0:
        raise AssertionError(
            f"command failed ({result.returncode}): {' '.join(map(str, argv))}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def git(repo, *args, check=True):
    return run(["git", "-C", repo, *args], repo, check=check)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def has_runtime_cursor(value):
    if isinstance(value, dict):
        return any(
            key in ("last_pinned", "last_sync") or has_runtime_cursor(child)
            for key, child in value.items()
        )
    if isinstance(value, list):
        return any(has_runtime_cursor(child) for child in value)
    return False


class BundleConformance(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="cross_team_bundle_"))
        self.consumer = self.root / "consumer"
        self.partner = self.root / "partner"
        self._init_repo(self.partner)
        self._write(self.partner / ".plan" / "baseline.md", "# Baseline\n")
        self._commit(self.partner, "fixture: partner baseline")
        self._write(
            self.partner / ".plan" / "260101-0000-reaction.md",
            "---\nartifact_type: reaction\naddressed_to: consumer\n---\n# Partner request\n",
        )
        self._commit(self.partner, "fixture: partner reaction")

        self._init_repo(self.consumer)
        os.symlink(BUNDLE_ROOT, self.consumer / "cross-team", target_is_directory=True)
        config = json.loads((BUNDLE_ROOT / "cross-team.default.json").read_text())
        config["parallax"]["partners"] = {
            "p": {"path": "../partner", "team_name": "partner"}
        }
        config["parallax"]["tiers"]["self_name"] = "consumer"
        self.config_path = self.consumer / "cross-team.json"
        self.config_path.write_text(json.dumps(config, indent=2) + "\n")
        self._write(
            self.consumer / ".plan" / "parent.md",
            "---\nartifact_type: study\nauthority: derived\ngenerated_by: fixture\n"
            "parent_artifacts:\n  - external:paper.md\n---\n# Parent study\n",
        )
        self._write(
            self.consumer / ".plan" / "child.md",
            "---\nartifact_type: plan\nauthority: derived\ngenerated_by: fixture\n"
            "parent_artifacts:\n  - .plan/parent.md\n---\n# Child plan\n",
        )
        self._commit(self.consumer, "fixture: consumer config and documents")
        self.template_hash = sha256(BUNDLE_ROOT / "cross-team.default.json")
        self.config_hash = sha256(self.config_path)

    def tearDown(self):
        for _ in range(5):
            shutil.rmtree(self.root, ignore_errors=True)
            if not self.root.exists():
                return
            time.sleep(0.1)
        self.fail(f"failed to remove fixture directory: {self.root}")

    def _init_repo(self, path):
        path.mkdir(parents=True)
        run(["git", "init", "-q"], path)
        run(["git", "config", "user.email", "fixture@example.invalid"], path)
        run(["git", "config", "user.name", "fixture"], path)

    def _write(self, path, content):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    def _commit(self, repo, message):
        git(repo, "add", "-A")
        git(repo, "commit", "-qm", message)

    def _tool(self, name, *args, cwd=None, explicit_config=False, check=True):
        env = dict(os.environ)
        if explicit_config:
            env["CROSS_TEAM_CONFIG"] = str(self.config_path)
        else:
            env.pop("CROSS_TEAM_CONFIG", None)
        return run(
            [self.consumer / "cross-team" / "bin" / name, *args],
            cwd or self.consumer,
            env=env,
            check=check,
        )

    def _state_dir(self):
        state = git(
            self.consumer, "rev-parse", "--git-path", "cross-team/parallax"
        ).stdout.strip()
        path = Path(state)
        return path if path.is_absolute() else self.consumer / path

    def _status(self):
        return git(self.consumer, "status", "--porcelain").stdout

    def test_ct1_default_config_is_static_and_registry_backed(self):
        config = json.loads((BUNDLE_ROOT / "cross-team.default.json").read_text())
        registry = json.loads(
            (BUNDLE_ROOT / "artifact_types" / "artifact_types.json").read_text()
        )
        self.assertEqual(config["parallax"]["partners"], {})
        self.assertFalse(has_runtime_cursor(config))
        self.assertTrue(
            set(config["parallax"]["tiers"]["atypes"]).issubset(registry["types"])
        )
        self.assertTrue(
            set(config["warrant"]["type_authority"]).issubset(registry["types"])
        )

    def test_ct2_bundle_closure_and_wrappers(self):
        for name in ("artifact_types", "parallax", "warrant"):
            self.assertEqual(
                git(BUNDLE_ROOT / name, "rev-parse", "--is-inside-work-tree").stdout.strip(),
                "true",
            )
        for name in ("parallax", "warrant-check"):
            wrapper = BUNDLE_ROOT / "bin" / name
            self.assertTrue(wrapper.is_file())
            self.assertTrue(os.access(wrapper, os.X_OK))

    def test_ct3_wrapper_config_discovery_and_explicit_config(self):
        self._tool("parallax", "detect", "p")
        self._tool("warrant-check")
        elsewhere = self.root / "elsewhere"
        elsewhere.mkdir()
        self._tool("parallax", "count", "p", cwd=elsewhere, explicit_config=True)
        self._tool("warrant-check", cwd=elsewhere, explicit_config=True)

    def test_ct4_parallax_uses_unified_static_config(self):
        self._tool("parallax", "detect", "p")
        detect = json.loads((self._state_dir() / "_detect.json").read_text())
        self.assertEqual(detect["partner"], "p")
        self.assertIn(".plan/260101-0000-reaction.md", detect["tiers"]["1"])
        self.assertEqual(sha256(self.config_path), self.config_hash)

    def test_ct5_warrant_resolves_consumer_root_and_registry(self):
        result = self._tool("warrant-check")
        self.assertIn("All frontmatter valid", result.stdout)

    def test_ct6_pin_advance_uses_private_cursor_state(self):
        self._tool("parallax", "detect", "p")
        self._tool("parallax", "read", "p", ".plan/260101-0000-reaction.md")
        self._tool("parallax", "prepare", "p", "--advance")
        cursor_file = self._state_dir() / "partner_cursors.json"
        cursor = json.loads(cursor_file.read_text())["partners"]["p"]
        partner_head = git(self.partner, "rev-parse", "HEAD").stdout.strip()
        self.assertEqual(cursor["last_pinned"], partner_head)
        self.assertTrue(cursor["last_sync"])
        self.assertEqual(sha256(self.config_path), self.config_hash)
        self.assertEqual(sha256(BUNDLE_ROOT / "cross-team.default.json"), self.template_hash)

    def test_ct7_runtime_state_does_not_dirty_consumer_worktree(self):
        self._tool("parallax", "detect", "p")
        self._tool("parallax", "read", "p", ".plan/260101-0000-reaction.md")
        self._tool("parallax", "prepare", "p", "--advance")
        self.assertEqual(self._status(), "")
        self.assertFalse((self.consumer / "_cross-team").exists())
        self.assertEqual(sha256(self.config_path), self.config_hash)

    def test_ct8_failures_do_not_mutate_static_configuration(self):
        unknown = self._tool("parallax", "detect", "missing", check=False)
        self.assertNotEqual(unknown.returncode, 0)
        self.assertEqual(sha256(self.config_path), self.config_hash)
        self.assertEqual(sha256(BUNDLE_ROOT / "cross-team.default.json"), self.template_hash)
        self.assertFalse((self._state_dir() / "partner_cursors.json").exists())

        empty = self.root / "empty"
        empty.mkdir()
        env = dict(os.environ)
        env.pop("CROSS_TEAM_CONFIG", None)
        missing = run(
            [self.consumer / "cross-team" / "bin" / "parallax", "detect", "p"],
            empty,
            env=env,
            check=False,
        )
        self.assertNotEqual(missing.returncode, 0)
        self.assertEqual(sha256(self.config_path), self.config_hash)
        self.assertEqual(sha256(BUNDLE_ROOT / "cross-team.default.json"), self.template_hash)

    def test_ct9_configured_ledger_stays_consumer_owned(self):
        config = json.loads(self.config_path.read_text())
        config["parallax"]["ledger_path"] = "methodology/sync_ledger.json"
        self.config_path.write_text(json.dumps(config, indent=2) + "\n")
        ledger_path = self.consumer / "methodology" / "sync_ledger.json"
        ledger_path.parent.mkdir(parents=True)
        ledger_path.write_text(json.dumps({
            "entries": [{
                "date": "2026-01-02",
                "partner": "p",
                "their_head": git(self.partner, "rev-parse", "HEAD").stdout.strip(),
                "obligations": ["consumer-owned-ledger-obligation"],
            }]
        }) + "\n")

        self._tool("parallax", "detect", "p")
        prepared = self._tool("parallax", "prepare", "p")
        summary = json.loads(self._tool("parallax", "ledger", "--recent", "1").stdout)

        self.assertIn("consumer-owned-ledger-obligation", prepared.stdout)
        self.assertEqual(summary["total_entries"], 1)
        self.assertFalse((self._state_dir() / "sync_ledger.json").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
