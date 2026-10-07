"""Orchestrator: runs both agents in order, logs what each did, saves the results.

    1. Bylaws & Compliance agent  ->  compliance.json
    2. Governance agent           ->  drafts.json and drafts.txt
    3. One evidence file per agent step, named YYYYMMDD-HHMM-<agent>.json and
       shaped like orchestration/evidence/template.json
    4. Log of every step          ->  log.json

Results go in their own folder under outputs/, named by date and time.

Evidence goes to orchestration/evidence/ by default. To change that, use
--evidence-dir or set EVIDENCE_DIR (in .env or your shell). Sample runs
(--use-sample) keep their evidence inside their outputs/ folder unless you
choose a folder explicitly, so practice runs never mix with the team's
real evidence.

Three ways to get the AI's answers:
    live, through Kylon (needs KYLON_API_KEY):
        .venv/bin/python run.py --today 2026-10-07
    pasted from Kylon agents (no key needed); --print-prompt writes the prompt
    for the next step that doesn't have an answer yet:
        .venv/bin/python run.py --today 2026-10-07 --print-prompt compliance-prompt.txt
        .venv/bin/python run.py --today 2026-10-07 --compliance-answer-file c.json \
            --print-prompt governance-prompt.txt
        .venv/bin/python run.py --today 2026-10-07 --compliance-answer-file c.json \
            --governance-answer-file g.json
    saved sample answers (practice; evidence stays in outputs/):
        .venv/bin/python run.py --use-sample --today 2026-10-07
"""

import argparse
import json
import os
from collections import Counter
from datetime import date, datetime
from pathlib import Path

import compliance_agent
import governance_agent
import paste_mode

HERE = Path(__file__).resolve().parent
OUTPUTS = HERE / "outputs"
TEAM_EVIDENCE = HERE.parent.parent / "orchestration" / "evidence"


class RunLog:
    """A simple list of what happened, in order, with timestamps."""

    def __init__(self):
        self.entries = []

    def add(self, agent: str, event: str, details: dict | None = None) -> None:
        entry = {
            "time": datetime.now().isoformat(timespec="seconds"),
            "agent": agent,
            "event": event,
            "details": details or {},
        }
        self.entries.append(entry)
        print(f"[{entry['time']}] {agent}: {event}")


def _save_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n")


def choose_evidence_dir(flag: Path | None, use_sample: bool, run_folder: Path) -> Path:
    """--evidence-dir wins, then EVIDENCE_DIR, then the default."""
    if flag:
        return flag
    if os.environ.get("EVIDENCE_DIR"):
        # A relative path in EVIDENCE_DIR means relative to this folder.
        return HERE / os.environ["EVIDENCE_DIR"]
    return run_folder / "evidence" if use_sample else TEAM_EVIDENCE


# How each source is described in evidence, so it's always honest.
TOOL = {
    paste_mode.SOURCE_API: "Kylon API, called by Python (agents/governance)",
    paste_mode.SOURCE_PASTED: "Kylon agent; answer pasted by a human, checked by Python",
    paste_mode.SOURCE_SAMPLE: "Python (agents/governance) with saved sample answers",
}
NOTES = {
    paste_mode.SOURCE_API: "Live AI via the Kylon API. Every quote verified word for word by code.",
    paste_mode.SOURCE_PASTED: ("Answer copied from a Kylon agent by a human, then checked by "
                               "code like a live answer: format, quotes word for word, statuses."),
    paste_mode.SOURCE_SAMPLE: "PRACTICE RUN: saved handwritten sample answers, not live AI.",
}


def source_for(use_sample: bool, answer_file: Path | None) -> str:
    if use_sample:
        return paste_mode.SOURCE_SAMPLE
    return paste_mode.SOURCE_PASTED if answer_file else paste_mode.SOURCE_API


def save_evidence(evidence_dir: Path, slug: str, agent: str, input_summary: str,
                  output, handed_to: str, status: str, source: str,
                  extra_notes: str = "") -> Path:
    """One evidence record, named and shaped as orchestration/evidence/README.md asks."""
    now = datetime.now().astimezone()  # includes the time zone, like the template
    evidence_dir.mkdir(parents=True, exist_ok=True)
    path = evidence_dir / f"{now:%Y%m%d-%H%M}-{slug}.json"
    n = 2
    while path.exists():  # two runs in the same minute: don't overwrite
        path = evidence_dir / f"{now:%Y%m%d-%H%M}-{slug}-{n}.json"
        n += 1
    _save_json(path, {
        "timestamp": now.isoformat(timespec="seconds"),
        "agent": agent,
        "tool": TOOL[source],
        "source": source,
        "input_summary": input_summary,
        "output": output,
        "handed_to": handed_to,
        "status": status,
        "notes": (NOTES[source] + " " + extra_notes).strip(),
    })
    return path


