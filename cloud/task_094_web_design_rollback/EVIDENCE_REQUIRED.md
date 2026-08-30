# Evidence required before Phase B may run (TASK 094)

Per the fail-closed rule, restore_controller.py hard-refuses to run unless every target in
`restore_map.json` is `VERIFIED_READY` with real hashes copied from a real
`audit_report.json`. This file lists exactly what evidence must exist first.

1. `audit_report.json` produced by an actual run of `forensic_audit.py` against the live
   `/home/Carix` filesystem (not fabricated, not copied from this report).
2. Confirmation of which TASK 086 backup (if any) contains the last approved catalog/card
   presentation, with its SHA-256 taken directly from `audit_report.json`.
3. Confirmation that the TASK 093 pre-write backup at
   `/home/Carix/backups/task_093_home_counters/20260830T010212Z_7e621e5028` matches the
   publicly recorded preimage hash exactly, re-derived by the audit script itself (the task
   text's hash string must be treated as a claim to verify, not a fact to trust).
4. A completed `restore_map.json` (based on `restore_map.template.json`) with every target's
   `status` set to `VERIFIED_READY` only after a human/ChatGPT-Codex reviewer has confirmed the
   selected backup is structurally correct (contains the four-stage Kyiv/Georgia/Ferry/Korea
   order and the image-above/text-below mobile card composition) by direct inspection of the
   backup file content, not by inference.
5. Confirmation that current live counts (13 / 3 / 1 / 7 / 2) and UA-0001..UA-0013
   (including UA-0011 on Ferry) are unaffected by the presentation-only restore, i.e. that the
   selected backup's data-bearing markup (IDs, stage assignment, counts) is either identical to
   current production or that the controller's post-restore re-apply step for counts is
   exercised and evidenced.

Until all five items exist as real, dated artifacts, `restore_controller.py` will refuse to
write, by design. This is intentional and is not a bug.
