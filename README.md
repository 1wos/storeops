# Off-Duty — an inventory-aware AI store manager for offline shops

**The owner is off duty; the agent runs the store — and proves every action in MongoDB.**
A multi-agent app (Google ADK + Gemini 3 on Vertex AI) over MongoDB Atlas. Cafe is the demo
vertical; the model is any small offline store. Built for the **Google Cloud Rapid Agent
Hackathon — MongoDB track**.

**Live demo:** https://off-duty-180895049757.us-central1.run.app
(Owner Ops Console at `/`, Customer Counter at `/counter`)

## What it does

- **Customer Counter** (`/counter`) — customers order in natural language; answers are
  **grounded in live inventory** (never offers a sold-out item) and discounts stay inside the
  owner's rules (enforced in code, not just the prompt). Live availability chips, suggested
  order chips, and stepped "thinking" feedback.
- **Owner Ops Console** (`/`) — chat-forward dashboard:
  - **Ask Off-Duty** chat that **streams the live agent trace** (`Routing → Reading sales →
    …`) over SSE, then prints a **MongoDB grounding receipt** under each answer, linked to the
    exact evidence trace it used.
  - A "while you were off-duty" **digest** + a **daily ops report** with **6 reconciliation
    integrity checks**.
  - A one-click **"Needs you"** approval inbox (restocks, vision suggestions, **review
    actions**) with 5-second Undo — human-in-the-loop on every write.
  - **Review-to-Action**: classify a customer review → match the product via **Atlas
    Search + Vector Search** → check live stock → draft a reply → route anything actionable
    to "Needs you" — each step traced.
  - **Store-State vision**: upload a shelf photo → Gemini reads the stock → suggestions.
  - An **Evidence drawer** that traces any agent action back to the **real MongoDB documents**
    it touched, a live **MongoDB engine** panel (aggregation + `explain` query plan), and a
    **MongoDB MCP** live-call button.
  - Sticky section tabs (Overview / Reviews / Activity / MongoDB), a one-click **Run live
    demo** hero, and a **light/dark theme** toggle.
- **One order → a chain**: `create_order` → `inventory_event` → `restock_task`, all linked by a
  single `trace_id` and visible in the Evidence drawer.

## Why MongoDB (the moat)

| Capability | Where |
|---|---|
| Operational DB + **Aggregation** pipelines (+ `explain` plan) | owner summary / digest / daily report / reconciliation |
| **Atlas Search** (`$search`, fuzzy) + **Vector Search** (`$vectorSearch`, Gemini 768-dim) + **RRF hybrid** | product matching in vision / ordering / review-to-action |
| **`agent_action_logs`** evidence trail (`trace_id` + `collection:id` refs → live docs) | Evidence drawer + grounding receipt |
| **MongoDB MCP server — LIVE** read-only tool calls, logged & shown | `POST /api/mcp-proof` + console button |

## Architecture

```
Customer (Counter) ─┐
                    ├─► FastAPI on Cloud Run ─► ADK Supervisor (Gemini 3, Vertex) ─► ordering / inventory / vision / owner sub-agents
Owner (Console) ────┘         │  SSE stream                  │ intent-based delegation        │
                              │                              ▼                                ▼
                              └─► MongoDB MCP server    Vertex AI · Gemini 3            MongoDB Atlas
                                  (live read-only)      + gemini-embedding-001          Aggregation · Atlas Search
                                                                                        $vectorSearch · RRF · agent_action_logs
```

The supervisor delegates by **intent**, not keywords; every meaningful read/write/recommend is
auto-logged to `agent_action_logs` so the owner can audit the whole chain by `trace_id`.

## Security & Architecture (Well-Architected aligned)

Reviewed against the Google Cloud **Well-Architected Framework — Security pillar**:

- **Secrets out of code (shift-left):** no credentials in the repo or images. `app/.env` is
  git-ignored; runtime secrets come from Cloud Run env / `.env` only. The repo ships only
  `*.env.example` placeholders.
- **Identity without embedded keys:** Vertex AI is reached via **Application Default
  Credentials** with a service account scoped to `roles/aiplatform.user` — no API key in the
  app.
- **Least privilege:** the MongoDB user is scoped to the application database; the **MongoDB
  MCP server runs read-only**.
- **Use AI responsibly (SAIF):** answers are **grounded in tool results** (anti-hallucination);
  every action is written to `agent_action_logs` with a `trace_id` (fully auditable); and all
  **write actions are gated behind human approval** ("Needs you" HITL, with Undo).
- **Cloud Run hardening:** stateless container, binds `0.0.0.0:$PORT`, built from source; TLS
  to Atlas.

## Quickstart

### Zero-setup (mock mode) — see the whole app in 30 seconds, no credentials

Clone, install, and run with **canned data** — no Atlas, no GCP, no keys. Every screen, the
streaming chat, the Evidence drawer, and the MCP panel all work offline.

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
- **Reset between rehearsals**: `python scripts/reset_demo.py --clean`.
- **Reliability**: `python scripts/run_demo_checks.py` (golden checks, 10/10).
- **Eval pack**: `python scripts/run_eval_golden.py` (LLM accuracy harness on a labelled golden
  set); `python scripts/prepare_review_seed.py` loads the review seed.
- **Web e2e**: `cd tests/e2e && npm install && npm run test:fast` (Playwright).

## Data sources

- **Reviews** for the Review-to-Action flow are seeded from public datasets — Hugging Face
  `yelp_review_full` and a Kaggle restaurant-reviews set — normalised into the `reviews`
  collection by `scripts/prepare_review_seed.py`. Raw downloads are **git-ignored** (not
  redistributed); only a small synthetic example seed is committed.
- **Inventory / orders** use a small curated demo seed (`store_001`). The product uses Gemini
  for multimodal shelf reading; it does **not** train on any dataset.

## Runtime

Defaults to **Vertex AI** (`USE_VERTEX=true`) — `gcloud` ADC auth, no free-tier rate limit, and
the same path as Agent Engine deploy. `gemini-3-flash-preview` runs on Vertex location `global`;
embeddings use `gemini-embedding-001` (768-dim). Set `USE_VERTEX=false` + `GEMINI_API_KEY` to
use the AI Studio key instead. Streaming chat is served at `POST /api/chat/stream` (SSE) with
`POST /api/chat` kept as a non-streaming fallback.

## Layout

```text
app/        FastAPI + ADK agents (supervisor + ordering/inventory/vision/owner + mcp_agent)
  core/     product_search ($search/$vectorSearch/RRF), audit (evidence trail), mcp (MCP toolset)
  flows/    owner_read (summary/timeline/evidence/explain/impact/approvals/daily report/reconcile)
            review_to_action (classify → match → stock → reply → route)
  static/   console.html (Owner Ops Console) · counter.html (Customer Counter)
scripts/    run_demo_checks.py (golden checks) · run_eval_golden.py (LLM accuracy harness)
            prepare_review_seed.py (review seed) · reset_demo.py · setup_search.py (indexes)
tests/e2e/  Playwright suite for the web UIs
Dockerfile  Cloud Run source build (Python + Node for the MongoDB MCP server)
```

See [DEMO_SCRIPT.md](DEMO_SCRIPT.md) for the 3-minute walkthrough.
