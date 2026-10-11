"""Watches the Fed's own press-release feed for FOMC statements and minutes."""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from html.parser import HTMLParser

from . import net
from .rss import Item, parse_feed

FEED = "https://www.federalreserve.gov/feeds/press_monetary.xml"


def is_statement(item: Item) -> bool:
    t = item.title.lower()
    return "fomc statement" in t or ("federal reserve issues" in t and "fomc" in t)


def is_minutes(item: Item) -> bool:
    return "minutes of the federal open market committee" in item.title.lower()


def poll() -> list[Item]:
    return parse_feed(net.get(FEED).text)


class _ArticleText(HTMLParser):
    """Collects paragraph text, preferring the press release's article container."""

    def __init__(self):
        super().__init__()
        self.depth_article = 0
        self.in_p = False
        self.buf: list[str] = []
        self.paras_article: list[str] = []
        self.paras_all: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "div" and (a.get("id") == "article" or self.depth_article):
            self.depth_article += 1
        if tag == "p":
            self.in_p, self.buf = True, []

    def handle_endtag(self, tag):
        if tag == "p" and self.in_p:
            text = re.sub(r"\s+", " ", "".join(self.buf)).strip()
            if text:
                self.paras_all.append(text)
                if self.depth_article:
                    self.paras_article.append(text)
            self.in_p = False
        if tag == "div" and self.depth_article:
            self.depth_article -= 1

    def handle_data(self, data):
        if self.in_p:
            self.buf.append(data)


def page_text(html: str) -> str:
    p = _ArticleText()
    p.feed(html)
    paras = p.paras_article or p.paras_all
    return "\n".join(paras)


def _frac(s: str) -> float:
    # "4-1/4" -> 4.25, "4" -> 4.0, "1/4" -> 0.25
    s = s.strip()
    m = re.match(r"^(\d+)(?:-(\d+)/(\d+))?$", s)
    if m:
        whole = float(m.group(1))
        return whole + (float(m.group(2)) / float(m.group(3)) if m.group(2) else 0.0)
    m = re.match(r"^(\d+)/(\d+)$", s)
    return float(m.group(1)) / float(m.group(2)) if m else float("nan")


@dataclass
class StatementFacts:
    decision: str | None
    lower: float | None
    upper: float | None
    dissents: int


def facts(text: str) -> StatementFacts:
    t = re.sub(r"\s+", " ", text)
    m = re.search(r"decided to (raise|lower|maintain|reduce|increase)\s+the target range for the federal funds rate"
                  r"(?: by [^.]*?)?\s+(?:to|at)\s+([\d\-/]+)\s+to\s+([\d\-/]+)\s+percent", t, re.I)
    decision = lower = upper = None
    if m:
        verb = m.group(1).lower()
        decision = {"raise": "hike", "increase": "hike", "lower": "cut", "reduce": "cut", "maintain": "hold"}[verb]
        lower, upper = _frac(m.group(2)), _frac(m.group(3))
    d = re.search(r"Voting against (?:the|this) action (?:were|was)\s+([^.]*)\.", t, re.I)
    dissents = 0
    if d:
        who = re.split(r",?\s+who\s", d.group(1))[0]
        names = re.split(r",\s*(?:and\s+)?|\s+and\s+", who)
        dissents = len([n for n in names if n.strip()])
    return StatementFacts(decision, lower, upper, dissents)


def wording_changes(prev: str, new: str, limit: int = 4) -> list[str]:
    """Sentences added or removed since the last statement (how the Fed signals a shift)."""
    split = lambda s: [x.strip() for x in re.split(r"(?<=[.;])\s+", re.sub(r"\s+", " ", s)) if len(x.strip()) > 25]
    a, b = split(prev), split(new)
    out = []
    for line in difflib.ndiff(a, b):
        if line.startswith("+ "):
            out.append("ADDED: " + line[2:][:220])
        elif line.startswith("- "):
            out.append("REMOVED: " + line[2:][:220])
        if len(out) >= limit:
            break
    return out
