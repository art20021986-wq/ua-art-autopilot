# Точная применимость исторического Preview 24/24

Исторический PASS от 2026-09-15 сохраняется без изменения даты. Это 24 критерия для 18 карточек, 20 обслуживаемых страниц и 120 наблюдений (RU/UA/GE × desktop1280×900/mobile390×844). Installation candidate `eaceee78…` и Preview resource manifest `c6febae0…` — разные контракты. Старый Gate не является свежим PASS для 22 машин.

Проверенные первичные документы:

- `cloud/task088_v5_acceptance/resume_20260915_2/PREVIEW_GATE.json`, SHA256 `3ed070183d19de801348aef5a521d30781c6528aa585441c6593ab34ae7f864a`.
- `resume_20260914/canonical/PREFLIGHT_BROWSER_BINDING_V2.json`: 20 точных HTML SHA из реально наблюдавшегося harness и совпадающие SHA кандидата.
- `resume_20260915/preflight_retry/PREFLIGHT_COMPLETION_VERIFICATION.json`: старые 54 файла, 40 HTML, 9625 файлов inventory и отдельный DB/schema bridge. Это исторические результаты.
- `resume_20260915/PHOTOS_ACCEPTANCE_20260915.json`: прежнее подтверждение владельцем галереи сохраняется; нового подтверждения того же поведения не требуется.

Сравнение сохранённых шести полей старых rows с реальным SQL-readback 2026-09-20: добавлены UA-0019–0022; UA-0017 изменилась `ua_arrived/23000` → `ge_waiting/22000`. Остальные 17 старых rows совпадают. Новые ожидаемые группы: Kyiv6, Georgia7, sea4, Korea5; всего22. Это конкретная дельта данных, а не доказательство неизменности всех HTML и ресурсов.

Первый полный observer остановился на INVENTORY_PASS_1 через180s. Его `PARTIAL_NOT_ACCEPTED` не подтверждает HTML, второй проход или full inventory. Новый ограниченный core observer должен дать complete terminal summary с `export_completed:true`, всеми10 stability flags, совпадающими DB/schema2pass и всеми48 coreHTML. Встроенный pre-export `observation_summary.json` сам по себе не является terminal outcome.

