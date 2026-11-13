"""Home «5 steps» block, other 7 countries (HOME-OTHER-SOON-001, owner 2026-11-13): keep step 1 only.

For every country except Korea, the hidden steps 2–5 are removed and the note «уточнюйте в менеджера» becomes a
«coming soon» title and text (ru/uk/ka); the «Заповнити заявку» button stays. One CSS rule styles the title.
Korea's steps, step 1 and every other byte stay. Each anchor must occur exactly once, otherwise nothing is changed.
"""
# Today's hidden steps 2–5 of the other countries, byte for byte as live.
OLD_STEPS = (
    '<li data-ua-for="other" hidden><i>2</i><b data-ru="Сопровождение автомобиля" data-uk="Супровід автомобіля" data-ka="ავტომობილის თანხლება">Супровід автомобіля</b><small data-ru="Фото, видео и OBD-диагностика" data-uk="Фото, відео та OBD-діагностика" data-ka="ფოტო, ვიდეო და OBD დიაგნოსტიკა">Фото, відео та OBD-діагностика</small></li>',
    '<li data-ua-for="other" hidden><i>3</i><b data-ru="Договор" data-uk="Договір" data-ka="ხელშეკრულება">Договір</b><small data-ru="Цена фиксируется до покупки" data-uk="Ціна фіксується до купівлі" data-ka="ფასი ფიქსირდება შეძენამდე">Ціна фіксується до купівлі</small></li>',
    '<li data-ua-for="other" hidden><i>4</i><b data-ru="Доставка" data-uk="Доставка" data-ka="მიწოდება">Доставка</b><small data-ru="Маршрут и дата онлайн" data-uk="Маршрут і дата онлайн" data-ka="მარშრუტი და თარიღი ონლაინ">Маршрут і дата онлайн</small></li>',
    '<li data-ua-for="other" hidden><i>5</i><b data-ru="Растаможка и выдача" data-uk="Розмитнення і видача" data-ka="განბაჟება და გადაცემა">Розмитнення і видача</b><small data-ru="В Украине и Грузии, с сопровождением" data-uk="В Україні та Грузії, з супроводом" data-ka="საქართველოსა და უკრაინაში, თანხლებით">В Україні та Грузії, з супроводом</small></li>',
)
OLD = ('<p data-ru="Условия для этой страны — уточняйте у менеджера." data-uk="Умови для цієї країни — уточнюйте в менеджера." data-ka="ამ ქვეყნის პირობები — დააზუსტეთ მენეჯერთან.">Умови для цієї країни — уточнюйте в менеджера.</p>')
NEW = ('<b class="ua-soon" data-ru="Скоро здесь появится подробная информация" '
       'data-uk="Незабаром тут з’явиться детальна інформація" '
       'data-ka="მალე აქ დეტალური ინფორმაცია გამოჩნდება">Незабаром тут з’явиться детальна інформація</b>'
       '<p data-ru="Мы уже готовим этапы, сроки и стоимость для этой страны. А пока оставьте заявку — менеджер всё расскажет лично." '
       'data-uk="Ми вже готуємо етапи, строки та вартість для цієї країни. А поки залиште заявку — менеджер усе розповість особисто." '
       'data-ka="ამ ქვეყნისთვის ეტაპებს, ვადებსა და ღირებულებას უკვე ვამზადებთ. მანამდე დატოვეთ განაცხადი — მენეჯერი ყველაფერს პირადად მოგიყვებათ.">'
       'Ми вже готуємо етапи, строки та вартість для цієї країни. А поки залиште заявку — менеджер усе розповість особисто.</p>')
CSS_AFTER = '.ua-cc-other p{margin:0;font-size:16px;line-height:1.6;color:#e6edf5}'
CSS = '.ua-cc-other .ua-soon{font-size:18px;line-height:1.35;font-weight:800;color:var(--gold)}'
# Public proof.
CHECK = 'Незабаром тут з’явиться детальна інформація'
GONE = ('уточнюйте в менеджера', '<li data-ua-for="other"')


def build(source):
    page = source.decode('utf-8')
    if CHECK in page or any(page.count(a) != 1 for a in OLD_STEPS + (OLD, CSS_AFTER)):
        raise ValueError('HOME_OTHER_SOON_ANCHOR')
    for step in OLD_STEPS:
        page = page.replace(step, '', 1)
    page = page.replace(OLD, NEW, 1).replace(CSS_AFTER, CSS_AFTER + CSS, 1)
    return page.encode('utf-8')
