"""Reads CPI, PPI and jobs numbers straight from the official BLS API the moment they post.

A free BLS API key is needed: without one the API allows only 25 requests a day,
which a release-time poll uses up quickly. Register at https://data.bls.gov/registrationEngine/
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from . import net

API = "https://api.bls.gov/publicAPI/v2/timeseries/data/"

# What each release needs: name -> {label: (series id, how to compute)}
RELEASES = {
    "CPI": {
        "CPI m/m": ("CUSR0000SA0", "mom"),
        "Core CPI m/m": ("CUSR0000SA0L1E", "mom"),
        "CPI y/y": ("CUUR0000SA0", "yoy"),
        "Core CPI y/y": ("CUUR0000SA0L1E", "yoy"),
    },
    "PPI": {
        "PPI m/m": ("WPSFD4", "mom"),
        "PPI y/y": ("WPUFD4", "yoy"),
    },
    "JOBS": {
        "Non-Farm Employment Change": ("CES0000000001", "diff_k"),
        "Unemployment Rate": ("LNS14000000", "level"),
        "Average Hourly Earnings m/m": ("CES0500000003", "mom"),
    },
}

# Forex Factory calendar titles that tell the bot which release is coming
CALENDAR_TITLES = {
    "CPI m/m": "CPI", "Core CPI m/m": "CPI", "CPI y/y": "CPI",
    "PPI m/m": "PPI",
    "Non-Farm Employment Change": "JOBS", "Unemployment Rate": "JOBS",
}


@dataclass
class Reading:
    label: str
    value: float          # % for m/m, y/y and rates; thousands of jobs for payrolls
    period: str           # e.g. "2026-09"
    unit: str


def _points(series: dict) -> list[tuple[str, float]]:
    pts = []
    for d in series.get("data", []):
        p = d.get("period", "")
        if not p.startswith("M") or p == "M13":
            continue
        try:
            pts.append((f"{d['year']}-{p[1:]}", float(d["value"])))
        except (KeyError, ValueError):
            continue
    return sorted(pts, reverse=True)       # newest first


def compute(kind: str, pts: list[tuple[str, float]]) -> float | None:
    if kind == "level":
        return pts[0][1] if pts else None
    if kind == "mom" and len(pts) >= 2:
        return round((pts[0][1] / pts[1][1] - 1) * 100, 1)
    if kind == "yoy" and len(pts) >= 13:
        return round((pts[0][1] / pts[12][1] - 1) * 100, 1)
    if kind == "diff_k" and len(pts) >= 2:
        return round(pts[0][1] - pts[1][1])      # series is in thousands
    return None


def parse_response(release: str, payload: dict) -> list[Reading]:
    by_id = {s["seriesID"]: s for s in payload.get("Results", {}).get("series", [])}
    out = []
    for label, (sid, kind) in RELEASES[release].items():
        pts = _points(by_id.get(sid, {}))
        v = compute(kind, pts)
        if v is None:
            continue
        unit = "K" if kind == "diff_k" else "%"
        out.append(Reading(label, v, pts[0][0], unit))
    return out


def fetch(release: str, api_key: str = "") -> dict:
    y = date.today().year
    body = {"seriesid": [sid for sid, _ in RELEASES[release].values()],
            "startyear": str(y - 1), "endyear": str(y)}
    if api_key:
        body["registrationkey"] = api_key
    data = net.post(API, json=body).json()
    if data.get("status") != "REQUEST_SUCCEEDED":
        raise RuntimeError(f"BLS API: {data.get('status')} {data.get('message')}")
    return data


def latest_period(readings: list[Reading]) -> str | None:
    return max((r.period for r in readings), default=None)
