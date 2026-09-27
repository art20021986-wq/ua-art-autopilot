"""Validate installed OCR and Telegram APIs without opening the live CRM."""
import ast
import shutil
import subprocess
from types import SimpleNamespace

from crm_explicit_fields import parse
from crm_photo_intake import register


def verify_runtime(root):
    from PIL import Image, ImageOps
    from telegram.ext import MessageHandler
    binary = shutil.which('tesseract')
    if not binary:
        raise RuntimeError('OCR_UNAVAILABLE')
    languages = subprocess.run([binary, '--list-langs'], capture_output=True,
                               text=True, timeout=5, check=True).stdout.splitlines()
    if 'eng' not in [line.strip() for line in languages]:
        raise RuntimeError('OCR_ENGLISH_UNAVAILABLE')
    values = {}
    names = {'ALLOWED', 'FUEL', 'GEARBOX', 'DRIVE', 'COLOR'}
    for node in ast.parse((root/'ai_filter.py').read_text()).body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in names:
                    values[target.id] = ast.literal_eval(node.value)
    if set(values) != names:
        raise RuntimeError('LIVE_ENUM_CONTRACT')
    registered = []
    app = SimpleNamespace(add_handler=lambda handler, group: registered.append((handler, group)))
    register(app, object(), SimpleNamespace(**values), object(), object())
    if len(registered) != 1 or registered[0][1] != -3 or not isinstance(registered[0][0], MessageHandler):
        raise RuntimeError('HANDLER_REGISTRATION')
    mapping = {key: values[name] for key, name in
               [('fuel', 'FUEL'), ('gearbox', 'GEARBOX'), ('drive', 'DRIVE'), ('color', 'COLOR')]}
    facts, bad, _ = parse('Mileage 109,353 km\nRegistration Date 2022/00\nEngine Capacity 1,999 cc\nColor Black\nTransmission Automatic\nFuel Type LPG', values['ALLOWED'], mapping)
    if bad or facts.get('mileage_km') != 109353 or facts.get('engine_cc') != 1999 or 'year' in facts:
        raise RuntimeError('LIVE_FIELD_CONTRACT')
    return dict(telegram_handler='PASS', existing_ocr='PASS', explicit_fields='PASS', crm_write=False)
