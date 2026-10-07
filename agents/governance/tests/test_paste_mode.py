"""Tests for paste mode: prompt files and pasted Kylon agent answers.

No API key or network needed.
"""

import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import compliance_agent  # noqa: E402
import governance_agent  # noqa: E402
import run  # noqa: E402
from paste_mode import PastedAnswerError, parse_pasted_answer  # noqa: E402

BYLAWS_PATH = compliance_agent.DEFAULT_BYLAWS
BYLAWS = BYLAWS_PATH.read_text()
PROPOSAL = "Raise the house food budget by 10%"
TODAY, GA = date(2026, 10, 7), date(2026, 10, 12)
SAMPLE_EXTRACTION = compliance_agent.SAMPLE_EXTRACTION.read_text()
SAMPLE_DRAFTS = governance_agent.SAMPLE_DRAFTS.read_text()


class TempDir(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, name: str, text: str) -> Path:
        path = self.tmp / name
        path.write_text(text)
        return path


class CompliancePrompt(unittest.TestCase):

    def setUp(self):
        self.prompt = compliance_agent.paste_prompt(BYLAWS, PROPOSAL, 40, TODAY, GA)

    def test_contains_bylaws_facts_proposal_and_format(self):
        self.assertIn("Quorum is 50 percent of voting members plus one.", self.prompt)
        self.assertIn("Days from today to the GA: 5", self.prompt)
        self.assertIn("Voting members: 40", self.prompt)
        self.assertIn(PROPOSAL, self.prompt)
        self.assertIn("JSON Schema", self.prompt)
        for field in ["notice_period", "vote_base", "budget_change_percent", "quote"]:
            self.assertIn(field, self.prompt)

    def test_is_exactly_what_a_live_call_sends(self):
        with mock.patch("compliance_agent.ask_claude") as ask:
            ask.return_value = compliance_agent.load_sample_extraction()
            compliance_agent.run(BYLAWS, PROPOSAL, 40, TODAY, GA)
        system, message, _ = ask.call_args.args
        self.assertTrue(self.prompt.startswith(system.strip() + "\n\n" + message.strip()))


class PastedComplianceAnswer(TempDir):

    def report(self, answer_text: str) -> dict:
        return compliance_agent.run(BYLAWS, PROPOSAL, 40, TODAY, GA,
                                    answer_file=self.write("answer.json", answer_text))

    def test_same_results_as_sample(self):
        pasted = self.report(SAMPLE_EXTRACTION)
        sample = compliance_agent.run(BYLAWS, PROPOSAL, 40, TODAY, GA, use_sample=True)
        self.assertEqual(pasted["results"], sample["results"])
        self.assertEqual(pasted["source"], "kylon-agent-pasted")

    def test_code_fences_and_chatter_are_ignored(self):
        text = f"Here is the JSON you asked for:\n```json\n{SAMPLE_EXTRACTION}\n```\nThanks!"
        self.assertEqual(len(self.report(text)["results"]), 6)

    def test_invented_quote_becomes_unclear(self):
        data = json.loads(SAMPLE_EXTRACTION)
        data["rules"][0]["quote"] = "Notice must be sent 2 days before a GA."
        results = {r["rule"]: r for r in self.report(json.dumps(data))["results"]}
        self.assertEqual(results["Notice period"]["status"], "UNCLEAR")

    def test_statuses_come_from_code_only(self):
        # Even if the agent adds its own "status", code decides.
        data = json.loads(SAMPLE_EXTRACTION)
        data["rules"][0]["status"] = "PASS"
        results = {r["rule"]: r for r in self.report(json.dumps(data))["results"]}
        self.assertEqual(results["Notice period"]["status"], "FAIL")
        self.assertTrue(all(r["status"] in {"PASS", "FAIL", "UNCLEAR"}
                            for r in self.report(json.dumps(data))["results"]))

    def test_not_json(self):
        with self.assertRaisesRegex(PastedAnswerError, "doesn't contain a JSON object"):
            self.report("Sorry, I can't help with that.")

    def test_broken_json(self):
        with self.assertRaisesRegex(PastedAnswerError, "not valid JSON"):
            self.report('{"rules": [}')

    def test_wrong_type_names_the_field(self):
        data = json.loads(SAMPLE_EXTRACTION)
        data["rules"][0]["days"] = "seven"
        with self.assertRaisesRegex(PastedAnswerError, r"rules\[0\]\.days"):
            self.report(json.dumps(data))

    def test_unknown_rule_kind_is_rejected(self):
        data = json.loads(SAMPLE_EXTRACTION)
        data["rules"][0]["kind"] = "parking_rules"
        with self.assertRaisesRegex(PastedAnswerError, r"rules\[0\]\.kind"):
            self.report(json.dumps(data))

    def test_missing_field_is_rejected(self):
        data = json.loads(SAMPLE_EXTRACTION)
        del data["proposal"]
        with self.assertRaisesRegex(PastedAnswerError, "proposal"):
            self.report(json.dumps(data))

    def test_sample_and_answer_file_together_is_an_error(self):
        with self.assertRaises(ValueError):
            compliance_agent.run(BYLAWS, PROPOSAL, 40, TODAY, GA, use_sample=True,
                                 answer_file=self.write("a.json", SAMPLE_EXTRACTION))


