"""Small HTTP helper with a polite User-Agent and short timeouts."""
from __future__ import annotations

import requests

_session = requests.Session()


def set_contact(email: str) -> None:
    # Government sites (BLS, Fed) ask automated clients to identify themselves.
    ua = "nq-newsbot/1.0"
    if email:
        ua += f" (contact: {email})"
    _session.headers["User-Agent"] = ua


def get(url: str, timeout: float = 8.0, **kw) -> requests.Response:
    r = _session.get(url, timeout=timeout, **kw)
    r.raise_for_status()
    return r


def post(url: str, timeout: float = 8.0, **kw) -> requests.Response:
    r = _session.post(url, timeout=timeout, **kw)
    r.raise_for_status()
    return r


set_contact("")
