"""Build the AUCTION-LIMIT candidate from the exact installed sources (AUCTION-CLIENTS, AUCTION-BIDS and AUCTION-HOME
installs of 2026-11-10/11). Owner 2026-11-12: the deposit is at least 1 000 $ and there is no bid limit.

- ua_auction_clients.py: deposit from 1 000 $ (was 2 000 $); no limit_usd (was 15 000 $ per 2 000 $ of deposit).
- ua_auction_bids.py: a bid is no longer refused for being above the client's limit (step, minimum, day limit stay).
- ua_auction_clients_view.py / ua_auction_clients_bot.py / ua_auction_stats.py: the CRM bot shows no bid limit.
- ua_auction_web.py: the login answer has no limit.
No page change: the Korea page no longer carries the client cabinet (removed by KOREA-LOTS-FULL, 2026-11-12).
"""
import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
# Installed versions this package was written against; any other version stops the build.
SOURCE_SHA256 = {
    'ua_auction_clients.py': '3d54afd110e28f170b0e88ca1a4c387d07a48941307024f1bddc90853f414a5d',
    'ua_auction_clients_view.py': '85a8381c23254ff595f48e12f1fbafa7180a1a67eddf28dff1b5b48c70e1c8d5',
    'ua_auction_clients_bot.py': '76ab27475cc83c9fa3c47cfb27e7d4f020faee2a23f2beb1591da181c4a2cc19',
    'ua_auction_bids.py': '934ae8642946ea66c7c7782c1bc550f8df7adf65dee96e8a8fc61af48965ecb4',
    'ua_auction_stats.py': '268e9299c8004b55db8784e85675e6319042163f4d0179457ed4e50ae1a019db',
    'ua_auction_web.py': '4f7b52aff7e5fa95d06b392ce154e5382f733b2056d2e420e32ed35c2586e148',
}
MODULES = tuple(SOURCE_SHA256)
SOURCE_FILES = MODULES
DEPENDENCY_SHA256 = {}
def build(source, dependencies):
    for name, digest in SOURCE_SHA256.items():
        if hashlib.sha256(source[name]).hexdigest() != digest:
            raise ValueError('INPUT_HASH:' + name)
    return {name: (HERE / name).read_bytes() for name in MODULES}
