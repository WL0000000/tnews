"""This week's economic calendar with forecasts, from the free Forex Factory JSON feed."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from . import net

FF_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"


@dataclass
class Event:
    title: str
    when: datetime          # timezone-aware
    impact: str             # High / Medium / Low / Holiday
    forecast: str
    previous: str

    @property
    def key(self) -> str:
        return f"{self.title}|{self.when.isoformat()}"


def parse_number(s: str | None) -> float | None:
    """'0.3%' -> 0.3, '150K' -> 150000, '-1.2M' -> -1200000, '' -> None."""
    if not s:
        return None
    m = re.match(r"^\s*([-+]?\d+(?:\.\d+)?)\s*([%KMB]?)\s*$", s.strip(), re.I)
    if not m:
        return None
    v = float(m.group(1))
    mult = {"K": 1e3, "M": 1e6, "B": 1e9}.get(m.group(2).upper(), 1)
    return v * mult


def parse(items: list[dict], country: str = "USD", impacts=("High",)) -> list[Event]:
    out = []
    for it in items:
        if it.get("country") != country or it.get("impact") not in impacts:
            continue
        try:
            when = datetime.fromisoformat(it["date"])
        except (KeyError, ValueError):
            continue
        out.append(Event(it.get("title", ""), when, it.get("impact", ""),
                         it.get("forecast", "") or "", it.get("previous", "") or ""))
    return sorted(out, key=lambda e: e.when)


def fetch(impacts=("High",)) -> list[Event]:
    return parse(net.get(FF_URL).json(), impacts=impacts)


def forecast_for(events: list[Event], title: str) -> float | None:
    for e in events:
        if e.title.lower() == title.lower():
            return parse_number(e.forecast)
    return None
