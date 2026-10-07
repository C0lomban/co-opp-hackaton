"""End-to-end test of the orchestrator: both agents, saved files and log.

Uses the saved sample AI answers, so no API key is needed.
"""

import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import compliance_agent  # noqa: E402
from run import run_pipeline  # noqa: E402


class FoodBudgetRun(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = run_pipeline(
            compliance_agent.DEFAULT_BYLAWS, "Raise the house food budget by 10%",
            members=40, today=date(2026, 10, 7), ga_date=date(2026, 10, 12),
            use_sample=True, out_root=Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_all_files_are_saved(self):
        for name in ["compliance.json", "drafts.json", "drafts.txt", "log.json"]:
            self.assertTrue((self.folder / name).exists(), name)

    def test_expected_results(self):
        results = {r["rule"]: r for r in
                   json.loads((self.folder / "compliance.json").read_text())["results"]}
        self.assertEqual(results["Notice period"]["verdict"], "FAIL")
        self.assertEqual(results["Quorum"]["computed"]["quorum_needed"], 21)
        self.assertEqual(results["Committee review"]["computed"]["review_deadline"], "2026-10-09")
        self.assertEqual(results["Vote threshold"]["verdict"], "UNCLEAR")

    def test_log_shows_each_agent_in_order(self):
        log = json.loads((self.folder / "log.json").read_text())
        steps = [(e["agent"], e["event"]) for e in log]
        self.assertEqual(steps, [
            ("orchestrator", "started"),
            ("compliance", "finished"),
            ("governance", "finished"),
            ("orchestrator", "saved"),
        ])
        self.assertEqual(log[1]["details"]["failed_rules"], ["Notice period"])


class FailedRun(unittest.TestCase):

    def test_log_is_saved_even_when_a_step_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                run_pipeline(Path("no-such-bylaws.txt"), "x", 40, date(2026, 10, 7),
                             date(2026, 10, 12), use_sample=True, out_root=Path(tmp))
            log_file = next(Path(tmp).glob("*/log.json"))
            events = [e["event"] for e in json.loads(log_file.read_text())]
            self.assertIn("failed", events)


if __name__ == "__main__":
    unittest.main()
