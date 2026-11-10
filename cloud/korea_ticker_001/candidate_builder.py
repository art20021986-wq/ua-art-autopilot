"""Build the KOREA-TICKER candidate: the collector package and its launcher as new files in /home/Carix.

The collector modules come from korea_auction/ in this package (zipped flat as kauc_<module>.py by the transport).
Nothing existing changes: no page, no CRM module; the job itself writes only video/korea/ticker.html and video/korea/img/.
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODULES = ('catalog', 'collect', 'html_tools', 'job', 'lots', 'nbu', 'selection', 'session', 'ticker')
LAUNCHER = 'korea_ticker_job.py'
LAUNCHER_SOURCE = (b'"""Hourly PythonAnywhere task: the home ticker of Korea online auctions (korea_auction.job)."""\n'
                   b'import sys\n\nfrom korea_auction import job\n\nsys.exit(job.main())\n')
SOURCE_FILES = ()
DEPENDENCY_SHA256 = {}


def build(source, dependencies, here=HERE):
    files = {'korea_auction/__init__.py': b''}
    for name in MODULES:
        files['korea_auction/%s.py' % name] = (here / ('kauc_%s.py' % name)).read_bytes()
    files[LAUNCHER] = LAUNCHER_SOURCE
    return files


def is_page(name):
    return False
