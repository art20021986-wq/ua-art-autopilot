# JPAUTO-KOREA-001 — чтение кабинета аукциона, 2026-11-10

Запуск: Actions «JP Auto Korea Read-Only Probe», run 42761482068 (успех), 3 запроса.
Вход по секретам `JPAUTO_EMAIL`/`JPAUTO_PASSWORD` — OK, кабинет `/customers_dashboard`.
Площадка: BE FORWARD Live Auction (jpauto.auction). Поиск Кореи: `/vehicle-search/kr/`
(форма `purchase_search_form`, POST `/vehicle-search/kr/index`, `auction_country_id=28`).

## Параметры поиска (Корея), один в один
| Поле | Имя | Значения |
|---|---|---|
| Марка (Manufacturer) | `maker[]` | 224 варианта, множественный выбор |
| Модель | `model[]` | 2530 вариантов (зависит от марки) |
| Комплектация (Trim Level) | `grade_en` | текст |
| Год от/до | `model_year_en_from/_to` | 2000–2027 |
| Пробег от/до, км | `mileage_num_from/_to` | 10 000 … 200 000 |
| Объём от/до, см³ | `displacement_num_from/_to` | 0 … 4 000 |
| Цвет | `color[]` | 16 цветов |
| Левый руль | `left_hd[]` | флажок |
| Оценка (Score) | `scores[]` | 24: AA … DF |
| Номер лота | `bid` | текст |
| Показать закрытые торги | `order_closed[]` | флажок |
| Аукционы по дням | `auction_group[]`, `auction[]` | флажки |

## Аукционы и дни (из страницы поиска)
- Пн: AutoPlus (Weekly)
- Вт: AutoPlus (36), K-Car O-San (126), K-Car Se-Jong (425), SK Rent Car Auction (751)
- Ср: Auto Hub Auction (2 382), AutoHands
- Чт, Пт, Сб; Oneprice (фиксированная цена)

Вывод: торги идут почти каждый день (Пн–Сб), самый большой — среда. Одно обновление
в неделю (понедельник) будет показывать устаревшие лоты — нужен выбор владельца.

## Дальше
- Прочитать страницу результатов и одну карточку лота: поля, фото, водяные знаки.
- Согласовать с владельцем частоту обновлений и план раздела.
