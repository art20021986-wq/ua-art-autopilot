# ORDER-PROCESS-001 — код сотрудника без ограничения по времени

Владелец 2026-11-05: код из «Сотрудников» работает, пока не использован, без срока. Меняется только
`ua_staff_invite.py` (установлен CRM-INVITE-INSTALL-20261105); охрана `bezopasnost.py` не меняется.
Тесты: `test_staff_invite.py`, `test_deployment.py`.
