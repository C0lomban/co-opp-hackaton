"""Tests for the plain-code math. No AI, no internet, no API key needed.

Run from the agents/governance folder:
    python3 -m unittest discover tests -v
"""

import sys
import unittest
from datetime import date
from pathlib import Path

# Let the tests find date_and_vote_math.py in the folder above.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from date_and_vote_math import (  # noqa: E402
    check_notice,
    days_between,
    deadline_before,
    earliest_compliant_ga,
    exceeds_limit,
    quorum,
    simple_majority,
    votes_needed,
)

TODAY = date(2026, 10, 7)
GA = date(2026, 10, 12)


class FoodBudgetTestCase(unittest.TestCase):
    """The numbers from our test case: 40 members, today Oct 7, GA Oct 12."""

    def test_only_5_days_until_ga(self):
        self.assertEqual(days_between(TODAY, GA), 5)

    def test_notice_period_fails(self):
        result = check_notice(TODAY, GA, required_days=7)
        self.assertEqual(result["days_available"], 5)
        self.assertFalse(result["passes"])

    def test_earliest_ga_with_proper_notice_is_oct_14(self):
        self.assertEqual(earliest_compliant_ga(TODAY, 7), date(2026, 10, 14))

    def test_quorum_is_21(self):
        self.assertEqual(quorum(40, percent=50, plus=1), 21)

    def test_finance_review_due_oct_9(self):
        self.assertEqual(deadline_before(GA, 3), date(2026, 10, 9))

    def test_two_thirds_of_all_members_is_27(self):
        self.assertEqual(votes_needed(40, 2, 3), 27)

    def test_two_thirds_of_21_present_is_14(self):
        self.assertEqual(votes_needed(21, 2, 3), 14)

    def test_10_percent_is_more_than_5_percent(self):
        self.assertTrue(exceeds_limit(10, 5))


class EdgeCases(unittest.TestCase):
    """Trickier inputs, to make sure the rounding and boundaries are right."""

    def test_exactly_7_days_is_enough(self):
        self.assertTrue(check_notice(TODAY, date(2026, 10, 14), 7)["passes"])

    def test_dates_across_a_month_boundary(self):
        self.assertEqual(days_between(date(2026, 10, 28), date(2026, 11, 4)), 7)

    def test_quorum_rounds_up_for_odd_member_count(self):
        # 50% of 41 = 20.5, plus one = 21.5 -> 22 people needed
        self.assertEqual(quorum(41, percent=50, plus=1), 22)

    def test_simple_majority(self):
        self.assertEqual(simple_majority(21), 11)
        self.assertEqual(simple_majority(20), 11)

    def test_exactly_at_limit_does_not_exceed(self):
        self.assertFalse(exceeds_limit(5, 5))


if __name__ == "__main__":
    unittest.main()
