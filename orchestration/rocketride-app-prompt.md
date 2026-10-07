# Prompt for Claude Code (VS Code, RocketRide workspace)

Paste everything inside the block below into Claude Code, opened in the RocketRide workspace.

```
You are building "CoopOS Bylaws Checker", a small web app on the RocketRide platform
for a hackathon (deadline today 18:00). Follow the project rules in
.claude/rules/rocketride.md strictly.

STEP 0 - READ FIRST (do not write code before this)
Read .rocketride/docs/ROCKETRIDE_README.md, ROCKETRIDE_CONCEPTS.md,
ROCKETRIDE_PIPELINES.md, ROCKETRIDE_COMPONENT_REFERENCE.md, ROCKETRIDE_APPS.md,
ROCKETRIDE_UI_COMPONENTS.md and ROCKETRIDE_INTEGRATIONS.md. Verify every component
name and config field against .rocketride/services-catalog.json and
.rocketride/schema/. Do not invent anything. Create the app ONLY through the
scaffold (client.deploy.createApp), never by hand-creating app files. Use the
development connection from .env (ROCKETRIDE_URI / ROCKETRIDE_APIKEY) for running
and validating. Do not deploy or publish without asking me.

WHAT THE PRODUCT IS
CoopOS is an AI back office for student housing co-ops (UC Berkeley first). A co-op
officer types a proposal; the app checks it against the co-op's bylaws and drafts the
General Assembly (GA) documents. Humans make every decision; the AI only checks and
drafts.

APP UI (one page)
Inputs: bylaws text (large textarea, prefilled with the sample below), member count
(number, default 40), next GA date (date), today's date (date, default today),
proposal (text, default "Raise the house food budget by 10%").
Button: "Check proposal".
Outputs, in 4 tabs: (1) Bylaw check (table: rule, status badge PASS/FAIL/UNCLEAR,
section, quote, reasoning, action needed), (2) Motion, (3) GA agenda, (4) Notice email.
Show a banner at the top listing every FAIL or UNCLEAR. Show a "Pipeline log" panel
with one line per pipeline step (what ran, pass/fail, time). A "Download evidence
JSON" button exports that log.

PIPELINE (one repeatable .pipe, called by the app)
1. Bylaw check (LLM step, "Compliance agent")
2. Quote verification (code/deterministic step): every `quote` must appear word for
   word in the bylaws text (ignore whitespace differences). If not, set that rule to
   UNCLEAR and add "quote not found in bylaws" to its reasoning.
3. Drafts (LLM step, "Governance agent"), receiving the verified check
4. Validation (deterministic step, "Prelint rules" below)
5. Output: { check, motion, agenda, email, validation, log }
The handoff between step 1 and step 3 happens inside the pipeline. Keep the handoff
as a single clearly named step so it can later be replaced by a call to BAND (an
external agent-messaging tool) over HTTP/webhook if BAND access works. Do not invent
a BAND API; leave a documented placeholder and config flag only.

COMPLIANCE AGENT PROMPT (step 1)
You check a co-op proposal against its bylaws. Inputs: bylaws text, member count,
next GA date, today's date, proposal. For each relevant rule (who can propose,
seconder, notice period, quorum, vote threshold, committee review, bylaw change)
output a JSON array of {rule, status: PASS|FAIL|UNCLEAR|NOT_APPLICABLE, section,
quote, reasoning, action_needed}. "quote" must be copied word for word from the
bylaws. Never invent bylaw text. If no section covers a rule, or it is ambiguous, use
UNCLEAR. If a threshold does not say of whom (members present, voting members, all
members), mark UNCLEAR and compute the required votes for each reading. Show your
math (quorum, deadlines). Humans make every decision; you only check.

GOVERNANCE AGENT PROMPT (step 3)
You draft co-op General Assembly documents. Inputs: proposal, member count, GA date,
and the verified bylaw check. Output JSON {motion, agenda, email}. The motion has a
title, Whereas, Resolved, and [PROPOSER] / [SECONDER] placeholders. Reflect every
constraint from the check (vote threshold, committee review, notice deadline). Flag
any FAIL or UNCLEAR at the top. Never invent numbers: use placeholders like
[CURRENT AMOUNT]. Final decisions belong to humans.

PRELINT RULES (step 4, implement as deterministic checks)
- every rule has a status in PASS, FAIL, UNCLEAR, NOT_APPLICABLE
- every rule has a section and a quote found verbatim in the bylaws
- all 4 outputs are present: motion, bylaw check, agenda, notice email
- the motion contains [PROPOSER] and [SECONDER]
- no sentence decides for humans (reject phrases like "the motion is approved",
  "is hereby adopted", "has passed")
- no payments, no applicant decisions
Return pass/fail per rule so the UI can show them.

SAMPLE BYLAWS (prefill)
SAMPLE HOUSE CO-OP BYLAWS (fictional)
Article 1. Membership. The co-op has 40 voting members. Every resident is a member.
Article 2. General Assembly (GA). The GA is the highest decision-making body.
Section 2.1. A regular GA is held at least once per month during the academic term.
Section 2.2. Written notice of the agenda must be sent to all members at least
7 days before a regular GA.
Section 2.3. Quorum is 50 percent of voting members plus one.
Article 3. Motions.
Section 3.1. Any member may propose a motion. A motion needs a seconder
to be discussed.
Section 3.2. Ordinary motions pass by a simple majority of members present.
Section 3.3. Motions that change the budget by more than 5 percent need
a two-thirds majority and must be reviewed by the Finance Committee
at least 3 days before the GA.
Section 3.4. Changes to these bylaws need a two-thirds majority of all
voting members.
Article 4. Shifts. Each member works 4 hours of house duties per week.
Shifts are assigned by the Shift Manager and published every Sunday.

ACCEPTANCE TEST (must pass before you say done)
Input: the sample bylaws, 40 members, today 2026-10-07, GA 2026-10-17, proposal
"Raise the house food budget by 10%". Expected:
- quorum = 21 of 40
- Section 3.3 applies (two-thirds + Finance Committee review at least 3 days before
  the GA, i.e. by 2026-10-14); notice due by 2026-10-10
- vote threshold = UNCLEAR with both readings computed (14 votes if two-thirds of 21
  present, 27 if two-thirds of all 40)
- proposer and seconder = UNCLEAR (not named)
- Section 3.4 = NOT_APPLICABLE
- all 6+ quotes verified verbatim; all Prelint rules pass; motion contains
  [PROPOSER] and [SECONDER]
Run the pipeline, show me the real output, and tell me honestly what passed and what
failed. Do not claim success without running it.

WORKING STYLE
Explain each step in simple French before you do it (I am not an expert). Make small
steps, validate the .pipe before running it, and ask me before anything that
deploys, publishes, or needs a key I have not given you.
```
