// Native Node harness for the production module; no network or customer messages.
// Run: node --experimental-vm-modules tests/test_web_language.mjs
import fs from 'node:fs/promises';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import {randomUUID} from 'node:crypto';

const read=path=>fs.readFile(new URL(path,import.meta.url),'utf8');
const [source,stateSource,catalog,strings]=await Promise.all([
  read('../web/order.js'),read('../web/order-state.js'),
  read('../../ua_order_ge_8country_guard_016/country_models.json').then(JSON.parse),
  read('../strings.json').then(JSON.parse)
]);
class Element extends EventTarget {
  constructor(id='',tag='div') {super();this.id=id;this.tag=tag;this.children=[];this.value='';this.dataset={};this.hidden=false;}
  append(...nodes) {this.children.push(...nodes);}
  replaceChildren(...nodes) {this.children=nodes;}
  setAttribute(key,value) {this[key]=value;}
  scrollIntoView() {}
  focus() {}
  reportValidity() {return true;}
}
const elements=new Map();
const get=id=>{if(!elements.has(id)) elements.set(id,new Element(id));return elements.get(id);};
const root=get('ua-order'),form=get('order-form');
form.elements=Object.fromEntries(['other_model','budget','vehicle_type','delivery_country','delivery_city',
  'customer_name','contact_value','comment','consent'].map(name=>[name,new Element(name)]));
root.querySelector=selector=>get(selector.slice(1));
const descendants=element=>element.children.flatMap(child=>[child,...descendants(child)]);
const buttons=['other-model','edit','confirm','handoff','new-request'].map(get);
const title=get('title');title.dataset.label='title';
root.querySelectorAll=selector=>selector==='button'
  ?[...buttons,...descendants(get('models')).filter(node=>node.tag==='button')]:[title];
const document=new EventTarget(),window=new EventTarget();
document.readyState='loading';
document.querySelector=()=>root;
document.createElement=tag=>new Element('',tag);
let observer,lang='ru',languageNotifications=0;
document.documentElement={get lang(){return lang;},set lang(value){lang=value;queueMicrotask(()=>{languageNotifications++;observer?.();});}};
let headerLanguage='ru';
window.UAArtLocale={choose(value){headerLanguage=value;document.documentElement.lang=value;}};
let currentUrl='https://example.test/video/podbor.html?strana=korea';
const history={pushState(_state,_title,url){currentUrl=String(url);},replaceState(_state,_title,url){currentUrl=String(url);}};
const location={get href(){return currentUrl;}};
const stored=new Map();
const context=vm.createContext({document,window,history,location,URL,crypto:{randomUUID},structuredClone,
  MutationObserver:class {constructor(callback){observer=callback;}observe(){}},
  FormData:class extends Map {constructor(){super(Object.entries(form.elements).map(([name,field])=>[name,field.value]));}},
  sessionStorage:{getItem:key=>stored.get(key),setItem:(key,value)=>stored.set(key,value)},
  fetch:async url=>({ok:true,json:async()=>String(url).includes('bootstrap')
    ?{catalog,consent_text:{uk:'UK consent',ru:'RU consent',ka:'KA consent'}}:strings})});
const stateModule=new vm.SourceTextModule(stateSource,{context});
const app=new vm.SourceTextModule(source+'\nexport {state,setBusy};',{context,
  initializeImportMeta(meta){meta.url='https://example.test/video/order/order.js';}});
await app.link(()=>stateModule);
const evaluating=app.evaluate();
// Simulate the shared header applying a saved language after the fetch begins.
window.UAArtLocale.choose('ka');
document.readyState='interactive';
document.dispatchEvent(new Event('DOMContentLoaded'));
await evaluating;
const {state,setBusy}=app.namespace;
assert.equal(state.lang,'ka');
assert.equal(get('countries').children.length,8);
assert.equal(get('models').children.length,5);
const firstModel=get('models').children[0];
assert.deepEqual(firstModel.children[1].children.map(el=>el.tag),['h3','span','button']);
firstModel.children[1].children.at(-1).dispatchEvent(new Event('click'));
const selectedModel=state.model;
form.elements.customer_name.value='Test customer';
form.elements.delivery_city.value='Kyiv';
form.elements.budget.value='b2';
const flush=()=>new Promise(resolve=>setImmediate(resolve));
for(const language of ['ru','uk','ka']) {
  window.UAArtLocale.choose(language);await flush();
  assert.equal(state.lang,language);
  assert.equal(title.textContent,strings[language].title);
  assert.equal(get('models').children[0].children[1].children[0].textContent,catalog.countries.korea.models[0].labels[language]);
  assert.equal(get('countries').children[0].children[0].textContent,catalog.countries.korea.name[language]);
  assert.equal(new URL(currentUrl).searchParams.get('lang'),language);
  assert.equal(state.country,'korea');assert.equal(state.model,selectedModel);
  assert.equal(form.hidden,false);
  assert.equal(form.elements.customer_name.value,'Test customer');
  assert.equal(form.elements.delivery_city.value,'Kyiv');
  assert.equal(form.elements.budget.value,'b2');
}
currentUrl='https://example.test/video/podbor.html?strana=korea&lang=uk';
window.dispatchEvent(new Event('popstate'));await flush();
assert.equal(headerLanguage,'uk');assert.equal(state.lang,'uk');
setBusy(true);window.UAArtLocale.choose('ru');await flush();
assert.ok(root.querySelectorAll('button').every(button=>button.disabled));
setBusy(false);
form.dispatchEvent(new Event('submit',{cancelable:true}));
assert.equal(state.review.lang,'ru');
window.UAArtLocale.choose('uk');await flush();
assert.equal(state.review.lang,'uk');
currentUrl='https://example.test/video/podbor.html?strana=korea&lang=ru';
window.dispatchEvent(new Event('popstate'));await flush();
assert.equal(headerLanguage,'ru');assert.equal(state.review.lang,'ru');
state.pending=state.review;
const pendingBefore=JSON.stringify(state.pending);
window.UAArtLocale.choose('ka');await flush();
assert.equal(JSON.stringify(state.pending),pendingBefore);
assert.ok(root.querySelectorAll('button').every(button=>button.disabled===(button.id!=='confirm')));
assert.ok(languageNotifications<20,'Language synchronization must not loop');
console.log('PASS: saved language, all three header languages, preserved fields/model, browser history, busy controls and immutable retry payload');
