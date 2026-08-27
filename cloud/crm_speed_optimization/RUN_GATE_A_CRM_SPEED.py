#!/usr/bin/env python3
'''No-argument launcher for the CRM-SPEED-001 Gate A fail-closed runner.

Safe to repeat. Never writes to production. Writes only beneath
<source_base>/qa/crm_speed_task020/<run_id>/ and emits a JSON and Markdown
receipt there. Does not restart the bot, web app, or any process, and does
not publish UA-0009.

Usage on PythonAnywhere Bash (single command):
    python3 RUN_GATE_A_CRM_SPEED.py
'''

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from crm_speed_gate_a import run_gate_a  # noqa: E402


def main():
    receipt = run_gate_a()
    status = receipt.get('status', 'BLOCKED')
    print('CRM-SPEED-001 Gate A run_id: ' + str(receipt.get('run_id')))
    print('CRM-SPEED-001 Gate A status: ' + str(status))
    for blocker in receipt.get('blockers', []):
        print('  BLOCKER: ' + str(blocker))
    print('PRODUCTION_WRITE: ' + str(receipt.get('production_write', 'NO')))
    if status == 'GATE_A_PASS_AWAITING_PRODUCTION_APPROVAL':
        return 0
    return 1


if __name__ == '__main__':
    sys.exit(main())
