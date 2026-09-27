// Actual production modules in a DOM, with isolated storage and mocked transport.
// Test-only dependency: npm install --prefix /tmp/order-test-tools jsdom@26.1.0
// UA_ORDER_TEST_NODE_MODULES=/tmp/order-test-tools/node_modules node --experimental-vm-modules tests/test_web_language.mjs
import fs from 'node:fs/promises';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import {randomUUID} from 'node:crypto';
import {pathToFileURL} from 'node:url';
const testModules=process.env.UA_ORDER_TEST_NODE_MODULES;
if(!testModules)throw Error('Set UA_ORDER_TEST_NODE_MODULES to the isolated test-only jsdom installation');
const {JSDOM}=await import(pathToFileURL(`${testModules}/jsdom/lib/api.js`));
const read=path=>fs.readFile(new URL(path,import.meta.url),'utf8');
const [html,catalog,preferences,strings]=await Promise.all([read('../web/podbor.html'),read('../../ua_order_ge_8country_guard_016/country_models.json').then(JSON.parse),read('../ua_order/preferences.json').then(JSON.parse),read('../strings.json').then(JSON.parse)]);
preferences.current_year=new Date().getUTCFullYear();
const dom=new JSDOM(html,{url:'https://example.test/video/podbor.html?strana=korea&lang=ru',runScripts:'outside-only',pretendToBeVisual:true});
const {window}=dom,{document}=window;
window.structuredClone=structuredClone;window.crypto.randomUUID=randomUUID;
window.HTMLElement.prototype.scrollIntoView=function(){};
window.UAArtLocale={choose(lang){document.documentElement.lang=lang;}};
window.UAArtLocale.choose('ka');
const sent=[];let failOnce=true;
window.fetch=async(url,options)=>{
 if(String(url).includes('/bootstrap'))return {ok:true,json:async()=>({catalog,preferences,consent_version:'test-v1',consent_text:Object.fromEntries(['uk','ru','ka'].map(lang=>[lang,strings[lang].consent])),csrf:'test'})};
 if(String(url).includes('order-strings.json'))return {ok:true,json:async()=>strings};
 if(String(url).includes('/submit')){sent.push(JSON.parse(options.body));if(failOnce){failOnce=false;throw Error('lost response');}return {ok:true,json:async()=>({status:'saved',request_id:sent[0].request_id,number:'TEST-001'})};}
 throw Error('Unexpected request: '+url);
};
const context=dom.getInternalVMContext(),modules=new Map();
for(const name of ['order-state.js','preferences-state.js','preferences-form.js','order.js']) {
 const source=await read('../web/'+name);
 modules.set('./'+name,new vm.SourceTextModule(source+(name==='order.js'?'\nexport {state,setBusy,selectModel};':''),{context,initializeImportMeta(meta){meta.url='https://example.test/video/order/'+name;}}));
}
const app=modules.get('./order.js');await app.link(specifier=>modules.get(specifier.split('?')[0]));await app.evaluate();
const {state,setBusy,selectModel}=app.namespace;
const $=selector=>{const e=document.querySelector(selector);assert.ok(e,selector);return e;};
const flush=()=>new Promise(resolve=>setImmediate(resolve));
// A selection keeps its native control and focus: no detach/replace/refocus that
// can reopen the iOS picker. Exercise every select used by the real form below.
let focusCalls=0;
const nativeFocus=window.HTMLElement.prototype.focus;
window.HTMLElement.prototype.focus=function(...args){focusCalls++;return nativeFocus.apply(this,args);};
const change=(name,value)=>{
 const control=$(`[name="${name}"]`);control.focus();const before=focusCalls;
 let detached=false;
 const observer=new window.MutationObserver(()=>{});observer.observe(document.body,{childList:true,subtree:true});
 control.value=value;control.dispatchEvent(new window.Event('change',{bubbles:true}));
 for(const record of observer.takeRecords())for(const node of record.removedNodes)if(node===control||node.contains(control))detached=true;
 observer.disconnect();
 assert.equal($(`[name="${name}"]`),control,`${name}: same control`);
 assert.equal(document.activeElement,control,`${name}: keyboard focus retained`);
 assert.equal(focusCalls,before,`${name}: no programmatic refocus`);
 assert.equal(detached,false,`${name}: no detached active control`);
};
const input=(name,value)=>{const control=$(`[name="${name}"]`);control.value=value;control.dispatchEvent(new window.Event('input',{bubbles:true}));};
const check=(name,value)=>{const control=$(`[name="${name}"]`);control.checked=value;control.dispatchEvent(new window.Event('change',{bubbles:true}));};
assert.equal(state.lang,'ka');assert.equal(document.querySelectorAll('#countries a').length,8);assert.equal(document.querySelectorAll('#models article').length,5);
$('#models button').click();assert.equal($('#order-form').hidden,false);assert.equal(state.preferences.values.make,'kia');
assert.equal($('[name="budget"]').value,'');assert.equal($('[name="mileage"]').value,'');assert.equal($('[name="vehicle_type"]').value,'');
input('make-search','Toyota');assert.ok(Array.from($('[name="make"]').options).some(x=>x.value==='toyota'));assert.equal(state.preferences.values.make,'kia');
change('purchase_country_code','other');input('purchase_country_other','Италия');change('purchase_country_code','korea');
change('make','other');input('make_other','Custom');change('make','toyota');
change('model_mode','other');input('other_model','Custom');change('model_mode','selected');
change('models','Camry');assert.equal(state.preferences.values.models[0],'Camry');
assert.equal($('[name="models"]').value,'');assert.ok(!Array.from($('[name="models"]').options).some(o=>o.value==='Camry'));
change('models','Corolla');assert.equal(state.preferences.values.models.length,2);
$('.selected-models li:last-child button').click();assert.equal(state.preferences.values.models.length,1);
assert.ok(Array.from($('[name="models"]').options).some(o=>o.value==='Corolla'));
selectModel('kia-k5');assert.equal(state.preferences.values.make,'toyota');assert.equal(state.preferences.values.models[0],'Camry');
change('budget','custom');input('budget-custom','17 500');
change('vehicle_type','sedan');change('year-from','2016');change('year-to','2021');change('mileage','custom');input('mileage-custom','109.353');
change('delivery_country','georgia');change('delivery_city','tbilisi');input('customer_name','Тестовый клиент');change('contact_method','telegram');input('contact','@test_user');
change('delivery_city','other');input('delivery_city_other','Батуми');change('delivery_city','tbilisi');
check('colours-white',true);check('colours-black',true);check('colours-any',true);assert.equal(state.preferences.values.colours.length,1);assert.equal(state.preferences.values.colours[0],'any');
check('colours-white',true);assert.equal(state.preferences.values.colours.length,1);assert.equal(state.preferences.values.colours[0],'white');
input('comment','Белый кузов. https://example.test/car');check('consent',true);
// Colour names and checkbox state remain accessible independently of the swatch.
assert.equal(document.querySelectorAll('[data-field="colours"] .colour-swatch').length,13);
assert.equal($('[name="colours-white"]').closest('label').querySelector('.colour-swatch').getAttribute('aria-hidden'),'true');
assert.ok($('[name="colours-white"]').closest('label').textContent.includes(preferences.options.colours.white[state.lang]));
// The limit counts Unicode code points and explains overflow without truncation.
input('comment','🚗'.repeat(3000));assert.ok($('#comment-count').textContent.includes('3000'));
$('#order-form').dispatchEvent(new window.Event('submit',{cancelable:true}));assert.ok(state.review);$('#edit').click();
input('comment','🚗'.repeat(3001));$('#optional-preferences').open=false;
$('#order-form').dispatchEvent(new window.Event('submit',{cancelable:true}));
assert.equal(state.review,null);assert.equal($('#optional-preferences').open,true);assert.equal($('#error-comment').hidden,false);
assert.equal($('[name="comment"]').value,'🚗'.repeat(3001));assert.equal(document.activeElement.id,'pref-comment');
input('comment','Белый кузов. https://example.test/car');assert.equal($('#error-comment').hidden,true);
assert.equal($('[name="comment"]').getAttribute('aria-describedby'),'comment-help comment-count');
$('#optional-preferences').open=true;
for(const lang of ['ru','uk','ka']){
 window.UAArtLocale.choose(lang);await flush();
 assert.equal(state.lang,lang);assert.equal($('[data-label="main"]').textContent,preferences.labels[lang].main);
 assert.equal(document.querySelector('[name^="priority-"], [name="year-any"], [data-label="priority_help"]'),null);
 assert.equal($('[name="customer_name"]').value,'Тестовый клиент');assert.equal($('[name="contact"]').value,'@test_user');
 assert.equal($('[name="budget-custom"]').value,'17 500');assert.equal(state.preferences.values.models[0],'Camry');
 assert.equal($('#optional-preferences').open,true);assert.equal(new URL(window.location.href).searchParams.get('lang'),lang);
 // Numeric lists keep the intended order; years have no thousands separator.
 const years=Array.from($('[name="year-from"]').options).filter(o=>/^\d+$/.test(o.value));
 assert.equal(years[0].textContent,String(preferences.current_year));
 assert.equal(years.at(-1).textContent,'1990');
 assert.ok(years.every((o,i)=>o.textContent===String(preferences.current_year-i)));
 const engines=Array.from($('[name="engine-from"]').options).filter(o=>o.value&&o.value!=='custom').map(o=>Number(o.value));
 assert.ok(engines.every((value,i)=>!i||value>engines[i-1]));
 change('year-from','2017');change('year-from','2016');change('purchase_timing','month');
}
// Correct field errors, automatic reveal, preserved input, and range validation.
change('engine-from','custom');input('engine-from-custom','0');$('#optional-preferences').open=false;
$('#order-form').dispatchEvent(new window.Event('submit',{bubbles:true,cancelable:true}));
assert.equal(state.review,null);assert.equal($('#optional-preferences').open,true);assert.equal($('#error-engine').hidden,false);
input('engine-from-custom','1,5');change('engine-to','2');
change('year-from','2024');$('#order-form').dispatchEvent(new window.Event('submit',{cancelable:true}));assert.equal($('#error-year').hidden,false);
change('year-from','2016');
$('#order-form').dispatchEvent(new window.Event('submit',{cancelable:true}));
assert.ok(state.review);assert.equal(state.review.make,'toyota');assert.equal(state.review.models[0],'Camry');assert.equal(state.review.budget.max,17500);assert.equal(state.review.mileage.max,109353);assert.equal(state.review.preferences.criteria.engine.from,1.5);
assert.equal(state.review.preferences.schema_version,1);assert.equal(Object.keys(state.review.preferences.priority).length,0);assert.equal(state.review.year.any,false);assert.equal('engine' in state.review,false);
assert.ok($('#summary').textContent.includes('Camry'));assert.ok($('#summary').textContent.includes('109'));
$('#edit').click();assert.equal($('#order-form').hidden,false);selectModel('hyundai-sonata');
assert.equal(state.preferences.values.make,'hyundai');assert.equal(state.preferences.values.colours[0],'white');assert.equal($('[name="budget-custom"]').value,'17 500');assert.equal($('[name="contact"]').value,'@test_user');
$('#order-form').dispatchEvent(new window.Event('submit',{cancelable:true}));
$('#confirm').click();await flush();assert.ok(state.pending);assert.equal(sent.length,1);const pending=JSON.stringify(state.pending);
window.UAArtLocale.choose('ru');await flush();assert.equal(JSON.stringify(state.pending),pending);
assert.ok(Array.from(document.querySelectorAll('#ua-order button')).every(b=>b.disabled===(b.id!=='confirm')));
$('#confirm').click();await flush();assert.equal(JSON.stringify(sent[0]),JSON.stringify(sent[1]));assert.equal($('#receipt').hidden,false);assert.equal($('#number').textContent,'TEST-001');
assert.equal(state.receipt.status,'saved');assert.equal(state.pending,null);
console.log('PASS: native field construction, 3 languages, search, editable autofill, multi-select, custom numeric inputs, errors/focus, optional reveal, review/edit, unchanged retry after lost response, commit receipt');
dom.window.close();
