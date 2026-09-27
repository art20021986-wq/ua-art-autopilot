"""Pure customer conversation: reusable with the existing Telegram library."""
from uuid import uuid4
from copy import deepcopy
from . import preference_summary
from .preferences import directory

from .catalog import COUNTRIES, LANGUAGES
from .contract import Invalid, SCHEMA, text

TEXT_STEPS = ('other_model', 'delivery_country', 'delivery_city', 'customer_name', 'contact', 'comment')


def create(catalog, *, data=None):
    initial = dict(schema_version=SCHEMA, request_id=str(uuid4()), config_version=catalog.version,
                   purchase_country_code='', model='', other_model='',
                   budget={'code':'undecided','currency':'USD'}, vehicle_type='any',
                   delivery_country='', delivery_city='', customer_name='', contact={},
                   comment='', lang='uk', source_path='/telegram')
    if data and data.get('schema_version') == 'ua_order_request.v2':
        initial = deepcopy(data)
    else:
        initial.update(data or {})
    # The request UUID lets the server recover an already committed receipt
    # after a bot restart. It is never used as authorization on its own.
    return dict(nonce=initial['request_id'], revision=0, step='country', data=initial, receipt=None)


def callback(state, action, value=''):
    return f'ord:{state["nonce"]}:{state["revision"]}:{action}:{value}'


def transition(state, action, value, catalog):
    data, step = state['data'], state['step']
    if state['receipt']:
        return
    if data.get('schema_version') == 'ua_order_request.v2':
        if action == 'lang' and value in LANGUAGES: data['lang'] = value
        elif action == 'edit' and step == 'review': state['step'] = 'edit_web'
        elif action == 'back' and step == 'edit_web': state['step'] = 'review'
        else: raise Invalid('callback')
        state['revision'] += 1
        return
    if action == 'lang' and value in LANGUAGES:
        data['lang'] = value
    elif action == 'country' and step == 'country' and value in COUNTRIES:
        if value != data['purchase_country_code']:
            data['model'] = ''
        data['purchase_country_code'], state['step'] = value, 'models'
    elif action == 'model' and step == 'models' and value in ('0','1','2','3','4'):
        model = catalog.country(data['purchase_country_code'])['models'][int(value)]
        data['model'], data['other_model'], state['step'] = model['key'], '', 'photo'
    elif action == 'other' and step == 'models':
        data['model'], state['step'] = '', 'other_model'
    elif action == 'select' and step == 'photo':
        state['step'] = 'budget'
    elif action == 'budget' and step == 'budget' and value in catalog.choices('budgets'):
        data['budget']['code'], state['step'] = value, 'vehicle_type'
    elif action == 'type' and step == 'vehicle_type' and value in catalog.choices('vehicle_types'):
        data['vehicle_type'], state['step'] = value, 'delivery_country'
    elif action == 'skip' and step == 'comment':
        data['comment'], state['step'] = '', 'review'
    elif action == 'back':
        state['step'] = {'models':'country','photo':'models','other_model':'models','budget':'models',
                         'vehicle_type':'budget','delivery_country':'vehicle_type','delivery_city':'delivery_country',
                         'customer_name':'delivery_city','contact':'customer_name','comment':'contact','review':'comment'}.get(step,'country')
    elif action == 'edit' and step == 'review':
        state['step'] = 'country'
    else:
        raise Invalid('callback')
    state['revision'] += 1


def enter_text(state, value):
    step, data = state['step'], state['data']
    if step not in TEXT_STEPS or state['receipt']:
        raise Invalid('step')
    if step == 'contact':
        contact = text(value, 'contact', 5, 80)
        data['contact'] = {'telegram':contact} if contact.startswith('@') else {'phone':contact}
    else:
        maximum = 2000 if step == 'comment' else (120 if step == 'other_model' else 80)
        data[step] = text(value, step, 0 if step == 'comment' else 2, maximum)
    state['step'] = {'other_model':'budget','delivery_country':'delivery_city','delivery_city':'customer_name',
                     'customer_name':'contact','contact':'comment','comment':'review'}[step]
    state['revision'] += 1


def view(state, catalog, strings, consent_text):
    data, step = state['data'], state['step']
    lang = data['lang']; t = strings[lang]
    rows, photo = [], None
    def button(label, action, value=''):
        return (label, callback(state,action,value))
    if state['receipt']:
        return dict(text=f'{t["saved"]}: {state["receipt"]["number"]}', buttons=[], photo=None)
    if data.get('schema_version') == 'ua_order_request.v2':
        labels = directory()['labels'][lang]
        if step == 'edit_web':
            title = labels['edit_web_help']
            rows = [[(labels['edit_web'], f'https://www.uaart.com.ua/video/podbor.html?lang={lang}')], [button(t['back'],'back')]]
        else:
            title = t['review']+'\n'+'\n'.join(f'{k}: {v}' for k,v in preference_summary.pairs(data,catalog,lang))+'\n\n'+consent_text[lang]
            rows = [[button(t['confirm'],'submit')],[button(t['edit'],'edit')]]
        rows.append([button(label,'lang',code) for label,code in (('UA','uk'),('RU','ru'),('GE','ka'))])
        return dict(text=title,parts=preference_summary.split_text(title),buttons=rows,photo=None)
    if step == 'country':
        title = t['choose_country']
        buttons=[button(catalog.country(c)['name'][lang],'country',c) for c in COUNTRIES]
        rows = [buttons[i:i+2] for i in range(0,8,2)]
    elif step == 'models':
        title = t['choose_model'] + ' · ' + catalog.country(data['purchase_country_code'])['name'][lang]
        rows = [[button(m['labels'][lang],'model',str(i))] for i,m in enumerate(catalog.country(data['purchase_country_code'])['models'])]
        rows.append([button(t['other'],'other')])
    elif step == 'photo':
        model = catalog.model(data['purchase_country_code'],data['model'])
        title = model['labels'][lang] + ' · ' + t['under_order']
        if model['media']['approval'] == 'approved':
            photo = model['media']['path']
        if not photo:
            title += '\n' + t['media_pending']
        rows = [[button(t['select'],'select')]]
    elif step in ('budget','vehicle_type'):
        title=t[step]
        options = catalog.choices('budgets' if step=='budget' else 'vehicle_types')
        rows=[[button(labels[lang],'budget' if step=='budget' else 'type',code)] for code,labels in options.items()]
    elif step == 'review':
        model = catalog.model(data['purchase_country_code'],data['model']) if data['model'] else None
        pairs=[('country',catalog.country(data['purchase_country_code'])['name'][lang]),
               ('model',model['labels'][lang] if model else data['other_model']),
               ('budget',catalog.choices('budgets')[data['budget']['code']][lang]),
               ('vehicle_type',catalog.choices('vehicle_types')[data['vehicle_type']][lang]),
               ('delivery_country',data['delivery_country']),('delivery_city',data['delivery_city']),
               ('customer_name',data['customer_name']),('contact',', '.join(data['contact'].values())),('comment',data['comment'])]
        title=t['review']+'\n'+'\n'.join(f'{t[k]}: {v}' for k,v in pairs if v)+'\n\n'+consent_text[lang]
        rows=[[button(t['confirm'],'submit')],[button(t['edit'],'edit')]]
    else:
        title = t['other'] if step == 'other_model' else t[step]
        if step == 'comment': rows.append([button(t['skip'],'skip')])
    if step != 'country': rows.append([button(t['back'],'back')])
    rows.append([button(label,'lang',code) for label,code in (('UA','uk'),('RU','ru'),('GE','ka'))])
    return dict(text=title,buttons=rows,photo=photo)
