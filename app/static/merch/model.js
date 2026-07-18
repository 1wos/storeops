// ============================================================================
//  StoreOps · Merchandising Alignment Model  (single source of truth)
//  Pure ES module — NO three.js, NO DOM. Imported by BOTH:
//    · the 3D UI  (/static/layout3d.html)      → what users actually run
//    · the verifier (verify_merch.mjs, Node)   → 999-config mechanical check
//  So every invariant the verifier proves holds for the code that ships.
//
//  Design principle: every point of the score decomposes into a NAMED rule,
//  and every rule carries its real citation + evidence reliability. Nothing is
//  a black box. The coefficients below are grounded in a 13-topic literature
//  review; see PRINCIPLES[*].cites. Where a number is a modeling choice rather
//  than a measured value it is flagged (reliability:'input' or heuristic:true).
// ============================================================================

// ── Evidence-graded coefficients (the ONLY place these live) ────────────────
export const K = {
  // vertical shelf position tiers (Drèze/Hoch/Purk 1994; Chandon 2009; Chen 2021)
  VTIER: { eye: 1.35, top: 1.30, waist: 1.00, low: 0.68 },
  // right-side lateral attention bias (Chen/Burke/Hui 2021) — modest, real
  RIGHT_BONUS: 1.15,
  // entrance exposure (Otterbring 2018 debunks the decompression penalty)
  ENTRANCE: 0.95,          // neutral-to-slightly-below, evidence-based default
  ENTRANCE_DECOMP: 0.55,   // the DEBUNKED penalty — only if user opts in
  // endcap lift, price-independent, category-tiered (Nakamura 2014; Tan 2018)
  ENDCAP_BASE: 0.25, ENDCAP_IMPULSE: 0.85, ENDCAP_REAR: 1.10, ENDCAP_CAP: 2.15,
  // checkout impulse, gated to cheap impulse goods, capped (Ejlerskov 2018)
  CHECKOUT_IMPULSE: 0.90, CHECKOUT_MIN_IMPULSE: 0.40,
  // back-wall destination pull — mechanism supported, magnitude heuristic (Hui 2013)
  BACKWALL: 1.06,
  // complementary adjacency — capped at marketing-mix size, co-incidence-discounted
  ADJ_COEF: 0.10, ADJ_COINCIDENCE: 0.35, ADJ_CAP: 0.14,   // (Bezawada 2009; Manchanda 1999)
  // shelf-space / facings — saturating, elasticity ≈ 0.17 (Eisend 2014 meta)
  FACINGS_ELASTICITY: 0.17,
  // low-stock opportunity cost, scaled by how prime the zone is (Drèze 1994; Corstjens 1981)
  LOWSTOCK_K: 0.75,
};