def run_pipeline(bylaws_path: Path, proposal: str, members: int, today: date,
                 ga_date: date, use_sample: bool = False,
                 out_root: Path = OUTPUTS, evidence_dir: Path | None = None,
                 compliance_answer_file: Path | None = None,
                 governance_answer_file: Path | None = None) -> Path:
    """Run both agents and return the folder the results were saved in."""
    if use_sample and (compliance_answer_file or governance_answer_file):
        raise ValueError("Choose either --use-sample or answer files, not both.")
    sources = {
        "compliance": source_for(use_sample, compliance_answer_file),
        "governance": source_for(use_sample, governance_answer_file),
    }
    folder = out_root / datetime.now().strftime("%Y-%m-%d_%H%M%S")
    folder.mkdir(parents=True, exist_ok=True)
    evidence_dir = choose_evidence_dir(evidence_dir, use_sample, folder)
    log = RunLog()
    input_summary = (f"{proposal}, {members} members, today {today.isoformat()}, "
                     f"GA {ga_date.isoformat()}, {bylaws_path.name}")

    log.add("orchestrator", "started", {
        "bylaws": str(bylaws_path), "proposal": proposal, "members": members,
        "today": today.isoformat(), "ga_date": ga_date.isoformat(),
        "sources": sources,
        "evidence_dir": str(evidence_dir),
    })
    step = ("compliance", "Bylaws & Compliance Agent")
    try:
        report = compliance_agent.run(bylaws_path.read_text(), proposal, members,
                                      today, ga_date, use_sample=use_sample,
                                      answer_file=compliance_answer_file)
        _save_json(folder / "compliance.json", report)
        statuses = Counter(r["status"] for r in report["results"])
        log.add("compliance", "finished", {
            "source": report["source"],
            "statuses": dict(statuses),
            "failed_rules": [r["rule"] for r in report["results"] if r["status"] == "FAIL"],
        })
        save_evidence(evidence_dir, *step, input_summary, report["results"],
                      "Governance Agent", "ok", sources["compliance"])

        step = ("governance", "Governance Agent")
        package = governance_agent.run(report, use_sample=use_sample,
                                       answer_file=governance_answer_file)
        _save_json(folder / "drafts.json", package)
        (folder / "drafts.txt").write_text(governance_agent.to_text(package) + "\n")
        log.add("governance", "finished", {
            "checklist_items": len(package["before_you_send"]),
            "draft_warnings": package["draft_warnings"],
        })
        save_evidence(evidence_dir, *step, input_summary, package,
                      "Human (review)", "ok", sources["governance"])
    except (Exception, SystemExit) as error:
        # Record the failure as evidence too, so you can see which step went wrong.
        message = str(error) or type(error).__name__
        log.add("orchestrator", "failed", {"agent": step[0], "error": message})
        save_evidence(evidence_dir, *step, input_summary, None,
                      "Nobody (step failed)", "error", sources[step[0]],
                      f"Error: {message}")
        raise
    finally:
        log.add("orchestrator", "saved", {"folder": str(folder)})
        _save_json(folder / "log.json", log.entries)

    return folder


def write_next_prompt(path: Path, bylaws_path: Path, proposal: str, members: int,
                      today: date, ga_date: date,
                      compliance_answer_file: Path | None = None) -> str:
    """Write the prompt for the next step that has no answer yet. Returns which one."""
    bylaws_text = bylaws_path.read_text()
    if not compliance_answer_file:
        path.write_text(compliance_agent.paste_prompt(
            bylaws_text, proposal, members, today, ga_date))
        return "compliance"
    report = compliance_agent.run(bylaws_text, proposal, members, today, ga_date,
                                  answer_file=compliance_answer_file)
    path.write_text(governance_agent.paste_prompt(report))
    return "governance"


def main() -> None:
    parser = argparse.ArgumentParser(description="Check a proposal and draft GA documents.")
    parser.add_argument("--bylaws", type=Path, default=compliance_agent.DEFAULT_BYLAWS)
    parser.add_argument("--proposal", default="Raise the house food budget by 10%")
    parser.add_argument("--members", type=int, default=40)
    parser.add_argument("--today", type=date.fromisoformat, default=date.today())
    parser.add_argument("--ga", type=date.fromisoformat, default=date(2026, 10, 12))
    parser.add_argument("--use-sample", action="store_true",
                        help="Use the saved sample answers (practice).")
    parser.add_argument("--print-prompt", type=Path, metavar="FILE",
                        help="Write the prompt for the next step to paste into a Kylon "
                             "agent, then stop.")
    parser.add_argument("--compliance-answer-file", type=Path,
                        help="The Compliance Kylon agent's JSON answer.")
    parser.add_argument("--governance-answer-file", type=Path,
                        help="The Governance Kylon agent's JSON answer.")
    parser.add_argument("--evidence-dir", type=Path,
                        help="Where to save evidence files "
                             "(default: EVIDENCE_DIR, else orchestration/evidence).")
    args = parser.parse_args()

    # Lets EVIDENCE_DIR be set in .env as well as in the shell.
    from dotenv import load_dotenv
    load_dotenv(HERE / ".env")

    if args.use_sample and (args.print_prompt or args.compliance_answer_file
                            or args.governance_answer_file):
        parser.error("--use-sample can't be combined with paste mode options.")

    try:
        if args.print_prompt:
            step = write_next_prompt(args.print_prompt, args.bylaws, args.proposal,
                                     args.members, args.today, args.ga,
                                     args.compliance_answer_file)
            flag = f"--{step}-answer-file"
            print(f"Wrote the {step.title()} agent prompt to {args.print_prompt}.\n"
                  f"Paste it into your Kylon {step.title()} agent, save its JSON reply "
                  f"to a file, then run again with {flag} <that file>.")
            return
        folder = run_pipeline(args.bylaws, args.proposal, args.members, args.today,
                              args.ga, use_sample=args.use_sample,
                              evidence_dir=args.evidence_dir,
                              compliance_answer_file=args.compliance_answer_file,
                              governance_answer_file=args.governance_answer_file)
    except paste_mode.PastedAnswerError as error:
        raise SystemExit(f"\n{error}")
    print(f"\nDone. Open {folder / 'drafts.txt'} to read the drafts.")


if __name__ == "__main__":
    main()
