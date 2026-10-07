"""Plain-code arithmetic for bylaw checks.

No AI in this file. The AI reads the bylaws and tells us the numbers
(for example "7 days" or "50 percent plus one"); these functions do the
counting so the answer is always the same and always correct.
"""

from datetime import date, timedelta
from fractions import Fraction
import math


# ---------------------------------------------------------------------------
# DAY-COUNTING RULE (change it here if your co-op counts differently)
#
# We count days as a plain difference between the two dates:
#   Oct 7 -> Oct 12 = 5 days.
# Some bylaws count "clear days" (excluding both the sending day and the
# GA day), which would give 4. Every date function below uses this one
# helper, so this is the only place to change.
# ---------------------------------------------------------------------------
def days_between(start: date, end: date) -> int:
    """Number of days from `start` to `end` (Oct 7 -> Oct 12 is 5)."""
    return (end - start).days


def check_notice(today: date, ga_date: date, required_days: int) -> dict:
    """Is there still enough time to give notice before the GA?"""
    available = days_between(today, ga_date)
    return {
        "days_available": available,
        "days_required": required_days,
        "passes": available >= required_days,
    }


def earliest_compliant_ga(today: date, required_days: int) -> date:
    """First GA date that works if notice is sent today."""
    return today + timedelta(days=required_days)


def deadline_before(ga_date: date, days_before: int) -> date:
    """Date something must happen by, e.g. 3 days before Oct 12 is Oct 9."""
    return ga_date - timedelta(days=days_before)


def quorum(members: int, percent: int, plus: int = 0) -> int:
    """Members needed for quorum, e.g. 50 percent of 40 plus one = 21.

    If the result is not a whole number (41 members -> 21.5), we round UP,
    because you can't have half a person and rounding down would fall
    short of the rule.
    """
    # Fraction keeps the math exact (no 0.1 + 0.2 style rounding errors).
    needed = Fraction(members * percent, 100) + plus
    return math.ceil(needed)


def votes_needed(voters: int, numerator: int, denominator: int) -> int:
    """Smallest number of votes that is at least the given fraction.

    Two-thirds of 40 is 26.67, so 27 votes are needed.
    Two-thirds of 21 is exactly 14, so 14 votes are enough.
    """
    return math.ceil(Fraction(voters * numerator, denominator))


def simple_majority(voters: int) -> int:
    """More than half: 21 present -> 11 votes, 20 present -> 11 votes."""
    return voters // 2 + 1


def exceeds_limit(value_percent: float, limit_percent: float) -> bool:
    """Is the change MORE than the limit? (Exactly 5% on a 5% limit is not.)"""
    return value_percent > limit_percent
