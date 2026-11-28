# SHARE-LOTS-001 — «Поділитися» в карточке лота аукциона

Владелец «да» 28.11 06:33Z (через координатора, event be4a0b34). Где: открытая карточка лота (диалог `#kl-card`),
круглая оранжевая кнопка в верхнем ряду справа (слева от «на весь екран» и ×). Делает то же, что в каталоге
(`v171_knopka`): на телефоне — системное меню «поделиться» (Web Share API), иначе меню Telegram / WhatsApp /
«Скопіювати посилання». Ссылка — страница страны + `#lot-ID` (страница сама открывает этот лот). Превью ссылки —
общая картинка сайта (og:image страницы).

- `lot-share.js` → `video/order/lot-share.js` — один общий модуль на все страны (Корея, Япония, США).
- `video/korea.html`, `video/japan.html` — одна строка `<script src="/video/order/lot-share.js?v=share-lots-1" defer>` перед `</body>`.
- США (`video/usa.html`) — страница сессии 45: та же строка, когда на странице появится карточка лота (через координатора).

Best practice (MDN Web Share API): `share()` только по нажатию, проверка `canShare()`, отмена (AbortError) — не ошибка;
меню — отдельный `<dialog>` поверх карточки (top layer); копирование — `navigator.clipboard.writeText`, запасной путь — `execCommand`.

Пакет: `make_release.py preview` → превью → «Да» владельца на скрин 390px → `make_release.py install`.
Скрины: `cloud/photos/40-share-korea.png`, `40-share-korea-menu.png`, `40-share-japan.png`.
