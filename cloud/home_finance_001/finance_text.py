"""Texts of the home «Кредит і лізинг» block (HOME-FINANCE-001, owner 2026-11-12). Pure data, no logic.

Every entry is (ru, uk, ka). Partner facts are the ones already live on the finance page (ua_finance_partners):
ОТП Банк credits a car on its way or under order (owner 2026-11-04 and 2026-11-12), ХАПАЙ Авто leasing from 20%.
"""
KICKER = ('ФИНАНСИРОВАНИЕ ПОКУПКИ', 'ФІНАНСУВАННЯ КУПІВЛІ', 'შეძენის დაფინანსება')
TITLE = ('Купите авто в кредит или лизинг', 'Купуйте авто в кредит або лізинг',
         'შეიძინეთ ავტომობილი კრედიტით ან ლიზინგით')

# The finance page (made by ua_seo_landings); Georgian visitors get the Ukrainian page, as from the car cards.
PAGE = '/video/seo/ua/kredyt-lizynh-avto.html'

CARDS = (
    dict(key='otp', anchor='kredyt', logo='/video/finance/otp-bank.png', size=(480, 126), alt='OTP Bank',
         kind=('Кредит', 'Кредит', 'კრედიტი'),
         badge=('Преимущество OTP', 'Перевага OTP', 'OTP-ის უპირატესობა'),
         main=('Кредит на авто в пути или под заказ', 'Кредит на авто в дорозі або під замовлення',
               'კრედიტი გზაში მყოფ ან შეკვეთით ავტომობილზე'),
         go=('Рассчитать кредит', 'Розрахувати кредит', 'კრედიტის გამოთვლა')),
    dict(key='hapai', anchor='lizynh', logo='/video/finance/hapai-lizing.png', size=(480, 66), alt='ХАПАЙ лізинг',
         kind=('Лизинг', 'Лізинг', 'ლიზინგი'),
         badge=None,
         main=('Аванс от 20%', 'Аванс від 20%', 'ავანსი 20%-დან'),
         go=('Рассчитать лизинг', 'Розрахувати лізинг', 'ლიზინგის გამოთვლა')),
)
