# RISK REGISTER — TASK105

| ID | Risk | Evidence | Severity | Control |
|---|---|---|---|---|
| R1 | False `FINISHED` | Multiple intermediate completion vocabularies | Critical | Receipt-gated final state |
| R2 | Hidden production writer | 107 workflows heuristically production-capable | Critical | Explicit capability manifest + deny-by-default |
| R3 | PythonAnywhere transport drift | 109 workflows reference PythonAnywhere | High | One transport adapter with immutable SHA |
| R4 | Excess AI cost/latency | 22 workflows reference Anthropic/Claude | High | AI router and per-task budgets |
| R5 | Global serialization | Shared queue patterns can block unrelated resources | High | Resource-aware locks |
| R6 | Retry storm | Versioned retry/recovery workflows exist | High | Transient allowlist, bounded retries, ROOT_CAUSE_MODE |
| R7 | Workflow cleanup breaks recovery | Many task-specific workflows may still be rollback paths | High | Archive first; delete only after dependency proof |
| R8 | New orchestrator misclassifies risk | Rule-based classifier may under-rank a change | Critical | Conservative default + protected-path escalation |
| R9 | Token/secret exposure | Multiple automation layers consume credentials | Critical | Least privilege, no secret logging, no PR secrets |
| R10 | Migration changes production too early | Pressure to speed up may bypass canary | Critical | Shadow mode and owner-controlled production gate |

## Safety conclusion

Speed must come from eliminating duplicated orchestration and unnecessary AI, not by removing
backup, protected-path validation, live verification or rollback.
