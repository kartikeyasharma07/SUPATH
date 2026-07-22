"""GDELT Cloud (gdeltcloud.com) — an optional, higher-quality conflict signal.

This is a *different product* from the free GDELT DOC 2.0 API already used in
news.py — DOC 2.0 is the official GDELT Project's free, keyless full-text
search; GDELT Cloud is an independent third-party service that runs the same
raw GDELT article stream through its own classifier to produce structured,
de-duplicated Conflict Events with real Goldstein-scale severity scores,
instead of the keyword-substring matching news.py otherwise has to fall back
to. It requires a free account and a Bearer API key (gdelt_sk_...).

Two honesty notes, on purpose:

1. This module is best-effort against a genuinely new API (GDELT Cloud's own
   docs note its Events/Stories coverage only becomes reliable from March
   2026 onward, and that "schemas, classifiers, scoring logic... may change
   over time"). Every field read from the response is read defensively —
   a response shape we don't recognise degrades to "unavailable", the same
   as every other source in this app, rather than raising.

2. GDELT Cloud's Maritime & Trade endpoints (chokepoint transits, AIS-dark
   gap detection, port pulse) would be a genuinely strong fit for SUPATH — but
   they are plan-gated (`can_use_maritime`) behind a paid tier, not part of
   the free account. This module does not call them. Wiring them in against
   a free key would just return 403 PLAN_REQUIRED, which is worse than not
   building it.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx

from ..config import CACHE, SETTINGS

GDELT_CLOUD_LABEL = "GDELT Cloud — generated Conflict Events"
GDELT_CLOUD_HOME = "https://gdeltcloud.com/"

STATE: dict[str, Any] = {"ok": None, "detail": "not attempted yet", "sample_keys": None}


def configured() -> bool:
    return bool(SETTINGS.gdelt_cloud_key)


async def corridor_events(countries: list[str], days: int = 7) -> Optional[dict]:
    """Real classified Conflict Events for a corridor's supplier countries,
    over the trailing `days` (capped at 30 by GDELT Cloud itself). Returns
    None on anything unexpected — missing key, plan restriction, network
    failure, or a response shape this code doesn't recognise — so callers
    can fall back to the keyword-based signal exactly as if no key were set.
    """
    if not configured() or not countries:
        return None

    cache_key = f"gdeltcloud:{','.join(sorted(countries))}:{days}"
    cached = CACHE.get(cache_key, ttl=1800)
    if cached is not None:
        return cached

    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=min(days, 30))
    params = {
        "country": ",".join(countries),
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "limit": 25,
    }
    try:
        async with httpx.AsyncClient(timeout=SETTINGS.http_timeout) as client:
            r = await client.get(
                f"{SETTINGS.gdelt_cloud_url}/api/v2/events",
                params=params,
                headers={"Authorization": f"Bearer {SETTINGS.gdelt_cloud_key}"},
            )
        if r.status_code == 403:
            STATE.update(ok=False, detail="HTTP 403 — likely PLAN_REQUIRED "
                                          "(Events may need a paid plan tier on this key)")
            return None
        if r.status_code != 200:
            STATE.update(ok=False, detail=f"HTTP {r.status_code}: {r.text[:200]}")
            return None

        body = r.json()
        rows = body.get("data")
        if not isinstance(rows, list):
            STATE.update(ok=False, detail=f"unexpected response shape: {str(body)[:200]}")
            return None
        if rows:
            STATE["sample_keys"] = sorted(rows[0].keys()) if isinstance(rows[0], dict) else None

        events = []
        goldstein_vals = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            # Confirmed against a real response (2026-07-21): top-level keys are
            # actors, category, civilian_targeting[_label], coded_at, domain,
            # entity_refs, event_code, event_date, family, fatalities, geo,
            # geo_context, has_fatalities, id, image_url, language_breakdown,
            # metrics, primary_story_url, processed_at, story_refs, subcategory,
            # summary, title, top_articles, top_language, updated_at, url.
            # Goldstein lives inside `metrics`, not at the top level — the
            # first version of this code looked in the wrong place, which is
            # why avg_goldstein came back None even on a successful fetch.
            metrics = row.get("metrics") or {}
            gold = metrics.get("goldstein", metrics.get("goldstein_scale"))
            if isinstance(gold, (int, float)):
                goldstein_vals.append(float(gold))
            events.append({
                "title": row.get("title") or row.get("summary") or "Event",
                "url": row.get("primary_story_url") or row.get("url")
                       or ((row.get("top_articles") or [{}])[0].get("url", "")),
                "domain": row.get("domain") or "gdeltcloud.com",
                "seen": row.get("event_date") or row.get("coded_at") or "",
                "goldstein": gold,
                "category": row.get("category") or row.get("subcategory"),
            })

        avg_goldstein = sum(goldstein_vals) / len(goldstein_vals) if goldstein_vals else None
        result = {
            "count": len(events),
            "avg_goldstein": round(avg_goldstein, 2) if avg_goldstein is not None else None,
            "events": events,
        }
        CACHE.set(cache_key, result)
        STATE.update(ok=True, detail=f"{len(events)} events, avg goldstein "
                                      f"{result['avg_goldstein']}")
        return result
    except Exception as exc:
        STATE.update(ok=False, detail=f"{type(exc).__name__}: {exc}")
        return None


def status() -> dict:
    return {"configured": configured(), **STATE}
