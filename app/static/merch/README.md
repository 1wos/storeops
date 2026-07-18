# StoreOps — Evidence-Grounded Merchandising Alignment Simulator

An interactive 3D tool that lets a small-business owner **try a store layout before rearranging it**,
and scores how well that layout follows *proven* consumer-psychology / retail-merchandising principles.
Every point of the score decomposes, in a **"Why this score?"** drawer, into a specific rule + its
coefficient + an evidence sensitivity range + a reliability badge + the real paper it comes from.

> Single self-contained file: [`../layout3d.html`](../layout3d.html) (Three.js).
> Pure scoring model, shared by the UI and the verifiers: [`model.js`](./model.js).

## What it does
- **0–100 Merchandising Alignment score** — how close your layout is to the evidence-optimal one.
- **"Why this score?" drawer** — every point traces to a cited rule (eye-level, endcap lift, checkout
  impulse, complementary adjacency, facings, low-stock cost, entrance exposure, right-side bias…),
  each badged by reliability (🟢 strong · 🔵 peer-reviewed · 🟣 meta-analysis · 🟠 heuristic · ⚪ assumption).
- **Advisor + Optimize** — evidence-tagged moves and the best layout the model can find.
- **Grounded shopper path** — a mission ("Coffee run" vs "Full order") walks a clear aisle
  entrance→shelves→checkout, with a **travel-distance indicator** (Hui 2013 / Larson 2005), kept
  *out* of the score and labelled "directional, not calibrated".
- Two store types (Café, Convenience), heatmap, top view, themes, before/after compare, shareable URL.

## What it deliberately does NOT do
- **It does not predict a revenue number (₩/$).** The honest research gives directional effects with
  wide uncertainty; a per-store sales figure would be false precision. The compare bar exposes the
  model's *directional* bet ("alignment up"), never an amount. Refusing to fake a number is the point.
- The composite is an **alignment index, not a validated sales model** — see the "How the rules
  combine" note in the drawer (effects are multiplied as if independent, summed across products,
  using coefficients transferred from mostly US/EU grocery/CPG field studies; never calibrated to
  real sales).

## Verification (the credibility anchor)
The UI and the checkers **import the same `model.js`**, so what is verified is what ships.

```
cd verify && npm run verify
#  ✅ 1,360 property trials — capacity, optimizer-dominance, alignment endpoints,
#     advisor-consistency, URL round-trip, decompression, mission-route invariants
#  ✅ geometry — 0 fixture overlaps · 0 stand-points-in-shelf · 0 route-clips
#     (across stores × room sizes × missions)
```

## Prior art / positioning
No open-source project combines **3D layout + shopper path + evidence-grounded cited scoring +
small-business focus**. Closest is **StoreGrid** (RL trajectories + 3D twin) — but it is a nascent
research artifact with no cited scorecard and no small-biz framing. Academic shelf-space optimizers
(`ShelfSpaceAllocation.jl`) have coefficients but no 3D/path; `blueprint3d` gives 3D layout only;
`covid19-supermarket-abm` (PLoS ONE 2021) gives graph-based paths but epidemiology, not merchandising.
The novelty here is the **packaging + a transparent, citation-decomposed scorecard**.

## Key evidence
Drèze/Hoch/Purk 1994 · Chandon 2009 · Chen/Burke/Hui 2021 · Eisend 2014 (meta, elasticity ≈0.17) ·
Otterbring 2018 (debunks the entrance "decompression zone") · Nakamura 2014 · Ejlerskov 2018 (PLOS
Med) · Bezawada 2009 · Manchanda 1999 · Hui 2013 · Larson/Bradlow/Fader 2005 · Corstjens & Doyle 1981.
Full citations + coefficients live in `PRINCIPLES` inside [`model.js`](./model.js).

## Add a scoring rule (contribution hook)
1. Add an entry to `PRINCIPLES` in `model.js`: `{ label, coefficient(s), evLow/evHigh range,
   reliability, citations[], tip, heuristic?, contested? }`.
2. Wire its multiplier/term into `placementMults` or `storeScore`, tagged with the principle id.
3. Run `cd verify && npm run verify` — it must stay green.
Every visible number must trace to a citation with a reliability badge, or it does not get a number.

## Run
Serve the `app/static/` directory with any static file server, then open `layout3d.html`:
```
cd app/static && python3 -m http.server 8900
# → http://localhost:8900/layout3d.html
```
(Imports are relative — no framework or backend required.)
