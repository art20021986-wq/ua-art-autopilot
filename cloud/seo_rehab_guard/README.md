# SEO REHAB GUARD 068

Изолированный контур реабилитации для `canonical`, `robots`, `sitemap` и CTA карточек UA ART.

## Что делает

- собирает живой срез публичного сайта только методом GET и не следует редиректам;
- динамически обнаруживает все `UA-XXXX` только по карточным ссылкам каталога;
- строит кандидат без `noindex,nofollow` и с единственным self-canonical;
- нормализует CTA каждой текущей и будущей карточки до `Задаток 500 $`;
- требует ровно одну диагностику того же ID и блокирует будущую карточку без неё;
- создаёт настоящие кандидаты `robots.txt` и `sitemap.xml`;
- сравнивает защищённое содержимое и выполняет 10 одинаковых сборок.

## Граница безопасности

Контур не содержит API записи, D1/CRM/PythonAnywhere write, reload или production deploy. Preview Worker принимает только GET/HEAD, не имеет cron/bindings/routes, отключает формы, выдаёт `X-Robots-Tag: noindex, nofollow, nosnippet` и служит только ветке GitHub Preview.

## Проверка

```bash
npm run test:rehab
node cloud/seo_rehab_guard/audit.mjs --output /tmp/GATE-REPORT.json
```

Production может быть затронут только отдельной командой владельца после зелёного CI и визуального утверждения.
