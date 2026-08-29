# TASK 081 — UA-0013-PUBLISH-REPAIR-001 v1.0

Актуальный путь: **V2**. Свежий secret-backed GET-only аудит выполнен,
live-дефект воспроизведён, release candidate и внешний rollback прошли Gate A.
Подробные факты и точный production handoff: `RELEASE_STATUS_V2.md`.

## Разрешённые entrypoints

- `live_audit_v2.py` — только GET, точные live SHA/functions/CRM/public state.
- `patcher_v2.py` — чистые bounded AST/SHA transforms пяти live-файлов.
- `test_release_candidate_v2.py` — UI/publisher/SEO/future-card/fault tests.
- `test_gate_b_v2.py` — bounded target discovery и внешний backup/rollback.
- `gate_a_v2.py` — итог `PASS_READY_FOR_SEPARATE_PRODUCTION_APPROVAL`.
- `gate_b_installer_v2.py`, `gate_b_controller_v2.py`, `postcheck_v2.py` —
  только для отдельно разрешённого manual Gate B.

Workflows:

- `.github/workflows/task081_publish_repair_live_audit_v2.yml`
- `.github/workflows/task081_publish_repair_gate_b_v2.yml`

## Важное

Первый fixture-only комплект (`controller.py`, `installer.py`,
`gate_a_workflow.yml`, `gate_b_workflow.yml`) не имеет live-якорей и не является
release path. Старый `patcher.py` заменён безопасным compatibility shim и не
разрешает прямую установку.

Production Gate B требует точное отдельное подтверждение:

`UA-0013-PUBLISH-REPAIR-001-V1.0-PRODUCTION-APPROVED`

Без него workflow останавливается до доступа к секретам и до любых записей.
