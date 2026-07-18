// Mechanical verification of the SHIPPING merch model (imports the real code).
// Runs many store × room × toggle × layout configs and asserts invariants.
import {
  STORES, buildZones, storeScore, optimize, bounds, alignment, advise,
  contributions, encodePlace, decodePlace, K, PRINCIPLE_ORDER,
  MISSIONS, missionRoute, zoneById,
} from '../app/static/merch/model.js';

// tiny seeded RNG so runs are reproducible
function mulberry32(a){return function(){a|=0;a=a+0x6D2B79F5|0;let t=Math.imul(a^a>>>15,1|a);t=t+Math.imul(t^t>>>7,61|t)^t;return((t^t>>>14)>>>0)/4294967296;};}

const stores = Object.keys(STORES);
const rooms = [[8,8],[10,12],[12,10],[16,14],[20,18],[6,9],[22,22],[7,15],[14,7],[11,11]];
const ctxs = [
  {decompression:false, circulation:'right'},
  {decompression:true,  circulation:'right'},
  {decompression:false, circulation:'clockwise'},
  {decompression:true,  circulation:'clockwise'},
];
const TRIALS_PER = 15; // random feasible layouts per config

let trials=0; const fails=[];
const check=(cond,label,info)=>{ if(!cond) fails.push(`${label} ${info||''}`); };

// static coefficient sanity (the honesty fixes)
check(K.ENTRANCE > K.ENTRANCE_DECOMP, 'I-static entrance-raised', `(${K.ENTRANCE} > ${K.ENTRANCE_DECOMP})`);
check(K.VTIER.eye>=K.VTIER.low && K.VTIER.top>=K.VTIER.waist, 'I-static vtier-ordered');
check(K.RIGHT_BONUS>1 && K.RIGHT_BONUS<1.3, 'I-static rightside-modest');

