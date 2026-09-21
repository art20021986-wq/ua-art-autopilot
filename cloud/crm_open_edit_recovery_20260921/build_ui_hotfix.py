"""Build a private cars_ui candidate; never import or install the source."""
import argparse
import ast
import hashlib
from pathlib import Path

SOURCE_SHA256 = 'd9bd8cb352ad95892f8ac2cddcce02898ec7f3f2fe5013f1a5007bf1469db837'
FUNCTIONS = {'open_card', 'edit_menu', 'edit_ask'}


def build(source):
    if hashlib.sha256(source).hexdigest() != SOURCE_SHA256:
        raise ValueError('Source hash mismatch; fresh review is required')
    text = source.decode('utf-8')
    lines = text.splitlines(keepends=True)
    tree = ast.parse(text)
    replacements = [n for n in tree.body if isinstance(n, ast.AsyncFunctionDef)
                    and n.name in FUNCTIONS]
    if len(replacements) != 3 or {n.name for n in replacements} != FUNCTIONS:
        raise ValueError('Unexpected handler topology')
    block = Path(__file__).with_name('ui_hotfix_block.py.txt').read_text('utf-8')
    ast.parse(block)
    first = min(n.lineno for n in replacements)
    for node in sorted(replacements, key=lambda n: n.lineno, reverse=True):
        lines[node.lineno - 1:node.end_lineno] = [block + '\n' if node.lineno == first else '']
    result = ''.join(lines).encode('utf-8')
    compile(result, '<cars_ui.candidate>', 'exec')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve():
        parser.error('Source and output must differ')
    output = build(args.source.read_bytes())
    with args.output.open('xb') as file:
        file.write(output)
    print('candidate_sha256=' + hashlib.sha256(output).hexdigest())
