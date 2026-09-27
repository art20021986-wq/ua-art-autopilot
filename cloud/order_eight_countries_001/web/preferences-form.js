// Native controls, localized labels and field errors. No requests or submission here.
import {changeMake,normalizePhone} from './preferences-state.js?v=20260927.10';
const el=(tag,text,attrs={})=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;for(const [k,v] of Object.entries(attrs))n.setAttribute(k,v);return n;};
export class PreferenceForm {
  constructor(main,optional,directory,catalog,state,onChange) {
    Object.assign(this,{main,optional,directory,catalog,state,onChange});this.lang='uk';this.ui={};this.groups={};
  }
  t(key){return this.directory.labels[this.lang][key];}
  get v(){return this.state.values;}
  update(key,value){this.v[key]=value;this.state.dirty[key]=true;this.clearError(key);this.onChange();}
  refresh(...keys){const focused=document.activeElement;for(const key of keys){const next=this.group(key);this.groups[key]?.replaceWith(next);this.groups[key]=next;}if(focused?.id&&!focused.isConnected)document.getElementById(focused.id)?.focus({preventScroll:true});}
  render(lang) {
    clearTimeout(this.countTimer);
    this.lang=lang;this.groups={};
    const main=['purchase_country_code','vehicle_type','make','models','budget','year','mileage','delivery_country','delivery_city','customer_name','contact'];
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
  modelControls() {
    const wrap=el('div'),list=el('div',undefined,{class:'model-choices'}),rows=[];
    const models=this.directory.makes[this.v.make]?.models||[];
    const add=el('button',this.t('add_model'),{type:'button',class:'secondary'});let serial=0;
    const refresh=()=>{
      for(const row of rows) {
        const others=new Set(rows.filter(x=>x!==row).map(x=>x.value));
        row.select.replaceChildren(el('option',this.t('choose'),{value:''}),...models.filter(x=>!others.has(x)).map(x=>el('option',x,{value:x})));
        row.select.value=row.value;
        row.remove.hidden=rows.length===1&&!row.value;
        row.remove.setAttribute('aria-label',`${this.t('remove')}: ${row.value||this.t('models')}`);
      }
      add.hidden=rows.some(row=>!row.value)||rows.length>=models.length;
    };
    const save=()=>{this.update('models',rows.map(row=>row.value).filter(Boolean));refresh();};
    const append=value=>{
      const index=serial++,row={value,element:el('div',undefined,{class:'model-choice'})};
      row.select=this.select(index?`models-${index}`:'models',{},'',value=>{row.value=value;save();});
      row.select.setAttribute('aria-labelledby','legend-models');
      row.remove=el('button','×',{type:'button',class:'secondary'});
      row.remove.addEventListener('click',()=>{
        const index=rows.indexOf(row);rows.splice(index,1);row.element.remove();
        if(!rows.length)append('');save();
        rows[Math.min(index,rows.length-1)].select.focus({preventScroll:true});
      });
      row.element.append(row.select,row.remove);rows.push(row);list.append(row.element);return row;
    };
    for(const value of this.v.models.length?this.v.models:[''])append(value);
    add.addEventListener('click',()=>{const row=append('');refresh();row.select.focus({preventScroll:true});});
    refresh();wrap.append(list,add);return wrap;
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
    // Keep the native select attached: replacing and refocusing it can reopen
    // the mobile picker. Only its dependent manual input changes.
    const manual=el('div');
    const renderManual=(code,current)=>{
      manual.replaceChildren();manual.hidden=code!=='custom';
      if(code!=='custom')return;
      const custom=this.input(`${name}-custom`,current,text=>callback(text.trim()===''?null:text),{numeric:true,max});
      custom.setAttribute('aria-label',`${this.t('custom')}: ${select.getAttribute('aria-label')}`);manual.append(custom);
    };
    const select=this.select(name,choices,mode,code=>{
      this.ui[name]=code;callback(code==='custom'||code===''?null:(code in extra?code:Number(code)));renderManual(code,null);
    });select.setAttribute('aria-label',`${this.t(name.split('-')[0])}${name.includes('-')?' · '+this.t(name.split('-')[1]):''}`);
    renderManual(mode,value);wrap.append(select,manual);
    return wrap;
  }
  group(key) {
    const box=el('fieldset',undefined,{'data-field':key}),legend=el('legend',this.t(key),{id:`legend-${key}`});box.append(legend);
    const v=this.v,options=this.directory.options,local=field=>Object.fromEntries(Object.entries(options[field]).map(([k,val])=>[k,val[this.lang]]));
    const addInput=(name,value,callback,settings)=>box.append(this.label(name,this.input(name,value,callback,settings)));
    const manual=el('div');
    const showManual=(show,name,value,callback)=>manual.replaceChildren(...(show?[this.label(name,this.input(name,value,callback,{max:120}))]:[]));
    if(key==='purchase_country_code') {
      const countries=Object.fromEntries(Object.entries(this.catalog.countries).map(([k,c])=>[k,c.name[this.lang]]));
      const renderManual=()=>showManual(v[key]==='other','purchase_country_other',v.purchase_country_other,value=>{v.purchase_country_other=value;this.update(key,v[key]);});
      box.append(this.select(key,{...countries,other:this.t('other_value'),help:this.t('help')},v[key],value=>{v.purchase_country_other='';this.update(key,value);renderManual();}),manual);renderManual();
    } else if(key==='make') {
      const renderManual=()=>showManual(v.make==='other','make_other',v.make_other,value=>{v.make_other=value;this.update(key,v.make);});
      box.append(this.select(key,{...Object.fromEntries(Object.entries(this.directory.makes).map(([k,m])=>[k,m.name])),other:this.t('other_value'),help:this.t('help')},v.make,value=>{changeMake(this.state,value,this.directory);this.clearError(key);renderManual();this.refresh('models');this.onChange();}),manual);renderManual();
    } else if(key==='models') {
      box.append(this.note('model_help'));
      if(v.make==='help')box.append(el('p',this.t('help')));
      else {
        const modes={selected:this.t('selected'),other:this.t('other_value')};
        const details=el('div');
        const renderModels=()=>{
          details.replaceChildren();
          if(v.model_mode==='selected')details.append(this.modelControls());
          if(v.model_mode==='other')details.append(this.label('other_model',this.input('other_model',v.other_model,value=>{v.other_model=value;this.update(key,v.models);},{max:120})));
          for(const select of details.querySelectorAll('select'))select.setAttribute('aria-labelledby',legend.id);
        };
        const mode=this.select('model_mode',modes,v.model_mode||'selected',value=>{if(v.model_mode===value)return;v.model_mode=value;v.models=[];v.other_model='';this.update(key,[]);renderModels();},{placeholder:false});
        mode.options[0].disabled=!this.directory.makes[v.make];
        mode.disabled=!v.make;mode.setAttribute('aria-label',this.t('model_mode'));box.append(mode,details);renderModels();
      }
    } else if(key==='budget') {
      const value=v.budget.mode==='help'?'help':v.budget.max;
      box.append(this.presetNumber(key,value,this.directory.budgets,x=>this.update(key,{mode:x==='help'?'help':(this.ui[key]?'limit':''),max:x==='help'?null:x,currency:'USD'}),{extra:{help:this.t('consult')}}));
    } else if(key==='vehicle_type'||key==='purchase_timing') {
      box.append(this.select(key,local(key),v[key],value=>this.update(key,value||null)));
    } else if(key==='year'||key==='engine') {
      const row=el('div',undefined,{class:'range-controls'});for(const bound of ['from','to']) {
        const values=key==='year'?Array.from({length:this.directory.current_year-1989},(_,i)=>this.directory.current_year-i):this.directory.engines;
        const control=this.presetNumber(`${key}-${bound}`,v[key]?.[bound]??null,values,value=>{
          const interval={...(v[key]||{from:null,to:null}),[bound]:value};this.update(key,key==='engine'&&interval.from===null&&interval.to===null?null:interval);
        },{max:key==='year'?4:5,useGrouping:key!=='year'});const wrap=el('div');wrap.append(el('span',this.t(bound)),control);row.append(wrap);
      }box.append(row);
    } else if(key==='mileage') {
      box.append(this.presetNumber(key,v.mileage.any?'any':v.mileage.max,this.directory.mileages,x=>this.update(key,{max:x==='any'?null:x,any:x==='any'}),{extra:{any:this.t('any')}}),this.note('mileage_help'));
    } else if(key==='delivery_country') {
      box.append(this.select(key,local(key),v[key],value=>{this.update(key,value);this.update('delivery_city',{code:'',other:''});this.refresh('delivery_city');}),this.note('delivery_help'));
    } else if(key==='delivery_city') {
      const cities=Object.fromEntries(Object.entries(this.directory.cities[v.delivery_country]||{}).map(([k,val])=>[k,val[this.lang]]));
      const renderManual=()=>showManual(v[key].code==='other','delivery_city_other',v[key].other,value=>this.update(key,{code:'other',other:value}));
      const control=this.select(key,{...cities,other:this.t('other_value')},v[key].code,value=>{this.update(key,{code:value,other:''});renderManual();});
      control.disabled=!v.delivery_country;
      box.append(control,manual);renderManual();
    } else if(key==='customer_name') {
      const input=this.input(key,v[key],value=>this.update(key,value),{autocomplete:'name'});input.setAttribute('aria-labelledby',legend.id);box.append(input);
    } else if(key==='contact') {
      box.append(this.label('contact_method',this.select('contact_method',local('contact_method'),v.contact.method,value=>{this.update(key,{...v.contact,method:value});input.autocomplete=value==='telegram'?'off':'tel';input.type=value==='telegram'?'text':'tel';input.inputMode=value==='telegram'?'text':'tel';input.placeholder=value==='telegram'?'':'+380…';note.textContent=this.t(value==='telegram'?'telegram_help':'phone_help');})));
      const input=this.input(key,v.contact.value,value=>this.update(key,{...v.contact,value}),{autocomplete:v.contact.method==='telegram'?'off':'tel'});
      if(v.contact.method!=='telegram')input.type='tel';input.inputMode=v.contact.method==='telegram'?'text':'tel';input.placeholder=v.contact.method==='telegram'?'':'+380…';
      const formatPhone=()=>{if(v.contact.method==='telegram')return;const value=normalizePhone(input.value);if(input.value!==value)input.value=value;if(v.contact.value!==value)this.update(key,{...v.contact,value});};
      input.addEventListener('input',event=>{if(['insertReplacementText','insertFromPaste'].includes(event.inputType))formatPhone();});
      input.addEventListener('change',formatPhone);input.addEventListener('blur',formatPhone);
      input.setAttribute('aria-labelledby',legend.id);input.setAttribute('aria-describedby','contact-help');
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
