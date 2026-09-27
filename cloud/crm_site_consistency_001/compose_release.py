"""Compose media with the reviewed stage, performance and one-click repairs.

This builds private bytes only. The publication intermediate is SHA-bound;
changes in either release fail closed and require a fresh review. No installer,
protected runtime-pin update or production write is performed here.
"""
import hashlib
import importlib.util
from pathlib import Path

import build_gallery_patch as MEDIA

HERE = Path(__file__).resolve().parent
PUBLICATION_CANDIDATE_SHA256 = {
    'cars_ui.py': 'fed3ccd110e750947288bbe5892f1c62262b23d6818653f43c7d57b584bf92dd',
    'publikaciya.py': '4d1adb53cb659daa125c7480c289ad25e03a57e34d3d0c1f4e0989de1d7a8ac8',
    'ua_crm_public_sync.py': '8c65eeb598c15007f489e2eaa0453362c97b9c426a3f67cf02c6a09a0d37015f',
    'ua_publish_requests.py': '746657dd1c6b23968582cbb19bb6bb819ed5ad28654c1f4a657b258cd14645a1',
}


def publication_builder():
    base = HERE / 'release_builders'
    path = base / 'crm_oneclick_publish_001' / 'build_candidate.py'
    spec = importlib.util.spec_from_file_location('media_publication_builder', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def combine(sources, publication):
    """Accept only the reviewed complete publication output and live media inputs."""
    if set(publication) != set(PUBLICATION_CANDIDATE_SHA256):
        raise ValueError('PUBLICATION_CANDIDATE_SET')
    if set(sources) != set(MEDIA.SOURCES):
        raise ValueError('MEDIA_SOURCE_SET')
    for name, expected in PUBLICATION_CANDIDATE_SHA256.items():
        if hashlib.sha256(publication[name]).hexdigest() != expected:
            raise ValueError('PUBLICATION_CANDIDATE_CHANGED:' + name)
    result = dict(publication)
    for name, original in sources.items():
        result[name] = compose_file(name, original, publication.get(name))
    for name, raw in result.items():
        compile(raw, name, 'exec')
    return result


def compose_file(name, original, intermediate=None):
    # Verify full live-source SHA even when using a reviewed intermediate.
    candidate = MEDIA.build(name, original)
    if intermediate is not None:
        expected = PUBLICATION_CANDIDATE_SHA256.get(name)
        if not expected or hashlib.sha256(intermediate).hexdigest() != expected:
            raise ValueError('PUBLICATION_CANDIDATE_CHANGED:' + name)
        candidate = MEDIA.apply_reviewed_changes(name, intermediate)
    return candidate


def build(sources, dependencies):
    publication = publication_builder()
    expected = set(MEDIA.SOURCES) | set(publication.SOURCE_SHA256)
    if set(sources) != expected:
        raise ValueError('COMBINED_SOURCE_SET')
    base = publication.build({name: sources[name] for name in publication.SOURCE_SHA256}, dependencies)
    return combine({name: sources[name] for name in MEDIA.SOURCES}, base)
