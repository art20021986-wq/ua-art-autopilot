#!/usr/bin/env python3
'''Offline validator for a CRM-SPEED-001 Gate A receipt.json.

Does not touch production. Reads a receipt file produced by
crm_speed_gate_a.run_gate_a and checks the required fields and booleans
listed in the CRM-SPEED-001 specification.
'''

import json
import sys

REQUIRED_TRUE_KEYS_FOR_PASS = [
    'inputs_resolved_ok',
    'backup_verified_ok',
    'all_core_candidates_ok',
    'all_candidates_compile_ok',
    'cars_ui_text_only_ok',
    'avtoperedacha_no_subprocess_ok',
    'singleton_guard_ok',
    'deterministic_repeat_ok',
    'ua0009_inspection_ok',
    'synthetic_latency_ok',
    'protected_inputs_unchanged',
]


def load_receipt(path):
    with open(path, 'r', encoding='utf-8') as fh:
        return json.load(fh)


def verify(receipt):
    problems = []
    checks = receipt.get('checks', {})
    for key in REQUIRED_TRUE_KEYS_FOR_PASS:
        if checks.get(key) is not True:
            problems.append('check_not_true:' + key)
    if receipt.get('production_write') != 'NO':
        problems.append('production_write_not_NO')
    status = receipt.get('status')
    if not problems and status != 'GATE_A_PASS_AWAITING_PRODUCTION_APPROVAL':
        problems.append('unexpected_status_for_clean_checks:' + str(status))
    if problems and status not in ('BLOCKED',):
        problems.append('status_should_be_BLOCKED_but_is:' + str(status))
    return problems


def main(argv):
    if len(argv) != 2:
        print('Usage: verify_gate_a.py <receipt.json>')
        return 2
    receipt = load_receipt(argv[1])
    problems = verify(receipt)
    if problems:
        print('BLOCKED OR INVALID RECEIPT:')
        for p in problems:
            print(' - ' + p)
        return 1
    print('Receipt OK: GATE_A_PASS_AWAITING_PRODUCTION_APPROVAL')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