// ── PRINCIPLES: the inspectable rulebook shown in "Why this score?" ──────────
// reliability: 'strong' peer-reviewed-strong · 'peer' peer-reviewed ·
//              'meta' meta-analysis · 'heuristic' practitioner lore ·
//              'input' foundational assumption / modeling choice (uncited)
export const PRINCIPLES = {
  inputs: {
    label: 'Store inputs (velocity × margin)',
    reliability: 'input', heuristic: false, contested: false,
    coefText: 'demand ≈ 100 · velocity · (1 + 0.4·margin)',
    rangeText: 'owner-supplied assumptions, not measured',
    tip: 'The baseline demand for each product is an assumption you provide (how fast it sells, its margin) — not an evidence-based effect. Everything else adjusts this.',
    cites: ['Modeling choice — baseline is a normalization anchor, not a cited coefficient.'],
  },
  vertical: {
    label: 'Vertical shelf position',
    reliability: 'strong', heuristic: false, contested: false,
    coefText: 'eye ×1.35 · top ×1.30 · waist ×1.00 · low ×0.68',
    rangeText: 'low ×0.68 … eye ×1.35 (top comparable to eye, not proven equal)',
    tip: 'Eye/hand level sells well, but field eye-tracking shows top shelf can match it — "eye level is buy level" is a slogan, not a law. Bottom shelves get far fewer glances.',
    cites: [
      'Chen, Burke, Hui & Leykin (2021), Lateral & Vertical Biases in Consumer Attention, J. Marketing Research 58(6):1120-1141',
      'Chandon, Hutchinson, Bradlow & Young (2009), Does In-Store Marketing Work?, J. Marketing 73(6):1-17',
      'Drèze, Hoch & Purk (1994), Shelf Management and Space Elasticity, J. Retailing 70(4):301-326',
    ],
  },
  rightside: {
    label: 'Right-side attention bias',
    reliability: 'strong', heuristic: false, contested: false,
    coefText: 'favored lateral side ×1.15',
    rangeText: '×1.05 … ×1.25',
    tip: 'Shoppers really do look to their right more as they move through a store (in-store eye-tracking). The related "always circulate counter-clockwise" claim is disputed, so flow direction is a toggle.',
    cites: [
      'Chen, Burke, Hui & Leykin (2021), Lateral & Vertical Biases in Consumer Attention, J. Marketing Research 58(6):1120-1141',
      'Gröppel-Klein & Bartmann (2009), Turning Bias and Walking Patterns (found clockwise superior) — Marketing:JRM',
    ],
  },
  entrance: {
    label: 'Entrance exposure',
    reliability: 'peer', heuristic: false, contested: false,
    coefText: 'entrance ×0.95  (decompression penalty ×0.55 only if opted in)',
    rangeText: '×0.85 … ×1.10',
    tip: 'The "customers ignore the entrance (decompression zone)" idea is contradicted by the one peer-reviewed field test of it, which found entrance displays LIFTED sales. So the front door is not penalized by default. (Single study — directional, not settled law.)',
    cites: [
      'Otterbring (2018), Decompression zone deconstructed, Int. J. Retail & Distribution Mgmt 46(11/12):1108-1124',
      'Underhill (1999), Why We Buy — trade book, proprietary data (the debunked source)',
    ],
  },
  endcap: {
    label: 'Endcap lift',
    reliability: 'strong', heuristic: false, contested: false,
    coefText: '×(1.25 … 2.15) by impulse category · rear endcap ×1.10',
    rangeText: '+23% (beer) … +114% (tea) unit-sales lift, no price cut',
    tip: 'Moving a product to an end-of-aisle cap lifts sales even with no discount, +25% to +100%+ depending on category. Rear (back-of-store) endcaps outpull front ones. The upper ladder is extrapolated from category studies.',
    cites: [
      'Nakamura et al. (2014), Sales impact of end-of-aisle placement, Social Science & Medicine',
      'Tan et al. (2018), Sales effectiveness of differently located endcaps, J. Retailing & Consumer Services 43:200-208',
      'Schweiger et al. (2023), In-store endcap projections, J. Retailing 99(1):5-16',
    ],
  },
  checkout: {
    label: 'Checkout impulse',
    reliability: 'strong', heuristic: false, contested: false,
    coefText: '×(1 + impulse·0.90) for cheap impulse goods only; ≈×1 otherwise',
    rangeText: 'checkout removal cut such purchases ~17% (76% for on-the-go)',
    tip: 'Checkout is the single strongest impulse spot — but only for small, cheap, low-consideration treats. Big or considered items get almost no lift here.',
    cites: [
      'Ejlerskov et al. (2018), Supermarket checkout food policies, PLOS Medicine 15(12):e1002712',
      'Inman, Winer & Ferraro (2009), In-Store Decision Making, J. Marketing 73(5):19-29 (46%→93% unplanned)',
    ],
  },
  backwall: {
    label: 'Back-wall destination pull',
    reliability: 'peer', heuristic: true, contested: false,
    coefText: 'destination staple on back wall ×1.06',
    rangeText: '×1.00 … ×1.12 (magnitude is a heuristic, mechanism supported)',
    tip: 'Putting a must-have item deep makes shoppers walk the store, and longer trips mean bigger baskets. The mechanism is well supported; the exact 6% is a reasonable guess, not a measured value.',
    cites: [
      'Hui, Inman, Huang & Suher (2013), In-Store Travel Distance & Unplanned Spending, J. Marketing 77(2):1-16',
      'Tan et al. (2018), Differently located endcaps, J. Retailing & Consumer Services 43:200-208',
      'Larson, Bradlow & Fader (2005), Supermarket Shopping Paths, IJRM 22(4):395-414 (caveat: deep = under-exposed)',
    ],
  },
  adjacency: {
    label: 'Complementary adjacency',
    reliability: 'strong', heuristic: false, contested: false,
    coefText: 'co-located complements: +min(base)·0.10·(1−0.35 co-incidence), capped',
    rangeText: 'comparable to price/feature/display effects, not larger',
    tip: 'Pairing complements lifts sales — but only the part that happens BECAUSE they are placed together, not the part where both just end up in most carts anyway (co-incidence). The lift is asymmetric and capped at marketing-mix size.',
    cites: [
      'Bezawada, Balachander, Kannan & Shankar (2009), Cross-Category Effects of Aisle & Display Placement, J. Marketing 73(3):99-117',
      'Manchanda, Ansari & Gupta (1999), The Shopping Basket, Marketing Science 18(2):95-114',
      'Agrawal & Srikant (1994), Apriori / association rules, VLDB',
    ],
  },
  facings: {
    label: 'Facings / shelf space',
    reliability: 'meta', heuristic: false, contested: false,
    coefText: 'saturating, elasticity ≈ 0.17 (diminishing returns)',
    rangeText: '+10% space → ~+1.7% sales, on average',
    tip: 'More facings help only a little and quickly plateau. Keep enough to avoid empty shelves, but do not over-cram your winners — space is worth far less than position.',
    cites: [
      'Eisend (2014), Shelf Space Elasticity: A Meta-Analysis (1,268 estimates, avg 0.17), J. Retailing 90(2):168-181',
      'Drèze, Hoch & Purk (1994), Shelf Management and Space Elasticity, J. Retailing 70(4):301-326',
    ],
  },
  lowstock: {
    label: 'Low-stock opportunity cost',
    reliability: 'strong', heuristic: false, contested: false,
    coefText: 'penalty ∝ base · (zone selling-power − 1)',
    rangeText: 'scales with how prime the zone is',
    tip: 'Do not spend your best shelf on something that keeps selling out — an empty prime spot is lost money. The penalty grows the more prime the zone.',
    cites: [
      'Drèze, Hoch & Purk (1994), Shelf Management and Space Elasticity (min-facings/anti-stockout), J. Retailing 70(4):301-326',
      'Corstjens & Doyle (1981), Optimizing Retail Space Allocations (out-of-stock cost), Management Science 27(7):822-833',
    ],
  },
};
export const PRINCIPLE_ORDER = ['vertical','endcap','checkout','rightside','entrance','adjacency','backwall','facings','lowstock'];

