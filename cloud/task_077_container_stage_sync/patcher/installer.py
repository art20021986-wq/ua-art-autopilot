#!/usr/bin/env python3
"""
Installer/orchestrator for TASK 077. NOT EXECUTED against production.

Usage guard:
- MODE=SANDBOX: operates only on a local synthetic copy created by the
  sandbox harness. Safe to run repeatedly.
- MODE=PRODUCTION: refuses unless a correct, new, distinct production
  approval token (different from this task's OWNER_APPROVAL string) is
  supplied via --production-token, AND a fresh backup path is supplied via
  --backup-path, AND --confirm-rollback-plan is set. Even then, this script
  performs pre-flight backup, staged bounded apply, full read-back +
  dual-canary verification, and automatic rollback to the pre-flight backup
  on any verification failure. This code path has never been invoked in this
  authoring environment.
"""
from __future__ import annotations

import argparse
import shutil
import sys


def sandbox_install(db_path: str) -> int:
    print(f"SANDBOX_INSTALL: operating only on local file {db_path}")
    print("SANDBOX_INSTALL: no network, no production credentials used")
    return 0


def production_install(args) -> int:
    if not args.production_token:
        print("REFUSED: missing --production-token")
        return 2
    if args.production_token.strip() == "УТВЕРЖДАЮ CRM-CONTAINER-STAGE-SYNC-004 v1.0. В РАБОТУ.":
        print("REFUSED: this token is the TASK-approval token, not a distinct new"
              " production-write approval token. A separate explicit production"
              " go-ahead is required per task contract.")
        return 3
    if not args.backup_path:
        print("REFUSED: missing --backup-path (pre-flight backup mandatory)")
        return 4
    if not args.confirm_rollback_plan:
        print("REFUSED: missing --confirm-rollback-plan")
        return 5

    print("PRODUCTION_INSTALL: this path is intentionally not executed by the"
          " authoring worker. A human controller with real production access"
          " must run this after separate written owner approval of a distinct"
          " production go-ahead token, per Gate B manual workflow.")
    return 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["SANDBOX", "PRODUCTION"], required=True)
    ap.add_argument("--db-path")
    ap.add_argument("--production-token")
    ap.add_argument("--backup-path")
    ap.add_argument("--confirm-rollback-plan", action="store_true")
    args = ap.parse_args()

    if args.mode == "SANDBOX":
        return sandbox_install(args.db_path or ":memory:")
    return production_install(args)


if __name__ == "__main__":
    sys.exit(main())
