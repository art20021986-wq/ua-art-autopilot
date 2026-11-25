"""Build the KOREA-OFFER-001 candidate from the live korea.html (ru/korea.html follows by the installed job)."""
import offer

DEPENDENCY_SHA256 = {}


def targets(root):
    return (offer.NAME,)


def build(source, dependencies=None):
    if set(source) != {offer.NAME}:
        raise ValueError('UNPLANNED')
    return {offer.NAME: offer.build(source[offer.NAME])}
