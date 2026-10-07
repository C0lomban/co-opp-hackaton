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

Try it without a Kylon key (uses the saved sample AI answers):
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


def save_evidence(evidence_dir: Path, slug: str, agent: str, input_summary: str,
                  output, handed_to: str, status: str, notes: str) -> Path:
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
        "tool": "Python (agents/governance)",
        "input_summary": input_summary,
        "output": output,
        "handed_to": handed_to,
        "status": status,
        "notes": notes,
    })
    return path


def run_pipeline(bylaws_path: Path, proposal: str, members: int, today: date,
                 ga_date: date, use_sample: bool = False,
                 out_root: Path = OUTPUTS, evidence_dir: Path | None = None) -> Path:
    """Run both agents and return the folder the results were saved in."""
    folder = out_root / datetime.now().strftime("%Y-%m-%d_%H%M%S")
    folder.mkdir(parents=True, exist_ok=True)
    evidence_dir = choose_evidence_dir(evidence_dir, use_sample, folder)
    log = RunLog()
    input_summary = (f"{proposal}, {members} members, today {today.isoformat()}, "
                     f"GA {ga_date.isoformat()}, {bylaws_path.name}")
    notes = ("PRACTICE RUN: AI answers from saved handwritten samples, not live AI."
             if use_sample else
             "Live AI via Kylon. Every quote verified word for word by code.")

    log.add("orchestrator", "started", {
        "bylaws": str(bylaws_path), "proposal": proposal, "members": members,
        "today": today.isoformat(), "ga_date": ga_date.isoformat(),
        "ai_answers": "saved samples" if use_sample else "live AI via Kylon",
        "evidence_dir": str(evidence_dir),
    })
    step = ("compliance", "Bylaws & Compliance Agent")
    try:
        report = compliance_agent.run(bylaws_path.read_text(), proposal, members,
                                      today, ga_date, use_sample=use_sample)
        _save_json(folder / "compliance.json", report)
        statuses = Counter(r["status"] for r in report["results"])
        log.add("compliance", "finished", {
            "source": report["source"],
            "statuses": dict(statuses),
            "failed_rules": [r["rule"] for r in report["results"] if r["status"] == "FAIL"],
        })
        save_evidence(evidence_dir, *step, input_summary, report["results"],
                      "Governance Agent", "ok", notes)

        step = ("governance", "Governance Agent")
        package = governance_agent.run(report, use_sample=use_sample)
        _save_json(folder / "drafts.json", package)
        (folder / "drafts.txt").write_text(governance_agent.to_text(package) + "\n")
        log.add("governance", "finished", {
            "checklist_items": len(package["before_you_send"]),
            "draft_warnings": package["draft_warnings"],
        })
        save_evidence(evidence_dir, *step, input_summary, package,
                      "Human (review)", "ok", notes)
    except (Exception, SystemExit) as error:
        # Record the failure as evidence too, so you can see which step went wrong.
        message = str(error) or type(error).__name__
        log.add("orchestrator", "failed", {"agent": step[0], "error": message})
        save_evidence(evidence_dir, *step, input_summary, None,
                      "Nobody (step failed)", "error", f"{notes} Error: {message}")
        raise
    finally:
        log.add("orchestrator", "saved", {"folder": str(folder)})
        _save_json(folder / "log.json", log.entries)

    return folder


def main() -> None:
    parser = argparse.ArgumentParser(description="Check a proposal and draft GA documents.")
    parser.add_argument("--bylaws", type=Path, default=compliance_agent.DEFAULT_BYLAWS)
    parser.add_argument("--proposal", default="Raise the house food budget by 10%")
    parser.add_argument("--members", type=int, default=40)
    parser.add_argument("--today", type=date.fromisoformat, default=date.today())
    parser.add_argument("--ga", type=date.fromisoformat, default=date(2026, 10, 12))
    parser.add_argument("--use-sample", action="store_true",
                        help="Use the saved AI answers instead of calling Kylon.")
    parser.add_argument("--evidence-dir", type=Path,
                        help="Where to save evidence files "
                             "(default: EVIDENCE_DIR, else orchestration/evidence).")
    args = parser.parse_args()

    # Lets EVIDENCE_DIR be set in .env as well as in the shell.
    from dotenv import load_dotenv
    load_dotenv(HERE / ".env")

    folder = run_pipeline(args.bylaws, args.proposal, args.members, args.today,
                          args.ga, use_sample=args.use_sample,
                          evidence_dir=args.evidence_dir)
    print(f"\nDone. Open {folder / 'drafts.txt'} to read the drafts.")


if __name__ == "__main__":
    main()
