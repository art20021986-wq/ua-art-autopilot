"""Exact rollback operation for the existing CRITICAL dispatcher."""
from controller import main


if __name__ == '__main__':
    raise SystemExit(main('rollback'))
