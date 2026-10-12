"""Check structured identity and main specifications against a captured CRM row; no I/O."""
import re
from html import unescape
from html.parser import HTMLParser


def plain(value):
    return ' '.join(unescape(value).split())


class Fields(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack=[]
        self.headings=[]
        self.tables=[]
        self.paragraphs=[]
        self.spans=[]
        self.visible_vins=[]
        self.current_table=None
        self.row=None

    def handle_starttag(self, tag, attrs):
        attrs=dict(attrs)
        if tag in {'img','meta','link','br','hr','input','source','wbr'}:
            return
        self.stack.append([tag,attrs,[]])
        if tag=='table' and 'kratko' in attrs.get('class','').split():
            self.current_table=[]
        if tag=='tr' and self.current_table is not None:
            self.row=[]

    def handle_data(self,data):
        for node in self.stack:
            node[2].append(data)

    def handle_endtag(self,tag):
        match=next((i for i in range(len(self.stack)-1,-1,-1) if self.stack[i][0]==tag),None)
        if match is None:return
        node=self.stack[match];del self.stack[match:]
        text=plain(''.join(node[2]))
        if tag in {'title','h1','h2'}:self.headings.append((tag,text))
        if tag=='p':self.paragraphs.append(text)
        if tag=='span':self.spans.append(text)
        if 'ua-vin-value' in node[1].get('class','').split():self.visible_vins.append(text)
        if tag=='td' and self.row is not None:self.row.append(text)
        if tag=='tr' and self.row is not None:
            self.current_table.append(self.row);self.row=None
        if tag=='table' and self.current_table is not None:
            self.tables.append(self.current_table);self.current_table=None


def _integer(value,field):
    text=str(value).strip()
    if not re.fullmatch(r'\d+',text):raise RuntimeError('Unverified CRM '+field)
    return int(text)


def verify_core_fields(source,card,catalog=False):
    """Scope is explicit: identity and main specifications, not full specification acceptance."""
    doc=Fields();doc.feed(source);doc.close()
    year=str(card.get('year') or '').strip()
    if not re.fullmatch(r'\d{4}',year):raise RuntimeError('Unverified CRM year')
    brand=plain(str(card.get('brand') or ''));model=plain(str(card.get('model') or ''))
    if not brand or not model:raise RuntimeError('Unverified CRM brand/model')
    expected=plain(f'{brand} {model} {year}').casefold()
    required=('h2',) if catalog else ('title','h1')
    for tag in required:
        values=[v for t,v in doc.headings if t==tag]
        if len(values)!=1:raise RuntimeError('Missing or ambiguous '+tag)
        value=values[0].casefold()
        # The title includes an existing company suffix; visible headings are exact.
        if not (value==expected or (tag=='title' and value.startswith(expected+' — '))):
            raise RuntimeError('CRM identity differs in '+tag)
    mileage=_integer(card.get('mileage_km'),'mileage_km')
    engine=_integer(card.get('engine_cc'),'engine_cc')
    def field(key):
        value=plain(str(card.get(key) or ''))
        if not value:raise RuntimeError('Unverified CRM '+key)
        return value.casefold()
    if catalog:
        candidates=[]
        for value in doc.paragraphs:
            m=re.fullmatch(r'([\d\s\u00a0\u202f]+)\s*км(?:\s*·.*)?',value)
            if m:candidates.append(int(re.sub(r'\s','',m[1])))
        if candidates != [mileage]:raise RuntimeError('CRM mileage differs in catalog')
        specs=[x for x in doc.paragraphs if re.match(r'^[\d\s]+км',x)]
        parts=specs[0].split('·') if len(specs)==1 else []
        if len(parts)!=4:raise RuntimeError('Unsupported catalog specification')
        match=re.fullmatch(r'([\d\s]+)\s*см³',parts[1].strip())
        if not match or int(re.sub(r'\s','',match[1]))!=engine:
            raise RuntimeError('CRM engine_cc differs in catalog')
        if plain(parts[2]).casefold()!=field('fuel'):raise RuntimeError('CRM fuel differs in catalog')
        if plain(parts[3]).casefold()!=field('gearbox'):raise RuntimeError('CRM gearbox differs in catalog')
        vins=[v for v in doc.spans if v.startswith('VIN ')]
        if vins!=['VIN '+str(card.get('vin') or '').strip()]:raise RuntimeError('CRM VIN differs in catalog row')
    else:
        if len(doc.tables)!=1:raise RuntimeError('Missing or ambiguous short specification')
        rows=doc.tables[0]
        def one(label):
            found=[r[1] for r in rows if len(r)==2 and r[0]==label]
            if len(found)!=1:raise RuntimeError('Missing or ambiguous '+label)
            return found[0]
        vin=str(card.get('vin') or '').strip().upper()
        table_vins=[r[1] for r in rows if len(r)==2 and r[0]=='VIN']
        if len(table_vins)>1 or len(doc.visible_vins)>1:
            raise RuntimeError('Missing or ambiguous VIN')
        visible_vins=table_vins+doc.visible_vins
        if not vin or not visible_vins or any(v.strip().upper()!=vin for v in visible_vins):
            raise RuntimeError('CRM VIN differs in visible row')
        found=re.fullmatch(r'([\d\s\u00a0\u202f]+)\s*км',one('Пробег'))
        if not found or int(re.sub(r'\s','',found[1]))!=mileage:
            raise RuntimeError('CRM mileage differs in visible row')

        match=re.fullmatch(r'([\d\s]+)\s*см³,\s*(.+)',one('Двигатель'))
        if not match or int(re.sub(r'\s','',match[1]))!=engine:
            raise RuntimeError('CRM engine_cc differs in visible row')
        if plain(match[2]).casefold()!=field('fuel'):raise RuntimeError('CRM fuel differs in visible row')
        for key,label in [('gearbox','Коробка'),('drive','Привод'),('color','Цвет')]:
            if one(label).casefold()!=field(key):raise RuntimeError('CRM '+key+' differs in visible row')
