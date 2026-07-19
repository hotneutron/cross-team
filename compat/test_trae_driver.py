#!/usr/bin/env python3
"""Platform-independent tests for the TRAE compatibility driver."""
import importlib.util
import tempfile
import unittest
from pathlib import Path


DRIVER_PATH = Path(__file__).parent / "drivers" / "trae-agent" / "run_agent_compat.py"
SPEC = importlib.util.spec_from_file_location("trae_agent_driver", DRIVER_PATH)
driver = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(driver)


class ScenarioStateTest(unittest.TestCase):
    def _ac9_consumer(self, tmp, commit_append):
        consumer = Path(tmp) / "consumer"
        consumer.mkdir()
        driver.configure_repository(consumer)
        (consumer / ".plan").mkdir()
        ledger = consumer / ".plan" / "sync-ledger.md"
        prior = driver.sync_ledger()
        ledger.write_text(prior, encoding="utf-8")
        driver.commit_all(consumer, "seed ledger")
        ledger.write_text(
            prior
            + "\n## close p\n"
            + "partner HEAD: abc1234\n"
            + "reads: .plan/required.md\n"
            + "responding artifacts: .plan/reaction.md\n"
            + "open obligations: none\n",
            encoding="utf-8",
        )
        if commit_append:
            driver.commit_all(consumer, "close sync")
        before = {"ledger": prior, "partner_head": "abc1234def5678"}
        return driver.scenario_state("AC9", consumer, before, [])

    def test_ac9_committed_ledger_append_closes_sync(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = self._ac9_consumer(tmp, commit_append=True)
            self.assertTrue(all(state.values()), state)

    def test_ac9_uncommitted_ledger_append_is_not_closure(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = self._ac9_consumer(tmp, commit_append=False)
            self.assertTrue(state["ledger_entry_appended"])
            self.assertFalse(state["ledger_committed_clean"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
