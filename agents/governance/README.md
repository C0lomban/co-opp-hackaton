# Governance agents

Two agents for preparing a co-op General Assembly (GA):
- **Bylaws & Compliance agent** checks a proposal against the bylaws. Each rule gets
  `rule, status, section, quote, reasoning, action_needed` (the spec in
  `orchestration/agents/01-bylaws-compliance.md`), plus `computed` with the raw numbers.
  `status` is PASS, FAIL or UNCLEAR. Rules that exist but don't cover this proposal
  (e.g. Section 3.4 for a budget change) are listed separately under `not_applicable`.
- **Governance agent** uses that check to draft the motion, the GA agenda and the notice email.

All AI requests go through the **Kylon proxy** (`https://api.kylon.io/proxy/anthropic`).

## One-time setup

Run these from this folder (`agents/governance`):

```
python3 -m venv .venv
.venv/bin/python -m pip install anthropic python-dotenv
cp .env.example .env      # then open .env and paste your Kylon key after KYLON_API_KEY=
```

`.venv` is a private box of Python libraries just for this project.
`.env` holds your Kylon key. Both are listed in `.gitignore`, so git never uploads them.

## Try it

Run everything (both agents):
```
.venv/bin/python run.py --today 2026-10-07                # live AI via Kylon
.venv/bin/python run.py --use-sample --today 2026-10-07   # practice: saved answers, no key
```

Each run makes a folder like `outputs/2026-10-07_151453/` with `drafts.txt` (read this),
`compliance.json`, `drafts.json` and `log.json` (what each agent did, in order).

### Paste mode: use a Kylon agent without an API key

A human carries the prompt to a Kylon agent and its JSON answer back.
`--print-prompt` writes the prompt for the next step that doesn't have an answer yet:

```
# 1. Compliance prompt -> paste into the Kylon Compliance agent, save its reply as c.json
.venv/bin/python run.py --today 2026-10-07 --print-prompt compliance-prompt.txt

# 2. Governance prompt (needs c.json) -> paste into the Governance agent, save reply as g.json
.venv/bin/python run.py --today 2026-10-07 --compliance-answer-file c.json \
    --print-prompt governance-prompt.txt

# 3. Full run with both pasted answers (evidence goes to orchestration/evidence/)
.venv/bin/python run.py --today 2026-10-07 --compliance-answer-file c.json \
    --governance-answer-file g.json
```

The prompt file is exactly what a live call would send (instructions, bylaws, facts
calculated by code, proposal) plus the JSON format the answer must follow. The Compliance
agent only extracts the rules as data; code still does all the math and decides every status.

Pasted answers get the same checks as live ones: the JSON must match the format (you get a
message naming any wrong field, e.g. `rules[0].days`), quotes must be word for word in the
bylaws, and statuses are only PASS / FAIL / UNCLEAR. ```json fences and extra sentences
around the JSON are fine. Evidence records `"source": "kylon-agent-pasted"`.

Each agent script also has `--print-prompt` and `--ai-answer-file` for one step at a time
(`governance_agent.py` also takes `--compliance-answer-file`).

### Evidence

Each agent step also writes one evidence file named `YYYYMMDD-HHMM-<agent>.json`, in the
format of `orchestration/evidence/template.json`. Failed steps get a file too, with
`"status": "error"`. Where they go:

1. `--evidence-dir <folder>` if you pass it, otherwise
2. `EVIDENCE_DIR` from your shell or `.env` (a relative path is relative to this folder), otherwise
3. `orchestration/evidence/` for live runs, and the run's own `outputs/.../evidence/` for
   `--use-sample` practice runs, so practice results never mix with the team's real evidence.

### One agent at a time

```
.venv/bin/python compliance_agent.py --use-sample --today 2026-10-07
.venv/bin/python governance_agent.py --use-sample --today 2026-10-07   # add --json for JSON
```
Leave out `--use-sample` to use the live AI. Other options: `--ga`, `--members`, `--proposal`, `--bylaws`.

## Run the tests (no Kylon key or internet needed)

```
.venv/bin/python -m unittest discover tests -v
```

## Files

- `run.py`: the orchestrator. Runs both agents, logs each step, saves results and evidence.
- `date_and_vote_math.py`: all the arithmetic (dates, quorum, vote counts). No AI.
- `compliance_agent.py`: AI reads the rules, then code checks quotes and gives statuses.
- `governance_agent.py`: AI drafts motion, agenda and email; code adds the checklist and placeholders.
- `paste_mode.py`: prompt files and checks for answers pasted from Kylon agents.
- `ai_client.py`: the one place that talks to Claude, always through Kylon (reads the key from `.env`).
- `prompts/`: the instructions given to the AI. Edit these to improve its reading and writing.
- `tests/fixtures/`: handwritten example AI answers, used by `--use-sample` and the tests.
