// Geometry self-check (no GPU): does the shopper route clip fixtures? do
// fixtures overlap or leave the room? Uses the SAME model the UI renders from.
import { STORES, MISSIONS, buildZones, fixtureFootprint, fixtureSize, missionRoute } from '../app/static/merch/model.js';

const cross=(o,a,b)=>(a.x-o.x)*(b.z-o.z)-(a.z-o.z)*(b.x-o.x);
const ptInBox=(x,z,b,t=0)=> x>=b.minx+t&&x<=b.maxx-t&&z>=b.minz+t&&z<=b.maxz-t;
function segSeg(a,b,c,d){
  const d1=cross(c,d,a),d2=cross(c,d,b),d3=cross(a,b,c),d4=cross(a,b,d);
  return ((d1>0&&d2<0)||(d1<0&&d2>0))&&((d3>0&&d4<0)||(d3<0&&d4>0));
}
function segBox(p0,p1,b,t=0){
  const bb={minx:b.minx+t,maxx:b.maxx-t,minz:b.minz+t,maxz:b.maxz-t};
  if(ptInBox(p0.x,p0.z,bb)||ptInBox(p1.x,p1.z,bb)) return true;
  const c=[{x:bb.minx,z:bb.minz},{x:bb.maxx,z:bb.minz},{x:bb.maxx,z:bb.maxz},{x:bb.minx,z:bb.maxz}];
  for(let i=0;i<4;i++) if(segSeg(p0,p1,c[i],c[(i+1)%4])) return true;
  return false;
}
const boxOverlap=(a,b,t=0)=> a.minx<b.maxx-t&&a.maxx>b.minx+t&&a.minz<b.maxz-t&&a.maxz>b.minz+t;

const rooms=[[10,10],[12,12],[16,14],[20,18],[8,9]];
let clip=0, overlap=0, oob=0, standIn=0, routes=0;
const samples=[];

for(const sk of Object.keys(STORES)){
  const products=STORES[sk].products;
  for(const [W,D] of rooms){
    const zones=buildZones(W,D);
    const fps=zones.map(z=>fixtureFootprint(z,W,D));
    // fixtures out of room
    for(const f of fps){ if(f.minx< -W/2||f.maxx>W/2||f.minz< -D/2||f.maxz>D/2){ oob++; if(samples.length<6)samples.push(`OOB ${sk} ${W}x${D} ${f.id}`);} }
    // fixture-fixture overlap
    for(let i=0;i<fps.length;i++)for(let j=i+1;j<fps.length;j++){ if(boxOverlap(fps[i],fps[j],0.05)){ overlap++; if(samples.length<6)samples.push(`OVERLAP ${sk} ${W}x${D} ${fps[i].id}~${fps[j].id}`);} }
    // routes
    for(const m of (MISSIONS[sk]||[])){
      const rr=missionRoute({...STORES[sk].layout}, zones, products, m, {});
      routes++;
      // stand points inside a fixture?
      for(const p of rr.route){ for(const f of fps){ if(ptInBox(p.x,p.z,f,0.05)){ standIn++; if(samples.length<8)samples.push(`STAND-IN ${sk} ${W}x${D} ${m.id} pt@${f.id}`);} } }
      // route segments crossing fixtures (tolerance 0.15 to ignore edge-graze)
      for(let i=1;i<rr.route.length;i++){ const p0=rr.route[i-1],p1=rr.route[i];
        for(const f of fps){ if(segBox(p0,p1,f,0.15)){ clip++; if(samples.length<8)samples.push(`CLIP ${sk} ${W}x${D} ${m.id} seg${i}(${p0.id||''}->${p1.id||''}) x ${f.id}`);} }
      }
    }
  }
}

const sz=fixtureSize(12,12);
console.log(`\nGeometry self-check  (fixture ${sz.sx.toFixed(2)}w x ${sz.sz.toFixed(2)}d @ 12x12 room)`);
console.log(`  stores x rooms: ${Object.keys(STORES).length}x${rooms.length} · mission routes: ${routes}`);
console.log(`  fixtures out of room:        ${oob}`);
console.log(`  fixture-fixture overlaps:    ${overlap}`);
console.log(`  stand-points inside a shelf: ${standIn}`);
console.log(`  ROUTE SEGMENTS CLIPPING A FIXTURE: ${clip}   <-- the "walks through furniture" bug`);
if(samples.length){ console.log(`\n  samples:`); samples.forEach(s=>console.log(`    · ${s}`)); }
console.log(clip+overlap+oob+standIn===0 ? `\n  ✅ CLEAN — nothing clips, overlaps, or escapes the room.\n` : `\n  ❌ issues found (see above)\n`);

process.exit(clip+overlap+oob+standIn===0?0:1);
