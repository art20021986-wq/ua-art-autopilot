"""Complete readable v2 summaries for the existing inbox and Telegram review."""
from html import escape
from .preferences import directory


def country_label(data, catalog, lang='ru'):
    code = data['purchase_country_code']
    if code in catalog.export()['countries']:
        return catalog.country(code)['name'][lang]
    return directory()['labels'][lang]['help'] if code == 'help' else data.get('purchase_country_other', '')


def pairs(data, catalog, lang='ru'):
    config = directory(); t = config['labels'][lang]
    def option(field, key): return config['options'][field][key][lang]
    def number(value): return f'{value:,}'.replace(',', ' ')
    def interval(value):
        return ' '.join(f'{t[key]} {value[key]:g}' for key in ('from','to') if value[key] is not None)
    mode = data['model_mode']
    model = ', '.join(data['models']) if mode == 'selected' else data['other_model'] if mode == 'other' else t['any_model' if mode == 'any' else 'help']
    make = config['makes'][data['make']]['name'] if data['make'] in config['makes'] else t['help'] if data['make']=='help' else data['make_other']
    budget = t['consult'] if data['budget']['mode']=='help' else f'{t["to"]} {number(data["budget"]["max"])} USD'
    city = data['delivery_city']; city = city['other'] if city['code']=='other' else config['cities'][data['delivery_country']][city['code']][lang]
    fields = [('purchase_country_code',country_label(data,catalog,lang)),('make',make),('models',model),('budget',budget),
              ('vehicle_type',option('vehicle_type',data['vehicle_type'])),('year',t['any'] if data['year']['any'] else interval(data['year'])),
              ('mileage',t['any'] if data['mileage']['any'] else f'{t["to"]} {number(data["mileage"]["max"])} {t["km_unit"]}'),
              ('delivery_country',option('delivery_country',data['delivery_country'])),('delivery_city',city),
              ('customer_name',data['customer_name']),('contact',f'{option("contact_method",data["contact"]["method"])}: {data["contact"]["value"]}')]
    for field in ('fuel','drive'):
        if data[field]: fields.append((field,', '.join(option(field,x) for x in data[field])))
    if data['engine']: fields.append(('engine',interval(data['engine'])))
    if data['colours']:
        fields.append(('colours',', '.join(f'{option("colours",x)}: {data["colour_other"] or t["clarify"]}' if x=='other' else option('colours',x) for x in data['colours'])))
    if data['purchase_timing']: fields.append(('purchase_timing',option('purchase_timing',data['purchase_timing'])))
    if data['comment']: fields.append(('comment',data['comment']))
    return [(t[key],value+(f' ({t["required"]})' if data['priority'].get(key)=='required' else '')) for key,value in fields]


def split_text(value, *, limit=3500):
    """Split by UTF-16 units conservatively, without truncating or breaking emoji."""
    chunks=[]; current=[]; size=0
    for char in value:
        units=2 if ord(char)>0xffff else 1
        if size+units>limit:
            chunks.append(''.join(current));current=[];size=0
        current.append(char);size+=units
    if current: chunks.append(''.join(current))
    return chunks or ['']


def detail(row, catalog):
    fields=[('Заявка',row['number']),*pairs(row['data'],catalog)]
    if row.get('telegram_user_id'): fields.append(('Telegram ID',row['telegram_user_id']))
    plain='\n'.join(f'{key}: {value}' for key,value in fields)
    chunks=split_text(plain)
    parts=[escape(f'{row["number"]} · {i+1}/{len(chunks)}\n{part}' if len(chunks)>1 else part) for i,part in enumerate(chunks)]
    return dict(text=escape(plain),parts=parts,buttons=[[('К заявкам','orders:list')]])
