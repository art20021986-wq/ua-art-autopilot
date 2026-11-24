"""Bind the standard production backup phase."""
import os
from deployment_controller import run

if __name__ == '__main__':
    if os.environ.get('UAART_OPERATION') != 'backup':
        raise SystemExit('OPERATION_SCOPE')
    raise SystemExit(run('backup'))
