# Off-Duty — an inventory-aware AI store manager for offline shops

**The owner is off duty; the agent runs the store — and proves every action in MongoDB.**
A multi-agent app (Google ADK + Gemini 3 on Vertex AI) over MongoDB Atlas. Cafe is the demo
vertical; the model is any offline store. Built for the **Google Cloud Rapid Agent Hackathon —
MongoDB track**.

## What it does

- **Customer Counter** (`/counter`) — customers order in natural language; answers are
  **grounded in live inventory** (never offers a sold-out item) and discounts stay inside the
  owner's rules (enforced in code, not just the prompt).
- **Owner Ops Console** (`/`) — a "while you were off-duty" digest, a one-click **"Needs you"**
  approval inbox (restocks + vision suggestions), an **Evidence drawer** that traces any agent
  action back to the **real MongoDB documents** it touched, a live **MongoDB engine** panel
  (aggregation + `explain` query plan), and a **MongoDB MCP** live-call button.
- **One order → a chain**: `create_order` → `inventory_event` → `restock_task`, all linked by a
  single `trace_id` and visible in the Evidence drawer.

## Why MongoDB (the moat)

| Capability | Where |
|---|---|
| Operational DB + **Aggregation** pipelines (+ `explain` plan) | owner summary / digest / ops |
| **Atlas Search** (`$search`, fuzzy) + **Vector Search** (`$vectorSearch`, Gemini 768-dim) | product matching in vision/ordering |
| **`agent_action_logs`** evidence trail (`trace_id` + `collection:id` refs → live docs) | Evidence drawer |
| **MongoDB MCP server — LIVE** read-only tool calls, logged & shown | `POST /api/mcp-proof` + console button |

## Quickstart

### Zero-setup (mock mode) — see the whole app in 30 seconds, no credentials

For teammates: clone, install, and run with **canned data** — no Atlas, no GCP, no keys.
Every screen, the chat, the Evidence drawer, and the MCP panel all work offline.

```bash
pip install -r app/requirements.txt
MOCK_MODE=true python -m uvicorn app.main:app --port 8080
# open http://localhost:8080  (console)  and  http://localhost:8080/counter
```

### Full (live MongoDB + Vertex)

```bash
gcloud auth application-default login            # Vertex AI runtime (default; no API key needed)
cp app/.env.example app/.env                     # set MONGODB_URI; GCP project/location default to ours
python scripts/reset_demo.py --snapshot          # capture a clean inventory baseline (first run)
python -m uvicorn app.main:app --port 8080
```

- **Demo**: follow [DEMO_SCRIPT.md](DEMO_SCRIPT.md) (3-min walk-through, pre-demo checklist).
- **Reset between rehearsals**: `python scripts/reset_demo.py --clean` (restores inventory,
  clears the demo timeline — otherwise rehearsal noise piles up).
- **Reliability**: `python scripts/run_demo_checks.py` (golden checks, currently 7/7).
- **Web e2e**: `cd tests/e2e && npm install && npm run test:fast` (Playwright).

## Runtime

Defaults to **Vertex AI** (`USE_VERTEX=true`) — `gcloud` ADC auth, no free-tier rate limit, and
the same path as Agent Engine deploy. `gemini-3-flash-preview` runs on Vertex location `global`.
Set `USE_VERTEX=false` + `GEMINI_API_KEY` to use the AI Studio key instead.

## Credentials

You do **not** need any credentials to run and explore the app — use **`MOCK_MODE=true`** (above).

For the live path, bring your **own** access (never reuse a teammate's): a MongoDB Atlas
connection (ask the maintainer to add you to the Atlas project) and a Google Cloud project
(`gcloud auth application-default login`). Put them in `app/.env` — it is **git-ignored and
never committed**. Secrets stay in `.env` / a secret manager, never in code or the repo.

## Layout

```text
app/        FastAPI + ADK agents (supervisor + ordering/inventory/vision/owner + mcp_agent)
  core/     product_search ($search/$vectorSearch), audit (evidence trail), mcp (MCP toolset)
  flows/    owner_read (summary/timeline/evidence/explain/impact/approvals)
  static/   console.html (Owner Ops Console) · counter.html (Customer Counter)
scripts/    run_demo_checks.py (eval) · reset_demo.py (demo reset) · setup_search.py (indexes)
tests/e2e/  Playwright suite for the web UIs
```

See [DEMO_SCRIPT.md](DEMO_SCRIPT.md) for the 3-minute walkthrough.
