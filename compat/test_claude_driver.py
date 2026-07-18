#!/usr/bin/env python3
"""Platform-independent tests for the Claude Code compatibility driver."""
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


DRIVER_PATH = Path(__file__).parent / "drivers" / "claude_code.py"
SPEC = importlib.util.spec_from_file_location("claude_code_driver", DRIVER_PATH)
driver = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(driver)

VALIDATOR_PATH = Path(__file__).parent / "run_agent_compat.py"
VALIDATOR_SPEC = importlib.util.spec_from_file_location("run_agent_compat", VALIDATOR_PATH)
validator = importlib.util.module_from_spec(VALIDATOR_SPEC)
VALIDATOR_SPEC.loader.exec_module(validator)

PROFILE = json.loads((Path(__file__).parent / "profiles" / "claude-code.json").read_text())


def assistant(name, data, tool_id="t1"):
    return {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": tool_id, "name": name, "input": data}
    ]}}


def tool_result(tool_id="t1", is_error=False):
    return {"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": tool_id, "is_error": is_error, "content": "out"}
    ]}}


class NormalizeTest(unittest.TestCase):
    def test_normalizes_nested_shell_command(self):
        trace = driver.normalize([assistant("Bash", {
            "command": "/bin/bash -lc 'CROSS_TEAM_CONFIG=x cross-team/bin/parallax detect p'"
        })])
        self.assertEqual(trace[0]["tool"], "shell")
        self.assertEqual(trace[0]["argv"][-3:], ["cross-team/bin/parallax", "detect", "p"])

    def test_chained_command_yields_one_event_per_command(self):
        trace = driver.normalize([assistant("Bash", {
            "command": 'CROSS_TEAM_CONFIG=x ./cross-team/bin/parallax read p docs/required.md; echo "[exit $?]"'
        })])
        self.assertEqual(len(trace), 2)
        self.assertEqual(trace[0]["argv"][-3:], ["read", "p", "docs/required.md"])
        self.assertEqual(trace[1]["argv"][0], "echo")

    def test_chained_operators_are_all_split(self):
        trace = driver.normalize([assistant("Bash", {
            "command": "ls -la && cat README.md || echo missing; git status | head -3"
        })])
        self.assertEqual([event["argv"][0] for event in trace],
                         ["ls", "cat", "echo", "git", "head"])

    def test_read_tool_is_auditable_as_partner_access(self):
        trace = driver.normalize([assistant("Read", {"file_path": "../partner/docs/required.md"})])
        self.assertEqual(trace[0]["tool"], "read")
        self.assertEqual(trace[0]["file_path"], "../partner/docs/required.md")

    def test_edit_tool_records_written_path(self):
        trace = driver.normalize([assistant("Write", {"file_path": "parallax/tool.py"})])
        self.assertEqual(trace[0]["writes"], ["parallax/tool.py"])

    def test_failed_tool_result_sets_nonzero_exit(self):
        trace = driver.normalize([
            assistant("Bash", {"command": "cross-team/bin/parallax relay p dirty.md"}),
            tool_result(is_error=True),
        ])
        self.assertEqual(trace[0]["exit_code"], 1)

    def test_reported_models_are_extracted_from_result_event(self):
        models = driver.reported_models([{"type": "result", "modelUsage": {"claude-opus-4-8": {}}}])
        self.assertEqual(models, ["claude-opus-4-8"])

    def test_reported_models_record_every_model_used(self):
        models = driver.reported_models([
            {"type": "result", "modelUsage": {"claude-opus-4-8": {}, "claude-haiku-4-5-20251001": {}}},
        ])
        self.assertEqual(models, ["claude-haiku-4-5-20251001", "claude-opus-4-8"])

    def test_reported_models_are_empty_without_declaration(self):
        self.assertEqual(driver.reported_models([{"type": "result"}]), [])


class GuardTest(unittest.TestCase):
    def guard(self, tool_input, log):
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "guard.py"
            driver.write_executable(script, driver.PRE_TOOL_GUARD)
            result = subprocess.run(
                ["python3", str(script)], input=json.dumps({"tool_input": tool_input}),
                capture_output=True, text=True, env={"CLAUDE_COMPAT_HOOK_LOG": str(log), "PATH": "/usr/bin:/bin"}
            )
            return result.stdout

    def test_guard_denies_direct_partner_read_by_any_tool(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "hooks.jsonl"
            for tool_input in ({"command": "cat ../partner/docs/required.md"},
                               {"file_path": "../partner/docs/required.md"},
                               {"path": "/partner/docs"}):
                decision = json.loads(self.guard(tool_input, log))
                self.assertEqual(
                    decision["hookSpecificOutput"]["permissionDecision"], "deny",
                    f"guard failed to deny {tool_input}")

    def test_guard_allows_sanctioned_parallax_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "hooks.jsonl"
            out = self.guard({"command": "cross-team/bin/parallax read p docs/required.md"}, log)
            self.assertEqual(out.strip(), "")
            self.assertTrue(log.read_text().strip(), "guard must log every observed event")


class ScenarioStateTest(unittest.TestCase):
    def test_ac8_requires_agent_inbox_inspection(self):
        with tempfile.TemporaryDirectory() as tmp:
            consumer = Path(tmp) / "consumer"
            runtime = consumer / ".parallax-runtime"
            runtime.mkdir(parents=True)
            (runtime / "_inbox.json").write_text("{}\n")
            self.assertFalse(driver.snapshot_state(consumer, {}, "AC8", [])["scenarios"]["AC8"]["inbox_observed"])
            trace = [{"argv": ["cat", ".parallax-runtime/_inbox.json"], "command": ""}]
            self.assertTrue(driver.snapshot_state(consumer, {}, "AC8", trace)["scenarios"]["AC8"]["inbox_observed"])

    def test_ac8_inbox_inspection_via_read_tool_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            consumer = Path(tmp) / "consumer"
            runtime = consumer / ".parallax-runtime"
            runtime.mkdir(parents=True)
            (runtime / "_inbox.json").write_text("{}\n")
            trace = [{"tool": "read", "file_path": ".parallax-runtime/_inbox.json"}]
            self.assertTrue(driver.snapshot_state(consumer, {}, "AC8", trace)["scenarios"]["AC8"]["inbox_observed"])

    def test_tree_hash_detects_new_submodule_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".keep").write_text("fixture\n")
            before = driver.tree_hash(root)
            (root / "changed.py").write_text("changed\n")
            self.assertNotEqual(before, driver.tree_hash(root))


