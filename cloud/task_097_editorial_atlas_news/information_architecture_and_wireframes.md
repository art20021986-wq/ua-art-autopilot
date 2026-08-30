# Information architecture and wireframes (ASCII specification, not built)

## 1. Desktop — news homepage ("Editorial Atlas" hub)

```
+--------------------------------------------------------------------------------+
| UA ART  [ЛОГО]        Автоновини UA/RU switch          Пошук   Меню сайту     |
+--------------------------------------------------------------------------------+
| ROUTE PULSE (left rail, sticky)   | TOP NEWS (hero card, 16:9 image)          |
|  o Korea -> Georgia -> Ukraine     |  [Country Seal] [Impact Compass mini]     |
|  · story A - updated 2h ago        |  Headline (serif, 2 lines max)            |
|  · story B - updated 6h ago        |  Lead paragraph (2-3 sentences)           |
|  · story C - updated 1d ago        |  Route Spine divider                      |
|  [show more]                       +--------------------------------------------+
|                                    | STORY GRID (4:3 cards, 3 per row)         |
|                                    |  [card] [card] [card]                     |
|                                    |  [card] [card] [card]                     |
+--------------------------------------------------------------------------------+
| Rubric filters: Україна · Корея · Грузія · Японія · США · Європа · Китай      |
+--------------------------------------------------------------------------------+
| Footer: about the editorial desk, correction policy link, Source Ledger link  |
+--------------------------------------------------------------------------------+
```

## 2. Mobile — news homepage

```
+----------------------------------+
| UA ART   [UA|RU]   [menu]        |
+----------------------------------+
| TOP NEWS hero (16:9, full width) |
| Country Seal · headline · lead   |
+----------------------------------+
| Rubric chips (scrollable row)    |
+----------------------------------+
| Story card (4:3)                 |
| Story card (4:3)                 |
| Story card (4:3)                 |
+----------------------------------+
| Route Pulse (collapsed, tap to   |
| expand) — below the fold         |
+----------------------------------+
| Footer links                     |
+----------------------------------+
```

## 3. Desktop — article page

```
+--------------------------------------------------------------------------------+
| breadcrumb: Автоновини / Корея / Заголовок рубрики                            |
+--------------------------------------------------------------------------------+
| Hero image 16:9                     | STORY DOSSIER (right rail)               |
| Country Seal · date · category      |  Sources: 3   Confidence: high           |
| H1 headline (serif)                 |  Published: DD.MM.YYYY                   |
| Lead paragraph                      |  Updated: DD.MM.YYYY                     |
| Route Spine divider                 |  [Correction log]                        |
| Body copy, constrained measure      |                                          |
| Impact Compass (4 quadrants)        |                                          |
+--------------------------------------------------------------------------------+
| SOURCE LEDGER (full width, footer of article)                                 |
|  [domain A · class A]  [domain B · class B]  [domain C · class B]             |
+--------------------------------------------------------------------------------+
| hreflang switch: Читати українською / Читать на русском                       |
+--------------------------------------------------------------------------------+
```

## 4. Mobile — article page

Same stacking order as desktop, single column: hero → seal/date/category → H1 → lead → Route Spine → body → Impact Compass → Story Dossier (expandable panel, not a fixed right rail) → Source Ledger → language switch.

## 5. Owner candidate card (manual approval UI, desktop)

```
+--------------------------------------------------------------------------------+
| Кандидат новини #STORY-ID           NEWS SCORE: 78   [Owner approval queue]   |
+--------------------------------------------------------------------------------+
| Заголовок UA: ...                  | Заголовок RU: ...                       |
| Короткий опис UA: ...               | Короткое описание RU: ...                |
| Чому важливо клієнту: ...           |                                          |
+--------------------------------------------------------------------------------+
| Країна: Корея   Рубрика: Аукціони   Дата події: ...   Дата виявлення: ...     |
+--------------------------------------------------------------------------------+
| Достовірність фактів: 88   Ймовірність дубля: 6%   Оригінальність тексту: 94% |
+--------------------------------------------------------------------------------+
| Джерела: [домен A ↗] [домен B ↗]     Зображення: [thumbnail]  Права: PENDING  |
+--------------------------------------------------------------------------------+
| Пропоновані URL: /ua/avto-novyny/... і /ru/avto-novosti/...                   |
+--------------------------------------------------------------------------------+
|  [ОПУБЛИКОВАТЬ]   [УДАЛИТЬ]   [ОТЛОЖИТЬ]   [АУДИТ]                            |
+--------------------------------------------------------------------------------+
```

## 6. Autopilot settings screen (desktop, OFF by default)

```
+--------------------------------------------------------------------------------+
| Автопілот новин                                             [ ВИМКНЕНО  ○—— ] |
+--------------------------------------------------------------------------------+
| Пороги TOP NEWS (тільки перегляд, не редагується на цьому екрані):            |
|  NEWS SCORE ≥ 85   FACT CONFIDENCE ≥ 92   SOURCE CONFIDENCE ≥ 85              |
|  DUPLICATE PROBABILITY < 15%   TEXT ORIGINALITY ≥ 90%                        |
|  Права на зображення підтверджені · Джерело справне · UA/RU валідні          |
|  Категорія не є чутливою                                                     |
+--------------------------------------------------------------------------------+
| Щоб увімкнути автопілот, власник має:                                        |
|  1) перемкнути тумблер                                                       |
|  2) підтвердити дію в модальному вікні "Підтвердити включення автопілота"     |
+--------------------------------------------------------------------------------+
```

## 7. Explicit non-goal for this task

These are text wireframes for planning only. No HTML/CSS/component was built or deployed for any of the screens above.
