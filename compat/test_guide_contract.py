#!/usr/bin/env python3
"""Validate AGENTS.md rule IDs against the compatibility contract."""
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPAT = ROOT / "compat"


class GuideContractTest(unittest.TestCase):
    def setUp(self):
        self.guide = (ROOT / "AGENTS.md").read_text()
        self.contract = json.loads((COMPAT / "guide_contract.json").read_text())
        self.scenarios = {}
        for path in sorted((COMPAT / "scenarios").glob("*.json")):
            scenario = json.loads(path.read_text())
            self.scenarios[scenario["id"]] = scenario

    def test_rule_ids_are_visible_once_in_agents_md(self):
        rule_ids = set(self.contract["rules"])
        found = re.findall(r"\[(AG\d{2})\]", self.guide)
        self.assertEqual(set(found), rule_ids)
        for rule_id in sorted(rule_ids):
            self.assertEqual(found.count(rule_id), 1, rule_id)

    def test_hard_rules_have_scenarios(self):
        scenario_ids = set(self.scenarios)
        for rule_id, rule in self.contract["rules"].items():
            self.assertRegex(rule_id, r"^AG\d{2}$")
            self.assertEqual(rule.get("severity"), "hard")
            self.assertNotIn("text", rule)
            self.assertNotIn("rule", rule)
            self.assertTrue(rule.get("scenarios"), rule_id)
            for scenario_id in rule["scenarios"]:
                self.assertIn(scenario_id, scenario_ids, (rule_id, scenario_id))

    def test_scenarios_reference_existing_rules(self):
        rule_ids = set(self.contract["rules"])
        for scenario_id, scenario in self.scenarios.items():
            self.assertEqual(scenario["id"], scenario_id)
            for field in ("rules", "prompt_fixture", "requires",
                          "required_events", "forbidden_events", "expected_repo_state"):
                self.assertIn(field, scenario, scenario_id)
            for rule_id in scenario["rules"]:
                self.assertIn(rule_id, rule_ids, (scenario_id, rule_id))

    def test_all_hard_rules_are_covered_by_at_least_one_scenario(self):
        covered = set()
        for scenario in self.scenarios.values():
            covered.update(scenario["rules"])
        missing = sorted(set(self.contract["rules"]) - covered)
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
