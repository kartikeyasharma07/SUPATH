"""Open-Meteo — sea state and wind at the points that matter.

No API key, no rate-limit theatre. We sample the marine API at each chokepoint
and each Indian discharge port, then convert wave height and wind into a 0–1
transit-difficulty term. The thresholds below are the operational ones tanker
masters actually use, not arbitrary bands:

  wave height  > 4 m   → VLCC berthing/lightering typically suspended
  wind         > 34 kt → gale force; port cranes and mooring stop
"""

from __future__ import annotations

import asyncio

import httpx

from ..config import CACHE, CACHED, LIVE, SETTINGS, UNAVAILABLE, sourced
from ..reference import CHOKEPOINTS, PORTS

OM_LABEL = "Open-Meteo Marine & Forecast API"
OM_HOME = "https://open-meteo.com/en/docs/marine-weather-api"

WAVE_SUSPEND_M = 4.0
GALE_KT = 34.0

# No key is used here — Open-Meteo is fully public. "Not live" in the banner
# means the requests themselves failed (network/timeout), never a missing
# credential. Tracked per-point-count rather than per-point, since this
# queries a dozen-plus locations every cycle.
STATUS: dict = {"ok": None, "detail": "not attempted yet"}


async def _point(client: httpx.AsyncClient, lat: float, lon: float) -> dict | None:
    try:
        marine = await client.get(SETTINGS.open_meteo_marine, params={
            "latitude": lat, "longitude": lon,
            "current": "wave_height,wave_period,wind_wave_height",
            "timezone": "UTC",
        })
        wx = await client.get(SETTINGS.open_meteo_weather, params={
            "latitude": lat, "longitude": lon,
            "current": "wind_speed_10m,wind_gusts_10m,precipitation",
            "wind_speed_unit": "kn", "timezone": "UTC",
        })
        m = marine.json().get("current", {}) if marine.status_code == 200 else {}
        w = wx.json().get("current", {}) if wx.status_code == 200 else {}
        if not w and not m:
            return None
        return {
            "wave_height_m": m.get("wave_height"),
            "wave_period_s": m.get("wave_period"),
            "wind_kt": w.get("wind_speed_10m"),
            "gust_kt": w.get("wind_gusts_10m"),
            "precip_mm": w.get("precipitation"),
        }
    except Exception:
        return None


def _difficulty(obs: dict) -> dict:
    """0–1 transit difficulty, with the arithmetic exposed."""
    wave = obs.get("wave_height_m") or 0.0
    wind = obs.get("wind_kt") or 0.0
    gust = obs.get("gust_kt") or wind

    wave_term = min(1.0, wave / WAVE_SUSPEND_M)
    wind_term = min(1.0, wind / GALE_KT)
    gust_term = min(1.0, gust / (GALE_KT * 1.3))
    score = round(0.5 * wave_term + 0.3 * wind_term + 0.2 * gust_term, 3)

    if wave >= WAVE_SUSPEND_M or wind >= GALE_KT:
        status = "Operations likely suspended"
    elif score > 0.55:
        status = "Degraded — expect berthing delay"
    else:
        status = "Workable"

    return {
        "score": score,
        "status": status,
        "wave_term": round(wave_term, 3),
        "wind_term": round(wind_term, 3),
        "gust_term": round(gust_term, 3),
        "formula": "0.5·(wave/4m) + 0.3·(wind/34kt) + 0.2·(gust/44kt), each capped at 1.0",
    }


async def chokepoint_weather() -> dict:
    cached = CACHE.get("weather", ttl=1800)
    if cached:
        cached["mode"] = CACHED
        return cached

    points = [(k, v["name"], v["lat"], v["lon"], "chokepoint") for k, v in CHOKEPOINTS.items()]
    points += [(k, v["name"], v["lat"], v["lon"], "port")
               for k, v in PORTS.items() if v["country"] == "IN"]

    results: dict[str, dict] = {}
    gather_error = None
    try:
        async with httpx.AsyncClient(timeout=SETTINGS.http_timeout) as client:
            obs_list = await asyncio.gather(
                *[_point(client, p[2], p[3]) for p in points], return_exceptions=True)
    except Exception as exc:
        obs_list = [None] * len(points)
        gather_error = f"{type(exc).__name__}: {exc}"

    live_any = False
    live_count = 0
    for (key, name, lat, lon, kind), obs in zip(points, obs_list):
        if isinstance(obs, dict):
            live_any = True
            live_count += 1
            results[key] = {"name": name, "lat": lat, "lon": lon, "kind": kind,
                            "obs": obs, **_difficulty(obs)}
        else:
            results[key] = {"name": name, "lat": lat, "lon": lon, "kind": kind,
                            "obs": {}, "score": 0.25, "status": "No observation",
                            "formula": "Neutral prior 0.25 applied — Open-Meteo unreachable."}

    if gather_error:
        STATUS.update(ok=False, detail=gather_error)
    elif live_count == 0:
        STATUS.update(ok=False, detail=f"0 of {len(points)} points returned an observation "
                                       f"(each point fails independently — likely a network "
                                       f"or timeout issue reaching open-meteo.com)")
    else:
        STATUS.update(ok=True, detail=f"{live_count} of {len(points)} points returned an observation")

    payload = sourced(results, source=OM_LABEL, url=OM_HOME,
                      mode=LIVE if live_any else UNAVAILABLE,
                      method="Current wave height (marine API) and 10 m wind/gust (forecast API) "
                             "sampled at each chokepoint and Indian discharge port.")
    if live_any:
        CACHE.set("weather", payload)
    return payload


def status() -> dict:
    return STATUS


def weather_subscore(corridor: dict, wx: dict) -> dict:
    """Corridor weather term = worst chokepoint on the corridor. A route is only
    as passable as its hardest gate — averaging would hide exactly the event we
    are built to catch."""
    values = wx.get("value", {})
    parts = []
    for cp in corridor["chokepoints"]:
        d = values.get(cp)
        if d:
            parts.append({"chokepoint": cp, "name": d["name"], "score": d["score"],
                          "status": d["status"], "obs": d.get("obs", {})})
    if not parts:
        return {"score": 0.25, "parts": [], "note": "No sea-state observation; neutral prior 0.25."}
    worst = max(parts, key=lambda p: p["score"])
    return {
        "score": worst["score"],
        "parts": parts,
        "note": f"Governed by {worst['name']} — the worst gate on this corridor "
                f"({worst['status'].lower()}).",
    }
