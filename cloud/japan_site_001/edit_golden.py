"""catalog_design_golden.html: «Выкуплены» filter and the country row «Все · Корея · Япония» (JAPAN-STOCK-001 step 2).

- the stage-1 filter button «В Корее · N» becomes «Выкуплены · N» / «Викуплені · N» (catalog_design_guard and
  ua_site_counters recount it; the counter script of the page knows the new label);
- below the stage filters, for «Выкуплены» and «На пароме» only, the row «Все · 🇰🇷 Корея · 🇯🇵 Япония» with counts
  of that stage. It is not a .filter-row and has no data-f, so the existing filter, counters and shell checks ignore
  it; cards are hidden by CSS on the data-country attribute of each catalog card (inline display stays the existing
  filter's).
"""
from edits import replace_once

NAME = 'catalog_design_golden.html'
ROW = ('<div class="ua-country-row" hidden aria-label="Страна" data-ru-aria="Страна" data-uk-aria="Країна">'
       '<button type="button" data-c="all" class="active" aria-pressed="true">'
       '<span data-ru="Все" data-uk="Усі">Все</span> · <b>0</b></button>'
       '<button type="button" data-c="korea" class="" aria-pressed="false">'
       '🇰🇷 <span data-ru="Корея" data-uk="Корея">Корея</span> · <b>0</b></button>'
       '<button type="button" data-c="japan" class="" aria-pressed="false">'
       '🇯🇵 <span data-ru="Япония" data-uk="Японія">Япония</span> · <b>0</b></button></div>'
       '<style id="ua-country-row-v1">'
       '.ua-country-row{display:flex;gap:9px;overflow-x:auto;margin:-10px 0 22px;padding-bottom:4px;scrollbar-width:none}'
       '.ua-country-row::-webkit-scrollbar{display:none}.ua-country-row[hidden]{display:none}'
       '.ua-country-row button{flex:0 0 auto;padding:12px 17px;border:1px solid var(--line);border-radius:999px;'
       'background:#0b1829;color:#aab8ca;cursor:pointer}'
       '.ua-country-row b{font-weight:inherit}.ua-country-row button.active{border-color:var(--gold);color:var(--gold);background:rgba(232,168,56,.08)}'
       'html[data-ua-country="korea"] .catalog-card:not([data-country="korea"]),'
       'html[data-ua-country="japan"] .catalog-card:not([data-country="japan"]){display:none!important}'
       '</style>'
       '<script id="ua-country-row-v1-js">/* UA-COUNTRY-ROW-V1 (JAPAN-STOCK-001) */(function(){'
       'var row=document.querySelector(".ua-country-row");if(!row)return;'
       'var root=document.documentElement,buttons=row.querySelectorAll("button[data-c]"),country="all";'
       'function stage(){var a=document.querySelector(".filter-row button.active");return a?a.getAttribute("data-f"):"all";}'
       'function counts(){var s=stage(),n={all:0,korea:0,japan:0},'
       'cards=document.querySelectorAll(".catalog-card[data-stage=\\""+s+"\\"]");'
       'for(var i=0;i<cards.length;i++){if(cards[i].getAttribute("data-ua-dubl"))continue;'
       'n.all++;n[cards[i].getAttribute("data-country")==="japan"?"japan":"korea"]++;}return n;}'
       'function show(){var s=stage(),on=s==="korea"||s==="sea";row.hidden=!on;if(!on)country="all";'
       'if(country==="all")root.removeAttribute("data-ua-country");else root.setAttribute("data-ua-country",country);'
       'var n=counts();for(var i=0;i<buttons.length;i++){var c=buttons[i].getAttribute("data-c"),a=c===country;'
       'buttons[i].className=a?"active":"";buttons[i].setAttribute("aria-pressed",a?"true":"false");'
       'buttons[i].querySelector("b").textContent=n[c];}'
       'var r=document.querySelector(".catalog-result");if(on&&r)r.textContent="Показано: "+n[country];}'
       'row.addEventListener("click",function(e){var b=e.target.closest("button[data-c]");'
       'if(b){country=b.getAttribute("data-c");show();}});'
       'document.addEventListener("click",function(e){if(e.target.closest&&e.target.closest(".filter-row button")){'
       'country="all";setTimeout(show,0);}});'
       'document.addEventListener("DOMContentLoaded",show);setTimeout(show,600);})();</script>')
PAIRS = (
    ('data-ru="В Корее · 2" data-uk="У Кореї · 2">В Корее · 2</button></div>',
     'data-ru="Выкуплены · 2" data-uk="Викуплені · 2">Выкуплены · 2</button></div>' + ROW),
    ('korea:["В Корее","У Кореї","У Кореi","Корея"]',
     'korea:["Выкуплены","Викуплені","В Корее","У Кореї","У Кореi","Корея"]'),
)


def build(source):
    return replace_once(source.decode('utf-8'), PAIRS, NAME).encode('utf-8')
