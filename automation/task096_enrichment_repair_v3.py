#!/usr/bin/env python3
"""TASK096 repair v3: compatibility-loader for the approved enrichment controller."""
from __future__ import annotations

import pathlib
import sys
import types

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / "automation/task096_data_enrichment_controller.py"
MODULE_NAME = "task096_data_enrichment_controller"


def load_fixed_controller():
    source = SOURCE.read_text(encoding="utf-8")
    bad = '{"\\n\\n".join(source_blocks)}'
    if bad in source:
        source = source.replace(
            '    prompt = f"""You are extracting additional technical specifications for one vehicle into a closed sandbox.',
            '    source_text = "\\n\\n".join(source_blocks)\n    prompt = f"""You are extracting additional technical specifications for one vehicle into a closed sandbox.',
            1,
        )
        source = source.replace(bad, '{source_text}', 1)
    module = types.ModuleType(MODULE_NAME)
    module.__file__ = str(SOURCE)
    sys.modules[MODULE_NAME] = module
    code = compile(source, str(SOURCE), "exec")
    exec(code, module.__dict__)
    return module


def main() -> int:
    load_fixed_controller()
    import task096_enrichment_repair_v2 as repair
    return repair.main()


if __name__ == "__main__":
    raise SystemExit(main())