// ── Zone template — positions are FRACTIONS of the room (polygon-ready) ──────
// v1 rooms are rectangles from width/depth; zones re-place themselves so the
// sliders (and, in v2, a drag-corner polygon editor) actually move the store.
// Perimeter + centre-island layout with a clear ring aisle. Fractions chosen so
// fixtures never overlap and a walkable ring stays open (verified by geom_check.mjs).
const ZONE_TPL = [
  { id:'entrance', name:'Entrance',     fx:-0.34, fz:0.92,  cap:1, vTier:'waist', lateral:null,    entrance:true,  traffic:0.95, vis:0.70, note:'just inside the door' },
  { id:'counter',  name:'Checkout',     fx:0.60,  fz:0.90,  cap:2, vTier:'waist', lateral:'right', checkout:true,  traffic:0.90, vis:0.75, note:'impulse at the till' },
  { id:'endcap',   name:'Endcap (rear)',fx:-0.90, fz:0.02,  cap:1, vTier:'waist', lateral:'left',  endcap:true, rear:true, traffic:0.60, vis:0.80, note:'end-of-aisle cap' },
  { id:'power',    name:'Power Wall',   fx:0.90,  fz:0.02,  cap:2, vTier:'eye',   lateral:'right',                traffic:0.70, vis:0.85, note:'right-hand wall' },
  { id:'eye',      name:'Eye-level',    fx:0.00,  fz:0.34,  cap:2, vTier:'eye',   lateral:'center',               traffic:0.65, vis:0.90, note:'centre island, eye height' },
  { id:'lower',    name:'Lower Shelf',  fx:0.00,  fz:-0.40, cap:3, vTier:'low',   lateral:'center',               traffic:0.60, vis:0.40, note:'centre island, bottom' },
  { id:'back',     name:'Back Wall',    fx:0.00,  fz:-0.92, cap:2, vTier:'eye',   lateral:'center', backwall:true, traffic:0.35, vis:0.60, note:'destination pull, deep' },
];

export function buildZones(roomW = 12, roomD = 12) {
  const mx = Math.max(1.4, roomW * 0.14), mz = Math.max(1.4, roomD * 0.14);
  const arr = ZONE_TPL.map(z => ({
    ...z,
    x: +(z.fx * (roomW / 2 - mx)).toFixed(3),
    z: +(z.fz * (roomD / 2 - mz)).toFixed(3),
  }));
  arr._fs = fixtureSize(roomW, roomD); arr._room = { W: roomW, D: roomD };
  return arr;
}
export const zoneById = (zones, id) => zones.find(z => z.id === id);

// Fixture footprint (XZ axis-aligned box) — SINGLE SOURCE shared by the 3D UI
// (buildZones) and the geometry verifier, so "does the shopper clip a shelf"
// is a checkable fact, not a guess. Must match the mesh sizes in layout3d.html.
export function fixtureSize(roomW, roomD) {
  const cl = (v,a,b)=>Math.max(a,Math.min(b,v));
  return { sx: cl(roomW*0.18, 1.5, 2.5), sz: cl(roomD*0.13, 1.0, 1.7) };
}
export function fixtureFootprint(z, roomW, roomD) {
  const { sx, sz } = fixtureSize(roomW, roomD);
  const d = z.checkout ? sz*0.8 : sz;          // counter is shallower
  return { id:z.id, minx:z.x-sx/2, maxx:z.x+sx/2, minz:z.z-d/2, maxz:z.z+d/2, sx, sz:d };
}

