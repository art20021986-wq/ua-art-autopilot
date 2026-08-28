# TASK 072 — Production Gate B plan

Gate B is prepared but intentionally not started.

It can run only by manual `workflow_dispatch` with the exact separate owner approval
`TASK_072_GATE_B_APPROVED`. There is no push trigger.

The approved run will:

1. Revalidate the complete Gate A evidence and current live SHA.
2. Refuse to overlap another production workflow.
3. Run a read-only shadow against `cars_ui.py` and `crm.db`.
4. Back up the current `cars_ui.py` and any prior standalone writer.
5. Atomically install the standalone writer, then the guarded `cars_ui.py` patch.
6. Verify that `crm.db`, all 11 cards, UA-0009 and the durable queue did not change.
7. Restart only the existing CRM launcher.
8. Test all 11 cards through the installed writer on a consistent temporary DB clone.
9. Repeat the postcheck after a delay.
10. Automatically restore the code backup and restart the bot if any postcheck fails.

Rollback is code-only. It never deletes or rewrites the durable description queue and
never restores an old `crm.db`, so accepted user descriptions cannot be lost by rollback.

