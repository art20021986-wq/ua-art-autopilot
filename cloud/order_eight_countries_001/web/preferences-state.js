// Pure preference state. Card metadata never becomes submitted customer data.
export const schema='ua_order_request.v2';
export function emptyValues() {
  return {purchase_country_code:'',purchase_country_other:'',make:'',make_other:'',model_mode:'',models:[],other_model:'',
    budget:{mode:'',max:null,currency:'USD'},vehicle_type:'',delivery_country:'',delivery_city:{code:'',other:''},
    customer_name:'',contact:{method:'',value:''},year:{from:null,to:null,any:false},mileage:{max:null,any:false},
    fuel:null,drive:null,engine:null,colours:null,colour_other:'',purchase_timing:null,comment:'',priority:{}};
}
// Retire removed controls in editable drafts without changing uncertain requests.
export function editableValues(values) {
  const result=structuredClone(values);
  result.priority={};result.year.any=false;
  return result;
}
export function createPreferences() {return {values:emptyValues(),dirty:{},card:null};}
export function applyCard(previous,country,key,preset={}) {
  const id=`${country}/${key}`;
  if(previous.card===id) return structuredClone(previous);
  const next=structuredClone(previous),empty=emptyValues();
  Object.assign(next.values,{purchase_country_code:country,purchase_country_other:'',make:preset.make||'',make_other:'',
    models:preset.models||[],model_mode:preset.model_mode||'',other_model:''});
  for(const field of ['budget','vehicle_type','year','mileage','fuel','drive','engine','colours']) {
    if(!next.dirty[field]) next.values[field]=structuredClone(preset[field]??empty[field]);
  }
  if(!next.dirty.colours) next.values.colour_other=preset.colour_other||'';
  for(const field of ['purchase_country_code','make','models']) delete next.dirty[field];
  next.card=id;return next;
}
export function changeMake(state,make,directory) {
  if(state.values.make===make) return;
  state.values.make=make;state.values.make_other='';state.dirty.make=true;
  const allowed=directory.makes[make]?.models||[];
  state.values.models=state.values.models.filter(model=>allowed.includes(model));
  state.values.other_model='';
  state.values.model_mode=make==='help'?'help':(directory.makes[make]?'selected':'');
  state.dirty.models=true;
}
export function parseInteger(value,min=0,max=5000000) {
  if(typeof value==='number') return Number.isSafeInteger(value)&&value>=min&&value<=max?value:null;
  if(typeof value!=='string'||! /^(?:[0-9]+|[0-9]{1,3}([ .,\u00a0\u202f])[0-9]{3}(?:\1[0-9]{3})*)$/.test(value.trim())) return null;
  return parseInteger(Number(value.trim().replace(/[ .,\u00a0\u202f]/g,'')),min,max);
}
export function parseLitres(value) {
  if(!/^[0-9]{1,2}(?:[.,][0-9]{1,2})?$/.test(String(value).trim())) return null;
  const result=Number(String(value).trim().replace(',','.'));return result>0&&result<=20?result:null;
}
export function preferenceErrors(v,directory) {
  const errors={};const fail=(field,key='required_error')=>{errors[field]=key;};
  if(!v.purchase_country_code||(v.purchase_country_code==='other'&&v.purchase_country_other.trim().length<2)) fail('purchase_country_code');
  if(!v.make||(v.make==='other'&&v.make_other.trim().length<2)) fail('make');
  if(!v.model_mode||(v.model_mode==='selected'&&!v.models.length)||(v.model_mode==='other'&&v.other_model.trim().length<2)) fail('models');
  if(v.budget.mode!=='help'&&parseInteger(v.budget.max,1,1000000000)===null) fail('budget','field_error');
  if(!v.vehicle_type) fail('vehicle_type');
  if(!v.delivery_country) fail('delivery_country');
  if(!v.delivery_city.code||(v.delivery_city.code==='other'&&v.delivery_city.other.trim().length<2)) fail('delivery_city');
  if(v.customer_name.trim().length<2) fail('customer_name');
  const contact=v.contact.value.trim(), phone=contact.replace(/[ ()-]/g,'');
  if(!v.contact.method||!(v.contact.method==='telegram'&&/^@[a-zA-Z][a-zA-Z0-9_]{4,31}$/.test(contact))&&!(/^\+[0-9 ()-]+$/.test(contact)&&/^\+[1-9][0-9]{6,14}$/.test(phone))) fail('contact','contact_error');
  for(const field of ['year','engine']) {
    const interval=v[field];if(!interval) continue;
    const convert=field==='year'?x=>parseInteger(x,1900,directory.current_year):parseLitres;
    const bounds=['from','to'].map(key=>interval[key]===null?null:convert(interval[key]));
    if(bounds.every(x=>x===null)||['from','to'].some((key,i)=>interval[key]!==null&&bounds[i]===null)) fail(field,'field_error');
    else if(bounds.every(x=>x!==null)&&bounds[0]>bounds[1]) fail(field,'range_error');
  }
  if(!v.mileage.any&&parseInteger(v.mileage.max)===null) fail('mileage','field_error');
  for(const [field,value] of [['purchase_country_code',v.purchase_country_other],['make',v.make_other],['models',v.other_model],['delivery_city',v.delivery_city.other],['colours',v.colour_other]]) {
    if(Array.from(value).length>120) fail(field,'text_limit_error');
  }
  if(Array.from(v.comment).length>3000) fail('comment','comment_limit_error');
  return errors;
}
export function payload(values,catalog,directory,lang,requestId,consentVersion,accepted,sourcePath='/video/podbor.html') {
  const result=editableValues(values);
  if(result.budget.mode==='limit') result.budget.max=parseInteger(result.budget.max,1,1000000000);
  if(!result.mileage.any) result.mileage.max=parseInteger(result.mileage.max);
  for(const bound of ['from','to']) if(result.year[bound]!==null) result.year[bound]=parseInteger(result.year[bound],1900,directory.current_year);
  if(result.engine) for(const bound of ['from','to']) if(result.engine[bound]!==null) result.engine[bound]=parseLitres(result.engine[bound]);
  const criteria=Object.fromEntries(directory.preference_fields.map(key=>[key,result[key]]));
  const preferences={schema_version:1,criteria,priority:result.priority};
  for(const key of [...directory.preference_fields,'priority']) delete result[key];
  return {...result,preferences,schema_version:schema,request_id:requestId,config_version:catalog.version,preferences_version:directory.version,
    lang,source_path:sourcePath,consent:{accepted,version:consentVersion}};
}
export function summaryPairs(data,catalog,directory,lang) {
  const v={...data,...data.preferences.criteria,priority:data.preferences.priority};
  const t=key=>directory.labels[lang][key],option=(field,key)=>directory.options[field]?.[key]?.[lang]||key;
  const num=value=>Number(value).toLocaleString(lang==='ka'?'ka-GE':lang==='uk'?'uk-UA':'ru-RU');
  const range=value=>['from','to'].filter(k=>value[k]!==null).map(k=>`${t(k)} ${value[k]}`).join(' ');
  const pairs=[['purchase_country_code',catalog.countries[v.purchase_country_code]?.name[lang]||(v.purchase_country_code==='help'?t('help'):v.purchase_country_other)],
    ['make',directory.makes[v.make]?.name||(v.make==='help'?t('help'):v.make_other)],
    ['models',v.model_mode==='selected'?v.models.join(', '):v.model_mode==='other'?v.other_model:t(v.model_mode==='any'?'any_model':'help')],
    ['budget',v.budget.mode==='help'?t('consult'):`${t('to')} ${num(v.budget.max)} USD`],['vehicle_type',option('vehicle_type',v.vehicle_type)],
    ['year',v.year.any?t('any'):range(v.year)],['mileage',v.mileage.any?t('any'):`${t('to')} ${num(v.mileage.max)} ${t('km_unit')}`],
    ['delivery_country',option('delivery_country',v.delivery_country)],['delivery_city',v.delivery_city.code==='other'?v.delivery_city.other:directory.cities[v.delivery_country]?.[v.delivery_city.code]?.[lang]],
    ['customer_name',v.customer_name],['contact',`${option('contact_method',v.contact.method)}: ${v.contact.value}`]];
  for(const field of ['fuel','drive']) if(v[field]?.length) pairs.push([field,v[field].map(x=>option(field,x)).join(', ')]);
  if(v.engine) pairs.push(['engine',range(v.engine)]);
  if(v.colours?.length) pairs.push(['colours',v.colours.map(x=>x==='other'?`${option('colours',x)}: ${v.colour_other||t('clarify')}`:option('colours',x)).join(', ')]);
  if(v.purchase_timing) pairs.push(['purchase_timing',option('purchase_timing',v.purchase_timing)]);
  if(v.comment) pairs.push(['comment',v.comment]);
  return pairs.map(([key,value])=>[t(key),`${value}${v.priority[key]==='required_for_search'?` (${t('required')})`:''}`]);
}
