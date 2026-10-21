"""Create a local hash-bound cars_ui candidate; never install it."""
import argparse
import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE_SHA256 = 'd9bd8cb352ad95892f8ac2cddcce02898ec7f3f2fe5013f1a5007bf1469db837'


def apply_to_candidate(source):
    """Compose after caller verifies baseline hash and other approved edits.

    This function checks the exact old destructive handlers independently;
    public build_candidate also enforces the complete live baseline digest.
    """
    text = source.decode('utf-8')
    if 'UA-ART-CRM-DELETE-RECOVERY-002:BEGIN' in text:
        raise ValueError('Deletion adapter already present')
    tree = ast.parse(text)
    nodes = [node for node in tree.body if isinstance(node, ast.AsyncFunctionDef)
             and node.name in ('delete_ask', 'delete_ok')]
    if [node.name for node in nodes] != ['delete_ask', 'delete_ok']:
        raise ValueError('Unique original deletion handlers required')
    lines = text.splitlines(keepends=True)
    old = ''.join(lines[nodes[0].lineno - 1:nodes[-1].end_lineno])
    if hashlib.sha256(old.encode()).hexdigest() != OLD_HANDLERS_SHA256:
        raise ValueError('Deletion handler source changed; review required')
    replacement = (ROOT / 'replacement_handlers.py.txt').read_text().rstrip() + '\n'
    new_text = (''.join(lines[:nodes[0].lineno - 1]) + replacement +
                ''.join(lines[nodes[-1].end_lineno:]) + '\n\n' +
                (ROOT / 'register_block.py.txt').read_text())
    candidate = new_text.encode()
    compile(candidate, 'cars_ui.py.delete-candidate', 'exec')
    return candidate


OLD_HANDLERS_SHA256 = '8fdbba2b429bbd29034c45b7aae7d7974a74689efa1ecd20314d7284a4a2eb5a'


def build_candidate(source):
    if hashlib.sha256(source).hexdigest() != SOURCE_SHA256:
        raise ValueError('Source hash mismatch; review current cars_ui.py')
    return apply_to_candidate(source)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--destination', type=Path, required=True)
    args = parser.parse_args()
    if args.source.resolve() == args.destination.resolve():
        raise SystemExit('Source overwrite prohibited')
    candidate = build_candidate(args.source.read_bytes())
    with args.destination.open('xb') as stream:
        stream.write(candidate)
    print(json.dumps({'source_sha256': SOURCE_SHA256,
                      'candidate_sha256': hashlib.sha256(candidate).hexdigest(),
                      'installed': False, 'runtime_binding_required': 'ua_delete_runtime.create_coordinator'}))


if __name__ == '__main__':
    main()
