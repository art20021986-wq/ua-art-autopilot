import {languages, fromUrl} from './order-state.js';
import {createPreferences,editableValues,applyCard,preferenceErrors,payload,summaryPairs} from './preferences-state.js?v=20260927.9';
import {PreferenceForm} from './preferences-form.js?v=20260927.9';

const root=document.querySelector('#ua-order');
const assets=new URL('./',import.meta.url);
const $=id=>root.querySelector(`#${id}`);
const form=$('order-form');
const fields=form.elements;
const state={catalog:null,strings:null,lang:'uk',country:'',model:'',review:null,receipt:null,
  requestId:crypto.randomUUID(),busy:false,bootstrap:null,pending:null,preferences:createPreferences()};
let preferenceForm;
const t=key=>state.bootstrap?.preferences?.labels[state.lang][key]??state.strings[state.lang][key];
function node(tag,text,className) {
  const element=document.createElement(tag);
  if(text!==undefined) element.textContent=text;
  if(className) element.className=className;
  return element;
}
function message(key) {$('message').textContent=key?t(key):'';}
function setUrl(push=true) {
  const url=new URL(location.href);
  if(state.country) url.searchParams.set('strana',state.country); else url.searchParams.delete('strana');
  url.searchParams.set('lang',state.lang);
  history[push?'pushState':'replaceState']({},'',url);
}
function setBusy(value) {
  state.busy=value;
  for(const button of root.querySelectorAll('button')) button.disabled=value;
  if(!value && state.pending && !state.receipt) {
    for(const button of root.querySelectorAll('button')) button.disabled=button.id!=='confirm';
  }
  root.setAttribute('aria-busy',String(value));
}
function discardReview() {
  state.review=null;
  $('review').hidden=true;
  // Keep the request ID while a response is uncertain; edits after a successful
  // receipt require the explicit New request action below.
}
function countries() {
  $('countries').replaceChildren(...Object.entries(state.catalog.countries).map(([code,country])=>{
    const a=node('a',undefined,'country');
    a.href=`podbor.html?strana=${code}&lang=${state.lang}`;
    a.setAttribute('aria-current',String(code===state.country));
    a.append(node('span',country.name[state.lang]));
    const flag=node('img');flag.src=new URL(country.flag,assets);flag.alt='';flag.width=54;flag.height=36;a.append(flag);
    a.addEventListener('click',event=>{
      if(event.ctrlKey||event.metaKey||event.shiftKey||event.altKey) return;
      event.preventDefault();
      if(state.busy||state.receipt||state.pending) return;
      if(state.country!==code) {state.model=''; form.hidden=true; discardReview();}
      state.country=code;setUrl();render();
    });
    return a;
  }));
}
function selectModel(key) {
  if(state.busy||state.receipt||state.pending) return;
  state.model=key;discardReview();
  const before=state.preferences.card;
  state.preferences=applyCard(state.preferences,state.country,key,state.bootstrap.preferences.card_presets[key]||{});
  preferenceForm.state=state.preferences;
  if(before!==state.preferences.card) for(const name of Object.keys(preferenceForm.ui)) {
    if(!state.preferences.dirty[name.split('-')[0]]) delete preferenceForm.ui[name];
  }
  preferenceForm.render(state.lang);form.hidden=false;renderSelection();persist();
  $('pref-notice').hidden=!key;
  form.scrollIntoView({behavior:'smooth',block:'start'});
  form.querySelector('select')?.focus({preventScroll:true});
}
function models() {
  $('model-section').hidden=!state.country || Boolean(state.receipt);
  if(!state.country) {$('models').replaceChildren();return;}
  $('models').replaceChildren(...state.catalog.countries[state.country].models.map((model,index)=>{
    const article=node('article',undefined,'model');
    const media=node('div',undefined,'model-media');
    if(model.media.approval==='approved' && model.media.path) {
      const img=node('img');img.src=new URL(model.media.path,assets);img.alt=model.media.alt[state.lang];
      img.width=model.media.width;img.height=model.media.height;img.decoding='async';
      img.loading=index>0?'lazy':'eager';
      img.addEventListener('error',()=>media.replaceChildren(node('span',t('media_pending'))),{once:true});
      media.append(img);
    } else media.append(node('span',t('media_pending')));
    const info=node('div',undefined,'model-info');
    info.append(node('h3',model.labels[state.lang]),node('span',t('under_order'),'tag'));
    const button=node('button',t('calculate'));button.type='button';button.addEventListener('click',()=>selectModel(model.key));
    info.append(button);article.append(media,info);return article;
  }));
}
function renderSelection() {
  if(!state.country) return;
  const country=state.catalog.countries[state.country];
  const model=country.models.find(m=>m.key===state.model);
  $('selection').textContent=`${country.name[state.lang]} · ${model?model.labels[state.lang]:t('other')}`;
}
function renderLegacySummary() {
  if(!state.review) return;
  const data=state.review;
  const country=state.catalog.countries[data.purchase_country_code];
  const model=country.models.find(m=>m.key===data.model);
  const pairs=[['country',country.name[state.lang]],['model',model?model.labels[state.lang]:data.other_model],
    ['budget',state.catalog.budgets[data.budget.code][state.lang]],['vehicle_type',state.catalog.vehicle_types[data.vehicle_type][state.lang]],
    ['delivery_country',data.delivery_country],['delivery_city',data.delivery_city],['customer_name',data.customer_name],
    ['contact',Object.values(data.contact).join(', ')],['comment',data.comment]];
  $('summary').replaceChildren(...pairs.filter(([,value])=>value).flatMap(([key,value])=>[node('dt',t(key)),node('dd',value)]));
}
function renderSummary() {
  if(!state.review) return;
  if(state.review.schema_version==='ua_order_request.v1') return renderLegacySummary();
  const pairs=summaryPairs(state.review,state.catalog,state.bootstrap.preferences,state.lang);
  $('summary').replaceChildren(...pairs.flatMap(([key,value])=>[node('dt',key),node('dd',value)]));
}
function render() {
  if(document.documentElement.lang!==state.lang) {
    if(window.UAArtLocale) window.UAArtLocale.choose(state.lang);
    else document.documentElement.lang=state.lang;
  }
  document.title=`${t('title')} — UA ART COMPANY`;
  for(const el of root.querySelectorAll('[data-label]')) el.textContent=t(el.dataset.label);
  preferenceForm?.render(state.lang);
  $('consent-copy').textContent=state.bootstrap.consent_text[state.lang];
  countries();models();renderSelection();renderSummary();
  setBusy(state.busy);
}
function identityHeaders() {
  const headers={};
  const initData=window.Telegram?.WebApp?.initData;
  if(initData) headers['X-Telegram-Init-Data']=initData;
  return headers;
}
async function api(path,payload) {
  const headers={...identityHeaders(),'Content-Type':'application/json','X-CSRF-Token':state.bootstrap.csrf};
  const response=await fetch(`/api/orders/${path}`,{method:'POST',credentials:'same-origin',headers,body:JSON.stringify(payload)});
  const data=await response.json();
  if(!response.ok) {const error=new Error(data.error||'request_failed');error.status=response.status;error.field=data.field;throw error;}
  return data;
}
// The existing site header owns language selection. Observe only its language
// attribute; this form keeps its own dictionary and never rewrites input values.
new MutationObserver(()=>{
  const lang=document.documentElement.lang;
  if(!state.strings||!languages.includes(lang)||lang===state.lang) return;
  state.lang=lang;
  // An uncertain submission must retain the exact payload for an idempotent retry.
  if(state.review&&!state.pending) state.review.lang=lang;
  setUrl(false);render();
}).observe(document.documentElement,{attributes:true,attributeFilter:['lang']});
$('other-model').addEventListener('click',()=>selectModel(''));
form.addEventListener('submit',event=>{
  event.preventDefault();if(state.busy||state.receipt||state.pending) return;
  const errors=preferenceErrors(state.preferences.values,state.bootstrap.preferences);
  preferenceForm.errors(errors);
  if(Object.keys(errors).length||!form.reportValidity()) return;
  state.review=payload(state.preferences.values,state.catalog,state.bootstrap.preferences,state.lang,state.requestId,state.bootstrap.consent_version,fields.consent.checked);
  $('review').hidden=false;form.hidden=true;renderSummary();message('');$('review').scrollIntoView({behavior:'smooth'});
});
$('edit').addEventListener('click',()=>{if(!state.busy) {form.hidden=false;discardReview();}});
$('confirm').addEventListener('click',async()=>{
  if(state.busy||!state.review||state.receipt) return;
  setBusy(true);message('');
  try {
    state.pending=state.pending||structuredClone(state.review);
    persist();
    const receipt=await api('submit',state.pending);
    if(receipt.status!=='saved'||receipt.request_id!==state.requestId) throw new Error('invalid_receipt');
    state.receipt=receipt;state.pending=null;$('review').hidden=true;form.hidden=true;$('model-section').hidden=true;
    $('number').textContent=receipt.number;
    $('whatsapp').href=`https://wa.me/380992222002?text=${encodeURIComponent(`${t('saved')}: ${receipt.number}`)}`;
    $('receipt').hidden=false;persist();
  } catch(error) {
    if([400,403,413,429].includes(error.status)) state.pending=null;
    message(error.status===400?'invalid':'error');
    if(error.status===400&&error.field){form.hidden=false;discardReview();const key={purchase_country_other:'purchase_country_code',make_other:'make',model_mode:'models',other_model:'models',colour_other:'colours',priority:'make'}[error.field]||error.field;preferenceForm.errors({[key]:'field_error'});}
    persist();
  }
  finally {setBusy(false);}
});
$('handoff').addEventListener('click',async()=>{
  if(state.busy||!state.review) return;
  setBusy(true);
  try {
    const result=await api('handoff',state.review);
    const telegram=window.Telegram?.WebApp;
    if(telegram?.openTelegramLink) telegram.openTelegramLink(result.url);
    else {const link=node('a',t('handoff'));link.href=result.url;link.target='_blank';link.rel='noopener';$('handoff-link').replaceChildren(link);link.click();}
  }
  catch {message('error');}
  finally {setBusy(false);}
});
$('new-request').addEventListener('click',()=>{
  if(state.busy) return;
  state.receipt=null;state.review=null;state.pending=null;state.model='';state.requestId=crypto.randomUUID();
  form.reset();state.preferences=createPreferences();preferenceForm.state=state.preferences;preferenceForm.ui={};form.hidden=true;$('receipt').hidden=true;render();persist();
});
window.addEventListener('popstate',()=>{
  if(!state.catalog||state.busy||state.receipt||state.pending) return;
  const next=fromUrl(location.href,Object.keys(state.catalog.countries));
  if(next.country!==state.country) {state.model='';form.hidden=true;discardReview();}
  state.lang=next.lang;state.country=next.country;
  if(state.review) state.review.lang=state.lang;
  render();
});
function persist() {
  try {
    if(state.receipt) {
      sessionStorage.setItem('ua_order_draft',JSON.stringify({expires:Date.now()+1800000,receipt:state.receipt,requestId:state.requestId}));
    } else {
      sessionStorage.setItem('ua_order_draft',JSON.stringify({expires:Date.now()+1800000,
        config:state.catalog.version,requestId:state.requestId,country:state.country,model:state.model,
        formVersion:2,preferencesVersion:state.bootstrap.preferences.version,preferences:state.preferences,ui:preferenceForm.ui,consent:fields.consent.checked,pending:state.pending}));
    }
  } catch { /* Private-mode storage restrictions must not prevent intake. */ }
}
form.addEventListener('change',persist);
window.addEventListener('pagehide',()=>{if(state.catalog) persist();});
try {
  const pageReady=document.readyState==='loading'
    ?new Promise(resolve=>document.addEventListener('DOMContentLoaded',resolve,{once:true}))
    :Promise.resolve();
  const [bootstrap,strings]=await Promise.all([fetch('/api/orders/bootstrap',{credentials:'same-origin'}),fetch(new URL('order-strings.json',assets)),pageReady]);
  if(!bootstrap.ok||!strings.ok) throw new Error('bootstrap_failed');
  state.bootstrap=await bootstrap.json();state.catalog=state.bootstrap.catalog;state.strings=await strings.json();
  if(!state.bootstrap.preferences) throw new Error('preferences_unavailable');
  preferenceForm=new PreferenceForm($('main-fields'),$('optional-fields'),state.bootstrap.preferences,state.catalog,state.preferences,persist);
  const initial=fromUrl(location.href,Object.keys(state.catalog.countries));Object.assign(state,initial);
  if(window.UAArtLocale&&languages.includes(document.documentElement.lang)) state.lang=document.documentElement.lang;
  render();message('');
  try {
    const saved=JSON.parse(sessionStorage.getItem('ua_order_draft')||'null');
    if(saved && saved.expires>Date.now()) {
      if(saved.receipt) {
        const response=await fetch(`/api/orders/receipt?request_id=${encodeURIComponent(saved.requestId)}`,{credentials:'same-origin',headers:identityHeaders()});
        if(response.ok) {
          const receipt=await response.json();
          if(receipt.status!=='saved'||receipt.request_id!==saved.requestId) throw new Error('invalid_receipt');
          state.requestId=saved.requestId;state.receipt=receipt;$('receipt').hidden=false;$('model-section').hidden=true;
          $('number').textContent=state.receipt.number;
          $('whatsapp').href=`https://wa.me/380992222002?text=${encodeURIComponent(state.receipt.number)}`;
        }
      } else if(saved.config===state.catalog.version && saved.country in state.catalog.countries) {
        // An uncertain submission must retain its identity and payload. Other
        // drafts yield to an explicit incoming country link.
        if(saved.pending || !state.country || state.country===saved.country) {
          state.requestId=saved.requestId;state.country=saved.country;state.model=saved.model;
          if(saved.formVersion===2&&saved.preferencesVersion===state.bootstrap.preferences.version&&saved.preferences?.values) {
            state.preferences=saved.preferences;
            if(!saved.pending) state.preferences.values=editableValues(state.preferences.values);
            preferenceForm.state=state.preferences;preferenceForm.ui=saved.ui||{};
            fields.consent.checked=saved.consent===true;
          }
          state.pending=saved.pending||null;state.review=state.pending;
          render();form.hidden=Boolean(saved.pending)||saved.formVersion!==2;$('review').hidden=!saved.pending;
          $('pref-notice').hidden=!state.model;
          setBusy(false);
        }
      }
    }
  } catch {
    // Recover from corrupted local drafts; an unverified receipt is never shown.
    state.preferences=createPreferences();preferenceForm.state=state.preferences;preferenceForm.ui={};
    state.pending=null;state.review=null;state.receipt=null;state.requestId=crypto.randomUUID();state.model='';
    form.hidden=true;$('review').hidden=true;$('receipt').hidden=true;render();
  }
} catch {form.hidden=true;$('message').textContent='Форма тимчасово недоступна. Телефон: +380 99 222 20 02.';}
