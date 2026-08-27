#!/usr/bin/env python3
"""
RUN_GATE_A_CRM_SPEED.py

No-argument PythonAnywhere Bash launcher for CRM-SPEED-001 Gate A.
Safe to repeat. Never writes outside /home/Carix/qa/crm_speed_task020.
Never touches production files, the live database's mutable state, the
CRM bot, the site, or UA-0009 publication state. Returns nonzero on
BLOCKED.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from crm_speed_gate_a import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