class GovernancePasteMode(TempDir):

    def setUp(self):
        super().setUp()
        self.report = compliance_agent.run(BYLAWS, PROPOSAL, 40, TODAY, GA, use_sample=True)

    def test_prompt_contains_bylaw_check_and_format(self):
        prompt = governance_agent.paste_prompt(self.report)
        self.assertIn("Section 2.2", prompt)
        self.assertIn('"status": "FAIL"', prompt)
        self.assertIn("notice_email", prompt)
        self.assertIn("JSON Schema", prompt)

    def test_prompt_is_exactly_what_a_live_call_sends(self):
        with mock.patch("governance_agent.ask_claude") as ask:
            ask.return_value = governance_agent.load_sample_drafts()
            governance_agent.run(self.report)
        system, message, _ = ask.call_args.args
        self.assertTrue(governance_agent.paste_prompt(self.report)
                        .startswith(system.strip() + "\n\n" + message.strip()))

    def test_pasted_drafts_get_same_checks_as_sample(self):
        pasted = governance_agent.run(self.report,
                                      answer_file=self.write("d.json", SAMPLE_DRAFTS))
        sample = governance_agent.run(self.report, use_sample=True)
        self.assertEqual(pasted["source"], "kylon-agent-pasted")
        for key in ["before_you_send", "draft_warnings", "motion", "agenda", "notice_email"]:
            self.assertEqual(pasted[key], sample[key], key)
        self.assertEqual(pasted["motion"]["proposer"], "[PROPOSER]")

    def test_unchecked_section_in_pasted_drafts_is_flagged(self):
        data = json.loads(SAMPLE_DRAFTS)
        data["notice_email"]["body"] += " See Section 4.1."
        pasted = governance_agent.run(self.report,
                                      answer_file=self.write("d.json", json.dumps(data)))
        self.assertIn("Section 4.1", pasted["draft_warnings"][0])

    def test_bad_drafts_are_rejected(self):
        data = json.loads(SAMPLE_DRAFTS)
        data["agenda"][0]["minutes"] = "a few"
        with self.assertRaisesRegex(PastedAnswerError, r"agenda\[0\]\.minutes"):
            governance_agent.run(self.report, answer_file=self.write("d.json", json.dumps(data)))


class OrchestratorPasteMode(TempDir):

    def test_next_prompt_is_compliance_then_governance(self):
        step = run.write_next_prompt(self.tmp / "p1.txt", BYLAWS_PATH, PROPOSAL, 40, TODAY, GA)
        self.assertEqual(step, "compliance")
        self.assertIn("<bylaws>", (self.tmp / "p1.txt").read_text())

        answer = self.write("c.json", SAMPLE_EXTRACTION)
        step = run.write_next_prompt(self.tmp / "p2.txt", BYLAWS_PATH, PROPOSAL, 40, TODAY,
                                     GA, compliance_answer_file=answer)
        self.assertEqual(step, "governance")
        self.assertIn("<bylaw_check>", (self.tmp / "p2.txt").read_text())

    def test_pasted_run_records_honest_source_in_evidence(self):
        evidence = self.tmp / "evidence"
        run.run_pipeline(BYLAWS_PATH, PROPOSAL, 40, TODAY, GA,
                         out_root=self.tmp / "outputs", evidence_dir=evidence,
                         compliance_answer_file=self.write("c.json", SAMPLE_EXTRACTION),
                         governance_answer_file=self.write("g.json", SAMPLE_DRAFTS))
        records = [json.loads(f.read_text()) for f in sorted(evidence.glob("*.json"))]
        self.assertEqual([r["source"] for r in records],
                         ["kylon-agent-pasted", "kylon-agent-pasted"])
        for r in records:
            self.assertIn("pasted by a human", r["tool"])
            self.assertNotIn("PRACTICE", r["notes"])

    def test_pasted_runs_default_to_team_evidence_folder(self):
        # Pasted answers are real agent output, unlike --use-sample.
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertEqual(run.choose_evidence_dir(None, False, self.tmp), run.TEAM_EVIDENCE)

    def test_sample_run_evidence_says_sample(self):
        evidence = self.tmp / "evidence"
        run.run_pipeline(BYLAWS_PATH, PROPOSAL, 40, TODAY, GA, use_sample=True,
                         out_root=self.tmp / "outputs", evidence_dir=evidence)
        sources = {json.loads(f.read_text())["source"] for f in evidence.glob("*.json")}
        self.assertEqual(sources, {"sample"})

    def test_bad_pasted_answer_is_recorded_as_error(self):
        evidence = self.tmp / "evidence"
        with self.assertRaises(PastedAnswerError):
            run.run_pipeline(BYLAWS_PATH, PROPOSAL, 40, TODAY, GA,
                             out_root=self.tmp / "outputs", evidence_dir=evidence,
                             compliance_answer_file=self.write("c.json", "not json"))
        [record] = [json.loads(f.read_text()) for f in evidence.glob("*.json")]
        self.assertEqual((record["status"], record["source"]), ("error", "kylon-agent-pasted"))
        self.assertIn("JSON", record["notes"])

    def test_sample_and_answer_files_together_is_an_error(self):
        with self.assertRaises(ValueError):
            run.run_pipeline(BYLAWS_PATH, PROPOSAL, 40, TODAY, GA, use_sample=True,
                             out_root=self.tmp / "outputs", evidence_dir=self.tmp / "e",
                             compliance_answer_file=self.write("c.json", SAMPLE_EXTRACTION))


class ParseHelper(unittest.TestCase):

    def test_error_lists_every_problem(self):
        data = json.loads(SAMPLE_EXTRACTION)
        data["rules"][0]["days"] = "seven"
        data["rules"][1]["percent"] = "half"
        with self.assertRaises(PastedAnswerError) as caught:
            parse_pasted_answer(json.dumps(data), compliance_agent.Extraction)
        self.assertIn("rules[0].days", str(caught.exception))
        self.assertIn("rules[1].percent", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
