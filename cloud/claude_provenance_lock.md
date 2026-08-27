# CLAUDE-ONLY OWNER DELIVERABLE PROVENANCE LOCK

TASK: task_008
STATUS: ACKNOWLEDGED AND ACCEPTED

## Policy recorded

This document records acceptance of the owner-approved strict provenance rule for all future owner-facing technical deliverables placed under `cloud/`.

1. Every executable, script, patch, specification, report, archive content, or other technical deliverable presented to the owner as a working project file must originate from Claude through the Anthropic API worker (the process that receives task content and returns a response handled by `automation/claude_worker.py`).
2. ChatGPT/Codex may create task specifications under `tasks/`, audit Claude outputs, manage orchestration/infrastructure, and relay verified results — but must never substitute its own technical deliverable and label it as Claude output.
3. Every such deliverable must be written under `cloud/` by the Anthropic API worker and committed by the `Claude Autopilot` GitHub Actions job.
4. ChatGPT/Codex must verify the relevant successful Actions run and commit before telling the owner that a file is from Claude.
5. If provenance cannot be verified, the file must be labeled UNVERIFIED and must not be presented to the owner as a Claude deliverable.
6. The ordinary Claude Chat UI and the Anthropic API worker are separate sessions with no shared memory. Nothing produced in the ordinary Claude Chat UI may be claimed as authored by the API worker, and vice versa, unless the owner explicitly connects the Chat UI to this GitHub bridge.
7. The durable shared handoff between ChatGPT/Codex and Claude is GitHub: the newest task under `tasks/`, `cloud/latest_status.md`, `cloud/owner_reply.md`, and detailed reports under `cloud/`.

## Scope confirmation for this task

- No PythonAnywhere, CRM, UA ART production, cards, media, or website files were accessed or modified.
- No publishing action was performed.
- This task only records and acknowledges the provenance policy above.

## Effective

This policy applies to all future tasks processed through this repository's Claude worker pipeline, starting with task_008.
