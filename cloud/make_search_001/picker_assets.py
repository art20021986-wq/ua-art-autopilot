"""The two new files of the searchable list, served as /video/order/search-picker.js and .css (MAKE-SEARCH-001).

Kept as text here because the package upload carries Python files only.
"""
JS = r'''// One choice from a long list: a button opens a modal list with a search field on top and fixed
// entries (for example «Інша модель») at the bottom. Native <dialog>; no requests, no form state.
const el=(tag,text,attrs={})=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;for(const [k,v] of Object.entries(attrs))n.setAttribute(k,v);return n;};
const words=text=>text.toLocaleLowerCase().split(/[\s\-–—/().,]+/).filter(Boolean);

// Typed first letters match the start of the title or of any word in it: «ro» finds «Land Rover».
export function matches(title,query) {
  const q=query.trim().toLocaleLowerCase();
  return !q||title.toLocaleLowerCase().startsWith(q)||words(title).some(word=>word.startsWith(q));
}

// choices and pinned are functions returning [[code,title],…], read again on every opening.
export function searchPicker({id,value,choices,pinned=()=>[],labels,labelledBy,onChange}) {
  let current=value??'';
  const button=el('button',undefined,{type:'button',id,class:'search-picker','aria-haspopup':'dialog'});
  if(labelledBy)button.setAttribute('aria-labelledby',`${labelledBy} ${id}`);
  const show=()=>{button.textContent=[...choices(),...pinned()].find(([code])=>code===current)?.[1]??labels.choose;};
  button.addEventListener('click',()=>{
    const dialog=el('dialog',undefined,{class:'search-picker-dialog'});
    if(labelledBy)dialog.setAttribute('aria-labelledby',labelledBy);
    const body=el('div',undefined,{class:'search-picker-body'});
    const search=el('input',undefined,{type:'search',autocomplete:'off',enterkeyhint:'search',
      'aria-label':labels.search,placeholder:labels.search});
    const list=el('ul',undefined,{class:'search-picker-list'});
    const fixed=el('ul',undefined,{class:'search-picker-list search-picker-pinned'});
    const empty=el('p',labels.no_matches,{class:'field-help',role:'status'});
    const item=([code,title])=>{
      const option=el('button',title,{type:'button',class:'secondary'});
      if(code===current)option.setAttribute('aria-current','true');
      option.addEventListener('click',()=>{
        dialog.close();
        if(code!==current){current=code;show();onChange(code);}
      });
      const row=el('li');row.append(option);return row;
    };
    const rows=choices().map(item);
    const filter=()=>{
      let shown=0;
      for(const row of rows){row.hidden=!matches(row.textContent,search.value);shown+=!row.hidden;}
      empty.hidden=shown>0;
    };
    search.addEventListener('input',filter);
    // A tap outside the list closes it, as Esc and the phone's back gesture do.
    dialog.addEventListener('click',event=>{if(event.target===dialog)dialog.close();});
    dialog.addEventListener('close',()=>dialog.remove());
    const bottom=pinned().map(item);list.append(...rows);fixed.append(...bottom);fixed.hidden=!bottom.length;
    body.append(search,list,empty,fixed);dialog.append(body);filter();
    button.after(dialog);dialog.showModal();search.focus();
  });
  show();
  return button;
}
'''

CSS = r'''/* Searchable list of the order form (search-picker.js); scoped to the order form. */
.ua-order .search-picker{width:100%;display:flex;justify-content:space-between;align-items:center;gap:8px;text-align:left;font-weight:400;background:#0b1c2d;color:#fff;border-color:#728292;border-radius:8px;padding:12px}
.ua-order .search-picker::after{content:"▾";color:var(--gold)}
.ua-order .search-picker:disabled{cursor:not-allowed}
/* In a model row the list takes the free width; the × button keeps its own size. */
.ua-order .model-choice .search-picker{flex:1;padding:12px}
.ua-order .search-picker-dialog{width:min(560px,calc(100vw - 32px));margin:16px auto auto;padding:0;border:1px solid #3c5367;border-radius:12px;background:var(--panel);color:#f4f5f7}
.ua-order .search-picker-dialog::backdrop{background:rgba(0,0,0,.6)}
.ua-order .search-picker-body{display:flex;flex-direction:column;gap:8px;padding:12px;max-height:calc(100vh - 96px);max-height:calc(100dvh - 96px);box-sizing:border-box}
.ua-order .search-picker-list{list-style:none;margin:0;padding:0;overflow:auto;flex:1 1 auto;min-height:0}
.ua-order .search-picker-list li{margin:0 0 6px}
.ua-order .search-picker-list button{width:100%;text-align:left;font-weight:400}
.ua-order .search-picker-list button[aria-current="true"]{border-color:var(--gold);color:var(--gold)}
.ua-order .search-picker-pinned{flex:none;overflow:visible;border-top:1px solid #3c5367;padding-top:8px}
.ua-order .search-picker-body .field-help{margin:0}
'''
