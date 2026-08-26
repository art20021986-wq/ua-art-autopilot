#!/usr/bin/env python3
import json, os, pathlib, re, subprocess, sys, urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
TASKS = ROOT / 'tasks'
CLOUD = ROOT / 'cloud'
CLOUD.mkdir(exist_ok=True)


def latest_task():
    files = sorted(TASKS.glob('task_*.md'))
    if not files:
        raise SystemExit('NO_TASK')
    return files[-1]


def call_claude(system_text, task_text):
    key = os.environ.get('ANTHROPIC_API_KEY')
    if not key:
        raise SystemExit('ANTHROPIC_API_KEY_MISSING')
    model = os.environ.get('ANTHROPIC_MODEL', 'claude-sonnet-4-20250514')
    payload = {
        'model': model,
        'max_tokens': 12000,
        'system': system_text,
        'messages': [{'role':'user','content': task_text + '\n\nReturn ONLY valid JSON of the form {"files":{"cloud/path":"content"},"status":"DONE|BLOCKED","summary":"...","owner_action_required":"YES|NO","owner_question":"..."}. All file paths MUST start with cloud/. Do not propose or perform production writes.'}]
    }
    req = urllib.request.Request(
        'https://api.anthropic.com/v1/messages',
        data=json.dumps(payload).encode(),
        headers={'x-api-key': key, 'anthropic-version':'2023-06-01', 'content-type':'application/json'},
        method='POST'
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        data = json.load(r)
    text = ''.join(x.get('text','') for x in data.get('content',[]) if x.get('type') == 'text').strip()
    m = re.search(r'\{.*\}', text, re.S)
    if not m:
        raise SystemExit('CLAUDE_JSON_MISSING')
    return json.loads(m.group(0))


def safe_write(files):
    written = []
    for rel, content in files.items():
        p = pathlib.PurePosixPath(rel)
        if not str(p).startswith('cloud/') or '..' in p.parts:
            raise SystemExit('UNSAFE_PATH:' + rel)
        dst = ROOT / p
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(str(content), encoding='utf-8')
        written.append(str(p))
    return written


def main():
    task = latest_task()
    system_text = (ROOT / 'CLAUDE.md').read_text(encoding='utf-8') if (ROOT/'CLAUDE.md').exists() else 'Work only in cloud/. Never touch production.'
    result = call_claude(system_text, task.read_text(encoding='utf-8'))
    written = safe_write(result.get('files', {}))
    task_id = task.stem
    status_path = CLOUD / 'latest_status.md'
    if not status_path.exists():
        status_path.write_text(
            f'TASK_ID: {task_id}\nROUND: 1\nCLAUDE_STATUS: {result.get("status","BLOCKED")}\nCURRENT_ACTION: autonomous GitHub worker completed\nFILES_CREATED: {",".join(written) or "NONE"}\nPRODUCTION_TOUCHED: NO\nOWNER_ACTION_REQUIRED: {result.get("owner_action_required","NO")}\nOWNER_QUESTION: {result.get("owner_question","NONE")}\nNEXT_FOR_CHATGPT: inspect cloud outputs and issue next task\n',
            encoding='utf-8'
        )
    print(json.dumps({'task':task_id,'written':written,'status':result.get('status'),'summary':result.get('summary')}, ensure_ascii=False))

if __name__ == '__main__':
    main()
