# UA-ART-MEDIA-GALLERY-001

Общая галерея фото и видео для существующих и будущих карточек: один основной кадр, горизонтальные миниатюры, увеличенный просмотр с той же лентой, нативное видео и доступный браузеру полный экран. Порядок, адреса медиа и данные автомобиля сохраняются. Автопрокрутки и автозапуска видео нет.

Рабочий компонент состоит из трёх модулей: `ua_media_gallery.py` формирует HTML и данные, `ua_media_styles.py` содержит ограниченные компонентом стили, `ua_media_script.py` управляет выбором и нативным диалогом/плеером. Сторонние библиотеки, сервисы и глобальные перехватчики событий не добавляются.

`build_candidate.py` меняет только исходные блоки фото/видео и старый просмотрщик внутри исходной функции `sobrat_kartochku`. Последующие обёртки и диагностика сохраняются. `media_migration.py` преобразует существующие HTML-карточки, сохраняя байты вне медиаблоков; неизвестная структура останавливает подготовку. Поддержаны прежний просмотрщик и версия desktop-v1.

Процесс выпуска повторяет уже проверенный gallery_desktop_001 в отдельном пакете, чтобы параллельная задача desktop и её закреплённые хеши не менялись. Подготовка выполняется в приватной временной области; применение требует свежего плана, штатных Gate A/B, точной команды запуска, резервной копии, блокировок публикации, проверки живых страниц и готового отката. При изменении файлов между подготовкой и установкой выпуск останавливается. Защиты автопилота не меняются.

Проверки: `python -m unittest discover -s cloud/media_gallery_002 -p 'test_*.py'`. 44 теста проверяют исходный генератор из аудита, структуру и порядок медиа, экранирование, миграцию, реальные временные файлы/SQLite, восстановление после прерывания и сохранение чужих изменений. JavaScript отдельно проверяется `node --check`.

До приёмки обязательны проверка фактического текущего генератора в shadow-подготовке и проверка интерфейса: мышь/клавиатура, диалог с миниатюрами, отсутствие автозапуска, смена/остановка видео, полный экран, маленький экран и возврат фокуса. Эти проверки не подменяются результатом unit-тестов. iPhone Safari/Chrome и TikTok требуют отдельной проверки на реальных устройствах.

Официальные источники:
- https://www.w3.org/WAI/ARIA/apg/patterns/carousel/
- https://www.w3.org/WAI/ARIA/apg/patterns/tabs/
- https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/
- https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/video
- https://developer.mozilla.org/en-US/docs/Web/API/Element/requestFullscreen

## Current release coordination

R2 shadow run 36354666743 passed for all 22 canonical cards and their site mirrors. It did not change production. CRM-PHOTO-VISIBILITY-INSTALL-20260928 run 36355030909 started immediately afterwards and changes the same source and UA-0023 card. This isolated R3 package refreshes the actual server plan after that installation; its three runtime media modules are byte-identical to the reviewed R2 gallery . Preserve consumed R2 code and evidence. Do not install from its stale plan. R3 must run after already active photo/tracking writes finish, followed by the exact gallery install; the alias companion must wait for that successful install and synchronize its JavaScript to the exact installed version (R2 adds selected-tab focus reset and initial broken-thumbnail handling).
