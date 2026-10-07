"""Governance agent.

Takes the proposal and the Bylaws & Compliance report, and drafts:
  - a motion (title, whereas / resolved, proposer and seconder placeholders)
  - a GA agenda
  - a notice email to members

The AI writes the text. Code adds the parts that must be exact: the
"before you send" checklist (straight from the compliance report) and
the proposer / seconder placeholders. Code also checks the AI didn't
mention any bylaw section the compliance agent didn't check.

Try it without an API key (uses the saved sample AI answers):
    .venv/bin/python governance_agent.py --use-sample --today 2026-10-07
"""

import argparse
import json
import re
from datetime import date
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

import compliance_agent
from ai_client import ask_claude

HERE = Path(__file__).resolve().parent
DRAFT_PROMPT = HERE / "prompts" / "draft_documents.md"
SAMPLE_DRAFTS = HERE / "tests" / "fixtures" / "sample_drafts.json"

PROPOSER = "[Proposer name]"
SECONDER = "[Seconder name]"


# ---------------------------------------------------------------------------
# The shape of the AI's answer
# ---------------------------------------------------------------------------
class Motion(BaseModel):
    title: str
    whereas: list[str]
    resolved: list[str]


class AgendaItem(BaseModel):
    title: str
    minutes: Optional[int]
    notes: str


class Email(BaseModel):
    subject: str
    body: str


class Drafts(BaseModel):
    motion: Motion
    agenda: list[AgendaItem]
    notice_email: Email


# ---------------------------------------------------------------------------
# AI writes the drafts
# ---------------------------------------------------------------------------
def draft_with_ai(report: dict) -> Drafts:
    """Ask Claude to write the drafts. Needs ANTHROPIC_API_KEY."""
    check = json.dumps(report["results"], indent=2)
    message = (
        f"<proposal>\n{report['proposal']}\n</proposal>\n\n"
        f"<ga>\nDate: {report['ga_date']}\nVoting members: {report['members']}\n"
        f"Today: {report['today']}\n</ga>\n\n"
        f"<bylaw_check>\n{check}\n</bylaw_check>"
    )
    return ask_claude(DRAFT_PROMPT.read_text(), message, Drafts)


def load_sample_drafts(path: Path = SAMPLE_DRAFTS) -> Drafts:
    """A saved AI answer for the food budget test case."""
    return Drafts.model_validate_json(path.read_text())


# ---------------------------------------------------------------------------
# Code: checklist and guardrails
# ---------------------------------------------------------------------------
def before_you_send(report: dict) -> list[str]:
    """Every FAIL and UNCLEAR from the compliance report, FAILs first."""
    order = {"FAIL": 0, "UNCLEAR": 1}
    problems = [r for r in report["results"] if r["verdict"] in order]
    problems.sort(key=lambda r: order[r["verdict"]])
    return [
        f"{r['verdict']}: {r['rule']}"
        + (f" ({r['bylaw_section']})" if r["bylaw_section"] else "")
        + f". {r['explanation']}"
        for r in problems
    ]


def _all_text(drafts: Drafts) -> str:
    m, e = drafts.motion, drafts.notice_email
    parts = [m.title, *m.whereas, *m.resolved, e.subject, e.body]
    parts += [f"{item.title} {item.notes}" for item in drafts.agenda]
    return "\n".join(parts)


def unchecked_sections(drafts: Drafts, report: dict) -> list[str]:
    """Bylaw sections the drafts mention that the compliance report doesn't."""
    known = {r["bylaw_section"] for r in report["results"] if r["bylaw_section"]}
    mentioned = {f"Section {n}" for n in re.findall(r"Section (\d+(?:\.\d+)*)", _all_text(drafts))}
    return sorted(mentioned - known)


def build_package(report: dict, drafts: Drafts) -> dict:
    warnings = [
        f"The drafts mention {s}, which the bylaw check did not cover. "
        f"Read that section before sending."
        for s in unchecked_sections(drafts, report)
    ]
    motion = drafts.motion.model_dump()
    motion["proposer"] = PROPOSER
    motion["seconder"] = SECONDER
    return {
        "ga_date": report["ga_date"],
        "before_you_send": before_you_send(report),
        "draft_warnings": warnings,
        "motion": motion,
        "agenda": [item.model_dump() for item in drafts.agenda],
        "notice_email": drafts.notice_email.model_dump(),
    }


def run(report: dict, use_sample: bool = False) -> dict:
    drafts = load_sample_drafts() if use_sample else draft_with_ai(report)
    return build_package(report, drafts)


# ---------------------------------------------------------------------------
# Readable output for humans
# ---------------------------------------------------------------------------
def to_text(package: dict) -> str:
    lines = ["DRAFTS FOR REVIEW. Nothing has been sent.", ""]
    if package["before_you_send"] or package["draft_warnings"]:
        lines.append("BEFORE YOU SEND")
        lines += [f"  - {x}" for x in package["before_you_send"] + package["draft_warnings"]]
        lines.append("")

    m = package["motion"]
    lines += ["=== MOTION ===", m["title"], ""]
    lines += [f"Whereas {w}" for w in m["whereas"]]
    lines += [f"Be it resolved that {r}" for r in m["resolved"]]
    lines += ["", f"Proposed by: {m['proposer']}", f"Seconded by: {m['seconder']}", ""]

    lines += [f"=== GA AGENDA ({package['ga_date']}) ==="]
    for i, item in enumerate(package["agenda"], 1):
        length = f" ({item['minutes']} min)" if item["minutes"] else ""
        lines.append(f"{i}. {item['title']}{length}")
        if item["notes"]:
            lines.append(f"   {item['notes']}")
    lines.append("")

    e = package["notice_email"]
    lines += ["=== NOTICE EMAIL ===", f"Subject: {e['subject']}", "", e["body"]]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Draft motion, agenda and notice email.")
    parser.add_argument("--bylaws", type=Path, default=compliance_agent.DEFAULT_BYLAWS)
    parser.add_argument("--proposal", default="Raise the house food budget by 10%")
    parser.add_argument("--members", type=int, default=40)
    parser.add_argument("--today", type=date.fromisoformat, default=date.today())
    parser.add_argument("--ga", type=date.fromisoformat, default=date(2026, 10, 12))
    parser.add_argument("--use-sample", action="store_true",
                        help="Use the saved AI answers instead of calling the API.")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of text.")
    args = parser.parse_args()

    # The Governance agent needs the compliance report first.
    report = compliance_agent.run(args.bylaws.read_text(), args.proposal, args.members,
                                  args.today, args.ga, use_sample=args.use_sample)
    package = run(report, use_sample=args.use_sample)
    print(json.dumps(package, indent=2) if args.json else to_text(package))


if __name__ == "__main__":
    main()
