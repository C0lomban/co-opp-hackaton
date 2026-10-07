# Governance agents

Two agents for preparing a co-op General Assembly (GA):
- **Bylaws & Compliance agent** checks a proposal against the bylaws (PASS / FAIL / UNCLEAR).
- **Governance agent** uses that check to draft the motion, the GA agenda and the notice email.

## One-time setup

Run these from this folder (`agents/governance`):

```
python3 -m venv .venv
.venv/bin/python -m pip install anthropic python-dotenv
cp .env.example .env      # then open .env and paste your API key after the =
```

`.venv` is a private box of Python libraries just for this project.
`.env` holds your API key. Both are listed in `.gitignore`, so git never uploads them.

## Try it

The easiest way: run everything (both agents, results saved to `outputs/`):
```
.venv/bin/python run.py --use-sample --today 2026-10-07
```
Leave out `--use-sample` once you have an API key. Each run makes a folder like
`outputs/2026-10-07_151453/` with `drafts.txt` (read this), `compliance.json`,
`drafts.json` and `log.json` (what each agent did, in order).

Or run one agent at a time. Without an API key, using the saved sample AI answer:
```
.venv/bin/python compliance_agent.py --use-sample --today 2026-10-07
```

With an API key (the AI really reads the bylaws):
```
.venv/bin/python compliance_agent.py --today 2026-10-07 --ga 2026-10-12 \
    --members 40 --proposal "Raise the house food budget by 10%"
```

Full drafts (runs the compliance check first, then the Governance agent):
```
.venv/bin/python governance_agent.py --use-sample --today 2026-10-07
```
Add `--json` for JSON instead of readable text.

## Run the tests (no API key needed)

```
.venv/bin/python -m unittest discover tests -v
```

## Files

- `run.py`: the orchestrator. Runs both agents, logs each step, saves results.
- `date_and_vote_math.py`: all the arithmetic (dates, quorum, vote counts). No AI.
- `compliance_agent.py`: AI reads the rules, then code checks quotes and gives verdicts.
- `governance_agent.py`: AI drafts motion, agenda and email; code adds the checklist and placeholders.
- `ai_client.py`: the one place that talks to Claude (reads the key from `.env`).
- `prompts/`: the instructions given to the AI. Edit these to improve its reading and writing.
- `tests/fixtures/`: handwritten example AI answers, used when there's no API key.
