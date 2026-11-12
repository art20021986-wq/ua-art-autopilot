"""Step 2 «Оформлення договору»: remove the old line «Підбираємо, перевіряємо і купуємо…» (HOME-STEP2-FIX-001).

Only that one paragraph goes; every other byte stays. The home page must hold it exactly once; video/korea.html
(its no-JS copy of the steps block) changes only if it holds it. Otherwise nothing is changed.
"""
OLD = ('<p data-ru="Подбираем, проверяем и покупаем автомобиль на корейских аукционах." '
       'data-uk="Підбираємо, перевіряємо і купуємо автомобіль на корейських аукціонах." '
       'data-ka="ვარჩევთ, ვამოწმებთ და ვყიდულობთ ავტომობილს კორეის აუქციონებზე.">'
       'Підбираємо, перевіряємо і купуємо автомобіль на корейських аукціонах.</p>')
# Public proof: the old words are gone and step 2 is still there.
GONE = 'корейських аукціонах'
STEP2 = 'data-uk="Оформлення договору"'


def build(source, required=True):
    text = source.decode('utf-8')
    count = text.count(OLD)
    if count > 1 or (required and (count != 1 or text.count(STEP2) != 1)):
        raise ValueError('HOME_STEP2_ANCHOR')
    if count == 0:
        return None
    return text.replace(OLD, '', 1).encode('utf-8')
