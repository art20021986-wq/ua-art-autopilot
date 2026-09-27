"""Offline browser fixture: exact form modules; all API calls stay in memory."""
import argparse
import base64
import mimetypes
import json
from pathlib import Path
import re
import shutil
from ua_order.catalog import Catalog
from ua_order.preferences import export

ROOT=Path(__file__).resolve().parent


def build(output):
    output=Path(output)
    if output.exists():raise ValueError('Use a new preview directory')
    shutil.copytree(ROOT/'web',output)
    catalog=Catalog(ROOT.parent/'ua_order_ge_8country_guard_016/country_models.json').export()
    def embedded(path):
        asset=ROOT/'web'/path
        return 'data:'+mimetypes.guess_type(asset.name)[0]+';base64,'+base64.b64encode(asset.read_bytes()).decode()
    for country in catalog['countries'].values():
        country['flag']=embedded(country['flag'])
        for model in country['models']:model['media']['path']=embedded(model['media']['path'])
    strings=json.loads((ROOT/'strings.json').read_text())
    data=dict(catalog=catalog,preferences=export(),csrf='offline',consent_version='offline-v1',consent_text={lang:strings[lang]['consent'] for lang in strings})
    script='''// OFFLINE PREVIEW ONLY. No requests leave this file.
const offlineBootstrap=BOOTSTRAP,offlineStrings=STRINGS;
const receipts=new Map();
window.fetch=async(path,options={})=>{
 const url=String(path);let data;
 if(url.includes('/bootstrap'))data=offlineBootstrap;
 else if(url.includes('order-strings.json'))data=offlineStrings;
 else if(url.includes('/submit')){const value=JSON.parse(options.body);data={status:'saved',request_id:value.request_id,number:'PREVIEW-001'};receipts.set(value.request_id,data);}
 else if(url.includes('/receipt'))data=receipts.get(new URL(url,'https://preview.test').searchParams.get('request_id'));
 else throw Error('Network disabled in offline preview');
 return {ok:Boolean(data),status:data?200:404,json:async()=>data};
};
'''.replace('BOOTSTRAP',json.dumps(data,ensure_ascii=False)).replace('STRINGS',json.dumps(strings,ensure_ascii=False))
    for name in ('order-state.js','preferences-state.js','preferences-form.js','order.js'):
        source=(ROOT/'web'/name).read_text()
        source=re.sub(r'^import .+;\n','',source,flags=re.M).replace('export ','')
        script+='\n'+source
    page=(ROOT/'web/podbor.html').read_text()
    page=re.sub(r'<link rel="stylesheet" href="[^"]+">','<style>'+(ROOT/'web/order.css').read_text()+'</style>',page)
    page=re.sub(r'<script type="module" src="[^"]+"></script>','',page)
    banner='<aside style="padding:16px;background:#162e41;color:white;font:16px system-ui">Тестовая форма · заявки не отправляются. <button id="lang-uk">UA</button> <button id="lang-ru">RU</button> <button id="lang-ka">GE</button></aside>'
    language="for(const lang of ['uk','ru','ka']) document.getElementById('lang-'+lang).onclick=()=>{document.documentElement.lang=lang;};\n"
    page=page.replace('<body>','<body>'+banner).replace('</body>','<script type="module">'+language+script.replace('</script','<\\/script')+'</script></body>')
    (output/'preview.html').write_text(page)
    print(output/'preview.html')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args();build(args.output)
