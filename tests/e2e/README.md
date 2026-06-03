# Off-Duty — Playwright e2e

End-to-end checks that the web UIs (Owner Ops Console `/` + Customer Counter `/counter`)
work before a live demo. Catches a broken page/panel before it embarrasses you on stage.

## Run

```bash
cd integration/tests/e2e
npm install            # @playwright/test (chromium already cached on this machine)
npx playwright install chromium   # only if the browser is missing

npm run test:fast      # deterministic UI + API checks (no LLM) — fast, must always pass
npm run test:llm       # LLM-dependent flows (chat, MCP button) — slow, tolerant
npm test               # everything
npm run report         # open the HTML report
```

The app server is started automatically by `playwright.config.js` (`webServer` runs
`uvicorn app.main:app` from the integration root, or reuses one already on `:8080`).
Override the port with `PORT=...`.

## What's covered

- **api.spec.js** — `/health`, `/api/availability|summary|explain|db-health|digest|ops|timeline|approvals`
  return 200 + expected shape; input validation (empty chat → 422), graceful errors
  (bad ObjectId, non-image upload → 400, unknown evidence trace → 404). No LLM.
- **console.spec.js** — Owner Console loads; summary cards, "Needs you" approvals,
  MongoDB engine panel, MongoDB MCP panel + button, vision upload card, timeline, ask box.
- **counter.spec.js** — Customer Counter loads; greeting, live availability strip,
  suggestion chips, composer, 16px input (no iOS zoom).
- **llm.spec.js** `@llm` — counter chat returns a reply *or* a graceful message; the MCP
  button yields real `tool_calls` *or* a graceful error. Tolerant by design: the demo
  must degrade gracefully under Gemini/MCP cold-start or rate limits, never hard-crash.

> Tip: pair with `scripts/reset_demo.py --clean` before a rehearsal so the timeline and
> inventory start from a known-good baseline.
