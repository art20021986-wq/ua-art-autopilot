# SEARCH-HOME-001 — разведка (сессия 40, 26.11)

## Макет
- cloud/photos/40-SEARCH-HOME-phone.png, 40-SEARCH-HOME-pc.png (было → станет).
- Меняется только верхний блок главной `section.ua-kr-auc` («Аукціони онлайн · Корея»):
  заголовок «Пошук авто на аукціонах світу», ряд стран (Усі країни, Корея, Америка, Японія,
  Європа, Китай, Канада, ОАЕ, Грузія — как нижний ряд, флаги order/flags/*.svg),
  поля Марка / Модель / Рік від / Ціна до + «Знайти авто». Слайдер торгов и нижний ряд — без изменений.
- Критерии — те же, что в фильтре korea.html (kl-maker, kl-model, kl-year, kl-usd).
  Страна с лотами онлайн → korea.html с фильтром; без лотов → podbor.html?strana=… (заявка).

## Copart / IAAI (поиск в сети; copart.com и iaai.com закрыты сетью сессии)
- IAAI: условия прямо запрещают роботов/парсинг («robot, spider … screen scrape the Service»).
  https://www.iaai.com/TermsOfUse
- Copart: фото и данные лотов — по отдельной лицензии (Image and Data License Agreement), стоит
  защита от ботов Imperva. Публичного API/фида нет.
- Сторонние API (apiauto.space от $59/мес, apicars.auction $150/мес) — неофициальные, лицензии
  Copart/IAAI нет: риск блокировки и претензий. Не рекомендую.
- Законно: (1) ссылки на страницы лотов Copart/IAAI (бесплатно); (2) лоты вручную под клиента;
  (3) письменный запрос фида у Copart (Registered Broker) и IAAI (Export Partners/Brokers),
  цена не публикуется.
