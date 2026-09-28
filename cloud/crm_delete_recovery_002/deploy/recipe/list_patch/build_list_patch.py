"""Build a hash-bound local candidate; never install or overwrite the input."""
import argparse
import hashlib
import json
from pathlib import Path

SOURCE_SHA256 = 'd9bd8cb352ad95892f8ac2cddcce02898ec7f3f2fe5013f1a5007bf1469db837'
START = b'# UA-ART-CRM-CATALOG-FOLDERS-001:START'
END = b'# UA-ART-CRM-CATALOG-FOLDERS-001:END'
ROOT = Path(__file__).resolve().parent


def build_candidate(source):
    if hashlib.sha256(source).hexdigest() != SOURCE_SHA256:
        raise ValueError('Source hash mismatch; re-review the current cars_ui.py')
    if source.count(START) != 1 or source.count(END) != 1:
        raise ValueError('Folder block markers are not unique')
    start = source.index(START)
    end = source.index(END, start) + len(END)
    replacement = (ROOT / 'replacement_block.py.txt').read_bytes().rstrip(b'\n')
    if not replacement.startswith(START) or not replacement.endswith(END):
        raise ValueError('Invalid replacement boundaries')
    candidate = source[:start] + replacement + source[end:]
    compile(candidate, 'cars_ui.py.candidate', 'exec')
    return candidate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--destination', required=True, type=Path)
    args = parser.parse_args()
    if args.source.resolve() == args.destination.resolve():
        raise SystemExit('Refusing to overwrite the source')
    candidate = build_candidate(args.source.read_bytes())
    # Exclusive create prevents silently replacing another executor's candidate.
    with args.destination.open('xb') as output:
        output.write(candidate)
    print(json.dumps({
        'source_sha256': SOURCE_SHA256,
        'candidate_sha256': hashlib.sha256(candidate).hexdigest(),
        'helper_sha256': hashlib.sha256((ROOT / 'ua_crm_resilient_list.py').read_bytes()).hexdigest(),
        'changed_region': 'UA-ART-CRM-CATALOG-FOLDERS-001',
        'source_preserved': True,
        'installed': False,
    }, sort_keys=True))


if __name__ == '__main__':
    main()
