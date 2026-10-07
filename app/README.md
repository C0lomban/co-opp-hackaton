# CoopOS web app (Track A)

## Run it (no install needed, just Node 18+)
```
node app/server.js
```
Open http://localhost:3000

## Modes
- **Demo (offline)**: rule based agents, no API key. Always works, use it as the demo backup.
- **Live AI (Claude)**: create `app/.env` with ONE of these lines, then restart:
  - `KYLON_API_KEY=pak_...` (uses Kylon's hackathon credits, Claude via the Kylon proxy)
  - `ANTHROPIC_API_KEY=sk-ant-...` (direct Anthropic account)
  Every bylaw quote returned by the model is checked against the bylaws text;
  anything that can't be found is downgraded to UNCLEAR.

## Plug in Track B / Track C
All agent logic lives in `app/agents.js`. The app only calls
`runPipeline({ bylaws, memberCount, gaDate, proposal, houseName, today, mode })`
and expects back `{ mode, checks[], motion, agenda[], email, log[] }`.
Replace `runCompliance` / `runGovernance` (or the whole `runPipeline`) with
the real agents, keep the same shapes, and the UI keeps working.
`log[]` is the evidence trail for the orchestration track.
