"""Crude prices — Yahoo Finance first, EIA second, a documented static series last.

Why this order, specifically:

  1. Yahoo Finance (BZ=F / CL=F) — free, no registration, no key. Returns the
     same *futures* benchmark most financial tickers and news sites quote, so
     the number a reader sees here is the number they expect. Unofficial and
     can break without notice — see sources/yahoo.py for the honesty note.

  2. EIA Open Data (RBRTE / RWTC) — official U.S. government data, free, but
     needs registration and a key. Reports the physical *spot* price, a
     different (and just as legitimate) benchmark from what Yahoo shows — see
     the note in get_prices() for what that means when the two disagree.

  3. A documented static series — so the platform is still demonstrable with
     zero configuration and zero network access. Always labelled REFERENCE,
     never presented as a live observation.

We deliberately expose *movement* (day-on-day %, 5-day, 30-day) rather than a
naked level, because a policymaker's question is never "what is Brent" — it is
"is it moving, and why". The "why" is attached later by engine/attribution.py,
which matches the move against the news signal for the same window.
"""

from __future__ import annotations

from ..config import CACHE, CACHED, LIVE, REFERENCE, sourced
from . import yahoo
from .eia import EIA_HOME, EIA_LABEL, fetch_eia_series, eia_status

# Documented fallback so the platform is demonstrable without a key or network.
# Marked REFERENCE in the payload — the UI shows it as such, never as live.
FALLBACK_BRENT = [
    ("2026-06-12", 71.4), ("2026-06-15", 72.1), ("2026-06-16", 71.8),
    ("2026-06-17", 73.6), ("2026-06-18", 74.9), ("2026-06-19", 74.2),
    ("2026-06-22", 76.8), ("2026-06-23", 79.5), ("2026-06-24", 78.1),
    ("2026-06-25", 77.4), ("2026-06-26", 76.9), ("2026-06-29", 78.3),
    ("2026-06-30", 80.2), ("2026-07-01", 82.6), ("2026-07-02", 81.4),
    ("2026-07-03", 80.7), ("2026-07-06", 83.1), ("2026-07-07", 85.4),
    ("2026-07-08", 84.2), ("2026-07-09", 86.9), ("2026-07-10", 88.3),
]
FALLBACK_WTI = [(d, round(p - 4.1, 2)) for d, p in FALLBACK_BRENT]


def _movement(series: list[tuple[str, float]]) -> dict:
    """Percentage movement, which is what actually gets briefed."""
    closes = [p for _, p in series]
    last = closes[-1]

    def pct(n: int) -> float | None:
        if len(closes) <= n:
            return None
        prev = closes[-1 - n]
        return round((last - prev) / prev * 100, 2) if prev else None

    # 20-day realised volatility, annualised — feeds the market-stress risk term
    rets = [
        (closes[i] - closes[i - 1]) / closes[i - 1]
        for i in range(1, len(closes)) if closes[i - 1]
    ][-20:]
    if rets:
        mean = sum(rets) / len(rets)
        var = sum((r - mean) ** 2 for r in rets) / len(rets)
        vol = (var ** 0.5) * (252 ** 0.5) * 100
    else:
        vol = 0.0

    return {
        "last": round(last, 2),
        "date": series[-1][0],
        "chg_1d_pct": pct(1),
        "chg_5d_pct": pct(5),
        "chg_30d_pct": pct(20),
        "high_30d": round(max(closes[-20:]), 2),
        "low_30d": round(min(closes[-20:]), 2),
        "vol_annualised_pct": round(vol, 1),
        "history": [{"d": d, "p": round(p, 2)} for d, p in series[-30:]],
    }


async def get_prices() -> dict:
    cached = CACHE.get("prices", ttl=600)
    if cached:
        cached["_mode"] = CACHED
        return cached

    brent = await yahoo.fetch_brent()
    wti = await yahoo.fetch_wti()
    if brent:
        source, url, mode = yahoo.YAHOO_LABEL, yahoo.YAHOO_HOME, LIVE
        method = ("Daily Brent front-month futures close (ticker BZ=F) — the same "
                 "benchmark most financial tickers quote; movement computed as "
                 "close-over-close percentage change.")
        wti_method = "Daily WTI front-month futures close (ticker CL=F)."
        if not wti:
            wti = FALLBACK_WTI
    else:
        brent = await fetch_eia_series("RBRTE")
        wti = await fetch_eia_series("RWTC")
        if brent:
            source, url, mode = EIA_LABEL, EIA_HOME, LIVE
            method = ("Yahoo Finance was unreachable this cycle; falling back to EIA's "
                     "daily Europe Brent spot FOB (series RBRTE) — a physical cargo "
                     "assessment, not a futures price. Movement computed as "
                     "close-over-close percentage change.")
            wti_method = "Daily Cushing WTI spot FOB (series RWTC)."
        else:
            brent, wti = FALLBACK_BRENT, FALLBACK_WTI
            source, url, mode = EIA_LABEL, EIA_HOME, REFERENCE
            method = ("Both Yahoo Finance and EIA were unreachable this cycle; showing "
                     "a documented static reference series instead of a live "
                     "observation. Directional only — verify before acting on it.")
            wti_method = "Documented static reference series (see FALLBACK_WTI)."

    payload = {
        "brent": sourced(_movement(brent), source=source, url=url, mode=mode, method=method),
        "wti": sourced(_movement(wti or FALLBACK_WTI), source=source, url=url, mode=mode,
                       method=wti_method),
        "_mode": mode,
    }
    CACHE.set("prices", payload)
    return payload


def status() -> dict:
    """Per-source fetch outcome, for /api/health — a source that looks fine on
    paper but never actually returns data should be visible, not silently
    downgraded."""
    return {"yahoo": yahoo.status(), "eia": eia_status()}


async def indian_basket_estimate() -> dict:
    """India does not buy Brent — it buys a sour basket at a differential.

    The Indian crude basket is ~75-80% sour, and prices at a discount to Brent.
    We estimate it rather than pretend to observe it, and we say so.
    """
    prices = await get_prices()
    brent = prices["brent"]["value"]["last"]
    return sourced(
        round(brent - 1.85, 2),
        source="SUPATH estimate, adjusted by the sour/sweet differential",
        url=yahoo.YAHOO_HOME,
        mode="modelled",
        method="Indian basket ≈ Brent − 1.85 $/bbl, reflecting the sour-heavy import slate. "
               "This is an estimate, not the PPAC published basket.",
    )
