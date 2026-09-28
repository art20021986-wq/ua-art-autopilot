"""Read-only URL Inspection entry point."""
from __future__ import annotations

import json
import os
import sys

from .gsc_client import GSCConfigError, inspect_url


DEFAULT_URLS = (
    "https://www.uaart.com.ua/",
    "https://www.uaart.com.ua/video/katalog.html",
    "https://www.uaart.com.ua/video/podbor.html",
)


def main() -> int:
    site_url = os.environ.get("GSC_SITE_URL", "sc-domain:uaart.com.ua").strip()
    urls = tuple(x.strip() for x in os.environ.get("GSC_INSPECTION_URLS", "").split(",") if x.strip()) or DEFAULT_URLS

    results = []
    try:
        for url in urls:
            raw = inspect_url(url, site_url)
            idx = raw.get("inspectionResult", {}).get("indexStatusResult", {})
            results.append({
                "url": url,
                "verdict": idx.get("verdict"),
                "coverageState": idx.get("coverageState"),
                "robotsTxtState": idx.get("robotsTxtState"),
                "indexingState": idx.get("indexingState"),
                "pageFetchState": idx.get("pageFetchState"),
                "lastCrawlTime": idx.get("lastCrawlTime"),
                "googleCanonical": idx.get("googleCanonical"),
                "userCanonical": idx.get("userCanonical"),
            })
    except GSCConfigError as exc:
        print(f"CONFIGURATION_BLOCK: {exc}", file=sys.stderr)
        return 2

    print(json.dumps({"site": site_url, "results": results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
