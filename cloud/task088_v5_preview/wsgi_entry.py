"""Entry point for a separately provisioned Preview web app only.

Requires UA_ART_PREVIEW_CONFIG to name its existing private configuration.
Missing configuration stops app startup; there is no unauthenticated fallback.
"""
from pathlib import Path
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

from wsgi_preview import application_from_environment

application = application_from_environment()