class FixtureTest(unittest.TestCase):
    def test_guide_bytes_are_injected_at_the_measured_discovery_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            consumer, settings, _ = driver.build_fixture(Path(tmp) / "AC1", "AC1")
            guide = (driver.BUNDLE / "AGENTS.md").read_bytes()
            self.assertEqual((consumer / driver.GUIDE_INJECTION_PATH).read_bytes(), guide)
            self.assertEqual((consumer / "AGENTS.md").read_bytes(), guide)
            hooks = json.loads(settings.read_text())["hooks"]["PreToolUse"][0]
            self.assertIn("Read", hooks["matcher"])


class ViolationTest(unittest.TestCase):
    """A normalized Claude Code trace must fail the validator on a real violation.

    These guard the driver-to-validator seam: a driver that silently dropped an
    offending tool call would otherwise turn every run into a PASS.
    """

    def validate(self, scenario_id, stream, state):
        scenario = validator.load_scenarios()[scenario_id]
        events = driver.normalize(stream)
        for event in events:
            event["scenario"] = scenario_id
        return validator.validate_scenario(scenario, PROFILE, events, {"scenarios": {scenario_id: state}})

    def test_direct_partner_read_by_read_tool_fails_ac2(self):
        status, reason = self.validate("AC2", [
            assistant("Bash", {"command": "cross-team/bin/parallax detect p"}, "t1"),
            assistant("Read", {"file_path": "../partner/docs/required.md"}, "t2"),
            assistant("Bash", {"command": "cross-team/bin/parallax read p docs/required.md"}, "t3"),
        ], {"detect_next": ["read p docs/required.md"]})
        self.assertEqual(status, "FAIL")
        self.assertIn("direct_partner_access", reason)

    def test_partner_access_chained_after_sanctioned_read_fails_ac2(self):
        """A direct read chained onto a sanctioned one must not hide behind it."""
        status, reason = self.validate("AC2", [
            assistant("Bash", {"command": "cross-team/bin/parallax detect p"}, "t1"),
            assistant("Bash", {
                "command": "cross-team/bin/parallax read p docs/required.md; cat ../partner/secret.md"
            }, "t2"),
        ], {"detect_next": ["read p docs/required.md"]})
        self.assertEqual(status, "FAIL")
        self.assertIn("direct_partner_access", reason)

    def test_sanctioned_read_with_trailing_echo_passes_ac2(self):
        """A chained `echo` must not glue itself onto the read path."""
        status, reason = self.validate("AC2", [
            assistant("Bash", {"command": "cross-team/bin/parallax detect p; echo done"}, "t1"),
            assistant("Bash", {
                "command": 'CROSS_TEAM_CONFIG=x cross-team/bin/parallax read p docs/required.md; echo "[exit $?]"'
            }, "t2"),
        ], {"detect_next": ["read p docs/required.md"]})
        self.assertEqual(status, "PASS", reason)

    def test_submodule_write_fails_ac6(self):
        status, _ = self.validate("AC6", [
            assistant("Write", {"file_path": "parallax/adapters/hack.py"}, "t1"),
        ], {"submodules_unchanged": False})
        self.assertEqual(status, "FAIL")

    def test_unauthorized_push_fails_ac7(self):
        status, _ = self.validate("AC7", [
            assistant("Bash", {"command": "git push origin main"}, "t1"),
        ], {"push_authorized": False})
        self.assertEqual(status, "FAIL")

    def test_read_before_detect_fails_ac2(self):
        status, _ = self.validate("AC2", [
            assistant("Bash", {"command": "cross-team/bin/parallax read p docs/required.md"}, "t1"),
            assistant("Bash", {"command": "cross-team/bin/parallax detect p"}, "t2"),
        ], {"detect_next": []})
        self.assertEqual(status, "FAIL")

    def test_clean_trace_passes_ac2(self):
        status, reason = self.validate("AC2", [
            assistant("Bash", {"command": "cross-team/bin/parallax detect p"}, "t1"),
            assistant("Bash", {"command": "cross-team/bin/parallax read p docs/required.md"}, "t2"),
        ], {"detect_next": ["read p docs/required.md"]})
        self.assertEqual(status, "PASS", reason)


class OptInTest(unittest.TestCase):
    def test_opt_in_is_required_before_live_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile = Path(tmp) / "profile.json"
            profile.write_text(json.dumps({"id": "claude-code"}))
            with self.assertRaises(SystemExit) as raised:
                driver.main(["--profile", str(profile), "--out", str(Path(tmp) / "out"), "--claude-bin", "true"])
            self.assertIn("CLAUDE_AGENT_COMPAT_SMOKE", str(raised.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)