| Критерий | Что повторно проверить для текущего кандидата | Что можно сохранить доказательно |
|---|---|---|
| all_published_cars | Независимые22rows, все44cardHTML,24servedpages, новые19–22 | Покрытие17 неизменённых старых карточек после привязки |
| homepage |6 locale/viewport cases, новые counts/links, inlinecounter после загрузкикаталога | Неизменный общий дизайн/медиа при SHA binding |
| catalog |6cases,22prices,5filters и точные code sets | Неизменный renderer/CSS/handler при SHA binding |
| full_cards |UA0017 и19–22; новые VIN/spec/additional/diag/gallery entries | Старые17card/diag при HTML+resource binding |
| ru |RU для affectedpages | ИсторическийRU для неизменныхpages |
| ua |UA(uk) для affectedpages | ИсторическийUA для неизменныхpages |
| ge |GE(ka) для affectedpages | ИсторическийGE для неизменныхpages |
| language_switching |Настоящие RU→UA→GE действия на обновлённыхhome/catalog; новыеcardlocale observations | Прежний общий переключатель если код и зависимости прежние |
| ua_price |Все22значения offline;affectedpage browser card/catalog | Прежние17значений/отображение при точномbinding |
| ge_price |Все22правила offline;6Kyiv UA-only;16nonKyiv GE, включаяUA0017 | NumericGE UA0010=8750 и старые примеры при binding |
| missing_ge |Новый nonKyiv/nullGE UA0017 и21/22: localized text/caption | ПрежнийUA0015 sample при binding |
| desktop |1280×900 affectedpages: фактические viewport/font/boxes | Старые60desktop observations только по retainedpages |
| mobile |390×844 affectedpages: overflow/fonts/pricecaptions | СтарыйCSS-mobile scope; Safari/touch не был доказан |
| links |Новые4detail+4diag actual destinations/ownIDs;UA0017 если diag/link changed | Остальные прежниеlinks с неизменными destinations/bytes |
| buttons |Новые counts/filter/language actions;newcarddetails/gallery еслиhandler/content affected | Нативные CTA destinations и прошлоеacceptedsharedbehavior |
| vin |Новые19–22 actualtextpresence плюс all48nonprice preservation | Прежние17VINpresence, без нового декодированияVIN |
| photos |Транзитивные referenced assets SHA/bytes, newcards decodedimages/gallery; exact runtime response binding | Старые560galleryroutes/owneracceptance только если медиа+галерея неизменны |
| specifications |НовыеcardDOMpresence;48HTML scopedpreservation | Старые неизменныеtables; сторонняя точностьspecs не расширяется |
| additional_specification |Новыеentries;expansion новымcontent еслиуникальна | Прежнийsharedtoggle иUA0015 31parameters при binding |
| stages |Новые sets6/7/4/5;actualcatalogfilters иhome destinations | Прежняя filtermechanics при кодовомbinding |
| counters |Новый server/clientfix: actual22counts, сменаязыка, homefetch/catalogparse; 13 targetedtests отдельно | Старые 18counts не переносить; invariant sharedrender если доказан |
| no_unrelated_diff |48currentbefore→exactcandidate, price regions+exactcounterliteral only;newsource boundedreview | Исторические40HTMLchecks сохраняются как история |
| source_generation |Точныеcurrent19inputs +runtimebeforeimages, finalsourcecomposition/compile, newaffectedtests+independentreview | Неизменные446/183 tests не повторять |
| independent_db_readback |Свежиеcars/audit/published/schema2pass,corebinding;preservation против currentcapture | СтарыйDBreceipt не заменяет свежийreadback |

Минимальная обязательная новая browsermatrix — семь страниц: `/video/index.html`, `/video/katalog.html`, `/video/UA-0017.html`, `/video/UA-0019.html`…`/video/UA-0022.html`; ×3locale ×2viewport =42 наблюдения. Это нижняя граница до сравнения фактических страниц и ресурсов. Новые HTML/JS/CSS/media дельты расширяют затронутую область.

Если у17старыхcardHTML отличается только точная известная inlinecounterliteral, checker проверяет обратную замену до старого wholepageSHA. Исключение из полной browsermatrix допускается после независимого доказательства, что изменённый classifier недостижим на этихкарточках: decoded DOM не имеет `.catalog-grid`/`.outline-cta[href]`, а привязанные inline/external scripts не создают entrypoints. Одного отсутствиястрок в HTML недостаточно; такиеpages отмечаются provisional, а не PASS. Нельзя слепо запускать102старыхcases только из-за изменившегося inertliteral, но нельзя скрыть недоказанную область.

Новые42observations должны быть настоящими: выбрать страницу/viewport в существующем harness, переключить язык штатной кнопкой, дождаться загруженныхшрифтов/картинок, сохранить реальныеDOMreadback/screenshots. `candidate_sha256` в harness — manifestpin, не самостоятельный response-bytehash; отдельно нужен running-worker/config/runtime/resource binding. Фильтры: все22, Kyiv{2,7,8,18,19,20}, Georgia{1,9,10,11,12,17,21},sea{5,6,13,14},Korea{3,4,15,16,22}. Проверить реальныесчётчики и возвратall, затемязыки; внешниесообщения/звонки не отправляются.

`check_current_preview.py` принимает currentcapture/candidate/finalsummary, валидирует all48 точных байтов, создаёт affectedmatrix и переченьусловногоretention. Он не выпускает Gate и не принимает24/24. Full inventory не нужен для повторного рендеринга каждого unchangedpage, но полный inventory/backup/writerexclusion остаётся отдельными поздними обязательствами. Для Preview достаточна точная транзитивная привязка обслуживаемыхресурсов/диагностик/runtime и текущихcoreinputs; stat-onlymedia этим не является.
