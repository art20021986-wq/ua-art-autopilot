import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
const source=await fs.readFile(new URL('../web/order-state.js',import.meta.url),'utf8');
const {fromUrl,changeCountry,requestPayload}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
const codes=['korea','japan','usa','europe','china','canada','uae','georgia'];
for(const country of codes) for(const lang of ['uk','ru','ka']) {
  assert.deepEqual(fromUrl(`https://example.test/podbor.html?strana=${country}&lang=${lang}`,codes),{country,lang});
}
assert.deepEqual(fromUrl('https://example.test/podbor.html?strana=nope&lang=ge',codes),{country:'',lang:'uk'});
assert.equal(fromUrl('https://example.test/podbor.html',codes).country,'');
const before={purchase_country_code:'korea',model:'kia-k5',budget:'b2',delivery_city:'Kyiv',comment:'Keep this'};
const changed=changeCountry(before,'georgia');
assert.equal(changed.model,'');assert.equal(changed.delivery_city,'Kyiv');assert.equal(changed.budget,'b2');
assert.equal(before.model,'kia-k5');
const payload=requestPayload({other_model:'',budget:'b2',vehicle_type:'k1',delivery_country:' Ukraine ',delivery_city:' Kyiv ',customer_name:' Test ',contact_value:'@test_user',comment:'hello',consent:'on'},
  {version:'v1'},{country:'korea',model:'kia-k5'},'uk','request-id','test-consent');
assert.deepEqual(payload.contact,{telegram:'@test_user'});
assert.equal(payload.model,'kia-k5');assert.equal(payload.comment,'hello');assert.equal(payload.consent.accepted,true);
assert.equal(payload.delivery_city,'Kyiv');
console.log('24 country/language routes + unknown-route, preserved-fields and payload scenarios passed');
