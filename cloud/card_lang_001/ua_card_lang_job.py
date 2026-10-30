"""Keeps the card language versions in step with the CRM pages (CARD-LANG-001): a CRM bot job, once a minute.

Under the existing publication fence (never during a publication): ua_card_lang.reconcile for the cards the
catalogue publishes; when a version was written or removed, ua_seo_index.refresh renews the sitemap and tells
IndexNow and Google, as after a publication. A failure is logged and retried next minute; it never touches
the CRM or blocks a publication.
"""
import asyncio
import logging
from pathlib import Path

ROOT = Path('/home/Carix/video')
NAME = 'card-lang-versions'
log = logging.getLogger(__name__)


def run(root=ROOT):
    from publication_fence import publication_fence
    import ua_card_lang
    import ua_seo_sitemap
    with publication_fence(timeout=5.0):
        published = ua_seo_sitemap.CatalogLinks((root/'katalog.html').read_text(encoding='utf-8')).names
        result = ua_card_lang.reconcile(root, published)
        if result['written'] or result['removed']:
            import ua_seo_index
            result['seo_index'] = ua_seo_index.refresh(root)
    return result


async def job(context):
    try:
        result = await asyncio.to_thread(run)
    except Exception as error:
        log.warning('Языковые версии карточек: %s: %s', type(error).__name__, str(error)[:160])
        return
    if result['written'] or result['removed'] or result['incomplete'] or result['failed']:
        log.info('Языковые версии карточек: %s', {k: v for k, v in result.items() if v})


def schedule(app):
    if app.job_queue is None:
        raise RuntimeError('JobQueue is required')
    if not app.job_queue.get_jobs_by_name(NAME):
        app.job_queue.run_repeating(job, interval=60, first=30, name=NAME,
                                    job_kwargs={'max_instances': 1, 'coalesce': True})
