# CARD-FULLSCREEN-001 (сессия 40)
Владелец 28.11 (через координатора, скрин Maserati MC20 на japan.html, iPhone): карточка лота должна открываться на весь
экран, сверху закреплённые наши кнопки, фон не листается, все кнопки нажимаются.
Решение: cloud/card_fullscreen_001/lot-card.css → /video/order/lot-card.css (только телефон ≤760px), одна строка link перед
</head> на korea.html/japan.html (usa — сессия 45). Скрины до/после: cloud/photos/40-cardfs-*.png. Ждёт «Да» владельца.
