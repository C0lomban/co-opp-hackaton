"""Bylaws & Compliance agent.

Checks a proposal against the co-op's bylaws in four steps:
  1. AI reads the bylaws and the proposal and returns the rules as data.
  2. Code checks that every quote really appears in the bylaws.
  3. Code decides which rules apply to this proposal.
  4. Code does the math and gives each rule PASS / FAIL / UNCLEAR.

Try it without an API key (uses the saved sample AI answer):
    .venv/bin/python compliance_agent.py --use-sample
"""

import argparse
import json
import re
from datetime import date
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel

from ai_client import MODEL, ask_claude
from date_and_vote_math import (
    check_notice,
    deadline_before,
    earliest_compliant_ga,
    exceeds_limit,
    quorum,
    simple_majority,
    votes_needed,
)

HERE = Path(__file__).resolve().parent
DEFAULT_BYLAWS = HERE.parent.parent / "docs" / "sample-bylaws.txt"
SAMPLE_EXTRACTION = HERE / "tests" / "fixtures" / "sample_extraction.json"
EXTRACT_PROMPT = HERE / "prompts" / "extract_rules.md"

# Rules every proposal must be checked against. If the AI can't find one,
# we report it as UNCLEAR instead of silently skipping it.
REQUIRED_KINDS = ["notice_period", "quorum", "who_can_propose", "vote_threshold"]


# ---------------------------------------------------------------------------
# The shape of the AI's answer. Pydantic checks the AI's JSON matches this
# exactly, so the rest of the code can trust the field names and types.
# ---------------------------------------------------------------------------
class Rule(BaseModel):
    kind: Literal[
        "notice_period",
        "quorum",
        "who_can_propose",
        "seconder",
        "vote_threshold",
        "committee_review",
    ]
    section: str
    quote: str
    applies_to: Literal[
        "all_motions", "ordinary_motions", "budget_change_over_limit", "bylaw_change"
    ]
    budget_limit_percent: Optional[float]
    days: Optional[int]
    percent: Optional[int]
    plus: Optional[int]
    threshold_type: Optional[Literal["simple_majority", "fraction"]]
    numerator: Optional[int]
    denominator: Optional[int]
    vote_base: Optional[Literal["members_present", "all_voting_members", "not_stated"]]
    committee: Optional[str]
    ambiguity: Optional[str]


class ProposalFacts(BaseModel):
    summary: str
    changes_budget: bool
    budget_change_percent: Optional[float]
    changes_bylaws: bool


class Extraction(BaseModel):
    rules: list[Rule]
    proposal: ProposalFacts


# ---------------------------------------------------------------------------
# Step 1: AI reads the rules
# ---------------------------------------------------------------------------
def extract_with_ai(bylaws_text: str, proposal_text: str) -> Extraction:
    """Ask Claude to read the bylaws and proposal. Needs ANTHROPIC_API_KEY."""
    return ask_claude(
        EXTRACT_PROMPT.read_text(),
        f"<bylaws>\n{bylaws_text}\n</bylaws>\n\n<proposal>\n{proposal_text}\n</proposal>",
        Extraction,
    )


def load_sample_extraction(path: Path = SAMPLE_EXTRACTION) -> Extraction:
    """A saved AI answer for the sample bylaws, used for tests and demos."""
    return Extraction.model_validate_json(path.read_text())


# ---------------------------------------------------------------------------
# Step 2: check the quotes are real
# ---------------------------------------------------------------------------
def _squash_spaces(text: str) -> str:
    # Bylaws wrap lines in odd places; compare text with all spacing
    # (spaces, line breaks) turned into single spaces.
    return re.sub(r"\s+", " ", text).strip()


def quote_is_real(quote: str, bylaws_text: str) -> bool:
    return bool(quote.strip()) and _squash_spaces(quote) in _squash_spaces(bylaws_text)


# ---------------------------------------------------------------------------
# Step 3: which rules apply to this proposal?
# ---------------------------------------------------------------------------
def rule_applies(rule: Rule, facts: ProposalFacts) -> Optional[bool]:
    """True / False, or None if we can't tell from the proposal."""
    if rule.applies_to == "all_motions":
        return True
    if rule.applies_to == "bylaw_change":
        return facts.changes_bylaws
    if rule.applies_to == "budget_change_over_limit":
        if not facts.changes_budget:
            return False
        if facts.budget_change_percent is None or rule.budget_limit_percent is None:
            return None
        return exceeds_limit(facts.budget_change_percent, rule.budget_limit_percent)
    return None  # "ordinary_motions" is decided in pick_vote_threshold


