"""Build the PAY-LABELS-001 candidate: the approved deal names next to the payment sums (pay_labels.EDITS).

Static pages change now (home, Korea auctions, conditions); stranica.py so the conditions page keeps the texts at
its next publication; the site dictionary gives the new conditions lines in Ukrainian and Georgian. The Russian
Korea page (/video/ru/korea.html) follows the Ukrainian one by itself (card version job).
"""
import pay_labels

DEPENDENCY_SHA256 = {}


def page_names(root):
    return pay_labels.PAGES


def targets(root):
    return pay_labels.FILES


def build(source, dependencies):
    return {name: pay_labels.apply(name, value.decode('utf-8')).encode('utf-8') for name, value in source.items()}


def is_page(name):
    return name in pay_labels.PAGES
