#!/usr/bin/env python3
"""UA-ART-HOME-TOTAL-AUTO-001: change only the homepage total and its updater."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from urllib.parse import urlsplit

CONTRACT = "UA-ART-HOME-TOTAL-AUTO-001"
START = "<!-- UA-HOME-TOTAL-AUTO-001:START -->"
END = "<!-- UA-HOME-TOTAL-AUTO-001:END -->"
ID_RE = re.compile(r"UA-[0-9]{4,}", re.I)
CTA_RE = re.compile(
    r'<i\b(?=[^>]*\bdata-ru\s*=\s*["\']Открыть все автомобили · \d+["\'])'
    r'[^>]*>[^<]*</i\s*>', re.I | re.S)
OLD_WRITE = 'if (cta && typeof total === "number") {'
OWNED_WRITE = 'if (cta && typeof total === "number" && !cta.hasAttribute("data-ua-home-total")) {'


class TotalError(ValueError):
    pass


class CatalogParser(HTMLParser):
    """Count card identities, never stage labels or unrelated page links."""
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input",
            "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self, origin: str):
        super().__init__(convert_charrefs=True)
        self.origin = origin
        self.stack = []
        self.cards = []
        self.current = None
        self.grid = False
        self.complete = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = (attrs.get("class") or "").split()
        self.grid |= "catalog-grid" in classes
        if self.current is None and (
            tag == "article" and "catalog-card" in classes
            or tag == "a" and "data-ua-card" in attrs
        ):
            self.current = {"depth": len(self.stack), "ids": set()}
        if self.current is not None:
            for key in ("data-ua-card", "data-ua"):
                value = (attrs.get(key) or "").strip().upper()
                if value:
                    if not ID_RE.fullmatch(value):
                        raise TotalError("INVALID_CARD_ID")
                    self.current["ids"].add(value)
            if tag == "a" and attrs.get("href"):
                url = urlsplit(attrs["href"])
                if not url.netloc or url.netloc == self.origin:
                    match = re.fullmatch(r"(UA-[0-9]{4,})\.html", url.path.rsplit("/", 1)[-1], re.I)
                    if match:
                        self.current["ids"].add(match.group(1).upper())
        if tag not in self.VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag == "html":
            self.complete = True
        if tag not in self.stack:
            return
        pos = len(self.stack) - 1 - self.stack[::-1].index(tag)
        del self.stack[pos:]
        if self.current is not None and len(self.stack) <= self.current["depth"]:
            ids = self.current["ids"]
            if len(ids) != 1:
                raise TotalError("MISSING_OR_CONFLICTING_CARD_ID")
            self.cards.append(next(iter(ids)))
            self.current = None


def catalog_ids(source: str, origin: str) -> tuple[str, ...]:
    parser = CatalogParser(origin)
    parser.feed(source)
    parser.close()
    if not parser.complete or parser.current is not None:
        raise TotalError("INCOMPLETE_CATALOG")
    if not parser.grid and not parser.cards:
        raise TotalError("CATALOG_STRUCTURE_MISSING")
    return tuple(sorted(set(parser.cards)))


def patch_home_total(source: str, total: int) -> str:
    if type(total) is not int or total < 0:
        raise TotalError("INVALID_TOTAL")
    matches = list(CTA_RE.finditer(source))
    if len(matches) != 1:
        raise TotalError("TOTAL_CTA_NOT_UNIQUE")
    match = matches[0]
    block = match.group()
    for language, label in (("ru", "Открыть все автомобили"), ("uk", "Відкрити всі автомобілі")):
        pattern = re.compile(r'(\bdata-' + language + r'\s*=\s*(["\']))' + re.escape(label) + r' · \d+\2')
        block, changed = pattern.subn(lambda m: m[1] + label + " · " + str(total) + m[2], block)
        if changed != 1:
            raise TotalError("CTA_LANGUAGE_ATTRIBUTE:" + language)
    block, changed = re.subn(r'>(Открыть все автомобили|Відкрити всі автомобілі) · \d+</i',
                            lambda m: ">" + m[1] + " · " + str(total) + "</i", block)
    if changed != 1:
        raise TotalError("CTA_TEXT_UNEXPECTED")
    if "data-ua-home-total=" not in block:
        block = block.replace("<i", '<i data-ua-home-total="v1"', 1)
    result = source[:match.start()] + block + source[match.end():]
    # Preserve the legacy stage writer, but give this fragment one total writer.
    if 'id="ua-home-stage-counter-sync-v1"' in result:
        if result.count(OLD_WRITE) == 1 and OWNED_WRITE not in result:
            result = result.replace(OLD_WRITE, OWNED_WRITE, 1)
        elif result.count(OWNED_WRITE) != 1:
            raise TotalError("UNRECOGNIZED_EXISTING_TOTAL_WRITER")
    js = Path(__file__).with_name("home_total.js").read_text(encoding="utf-8")
    script = START + '\n<script id="ua-home-total-auto-v1">\n' + js.rstrip() + "\n</script>\n" + END
    region = re.compile(re.escape(START) + r".*?" + re.escape(END), re.S)
    if START in result or END in result:
        if result.count(START) != 1 or result.count(END) != 1 or not region.search(result):
            raise TotalError("TOTAL_SCRIPT_REGION_INVALID")
        result = region.sub(lambda _: script, result, count=1)
    else:
        ends = list(re.finditer(r"</body\s*>", result, re.I))
        if len(ends) != 1:
            raise TotalError("BODY_NOT_UNIQUE")
        result = result[:ends[0].start()] + script + "\n" + result[ends[0].start():]
    return result


def atomic(path: Path, content: bytes, mode: int) -> None:
    handle, name = tempfile.mkstemp(dir=path.parent, prefix=".home-total-")
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(name, mode)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--home", type=Path, required=True)
    p.add_argument("--catalog", type=Path, required=True)
    p.add_argument("--catalog-origin", required=True, help="Verified public catalogue hostname")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--expected-home-sha256")
    p.add_argument("--expected-catalog-sha256")
    p.add_argument("--lock-file", type=Path, help="Verified existing publication writer lock")
    args = p.parse_args()
    lock = None
    if args.apply:
        if not args.lock_file or not args.lock_file.is_file() or args.lock_file.is_symlink():
            raise TotalError("EXISTING_PUBLICATION_LOCK_REQUIRED")
        lock = args.lock_file.open("r+")
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    if args.home.is_symlink() or args.catalog.is_symlink():
        raise TotalError("SYMLINK_TARGET")
    if args.home.resolve() == args.catalog.resolve():
        raise TotalError("HOME_IS_CATALOG")
    before = args.home.read_bytes()
    catalog = args.catalog.read_bytes()
    sha = lambda b: hashlib.sha256(b).hexdigest()
    ids = catalog_ids(catalog.decode("utf-8"), args.catalog_origin)
    after = patch_home_total(before.decode("utf-8"), len(ids)).encode("utf-8")
    report = {"contract": CONTRACT, "mode": "PLAN", "total": len(ids), "ids": ids,
              "home_sha256": sha(before), "catalog_sha256": sha(catalog), "candidate_sha256": sha(after)}
    if args.apply:
        if not args.expected_home_sha256 or not args.expected_catalog_sha256:
            raise TotalError("EXPECTED_PREIMAGE_HASHES_REQUIRED")
        if sha(before) != args.expected_home_sha256 or sha(catalog) != args.expected_catalog_sha256:
            raise TotalError("PREIMAGE_MISMATCH")
        if args.home.read_bytes() != before or args.catalog.read_bytes() != catalog:
            raise TotalError("SOURCE_CHANGED")
        backup = args.home.with_name(args.home.name + ".home-total-" + sha(before)[:16] + ".bak")
        if backup.exists() and backup.read_bytes() != before:
            raise TotalError("BACKUP_CONFLICT")
        if not backup.exists():
            shutil.copy2(args.home, backup)
        mode = args.home.stat().st_mode & 0o777
        atomic(args.home, after, mode)
        if args.home.read_bytes() != after or args.catalog.read_bytes() != catalog:
            if args.home.read_bytes() == after:
                atomic(args.home, before, mode)
            raise TotalError("POST_WRITE_CONFLICT")
        report.update(mode="APPLIED", backup=str(backup))
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
