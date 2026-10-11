"""Loads config.toml and fills in defaults."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_KEYWORDS = {
    # weight: how strongly a headline with this word matters for NQ
    "fed": 3, "fomc": 4, "powell": 4, "rate hike": 4, "rate cut": 4, "minutes": 2,
    "cpi": 4, "inflation": 3, "ppi": 3, "payrolls": 4, "jobs report": 4, "unemployment": 3,
    "treasury": 2, "yield": 2, "auction": 2,
    "iran": 3, "hormuz": 4, "israel": 2, "missile": 3, "strike": 2, "ceasefire": 3,
    "oil": 2, "brent": 2, "opec": 2, "saudi": 2, "pipeline": 2, "tanker": 2,
    "tariff": 4, "sanction": 3, "export control": 4, "china": 2, "taiwan": 3,
    "nvidia": 3, "apple": 3, "microsoft": 3, "amazon": 2, "alphabet": 2, "google": 2,
    "meta": 2, "tesla": 2, "broadcom": 2, "amd": 2, "micron": 2, "tsmc": 3,
    "openai": 3, "anthropic": 3, "ai chip": 3, "semiconductor": 3,
    "nasdaq": 2, "futures": 1, "s&p 500": 1, "trump": 2, "white house": 2, "shutdown": 3,
}

DEFAULT_FEEDS = [
    # Fed press releases (statements, minutes, speeches announcements)
    "https://www.federalreserve.gov/feeds/press_all.xml",
    # Google News searches, limited to the last hour
    "https://news.google.com/rss/search?q=Nasdaq+futures+when:1h&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=Federal+Reserve+when:1h&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=Iran+oil+Hormuz+when:1h&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=Nvidia+OR+Apple+OR+OpenAI+stock+when:1h&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=tariffs+OR+%22export+controls%22+when:1h&hl=en-US&gl=US&ceid=US:en",
    # CNBC top news
    "https://www.cnbc.com/id/100003114/device/rss/rss.html",
]


@dataclass
class Config:
    telegram_token: str = ""
    telegram_chat_id: str = ""
    discord_webhook: str = ""
    speak: bool = False
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-haiku-4-5-20251001"
    bls_api_key: str = ""
    contact_email: str = ""          # sent in the User-Agent, which official sites ask for
    timezone: str = "America/Vancouver"
    regime: str = "inflation"         # "inflation" (Fed hiking) or "growth" (Fed cutting on weak data)
    headline_start: str = "05:00"     # local time to start watching headlines
    headline_end: str = "13:30"
    headline_poll_seconds: int = 30
    min_headline_score: int = 4
    feeds: list[str] = field(default_factory=lambda: list(DEFAULT_FEEDS))
    keywords: dict[str, int] = field(default_factory=lambda: dict(DEFAULT_KEYWORDS))
    state_file: str = "state.json"


def load(path: str | Path = "config.toml") -> Config:
    p = Path(path)
    cfg = Config()
    if not p.exists():
        return cfg
    data = tomllib.loads(p.read_text(encoding="utf-8"))
    for section in ("alerts", "ai", "data", "schedule", "headlines"):
        for k, v in data.get(section, {}).items():
            if k == "extra_keywords":
                cfg.keywords.update({str(a).lower(): int(b) for a, b in v.items()})
            elif k == "extra_feeds":
                cfg.feeds.extend(v)
            elif hasattr(cfg, k):
                setattr(cfg, k, v)
    return cfg