// ── STORE PRESETS ────────────────────────────────────────────────────────────
// Adding a store = add ONE entry here (products + a furnished default layout).
// Nothing else in the app needs to change. v1 ships the two verticals closest to
// the grocery/convenience/food-service field studies the coefficients come from;
// external validity to café/convenience is ASSUMED, not measured.
export const STORES = {
  cafe: {
    label: 'Café', icon: '☕',
    products: [
      { id:'coldbrew', name:'Cold Brew',      kind:'cup',    velocity:.90, margin:.45, impulse:.50, cheap:false, cat:'beverage', comp:['brownie'],   color:0x5AA9E6 },
      { id:'oatlatte', name:'Oat Milk Latte', kind:'cup',    velocity:.85, margin:.50, impulse:.40, cheap:false, cat:'beverage', comp:['croissant'], color:0xD8C4A0 },
      { id:'brownie',  name:'Brownie',        kind:'pastry', velocity:.60, margin:.65, impulse:.80, cheap:true,  cat:'treat',    comp:['coldbrew'],  low:true, color:0x7A4A2B },
      { id:'croissant',name:'Croissant',      kind:'croissant',velocity:.55, margin:.55, impulse:.60, cheap:true, cat:'bakery',  comp:['oatlatte'],  color:0xD79A3E },
      { id:'cookie',   name:'Cookie',         kind:'cookie', velocity:.50, margin:.70, impulse:.85, cheap:true,  cat:'treat',    comp:[],            color:0xC98A4B },
      { id:'water',    name:'Bottled Water',  kind:'bottle', velocity:.95, margin:.20, impulse:.20, cheap:true,  cat:'staple',   comp:[], destination:true, color:0x7FC8E6 },
      { id:'giftcard', name:'Gift Card',      kind:'card',   velocity:.20, margin:.90, impulse:.70, cheap:false, cat:'addon',    comp:[],            color:0xF0664F },
    ],
    layout: { coldbrew:'eye', oatlatte:'power', brownie:'eye', croissant:'power', cookie:'endcap', giftcard:'counter', water:'back' },
  },
  convenience: {
    label: 'Convenience', icon: '🏪',
    products: [
      { id:'energy',    name:'Energy Drink',  kind:'can',      velocity:.85, margin:.40, impulse:.70, cheap:true,  cat:'beverage',    comp:['onigiri'],  color:0x63D471 },
      { id:'water',     name:'Bottled Water', kind:'bottle',   velocity:.95, margin:.20, impulse:.20, cheap:true,  cat:'staple',      comp:[], destination:true, color:0x7FC8E6 },
      { id:'onigiri',   name:'Rice Ball',     kind:'onigiri',  velocity:.80, margin:.35, impulse:.30, cheap:true,  cat:'meal',        comp:['energy'],   color:0xF2EFE6 },
      { id:'cupnoodle', name:'Cup Noodle',    kind:'noodlecup',velocity:.75, margin:.40, impulse:.35, cheap:true,  cat:'meal',        comp:[],           color:0xE0663F },
      { id:'gum',       name:'Gum',           kind:'gumbox',   velocity:.50, margin:.60, impulse:.90, cheap:true,  cat:'treat',       comp:[], low:true, color:0x4FC3E8 },
      { id:'chocolate', name:'Chocolate Bar', kind:'bar',      velocity:.60, margin:.55, impulse:.85, cheap:true,  cat:'treat',       comp:[],           color:0x6B3F2A },
      { id:'charger',   name:'Phone Charger', kind:'smallbox', velocity:.25, margin:.75, impulse:.50, cheap:false, cat:'electronics', comp:[], destination:true, color:0xF0664F },
      { id:'soda',      name:'Soft Drink',    kind:'can',      velocity:.80, margin:.45, impulse:.60, cheap:true,  cat:'beverage',    comp:['onigiri'],  color:0xE0A23D },
    ],
    layout: { energy:'eye', water:'back', onigiri:'power', cupnoodle:'lower', gum:'counter', chocolate:'counter', charger:'endcap', soda:'power' },
  },
};
export const productIndex = products => Object.fromEntries(products.map(p => [p.id, p]));

// ── Default per-product demand (a foundational INPUT, badged as assumption) ──
export const base = p => 100 * p.velocity * (1 + p.margin * 0.4);

// ── Per-placement multiplier breakdown (one product in one zone) ─────────────
// Returns the list of {pid, mult} contributions so the UI can decompose them.
export function placementMults(p, z, ctx, off) {
  const m = [];
  const on = id => !off || !off.has(id);
  if (on('vertical') && z.vTier) m.push({ pid:'vertical', mult: K.VTIER[z.vTier] ?? 1 });
  if (on('rightside') && z.lateral) {
    const favored = ctx.circulation === 'clockwise' ? 'left' : 'right';
    m.push({ pid:'rightside', mult: z.lateral === favored ? K.RIGHT_BONUS : 1.0 });
  }
  if (on('entrance') && z.entrance)
    m.push({ pid:'entrance', mult: ctx.decompression ? K.ENTRANCE_DECOMP : K.ENTRANCE });
  if (on('endcap') && z.endcap) {
    let mult = 1 + K.ENDCAP_BASE + p.impulse * K.ENDCAP_IMPULSE;
    if (z.rear) mult *= K.ENDCAP_REAR;
    m.push({ pid:'endcap', mult: Math.min(mult, K.ENDCAP_CAP) });
  }
  if (on('checkout') && z.checkout) {
    const mult = (p.cheap && p.impulse >= K.CHECKOUT_MIN_IMPULSE) ? 1 + p.impulse * K.CHECKOUT_IMPULSE : 1.0;
    m.push({ pid:'checkout', mult });
  }
  if (on('backwall') && z.backwall && p.destination)
    m.push({ pid:'backwall', mult: K.BACKWALL });
  return m;
}

// Effective placement multiplier (product of the above), used to judge "primeness".
export function placementMult(p, z, ctx, off) {
  return placementMults(p, z, ctx, off).reduce((a, b) => a * b.mult, 1);
}

