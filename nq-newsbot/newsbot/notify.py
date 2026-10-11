"""Sends alerts to Telegram and/or Discord, prints them, and can read them aloud."""
from __future__ import annotations

from . import net


class Notifier:
    def __init__(self, cfg):
        self.cfg = cfg
        self._tts = None
        if cfg.speak:
            try:
                import pyttsx3          # optional: pip install pyttsx3
                self._tts = pyttsx3.init()
            except Exception as e:
                print(f"[notify] voice off ({e})")

    def send(self, text: str, speak_text: str | None = None) -> None:
        print("\n" + "=" * 60 + "\n" + text + "\n" + "=" * 60, flush=True)
        if self.cfg.telegram_token and self.cfg.telegram_chat_id:
            try:
                net.post(f"https://api.telegram.org/bot{self.cfg.telegram_token}/sendMessage",
                          json={"chat_id": self.cfg.telegram_chat_id, "text": text[:4000],
                                "disable_web_page_preview": True})
            except Exception as e:
                print(f"[notify] Telegram failed: {e}")
        if self.cfg.discord_webhook:
            try:
                net.post(self.cfg.discord_webhook, json={"content": text[:1900]})
            except Exception as e:
                print(f"[notify] Discord failed: {e}")
        if self._tts and speak_text:
            try:
                self._tts.say(speak_text)
                self._tts.runAndWait()
            except Exception as e:
                print(f"[notify] voice failed: {e}")
