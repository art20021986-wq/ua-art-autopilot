"""video/order/preferences-form.js: the contact block goes to its own place at the end of the form, messenger last.

The «Контакт для зв'язку» group is rendered into a third container (after the consent box) instead of the main fields,
and inside it the phone or @username field comes first and «Як із вами зв'язатися» last. Values, validation and the
request do not change. Each original fragment must occur exactly once and an applied edit is refused.
"""
NAME = 'video/order/preferences-form.js'
EDITS = (
    ('  constructor(main,optional,directory,catalog,state,onChange) {\n'
     '    Object.assign(this,{main,optional,directory,catalog,state,onChange});',
     '  constructor(main,optional,directory,catalog,state,onChange,contact) {\n'
     '    Object.assign(this,{main,optional,directory,catalog,state,onChange,contact});'),
    ("'delivery_country','delivery_city','customer_name','contact'];",
     "'delivery_country','delivery_city','customer_name'];"),
    ('for(const [container,keys] of [[this.main,main],[this.optional,optional]])',
     "for(const [container,keys] of [[this.main,main],[this.optional,optional],[this.contact,['contact']]])"),
    ("      box.append(this.label('contact_method',this.select('contact_method',",
     "      const method=this.label('contact_method',this.select('contact_method',"),
    ("note.textContent=this.t(value==='telegram'?'telegram_help':'phone_help');})));",
     "note.textContent=this.t(value==='telegram'?'telegram_help':'phone_help');}));"),
    ("note.id='contact-help';box.append(input,note);",
     "note.id='contact-help';box.append(input,note,method);"),
)
# Public proof that the file is live.
CHECK = "[this.contact,['contact']]"


def build(source):
    text = source.decode('utf-8')
    for old, new in EDITS:
        if text.count(old) != 1 or new in text:
            raise ValueError('CONTACT_FORM_FRAGMENT_NOT_UNIQUE')
        text = text.replace(old, new, 1)
    return text.encode('utf-8')
