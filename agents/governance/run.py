"""Orchestrator: runs both agents in order, logs what each did, saves the results.

    1. Bylaws & Compliance agent  ->  compliance.json
    2. Governance agent           ->  drafts.json and drafts.txt
    3. Log of every step          ->  log.json

Each run gets its own folder under outputs/, named by date and time.

Try it without an API key (uses the saved sample AI answers):
    .venv/bin/python run.py --use-sample --today 2026-10-07
"""

import argparse
import json
from collections import Counter
from datetime import date, datetime
from pathlib import Path

import compliance_agent
import governance_agent

HERE = Path(__file__).resolve().parent
OUTPUTS = HERE / "outputs"


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


def run_pipeline(bylaws_path: Path, proposal: str, members: int, today: date,
                 ga_date: date, use_sample: bool = False,
                 out_root: Path = OUTPUTS) -> Path:
    """Run both agents and return the folder the results were saved in."""
    folder = out_root / datetime.now().strftime("%Y-%m-%d_%H%M%S")
    folder.mkdir(parents=True, exist_ok=True)
    log = RunLog()

    log.add("orchestrator", "started", {
        "bylaws": str(bylaws_path), "proposal": proposal, "members": members,
        "today": today.isoformat(), "ga_date": ga_date.isoformat(),
        "ai_answers": "saved samples" if use_sample else "live AI",
    })
    try:
        report = compliance_agent.run(bylaws_path.read_text(), proposal, members,
                                      today, ga_date, use_sample=use_sample)
        _save_json(folder / "compliance.json", report)
        verdicts = Counter(r["verdict"] for r in report["results"])
        log.add("compliance", "finished", {
            "source": report["source"],
            "verdicts": dict(verdicts),
            "failed_rules": [r["rule"] for r in report["results"] if r["verdict"] == "FAIL"],
        })

        package = governance_agent.run(report, use_sample=use_sample)
        _save_json(folder / "drafts.json", package)
        (folder / "drafts.txt").write_text(governance_agent.to_text(package) + "\n")
        log.add("governance", "finished", {
            "checklist_items": len(package["before_you_send"]),
            "draft_warnings": package["draft_warnings"],
        })
    except (Exception, SystemExit) as error:
        # Still save the log, so you can see which step went wrong.
        log.add("orchestrator", "failed", {"error": str(error) or type(error).__name__})
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
                        help="Use the saved AI answers instead of calling the API.")
    args = parser.parse_args()

    folder = run_pipeline(args.bylaws, args.proposal, args.members, args.today,
                          args.ga, use_sample=args.use_sample)
    print(f"\nDone. Open {folder / 'drafts.txt'} to read the drafts.")


if __name__ == "__main__":
    main()
