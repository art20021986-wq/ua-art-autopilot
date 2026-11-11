"""Build the AUTORIA-SOLD candidate: the job package and its launcher as new files in /home/Carix.

The job modules come from autoria_sold/ in this package (zipped flat as asold_<module>.py by the transport).
Nothing existing changes: no page, no CRM module; the job itself writes only video/brand/autoria-sold.json.
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODULES = ('job', 'page')
LAUNCHER = 'autoria_sold_job.py'
LAUNCHER_SOURCE = (b'"""Daily PythonAnywhere task: the AUTO.RIA sold-cars number, refreshed on Mondays (autoria_sold.job)."""\n'
                   b'import sys\n\nfrom autoria_sold import job\n\nsys.exit(job.main())\n')
SOURCE_FILES = ()
DEPENDENCY_SHA256 = {}


def build(source, dependencies, here=HERE):
    files = {'autoria_sold/__init__.py': b''}
    for name in MODULES:
        files['autoria_sold/%s.py' % name] = (here / ('asold_%s.py' % name)).read_bytes()
    files[LAUNCHER] = LAUNCHER_SOURCE
    return files


def is_page(name):
    return False
