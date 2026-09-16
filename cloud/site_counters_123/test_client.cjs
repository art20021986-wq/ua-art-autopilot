const assert = require('node:assert/strict');
const {snapshot,words} = require('./counters.js');
function card(id,stage,childStage=stage) {
  const marker={getAttribute:k=>({'data-ua-card':id,'data-category':childStage}[k]||null)};
  return {getAttribute:k=>k==='data-stage'?stage:null,querySelectorAll:selector=>selector==='a[href]'?[]:[marker]};
}
function doc(cards,grid=true) {
  return {querySelector:s=>s==='.catalog-grid'&&grid?{}:null,
    querySelectorAll:s=>s==='article.catalog-card'?cards:[]};
}
const cards=Array.from({length:18},(_,i)=>card('UA-'+String(i+1).padStart(4,'0'),i<5?'kiev':i===5?'gruzia':i<14?'more':'korea'));
assert.deepEqual(snapshot(doc(cards)),{all:18,kiev:5,georgia:1,sea:8,korea:4});
assert.equal(snapshot(doc([...cards,card('UA-0019','korea')])).all,19);
assert.equal(snapshot(doc(cards)).all,18);
assert.equal(snapshot(doc([...cards,...cards])).all,18);
assert.deepEqual(snapshot(doc([])),{all:0,kiev:0,georgia:0,sea:0,korea:0});
assert.equal(snapshot(doc([card('UA-10000','unknown')])).all,1);
assert.throws(()=>snapshot(doc(cards,false)));
assert.throws(()=>snapshot(doc([card('bad','kiev')])));
assert.throws(()=>snapshot(doc([card('UA-0001','kiev','more')])));
assert.throws(()=>snapshot(doc([...cards,card('UA-0001','more')])));
assert.deepEqual(snapshot(doc([card('UA-0001','more'),...cards.slice(1)])),{all:18,kiev:4,georgia:1,sea:9,korea:4});
for (const [n,ru,uk] of [[1,'1 автомобиль','1 автомобіль'],[2,'2 автомобиля','2 автомобілі'],[5,'5 автомобилей','5 автомобілів'],[11,'11 автомобилей','11 автомобілів'],[21,'21 автомобиль','21 автомобіль']]) {
  assert.equal(words(n,false),ru);assert.equal(words(n,true),uk);
}
console.log('PASS JS: 18/19/18, stage change, duplicate IDs, aliases, unknown/empty/invalid catalogs, RU/UK plural forms; DOM fixtures mocked.');
