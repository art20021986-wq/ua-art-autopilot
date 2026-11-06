"""Folders of the CRM enquiry desk by where an enquiry came from (LEAD-FOLDERS-001, owner 2026-11-06).

One list for leads and for orders («Заказы», signed contracts): a car card on the site or in the client bot →
«Авто в наличии»; an order form or short form → the purchase country; anything without a country → «Общие».
Pure functions, no I/O.
"""
STOCK, GENERAL = 'stock', 'general'
COUNTRIES = ('korea', 'japan', 'china', 'usa', 'europe', 'canada', 'uae', 'georgia')
FOLDERS = (STOCK,) + COUNTRIES + (GENERAL,)
LABELS = {STOCK: '🚗 Авто в наличии', 'korea': '🇰🇷 Корея', 'japan': '🇯🇵 Япония', 'china': '🇨🇳 Китай',
          'usa': '🇺🇸 США', 'europe': '🇪🇺 Европа', 'canada': '🇨🇦 Канада', 'uae': '🇦🇪 ОАЭ',
          'georgia': '🇬🇪 Грузия', GENERAL: '📂 Общие'}
CARD_SCHEMA = 'ua_order_request.card.v1'


def of_enquiry(data):
    """The folder of an order package enquiry (its stored data)."""
    if data.get('schema_version') == CARD_SCHEMA:
        return STOCK
    country = data.get('purchase_country_code')
    return country if country in COUNTRIES else GENERAL


def label(folder):
    return LABELS[folder]
