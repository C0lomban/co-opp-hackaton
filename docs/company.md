# CoopOS (working name)

## One-liner
An AI back office for student housing co-ops. Today's MVP turns a plain-language
idea into a bylaw-checked motion and a ready-to-send General Assembly (GA) agenda.

## Problem
Co-ops are run by student volunteers. Admin work (motions, agendas, minutes,
shifts, rent follow-up) eats their time, and mistakes against the bylaws
(missed notice period, no quorum) can invalidate decisions.

## Users
Co-op officers and members at UC Berkeley, then other co-ops and member-run groups.

## MVP flow (Phase 1)
INPUT
- Bylaws text (pasted or uploaded as .txt)
- Member count and date of the next GA
- A proposal in plain language ("We want to raise the house food budget by 10%")
OUTPUT
1. Draft motion (title, whereas / resolved, proposer and seconder placeholders)
2. Bylaw check: each relevant rule marked PASS / FAIL / UNCLEAR, quoting the exact
   bylaw section (notice period, quorum, who can propose, vote threshold)
3. Draft GA agenda
4. Draft notice email to members

## Guardrails
- Never invent bylaw text. Always quote the section. Say UNCLEAR when unsure.
- Humans make every decision. The AI drafts and checks.
- No payments in the MVP. No automated applicant decisions.

## AI team (Phase 1)
1. Governance agent: drafts motion, agenda, notice email
2. Bylaws & Compliance agent: runs the bylaw check
3. Orchestrator: passes work between them and logs what each agent did
(Next: Scheduling agent for shifts, Finance agent for rent tracking, Membership agent)

## Out of scope today
Rent payments, candidate selection, user accounts, mobile app.

## Test data needed
One sample bylaws file (real if public, otherwise one page written by us).
