"""Offline tests. Run from the project folder:  python -m unittest -v"""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from newsbot import bls, config, econcal, fed, headlines, impact, rss
from newsbot.bot import Bot

FIX = Path(__file__).parent / "fixtures"


def cfg_tmp():
    c = config.Config()
    c.state_file = str(Path(tempfile.mkdtemp()) / "state.json")
    return c


class Calendar(unittest.TestCase):
    def test_parse_filters_usd_and_impact(self):
        ev = econcal.parse(json.loads((FIX / "ff_calendar.json").read_text()))
        titles = [e.title for e in ev]
        self.assertIn("CPI m/m", titles)
        self.assertNotIn("German ZEW", titles)              # not USD
        self.assertNotIn("Crude Oil Inventories", titles)   # Medium, not asked for

    def test_numbers(self):
        self.assertEqual(econcal.parse_number("0.3%"), 0.3)
        self.assertEqual(econcal.parse_number("120K"), 120000)
        self.assertEqual(econcal.parse_number("-1.2M"), -1200000)
        self.assertIsNone(econcal.parse_number(""))


class BLS(unittest.TestCase):
    def test_cpi_changes(self):
        r = {x.label: x for x in bls.parse_response("CPI", json.loads((FIX / "bls_cpi.json").read_text()))}
        self.assertEqual(r["Core CPI m/m"].value, 0.4)
        self.assertEqual(r["CPI m/m"].period, "2026-09")
        self.assertAlmostEqual(r["CPI y/y"].value, 3.7, places=1)

    def test_payroll_diff(self):
        pts = [("2026-10", 159250.0), ("2026-09", 159100.0)]
        self.assertEqual(bls.compute("diff_k", pts), 150)


class Impact(unittest.TestCase):
    R = bls.Reading

    def test_hot_core_cpi_is_negative(self):
        v = impact.judge_data([self.R("Core CPI m/m", 0.5, "2026-09", "%")], {"Core CPI m/m": 0.3})
        self.assertEqual((v.label, v.strength), ("Negative", "strongly"))

    def test_cool_cpi_is_positive(self):
        v = impact.judge_data([self.R("Core CPI m/m", 0.2, "2026-09", "%")], {"Core CPI m/m": 0.3})
        self.assertEqual(v.label, "Positive")

    def test_in_line_is_neutral(self):
        v = impact.judge_data([self.R("CPI m/m", 0.3, "2026-09", "%")], {"CPI m/m": 0.3})
        self.assertEqual(v.label, "Neutral")

    def test_jobs_depend_on_regime(self):
        r = [self.R("Non-Farm Employment Change", 250, "2026-10", "K")]
        fc = {"Non-Farm Employment Change": 120000.0}
        self.assertEqual(impact.judge_data(r, fc, "inflation").label, "Negative")
        self.assertEqual(impact.judge_data(r, fc, "growth").label, "Positive")

    def test_fed_surprise_hike(self):
        self.assertEqual(impact.judge_fed("hike", 5.25, 5.0, 0).label, "Negative")
        self.assertEqual(impact.judge_fed("hold", 5.0, 5.0, 0).label, "Neutral")
        self.assertEqual(impact.judge_fed("cut", 4.75, 5.0, 0).label, "Positive")


class Fed(unittest.TestCase):
    def test_facts_from_statement(self):
        f = fed.facts(fed.page_text((FIX / "fomc_statement.html").read_text()))
        self.assertEqual((f.decision, f.lower, f.upper, f.dissents), ("hike", 4.75, 5.0, 2))

    def test_article_only(self):
        text = fed.page_text((FIX / "fomc_statement.html").read_text())
        self.assertNotIn("Board of Governors", text)        # header skipped
        self.assertNotIn("Last update", text)               # footer skipped

    def test_wording_changes(self):
        a = fed.page_text((FIX / "fomc_statement_prev.html").read_text())
        b = fed.page_text((FIX / "fomc_statement.html").read_text())
        ch = fed.wording_changes(a, b)
        self.assertTrue(any(c.startswith("ADDED: Inflation has moved up") for c in ch))

    def test_statement_and_minutes_titles(self):
        self.assertTrue(fed.is_statement(rss.Item("Federal Reserve issues FOMC statement", "", "")))
        self.assertTrue(fed.is_minutes(rss.Item("Minutes of the Federal Open Market Committee, September 15-16, 2026", "", "")))
        self.assertFalse(fed.is_statement(rss.Item("Federal Reserve Board announces approval of application", "", "")))


