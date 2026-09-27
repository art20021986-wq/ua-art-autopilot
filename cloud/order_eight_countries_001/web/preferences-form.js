// Native controls, localized labels and field errors. No requests or submission here.
import {criterionKeys,criterionActive,changeMake} from './preferences-state.js?v=20260927.5';
const el=(tag,text,attrs={})=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;for(const [k,v] of Object.entries(attrs))n.setAttribute(k,v);return n;};
export class PreferenceForm {
  constructor(main,optional,directory,catalog,state,onChange) {
    Object.assign(this,{main,optional,directory,catalog,state,onChange});this.lang='uk';this.ui={};this.groups={};
  }
  t(key){return this.directory.labels[this.lang][key];}
  get v(){return this.state.values;}
  update(key,value){this.v[key]=value;this.state.dirty[key]=true;this.clearError(key);const priority=this.groups[key]?.querySelector('.priority-control');if(priority)priority.hidden=!criterionActive(this.v,key);this.onChange();}
  refresh(...keys){const focused=document.activeElement?.id;for(const key of keys){const next=this.group(key);this.groups[key]?.replaceWith(next);this.groups[key]=next;}if(focused)document.getElementById(focused)?.focus({preventScroll:true});}
  render(lang) {
    clearTimeout(this.countTimer);
    this.lang=lang;this.groups={};
    const main=['purchase_country_code','make','models','budget','vehicle_type','year','mileage','delivery_country','delivery_city','customer_name','contact'];
    const optional=['fuel','drive','engine','colours','purchase_timing','comment'];
    for(const [container,keys] of [[this.main,main],[this.optional,optional]]) container.replaceChildren(...keys.map(key=>(this.groups[key]=this.group(key))));
  }
  input(name,value,onInput,{numeric=false,max=80,autocomplete='off'}={}) {
    const input=el('input',undefined,{id:`pref-${name}`,name,maxlength:max,autocomplete});input.value=value??'';
    if(numeric) input.inputMode='decimal';
    input.addEventListener('input',()=>onInput(input.value));return input;
  }
  label(key,control,text){const label=el('label',text??this.t(key),{for:control.id});const wrap=el('div',undefined,{class:'control'});wrap.append(label,control);return wrap;}
  select(name,choices,value,onChange,{placeholder=true}={}) {
    const select=el('select',undefined,{id:`pref-${name}`,name});
    const entries=Array.isArray(choices)?choices.slice():Object.entries(choices);if(placeholder)entries.unshift(['',this.t('choose')]);
    for(const [code,title] of entries)select.append(el('option',title,{value:code}));
    select.value=value??'';select.addEventListener('change',()=>onChange(select.value));return select;
  }
  searchable(name,choices,value,onChange) {
    const wrap=el('div',undefined,{class:'search-select'}),search=this.input(`${name}-search`,'',()=>{});
    search.type='search';search.setAttribute('aria-label',`${this.t('search')}: ${this.t(name)}`);search.placeholder=this.t('search');
    const select=this.select(name,choices,value,onChange);search.setAttribute('aria-controls',select.id);
    search.addEventListener('input',()=>{
      const term=search.value.toLocaleLowerCase(this.lang).trim(),selected=select.value;
      const filtered=Object.entries(choices).filter(([code,title])=>code===selected||code==='other'||code==='help'||title.toLocaleLowerCase(this.lang).includes(term));
      select.replaceChildren(el('option',this.t('choose'),{value:''}),...filtered.map(([code,title])=>el('option',title,{value:code})));
      select.value=selected;
    });
    wrap.append(search,select);return wrap;
  }
  note(key){return el('p',this.t(key),{class:'field-help'});}
  check(name,title,checked,callback) {
    const label=el('label',undefined,{class:'check-option'}),input=el('input',undefined,{type:'checkbox',name,id:`pref-${name}`});input.checked=checked;
    input.addEventListener('change',()=>callback(input.checked));label.append(input,el('span',title));return label;
  }
  presetNumber(name,value,presets,callback,{extra={},max=16,useGrouping=true}={}) {
    const wrap=el('div',undefined,{class:'number-choice'});
    const choices=[...presets.map(x=>[String(x),Number(x).toLocaleString(this.lang,{useGrouping})]),['custom',this.t('custom')],...Object.entries(extra)];
    const mode=this.ui[name]??(value===null?'':(choices.some(([code])=>code===String(value))?String(value):'custom'));
    const select=this.select(name,choices,mode,code=>{
      this.ui[name]=code;callback(code==='custom'||code===''?null:(code in extra?code:Number(code)));this.refresh(name.split('-')[0]);
    });select.setAttribute('aria-label',`${this.t(name.split('-')[0])}${name.includes('-')?' · '+this.t(name.split('-')[1]):''}`);
    wrap.append(select);
    if(mode==='custom') {
      const custom=this.input(`${name}-custom`,value,text=>callback(text.trim()===''?null:text),{numeric:true,max});
      custom.setAttribute('aria-label',`${this.t('custom')}: ${select.getAttribute('aria-label')}`);wrap.append(custom);
    }
    return wrap;
  }
  group(key) {
    const box=el('fieldset',undefined,{'data-field':key}),legend=el('legend',this.t(key),{id:`legend-${key}`});box.append(legend);
    const v=this.v,options=this.directory.options,local=field=>Object.fromEntries(Object.entries(options[field]).map(([k,val])=>[k,val[this.lang]]));
    const addInput=(name,value,callback,settings)=>box.append(this.label(name,this.input(name,value,callback,settings)));
    if(key==='purchase_country_code') {
      const countries=Object.fromEntries(Object.entries(this.catalog.countries).map(([k,c])=>[k,c.name[this.lang]]));
      box.append(this.select(key,{...countries,other:this.t('other_value'),help:this.t('help')},v[key],value=>{v.purchase_country_other='';this.update(key,value);this.refresh(key);}));
      if(v[key]==='other')addInput('purchase_country_other',v.purchase_country_other,value=>{v.purchase_country_other=value;this.update(key,v[key]);},{max:120});
    } else if(key==='make') {
      box.append(this.searchable(key,{...Object.fromEntries(Object.entries(this.directory.makes).map(([k,m])=>[k,m.name])),other:this.t('other_value'),help:this.t('help')},v.make,value=>{changeMake(this.state,value,this.directory);this.clearError(key);this.refresh('make','models');this.onChange();}));
      if(v.make==='other')addInput('make_other',v.make_other,value=>{v.make_other=value;this.update(key,v.make);},{max:120});
    } else if(key==='models') {
      box.append(this.note('model_help'));
      if(v.make==='help')box.append(el('p',this.t('help')));
      else {
        const modes={...(this.directory.makes[v.make]?{selected:this.t('selected')} :{}),any:this.t('any_model'),other:this.t('other_value')};
        const mode=this.select('model_mode',modes,v.model_mode,value=>{v.model_mode=value;v.models=[];v.other_model='';this.update(key,[]);this.refresh(key);});
        mode.disabled=!v.make;mode.setAttribute('aria-label',this.t('model_mode'));box.append(mode);
        if(v.model_mode==='selected') {
          const selected=el('ul',undefined,{class:'selected-models'});
          for(const model of v.models){const item=el('li'),button=el('button',`${model} ×`,{type:'button','aria-label':`${this.t('remove')}: ${model}`,class:'secondary'});button.addEventListener('click',()=>{this.update(key,v.models.filter(x=>x!==model));this.refresh(key);});item.append(button);selected.append(item);}
          box.append(selected,this.searchable('models',Object.fromEntries((this.directory.makes[v.make]?.models||[]).filter(x=>!v.models.includes(x)).map(x=>[x,x])),'',value=>{if(value){this.update(key,[...v.models,value]);this.refresh(key);}}));
        }
        if(v.model_mode==='other')addInput('other_model',v.other_model,value=>{v.other_model=value;this.update(key,v.models);},{max:120});
      }
    } else if(key==='budget') {
      const value=v.budget.mode==='help'?'help':v.budget.max;
      box.append(this.presetNumber(key,value,this.directory.budgets,x=>this.update(key,{mode:x==='help'?'help':(this.ui[key]?'limit':''),max:x==='help'?null:x,currency:'USD'}),{extra:{help:this.t('consult')}}));
    } else if(key==='vehicle_type'||key==='purchase_timing') {
      box.append(this.select(key,local(key),v[key],value=>this.update(key,value||null)));
    } else if(key==='year'||key==='engine') {
      if(key==='year')box.append(this.check('year-any',this.t('year_any'),v.year.any,checked=>{this.update(key,{from:null,to:null,any:checked});delete this.ui['year-from'];delete this.ui['year-to'];this.refresh(key);}));
      if(!v[key]?.any){const row=el('div',undefined,{class:'range-controls'});for(const bound of ['from','to']) {
        const values=key==='year'?Array.from({length:this.directory.current_year-1989},(_,i)=>this.directory.current_year-i):this.directory.engines;
        const control=this.presetNumber(`${key}-${bound}`,v[key]?.[bound]??null,values,value=>{
          const interval={...(v[key]||{from:null,to:null}),[bound]:value};this.update(key,key==='engine'&&interval.from===null&&interval.to===null?null:interval);
        },{max:key==='year'?4:5,useGrouping:key!=='year'});const wrap=el('div');wrap.append(el('span',this.t(bound)),control);row.append(wrap);
      }box.append(row);}
    } else if(key==='mileage') {
      box.append(this.presetNumber(key,v.mileage.any?'any':v.mileage.max,this.directory.mileages,x=>this.update(key,{max:x==='any'?null:x,any:x==='any'}),{extra:{any:this.t('any')}}),this.note('mileage_help'));
    } else if(key==='delivery_country') {
      box.append(this.select(key,local(key),v[key],value=>{this.update(key,value);this.update('delivery_city',{code:'',other:''});this.refresh('delivery_city');}),this.note('delivery_help'));
    } else if(key==='delivery_city') {
      const cities=Object.fromEntries(Object.entries(this.directory.cities[v.delivery_country]||{}).map(([k,val])=>[k,val[this.lang]]));
      const control=this.searchable(key,{...cities,other:this.t('other_value')},v[key].code,value=>{this.update(key,{code:value,other:''});this.refresh(key);});
      for(const input of control.querySelectorAll('input,select'))input.disabled=!v.delivery_country;
      box.append(control);if(v[key].code==='other')addInput('delivery_city_other',v[key].other,value=>this.update(key,{code:'other',other:value}),{max:120});
    } else if(key==='customer_name') {
      const input=this.input(key,v[key],value=>this.update(key,value),{autocomplete:'name'});input.setAttribute('aria-labelledby',legend.id);box.append(input);
    } else if(key==='contact') {
      box.append(this.label('contact_method',this.select('contact_method',local('contact_method'),v.contact.method,value=>{this.update(key,{...v.contact,method:value});this.refresh(key);})));
      const input=this.input(key,v.contact.value,value=>this.update(key,{...v.contact,value}),{autocomplete:v.contact.method==='telegram'?'off':'tel'});
      if(v.contact.method!=='telegram')input.type='tel';input.setAttribute('aria-labelledby',legend.id);input.setAttribute('aria-describedby','contact-help');
      const note=this.note(v.contact.method==='telegram'?'telegram_help':'phone_help');note.id='contact-help';box.append(input,note);
    } else if(['fuel','drive','colours'].includes(key)) {
      box.append(this.note('multi_help'));const checks=el('div',undefined,{class:'choice-grid'});
      for(const [code,label] of Object.entries(local(key))){const choice=this.check(`${key}-${code}`,label,(v[key]||[]).includes(code),checked=>{
        let values=(v[key]||[]).filter(x=>x!==code&&(!checked||x!=='any'));
        if(checked)values=code==='any'?['any']:[...values,code];
        if(key==='colours'&&!values.includes('other'))v.colour_other='';this.update(key,values.length?values:null);this.refresh(key);
      });
        if(key==='colours'&&options.colours[code].swatch){const swatch=el('span',undefined,{class:'colour-swatch','aria-hidden':'true'});swatch.style.backgroundColor=options.colours[code].swatch;choice.insertBefore(swatch,choice.lastChild);}
        checks.append(choice);
      }box.append(checks);
      if(key==='colours'&&v.colours?.includes('other'))addInput('colour_other',v.colour_other,value=>{v.colour_other=value;this.update(key,v.colours);},{max:120});
    } else if(key==='comment') {
      const input=el('textarea',undefined,{id:'pref-comment',name:'comment',rows:4,'aria-labelledby':legend.id,'aria-describedby':'comment-help comment-count'});input.value=v.comment;
      const help=this.note('comment_help');help.id='comment-help';
      const count=el('p','',{id:'comment-count',class:'field-help'}),announcement=el('span','',{class:'visually-hidden','aria-live':'polite','aria-atomic':'true'});
      const updateCount=announce=>{
        const length=Array.from(input.value).length;
        count.textContent=this.t('character_count').replace('{count}',String(length))+(length>3000?' · '+this.t('comment_limit_error'):'');
        count.classList.toggle('field-error',length>3000);
        clearTimeout(this.countTimer);
        if(announce)this.countTimer=setTimeout(()=>{if(announcement.isConnected)announcement.textContent=count.textContent;},750);
      };
      input.addEventListener('input',()=>{this.update(key,input.value);updateCount(true);});
      updateCount(false);box.append(input,help,count,announcement);
    }
    // A checkbox is an explicit strict requirement; unchecked means preferred.
    if(criterionKeys.includes(key)){const priority=this.check(`priority-${key}`,this.t('required'),v.priority[key]==='required_for_search',checked=>{v.priority[key]=checked?'required_for_search':'preferred';this.onChange();});priority.classList.add('priority-control');priority.hidden=!criterionActive(v,key);box.append(priority);}
    const error=el('p','',{id:`error-${key}`,class:'field-error',role:'alert'});error.hidden=true;box.append(error);
    for(const control of box.querySelectorAll('select'))if(!control.hasAttribute('aria-label'))control.setAttribute('aria-labelledby',legend.id);
    return box;
  }
  clearError(key){const box=this.groups[key];if(!box)return;box.querySelector(`#error-${key}`).hidden=true;for(const control of box.querySelectorAll('[aria-invalid]')){control.removeAttribute('aria-invalid');const ids=(control.getAttribute('aria-describedby')||'').split(' ').filter(id=>id&&id!==`error-${key}`);if(ids.length)control.setAttribute('aria-describedby',ids.join(' '));else control.removeAttribute('aria-describedby');}}
  errors(errors) {
    for(const key of Object.keys(this.groups))this.clearError(key);
    for(const [key,message] of Object.entries(errors)) {
      const box=this.groups[key];if(!box)continue;const error=box.querySelector(`#error-${key}`);error.textContent=this.t(message);error.hidden=false;
      const control=box.querySelector('select,input,textarea');if(control){control.setAttribute('aria-invalid','true');control.setAttribute('aria-describedby',[control.getAttribute('aria-describedby'),error.id].filter(Boolean).join(' '));}
    }
    const first=this.groups[Object.keys(errors)[0]];if(first){const details=first.closest('details');if(details)details.open=true;first.querySelector('select,input,textarea')?.focus();first.scrollIntoView({block:'center',behavior:'smooth'});}
  }
}
