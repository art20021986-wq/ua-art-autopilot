"""Home page: the step 1 button «Заповнити заявку» opens the order page in its «Оформлення заявки» view.

Only the href of that one button changes (podbor.html -> podbor.html#zayavka); every other byte stays.
"""
OLD = '<a class="button gold" href="podbor.html" data-ru="Заполнить заявку"'
NEW = '<a class="button gold" href="podbor.html#zayavka" data-ru="Заполнить заявку"'
# Public proof that this file is live.
CHECK = 'href="podbor.html#zayavka"'


def build(source):
    text = source.decode('utf-8')
    if text.count(OLD) != 1 or NEW in text:
        raise ValueError('HOME_STEP1_BUTTON')
    return text.replace(OLD, NEW, 1).encode('utf-8')