// ── Whole-store score, fully decomposed, with optional leave-one-out ─────────
// off = Set of principle ids to disable (for "what does this rule contribute?").
export function storeScore(place, zones, products, ctx = {}, off = null) {
  const PI = productIndex(products);
  const on = id => !off || !off.has(id);
  // occupancy for facings
  const occ = {}; for (const p of products) occ[place[p.id]] = (occ[place[p.id]] || 0) + 1;

  const perProduct = {};
  let total = 0;
  const byPrinciple = {}; // principle → summed point contribution (leave-one-out is computed elsewhere)

  for (const p of products) {
    const z = zoneById(zones, place[p.id]);
    if (!z) { perProduct[p.id] = { score: 0, mults: [] }; continue; }
    const b = base(p);
    const mults = placementMults(p, z, ctx, off);
    let s = b;
    for (const mm of mults) s *= mm.mult;
    // facings: saturating benefit for having room (fewer co-occupants), elasticity 0.17
    if (on('facings')) {
      const n = occ[z.id] || 1;
      const share = 1 / n, baseShare = 1 / z.cap;
      const fmult = 1 + K.FACINGS_ELASTICITY * Math.max(0, share - baseShare);
      s *= fmult;
      mults.push({ pid:'facings', mult: fmult });
    }
    perProduct[p.id] = { score: s, mults, base: b, zone: z.id };
    total += s;
  }

  // complementary adjacency (asymmetric, co-incidence-discounted, capped)
  if (on('adjacency')) {
    let adj = 0;
    for (const p of products) {
      for (const c of (p.comp || [])) {
        if (place[p.id] && place[p.id] === place[c]) {
          const cp = PI[c]; if (!cp) continue;
          const raw = K.ADJ_COEF * Math.min(base(p), base(cp)) * (1 - K.ADJ_COINCIDENCE);
          adj += Math.min(raw, K.ADJ_CAP * base(p));
        }
      }
    }
    total += adj; byPrinciple.adjacency = adj;
  }

  // low-stock opportunity cost (scales with zone primeness)
  if (on('lowstock')) {
    let pen = 0;
    for (const p of products) {
      if (!p.low) continue;
      const z = zoneById(zones, place[p.id]); if (!z) continue;
      const prime = placementMult(p, z, ctx, off);
      if (prime > 1.05) pen += K.LOWSTOCK_K * base(p) * (prime - 1);
    }
    total -= pen; byPrinciple.lowstock = -pen;
  }

  return { score: total, perProduct, byPrinciple };
}

// ── Capacity-respecting optimizer (hill-climb w/ restarts) · dir +1 max / −1 min
export function optimize(zones, products, ctx = {}, dir = 1, restarts = 60, rng = Math.random) {
  const pids = products.map(p => p.id);
  const cap = Object.fromEntries(zones.map(z => [z.id, z.cap]));
  const obj = pl => dir * storeScore(pl, zones, products, ctx).score;
  const feasible = pl => {
    const c = {}; for (const p of pids) c[pl[p]] = (c[pl[p]] || 0) + 1;
    return zones.every(z => (c[z.id] || 0) <= cap[z.id]);
  };
  const randStart = () => {
    const slots = [];
    zones.forEach(z => { for (let i = 0; i < cap[z.id]; i++) slots.push(z.id); });
    for (let i = slots.length - 1; i > 0; i--) { const j = Math.floor(rng() * (i + 1)); [slots[i], slots[j]] = [slots[j], slots[i]]; }
    const o = {}; pids.forEach((p, i) => o[p] = slots[i]); return o;
  };
  const climb = start => {
    let cur = { ...start }, best = obj(cur), imp = true;
    while (imp) {
      imp = false;
      for (const p of pids) for (const z of zones) {
        if (cur[p] === z.id) continue;
        const cand = { ...cur, [p]: z.id };
        if (feasible(cand)) { const s = obj(cand); if (s > best + 1e-6) { cur = cand; best = s; imp = true; } }
      }
      for (let i = 0; i < pids.length; i++) for (let j = i + 1; j < pids.length; j++) {
        const a = pids[i], b = pids[j]; if (cur[a] === cur[b]) continue;
        const cand = { ...cur, [a]: cur[b], [b]: cur[a] };
        const s = obj(cand); if (s > best + 1e-6) { cur = cand; best = s; imp = true; }
      }
    }
    return { pl: cur, score: best };
  };
  let bs = climb(randStart());
  for (let r = 0; r < restarts; r++) { const s = climb(randStart()); if (s.score > bs.score) bs = s; }
  return { place: bs.pl, score: dir * bs.score };
}

// ── 0–100 Alignment index (a modeling choice, clearly labeled as such) ───────
// 100 = matches the evidence-optimal layout · 0 = worst possible placement.
// seeded RNG so the 0-100 denominator is DETERMINISTIC (same layout → same score
// on every reload; a skeptic who refreshes must see a reproducible number).
function seeded(s){ return function(){ s|=0; s=s+0x6D2B79F5|0; let t=Math.imul(s^s>>>15,1|s); t=t+Math.imul(t^t>>>7,61|t)^t; return((t^t>>>14)>>>0)/4294967296; }; }
export function bounds(zones, products, ctx = {}) {
  const best  = optimize(zones, products, ctx, +1, 60, seeded(0x51ce)).score;
  const worst = optimize(zones, products, ctx, -1, 60, seeded(0x9a17)).score;
  return { best, worst };
}
export function alignment(score, b) {
  if (!b || b.best - b.worst < 1e-6) return 50;
  return Math.max(0, Math.min(100, 100 * (score - b.worst) / (b.best - b.worst)));
}

