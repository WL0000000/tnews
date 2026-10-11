"""Scores free RSS headlines for how much they matter to NQ."""
from __future__ import annotations

import re

from . import net
from .rss import Item, parse_feed

NEGATIVE = ["strike", "attack", "missile", "escalat", "tariff", "sanction", "ban", "export control",
            "hike", "hawkish", "hotter", "surge in inflation", "misses", "miss ", "cuts outlook", "warning",
            "downgrade", "plunge", "slump", "closes strait", "shut", "default", "probe", "shutdown",
            "selloff", "sell-off", "layoffs", "recall", "halt"]
POSITIVE = ["ceasefire", "peace", "deal", "truce", "agreement", "cut rates", "rate cut", "dovish",
            "cooler", "beats", "raises outlook", "record high", "surge", "rally", "reopen", "approve",
            "exemption", "pause", "eases", "eased", "easing", "upgrade", "stimulus"]


def score(title: str, keywords: dict[str, int]) -> tuple[int, list[str]]:
    t = title.lower()
    hits = [k for k in keywords if re.search(r"(?<![a-z])" + re.escape(k) + r"s?(?![a-z])", t)]
    return sum(keywords[k] for k in hits), hits


def tone(title: str) -> str:
    t = title.lower() + " "
    neg = sum(1 for w in NEGATIVE if w in t)
    pos = sum(1 for w in POSITIVE if w in t)
    if neg > pos:
        return "likely negative"
    if pos > neg:
        return "likely positive"
    return "direction unclear"


def fetch_all(feeds: list[str]) -> list[Item]:
    items: list[Item] = []
    for url in feeds:
        try:
            items.extend(parse_feed(net.get(url).text))
        except Exception as e:          # one bad feed should not stop the others
            print(f"[headlines] {url[:60]}... failed: {e}")
    return items


def new_important(items: list[Item], seen: set[str], keywords: dict[str, int], min_score: int):
    out = []
    for it in items:
        if not it.title or it.uid in seen:
            continue
        seen.add(it.uid)
        s, hits = score(it.title, keywords)
        if s >= min_score:
            out.append((s, it, hits))
    return sorted(out, key=lambda x: -x[0])
