"""Command line:
  python -m newsbot run        start watching (leave it running during the trading day)
  python -m newsbot calendar   show this week's high and medium-impact US events in your time zone
  python -m newsbot test       send a test alert to check Telegram/Discord/voice
  python -m newsbot demo       run sample CPI, Fed and headline data through the analysis (no internet needed)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from . import bls, config, econcal, fed, headlines, impact, rss
from .bot import Bot
from .notify import Notifier

FIX = Path(__file__).resolve().parent.parent / "tests" / "fixtures"


def demo(cfg):
    events = econcal.parse(json.loads((FIX / "ff_calendar.json").read_text()), impacts=("High", "Medium"))
    readings = bls.parse_response("CPI", json.loads((FIX / "bls_cpi.json").read_text()))
    fc = {r.label: econcal.forecast_for(events, r.label) for r in readings}
    v = impact.judge_data(readings, fc)
    print("CPI demo:", v.headline()); print("\n".join(v.lines)); print("Why:", v.reason, "\n")
    text = fed.page_text((FIX / "fomc_statement.html").read_text())
    prev = fed.page_text((FIX / "fomc_statement_prev.html").read_text())
    f = fed.facts(text)
    fv = impact.judge_fed(f.decision, f.upper, econcal.forecast_for(events, "Federal Funds Rate"), f.dissents)
    print("Fed demo:", fv.headline()); print("\n".join(fv.lines)); print("Why:", fv.reason)
    for c in fed.wording_changes(prev, text):
        print("  ", c)
    print()
    items = rss.parse_feed((FIX / "google_news.xml").read_text())
    for s, it, hits in headlines.new_important(items, set(), cfg.keywords, cfg.min_headline_score):
        print(f"Headline [{headlines.tone(it.title)}, score {s}]: {it.title}")


def main(argv=None):
    argv = argv or sys.argv[1:]
    cmd = argv[0] if argv else "run"
    cfg = config.load(Path("config.toml"))
    if cmd == "run":
        Bot(cfg).run()
    elif cmd == "calendar":
        b = Bot(cfg)
        b.refresh_calendar(force=True)
        for e in b.events:
            print(f"{e.when.astimezone(b.tz):%a %b %d %I:%M %p}  [{e.impact}] {e.title}  forecast {e.forecast or '-'}  previous {e.previous or '-'}")
    elif cmd == "test":
        Notifier(cfg).send("Test alert from your NQ news bot. If you see this, alerts work.", speak_text="Test alert. Alerts work.")
    elif cmd == "demo":
        demo(cfg)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
