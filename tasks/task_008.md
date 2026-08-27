# TASK 008 — CLAUDE-ONLY OWNER DELIVERABLE PROVENANCE LOCK

MODE: READ_ONLY
MAX_ROUNDS: 1

## Owner directive

The owner has explicitly approved a strict provenance rule: every executable, script, patch, specification, report, archive content, or other technical deliverable presented to the owner as a working project file must originate from Claude through the Anthropic API worker. ChatGPT/Codex may create task specifications under `tasks/`, audit Claude outputs, manage orchestration/infrastructure, and relay verified results, but must not substitute its own technical deliverable and label it as Claude output.

The ordinary Claude Chat UI and the Anthropic API worker are separate sessions. Do not claim shared chat memory. The durable shared handoff is GitHub.

## Required provenance rule

For every future owner-facing technical deliverable under `cloud/`:

1. It must be returned by the Anthropic API response handled by `automation/claude_worker.py`.
2. It must be written under `cloud/` by that worker and committed by the `Claude Autopilot` GitHub Actions job.
3. ChatGPT/Codex must verify the relevant successful Actions run and commit before telling the owner that the file is from Claude.
4. If provenance cannot be verified, the file must be described as UNVERIFIED and must not be given to the owner as a Claude deliverable.
5. Never claim that the ordinary Claude Chat UI authored an API-worker file.
6. Never claim that the API worker shares memory with the ordinary Claude Chat UI.

## Scope

This task only records and acknowledges the provenance policy. Do not access or modify PythonAnywhere, CRM, UA ART production, cards, media, or website files. Do not publish anything.

## Deliverables

1. `cloud/claude_provenance_lock.md`
2. `cloud/owner_reply.md`
3. `cloud/latest_status.md`

## Required owner reply

In clear Russian, confirm:

- the strict Claude-only deliverable provenance rule is accepted;
- Claude received TASK 008 through the GitHub/Anthropic API bridge;
- ChatGPT/Codex is only the task/orchestration/audit layer for owner-facing Claude deliverables;
- the ordinary Claude Chat UI remains a separate session unless the owner separately connects that UI to GitHub;
- no production, CRM, PythonAnywhere, or website changes were made;
- no owner action is required for this policy acknowledgement.

## Acceptance

- CLAUDE_STATUS: DONE
- All three deliverables exist under `cloud/`.
- No paths outside `cloud/` are written by Claude.
- PRODUCTION_TOUCHED: NO
- OWNER_ACTION_REQUIRED: NO
