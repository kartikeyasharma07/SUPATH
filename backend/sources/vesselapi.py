"""VesselAPI.com — a second, partial live-AIS layer.

Why partial, on purpose
------------------------
VesselAPI's free tier is 150 requests/month, and its bounding-box query is
capped at a 4-degree span (|dLat| + |dLon| <= 4). That is nowhere near enough
to cover five ocean corridors continuously — one honest pass over just the
Hormuz corridor's own geofence would blow the entire month's budget in a
single poll. So this module does not try to cover everything. It watches two
small, high-value windows — the Strait of Hormuz approach and the Gulf of
Kutch approach into Jamnagar/Vadinar — refreshed a few times a day, and lets
the deterministic corridor simulator (ais.py) continue to carry every corridor
those windows don't reach, exactly as it already does when no live key is
configured at all.

Why "unclassified", on purpose
-------------------------------
The bounding-box endpoint returns *any* AIS-transmitting vessel in the box —
cargo ships, tankers, fishing boats — not just tankers. Confirming a hull's
type costs a second, per-vessel request we cannot afford on this budget. So
every contact from this module is surfaced honestly as an unclassified AIS
position, not a confirmed tanker — drawn on the map as a plain dot, never the
tanker icon used for aisstream's live feed or the simulator's SIM fleet.

Quota governance
-----------------
A local monthly counter refuses to call upstream past MONTHLY_CEILING (kept
below VesselAPI's own 150 to leave headroom for local testing), independent of
whatever VesselAPI's own billing says. We would rather serve stale cache — or
fall through to the simulator — than ever find out the hard way, on judging
day, that the month's budget is gone.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from ..config import CACHE, SETTINGS
from ..flags import flag_for_mmsi

VESSELAPI_LABEL = "VesselAPI.com — terrestrial AIS, live windows"
VESSELAPI_HOME = "https://vesselapi.com/"

# Two 2°-ish boxes, each safely under the 4-degree (|dLat|+|dLon|) cap.
LIVE_WINDOWS = [
    {"id": "HORMUZ", "label": "Strait of Hormuz approach",
     "latBottom": 25.3, "latTop": 27.1, "lonLeft": 55.6, "lonRight": 57.4},
    {"id": "KUTCH", "label": "Gulf of Kutch approach (Jamnagar / Vadinar)",
     "latBottom": 21.6, "latTop": 23.2, "lonLeft": 68.6, "lonRight": 70.2},
]

# Refresh each window this often. 2 windows x 2 polls/day x 30 days = 120
# calls/month, leaving ~30 of the 150 free-tier calls as headroom.
POLL_SECONDS = 12 * 3600

# Stop calling upstream once we hit this many successful calls in the current
# UTC month — comfortably under VesselAPI's own 150, on purpose.
MONTHLY_CEILING = 140

NAV_STATUS = {
    0: "Under way (engine)", 1: "At anchor", 2: "Not under command",
    3: "Restricted manoeuvrability", 4: "Constrained by draught",
    5: "Moored", 6: "Aground", 7: "Fishing", 8: "Under way (sailing)",
}

STATE: Dict[str, Any] = {
    "windows": {w["id"]: {"ok": None, "count": 0, "error": "not polled yet"}
                for w in LIVE_WINDOWS},
    "quota_month": None, "quota_used": 0,
}


def _quota_month_key() -> tuple:
    now = datetime.now(timezone.utc)
    return (now.year, now.month)


def _quota_ok() -> bool:
    key = _quota_month_key()
    if STATE["quota_month"] != key:
        STATE["quota_month"] = key
        STATE["quota_used"] = 0
    return STATE["quota_used"] < MONTHLY_CEILING


def _quota_spend() -> None:
    STATE["quota_used"] += 1


async def _fetch_window(client: httpx.AsyncClient, window: dict) -> tuple[Optional[list], Optional[str]]:
    if not _quota_ok():
        return None, f"local monthly ceiling reached ({MONTHLY_CEILING} calls) — waiting for next month"

    params = {
        "filter.latBottom": window["latBottom"], "filter.latTop": window["latTop"],
        "filter.lonLeft": window["lonLeft"], "filter.lonRight": window["lonRight"],
        "pagination.limit": 50,
    }
    try:
        r = await client.get(
            f"{SETTINGS.vesselapi_url}/location/vessels/bounding-box",
            params=params,
            headers={"Authorization": f"Bearer {SETTINGS.vesselapi_key}",
                     "User-Agent": "SUPATH/1.0 (energy-resilience-hackathon)"},
        )
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"

    if r.status_code == 200:
        _quota_spend()  # VesselAPI only bills 2xx against quota — mirror that locally
        rows = r.json().get("vessels", [])
        out = []
        for v in rows:
            if v.get("suspected_glitch"):
                continue  # VesselAPI's own outlier flag — trust it, drop the fix
            lat, lon = v.get("latitude"), v.get("longitude")
            if lat is None or lon is None:
                continue
            mmsi = str(v.get("mmsi") or "")
            nav = v.get("nav_status")
            out.append({
                "mmsi": mmsi, "imo": str(v.get("imo") or ""),
                "name": v.get("vessel_name") or f"MMSI {mmsi}",
                "flag": flag_for_mmsi(mmsi),
                "lat": round(lat, 4), "lon": round(lon, 4),
                "heading": v.get("heading") if v.get("heading") is not None else v.get("cog") or 0,
                "speed": v.get("sog") or 0.0,
                "class": "Unclassified contact", "dwt": None,
                "cargo_kb": None, "grade": None, "laden": None,
                "corridor": None, "corridor_name": f"Live window — {window['label']}",
                "home_corridor": None,
                "destination": None, "eta_days": None,
                "status": NAV_STATUS.get(nav, "Unknown" if nav is None else f"AIS status {nav}"),
                "rerouted": False,
                "mode": "live", "provider": "vesselapi.com", "unclassified": True,
            })
        return out, None

    if r.status_code == 429:
        retry = r.headers.get("Retry-After", "?")
        return None, f"rate limited by VesselAPI (retry after {retry}s)"
    if r.status_code == 401:
        return None, "VesselAPI key rejected (401) — check VESSELAPI_KEY"
    try:
        body = r.json()
        msg = body.get("error", {})
        msg = msg.get("message") if isinstance(msg, dict) else msg
    except Exception:
        msg = r.text[:200]
    return None, f"HTTP {r.status_code}: {msg}"


async def refresh_all_windows() -> None:
    """Called on a timer by vesselapi_task(). Only spends quota on windows
    whose cache has actually gone stale — restarting the process does not
    reset the clock on a window that was fetched twenty minutes ago."""
    if not SETTINGS.vesselapi_key:
        return
    async with httpx.AsyncClient(timeout=SETTINGS.http_timeout) as client:
        for w in LIVE_WINDOWS:
            key = f"vesselapi:{w['id']}"
            if CACHE.get(key, ttl=POLL_SECONDS * 0.9) is not None:
                continue
            vessels, err = await _fetch_window(client, w)
            if vessels is not None:
                CACHE.set(key, vessels)
                STATE["windows"][w["id"]] = {"ok": True, "count": len(vessels), "error": None}
            else:
                STATE["windows"][w["id"]] = {"ok": False, "count": 0, "error": err}


async def vesselapi_task() -> None:
    """Long-lived background poller. No-ops forever if no key is set, so it
    costs nothing to always start it — matching how aisstream_task behaves."""
    if not SETTINGS.vesselapi_key:
        return
    while True:
        try:
            await refresh_all_windows()
        except Exception as exc:  # noqa: BLE001 — never take the app down over this
            for w in LIVE_WINDOWS:
                STATE["windows"][w["id"]]["error"] = f"{type(exc).__name__}: {exc}"
        await asyncio.sleep(POLL_SECONDS)


def cached_vessels() -> Optional[Dict[str, Any]]:
    """Synchronous read of whatever the background task last fetched — never
    makes a network call itself, so ais.vessels() can stay synchronous."""
    if not SETTINGS.vesselapi_key:
        return None
    out: List[dict] = []
    any_fresh = False
    for w in LIVE_WINDOWS:
        key = f"vesselapi:{w['id']}"
        fresh = CACHE.get(key, ttl=POLL_SECONDS * 1.5)
        rows = fresh if fresh is not None else CACHE.stale(key)
        if fresh is not None:
            any_fresh = True
        if rows:
            out.extend(rows)
    if not out:
        return None
    return {"vessels": out, "fresh": any_fresh,
            "windows": [w["id"] for w in LIVE_WINDOWS]}


def status() -> Dict[str, Any]:
    return {
        "configured": bool(SETTINGS.vesselapi_key),
        "windows": STATE["windows"],
        "quota_used_this_month": STATE["quota_used"],
        "quota_ceiling": MONTHLY_CEILING,
        "poll_hours": POLL_SECONDS / 3600,
    }
