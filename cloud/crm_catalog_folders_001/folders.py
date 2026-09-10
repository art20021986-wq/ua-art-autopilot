"""Read-only view model for the existing CRM cars list.

Integration candidate, not a deployed Telegram handler. The caller supplies one
complete, permission-filtered snapshot from the existing cars data source.
`published` must be the committed publication flag, reconciled with the public
catalog before installation. Never probe HTTP availability to classify cars.
"""
from dataclasses import dataclass
from typing import Callable, Iterable, Mapping, Any


FOLDERS = {"catalog": "В каталоге", "unpublished": "Не опубликованные"}
MENU_CALLBACK = "cars_folders"


class InvalidSnapshot(ValueError):
    """Reject ambiguous data without changing any record or publication flag."""


@dataclass(frozen=True)
class Button:
    text: str
    callback_data: str


@dataclass(frozen=True)
class View:
    text: str
    rows: tuple


def partition(cards: Iterable[Mapping[str, Any]]) -> dict:
    """Preserve card identity and ordering; never infer publication from stage."""
    groups = {key: [] for key in FOLDERS}
    seen = set()
    for card in cards:
        cid = card.get("id")
        if type(cid) is not int or cid <= 0 or cid in seen:
            raise InvalidSnapshot("Missing, invalid or duplicate car id")
        seen.add(cid)
        flag = card.get("published")
        if type(flag) not in (int, bool) or flag not in (0, 1):
            raise InvalidSnapshot("Car %s has no unambiguous publication flag" % cid)
        groups["catalog" if flag else "unpublished"].append(card)
    return groups


def menu(cards: Iterable[Mapping[str, Any]]) -> View:
    groups = partition(cards)
    return View("Автомобили", tuple(
        (Button("%s · %d" % (label, len(groups[key])),
                "cars_folder:%s:0" % key),)
        for key, label in FOLDERS.items()
    ))


def parse_callback(data: str) -> tuple:
    """Validate the exact namespace before the existing router handles it."""
    parts = data.split(":")
    if (len(parts) != 3 or parts[0] != "cars_folder"
            or parts[1] not in FOLDERS or not parts[2].isascii()
            or not parts[2].isdigit() or len(parts[2]) > 9):
        raise ValueError("Invalid cars folder callback")
    return parts[1], int(parts[2])


def listing(cards: Iterable[Mapping[str, Any]], folder: str, page: int,
            label: Callable[[Mapping[str, Any]], str], *, page_size: int) -> View:
    """Use the existing label formatter and car_open callbacks unchanged."""
    if (folder not in FOLDERS or type(page) is not int or page < 0
            or type(page_size) is not int or page_size <= 0):
        raise ValueError("Invalid cars folder or page")
    selected = partition(cards)[folder]
    last_page = max(0, (len(selected) - 1) // page_size)
    page = min(page, last_page)  # A publication may empty the previous last page.
    start = page * page_size
    rows = [(Button(label(card), "car_open:%d" % card["id"]),)
            for card in selected[start:start + page_size]]
    navigation = []
    if page:
        navigation.append(Button("←", "cars_folder:%s:%d" % (folder, page - 1)))
    if page < last_page:
        navigation.append(Button("→", "cars_folder:%s:%d" % (folder, page + 1)))
    if navigation:
        rows.append(tuple(navigation))
    rows.append((Button("← Автомобили", MENU_CALLBACK),))
    text = "%s · %d" % (FOLDERS[folder], len(selected))
    if not selected:
        text += "\nВ этой папке пока нет автомобилей."
    elif last_page:
        text += "\nСтраница %d из %d" % (page + 1, last_page + 1)
    return View(text, tuple(rows))
