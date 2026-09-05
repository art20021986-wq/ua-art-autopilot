#!/usr/bin/env python3
from __future__ import annotations

import pathlib
import tempfile

import remote_installer as target


def main() -> int:
    target.self_test()
    assert target.external_hosts("<a href='https://wa.me/1'>x</a>") == {"wa.me"}
    assert not (target.external_hosts("<a href='/video/UA-0001.html'>x</a>") - target.APPROVED_HOSTS)
    assert target.external_hosts("<a href='https://ads.example/x'>x</a>") - target.APPROVED_HOSTS == {"ads.example"}
    fixture = "A" + target.ADD_START + "SPEC" + target.ADD_END + "B"
    assert target.canonical(fixture) == "AB"
    for path in (pathlib.Path(__file__).with_name("remote_installer.py"), pathlib.Path(__file__).with_name("controller.py")):
        compile(path.read_text(encoding="utf-8"), str(path), "exec")
    print("TASK115_CONTRACT_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