def pick_vote_threshold(rules: list[Rule], facts: ProposalFacts) -> Optional[Rule]:
    """The special threshold if one applies, otherwise the ordinary one."""
    thresholds = [r for r in rules if r.kind == "vote_threshold"]
    for rule in thresholds:
        if rule.applies_to != "ordinary_motions" and rule_applies(rule, facts):
            return rule
    for rule in thresholds:
        if rule.applies_to == "ordinary_motions":
            return rule
    return None


# ---------------------------------------------------------------------------
# Step 4: math and verdicts
# ---------------------------------------------------------------------------
LABELS = {
    "notice_period": "Notice period",
    "quorum": "Quorum",
    "who_can_propose": "Who can propose",
    "seconder": "Seconder",
    "vote_threshold": "Vote threshold",
    "committee_review": "Committee review",
}


def _result(rule: Rule, verdict: str, explanation: str, computed: dict | None = None) -> dict:
    return {
        "rule": LABELS[rule.kind],
        "verdict": verdict,
        "bylaw_section": rule.section,
        "quote": rule.quote,
        "explanation": explanation,
        "computed": computed or {},
    }


def _fmt(d: date) -> str:
    return d.strftime("%b %-d")  # e.g. "Oct 9"


def judge_rule(rule: Rule, members: int, today: date, ga_date: date) -> dict:
    """Give one rule its verdict. All numbers come from date_and_vote_math."""
    if rule.kind == "notice_period":
        n = check_notice(today, ga_date, rule.days)
        earliest = earliest_compliant_ga(today, rule.days)
        computed = {**n, "earliest_compliant_ga": earliest.isoformat()}
        computed.pop("passes")
        if n["passes"]:
            return _result(rule, "PASS",
                f"Needs {rule.days} days' notice; {n['days_available']} days remain "
                f"before the GA on {_fmt(ga_date)}. Send the notice today.", computed)
        return _result(rule, "FAIL",
            f"Needs {rule.days} days' notice. Today is {_fmt(today)} and the GA is "
            f"{_fmt(ga_date)}, so only {n['days_available']} days are available. "
            f"Earliest GA with proper notice sent today: {_fmt(earliest)}.", computed)

    if rule.kind == "quorum":
        needed = quorum(members, rule.percent, rule.plus or 0)
        return _result(rule, "UNCLEAR",
            f"At least {needed} of {members} members must attend. Attendance "
            f"can only be confirmed at the GA.",
            {"members": members, "quorum_needed": needed})

    if rule.kind == "who_can_propose":
        return _result(rule, "UNCLEAR",
            "The bylaws say who may propose. Confirm the proposer meets this.")

    if rule.kind == "seconder":
        return _result(rule, "UNCLEAR",
            "A seconder is needed. Name one before the GA.")

    if rule.kind == "committee_review":
        due = deadline_before(ga_date, rule.days)
        computed = {"review_deadline": due.isoformat()}
        if today > due:
            return _result(rule, "FAIL",
                f"{rule.committee} review had to happen by {_fmt(due)}, "
                f"{rule.days} days before the GA. That date has passed.", computed)
        return _result(rule, "UNCLEAR",
            f"{rule.committee} must review this by {_fmt(due)} "
            f"({rule.days} days before the GA on {_fmt(ga_date)}). "
            f"Confirm the review happens.", computed)

    if rule.kind == "vote_threshold":
        return _judge_vote_threshold(rule, members)

    raise ValueError(f"Unknown rule kind: {rule.kind}")


def _judge_vote_threshold(rule: Rule, members: int) -> dict:
    def needed(voters: int) -> int:
        if rule.threshold_type == "simple_majority":
            return simple_majority(voters)
        return votes_needed(voters, rule.numerator, rule.denominator)

    name = ("a simple majority" if rule.threshold_type == "simple_majority"
            else f"{rule.numerator}/{rule.denominator}")

    if rule.vote_base == "all_voting_members":
        return _result(rule, "PASS",
            f"Needs {name} of all {members} voting members: {needed(members)} votes.",
            {"votes_needed": needed(members)})

    if rule.vote_base == "members_present":
        return _result(rule, "PASS",
            f"Needs {name} of members present at the GA; the exact number "
            f"depends on attendance.", {})

    # The section doesn't say whose votes count. check_compliance fills in
    # the explanation, because it needs the quorum number too.
    return _result(rule, "UNCLEAR", "", {"votes_needed_if_all_members": needed(members)})


