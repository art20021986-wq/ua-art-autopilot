# GitHub / Control-Plane Hardening Package (TASK 012, Phase A)

All items below are proposals or checklists. None are applied automatically by this task. Applying workflow-file changes still requires a normal PR + owner/Codex review, exactly like any other repository change — this task only prepares the recommendations.

## 1. Repository visibility
- Keep `art20021986-wq/ua-art-autopilot` **PRIVATE**. Confirmed current state — no change needed.

## 2. Branch protection — staged, non-breaking migration
Current fact: `main` is NOT protected. Do not protect `main` in a way that blocks the existing Claude Autopilot bot commit path before a safe migration exists.

Recommended staged approach:
1. Create a new protected branch, e.g. `release` or `stable`, that mirrors the currently working `main` state. Protect only this branch first (no deletion, no force-push, require PR for humans). The Claude worker keeps writing to `main`/task branches unaffected.
2. Only after the Claude Autopilot bot identity/token is confirmed compatible with required PR reviews (or given a bot bypass explicitly configured by the owner in GitHub UI), consider adding equivalent protection to `main`.
3. Never enable "require signed commits" or "require linear history" until confirmed compatible with the bot's commit flow.

Minimum protection to request on the new `release`/`stable` branch (manual, GitHub UI):
- Restrict deletions.
- Restrict force pushes.
- Require pull request before merging (for human collaborators only, not the automation path).

## 3. Workflow least privilege
For every workflow file, the top-level (or job-level) `permissions:` block should be the minimum needed, for example:
```yaml
permissions:
  contents: write   # only if the job commits to cloud/ or tasks/
  actions: read
  # everything else implicitly none
```
Default at the workflow level should be `permissions: {}` (i.e. `read` only or none) with job-level overrides where a job genuinely needs `contents: write`. Do not grant `id-token`, `packages`, `deployments`, or `pull-requests` scopes unless a job specifically requires them.

## 4. Pin third-party Actions to immutable commit SHAs
Any hardened workflow revision should replace `uses: owner/action@vX` with a full 40-char commit SHA and a trailing comment recording the human version tag, e.g.:
```yaml
- uses: actions/checkout@<FULL_COMMIT_SHA>   # v4.1.7
```
This task does not know which exact Action versions are currently in use in the live workflow files (that file was not provided for this task), so exact SHAs are not fabricated here. The concrete pin values must be filled in by Codex/owner review at the time an existing workflow is edited, using the SHA of the exact tag currently referenced.

## 5. No secrets on command line or in logs
- Never pass `${{ secrets.* }}` as a bare CLI argument; use environment variables and mask them.
- Ensure no `echo`/`print` of any secret-bearing variable exists in workflow steps.
- Use `::add-mask::` if a computed value ever risks resembling a secret.

## 6. No untrusted PR code execution with secrets
- Any workflow triggered by `pull_request_target` or that grants secrets to fork PR code must not run untrusted code (`pull_request` from forks should use the default read-only, no-secret token only).
- Only allow the Claude Autopilot job to run on protected trigger types (`push` to task branches, `workflow_dispatch`, or `repository_dispatch` from the trusted owner/Codex path) — never on arbitrary fork PRs.

## 7. Concurrency lock
Add, per workflow that syncs/deploys:
```yaml
concurrency:
  group: uaart-inbox-sync
  cancel-in-progress: false
```
This prevents two overlapping quarantine syncs or two overlapping Claude runs from racing on the same files.

## 8. Artifact / source SHA verification
- Every file Claude produces should be listed with its own SHA-256 in the task's `cloud_report_0NN.md` and, where relevant, in a manifest JSON (see `security_release_manifest.example.json`).
- The PythonAnywhere Inbox Sync step should verify the SHA-256 of each synced file against the manifest before it is placed in quarantine, and refuse silently-changed content.

## 9. Preserve Claude-only provenance
- Only the Claude Autopilot worker identity should be allowed to write under `cloud/`. If GitHub CODEOWNERS is available on the current plan, add:
```
/cloud/ @art20021986-wq
```
as a manual reviewer-of-record entry (does not block automation, provides an audit trail for human PRs touching `cloud/`).

## 10. Preserve Gate A / Gate B separation
- No workflow in this repository may call any PythonAnywhere execution endpoint automatically.
- The only allowed automatic transport is "quarantine sync" (already verified working). Execution remains a manual, owner-approved, PythonAnywhere-side action bound to TASK_ID + manifest SHA + file SHA (Gate A), and any resulting production file change remains a second, separate owner approval (Gate B).

## 11. `SECURITY.md` proposal
See `SECURITY.md.proposed` — ready to place at repository root as `SECURITY.md` after owner/Codex review.

## 12. `.gitignore` / deny-policy proposal
See `gitignore_security.proposed` — ready to be merged into `.gitignore` after review. Covers databases, backups, tokens, env files, private keys, credentials, and customer exports.

## 13. Manual GitHub settings checklist (cannot be safely set from code)
- [ ] Enable 2FA / passkey requirement for the owner's GitHub account (Settings → Password and authentication).
- [ ] Enable 2FA requirement for the organization/repository collaborators, if any exist beyond the owner.
- [ ] Confirm repository visibility remains **Private** (Settings → General → Danger Zone).
- [ ] Review and restrict forking policy (Settings → General → Features → "Allow forking", should be OFF for a private repo with no external contributors).
- [ ] Add branch protection / ruleset on the new `release`/`stable` branch (Settings → Branches / Rules).
- [ ] Enable Dependabot alerts and security updates if available on current plan (Settings → Code security and analysis). Mark this **plan-dependent** — do not assume it is available; verify in the UI first.
- [ ] Enable secret scanning if available on current plan (also plan-dependent for private repos — verify before relying on it).
- [ ] Review the list of installed GitHub Apps / OAuth Apps with repo access (Settings → Integrations) and remove anything unrecognized.
- [ ] Confirm the PythonAnywhere API token used for quarantine sync is stored only as an encrypted repository/environment secret, never in a workflow file or committed file.

## Plan-dependent honesty note
This task does **not** assume the owner's GitHub plan includes Advanced Security features (secret scanning / push protection / code scanning) for a private repository. Those items above are explicitly marked plan-dependent and must be verified in the GitHub UI, not assumed present.