class Headlines(unittest.TestCase):
    def test_dedupe_and_score(self):
        items = rss.parse_feed((FIX / "google_news.xml").read_text())
        found = headlines.new_important(items, set(), config.DEFAULT_KEYWORDS, 4)
        titles = [it.title for _, it, _ in found]
        self.assertEqual(len(titles), 2)                    # duplicate Iran story and bakery dropped
        self.assertTrue(titles[0].startswith("Iran"))

    def test_tone(self):
        self.assertEqual(headlines.tone("US launches strike on Iranian oil terminal"), "likely negative")
        self.assertEqual(headlines.tone("US and Iran agree ceasefire"), "likely positive")


class BotFlow(unittest.TestCase):
    """Runs the alert paths with the network mocked out."""

    def setUp(self):
        self.cfg = cfg_tmp()
        self.bot = Bot(self.cfg)
        self.bot.events = econcal.parse(json.loads((FIX / "ff_calendar.json").read_text()), impacts=("High", "Medium"))
        self.sent = []
        self.bot.notify.send = lambda text, speak_text=None: self.sent.append(text)

    def test_cpi_alert_message(self):
        readings = bls.parse_response("CPI", json.loads((FIX / "bls_cpi.json").read_text()))
        self.bot.alert_data("CPI", readings, "2026-09")
        msg = self.sent[0]
        self.assertIn("CPI RELEASED (September data)", msg)
        self.assertIn("Strongly negative for NQ", msg)
        self.assertIn("Core CPI m/m: 0.4% vs 0.3% expected", msg)

    def test_catch_bls_waits_for_new_month(self):
        old = json.loads((FIX / "bls_cpi.json").read_text())
        # baseline: August is the newest month; then September appears
        aug = json.loads(json.dumps(old))
        for s in aug["Results"]["series"]:
            s["data"] = s["data"][1:]
        calls = iter([aug, aug, old])
        due = datetime.now(timezone.utc) + timedelta(seconds=1)
        with mock.patch("newsbot.bls.fetch", side_effect=lambda *a, **k: next(calls)), \
             mock.patch("newsbot.bot.time.sleep", lambda s: None):
            self.bot.catch_bls("CPI", due)
        self.assertEqual(len(self.sent), 1)
        self.assertIn("September data", self.sent[0])

    def test_fed_statement_alert(self):
        html = (FIX / "fomc_statement.html").read_text()
        item = rss.Item("Federal Reserve issues FOMC statement",
                        "https://www.federalreserve.gov/newsevents/pressreleases/monetary20261028a.htm", "")
        with mock.patch("newsbot.fed.poll", return_value=[item]), \
             mock.patch("newsbot.net.get", return_value=mock.Mock(text=html)):
            self.bot.poll_fed()
            self.bot.poll_fed()          # second poll must not alert again
        self.assertEqual(len(self.sent), 1)
        self.assertIn("FOMC STATEMENT", self.sent[0])
        self.assertIn("Decision: hike, upper bound 5.00%", self.sent[0])

    def test_digest_lists_today(self):
        now = datetime(2026, 10, 14, 5, 0, tzinfo=self.bot.tz)
        with mock.patch.object(Bot, "now", return_value=now):
            d = self.bot.digest()
        self.assertIn("5:30 AM  [High] CPI m/m | forecast 0.3%", d)
        self.assertIn("7:30 AM  [Medium] Crude Oil Inventories", d)


class Config(unittest.TestCase):
    def test_load_toml(self):
        p = Path(tempfile.mkdtemp()) / "config.toml"
        p.write_text('[alerts]\ntelegram_chat_id = "123"\n[headlines]\nmin_headline_score = 6\n'
                     'extra_feeds = ["https://x.example/rss"]\n[headlines.extra_keywords]\npalantir = 2\n')
        c = config.load(p)
        self.assertEqual((c.telegram_chat_id, c.min_headline_score), ("123", 6))
        self.assertIn("https://x.example/rss", c.feeds)
        self.assertEqual(c.keywords["palantir"], 2)


if __name__ == "__main__":
    unittest.main()
