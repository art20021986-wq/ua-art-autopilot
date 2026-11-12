"""Step 2 payment line (HOME-STEP2-PAY-001, owner «да» 2026-11-12): the 600 $ is a service, not a purchase.

Only the word in that one line changes (ru/uk/ka); every other byte stays. The line must occur exactly once.
"""
OLD = ('<p class="ua-step-pay" data-ru="Оплата на этом шаге: покупка — 600 $, депозит — 1 000 $" '
       'data-uk="Оплата на цьому кроці: купівля — 600 $, депозит — 1 000 $" '
       'data-ka="გადახდა ამ ეტაპზე: ყიდვა — 600 $, დეპოზიტი — 1 000 $">'
       'Оплата на цьому кроці: купівля — 600 $, депозит — 1 000 $</p>')
NEW = ('<p class="ua-step-pay" data-ru="Оплата на этом шаге: услуга — 600 $, депозит — 1 000 $" '
       'data-uk="Оплата на цьому кроці: послуга — 600 $, депозит — 1 000 $" '
       'data-ka="გადახდა ამ ეტაპზე: მომსახურება — 600 $, დეპოზიტი — 1 000 $">'
       'Оплата на цьому кроці: послуга — 600 $, депозит — 1 000 $</p>')
# Public proof.
CHECK = 'послуга — 600 $, депозит — 1 000 $'
GONE = ('купівля — 600 $',)


def build(source):
    page = source.decode('utf-8')
    if page.count(OLD) != 1 or NEW in page:
        raise ValueError('HOME_STEP2_PAY_ANCHOR')
    return page.replace(OLD, NEW, 1).encode('utf-8')
