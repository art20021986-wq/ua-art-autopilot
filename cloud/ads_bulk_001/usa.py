"""The existing campaign «Пошук — США (UA ART)» as data (created by cloud/ads_usa_001; owner 28.11 «да»: its keyword
plan goes in every night together with Korea). Pure: no network.

Ad texts are the approved ones of cloud/ads_usa_001 (owner «да» 27.11), one responsive ad per new group. The site has
only the Ukrainian page usa.html (ru/usa.html answers 404 on 28.11), so ru groups land there too, as the existing ones
do. Policy lessons of plan.py kept: no «Ставка онлайн», no «Отримайте пропозицію», no forced capitals.
"""
import keywords_jpus

NAME = 'Пошук — США (UA ART)'
NAMES = "'%s'" % NAME
PAGE = 'https://www.uaart.com.ua/video/usa.html'
MAX_NEW_GROUPS = 40  # a night: 40 groups + 40 ads = 80 operations, so the total stays within the ~2 880 a day
UK_HEAD = ['Авто з США під ключ', 'Аукціони США: Copart', 'Послуга — 600 $', 'Звіт Carfax — 0 $',
           'Доступ до Copart безкоштовно', 'Офіс у Києві, Перемоги 20', 'Офіційний договір', 'Особистий кабінет 24/7',
           'Страхування авто в дорозі']
UK_DESC = ['Обираєте авто на аукціонах США — викуповуємо, страхуємо й веземо до Києва.',
           'Послуга 600 $ за договором. Звіт Carfax — 0 $, доступ до аукціонів безкоштовно.',
           'Залиште заявку — менеджер напише у Viber або Telegram.']
RU_HEAD = ['Авто из США под ключ', 'Аукционы США: Copart', 'Услуга — 600 $', 'Отчёт Carfax — 0 $',
           'Доступ к Copart бесплатно', 'Офис в Киеве, Победы 20', 'Официальный договор', 'Личный кабинет 24/7',
           'Страховка авто в пути']
RU_DESC = ['Выбираете авто на аукционах США — выкупаем, страхуем и везём в Киев.',
           'Услуга 600 $ по договору. Отчёт Carfax — 0 $, доступ к аукционам бесплатно.',
           'Оставьте заявку — менеджер напишет в Viber или Telegram.']


def plan():
    """{group name: [keyword]} — 'UA — США під ключ', 'UA — США — <brand>', 'UA — США — <brand> — роки', ru alike."""
    return keywords_jpus.plan('usa')


def ad(group, ad_group):
    """One responsive search ad: «<brand> з США» first for a brand group, then the approved headlines."""
    lang = 'uk' if group.startswith('UA') else 'ru'
    head, desc = (UK_HEAD, UK_DESC) if lang == 'uk' else (RU_HEAD, RU_DESC)
    parts = group.split(' — ')
    if len(parts) > 2:
        head = ['%s %s' % (parts[2], 'з США' if lang == 'uk' else 'из США')] + head
    head = [h for n, h in enumerate(head) if len(h) <= 30 and h not in head[:n]][:15]
    return {'adGroupAdOperation': {'create': {'adGroup': ad_group, 'status': 'ENABLED', 'ad': {
        'finalUrls': [PAGE], 'responsiveSearchAd': {'headlines': [{'text': h} for h in head],
                                                    'descriptions': [{'text': d} for d in desc],
                                                    'path1': 'usa', 'path2': 'kyiv' if lang == 'uk' else 'kiev'}}}}}


def group_operations(customer, current, limit=None):
    """Up to MAX_NEW_GROUPS missing plan groups with one ad each, and an ad for a plan group that has none."""
    campaign = current['campaign']['resourceName']
    new = [g for g in plan() if g not in current['groups']][:MAX_NEW_GROUPS if limit is None else limit]
    ops = []
    for n, group in enumerate(new):
        temp = 'customers/%s/adGroups/-%d' % (customer, 900 + n)
        ops.append({'adGroupOperation': {'create': {'resourceName': temp, 'name': group, 'status': 'ENABLED',
                                                    'campaign': campaign, 'type': 'SEARCH_STANDARD'}}})
        ops.append(ad(group, temp))
    ops += [ad(g, current['groups'][g]) for g in plan()
            if g in current['groups'] and g not in current.get('with_ads', set(current['groups']))]
    return ops


def waiting(current):
    """{group: [keyword]} of the plan not yet anywhere in the campaign (by text: never the same search twice)."""
    texts = {k for _, k in current['keywords']}
    return {g: [k for k in ks if k not in texts] for g, ks in plan().items()}
