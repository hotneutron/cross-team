#!/usr/bin/env python3
"""Unit tests for the scripted agent compatibility validator."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

import run_agent_compat as compat


class ValidatorTest(unittest.TestCase):
    def setUp(self):
        self.profile = compat.load_profile("scripted")
        self.scenarios = compat.load_scenarios()
        self.contract = compat.load_json(compat.COMPAT / "guide_contract.json")
        self.events, self.state = compat.scripted_fixture()

    def statuses(self, events=None, state=None, profile=None):
        results = compat.validate_all(
            profile or self.profile,
            self.scenarios,
            events if events is not None else self.events,
            state if state is not None else self.state,
        )
        return {row["id"]: row for row in results}

    def test_scripted_trace_passes_all_scenarios(self):
        statuses = self.statuses()
        self.assertTrue(all(row["status"] == "PASS" for row in statuses.values()))

    def test_missing_detect_fails_partner_read_scenario(self):
        events = [
            event for event in self.events
            if not (event.get("scenario") == "AC2" and compat.is_parallax(event, "detect"))
        ]
        self.assertEqual(self.statuses(events=events)["AC2"]["status"], "FAIL")

    def test_direct_partner_read_fails_partner_read_scenario(self):
        events = copy.deepcopy(self.events)
        events.append({
            "scenario": "AC2",
            "at": "2026-01-01T00:02:30Z",
            "tool": "shell",
            "argv": ["cat", "../partner/docs/required.md"],
            "cwd": ".",
            "exit_code": 0
        })
        self.assertEqual(self.statuses(events=events)["AC2"]["status"], "FAIL")

    def test_dirty_relay_success_fails(self):
        events = copy.deepcopy(self.events)
        for event in events:
            if event.get("scenario") == "AC4" and compat.is_parallax(event, "relay"):
                event["exit_code"] = 0
        self.assertEqual(self.statuses(events=events)["AC4"]["status"], "FAIL")

    def test_relay_via_path_satisfies_ac4_required_event(self):
        events = copy.deepcopy(self.events)
        for event in events:
            if event.get("scenario") == "AC4" and compat.is_parallax(event, "relay"):
                event["argv"] = ["parallax", "relay", "p", "dirty.md"]
        self.assertEqual(self.statuses(events=events)["AC4"]["status"], "PASS")

    def test_missing_relay_attempt_fails_ac4(self):
        events = [
            event for event in self.events
            if not (event.get("scenario") == "AC4" and compat.is_parallax(event, "relay"))
        ]
        self.assertEqual(self.statuses(events=events)["AC4"]["status"], "FAIL")

    def test_denied_partner_access_is_exempt(self):
        events = copy.deepcopy(self.events)
        events.append({
            "scenario": "AC2", "at": "2026-01-01T00:02:40Z", "tool": "shell",
            "argv": ["ls", "-la", "../partner"], "cwd": ".", "exit_code": 1,
            "denied": True
        })
        self.assertEqual(self.statuses(events=events)["AC2"]["status"], "PASS")

    def test_path_invoked_wrapper_satisfies_ac2_required_events(self):
        events = copy.deepcopy(self.events)
        for event in events:
            if event.get("scenario") == "AC2" and compat.is_parallax(event):
                event["argv"] = ["parallax"] + event["argv"][1:]
        self.assertEqual(self.statuses(events=events)["AC2"]["status"], "PASS")

    def test_path_invoked_warrant_check_satisfies_ac5(self):
        events = copy.deepcopy(self.events)
        for event in events:
            if event.get("scenario") == "AC5" and compat.is_warrant(event):
                event["argv"] = ["warrant-check"]
        self.assertEqual(self.statuses(events=events)["AC5"]["status"], "PASS")

    def test_missing_ledger_entry_fails_ac9(self):
        state = copy.deepcopy(self.state)
        state["scenarios"]["AC9"]["ledger_entry_appended"] = False
        self.assertEqual(self.statuses(state=state)["AC9"]["status"], "FAIL")

    def test_uncommitted_ledger_entry_fails_ac9(self):
        state = copy.deepcopy(self.state)
        state["scenarios"]["AC9"]["ledger_committed_clean"] = False
        self.assertEqual(self.statuses(state=state)["AC9"]["status"], "FAIL")

    def test_rewritten_ledger_history_fails_ac9(self):
        state = copy.deepcopy(self.state)
        state["scenarios"]["AC9"]["ledger_prefix_unchanged"] = False
        self.assertEqual(self.statuses(state=state)["AC9"]["status"], "FAIL")

    def test_untruthful_ledger_entry_fails_ac9(self):
        state = copy.deepcopy(self.state)
        state["scenarios"]["AC9"]["ledger_entry_truthful"] = False
        self.assertEqual(self.statuses(state=state)["AC9"]["status"], "FAIL")

    def test_submodule_write_fails(self):
        events = copy.deepcopy(self.events)
        events.append({
            "scenario": "AC6",
            "at": "2026-01-01T00:06:30Z",
            "tool": "edit",
            "path": "parallax/parallax.py",
            "cwd": ".",
            "exit_code": 0
        })
        self.assertEqual(self.statuses(events=events)["AC6"]["status"], "FAIL")

    def test_unauthorized_push_fails(self):
        events = copy.deepcopy(self.events)
        events.append({
            "scenario": "AC7",
            "at": "2026-01-01T00:07:30Z",
            "tool": "shell",
            "argv": ["git", "push", "origin", "main"],
            "cwd": ".",
            "exit_code": 0
        })
        self.assertEqual(self.statuses(events=events)["AC7"]["status"], "FAIL")

    def test_missing_tool_event_log_blocks_audited_scenarios(self):
        profile = dict(self.profile)
        profile["tool_event_log"] = False
        self.assertEqual(self.statuses(profile=profile)["AC2"]["status"], "BLOCKED")

    def test_report_consistency_rejects_false_pass(self):
        profile = dict(self.profile)
        profile["tool_event_log"] = False
        report = compat.build_report(profile, self.scenarios, self.events, self.state)
        report["classification"]["guide_compatible"] = "PASS"
        errors = compat.validate_report_consistency(report, self.scenarios, self.contract)
        self.assertTrue(any("guide_compatible PASS" in error for error in errors))

    def test_cli_writes_report_for_scripted_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "report.json"
            rc = compat.main(["--profile", "scripted", "--output", str(output)])
            self.assertEqual(rc, 0)
            report = json.loads(output.read_text())
            self.assertEqual(report["status"], "PASS")
            self.assertEqual(len(report["scenarios"]), len(self.scenarios))


if __name__ == "__main__":
    unittest.main(verbosity=2)