for(const sk of stores){
  const products = STORES[sk].products;
  for(const [w,d] of rooms){
    const zones = buildZones(w,d);
    const cap = Object.fromEntries(zones.map(z=>[z.id,z.cap]));
    for(const ctx of ctxs){
      const rng = mulberry32(1000+trials);
      const b = bounds(zones, products, ctx);
      const best = optimize(zones, products, ctx, +1, 40, rng);
      const worst = optimize(zones, products, ctx, -1, 40, rng);

      // I10 best >= worst
      check(b.best >= b.worst - 1e-6, 'I10 best>=worst', `${sk} ${w}x${d}`);
      // I3 alignment endpoints
      check(Math.abs(alignment(b.best,b)-100)<1e-6, 'I3 best=100', `${sk} got ${alignment(b.best,b).toFixed(2)}`);
      check(Math.abs(alignment(b.worst,b)-0)<1e-6, 'I3 worst=0', `${sk}`);
      // I1 optimizer feasible (capacity)
      for(const pl of [best.place, worst.place]){
        const c={}; for(const p of products) c[pl[p.id]]=(c[pl[p.id]]||0)+1;
        check(zones.every(z=>(c[z.id]||0)<=cap[z.id]), 'I1 capacity', `${sk} ${w}x${d}`);
      }
      // I6 advisor consistency: at the optimum, no single improving move remains
      const advBest = advise(best.place, zones, products, ctx).filter(a=>!a.warn);
      check(advBest.length===0, 'I6 advisor-consistent', `${sk} ${w}x${d} left ${advBest.length} moves`);

      // random feasible layouts
      for(let t=0;t<TRIALS_PER;t++){
        const slots=[]; zones.forEach(z=>{for(let i=0;i<z.cap;i++)slots.push(z.id);});
        for(let i=slots.length-1;i>0;i--){const j=Math.floor(rng()*(i+1));[slots[i],slots[j]]=[slots[j],slots[i]];}
        const pl={}; products.forEach((p,i)=>pl[p.id]=slots[i]);
        const s = storeScore(pl, zones, products, ctx).score;
        const al = alignment(s,b);
        // I2 optimizer dominates a random start
        check(b.best >= s-1e-6, 'I2 optimizer>=random', `${sk} best=${b.best.toFixed(1)} rand=${s.toFixed(1)}`);
        // I4 finiteness
        check(Number.isFinite(s)&&Number.isFinite(al), 'I4 finite', `${sk}`);
        // I3b alignment within [0,100]
        check(al>=-1e-6 && al<=100+1e-6, 'I3b in-range', `${sk} ${al}`);
        // I5 url roundtrip
        const code=encodePlace(pl,zones,products); const back=decodePlace(code,zones,products);
        check(back && products.every(p=>back[p.id]===pl[p.id]), 'I5 url-roundtrip', `${sk} ${code}`);
        // I7 leave-one-out contributions finite
        const con=contributions(pl,zones,products,ctx);
        check(Number.isFinite(con.full)&&con.rows.every(r=>Number.isFinite(r.points)), 'I7 contrib-finite', `${sk}`);
        trials++;
      }

      // I11-14 shopper mission routes (grounded path indicator)
      for(const mission of (MISSIONS[sk]||[])){
        // use the store's furnished layout so the wanted products resolve to zones
        const furnished = {...STORES[sk].layout};
        const r2 = missionRoute(furnished, zones, products, mission, ctx);
        check(r2.route[0]?.id==='entrance', 'I11 route-starts-entrance', `${sk} ${mission.id}`);
        check(r2.route[r2.route.length-1]?.id==='counter', 'I11 route-ends-checkout', `${sk} ${mission.id}`);
        check(Number.isFinite(r2.distance)&&r2.distance>=0, 'I12 route-distance-finite', `${sk} ${mission.id}=${r2.distance}`);
        check(r2.passedHighMargin.every(id=>zones.some(z=>z.id===id)), 'I13 passed-valid-zones', `${sk}`);
        check(r2.passedHighMargin.length<=r2.totalHighMargin, 'I13 passed<=total', `${sk} ${r2.passedHighMargin.length}/${r2.totalHighMargin}`);
        check(mission.wants.every(w=>products.some(p=>p.id===w)), 'I14 mission-wants-valid', `${sk} ${mission.id}`);
        trials++;
      }

      // I8 decompression toggle only ever lowers the entrance-product score
      const plE = {}; products.forEach((p,i)=>plE[p.id]= i===0?'entrance':'lower');
      const off = storeScore(plE, zones, products, {...ctx, decompression:false}).score;
      const on  = storeScore(plE, zones, products, {...ctx, decompression:true }).score;
      check(on <= off+1e-6, 'I8 decomp-penalizes', `${sk} on=${on.toFixed(1)} off=${off.toFixed(1)}`);
    }
  }
}

console.log(`\nMerch model verification`);
console.log(`  configs (store×room×ctx): ${stores.length*rooms.length*ctxs.length}`);
console.log(`  random-layout trials:     ${trials}`);
console.log(`  invariants checked:       I1 capacity · I2 optimizer≥random · I3 alignment-endpoints/range · I4 finite · I5 url-roundtrip · I6 advisor-consistent · I7 contrib-finite · I8 decompression · I10 best≥worst · I11 route entrance→checkout · I12 distance-finite · I13 passed-zones-valid · I14 mission-wants-valid + static`);
if(fails.length){
  console.log(`\n  ❌ ${fails.length} FAILURES:`);
  const seen={}; for(const f of fails){const k=f.split(' ')[0]; seen[k]=(seen[k]||0)+1;}
  for(const k in seen) console.log(`     ${k}: ${seen[k]}`);
  fails.slice(0,8).forEach(f=>console.log(`     · ${f}`));
  process.exit(1);
} else {
  console.log(`\n  ✅ ALL PASS — ${trials} trials, 0 violations across ${stores.length} stores, ${rooms.length} room sizes, ${ctxs.length} contexts.\n`);
}
