"""Build an isolated, explicitly historical-data preview; never deploys."""
from pathlib import Path
import hashlib
import html
import importlib.util
import json
import re
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "runtime"))
import profile_library
import spec_publication


def build():
    before_path = HERE / "evidence/UA-0001-before.html"
    before = before_path.read_text(encoding="utf-8")
    matches = [p for p in profile_library.PROFILES if any(v in before for v in p.get("exact_vins", ()))]
    if len(matches) != 1:
        raise RuntimeError("PREVIEW_EXACT_HISTORICAL_PROFILE_NOT_UNIQUE")
    profile = matches[0]
    facts = []
    for key, item in profile["facts"].items():
        label, category, unit = profile_library.FIELD_DEFS[key]
        facts.append({"field_key": key, "label_ru": label, "category": category, "unit": unit,
                      "field_value": item["value"], "verification_status": "CURATED_PASS", "is_visible": 1})
    after = spec_publication.inject(before, "UA-0001", facts)
    assert spec_publication.strip_block(after) == before
    assert spec_publication.inject(after, "UA-0001", facts) == after
    checked = spec_publication.validate_page(after, "UA-0001", facts)
    after_path = HERE / "evidence/UA-0001-candidate.html"
    after_path.write_text(after, encoding="utf-8")
    def frame(source):
        # Presentation-only transform; candidate file and comparison stay exact.
        source = source.replace('<head>', '<head><base href="https://www.uaart.com.ua/video/">', 1)
        source = source.replace('<details class="blok ua-additional-spec"', '<details open class="blok ua-additional-spec"', 1)
        return html.escape(source, quote=True)
    preview = '''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>UA ART — Preview дополнительной спецификации</title>
<style>*{box-sizing:border-box}body{margin:0;background:#101925;color:#edf2f8;font:16px/1.55 system-ui,sans-serif}main{max-width:1260px;margin:auto;padding:24px}h1{font-size:clamp(24px,4vw,36px);line-height:1.2;margin:12px 0}p{max-width:940px}.tag{color:#e6b75b;font-size:13px;text-transform:uppercase;letter-spacing:.08em}.note{border-left:3px solid #e6b75b;background:#1a2636;padding:14px 18px;margin:18px 0}.facts{display:flex;flex-wrap:wrap;gap:10px}.facts span{background:#223247;border:1px solid #344c68;border-radius:24px;padding:6px 12px}button{border:1px solid #e6b75b;border-radius:8px;padding:10px 15px;background:#e6b75b;color:#101925;font:inherit;font-weight:650;cursor:pointer;margin:14px 8px 14px 0}button[aria-pressed=false]{background:transparent;color:#e6b75b}.frames{display:grid;grid-template-columns:1fr 1fr;gap:16px}section{min-width:0}h2{font-size:18px}iframe{width:100%;height:900px;border:1px solid #40536b;border-radius:12px;background:#0a1220}.single .frames{grid-template-columns:1fr}.single #before{display:none}@media(max-width:750px){main{padding:16px}.frames{grid-template-columns:1fr}iframe{height:740px}}</style></head><body><main>
<div class="tag">UA-ART-SPEC-AUTO-10-RESTORE-001 · Preview</div><h1>Дополнительная спецификация возвращается в карточку</h1>
<p>Проверка изменения на копии реальной страницы UA-0001. Заголовок раздела — «Додаткова специфікація». Цены, описание, этапы, фотографии и видео в файле кандидата сохранены без изменений.</p>
<div class="note"><strong>Это предварительный просмотр, не опубликованное исправление.</strong><br>43 характеристики показаны из сохранённого справочного профиля от 04.09.2026, совпавшего по VIN. Текущая база CRM и новые ответы десяти источников ещё не проверены. Это не подтверждение восстановления всех 16 карточек.</div>
<div class="facts"><span>1 отдельный раздел</span><span>43 справочных параметра</span><span>0 изменений вне раздела</span><span>0 рекламных ссылок в разделе</span></div>
<button id="only" aria-pressed="true">Исправленная копия</button><button id="compare" aria-pressed="false">До / после</button>
<div class="frames"><section id="before"><h2>До — снимок сайта 09.09.2026</h2><iframe title="Текущая карточка без спецификации" sandbox srcdoc="BEFORE_FRAME"></iframe></section><section><h2>После — кандидат с дополнительной спецификацией</h2><iframe title="Кандидат карточки со спецификацией" sandbox srcdoc="AFTER_FRAME"></iframe></section></div>
<p>Раздел в копии раскрыт для просмотра. Сценарий в CRM после исправления: сохранить данные автомобиля → автоматический сбор → обычная публикация → проверенная ссылка. Старые карточки обрабатываются без отдельных нажатий.</p>
</main><script>document.body.classList.add('single');const a=document.getElementById('only'),b=document.getElementById('compare');a.onclick=()=>{document.body.classList.add('single');a.setAttribute('aria-pressed','true');b.setAttribute('aria-pressed','false')};b.onclick=()=>{document.body.classList.remove('single');b.setAttribute('aria-pressed','true');a.setAttribute('aria-pressed','false')};</script></body></html>'''
    preview = preview.replace("BEFORE_FRAME", frame(before)).replace("AFTER_FRAME", frame(after))
    (HERE / "Preview.html").write_text(preview, encoding="utf-8")
    report = {"task": "UA-ART-SPEC-AUTO-10-RESTORE-001", "preview_type": "captured_page_with_historical_profile",
              "data_source": "profile_library.py", "profile_date": profile_library.AUDIT_DATE,
              "profile_id": profile["id"], "runtime_database_verified": False, "live_sources_verified": False,
              "card": "UA-0001", "spec_rows": checked["rows"], "non_spec_changes": 0,
              "two_regenerations_identical": True, "before_sha256": hashlib.sha256(before.encode()).hexdigest(),
              "candidate_sha256": hashlib.sha256(after.encode()).hexdigest(), "production_write": False}
    (HERE / "evidence/preview.json").write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False, indent=2))
