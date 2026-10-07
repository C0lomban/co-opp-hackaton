"""Tests for the Bylaws & Compliance agent, using the saved sample AI answer.

No API key needed. Run from the agents/governance folder:
    .venv/bin/python -m unittest discover tests -v
"""

import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from compliance_agent import (  # noqa: E402
    DEFAULT_BYLAWS,
    check_compliance,
    load_sample_extraction,
    quote_is_real,
)

BYLAWS = DEFAULT_BYLAWS.read_text()
TODAY = date(2026, 10, 7)
GA = date(2026, 10, 12)


def by_rule(results):
    return {r["rule"]: r for r in results}


class FoodBudgetCase(unittest.TestCase):
    """40 members, today Oct 7, GA Oct 12, raise food budget by 10%."""

    def setUp(self):
        self.results = by_rule(check_compliance(
            BYLAWS, load_sample_extraction(), members=40, today=TODAY, ga_date=GA))

    def test_notice_period_fails(self):
        r = self.results["Notice period"]
        self.assertEqual(r["verdict"], "FAIL")
        self.assertEqual(r["bylaw_section"], "Section 2.2")
        self.assertEqual(r["computed"]["days_available"], 5)
        self.assertEqual(r["computed"]["days_required"], 7)

    def test_quorum_is_21(self):
        r = self.results["Quorum"]
        self.assertEqual(r["verdict"], "UNCLEAR")
        self.assertEqual(r["computed"]["quorum_needed"], 21)

    def test_finance_review_due_oct_9(self):
        r = self.results["Committee review"]
        self.assertEqual(r["verdict"], "UNCLEAR")
        self.assertEqual(r["computed"]["review_deadline"], "2026-10-09")

    def test_vote_threshold_is_unclear_with_both_readings(self):
        r = self.results["Vote threshold"]
        self.assertEqual(r["verdict"], "UNCLEAR")
        self.assertEqual(r["bylaw_section"], "Section 3.3")
        self.assertEqual(r["computed"]["votes_needed_if_all_members"], 27)
        self.assertEqual(r["computed"]["votes_needed_if_quorum_present"], 14)

    def test_every_result_has_the_required_fields(self):
        for r in self.results.values():
            self.assertEqual(
                {"rule", "verdict", "bylaw_section", "quote", "explanation"} - r.keys(),
                set())
            self.assertIn(r["verdict"], {"PASS", "FAIL", "UNCLEAR"})


class Guardrails(unittest.TestCase):

    def test_real_quote_is_found_even_across_line_breaks(self):
        # In the file, this sentence is split over two lines.
        self.assertTrue(quote_is_real(
            "Written notice of the agenda must be sent to all members at least "
            "7 days before a regular GA.", BYLAWS))

    def test_invented_quote_is_rejected(self):
        self.assertFalse(quote_is_real("Quorum is 30 percent of members.", BYLAWS))

    def test_invented_quote_makes_rule_unclear(self):
        extraction = load_sample_extraction()
        notice = next(r for r in extraction.rules if r.kind == "notice_period")
        notice.quote = "Notice must be sent 2 days before a GA."
        results = by_rule(check_compliance(BYLAWS, extraction, 40, TODAY, GA))
        self.assertEqual(results["Notice period"]["verdict"], "UNCLEAR")

    def test_missing_rule_is_reported_as_unclear(self):
        extraction = load_sample_extraction()
        extraction.rules = [r for r in extraction.rules if r.kind != "quorum"]
        results = by_rule(check_compliance(BYLAWS, extraction, 40, TODAY, GA))
        self.assertEqual(results["Quorum"]["verdict"], "UNCLEAR")
        self.assertIsNone(results["Quorum"]["bylaw_section"])

    def test_small_budget_change_uses_ordinary_threshold(self):
        extraction = load_sample_extraction()
        extraction.proposal.budget_change_percent = 3
        results = by_rule(check_compliance(BYLAWS, extraction, 40, TODAY, GA))
        self.assertEqual(results["Vote threshold"]["bylaw_section"], "Section 3.2")
        self.assertNotIn("Committee review", results)


if __name__ == "__main__":
    unittest.main()
