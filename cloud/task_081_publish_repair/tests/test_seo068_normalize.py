"""Offline tests modeling the SEO068 diagnostic-ordering bug and its fix:
placeholder must be created in the STAGING bundle before validation runs, so
a brand-new card without diagnostics is never blocked.
"""
import re


class StagingBundle:
    def __init__(self, primary_html, has_diag_initially):
        self.primary_html = primary_html
        self.diag_exists = has_diag_initially
        self.diag_content = None

    def diag_path(self, auto_number):
        class P:
            def __init__(self, exists):
                self._exists = exists

            def exists(self):
                return self._exists

        return P(self.diag_exists)

    def write_diag_placeholder(self, auto_number, text):
        self.diag_exists = True
        self.diag_content = text

    def primary_path(self, auto_number):
        return self.primary_html

    def extract_diag_href(self, primary_html):
        m = re.search(r'href="([^"]*-diag\.html)"', primary_html)
        return m.group(1) if m else None

    def expected_diag_href(self, auto_number):
        return f"{auto_number}-diag.html"


def buggy_normalize_checks_live_root_only(live_root_has_diag: bool):
    """Reproduces the bug: only checks live root existence, never staging,
    so a new card can never pass."""
    if not live_root_has_diag:
        raise ValueError("SEO068_DIAGNOSTIC_TARGET_MISSING:UA-0013")
    return True


def fixed_normalize(staging_bundle: StagingBundle, auto_number: str):
    if not staging_bundle.diag_path(auto_number).exists():
        staging_bundle.write_diag_placeholder(auto_number, text="Материалы диагностики ожидаются")
    href = staging_bundle.extract_diag_href(staging_bundle.primary_path(auto_number))
    expected = staging_bundle.expected_diag_href(auto_number)
    if href != expected:
        raise ValueError(f"SEO068_WRONG_DIAG_LINK:{auto_number}")
    return True


def test_reproduces_reported_bug_new_card_always_fails():
    try:
        buggy_normalize_checks_live_root_only(live_root_has_diag=False)
        assert False, "expected failure"
    except ValueError as exc:
        assert "SEO068_DIAGNOSTIC_TARGET_MISSING" in str(exc)


def test_fixed_creates_placeholder_and_passes_for_new_card():
    bundle = StagingBundle(primary_html='<a href="UA-0013-diag.html">diag</a>', has_diag_initially=False)
    assert fixed_normalize(bundle, "UA-0013") is True
    assert bundle.diag_exists is True
    assert bundle.diag_content == "Материалы диагностики ожидаются"


def test_fixed_still_rejects_wrong_diag_link():
    bundle = StagingBundle(primary_html='<a href="UA-9999-diag.html">diag</a>', has_diag_initially=True)
    try:
        fixed_normalize(bundle, "UA-0013")
        assert False, "expected wrong-link rejection"
    except ValueError as exc:
        assert "SEO068_WRONG_DIAG_LINK" in str(exc)


def test_fixed_generic_for_future_card_ua9999():
    bundle = StagingBundle(primary_html='<a href="UA-9999-diag.html">diag</a>', has_diag_initially=False)
    assert fixed_normalize(bundle, "UA-9999") is True
    assert bundle.diag_exists is True
