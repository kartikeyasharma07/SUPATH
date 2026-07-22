"""Yahoo Finance — the primary crude price source. No key, no registration.

Yahoo shut its official API down years ago, but the JSON endpoint that powers
finance.yahoo.com's own charts (`/v8/finance/chart/{ticker}`) still works and
returns clean, well-structured data. This is the same endpoint the popular
`yfinance` Python library calls under the hood — we hit it directly instead
of adding that dependency, since we already use httpx everywhere else.

Two honesty points, on purpose:

1. This is genuinely unofficial. Yahoo can change the endpoint or start
   blocking it without notice — there is no SLA and no support channel. If it
   ever breaks, the chain below falls through to EIA (official, needs a free
   key) and then to the documented static reference series, exactly like
   every other source in this app. Nothing here is load-bearing on its own.

2. Tickers BZ=F (ICE Brent Crude futures) and CL=F (NYMEX WTI Crude futures)
   are *futures* prices, not the physical spot prices EIA reports — which is
   actually the point: this is the same benchmark most financial tickers and
   news sites quote, so it is the number a reader expects to see, not the one
   most likely to look "wrong" next to Google.
"""

from __future__ import annotations

import datetime as _dt

import httpx

from ..config import CACHE, LIVE, SETTINGS, sourced

YAHOO_LABEL = "Yahoo Finance — Brent/WTI front-month futures"
YAHOO_HOME = "https://finance.yahoo.com/quote/BZ=F"
YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart"
TICKERS = {"BRENT": "BZ=F", "WTI": "CL=F"}

# Yahoo's own site sends a browser User-Agent on every request; the endpoint
# returns an empty/blocked response without one. This is not a secret or a
# credential — it is exactly what your own browser sends automatically —
# there is nothing here to protect and nothing that belongs in an env var.
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

STATUS: dict[str, dict] = {
    "BZ=F": {"ok": None, "detail": "not attempted yet"},
    "CL=F": {"ok": None, "detail": "not attempted yet"},
}


async def _fetch_series(ticker: str) -> list[tuple[str, float]] | None:
    cache_key = f"yahoo:{ticker}"
    cached = CACHE.get(cache_key, ttl=600)
    if cached is not None:
        return cached
    try:
        async with httpx.AsyncClient(timeout=SETTINGS.http_timeout) as client:
            r = await client.get(f"{YAHOO_URL}/{ticker}", params={"range": "3mo", "interval": "1d"},
                                 headers=_HEADERS)
        if r.status_code != 200:
            STATUS[ticker] = {"ok": False, "detail": f"HTTP {r.status_code}: {r.text[:200]}"}
            return None
        body = r.json()
        results = body.get("chart", {}).get("result")
        if not results:
            err = body.get("chart", {}).get("error")
            STATUS[ticker] = {"ok": False, "detail": f"no result in response: {err or str(body)[:200]}"}
            return None
        result = results[0]
        timestamps = result.get("timestamp") or []
        closes = (result.get("indicators", {}).get("quote") or [{}])[0].get("close") or []
        if not timestamps or not closes or len(timestamps) != len(closes):
            STATUS[ticker] = {"ok": False,
                              "detail": f"timestamp/close length mismatch or empty "
                                        f"({len(timestamps)} vs {len(closes)})"}
            return None

        out = []
        for ts, close in zip(timestamps, closes):
            if close is None:
                continue
            d = _dt.datetime.fromtimestamp(ts, tz=_dt.timezone.utc).date().isoformat()
            out.append((d, round(float(close), 2)))
        # Same trading day can appear twice across timezones at the edges —
        # keep the last (most complete) bar for any duplicate date.
        dedup = {}
        for d, p in out:
            dedup[d] = p
        out = sorted(dedup.items())
        if not out:
            STATUS[ticker] = {"ok": False, "detail": "request succeeded but produced zero usable rows"}
            return None

        STATUS[ticker] = {"ok": True, "detail": f"{len(out)} rows, latest {out[-1][0]} = {out[-1][1]}"}
        CACHE.set(cache_key, out)
        return out
    except httpx.TimeoutException:
        STATUS[ticker] = {"ok": False, "detail": f"timed out after {SETTINGS.http_timeout}s"}
        return None
    except Exception as exc:
        STATUS[ticker] = {"ok": False, "detail": f"{type(exc).__name__}: {exc}"}
        return None


async def fetch_brent() -> list[tuple[str, float]] | None:
    return await _fetch_series(TICKERS["BRENT"])


async def fetch_wti() -> list[tuple[str, float]] | None:
    return await _fetch_series(TICKERS["WTI"])


def status() -> dict:
    return STATUS
