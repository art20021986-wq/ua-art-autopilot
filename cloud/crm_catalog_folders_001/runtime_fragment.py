# UA-ART-CRM-CATALOG-FOLDERS-001:START
from pathlib import Path as _ua122_Path
from ua_crm_catalog_folders import (
    parse_catalog as _ua122_parse_catalog,
    partition_by_catalog as _ua122_partition,
)

_UA122_CATALOG = _ua122_Path('/home/Carix/video/katalog.html')
_UA122_LABELS = {'catalog': 'В каталоге', 'unpublished': 'Не опубликованные'}
_UA122_PAGE_SIZE = 20
_UA122_BASE_CARD_KB = card_kb
_UA122_BASE_REGISTER = register


def _ua122_catalog_ids():
    # An incomplete or concurrently replaced catalog must never empty a folder.
    before = _UA122_CATALOG.stat()
    source = _UA122_CATALOG.read_text(encoding='utf-8')
    after = _UA122_CATALOG.stat()
    if (before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_ino, after.st_size, after.st_mtime_ns):
        raise ValueError('Catalog changed while reading')
    return _ua122_parse_catalog(source)


async def cars_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await _v168_ack(q,)
    staff = db.get_staff(q.from_user.id)
    if not staff:
        await q.message.reply_text('Доступ только для сотрудников.')
        raise ApplicationHandlerStop
    drop_wait(context)
    context.user_data.pop('car_last', None)
    context.user_data.pop('car_voice_active', None)
    context.user_data.pop('voice_undo', None)
    try:
        cards = db.list_cards('cars', limit=-1)
        groups = _ua122_partition(cards, _ua122_catalog_ids())
        data = str(q.data or '')
        if data in ('cards_cars', 'cars_cards'):
            rows = [[InlineKeyboardButton('%s · %d' % (title, len(groups[key])),
                     callback_data='ua122_cars:%s:0' % key)]
                    for key, title in _UA122_LABELS.items()]
            rows.append([InlineKeyboardButton('← Назад', callback_data='menu')])
            await q.message.reply_text('Автомобили\nВыберите папку.',
                                       reply_markup=InlineKeyboardMarkup(rows))
            raise ApplicationHandlerStop
        parts = data.split(':')
        if (len(parts) != 3 or parts[0] != 'ua122_cars'
                or parts[1] not in _UA122_LABELS or not parts[2].isascii()
                or not parts[2].isdigit() or len(parts[2]) > 9):
            raise ValueError('Invalid folder callback')
        folder = parts[1]
        selected = groups[folder]
        last = max(0, (len(selected) - 1) // _UA122_PAGE_SIZE)
        page = min(int(parts[2]), last)
        lines = ['<b>%s · %d</b>' % (_UA122_LABELS[folder], len(selected))]
        rows = []
        if not selected:
            lines.append('В этой папке пока нет автомобилей.')
        for original in selected[page * _UA122_PAGE_SIZE:(page + 1) * _UA122_PAGE_SIZE]:
            card = card_of(original['id']) or original
            miss = S.missing_required(card)
            state = ('черновик, не хватает %d' % len(miss)) if miss else 'заполнена'
            stage = S.status_label(card.get('status')) if card.get('status') else 'этап не задан'
            lines.extend([_ua082_title_html(card), '   %s · %s' % (stage, state)])
            rows.append([InlineKeyboardButton(_ua082_title_button(card),
                          callback_data='car_open:%d' % card['id'])])
        nav = []
        if page:
            nav.append(InlineKeyboardButton('←', callback_data='ua122_cars:%s:%d' % (folder, page - 1)))
        if page < last:
            nav.append(InlineKeyboardButton('→', callback_data='ua122_cars:%s:%d' % (folder, page + 1)))
        if nav:
            lines.append('Страница %d из %d' % (page + 1, last + 1))
            rows.append(nav)
        rows.append([InlineKeyboardButton('← Автомобили', callback_data='cards_cars')])
        await q.message.reply_text('\n'.join(lines), parse_mode='HTML',
                                   reply_markup=InlineKeyboardMarkup(rows))
    except ApplicationHandlerStop:
        raise
    except Exception:
        log.exception('Не удалось прочитать папки автомобилей')
        await q.message.reply_text(
            'Не удалось обновить список. Повторите открытие раздела.',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton('← Автомобили', callback_data='cards_cars')]]))
    raise ApplicationHandlerStop


def card_kb(card, staff):
    markup = _UA122_BASE_CARD_KB(card, staff)
    try:
        folder = 'catalog' if card.get('auto_number') in _ua122_catalog_ids() else 'unpublished'
    except Exception:
        return markup  # Keep the existing return button on read failure.
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('← ' + _UA122_LABELS[folder],
             callback_data='ua122_cars:%s:0' % folder)
         if getattr(button, 'callback_data', None) in ('cards_cars', 'cars_cards')
         else button for button in row]
        for row in markup.inline_keyboard
    ])


def register(app):
    _UA122_BASE_REGISTER(app)
    app.add_handler(CallbackQueryHandler(cars_list,
        pattern=r'^ua122_cars:(?:catalog|unpublished):[0-9]{1,9}$'), group=-1)
# UA-ART-CRM-CATALOG-FOLDERS-001:END
