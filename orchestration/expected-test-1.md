# Expected result — Test 1

Input: `docs/sample-bylaws.txt`, 40 members, proposal "Raise the house food budget by 10%".

| Rule | Expected status | Section | Why |
|---|---|---|---|
| Who can propose | UNCLEAR | 3.1 | Any member may propose; proposer not named yet |
| Seconder | UNCLEAR | 3.1 | Seconder required; not named yet |
| Notice | PASS or FAIL | 2.2 | Notice ≥7 days before GA — depends on GA date |
| Quorum | UNCLEAR | 2.3 | 50% of 40 + 1 = 21 present; checked on the day |
| Vote threshold | UNCLEAR | 3.3 | +10% > 5% → two-thirds majority; of members present or all members? Not stated |
| Finance Committee review | UNCLEAR or FAIL | 3.3 | Review ≥3 days before GA; FAIL if that date has passed |
| Bylaw change | Not applicable | 3.4 | Budget change, not a bylaw change |

The "two-thirds of whom?" UNCLEAR is the key demo moment: the agent flags ambiguity instead of guessing.
