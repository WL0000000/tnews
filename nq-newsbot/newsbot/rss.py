"""Minimal RSS/Atom parser (standard library only)."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from email.utils import parsedate_to_datetime


@dataclass
class Item:
    title: str
    link: str
    published: str
    source: str = ""

    @property
    def uid(self) -> str:
        title = self.title
        # Google News appends " - Publisher"; drop it so the same story from two feeds dedupes
        if " - " in title and len(title.rsplit(" - ", 1)[1]) <= 40:
            title = title.rsplit(" - ", 1)[0]
        t = re.sub(r"[^a-z0-9 ]", "", title.lower())
        return re.sub(r"\s+", " ", t).strip()


def _text(el, *names):
    for n in names:
        x = el.find(n)
        if x is not None:
            return (x.text or x.get("href") or "").strip()
    return ""


def parse_feed(xml_text: str) -> list[Item]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    items = []
    atom = "{http://www.w3.org/2005/Atom}"
    for it in root.iter("item"):
        src = it.find("source")
        items.append(Item(_text(it, "title"), _text(it, "link"), _text(it, "pubDate"),
                          (src.text or "").strip() if src is not None else ""))
    for it in root.iter(atom + "entry"):
        link_el = it.find(atom + "link")
        items.append(Item(_text(it, atom + "title"), link_el.get("href", "") if link_el is not None else "",
                          _text(it, atom + "updated", atom + "published")))
    return items


def to_datetime(s: str):
    try:
        return parsedate_to_datetime(s)
    except (TypeError, ValueError):
        return None
