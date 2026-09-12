"""Build a Stage 2 candidate in memory; never install or import live source."""
import ast
import hashlib
from pathlib import Path

EXPECTED_SOURCE_SHA256 = '76d0a16e7a22940c6699293cf356a6cdba08bb76565bfdcd9b1c66d214b1fee4'
TARGETS = ('apply_value', 'auto_catch', 'catch_message')
HELPERS = ('_task088_ge_number', '_task088_apply_selected_price')


class Refused(ValueError):
    pass


def digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def unique(items, name):
    items = list(items)
    if len(items) != 1:
        raise Refused('ANCHOR_COUNT:' + name)
    return items[0]


def function(source, name):
    return unique((n for n in ast.parse(source).body
                   if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name), name)


def insert_start(source, name, branch):
    node = function(source, name)
    first = node.body[0]
    if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
        first = node.body[1]
    lines = source.splitlines(keepends=True)
    lines.insert(first.lineno - 1, branch)
    return ''.join(lines)


def build_candidate(source, *, expected_sha256=EXPECTED_SOURCE_SHA256):
    if digest(source) != expected_sha256:
        raise Refused('LIVE_SOURCE_SHA_MISMATCH')
    before_tree = ast.parse(source)
    if any(n.name in HELPERS for n in before_tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))):
        raise Refused('PARTIAL_OR_EXISTING_STAGE2')
    editable = unique((n for n in before_tree.body if isinstance(n, ast.Assign)
                       and any(isinstance(t, ast.Name) and t.id == 'EDITABLE' for t in n.targets)), 'EDITABLE')
    prices = [item for item in ast.literal_eval(editable.value) if item[0] in ('price_uah', 'price_georgia')]
    if prices != [('price_uah', 'Цена Украины'), ('price_georgia', 'Цена Грузии')]:
        raise Refused('STAGE1_PRICE_BINDINGS_REQUIRED')
    node = function(source, 'apply_value')
    if [arg.arg for arg in node.args.args] != ['card_id', 'field', 'raw', 'actor_id']:
        raise Refused('APPLY_SIGNATURE_DRIFT')
    original = source
    source = insert_start(source, 'apply_value',
        '    if field == "price_georgia":\n'
        '        return _task088_apply_selected_price(card_id, field, raw, actor_id)\n')
    source = insert_start(source, 'auto_catch',
        '    if (context.user_data.get("car_wait") or {}).get("field") in ("price_uah", "price_georgia"):\n'
        '        return False\n')
    catch = function(source, 'catch_message')
    no_wait = unique((n for n in catch.body if isinstance(n, ast.If)
                     and isinstance(n.test, ast.UnaryOp) and isinstance(n.test.op, ast.Not)
                     and isinstance(n.test.operand, ast.Name) and n.test.operand.id == 'wait'), 'CATCH_NOT_WAIT')
    prefix = '\n'.join(source.splitlines()[catch.lineno - 1:no_wait.lineno - 1])
    for anchor in ('input_text =', 'thinking =', 'wait = context.user_data.get("car_wait")'):
        if anchor not in prefix:
            raise Refused('CATCH_INPUT_ANCHOR:' + anchor)
    branch = '''    # TASK088_STAGE2_EXPLICIT_MARKET: preserve the selected field before general parsing.
    if wait and not wait.get("client") and wait.get("field") in ("price_uah", "price_georgia") and input_text:
        ok, answer = _task088_apply_selected_price(wait["card_id"], wait["field"], input_text, user_id)
        if ok:
            context.user_data.pop("car_wait", None)
        rows = [[InlineKeyboardButton("← Вернуться к карточке", callback_data="car_open:%d" % wait["card_id"])]]
        if thinking:
            await thinking.edit_text(answer, reply_markup=InlineKeyboardMarkup(rows))
        else:
            await msg.reply_text(answer, reply_markup=InlineKeyboardMarkup(rows))
        raise ApplicationHandlerStop
'''
    lines = source.splitlines(keepends=True)
    lines.insert(no_wait.lineno - 1, branch)
    source = ''.join(lines)
    helper_file = Path(__file__).with_name('runtime.py').read_text(encoding='utf-8')
    helper_source = '\n\n'.join(ast.get_source_segment(helper_file, function(helper_file, name)) for name in HELPERS) + '\n\n'
    first = next(n for n in ast.parse(source).body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)))
    line = min([first.lineno] + [n.lineno for n in first.decorator_list])
    lines = source.splitlines(keepends=True)
    lines.insert(line - 1, helper_source)
    source = ''.join(lines)
    compile(source, 'cars_ui_stage2_candidate.py', 'exec')
    after_tree = ast.parse(source)
    def untouched(tree):
        return [ast.dump(n, include_attributes=False) for n in tree.body
                if not (isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in (*TARGETS, *HELPERS))]
    if untouched(before_tree) != untouched(after_tree):
        raise Refused('UNRELATED_TOP_LEVEL_CHANGE')
    # Original statements inside each target survive verbatim in AST order.
    for name in TARGETS:
        old = function(original, name)
        new = function(source, name)
        expected = [ast.dump(n, include_attributes=False) for n in old.body]
        actual = [ast.dump(n, include_attributes=False) for n in new.body]
        if len(actual) != len(expected) + 1 or not any(actual[:i] + actual[i+1:] == expected for i in range(len(actual))):
            raise Refused('EXISTING_HANDLER_BODY_CHANGED:' + name)
    return source, {'status': 'CANDIDATE_ONLY', 'before_sha256': digest(original),
                    'after_sha256': digest(source), 'changed_functions': list(TARGETS),
                    'added_helpers': list(HELPERS), 'other_ast_nodes_preserved': True,
                    'installation': 'NOT_PERFORMED', 'live_acceptance': 'NOT_PERFORMED'}