// ── Coefficient sensitivity (honest uncertainty propagation) ─────────────────
// Every coefficient is a point estimate with real uncertainty. UNCERT is the ±
// relative wiggle on each rule's effect — from the papers' STATED ranges where
// published (rightside 1.05–1.25, entrance 0.85–1.10, facings 0.15–0.21,
// backwall 1.00–1.12), otherwise sized by evidence tier (single-study/heuristic
// wider). We Monte-Carlo the coefficients within these ranges to show a band on
// the score and to label each advised move robust vs sensitive.
export const UNCERT = {
  vertical:0.15, rightside:0.09, entrance:0.14, endcap:0.35, checkout:0.30,
  backwall:0.06, adjacency:0.40, facings:0.18, lowstock:0.40,
};
const K_BASE = JSON.parse(JSON.stringify(K));
function perturbK(rng){
  const r=()=>rng()*2-1;
  const dev=(base,u)=>1+(base-1)*(1+u*r());   // coefficients centred on 1.0
  const dir=(base,u)=>base*(1+u*r());          // additive-slope coefficients
  K.VTIER.eye=dev(K_BASE.VTIER.eye,UNCERT.vertical); K.VTIER.top=dev(K_BASE.VTIER.top,UNCERT.vertical); K.VTIER.low=dev(K_BASE.VTIER.low,UNCERT.vertical);
  K.RIGHT_BONUS=dev(K_BASE.RIGHT_BONUS,UNCERT.rightside);
  K.ENTRANCE=dev(K_BASE.ENTRANCE,UNCERT.entrance);
  K.ENDCAP_IMPULSE=dir(K_BASE.ENDCAP_IMPULSE,UNCERT.endcap);
  K.CHECKOUT_IMPULSE=dir(K_BASE.CHECKOUT_IMPULSE,UNCERT.checkout);
  K.BACKWALL=dev(K_BASE.BACKWALL,UNCERT.backwall);
  K.ADJ_COEF=dir(K_BASE.ADJ_COEF,UNCERT.adjacency);
  K.FACINGS_ELASTICITY=dir(K_BASE.FACINGS_ELASTICITY,UNCERT.facings);
  K.LOWSTOCK_K=dir(K_BASE.LOWSTOCK_K,UNCERT.lowstock);
}
function restoreK(){
  K.VTIER.eye=K_BASE.VTIER.eye; K.VTIER.top=K_BASE.VTIER.top; K.VTIER.waist=K_BASE.VTIER.waist; K.VTIER.low=K_BASE.VTIER.low;
  K.RIGHT_BONUS=K_BASE.RIGHT_BONUS; K.ENTRANCE=K_BASE.ENTRANCE; K.ENDCAP_IMPULSE=K_BASE.ENDCAP_IMPULSE;
  K.CHECKOUT_IMPULSE=K_BASE.CHECKOUT_IMPULSE; K.BACKWALL=K_BASE.BACKWALL; K.ADJ_COEF=K_BASE.ADJ_COEF;
  K.FACINGS_ELASTICITY=K_BASE.FACINGS_ELASTICITY; K.LOWSTOCK_K=K_BASE.LOWSTOCK_K;
}
// alignment band for the current layout under coefficient uncertainty (bounds
// held fixed = the uncertainty applied to your layout on a fixed scale). Seeded
// → reproducible. try/finally guarantees the real coefficients are restored.
export function alignmentBand(place, zones, products, ctx={}, b, N=16){
  const rng=seeded(0x5E01), al=[];
  try{ for(let i=0;i<N;i++){ perturbK(rng); al.push(alignment(storeScore(place,zones,products,ctx).score, b)); } }
  finally{ restoreK(); }
  al.sort((x,y)=>x-y);
  return { lo:al[Math.floor(N*0.1)], hi:al[Math.ceil(N*0.9)-1], spread:(al[al.length-1]-al[0])/2 };
}
// is a candidate move's gain positive across the coefficient ranges?
export function moveRobust(place, pid, toZone, zones, products, ctx={}, N=16){
  const rng=seeded(0x5E01); let pos=0; const moved={...place,[pid]:toZone};
  try{ for(let i=0;i<N;i++){ perturbK(rng);
    if(storeScore(moved,zones,products,ctx).score - storeScore(place,zones,products,ctx).score > 0) pos++; } }
  finally{ restoreK(); }
  return pos>=N-1 ? 'robust' : pos>=N*0.6 ? 'likely' : 'sensitive';
}

