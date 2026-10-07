# Track C — Orchestration plan

Goal for Phase 1 (Build Day, ends 6 PM): 5 AI employees created in **Kylon**,
connected through **BAND**, the MVP flow running as a **Rocket Ride** pipeline,
outputs validated by **Prelint**, and every agent's work logged as evidence.

Spec: [`docs/company.md`](../docs/company.md). Test data: [`docs/sample-bylaws.txt`](../docs/sample-bylaws.txt).

## Timeline

| Time | Step |
|---|---|
| 15:05–15:30 | Accounts + create the 5 agents in Kylon |
| 15:30–16:15 | Connect agents with BAND + first test |
| 16:15–17:00 | Rocket Ride pipeline |
| 17:00–17:30 | Prelint + collect evidence |
| 17:30–18:00 | Demo rehearsal |

If short on time, keep in this order: Kylon (5 agents) → BAND (Compliance → Governance) → evidence.

## 1. Kylon — the AI team (5 agents)

Instructions for each agent are in [`agents/`](agents/), ready to paste.

| # | Agent | Layer | Sends to |
|---|---|---|---|
| 1 | [Bylaws & Compliance](agents/01-bylaws-compliance.md) | Product | Governance |
| 2 | [Governance](agents/02-governance.md) | Product | Human (review) |
| 3 | [Market Research](agents/03-market-research.md) | Company | Growth, Finance & Pitch |
| 4 | [Growth](agents/04-growth.md) | Company | Finance & Pitch |
| 5 | [Finance & Pitch](agents/05-finance-pitch.md) | Company | Investors (Q&A) |

Product agents = what CoopOS sells. Company agents = run the startup and answer investors.

## 2. BAND — agent communication

```
Product flow (MVP demo)
  Proposal ─► [1] Compliance ─► [2] Governance ─► Human approves

Company flow (pitch)
  [3] Research ─► [4] Growth ─► [5] Finance & Pitch
        └────────────────────────────┘
```

**Test 1** — send to agent 1: `docs/sample-bylaws.txt`, 40 members, a GA date,
proposal "Raise the house food budget by 10%". Expected (see [expected-test-1.md](expected-test-1.md)):
quorum 21, Section 3.3 (two-thirds + Finance Committee review ≥3 days before GA),
UNCLEAR on "two-thirds of whom?". Result must reach agent 2 automatically.

## 3. Rocket Ride — repeatable pipeline

```
Input (bylaws + member count + GA date + proposal)
 → Bylaw check (agent 1)
 → Quote verification (each quote must appear verbatim in the bylaws, else → UNCLEAR)
 → Drafts (agent 2)
 → Prelint validation
 → Output: motion + check + agenda + email + evidence log
```

## 4. Prelint — validation rules

From the guardrails in `docs/company.md`:

- Every rule has status PASS, FAIL or UNCLEAR
- Every rule has a `section` and a `quote` found verbatim in the bylaws
- All 4 outputs present: motion, bylaw check, agenda, notice email
- Motion contains `[PROPOSER]` and `[SECONDER]` placeholders
- No sentence makes a decision for humans (e.g. "the motion is approved")
- No payments, no applicant decisions

## 5. Evidence

One JSON record per agent step in [`evidence/`](evidence/), using
[`evidence/template.json`](evidence/template.json). Also keep screenshots of
Kylon (agents), BAND (messages between agents) and Rocket Ride (pipeline run).

## 6. What we need from each tool

| Tool | Need | Ask the sponsor |
|---|---|---|
| Kylon | Account, 5 agents | Is the LLM included or do we need an API key? |
| BAND | Account / key | How does a Kylon agent hand off to another? How do we export message history? |
| Rocket Ride | Account | How to call a Kylon agent (or an LLM) as a step? Webhook/API trigger for the Track A app? |
| Prelint | Account | What spec format does it accept? Can it check agent outputs, not only code/PRs? |
| AdaL | Account | Used mainly by Track A to build the app |
