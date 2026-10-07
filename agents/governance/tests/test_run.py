"""End-to-end test of the orchestrator: both agents, saved files and evidence.

Uses the saved sample AI answers, so no Kylon key is needed. Evidence is
always written to a temporary folder, never to the team's real one.
"""

import json
import os
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import compliance_agent  # noqa: E402
import run  # noqa: E402
from run import choose_evidence_dir, run_pipeline  # noqa: E402

TEMPLATE = run.TEAM_EVIDENCE / "template.json"


def food_budget(tmp: Path, **kwargs) -> Path:
    return run_pipeline(
        compliance_agent.DEFAULT_BYLAWS, "Raise the house food budget by 10%",
        members=40, today=date(2026, 10, 7), ga_date=date(2026, 10, 12),
        use_sample=True, out_root=tmp / "outputs", **kwargs)


class FoodBudgetRun(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.tmp = Path(self.tmp_dir.name)
        self.evidence = self.tmp / "evidence"
        self.folder = food_budget(self.tmp, evidence_dir=self.evidence)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_all_files_are_saved(self):
        for name in ["compliance.json", "drafts.json", "drafts.txt", "log.json"]:
            self.assertTrue((self.folder / name).exists(), name)

    def test_evidence_files_follow_team_readme_and_template(self):
        files = sorted(self.evidence.glob("*.json"))
        # YYYYMMDD-HHMM-<agent>.json
        self.assertEqual(len(files), 2)
        for f, agent in zip(files, ["compliance", "governance"]):
            day, time, slug = f.stem.split("-", 2)
            self.assertEqual((len(day), len(time), slug), (8, 4, agent))
        template = json.loads(TEMPLATE.read_text())
        for f in files:
            record = json.loads(f.read_text())
            self.assertEqual(set(template) - record.keys(), set(), f.name)
            self.assertEqual(record["status"], "ok")
            self.assertIn("PRACTICE RUN", record["notes"])

    def test_second_run_in_same_minute_does_not_overwrite(self):
        food_budget(self.tmp, evidence_dir=self.evidence)
        self.assertEqual(len(list(self.evidence.glob("*.json"))), 4)

    def test_expected_results(self):
        report = json.loads((self.folder / "compliance.json").read_text())
        results = {r["rule"]: r for r in report["results"]}
        self.assertEqual(results["Notice period"]["status"], "FAIL")
        self.assertEqual(results["Quorum"]["computed"]["quorum_needed"], 21)
        self.assertEqual(results["Committee review"]["computed"]["review_deadline"], "2026-10-09")
        self.assertEqual(results["Vote threshold"]["status"], "UNCLEAR")
        self.assertEqual(results["Vote threshold"]["section"], "Section 3.3")

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


class EvidenceFolder(unittest.TestCase):

    def test_flag_wins_over_environment(self):
        with mock.patch.dict(os.environ, {"EVIDENCE_DIR": "/from/env"}):
            self.assertEqual(choose_evidence_dir(Path("/from/flag"), False, Path("/run")),
                             Path("/from/flag"))

    def test_environment_used_without_flag(self):
        with mock.patch.dict(os.environ, {"EVIDENCE_DIR": "/from/env"}):
            self.assertEqual(choose_evidence_dir(None, True, Path("/run")), Path("/from/env"))

    def test_relative_environment_path_is_relative_to_agent_folder(self):
        with mock.patch.dict(os.environ, {"EVIDENCE_DIR": "../../orchestration/evidence"}):
            chosen = choose_evidence_dir(None, False, Path("/run")).resolve()
        self.assertEqual(chosen, run.TEAM_EVIDENCE.resolve())

    def test_live_runs_default_to_team_folder(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(choose_evidence_dir(None, False, Path("/run")), run.TEAM_EVIDENCE)

    def test_practice_runs_default_to_their_own_folder(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(choose_evidence_dir(None, True, Path("/run")),
                             Path("/run/evidence"))


class FailedRun(unittest.TestCase):

    def test_failure_is_saved_as_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            evidence = Path(tmp) / "evidence"
            with self.assertRaises(FileNotFoundError):
                run_pipeline(Path("no-such-bylaws.txt"), "x", 40, date(2026, 10, 7),
                             date(2026, 10, 12), use_sample=True,
                             out_root=Path(tmp) / "outputs", evidence_dir=evidence)
            records = [json.loads(f.read_text()) for f in evidence.glob("*.json")]
            self.assertEqual([r["status"] for r in records], ["error"])
            self.assertEqual(records[0]["agent"], "Bylaws & Compliance Agent")
            log_file = next((Path(tmp) / "outputs").glob("*/log.json"))
            events = [e["event"] for e in json.loads(log_file.read_text())]
            self.assertIn("failed", events)


class SampleModeNeedsNoKey(unittest.TestCase):

    def test_sample_run_works_with_no_keys_at_all(self):
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.dict(os.environ, {}, clear=True), \
                mock.patch("ai_client.ENV_FILE", Path(tmp) / "missing.env"):
            folder = food_budget(Path(tmp), evidence_dir=Path(tmp) / "evidence")
            self.assertTrue((folder / "drafts.txt").exists())


if __name__ == "__main__":
    unittest.main()