// ── Advisor — top feasible improving moves (never contradicts the optimizer) ─
export function advise(place, zones, products, ctx = {}) {
  const PI = productIndex(products);
  const cur = storeScore(place, zones, products, ctx).score;
  const cap = Object.fromEntries(zones.map(z => [z.id, z.cap]));
  const occ = {}; for (const p of products) occ[place[p.id]] = (occ[place[p.id]] || 0) + 1;
  const cands = [];
  for (const p of products) for (const z of zones) {
    if (place[p.id] === z.id || (occ[z.id] || 0) >= cap[z.id]) continue;
    const gain = storeScore({ ...place, [p.id]: z.id }, zones, products, ctx).score - cur;
    if (gain > 2) cands.push({ p, z, gain });
  }
  cands.sort((a, b) => b.gain - a.gain);
  const seen = new Set(), out = [];
  for (const cd of cands) {
    if (seen.has(cd.p.id)) continue; seen.add(cd.p.id);
    out.push({ p: cd.p, z: cd.z, gain: cd.gain, ...explain(cd.p, cd.z, place, PI) });
    if (out.length >= 3) break;
  }
  for (const p of products) {
    const z = zoneById(zones, place[p.id]);
    if (p.low && z && placementMult(p, z, ctx) > 1.05)
      out.push({ warn: true, p, z, reason: 'is low on stock — an empty prime spot is lost money; restock or move it.', principle: 'lowstock' });
  }
  return out;
}
function explain(p, z, place, PI) {
  const compHere = (p.comp || []).find(c => place[c] === z.id);
  if (compHere) return { reason: `pair it with ${PI[compHere].name} — genuine complements lift each other`, principle: 'adjacency' };
  if (z.checkout && p.cheap && p.impulse >= K.CHECKOUT_MIN_IMPULSE) return { reason: 'a cheap impulse treat at the till', principle: 'checkout' };
  if (z.endcap) return { reason: 'feature it on the endcap — lift even with no discount', principle: 'endcap' };
  if (z.vTier === 'eye') return { reason: 'a strong seller at eye/hand height', principle: 'vertical' };
  if (z.entrance) return { reason: 'entrance exposure lifts sales (the one field test contradicts the "dead zone" idea)', principle: 'entrance' };
  if (z.backwall && p.destination) return { reason: 'a destination staple that pulls traffic deep', principle: 'backwall' };
  if (z.lateral === 'right') return { reason: 'the right-hand wall gets more shopper attention', principle: 'rightside' };
  return { reason: 'a better-aligned spot', principle: 'vertical' };
}

// ── Leave-one-out contribution of each principle (for the evidence drawer) ───
export function contributions(place, zones, products, ctx = {}) {
  const full = storeScore(place, zones, products, ctx).score;
  const rows = [];
  for (const id of PRINCIPLE_ORDER) {
    const without = storeScore(place, zones, products, ctx, new Set([id])).score;
    rows.push({ id, points: full - without });
  }
  // foundational inputs = the floor if every rule were switched off
  const floor = storeScore(place, zones, products, ctx, new Set(PRINCIPLE_ORDER)).score;
  return { full, floor, rows };
}

// ── Shopper missions + grounded travel-path INDICATOR ────────────────────────
// This is deliberately OUTSIDE the 0-100 alignment score. It reports only what
// is honestly COMPUTED (path geometry) and frames the behavioural effect as
// DIRECTIONAL, per the evidence — never a calibrated "optimal distance".
//   · Larson/Bradlow/Fader 2005 — real shoppers make short goal-directed
//     excursions, NOT a full-perimeter loop (why the old circle was unrealistic).
//   · Hui/Inman/Huang/Suher 2013 — longer in-store travel causally raises
//     unplanned spend (directional, single-study, context-specific — NOT a
//     per-meter coefficient).
// Missions are 2-3 ILLUSTRATIVE cases, not a prediction of how a shopper walks.
export const MISSIONS = {
  cafe: [
    { id:'coffee', name:'Coffee run',  wants:['coldbrew','cookie'] },
    { id:'full',   name:'Full order',  wants:['oatlatte','croissant','water','brownie'] },
  ],
  convenience: [
    { id:'snack',  name:'Quick snack', wants:['energy','chocolate'] },
    { id:'meal',   name:'Meal run',    wants:['onigiri','cupnoodle','water','soda'] },
  ],
};

// distance from point (px,pz) to segment (ax,az)-(bx,bz)
function distToSeg(px,pz,ax,az,bx,bz){
  const dx=bx-ax, dz=bz-az, l2=dx*dx+dz*dz;
  let t = l2 ? ((px-ax)*dx+(pz-az)*dz)/l2 : 0; t=Math.max(0,Math.min(1,t));
  const cx=ax+t*dx, cz=az+t*dz; return Math.hypot(px-cx,pz-cz);
}
// which zones count as "high-margin / high-visibility" prime space
export function highMarginZones(zones, ctx={}){
  const probe={velocity:1,margin:0,impulse:.5,cheap:true,destination:true};
  return zones.filter(z=>placementMult(probe,z,ctx)>=1.2);
}