def check_compliance(bylaws_text: str, extraction: Extraction,
                     members: int, today: date, ga_date: date) -> list[dict]:
    """Turn the AI's extracted rules into the final list of verdicts."""
    facts = extraction.proposal
    results = []

    # Step 2: drop nothing silently. A rule with a fake quote becomes UNCLEAR.
    real_rules = []
    for rule in extraction.rules:
        if quote_is_real(rule.quote, bylaws_text):
            real_rules.append(rule)
        else:
            results.append(_result(rule, "UNCLEAR",
                "The quoted text could not be found in the bylaws, so this "
                "rule was not checked. A human should read the section."))

    # Step 3: keep only rules that apply to this proposal.
    chosen_threshold = pick_vote_threshold(real_rules, facts)
    to_judge = []
    for rule in real_rules:
        if rule.kind == "vote_threshold":
            if rule is chosen_threshold:
                to_judge.append(rule)
            continue
        applies = rule_applies(rule, facts)
        if applies is None and rule.applies_to != "ordinary_motions":
            results.append(_result(rule, "UNCLEAR",
                "Can't tell from the proposal whether this rule applies "
                "(for example, the size of the budget change isn't stated)."))
        elif applies or rule.applies_to == "ordinary_motions":
            to_judge.append(rule)

    # Step 4: verdicts.
    judged = [(rule, judge_rule(rule, members, today, ga_date)) for rule in to_judge]
    quorum_needed = next((res["computed"]["quorum_needed"]
                          for rule, res in judged if rule.kind == "quorum"), None)

    for rule, result in judged:
        if rule.kind == "vote_threshold" and result["verdict"] == "UNCLEAR":
            # This explanation already covers the ambiguity.
            _explain_unclear_threshold(result, rule, members, quorum_needed)
        elif rule.ambiguity:
            # A rule the AI flagged as ambiguous can't PASS.
            if result["verdict"] == "PASS":
                result["verdict"] = "UNCLEAR"
            result["explanation"] += f" Note: {rule.ambiguity}"
        results.append(result)

    # Required rules the AI couldn't find at all.
    found = {r.kind for r in real_rules}
    for kind in REQUIRED_KINDS:
        if kind not in found:
            results.append({
                "rule": LABELS[kind], "verdict": "UNCLEAR", "bylaw_section": None,
                "quote": None, "computed": {},
                "explanation": "No rule about this was found in the bylaws. "
                               "A human should check.",
            })
    return results


def _explain_unclear_threshold(result: dict, rule: Rule, members: int,
                               quorum_needed: Optional[int]) -> None:
    """Fill in both readings so humans can see what's at stake."""
    frac = f"{rule.numerator}/{rule.denominator}"
    of_all = votes_needed(members, rule.numerator, rule.denominator)
    text = (f"{rule.section} requires {frac} but does not say whether that is "
            f"{frac} of members present or of all voting members. "
            f"Of all {members} members: {of_all} votes.")
    if quorum_needed:
        of_present = votes_needed(quorum_needed, rule.numerator, rule.denominator)
        text += (f" Of members present: depends on attendance "
                 f"({of_present} votes if only {quorum_needed} attend).")
        result["computed"]["votes_needed_if_quorum_present"] = of_present
    result["explanation"] = text + " The co-op should decide which reading applies."


# ---------------------------------------------------------------------------
# Putting it together
# ---------------------------------------------------------------------------
def run(bylaws_text: str, proposal_text: str, members: int, today: date,
        ga_date: date, use_sample: bool = False) -> dict:
    extraction = (load_sample_extraction() if use_sample
                  else extract_with_ai(bylaws_text, proposal_text))
    return {
        "proposal": proposal_text,
        "proposal_summary": extraction.proposal.summary,
        "members": members,
        "today": today.isoformat(),
        "ga_date": ga_date.isoformat(),
        "source": "saved sample AI answer" if use_sample else f"AI ({MODEL})",
        "results": check_compliance(bylaws_text, extraction, members, today, ga_date),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Check a proposal against the bylaws.")
    parser.add_argument("--bylaws", type=Path, default=DEFAULT_BYLAWS)
    parser.add_argument("--proposal", default="Raise the house food budget by 10%")
    parser.add_argument("--members", type=int, default=40)
    parser.add_argument("--today", type=date.fromisoformat, default=date.today())
    parser.add_argument("--ga", type=date.fromisoformat, default=date(2026, 10, 12))
    parser.add_argument("--use-sample", action="store_true",
                        help="Use the saved AI answer instead of calling the API.")
    args = parser.parse_args()

    report = run(args.bylaws.read_text(), args.proposal, args.members,
                 args.today, args.ga, use_sample=args.use_sample)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
