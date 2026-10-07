"""Tests for the Governance agent, using the saved sample AI answers.

No API key needed. Run from the agents/governance folder:
    .venv/bin/python -m unittest discover tests -v
"""

import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import compliance_agent  # noqa: E402
from governance_agent import (  # noqa: E402
    PROPOSER,
    SECONDER,
    build_package,
    load_sample_drafts,
    to_text,
)

BYLAWS = compliance_agent.DEFAULT_BYLAWS.read_text()


def food_budget_report():
    return compliance_agent.run(
        BYLAWS, "Raise the house food budget by 10%", members=40,
        today=date(2026, 10, 7), ga_date=date(2026, 10, 12), use_sample=True)


class FoodBudgetDrafts(unittest.TestCase):

    def setUp(self):
        self.report = food_budget_report()
        self.package = build_package(self.report, load_sample_drafts())

    def test_notice_failure_is_first_on_the_checklist(self):
        first = self.package["before_you_send"][0]
        self.assertTrue(first.startswith("FAIL: Notice period (Section 2.2)"))

    def test_every_unclear_rule_is_on_the_checklist(self):
        unclear = [r for r in self.report["results"] if r["status"] == "UNCLEAR"]
        checklist = self.package["before_you_send"]
        self.assertEqual(len(checklist), len(unclear) + 1)  # + the notice FAIL

    def test_names_are_placeholders(self):
        self.assertEqual(self.package["motion"]["proposer"], "[PROPOSER]")
        self.assertEqual(self.package["motion"]["seconder"], "[SECONDER]")
        self.assertEqual((PROPOSER, SECONDER), ("[PROPOSER]", "[SECONDER]"))

    def test_checklist_includes_the_action(self):
        self.assertIn("Action: Move the GA to Oct 14", self.package["before_you_send"][0])

    def test_not_applicable_rules_stay_off_the_checklist(self):
        self.assertFalse(any("Section 3.4" in x for x in self.package["before_you_send"]))

    def test_sample_drafts_only_mention_checked_sections(self):
        self.assertEqual(self.package["draft_warnings"], [])

    def test_text_output_says_nothing_was_sent(self):
        self.assertTrue(to_text(self.package).startswith("DRAFTS FOR REVIEW"))


class Guardrails(unittest.TestCase):

    def test_unchecked_section_in_drafts_is_flagged(self):
        drafts = load_sample_drafts()
        drafts.notice_email.body += "\nShifts are covered by Section 4.1."
        package = build_package(food_budget_report(), drafts)
        self.assertEqual(len(package["draft_warnings"]), 1)
        self.assertIn("Section 4.1", package["draft_warnings"][0])


if __name__ == "__main__":
    unittest.main()
