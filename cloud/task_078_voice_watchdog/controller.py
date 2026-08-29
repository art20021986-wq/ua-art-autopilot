"""Supervisor detection + restart-budget controller.

Used only to decide whether a full Telegram-process restart is even
admissible. Per task_078 rule 7: full-process restart is allowed only if a
GET audit proves an actual supervisor exists; otherwise only the STT worker
is restarted, and os._exit is never called from this codebase.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .circuit_breaker import ProcessRestartBudget

EXIT_CODE_SUPERVISOR_RESTART = 75


@dataclass
class SupervisorAuditResult:
    supervisor_confirmed: bool
    supervisor_kind: Optional[str] = None  # e.g. "systemd", "pa_always_on", None
    evidence_source: Optional[str] = None


class RestartDecisionController:
    """Decides restart action; never itself calls os._exit or performs a
    live restart. It only returns a decision string for the caller/operator
    to act on, and only after Gate A confirms a supervisor.
    """

    def __init__(self, audit: SupervisorAuditResult, budget: Optional[ProcessRestartBudget] = None):
        self._audit = audit
        self._budget = budget or ProcessRestartBudget()

    def record_health_probe(self, healthy: bool) -> None:
        self._budget.record_health_probe(healthy)

    def decide(self) -> str:
        """Returns one of:
        - 'restart_stt_worker_only'  (always safe, default)
        - 'exit_for_supervisor_restart'  (only if supervisor confirmed AND
           budget/probe conditions are satisfied)
        - 'no_action'
        """
        if not self._audit.supervisor_confirmed:
            return "restart_stt_worker_only"
        if not self._budget.probes_justify_restart():
            return "restart_stt_worker_only"
        if not self._budget.may_restart():
            return "restart_stt_worker_only"
        return "exit_for_supervisor_restart"

    def commit_restart_decision(self) -> None:
        """Call only after 'exit_for_supervisor_restart' AND owner-approved
        Gate B. This method itself intentionally performs no process exit;
        it only records the restart in the budget so limits are enforced.
        The actual `sys.exit(EXIT_CODE_SUPERVISOR_RESTART)` call must live in
        the real, owner-approved deployment code, not in this sandbox
        package, and only after supervisor + budget are independently
        reverified at apply time.
        """
        self._budget.record_restart()
