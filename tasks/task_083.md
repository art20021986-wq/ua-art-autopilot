# TASK 083 — UA-0012/UA-0013 publication transaction repair

## Прямая команда владельца

29.08.2026 владелец потребовал без дополнительного согласования:

- выявить и устранить причину, по которой полностью готовые UA-0012 и UA-0013 не появились в каталоге;
- немедленно разместить обе машины на правильных этапах;
- исправить CRM-бот так, чтобы следующие публикации не давали ложный успех и не оставляли CRM и сайт в разных состояниях;
- выполнить production-исправление с резервом, проверкой и автоматическим откатом.

Эта команда является прямым bounded production authorization для TASK 083. Новое подтверждение не требуется.

## Свежие доказательства

- UA-0012: `published=1`, `status=sea_transit`, этап 2, категория `more`, публичной страницы и записи в каталоге нет.
- UA-0013: `published=1`, `status=sea_loaded`, этап 2, категория `more`, публичной страницы и записи в каталоге нет.
- Активный `cars_ui.toggle_publish` не проверяет `ok` издателя и после отказа всегда пишет «Машина видна клиентам в каталоге.».
- Активный SEO guard требует уже существующий `UA-NNNN-diag.html` до создания placeholder новой карточки.
- Обычный publisher обновляет primary/diag, но не устанавливает оба каталога как часть той же транзакции.

## Разрешённый production scope

- `/home/Carix/publikaciya.py`;
- `/home/Carix/cars_ui.py`;
- `/home/Carix/publish_transaction_guard.py`;
- `/home/Carix/catalog_stage_guard_core.py`;
- primary и diagnostic HTML только UA-0012/UA-0013 в `/home/Carix/video` и `/home/Carix/site`;
- `/home/Carix/video/katalog.html` и `/home/Carix/site/katalog.html`;
- restart только единственного активного `python3.10 /home/Carix/start_safe.py` после PASS.

CRM rows, статусы, VIN, цена, описание и media не изменяются. Любой FAIL — полный откат к точному preimage.

## Обязательный результат

- UA-0012 и UA-0013 имеют HTTP 200 primary и diagnostic pages;
- каждая машина встречается в каждом каталоге ровно один раз;
- обе имеют stage 2, category `more`, label «На пароме»;
- отсутствие материалов диагностики создаёт корректный placeholder и не блокирует карточку;
- wrong diagnostic link по-прежнему блокируется;
- future publish выполняет primary + diag + оба каталога одним проверяемым пакетом;
- publisher FAIL/exception/readback mismatch возвращает exact preimage и одно итоговое сообщение;
- success разрешён только после полного readback и immediate + delayed public verification;
- runtime LLM tokens = 0.

