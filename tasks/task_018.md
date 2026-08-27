# TASK 018 — Execute the TASK 017 code patch, no prose-only response

Continue TASK 014. TASK 017 is the authoritative specification and safety audit.

The previous Claude run failed with:
`CLAUDE_REQUIRED_OUTPUTS_MISSING:cloud/ua_cards_unified/`
because it returned analysis/text but did not modify files.

## Mandatory action

Use the repository editing tools and **actually modify files** under:
`cloud/ua_cards_unified/`

Patch the existing TASK 016 implementation; do not rewrite the specification and do not return a prose-only design.

At minimum, modify the existing runner/manifest/launcher and add a preflight utility so every TASK 017 requirement is implemented. Focus token budget on code. Keep owner reply concise.

Before finishing, run local syntax checks/tests possible in GitHub runner, then verify with `git status --short` that `cloud/ua_cards_unified/` contains real changes.

Required deliverables:
- corrected runner;
- corrected manifest builder;
- corrected no-argument restricted launcher;
- read-only preflight/audit utility;
- operator instructions;
- updated status and owner reply.

Safety remains Gate A only:
- no production writes;
- no synthetic UA-0001…UA-0008;
- any card failure blocks `AWAITING_GATE_B`;
- do not execute against PythonAnywhere in this task.

Read TASK 017 in full and implement it exactly. If token/time is constrained, produce a smaller correct auditable implementation rather than explanation.
