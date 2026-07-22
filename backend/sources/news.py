"""GDELT DOC 2.0 — the news signal layer.

GDELT is the only free source that gives us *global, near-real-time, machine-
readable* news with tone. We query it per corridor with a hand-written boolean
query, because a generic "oil news" feed is noise: what we need to know is
whether something happened *in the water India's crude actually crosses*.

Every article that survives the filter keeps its URL and domain, so any
recommendation built on it can cite it. No signal without a citation.

Optional enrichment: if GDELT_CLOUD_API_KEY is set, real classified Conflict
Events from gdeltcloud.com (Goldstein-scored, not keyword-matched) are merged
into the same article list — a strictly better signal where it's available,
never a replacement for the free DOC path when it isn't.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

import httpx

from ..config import CACHE, CACHED, LIVE, SETTINGS, UNAVAILABLE, sourced
from ..reference import CORRIDORS
from . import gdeltcloud

GDELT_LABEL = "GDELT DOC 2.0 API"
GDELT_HOME = "https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/"

# Corridor -> supplier-country ISO3 list, reused as-is for GDELT Cloud's
# Events `country` filter — reference.py already carries exactly this data.
_CORRIDOR_COUNTRIES = {c["id"]: c.get("suppliers", []) for c in CORRIDORS}

# Corridor-specific queries. Kept explicit and readable so a domain expert can
# challenge them — an opaque query is an unexplainable model.
CORRIDOR_QUERIES = {
    "GULF_HORMUZ":
        '("Strait of Hormuz" OR "Persian Gulf" OR "Iran tanker" OR "Gulf shipping" '
        'OR "Ras Tanura" OR "Basrah") (oil OR crude OR tanker OR shipping)',
    "REDSEA_SUEZ":
        '("Red Sea" OR "Bab el-Mandeb" OR Houthi OR "Suez Canal" OR "Gulf of Aden") '
        '(tanker OR shipping OR crude OR attack OR vessel)',
    "CAPE":
        '("Cape of Good Hope" OR "Cape route" OR "West Africa oil" OR Nigeria OR Angola) '
        '(tanker OR crude OR shipping OR pipeline)',
    "MALACCA_PACIFIC":
        '("Strait of Malacca" OR "South China Sea" OR ESPO OR Kozmino) '
        '(tanker OR crude OR shipping OR sanctions)',
    "US_GULF":
        '("US Gulf Coast" OR "Gulf of Mexico" OR "Corpus Christi" OR "US crude exports") '
        '(crude OR tanker OR hurricane OR export)',
}

INDIA_QUERY = (
    '(India OR Indian) (crude OR "oil imports" OR refinery OR OPEC OR "petrol price" '
    'OR "diesel price" OR "strategic petroleum reserve")'
)

# Words that escalate an article from "coverage" to "signal".
ESCALATION_TERMS = {
    "attack": 1.0, "strike": 0.9, "missile": 1.0, "drone": 0.8, "seized": 1.0,
    "seizure": 1.0, "blockade": 1.0, "closure": 1.0, "close": 0.5, "halt": 0.8,
    "suspend": 0.7, "explosion": 0.9, "fire": 0.5, "sanction": 0.7,
    "sanctions": 0.7, "embargo": 0.9, "war": 0.8, "conflict": 0.6,
    "escalat": 0.7, "threat": 0.5, "hijack": 1.0, "detain": 0.8,
    "cyclone": 0.7, "storm": 0.5, "congestion": 0.4, "backlog": 0.4,
    "disruption": 0.6, "outage": 0.6, "shut": 0.5,
}


def _escalation(title: str) -> float:
    t = title.lower()
    hits = [w for w in ESCALATION_TERMS if w in t]
    if not hits:
        return 0.0
    return min(1.0, max(ESCALATION_TERMS[w] for w in hits))


def _matched_terms(title: str) -> list[str]:
    t = title.lower()
    return sorted({w for w in ESCALATION_TERMS if w in t})


def _parse_seendate(s: str) -> str:
    try:
        return datetime.strptime(s, "%Y%m%dT%H%M%SZ").replace(
            tzinfo=timezone.utc).isoformat(timespec="minutes")
    except Exception:
        return s


async def _query(q: str, timespan: str = "24h", n: int = 30) -> list[dict] | None:
    params = {
        "query": q, "mode": "ArtList", "format": "json",
        "maxrecords": n, "timespan": timespan, "sort": "DateDesc",
    }
    try:
        async with httpx.AsyncClient(timeout=SETTINGS.http_timeout) as client:
            r = await client.get(SETTINGS.gdelt_url, params=params,
                                 headers={"User-Agent": "SUPATH/1.0 (energy-resilience-research)"})
            r.raise_for_status()
            data = r.json()
    except Exception:
        return None

    out = []
    for a in data.get("articles", []):
        title = re.sub(r"\s+", " ", a.get("title", "")).strip()
        if not title:
            continue
        out.append({
            "title": title,
            "url": a.get("url", ""),
            "domain": a.get("domain", ""),
            "seen": _parse_seendate(a.get("seendate", "")),
            "language": a.get("language", ""),
            "escalation": round(_escalation(title), 2),
            "terms": _matched_terms(title),
        })
    return out


def _goldstein_to_escalation(goldstein) -> float:
    """Goldstein runs -10 (maximally destabilising) to +10 (maximally
    cooperative) — map the destabilising half onto our 0-1 escalation scale.
    A missing score reads as a moderate, not-alarming 0.4 rather than 0."""
    if not isinstance(goldstein, (int, float)):
        return 0.4
    return round(min(1.0, max(0.0, -goldstein / 10.0)), 2)


async def _cloud_events_as_articles(corridor_id: str, timespan: str) -> list[dict] | None:
    countries = _CORRIDOR_COUNTRIES.get(corridor_id)
    if not countries or not gdeltcloud.configured():
        return None
    days = 1 if timespan.lower() in ("24h", "1d") else 7
    result = await gdeltcloud.corridor_events(countries, days=days)
    if not result or not result["events"]:
        return None
    out = []
    for e in result["events"]:
        esc = _goldstein_to_escalation(e.get("goldstein"))
        out.append({
            "title": e["title"], "url": e.get("url") or gdeltcloud.GDELT_CLOUD_HOME,
            "domain": "gdeltcloud.com", "seen": e.get("seen") or "",
            "language": "en", "escalation": esc,
            "terms": [e["category"]] if e.get("category") else [],
        })
    return out


async def corridor_news(corridor_id: str, timespan: str = "24h") -> dict:
    key = f"news:{corridor_id}:{timespan}:v2"
    cached = CACHE.get(key, ttl=900)
    if cached:
        return cached

    q = CORRIDOR_QUERIES.get(corridor_id)
    doc_articles = await _query(q, timespan) if q else None
    cloud_articles = await _cloud_events_as_articles(corridor_id, timespan)

    if doc_articles is None and cloud_articles is None:
        stale = CACHE.stale(key)
        if stale:
            stale["_mode"] = CACHED
            return stale
        payload = sourced([], source=GDELT_LABEL, url=GDELT_HOME, mode=UNAVAILABLE,
                          method="GDELT unreachable. Conflict term contributes its "
                                 "neutral prior (0.35) to the risk score instead of a "
                                 "live reading, and the UI marks the term as degraded.")
        return payload

    articles = (doc_articles or []) + (cloud_articles or [])
    articles.sort(key=lambda a: (-a["escalation"], a["seen"]), reverse=False)
    articles.sort(key=lambda a: a["escalation"], reverse=True)

    if cloud_articles:
        source_label = (f"{GDELT_LABEL} + {gdeltcloud.GDELT_CLOUD_LABEL}" if doc_articles
                        else gdeltcloud.GDELT_CLOUD_LABEL)
        method = (f"{len(doc_articles or [])} DOC 2.0 keyword-matched articles + "
                 f"{len(cloud_articles)} classified Conflict Events from GDELT Cloud "
                 f"(Goldstein-scored, not keyword-matched), timespan={timespan}.")
    else:
        source_label, method = GDELT_LABEL, f"GDELT DOC 2.0 ArtList, timespan={timespan}, corridor query: {q}"

    payload = sourced(articles, source=source_label, url=GDELT_HOME, mode=LIVE, method=method)
    payload["query"] = q
    CACHE.set(key, payload)
    return payload


async def india_news(timespan: str = "24h") -> dict:
    key = f"news:INDIA:{timespan}"
    cached = CACHE.get(key, ttl=900)
    if cached:
        return cached
    articles = await _query(INDIA_QUERY, timespan, n=25)
    if articles is None:
        stale = CACHE.stale(key)
        if stale:
            return stale
        return sourced([], source=GDELT_LABEL, url=GDELT_HOME, mode=UNAVAILABLE)
    payload = sourced(articles, source=GDELT_LABEL, url=GDELT_HOME, mode=LIVE,
                      method=f"GDELT DOC 2.0 ArtList, timespan={timespan}, query: {INDIA_QUERY}")
    CACHE.set(key, payload)
    return payload


def conflict_subscore(articles: list[dict]) -> dict:
    """Turn a corridor's article set into a 0–1 conflict term, showing the work.

    volume term : how loudly the corridor is being written about (log-scaled,
                  saturating at 30 articles/24h)
    severity term: the mean escalation weight of the top 5 articles

    We take a weighted blend so that a single very severe report still moves the
    score even in a quiet news cycle — which is the case that actually matters.
    """
    n = len(articles)
    if n == 0:
        return {"score": 0.35, "n": 0, "volume_term": 0.0, "severity_term": 0.0,
                "top_terms": [], "note": "No corridor articles retrieved; neutral prior applied."}

    from math import log

    volume_term = min(1.0, log(1 + n) / log(31))
    top = sorted(articles, key=lambda a: -a["escalation"])[:5]
    severity_term = sum(a["escalation"] for a in top) / max(1, len(top))
    score = round(0.35 * volume_term + 0.65 * severity_term, 3)

    terms: dict[str, int] = {}
    for a in articles:
        for t in a["terms"]:
            terms[t] = terms.get(t, 0) + 1
    top_terms = sorted(terms.items(), key=lambda kv: -kv[1])[:5]

    return {
        "score": min(1.0, score),
        "n": n,
        "volume_term": round(volume_term, 3),
        "severity_term": round(severity_term, 3),
        "top_terms": [{"term": t, "count": c} for t, c in top_terms],
        "note": f"{n} corridor articles in window; blended 0.35×volume + 0.65×severity.",
    }
