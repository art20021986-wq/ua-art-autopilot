import {fromUrl, requestPayload} from './order-state.js';

const root=document.querySelector('#ua-order');
const assets=new URL('./',import.meta.url);
const $=id=>root.querySelector(`#${id}`);
const form=$('order-form');
const fields=form.elements;
const state={catalog:null,strings:null,lang:'uk',country:'',model:'',review:null,receipt:null,
  requestId:crypto.randomUUID(),busy:false,bootstrap:null,pending:null};
const t=key=>state.strings[state.lang][key];
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
function options(select,choices) {
  const previous=select.value;
  select.replaceChildren(...Object.entries(choices).map(([code,labels])=>{
    const option=node('option',labels[state.lang]);option.value=code;return option;
  }));
  if(previous in choices) select.value=previous;
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
  if(key) fields.other_model.value='';
  $('other-wrap').hidden=Boolean(key);fields.other_model.required=!key;
  form.hidden=false;renderSelection();
  form.scrollIntoView({behavior:'smooth',block:'start'});
  (key?fields.budget:fields.other_model).focus({preventScroll:true});
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
    if(model.media.source) {
      const credit=node('a',`${model.media.artist} · ${model.media.license}`,'photo-credit');
      credit.href=model.media.source;credit.target='_blank';credit.rel='noopener';info.append(credit);
    }
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
function renderSummary() {
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
function render() {
  document.documentElement.lang=state.lang;
  document.title=`${t('title')} — UA ART COMPANY`;
  for(const el of root.querySelectorAll('[data-label]')) el.textContent=t(el.dataset.label);
  for(const el of $('languages').querySelectorAll('button')) el.setAttribute('aria-pressed',String(el.dataset.lang===state.lang));
  options(fields.budget,state.catalog.budgets);options(fields.vehicle_type,state.catalog.vehicle_types);
  $('consent-copy').textContent=state.bootstrap.consent_text[state.lang];
  countries();models();renderSelection();renderSummary();
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
  if(!response.ok) {const error=new Error(data.error||'request_failed');error.status=response.status;throw error;}
  return data;
}
for(const button of $('languages').querySelectorAll('button')) button.addEventListener('click',()=>{
  if(state.busy||state.pending) return;
  state.lang=button.dataset.lang;
  if(state.review) state.review.lang=state.lang;
  setUrl();render();
});
$('other-model').addEventListener('click',()=>selectModel(''));
form.addEventListener('submit',event=>{
  event.preventDefault();if(state.busy||state.receipt||!form.reportValidity()) return;
  const data=Object.fromEntries(new FormData(form));
  state.review=requestPayload(data,state.catalog,{country:state.country,model:state.model},state.lang,state.requestId,state.bootstrap.consent_version);
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
    message(error.status===400?'invalid':'error');persist();
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
    else location.assign(result.url);
  }
  catch {message('error');}
  finally {setBusy(false);}
});
$('new-request').addEventListener('click',()=>{
  if(state.busy) return;
  state.receipt=null;state.review=null;state.pending=null;state.model='';state.requestId=crypto.randomUUID();
  form.reset();form.hidden=true;$('receipt').hidden=true;render();persist();
});
window.addEventListener('popstate',()=>{
  if(!state.catalog||state.busy||state.receipt||state.pending) return;
  const next=fromUrl(location.href,Object.keys(state.catalog.countries));
  if(next.country!==state.country) {state.model='';form.hidden=true;discardReview();}
  state.lang=next.lang;state.country=next.country;render();
});
function persist() {
  try {
    if(state.receipt) {
      sessionStorage.setItem('ua_order_draft',JSON.stringify({expires:Date.now()+1800000,receipt:state.receipt,requestId:state.requestId}));
    } else {
      sessionStorage.setItem('ua_order_draft',JSON.stringify({expires:Date.now()+1800000,
        config:state.catalog.version,requestId:state.requestId,country:state.country,model:state.model,
        form:Object.fromEntries(new FormData(form)),pending:state.pending}));
    }
  } catch { /* Private-mode storage restrictions must not prevent intake. */ }
}
form.addEventListener('input',persist);
window.addEventListener('pagehide',()=>{if(state.catalog) persist();});
try {
  const [bootstrap,strings]=await Promise.all([fetch('/api/orders/bootstrap',{credentials:'same-origin'}),fetch(new URL('order-strings.json',assets))]);
  if(!bootstrap.ok||!strings.ok) throw new Error('bootstrap_failed');
  state.bootstrap=await bootstrap.json();state.catalog=state.bootstrap.catalog;state.strings=await strings.json();
  const initial=fromUrl(location.href,Object.keys(state.catalog.countries));Object.assign(state,initial);
  render();fields.budget.value='undecided';fields.vehicle_type.value='any';message('');
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
          for(const [key,value] of Object.entries(saved.form||{})) {
            if(!fields[key]) continue;
            if(key==='consent') fields[key].checked=value==='on'; else fields[key].value=value;
          }
          state.pending=saved.pending;state.review=saved.pending;
          render();form.hidden=Boolean(saved.pending);$('review').hidden=!saved.pending;
          $('other-wrap').hidden=Boolean(state.model);fields.other_model.required=!state.model;
          setBusy(false);
        }
      }
    }
  } catch { /* Malformed or expired local state is not trusted as a receipt. */ }
} catch {$('message').textContent='Форма тимчасово недоступна. Телефон: +380 99 222 20 02.';}
