"""Prepare a local preview/bundle from exact public HTML; never writes live paths."""
import argparse
import hashlib
from html import escape
from html.parser import HTMLParser
import json
import re
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parent
CONFIG=ROOT.parent/'ua_order_ge_8country_guard_016/country_models.json'


class ElementSpan(HTMLParser):
    def __init__(self,source,predicate):
        super().__init__(convert_charrefs=False)
        self.source,self.predicate=source,predicate
        self.lines=[0]
        for line in source.splitlines(keepends=True): self.lines.append(self.lines[-1]+len(line))
        self.start=None;self.depth=0;self.tag=None;self.spans=[]
        self.feed(source)

    def position(self):
        line,column=self.getpos();return self.lines[line-1]+column

    def handle_starttag(self,tag,attrs):
        if self.start is None and self.predicate(tag,dict(attrs)):
            self.start=self.position();self.tag=tag;self.depth=1
        elif self.start is not None and tag==self.tag: self.depth+=1

    def handle_endtag(self,tag):
        if self.start is not None and tag==self.tag:
            self.depth-=1
            if self.depth==0:
                end=self.source.index('>',self.position())+1
                self.spans.append((self.start,end));self.start=None


def one_span(source,predicate):
    spans=ElementSpan(source,predicate).spans
    if len(spans)!=1: raise ValueError('Expected one exact integration region')
    return spans[0]


def patch_home(source,catalog):
    start,end=one_span(source,lambda tag,a:tag=='div' and a.get('class')=='countries-inline')
    links=[]
    for code,country in catalog['countries'].items():
        attrs=' '.join(f'data-{lang}="{escape(label,quote=True)}"' for lang,label in country['name'].items())
        links.append(f'<a href="podbor.html?strana={code}&amp;lang=uk" data-order-country="{code}"><span {attrs}>{escape(country["name"]["uk"])}</span><img src="order/flags/{code}.svg" width="54" height="36" alt=""></a>')
    replacement='<nav class="countries-inline ua-order-inline" aria-label="Авто під замовлення">'+''.join(links)+'</nav>'
    result=source[:start]+replacement+source[end:]
    if result.count('</head>')!=1 or result.count('</body>')!=1:raise ValueError('Invalid page shell')
    css='<style id="ua-order-country-grid">.countries-inline.ua-order-inline{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px}.ua-order-inline a{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8px;min-height:96px;padding:10px 3px;border:1px solid #b99b58;border-radius:9px;color:inherit;text-decoration:none;text-align:center;font-size:13px;overflow-wrap:anywhere}.ua-order-inline img{width:48px;height:32px;object-fit:contain}.ua-order-inline a:focus-visible{outline:3px solid #e8c87d;outline-offset:3px}</style>'
    script='<script id="ua-order-country-links">(()=>{const update=()=>{const lang=["uk","ru","ka"].includes(document.documentElement.lang)?document.documentElement.lang:"uk";document.querySelectorAll("[data-order-country]").forEach(a=>{a.href="podbor.html?strana="+a.dataset.orderCountry+"&lang="+lang;});};update();new MutationObserver(update).observe(document.documentElement,{attributes:true,attributeFilter:["lang"]});})();</script>'
    return result.replace('</head>',css+'</head>',1).replace('</body>',script+'</body>',1)


def patch_form(source):
    template=(ROOT/'web/podbor.html').read_text()
    a,b=one_span(template,lambda tag,attrs:tag=='main' and attrs.get('id')=='ua-order')
    fragment=template[a:b]
    installed=ElementSpan(source,lambda tag,attrs:tag=='main' and attrs.get('id')=='ua-order').spans
    if installed:
        if len(installed)!=1: raise ValueError('Expected one order form')
        start,end=installed[0]
        result=source[:start]+fragment+source[end:]
        for name in ('css','js'):
            version='20260927.10'
            result,count=re.subn(r'(order/order\.'+name+r'\?v=)[^"\s]+',r'\g<1>'+version,result)
            if count!=1: raise ValueError('Unexpected order asset includes')
        return result
    start,_=one_span(source,lambda tag,a:tag=='div' and a.get('id')=='p_zag')
    script_start=source.index('<script>',start)
    end=source.index('</script>',script_start)+len('</script>')
    block=source[start:end]
    if "id='p_forma'" not in block or "id='p_send'" not in block or "t:'podbor'" not in block:
        raise ValueError('Unknown order form implementation; inspect before patching')
    result=source[:start]+fragment+source[end:]
    includes='<link rel="stylesheet" href="order/order.css?v=20260927.10"><script type="module" src="order/order.js?v=20260927.10"></script>'
    return result.replace('</head>',includes+'</head>',1)


def build(output,*,homepage=None,podbor=None):
    output=Path(output).resolve()
    if output.exists(): raise ValueError('Use a fresh local output directory')
    if str(output).startswith('/home/Carix'):
        raise ValueError('Production paths are not a build destination')
    catalog=json.loads(CONFIG.read_text())
    output.mkdir(parents=True)
    shutil.copytree(ROOT/'web',output/'order')
    shutil.copy2(ROOT/'strings.json',output/'order/order-strings.json')
    if podbor:
        source=Path(podbor).read_text();(output/'podbor.html').write_text(patch_form(source))
    else:
        shutil.copy2(ROOT/'web/podbor.html',output/'order/podbor.html')
    if homepage:
        source=Path(homepage).read_text();(output/'index.html').write_text(patch_home(source,catalog))
    manifest={'config_version':catalog['version'],'production_write':False,'files':{}}
    for path in sorted(output.rglob('*')):
        if path.is_file():manifest['files'][str(path.relative_to(output))]=hashlib.sha256(path.read_bytes()).hexdigest()
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True)
    parser.add_argument('--homepage');parser.add_argument('--podbor')
    args=parser.parse_args();print(json.dumps(build(args.output,homepage=args.homepage,podbor=args.podbor),indent=2))
