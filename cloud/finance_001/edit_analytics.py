"""The site's own analytics (analitika_yadro.py, /ua/a.js) records a finance partner visit (FINANCE-001).

A click on a link marked data-finance-partner is sent as its own event type «finance» with the partner id
(not as a generic Telegram click), the type is accepted on intake and named «Кредиты и лизинг» in the
analytics report; ua_finance_crm reads these events for the CRM bot. Nothing else in the analytics changes.
Each original fragment must occur exactly once and an applied fragment is refused.
"""
NAME = 'analitika_yadro.py'
EDITS = (
    ('                  "phone", "share", "zakaz", "obyavlenie", "zayavka", "cta", "etap"])\n',
     '                  "phone", "share", "zakaz", "obyavlenie", "zayavka", "cta", "etap",\n'
     '                  "finance"])  # FINANCE-001: a visit to a finance partner\n'),
    ('"diag": "Диагностика", "card": "Карточка", "cta": "Кнопка", "etap": "Этап"}\n',
     '"diag": "Диагностика", "card": "Карточка", "cta": "Кнопка", "etap": "Этап",\n'
     '                "finance": "Кредиты и лизинг"}\n'),
    ("  var hl=h.toLowerCase();\n",
     "  var fp=a && a.getAttribute && a.getAttribute('data-finance-partner');\n"
     "  if(fp){ shlyom('finance',fp); return; }\n"
     "  var hl=h.toLowerCase();\n"),
)
CHECK_SCRIPT = "if(fp){ shlyom('finance',fp); return; }"


def build(name, source):
    text = source.decode('utf-8')
    for old, new in EDITS:
        if text.count(old) != 1 or new in text:
            raise ValueError('ANALYTICS_FRAGMENT_NOT_UNIQUE:' + old[:40])
        text = text.replace(old, new)
    compile(text, name, 'exec')
    return text.encode('utf-8')
