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


def check(extraction=None, ga_date=None):
    return check_compliance(BYLAWS, extraction or load_sample_extraction(),
                            40, TODAY, ga_date or GA)


def by_rule(checks):
    """The results, keyed by rule name."""
    return {r["rule"]: r for r in checks["results"]}


def skipped(checks):
    """Rules that don't apply, keyed by section."""
    return {r["section"]: r for r in checks["not_applicable"]}


class FoodBudgetCase(unittest.TestCase):
    """40 members, today Oct 7, GA Oct 12, raise food budget by 10%.
    Matches orchestration/expected-test-1.md."""

    def setUp(self):
        self.checks = check()
        self.results = by_rule(self.checks)

    def test_notice_period_fails(self):
        r = self.results["Notice period"]
        self.assertEqual(r["status"], "FAIL")
        self.assertEqual(r["section"], "Section 2.2")
        self.assertEqual(r["computed"]["days_available"], 5)
        self.assertEqual(r["computed"]["days_required"], 7)
        self.assertIn("Oct 14", r["action_needed"])

    def test_quorum_is_21(self):
        r = self.results["Quorum"]
        self.assertEqual(r["status"], "UNCLEAR")
        self.assertEqual(r["computed"]["quorum_needed"], 21)

    def test_finance_review_due_oct_9(self):
        r = self.results["Committee review"]
        self.assertEqual(r["status"], "UNCLEAR")
        self.assertEqual(r["computed"]["review_deadline"], "2026-10-09")

    def test_vote_threshold_is_unclear_with_both_readings(self):
        r = self.results["Vote threshold"]
        self.assertEqual(r["status"], "UNCLEAR")
        self.assertEqual(r["section"], "Section 3.3")
        self.assertEqual(r["computed"]["votes_needed_if_all_members"], 27)
        self.assertEqual(r["computed"]["votes_needed_if_quorum_present"], 14)

    def test_proposer_and_seconder_unclear(self):
        self.assertEqual(self.results["Who can propose"]["status"], "UNCLEAR")
        self.assertEqual(self.results["Seconder"]["status"], "UNCLEAR")

    def test_only_one_vote_threshold_in_results(self):
        thresholds = [r for r in self.checks["results"] if r["rule"] == "Vote threshold"]
        self.assertEqual(len(thresholds), 1)

    def test_other_vote_thresholds_listed_as_not_applicable(self):
        other = skipped(self.checks)
        self.assertEqual(set(other), {"Section 3.2", "Section 3.4"})
        self.assertIn("bylaws", other["Section 3.4"]["reason"])

    def test_every_result_has_the_spec_fields_and_statuses(self):
        # orchestration/agents/01-bylaws-compliance.md
        spec_fields = {"rule", "status", "section", "quote", "reasoning", "action_needed"}
        for r in self.checks["results"]:
            self.assertEqual(spec_fields - r.keys(), set())
            self.assertIn(r["status"], {"PASS", "FAIL", "UNCLEAR"})

    def test_every_problem_says_what_to_do(self):
        for r in self.checks["results"]:
            if r["status"] in {"FAIL", "UNCLEAR"}:
                self.assertTrue(r["action_needed"], r["rule"])


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
        results = by_rule(check(extraction))
        self.assertEqual(results["Notice period"]["status"], "UNCLEAR")

    def test_missing_rule_is_reported_as_unclear(self):
        extraction = load_sample_extraction()
        extraction.rules = [r for r in extraction.rules if r.kind != "quorum"]
        results = by_rule(check(extraction))
        self.assertEqual(results["Quorum"]["status"], "UNCLEAR")
        self.assertIsNone(results["Quorum"]["section"])

    def test_missing_number_makes_rule_unclear(self):
        extraction = load_sample_extraction()
        next(r for r in extraction.rules if r.kind == "notice_period").days = None
        results = by_rule(check(extraction))
        self.assertEqual(results["Notice period"]["status"], "UNCLEAR")

    def test_enough_notice_passes(self):
        results = by_rule(check(ga_date=date(2026, 10, 20)))
        self.assertEqual(results["Notice period"]["status"], "PASS")
        self.assertIn("Oct 13", results["Notice period"]["action_needed"])

    def test_small_budget_change_uses_ordinary_threshold(self):
        extraction = load_sample_extraction()
        extraction.proposal.budget_change_percent = 3
        checks = check(extraction)
        results = by_rule(checks)
        self.assertEqual(results["Vote threshold"]["section"], "Section 3.2")
        self.assertEqual(results["Vote threshold"]["status"], "PASS")
        self.assertNotIn("Committee review", results)
        review = next(r for r in checks["not_applicable"] if r["rule"] == "Committee review")
        self.assertIn("3%", review["reason"])


if __name__ == "__main__":
    unittest.main()
