## Stage 1 result

Status: PASS

What was prepared:
- minimal CRM-only patch proposal for `cars_ui.py`;
- synthetic local verification for the existing `price_uah` field relabel and new optional `price_georgia` field;
- automated tests for write → DB → read-back, field independence and empty Georgia price.

What was not changed:
- public site, publisher, production, PythonAnywhere, cards, VIN, media, stages, counters, SEO, languages and CTA.

Evidence basis:
- real CRM schema proof from `/home/runner/work/ua-art-autopilot/ua-art-autopilot/cloud/task_070/evidence/real_context.json`;
- real `cars_ui.py` snippets for `ensure_columns`, `LABELS_ALL`, `EDITABLE`, `NUMERIC`, `edit_menu`, `edit_ask`, `apply_value` from `/home/runner/work/ua-art-autopilot/ua-art-autopilot/cloud/task_066_stage_anchor/evidence/current.json`;
- real `db.py.update_card_field` snippet from `/home/runner/work/ua-art-autopilot/ua-art-autopilot/cloud/task_067/evidence/read_only_audit.json`.

Checks covered:
- `Цена` visual relabelled to `Цена Украины` while keeping backend key `price_uah`;
- new optional `Цена Грузии` uses separate DB column `price_georgia`;
- write → DB → read-back works for both prices;
- `price_uah` and `price_georgia` remain independent;
- empty Georgia price stays unset and shows as `—` in the edit prompt.

Validation run:
- `python cloud/task_088_ge_price_crm_stage1/simulator.py > cloud/task_088_ge_price_crm_stage1/evidence.json`
- `python - <<'PY' ... import cloud.task_088_ge_price_crm_stage1.tests.test_stage1 ... PY` → 5/5 PASS
- `python -m py_compile cloud/task_088_ge_price_crm_stage1/simulator.py cloud/task_088_ge_price_crm_stage1/tests/test_stage1.py`
- `python -m json.tool cloud/task_088_ge_price_crm_stage1/evidence.json`

Stage boundary:
- only Gate A / Stage 1 CRM work is covered here;
- no Gate B preview or public rendering changes were started.
