"""Folders of the CRM enquiry desk by where an enquiry came from (LEAD-FOLDERS-001, owner 2026-11-06).

One list for leads and for orders («Заказы», signed contracts): a car card on the site or in the client bot →
«Авто в наличии»; an order form or short form → the purchase country; anything without a country → «Общие».
Two groups on top (JPAUTO-KOREA-001, owner 2026-11-10): «Индивидуальный заказ» holds all the folders above;
«Аукционы онлайн» holds the online-auction access requests by auction country.
Pure functions, no I/O.
"""
STOCK, GENERAL = 'stock', 'general'
COUNTRIES = ('korea', 'japan', 'china', 'usa', 'europe', 'canada', 'uae', 'georgia')
FOLDERS = (STOCK,) + COUNTRIES + (GENERAL,)
LABELS = {STOCK: '🚗 Авто в наличии', 'korea': '🇰🇷 Корея', 'japan': '🇯🇵 Япония', 'china': '🇨🇳 Китай',
          'usa': '🇺🇸 США', 'europe': '🇪🇺 Европа', 'canada': '🇨🇦 Канада', 'uae': '🇦🇪 ОАЭ',
          'georgia': '🇬🇪 Грузия', GENERAL: '📂 Общие'}
CARD_SCHEMA = 'ua_order_request.card.v1'
AUCTION_SCHEMA = 'ua_order_request.auction.v1'
AUCTION_COUNTRIES = ('korea',)  # Japan and others later
AUCTION_FOLDERS = tuple('auction_' + country for country in AUCTION_COUNTRIES)
LABELS.update({'auction_korea': '🇰🇷 Корея'})
ALL_FOLDERS = FOLDERS + AUCTION_FOLDERS
ORDER_GROUP, AUCTION_GROUP = 'order', 'auction'
GROUPS = {ORDER_GROUP: FOLDERS, AUCTION_GROUP: AUCTION_FOLDERS}
GROUP_LABELS = {ORDER_GROUP: '🧾 Индивидуальный заказ', AUCTION_GROUP: '🔨 Аукционы онлайн'}


def of_enquiry(data):
    """The folder of an order package enquiry (its stored data)."""
    if data.get('schema_version') == CARD_SCHEMA:
        return STOCK
    if data.get('schema_version') == AUCTION_SCHEMA:
        folder = 'auction_' + str(data.get('purchase_country_code'))
        return folder if folder in AUCTION_FOLDERS else GENERAL
    country = data.get('purchase_country_code')
    return country if country in COUNTRIES else GENERAL


def label(folder):
    return LABELS[folder]


def group_of(folder):
    return AUCTION_GROUP if folder in AUCTION_FOLDERS else ORDER_GROUP


def group_label(group):
    return GROUP_LABELS[group]
