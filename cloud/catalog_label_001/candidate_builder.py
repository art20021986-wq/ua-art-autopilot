"""Build the catalogue label candidate: only the Japan rare-car card's name, labels and alt texts."""
import label

# The live catalogue is pinned by the plan.
SOURCE_FILES = (label.CATALOG,)
OWN_FILES = ()
DEPENDENCY_SHA256 = {}


def build(source, dependencies):
    return {label.CATALOG: label.build(source[label.CATALOG])}
