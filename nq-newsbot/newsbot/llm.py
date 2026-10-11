"""Optional: asks Claude for a two-line summary and an NQ impact call.

Only used when anthropic_api_key is set in config.toml. Without it the bot still works,
using the rule-based read in impact.py.
"""
from __future__ import annotations

import json
import re

from . import net

API = "https://api.anthropic.com/v1/messages"

PROMPT = """You are a terse markets desk assistant for a trader of Nasdaq-100 futures (NQ).
Context: {context}

Text:
<<<
{text}
>>>

Reply with JSON only: {{"summary": "<= 2 short sentences on what was said or released",
"impact": "Negative" | "Neutral" | "Positive" (for NQ over the next hour),
"why": "<= 1 short sentence"}}"""


def summarise(cfg, text: str, context: str, timeout: float = 12.0) -> dict | None:
    if not cfg.anthropic_api_key:
        return None
    try:
        r = net.post(API, timeout=timeout,
                      headers={"x-api-key": cfg.anthropic_api_key, "anthropic-version": "2023-06-01",
                               "content-type": "application/json"},
                      json={"model": cfg.anthropic_model, "max_tokens": 300,
                            "messages": [{"role": "user", "content": PROMPT.format(context=context, text=text[:12000])}]})
        out = "".join(b.get("text", "") for b in r.json().get("content", []))
        m = re.search(r"\{.*\}", out, re.S)
        return json.loads(m.group(0)) if m else None
    except Exception as e:
        print(f"[llm] skipped: {e}")
        return None
