"""Main loop: watches the calendar, catches releases the second they post, and sends alerts."""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from . import bls, econcal, fed, headlines, impact, llm, net
from .notify import Notifier

FED_TITLES = {"federal funds rate": "statement", "fomc statement": "statement", "fomc meeting minutes": "minutes"}


class State:
    def __init__(self, path: str):
        self.path = Path(path)
        d = json.loads(self.path.read_text()) if self.path.exists() else {}
        self.seen: list[str] = d.get("seen", [])
        self.fed_links: list[str] = d.get("fed_links", [])
        self.last_statement: str = d.get("last_statement", "")
        self.handled: list[str] = d.get("handled", [])

    def save(self):
        self.path.write_text(json.dumps({"seen": self.seen[-5000:], "fed_links": self.fed_links[-500:],
                                         "last_statement": self.last_statement,
                                         "handled": self.handled[-500:]}))


class Bot:
    def __init__(self, cfg):
        self.cfg = cfg
        self.tz = ZoneInfo(cfg.timezone)
        net.set_contact(cfg.contact_email)
        self.notify = Notifier(cfg)
        self.state = State(cfg.state_file)
        self.events: list[econcal.Event] = []
        self.events_at = 0.0
        self.seen = set(self.state.seen)

    # ---------- helpers ----------
    def now(self) -> datetime:
        return datetime.now(self.tz)

    def stamp(self, dt: datetime | None = None) -> str:
        return (dt or self.now()).astimezone(self.tz).strftime("%a %I:%M:%S %p").replace(" 0", " ")

    def refresh_calendar(self, force=False):
        if force or time.time() - self.events_at > 1800:
            try:
                self.events = econcal.fetch(impacts=("High", "Medium"))
                self.events_at = time.time()
            except Exception as e:
                print(f"[calendar] failed, retrying in 1 minute: {e}")
                self.events_at = time.time() - 1740

    def forecasts(self, labels) -> dict[str, float | None]:
        return {l: econcal.forecast_for(self.events, l) for l in labels}

    def digest(self) -> str:
        today = self.now().date()
        rows = [e for e in self.events if e.when.astimezone(self.tz).date() == today]
        if not rows:
            return f"No high or medium-impact US events today ({today:%a %b %d})."
        lines = [f"TODAY'S US EVENTS ({today:%a %b %d}, {self.cfg.timezone.split('/')[-1]} time)"]
        for e in rows:
            t = e.when.astimezone(self.tz).strftime("%I:%M %p").lstrip("0")
            fc = f" | forecast {e.forecast}" if e.forecast else ""
            pv = f" | previous {e.previous}" if e.previous else ""
            lines.append(f"{t}  [{e.impact}] {e.title}{fc}{pv}")
        lines.append("Blackout: no entries 5 minutes either side of High-impact events.")
        return "\n".join(lines)

    # ---------- data releases (BLS) ----------
    def catch_bls(self, release: str, due: datetime):
        try:
            base = bls.latest_period(bls.parse_response(release, bls.fetch(release, self.cfg.bls_api_key)))
        except Exception as e:
            print(f"[bls] baseline failed: {e}")
            base = None
        while self.now() < due - timedelta(seconds=2):
            time.sleep(0.5)
        deadline = due + timedelta(minutes=4)
        while self.now() < deadline:
            try:
                readings = bls.parse_response(release, bls.fetch(release, self.cfg.bls_api_key))
                period = bls.latest_period(readings)
                if period and (base is None or period > base):
                    self.alert_data(release, readings, period)
                    return
            except Exception as e:
                print(f"[bls] {e}")
            time.sleep(3)
        self.notify.send(f"{release} was due at {self.stamp(due)} but the BLS API has not updated yet. "
                         f"Check bls.gov or your X notifications.")

    def alert_data(self, release, readings, period):
        fc = self.forecasts([r.label for r in readings])
        v = impact.judge_data(readings, fc, getattr(self.cfg, "regime", "inflation"))
        month = datetime.strptime(period, "%Y-%m").strftime("%B")
        msg = [f"{release} RELEASED ({month} data) at {self.stamp()}", f">> {v.headline()}"]
        msg += v.lines + [f"Why: {v.reason}"]
        ai = llm.summarise(self.cfg, "\n".join(v.lines), f"US {release} release for {month}; rule-based read: {v.headline()}")
        if ai:
            msg.append(f"AI: {ai.get('summary', '')} ({ai.get('impact', '?')}: {ai.get('why', '')})")
        msg.append("Rule: wait for the first 5-min candle to close before entering.")
        self.notify.send("\n".join(msg), speak_text=f"{release} released. {v.headline()}. {v.lines[0] if v.lines else ''}")

    # ---------- Fed ----------
    def poll_fed(self):
        try:
            items = fed.poll()
        except Exception as e:
            print(f"[fed] {e}")
            return
        for it in items:
            if it.link in self.state.fed_links:
                continue
            self.state.fed_links.append(it.link)
            if fed.is_statement(it) or fed.is_minutes(it):
                self.alert_fed(it)
        self.state.save()

    def alert_fed(self, item):
        try:
            text = fed.page_text(net.get(item.link).text)
        except Exception as e:
            text = ""
            print(f"[fed] page failed: {e}")
        if fed.is_statement(item):
            f = fed.facts(text)
            exp = econcal.forecast_for(self.events, "Federal Funds Rate")
            v = impact.judge_fed(f.decision, f.upper, exp, f.dissents)
            msg = [f"FOMC STATEMENT at {self.stamp()}", f">> {v.headline()}"] + v.lines + [f"Why: {v.reason}"]
            if self.state.last_statement and text:
                ch = fed.wording_changes(self.state.last_statement, text)
                if ch:
                    msg.append("Wording changes vs last statement:")
                    msg += [f"  {c}" for c in ch]
            if text:
                self.state.last_statement = text
            ai = llm.summarise(self.cfg, text, "FOMC policy statement; compare with expectations of a "
                                               f"{exp if exp is not None else 'unknown'}% upper bound")
            speak = f"F O M C statement. {v.headline()}."
        else:
            msg = [f"FOMC MINUTES at {self.stamp()}", "Minutes move markets through tone: count how many officials want more hikes."]
            ai = llm.summarise(self.cfg, text, "Minutes of the latest FOMC meeting")
            speak = "F O M C minutes are out."
        if ai:
            msg.append(f"AI: {ai.get('summary', '')} ({ai.get('impact', '?')}: {ai.get('why', '')})")
        msg.append(item.link)
        self.notify.send("\n".join(msg), speak_text=speak)

    # ---------- headlines ----------
    def in_headline_window(self) -> bool:
        n = self.now()
        if n.weekday() == 5:          # Saturday
            return False
        hm = n.strftime("%H:%M")
        return self.cfg.headline_start <= hm <= self.cfg.headline_end

    def poll_headlines(self, quiet=False):
        items = headlines.fetch_all(self.cfg.feeds)
        found = headlines.new_important(items, self.seen, self.cfg.keywords, self.cfg.min_headline_score)
        self.state.seen = list(self.seen)
        self.state.save()
        if quiet or not found:
            return
        lines = [f"HEADLINES {self.stamp()}"]
        for s, it, hits in found[:5]:
            src = f" ({it.source})" if it.source else ""
            lines.append(f"- [{headlines.tone(it.title)}, score {s}] {it.title}{src}")
        self.notify.send("\n".join(lines), speak_text=found[0][1].title)

    # ---------- main loop ----------
    def run(self):
        self.refresh_calendar(force=True)
        print(self.digest())
        self.poll_headlines(quiet=True)        # mark what is already out as seen
        try:
            for it in fed.poll():
                if it.link not in self.state.fed_links:
                    self.state.fed_links.append(it.link)
            self.state.save()
        except Exception as e:
            print(f"[fed] startup: {e}")
        self.notify.send("NQ news bot started.\n" + self.digest())
        last_head = last_fed = 0.0
        digest_day = self.now().date()
        while True:
            self.refresh_calendar()
            now = self.now()
            if now.date() != digest_day and now.strftime("%H:%M") >= "05:45":
                digest_day = now.date()
                self.notify.send(self.digest())
            # releases due in the next 60 seconds
            for e in self.events:
                secs = (e.when - now).total_seconds()
                if e.key in self.state.handled or not (-30 <= secs <= 60):
                    continue
                rel = bls.CALENDAR_TITLES.get(e.title)
                fed_kind = FED_TITLES.get(e.title.lower())
                if rel:
                    # one release covers several calendar lines (CPI m/m, Core CPI m/m...)
                    for x in self.events:
                        if bls.CALENDAR_TITLES.get(x.title) == rel and x.when == e.when:
                            self.state.handled.append(x.key)
                    self.state.save()
                    self.catch_bls(rel, e.when)
                elif fed_kind:
                    for x in self.events:
                        if x.title.lower() in FED_TITLES and x.when == e.when:
                            self.state.handled.append(x.key)
                    self.state.save()
                    end = e.when + timedelta(minutes=5)
                    while self.now() < end:
                        before = len(self.state.fed_links)
                        self.poll_fed()
                        if len(self.state.fed_links) > before:
                            break
                        time.sleep(2)
            if time.time() - last_fed > 60:
                self.poll_fed()
                last_fed = time.time()
            if self.in_headline_window() and time.time() - last_head > self.cfg.headline_poll_seconds:
                self.poll_headlines()
                last_head = time.time()
            time.sleep(1)
