"""Bylaws & Compliance agent.

Checks a proposal against the co-op's bylaws in four steps:
  1. AI reads the bylaws and the proposal and returns the rules as data.
  2. Code checks that every quote really appears in the bylaws.
  3. Code decides which rules apply to this proposal.
  4. Code does the math and gives each rule PASS / FAIL / UNCLEAR.

Three ways to get the AI's answer:
    live, through Kylon (needs KYLON_API_KEY):
        .venv/bin/python compliance_agent.py --today 2026-10-07
    pasted from a Kylon agent (no key needed):
        .venv/bin/python compliance_agent.py --today 2026-10-07 --print-prompt prompt.txt
        (paste prompt.txt into the agent, save its reply as answer.json)
        .venv/bin/python compliance_agent.py --today 2026-10-07 --ai-answer-file answer.json
    saved sample answer, for tests and practice:
        .venv/bin/python compliance_agent.py --use-sample
"""

import argparse
import json
import re
from datetime import date
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel

import paste_mode
from ai_client import ask_claude, model_name
from date_and_vote_math import (
    check_notice,
    days_between,
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

# The only statuses the spec allows (orchestration/agents/01-bylaws-compliance.md).
ALLOWED_STATUSES = {"PASS", "FAIL", "UNCLEAR"}


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
def build_user_message(bylaws_text: str, proposal_text: str, members: int,
                       today: date, ga_date: date) -> str:
    """What the AI is given. Live calls and pasted prompts both use this."""
    return (
        f"<bylaws>\n{bylaws_text.strip()}\n</bylaws>\n\n"
        "<facts>\n"
        "Calculated by code from the inputs, for context only. Don't do any math.\n"
        f"Today: {today.isoformat()}\n"
        f"GA date: {ga_date.isoformat()}\n"
        f"Days from today to the GA: {days_between(today, ga_date)}\n"
        f"Voting members: {members}\n"
        "</facts>\n\n"
        f"<proposal>\n{proposal_text.strip()}\n</proposal>"
    )


def extract_with_ai(user_message: str) -> Extraction:
    """Ask Claude, through Kylon, to read the bylaws and proposal."""
    return ask_claude(EXTRACT_PROMPT.read_text(), user_message, Extraction)


def paste_prompt(bylaws_text: str, proposal_text: str, members: int,
                 today: date, ga_date: date) -> str:
    """The full prompt to paste into a Kylon agent, answer format included."""
    return paste_mode.build_paste_prompt(
        EXTRACT_PROMPT.read_text(),
        build_user_message(bylaws_text, proposal_text, members, today, ga_date),
        Extraction)


def load_pasted_extraction(path: Path) -> Extraction:
    """A Kylon agent's answer, saved to a file by a human. Checked like a live answer."""
    return paste_mode.parse_pasted_answer(path.read_text(), Extraction)


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
#
# Every result has the fields from the team spec (orchestration/agents/):
#   rule, status, section, quote, reasoning, action_needed
# plus "computed", the raw numbers, so anyone can check the math.
# status is only ever PASS, FAIL or UNCLEAR, as the spec requires. Rules
# that exist but don't cover this proposal are kept out of the results and
# listed separately under "not_applicable", so nothing disappears silently.
# ---------------------------------------------------------------------------
LABELS = {
    "notice_period": "Notice period",
    "quorum": "Quorum",
    "who_can_propose": "Who can propose",
    "seconder": "Seconder",
    "vote_threshold": "Vote threshold",
    "committee_review": "Committee review",
}

# Numbers the math needs. If the AI couldn't read one, the rule is UNCLEAR.
NEEDED_NUMBERS = {
    "notice_period": ["days"],
    "quorum": ["percent"],
    "committee_review": ["days"],
}


def _result(rule: Rule, status: str, reasoning: str,
            action_needed: Optional[str] = None, computed: dict | None = None) -> dict:
    return {
        "rule": LABELS[rule.kind],
        "status": status,
        "section": rule.section,
        "quote": rule.quote,
        "reasoning": reasoning,
        "action_needed": action_needed,
        "computed": computed or {},
    }


def _fmt(d: date) -> str:
    return d.strftime("%b %-d")  # e.g. "Oct 9"


def judge_rule(rule: Rule, members: int, today: date, ga_date: date,
               quorum_needed: Optional[int] = None) -> dict:
    """Give one rule its status. All numbers come from date_and_vote_math."""
    missing = [f for f in NEEDED_NUMBERS.get(rule.kind, []) if getattr(rule, f) is None]
    if missing:
        return _result(rule, "UNCLEAR",
            "The AI couldn't read the number this rule needs from the section.",
            f"Read {rule.section} and check this rule by hand.")

    if rule.kind == "notice_period":
        n = check_notice(today, ga_date, rule.days)
        earliest = earliest_compliant_ga(today, rule.days)
        send_by = deadline_before(ga_date, rule.days)
        computed = {"days_available": n["days_available"], "days_required": rule.days,
                    "notice_deadline": send_by.isoformat(),
                    "earliest_compliant_ga": earliest.isoformat()}
        if n["passes"]:
            return _result(rule, "PASS",
                f"Needs {rule.days} days' notice. Today is {_fmt(today)} and the GA is "
                f"{_fmt(ga_date)}, so {n['days_available']} days are available.",
                f"Send the written agenda to all members by {_fmt(send_by)}.", computed)
        return _result(rule, "FAIL",
            f"Needs {rule.days} days' notice. Today is {_fmt(today)} and the GA is "
            f"{_fmt(ga_date)}, so only {n['days_available']} days are available.",
            f"Move the GA to {_fmt(earliest)} or later, and send the written agenda "
            f"to all members today.", computed)

    if rule.kind == "quorum":
        needed = quorum(members, rule.percent, rule.plus or 0)
        return _result(rule, "UNCLEAR",
            f"{rule.percent}% of {members} members"
            + (f" plus {rule.plus}" if rule.plus else "")
            + f" = {needed} must attend. Attendance can only be confirmed at the GA.",
            f"Count voting members present at the GA and confirm at least {needed}.",
            {"members": members, "quorum_needed": needed})

    if rule.kind == "who_can_propose":
        return _result(rule, "UNCLEAR",
            "The bylaws say who may propose, but no proposer is named yet.",
            "Name the proposer and confirm they are allowed to propose.")

    if rule.kind == "seconder":
        return _result(rule, "UNCLEAR",
            "A seconder is required, but none is named yet.",
            "Name a seconder before the motion is discussed.")

    if rule.kind == "committee_review":
        due = deadline_before(ga_date, rule.days)
        computed = {"review_deadline": due.isoformat()}
        if today > due:
            return _result(rule, "FAIL",
                f"{rule.committee} review had to happen by {_fmt(due)}, "
                f"{rule.days} days before the GA. That date has passed.",
                f"Move the GA so the {rule.committee} can review at least "
                f"{rule.days} days before it.", computed)
        return _result(rule, "UNCLEAR",
            f"{rule.committee} must review this by {_fmt(due)} ({rule.days} days "
            f"before the GA on {_fmt(ga_date)}). No review is recorded yet.",
            f"Arrange the {rule.committee} review by {_fmt(due)} and record it.", computed)

    if rule.kind == "vote_threshold":
        return _judge_vote_threshold(rule, members, quorum_needed)

    raise ValueError(f"Unknown rule kind: {rule.kind}")


def _judge_vote_threshold(rule: Rule, members: int, quorum_needed: Optional[int]) -> dict:
    if rule.threshold_type == "fraction" and not (rule.numerator and rule.denominator):
        return _result(rule, "UNCLEAR",
            "The AI couldn't read the fraction this rule needs from the section.",
            f"Read {rule.section} and check this rule by hand.")

    def needed(voters: int) -> int:
        if rule.threshold_type == "simple_majority":
            return simple_majority(voters)
        return votes_needed(voters, rule.numerator, rule.denominator)

    name = ("a simple majority" if rule.threshold_type == "simple_majority"
            else f"{rule.numerator}/{rule.denominator}")

    if rule.vote_base == "all_voting_members":
        return _result(rule, "PASS",
            f"Needs {name} of all {members} voting members: {needed(members)} yes votes.",
            "Record the yes votes at the GA.", {"votes_needed": needed(members)})

    if rule.vote_base == "members_present":
        return _result(rule, "PASS",
            f"Needs {name} of members present; the exact number depends on attendance.",
            "Record attendance and yes votes at the GA.")

    # The section doesn't say whose votes count: show both readings.
    computed = {"votes_needed_if_all_members": needed(members)}
    reasoning = (f"{rule.section} requires {name} but does not say whether that is "
                 f"of members present or of all voting members. "
                 f"Of all {members} members: {needed(members)} votes.")
    if quorum_needed:
        computed["votes_needed_if_quorum_present"] = needed(quorum_needed)
        reasoning += (f" Of members present: depends on attendance "
                      f"({needed(quorum_needed)} votes if only {quorum_needed} attend).")
    return _result(rule, "UNCLEAR", reasoning,
        f"Before the vote, decide whether {name} means of members present "
        f"or of all voting members.", computed)


def _applies(rule: Rule, facts: ProposalFacts, chosen_threshold: Optional[Rule]) -> Optional[bool]:
    if rule.kind == "vote_threshold" and rule is not chosen_threshold:
        # Only one vote threshold applies; the others are not applicable,
        # unless we couldn't tell (None), which stays UNCLEAR.
        if rule.applies_to != "ordinary_motions" and rule_applies(rule, facts) is None:
            return None
        return False
    if rule.applies_to == "ordinary_motions":
        return True
    return rule_applies(rule, facts)


def _not_applicable_reason(rule: Rule, facts: ProposalFacts,
                           chosen_threshold: Optional[Rule]) -> str:
    if rule.applies_to == "ordinary_motions" and chosen_threshold is not None:
        return f"Replaced by the stricter rule in {chosen_threshold.section} for this proposal."
    if rule.applies_to == "bylaw_change":
        return "Applies only to changes to the bylaws. This proposal doesn't change the bylaws."
    if not facts.changes_budget:
        return "Applies only to budget changes. This proposal doesn't change the budget."
    return (f"Applies only to budget changes of more than {rule.budget_limit_percent:g}%. "
            f"This proposal changes the budget by {facts.budget_change_percent:g}%.")


def check_compliance(bylaws_text: str, extraction: Extraction,
                     members: int, today: date, ga_date: date) -> dict:
    """Turn the AI's extracted rules into the final checks, in bylaw order.

    Returns {"results": [...], "not_applicable": [...]}.
    """
    facts = extraction.proposal

    # Step 2: only rules whose quote is really in the bylaws are trusted.
    real = [r for r in extraction.rules if quote_is_real(r.quote, bylaws_text)]
    chosen_threshold = pick_vote_threshold(real, facts)
    quorum_rule = next((r for r in real if r.kind == "quorum" and r.percent is not None), None)
    quorum_needed = quorum(members, quorum_rule.percent, quorum_rule.plus or 0) if quorum_rule else None

    results = []
    not_applicable = []
    for rule in extraction.rules:
        if not any(rule is r for r in real):
            # Nothing is dropped silently: a rule with a fake quote becomes UNCLEAR.
            results.append(_result(rule, "UNCLEAR",
                "The quoted text could not be found in the bylaws, so this rule "
                "was not checked.", f"Read {rule.section} and check this rule by hand."))
            continue

        # Step 3: does this rule cover this proposal?
        applies = _applies(rule, facts, chosen_threshold)
        if applies is None:
            results.append(_result(rule, "UNCLEAR",
                "Can't tell from the proposal whether this rule applies.",
                "State the size of the budget change in the proposal."))
            continue
        if applies is False:
            not_applicable.append({
                "rule": LABELS[rule.kind], "section": rule.section, "quote": rule.quote,
                "reason": _not_applicable_reason(rule, facts, chosen_threshold),
            })
            continue

        # Step 4: the math.
        result = judge_rule(rule, members, today, ga_date, quorum_needed)
        is_unclear_threshold = rule.kind == "vote_threshold" and result["status"] == "UNCLEAR"
        if rule.ambiguity and not is_unclear_threshold:
            # A rule the AI flagged as ambiguous can't PASS.
            if result["status"] == "PASS":
                result["status"] = "UNCLEAR"
                result["action_needed"] = f"Read {rule.section} and decide how it applies."
            result["reasoning"] += f" Note: {rule.ambiguity}"
        results.append(result)

    # Required rules the AI couldn't find at all.
    found = {r.kind for r in real}
    for kind in REQUIRED_KINDS:
        if kind not in found:
            results.append({
                "rule": LABELS[kind], "status": "UNCLEAR", "section": None, "quote": None,
                "reasoning": "No rule about this was found in the bylaws.",
                "action_needed": "Check the bylaws for a rule about this.",
                "computed": {},
            })
    return {"results": results, "not_applicable": not_applicable}


# ---------------------------------------------------------------------------
# Putting it together
# ---------------------------------------------------------------------------
def run(bylaws_text: str, proposal_text: str, members: int, today: date,
        ga_date: date, use_sample: bool = False, answer_file: Path | None = None) -> dict:
    """Get the AI's answer (sample, pasted, or live), then check it in code."""
    if use_sample and answer_file:
        raise ValueError("Choose either --use-sample or an answer file, not both.")
    if use_sample:
        extraction, source = load_sample_extraction(), paste_mode.SOURCE_SAMPLE
    elif answer_file:
        extraction, source = load_pasted_extraction(answer_file), paste_mode.SOURCE_PASTED
    else:
        message = build_user_message(bylaws_text, proposal_text, members, today, ga_date)
        extraction, source = extract_with_ai(message), paste_mode.SOURCE_API

    checks = check_compliance(bylaws_text, extraction, members, today, ga_date)
    # Last guardrail: whatever happened above, only spec statuses leave this agent.
    bad = [r["status"] for r in checks["results"] if r["status"] not in ALLOWED_STATUSES]
    if bad:
        raise ValueError(f"Statuses not allowed by the spec: {bad}")
    return {
        "proposal": proposal_text,
        "proposal_summary": extraction.proposal.summary,
        "members": members,
        "today": today.isoformat(),
        "ga_date": ga_date.isoformat(),
        "source": source,
        "model": model_name() if source == paste_mode.SOURCE_API else None,
        "results": checks["results"],
        "not_applicable": checks["not_applicable"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Check a proposal against the bylaws.")
    parser.add_argument("--bylaws", type=Path, default=DEFAULT_BYLAWS)
    parser.add_argument("--proposal", default="Raise the house food budget by 10%")
    parser.add_argument("--members", type=int, default=40)
    parser.add_argument("--today", type=date.fromisoformat, default=date.today())
    parser.add_argument("--ga", type=date.fromisoformat, default=date(2026, 10, 12))
    answer = parser.add_mutually_exclusive_group()
    answer.add_argument("--use-sample", action="store_true",
                        help="Use the saved sample AI answer.")
    answer.add_argument("--ai-answer-file", type=Path,
                        help="Use a Kylon agent's JSON answer saved in this file.")
    answer.add_argument("--print-prompt", type=Path, metavar="FILE",
                        help="Write the prompt to paste into a Kylon agent, then stop.")
    args = parser.parse_args()
    bylaws_text = args.bylaws.read_text()

    if args.print_prompt:
        args.print_prompt.write_text(
            paste_prompt(bylaws_text, args.proposal, args.members, args.today, args.ga))
        print(f"Wrote the prompt to {args.print_prompt}. Paste it into your Kylon agent, "
              f"save its JSON reply to a file, then run again with --ai-answer-file.")
        return

    try:
        report = run(bylaws_text, args.proposal, args.members, args.today, args.ga,
                     use_sample=args.use_sample, answer_file=args.ai_answer_file)
    except paste_mode.PastedAnswerError as error:
        raise SystemExit(str(error))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