// The walkable RING aisle: a rectangle in the open band between the centre
// island (eye/lower) and the perimeter shelves. Computed from the actual fixture
// sizes so it is guaranteed clear (verified by geom_check.mjs).
export function ringRect(zones){
  const fs = zones._fs || fixtureSize(zones._room?.W||12, zones._room?.D||12);
  const zx = id => zoneById(zones,id);
  const islandRight = 0 + fs.sx/2;
  const sideInner   = Math.abs(zx('power').x) - fs.sx/2;
  const RX = Math.max(islandRight+0.4, (islandRight + sideInner)/2);
  const islandFront = zx('eye').z + fs.sz/2;
  const islandBack  = zx('lower').z - fs.sz/2;
  const frontInner  = Math.min(zx('entrance').z, zx('counter').z) - fs.sz/2;
  const backInner   = zx('back').z + fs.sz/2;
  const RZlo = Math.max(islandFront, -islandBack);
  const RZhi = Math.min(frontInner, -backInner);
  const RZ = RZhi>RZlo ? (RZlo+RZhi)/2 : RZlo+0.4;
  return { RX, RZ };
}
// nearest point on the ring rectangle perimeter
function projRing(px,pz,RX,RZ){
  const x=Math.max(-RX,Math.min(RX,px)), z=Math.max(-RZ,Math.min(RZ,pz));
  const dl=x+RX, dr=RX-x, dt=RZ-z, db=z+RZ, m=Math.min(dl,dr,dt,db);
  if(m===dl) return {x:-RX,z}; if(m===dr) return {x:RX,z}; if(m===dt) return {x,z:RZ}; return {x,z:-RZ};
}
// monotone parameter around the ring (0..1), consistent for points & corners
const ringT=(p,RX,RZ)=> (Math.atan2(p.z/RZ, p.x/RX)+Math.PI)/(2*Math.PI);
const fwd=(a,b)=> ((b-a)%1+1)%1;

const permute = a => a.length<=1 ? [a.slice()]
  : a.flatMap((v,i)=> permute(a.slice(0,i).concat(a.slice(i+1))).map(p=>[v,...p]));

// One mission's route: enter, visit the wanted shelves, exit at checkout. Each
// hop follows the SHORTER arc of the clear ring (never crosses a shelf), and the
// visiting order is the shortest total walk (brute force; wants are few). Honest
// geometry only; NO spend prediction, NO "optimal" flag.
export function missionRoute(place, zones, products, mission, ctx={}){
  const { RX, RZ } = ringRect(zones);
  const rp = z => { const p=projRing(z.x,z.z,RX,RZ); return {id:z.id, x:+p.x.toFixed(3), z:+p.z.toFixed(3), t:ringT(p,RX,RZ)}; };
  const entrance=zoneById(zones,'entrance'), checkout=zoneById(zones,'counter');
  const targetIds=[...new Set((mission.wants||[]).map(w=>place[w]).filter(Boolean))];
  const eP=rp(entrance), cP=rp(checkout);
  const dests=targetIds.map(id=>zoneById(zones,id)).filter(Boolean).map(rp);
  const cor=[{x:RX,z:RZ},{x:-RX,z:RZ},{x:-RX,z:-RZ},{x:RX,z:-RZ}].map(c=>({...c,t:ringT(c,RX,RZ)}));
  // corners between a and b along whichever ring direction is shorter
  const hopCorners = (ta,tb) => {
    const f=fwd(ta,tb), b=fwd(tb,ta);
    if(f<=b) return cor.filter(c=>{const x=fwd(ta,c.t); return x>1e-4 && x<f-1e-4;}).sort((p,q)=>fwd(ta,p.t)-fwd(ta,q.t));
    return cor.filter(c=>{const x=fwd(tb,c.t); return x>1e-4 && x<b-1e-4;}).sort((p,q)=>fwd(tb,p.t)-fwd(tb,q.t)).reverse();
  };
  const build = order => {
    const stops=[eP,...order,cP], route=[{id:stops[0].id,x:stops[0].x,z:stops[0].z}];
    for(let i=1;i<stops.length;i++){ const a=stops[i-1], b=stops[i];
      hopCorners(a.t,b.t).forEach(c=>route.push({x:c.x,z:c.z}));
      route.push({id:b.id,x:b.x,z:b.z});
    }
    let d=0; for(let i=1;i<route.length;i++) d+=Math.hypot(route[i].x-route[i-1].x, route[i].z-route[i-1].z);
    return { route, d };
  };
  let best=null;
  for(const o of permute(dests)){ const r=build(o); if(!best||r.d<best.d) best=r; }
  if(!best) best=build([]);
  const HM = highMarginZones(zones, ctx);
  const passed = HM.filter(z => targetIds.includes(z.id) ||
    best.route.slice(1).some((r,i)=> distToSeg(z.x,z.z, best.route[i].x,best.route[i].z, r.x,r.z) <= 2.4));
  return {
    route: best.route, distance:+best.d.toFixed(1),
    passedHighMargin: passed.map(z=>z.id), totalHighMargin: HM.length,
    stops: 2+dests.length,
  };
}

// ── Compact share code for URLs (product → zone index) ───────────────────────
export function encodePlace(place, zones, products) {
  return products.map(p => zones.findIndex(z => z.id === place[p.id])).join('');
}
export function decodePlace(code, zones, products) {
  if (!code || code.length !== products.length) return null;
  const o = {};
  for (let i = 0; i < products.length; i++) {
    const zi = +code[i]; if (Number.isNaN(zi) || !zones[zi]) return null;
    o[products[i].id] = zones[zi].id;
  }
  return o;
}
