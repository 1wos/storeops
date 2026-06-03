# Off-Duty — 3-minute demo script

> Maps to the app that **actually exists** in this repo (Owner Ops Console `/` +
> Customer Counter `/counter`). The wow moment is the **Evidence drawer** — clicking one
> agent action and seeing the real MongoDB documents it touched.

## Pre-demo checklist (do this 5 min before)

```bash
# 1) clean stage — fresh timeline + restored inventory (otherwise rehearsal noise shows)
python scripts/reset_demo.py --clean

# 2) start the server (Vertex runtime, no rate limit)
python -m uvicorn app.main:app --port 8080

# 3) sanity: health should say runtime "vertex" and the model
curl -s localhost:8080/health     # {"ok":true,...,"model":"gemini-3-flash-preview","runtime":"vertex"}

# 4) PRE-WARM the MCP call once (cold start is ~20s; warm is fast) so the live click is snappy
curl -s -X POST localhost:8080/api/mcp-proof >/dev/null
```

- Open two tabs: **Console** `http://localhost:8080/` and **Counter** `http://localhost:8080/counter`.
- **Do NOT show a terminal/editor** on screen — `.env` holds live credentials (rotate beforehand).
- Have a **shelf photo** ready for the vision beat.

## Script (≈3:00)

**0:00 — The hook (Console).** "This is Off-Duty — an AI store manager for offline shops.
The owner is *off duty*, so the agent ran the store." Point at the **"While you were
off-duty"** digest: orders, revenue, low-stock, and the green **`~N min saved · X actions
automated`** stat. "It didn't just answer questions — it took actions, and it can show its work."

**0:25 — A real order (Counter).** Switch to the Counter tab. Click **"What's available?"** —
note the answer only offers **in-stock** items (Cold Brew, Oat Milk Latte, Brownie), grounded
in live inventory, never something sold out. Then type **"A cold brew and a brownie, please"**
→ the agent confirms and places the order. "Availability-grounded, and the discount stays
inside the owner's rules — enforced in code, not just the prompt."

**0:55 — The chain reaction (Console).** Back to Console (it live-refreshes). The order
just **decremented inventory**, and because stock crossed the threshold a **restock task**
appeared in the **"⚠ Needs you"** inbox at the top. "One customer sentence triggered
order → inventory event → restock — all linked."

**1:20 — THE WOW: Evidence (Console).** In **Agent Activity**, click the trace for that order.
The **Evidence drawer** opens: every step (`create_order`, `write_inventory_event`,
`create_restock_task`) **and the actual MongoDB documents** each step read/wrote, resolved by
`trace_id` + `collection:id` references. "This is the trust layer — every agent action is
auditable back to the source document in MongoDB. That's the moat."

**1:55 — Vision (Console).** In the **Store-State** card, upload the shelf photo. Gemini Vision
reads the shelf, matches products via **Atlas Search + Vector Search**, and drops a suggestion
into **"Needs you"**. Each item has **Approve / Reject** (and a 5-second **Undo** toast) —
human-in-the-loop. Approve it. "The owner stays in control; the agent proposes, the owner
disposes — approve, reject, or undo, all logged to the evidence trail."

**2:25 — MongoDB is the backbone (Console).** Expand **"MongoDB engine"** (shows the real
aggregation pipeline + `explain` query plan + collections). Then expand **"MongoDB MCP ·
run a live tool call"** and click the button → real `list-collections` / `count` calls
**through the MongoDB MCP server**, logged to the evidence trail. "Operational DB,
aggregation, Atlas Search, Vector Search, and the MCP server — one platform."

**2:50 — Close.** "Off-Duty: an inventory-aware agent that takes action and proves every
one of them in MongoDB. Cafe today, any offline store next."

## If something fails live
- **MCP click is slow / times out** → it pre-warms in the checklist; if it still stalls, say
  "cold start" and fall back to the pre-captured `tool_calls=[list-collections, count]` screenshot.
- **Chat is slow** → Vertex has no free-tier limit, but if a call lags, the UI shows a thinking
  state, not a freeze; just wait or re-ask.
- **Numbers look off** → you forgot `reset_demo.py --clean`; re-run it and refresh.
