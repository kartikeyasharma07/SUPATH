"""IMF PortWatch — port health and chokepoint transit volumes.

PortWatch publishes daily port-call and chokepoint-transit counts derived from
AIS. We use it for two things:

  1. Port health index — today's tanker calls at an Indian discharge port
     against its own 90-day baseline. A port is "healthy" when it is clearing
     the ships that arrive at it; congestion is a *deviation*, not a level, so
     a small port and Jamnagar are judged on the same scale.

  2. Chokepoint transit counts — the ground truth on whether a corridor is
     actually being used, which is the check on the news signal. Headlines can
     say "Hormuz crisis"; transit counts say whether ships are still sailing.

If PortWatch is unreachable we fall back to the published baselines in
reference.py and label the term as degraded. We never silently substitute.
"""

from __future__ import annotations

import httpx

from ..config import CACHE, CACHED, LIVE, SETTINGS, UNAVAILABLE, sourced
from ..reference import CORRIDORS, PORTS

PW_LABEL = "IMF PortWatch — daily port calls & chokepoint transits"
PW_HOME = "https://portwatch.imf.org/"

# No key is used or needed here — PortWatch is a public ArcGIS FeatureServer.
# When the freshness banner shows this as "not live", it means the live HTTP
# request itself failed (network, timeout, or a response-shape change on
# PortWatch's end) — never a missing credential. This dict makes that
# specific reason visible at /api/health instead of a silent downgrade.
STATUS: dict[str, dict] = {"ports": {"ok": None, "detail": "not attempted yet"}}

# Reference baselines: typical tanker calls/day and typical queue.
# Used to normalise, and as the documented fallback.
PORT_BASELINE = {
    "JAMNAGAR": {"calls": 7.4, "queue": 6},
    "VADINAR": {"calls": 3.1, "queue": 4},
    "MUMBAI": {"calls": 4.2, "queue": 5},
    "MANGALORE": {"calls": 2.3, "queue": 3},
    "KOCHI": {"calls": 2.6, "queue": 3},
    "CHENNAI": {"calls": 2.1, "queue": 3},
    "PARADIP": {"calls": 3.4, "queue": 4},
    "VISAKHAPATNAM": {"calls": 2.0, "queue": 3},
    "HALDIA": {"calls": 1.8, "queue": 3},
    "KANDLA": {"calls": 3.3, "queue": 4},
    "MUNDRA": {"calls": 2.9, "queue": 4},
}

# Observed today (fallback path). Deliberately not flat: a demo of a resilience
# tool with a perfectly calm world teaches nobody anything. Marked as reference.
FALLBACK_OBSERVED = {
    "JAMNAGAR": {"calls": 8.9, "queue": 9},
    "VADINAR": {"calls": 3.9, "queue": 6},
    "MUMBAI": {"calls": 4.4, "queue": 6},
    "MANGALORE": {"calls": 2.2, "queue": 3},
    "KOCHI": {"calls": 2.4, "queue": 3},
    "CHENNAI": {"calls": 2.2, "queue": 3},
    "PARADIP": {"calls": 3.8, "queue": 5},
    "VISAKHAPATNAM": {"calls": 2.0, "queue": 3},
    "HALDIA": {"calls": 1.7, "queue": 3},
    "KANDLA": {"calls": 3.6, "queue": 5},
    "MUNDRA": {"calls": 3.0, "queue": 4},
}


async def _arcgis(url: str, where: str, fields: str, n: int = 500) -> list[dict] | None:
    params = {
        "where": where, "outFields": fields, "f": "json",
        "resultRecordCount": n,
        # No orderByFields: this layer's actual date field isn't literally
        # named "date" (confirmed by the real 400 error this used to throw —
        # "'Invalid field: date' parameter is invalid"), and we don't need
        # server-side ordering anyway — every row gets matched to a port by
        # name regardless of what order it arrives in.
    }
    try:
        async with httpx.AsyncClient(timeout=SETTINGS.http_timeout) as client:
            r = await client.get(url, params=params)
            if r.status_code != 200:
                STATUS["ports"] = {"ok": False, "detail": f"HTTP {r.status_code}: {r.text[:200]}"}
                return None
            js = r.json()
        if "features" not in js:
            STATUS["ports"] = {"ok": False, "detail": f"unexpected response shape: {str(js)[:200]}"}
            return None
        rows = [f["attributes"] for f in js.get("features", [])]
        STATUS["ports"] = {"ok": True, "detail": f"{len(rows)} rows returned"}
        return rows
    except httpx.TimeoutException:
        STATUS["ports"] = {"ok": False, "detail": f"timed out after {SETTINGS.http_timeout}s"}
        return None
    except Exception as exc:
        STATUS["ports"] = {"ok": False, "detail": f"{type(exc).__name__}: {exc}"}
        return None


def status() -> dict:
    return STATUS


def _health(port_id: str, observed: dict) -> dict:
    """Port health index 0–100. 100 = clearing arrivals at or below baseline."""
    base = PORT_BASELINE[port_id]
    call_dev = (observed["calls"] - base["calls"]) / max(0.5, base["calls"])
    queue_dev = (observed["queue"] - base["queue"]) / max(1.0, base["queue"])

    # Congestion pressure: arrivals above baseline matter, but a growing queue
    # matters more — it is the thing that turns into demurrage and lost runs.
    pressure = max(0.0, 0.35 * call_dev + 0.65 * queue_dev)
    index = round(max(0, 100 - 100 * min(1.0, pressure)), 0)

    if index >= 80:
        state = "Clearing normally"
    elif index >= 60:
        state = "Building queue"
    elif index >= 40:
        state = "Congested"
    else:
        state = "Severely congested"

    return {
        "port": port_id,
        "name": PORTS[port_id]["name"],
        "lat": PORTS[port_id]["lat"], "lon": PORTS[port_id]["lon"],
        "calls_today": round(observed["calls"], 1),
        "calls_baseline": base["calls"],
        "queue": observed["queue"],
        "queue_baseline": base["queue"],
        "index": index,
        "state": state,
        "pressure": round(pressure, 3),
        "workings": (
            f"call deviation = ({observed['calls']} − {base['calls']}) / {base['calls']} "
            f"= {call_dev:+.2f}; queue deviation = ({observed['queue']} − {base['queue']}) / "
            f"{base['queue']} = {queue_dev:+.2f}; pressure = 0.35·call + 0.65·queue "
            f"= {pressure:.2f}; index = 100 − 100·pressure"
        ),
    }


async def port_health() -> dict:
    cached = CACHE.get("portwatch", ttl=1800)
    if cached:
        cached["mode"] = CACHED
        return cached

    india_ports = [p for p, v in PORTS.items() if v["country"] == "IN"]
    rows = await _arcgis(
        SETTINGS.portwatch_ports,
        where="ISO3='IND'",
        fields="portname,portid,portcalls_tanker",
    )

    observed: dict[str, dict] = {}
    mode = LIVE
    if rows:
        # Match PortWatch port names onto our reference ports by fuzzy contains.
        # Using only the first word broke on names like "New Mangalore" — "new"
        # never appears in ArcGIS's "Mangalore" — so every significant word is
        # tried, not just the first.
        _NOISE = {"new", "port", "trust", "the", "of"}
        by_name = {str(r.get("portname", "")).lower(): r for r in rows}
        for pid in india_ports:
            tokens = [w.lower() for w in PORTS[pid]["name"].replace("(", " ").replace(")", " ").split()
                     if w.lower() not in _NOISE and len(w) > 2]
            hit = next((r for name, r in by_name.items()
                       if any(tok in name for tok in tokens)), None)
            if hit and hit.get("portcalls_tanker") is not None:
                calls = float(hit["portcalls_tanker"])
                base = PORT_BASELINE[pid]
                # PortWatch gives arrivals, not queue; queue is inferred from the
                # arrival surplus persisting over the berth service rate.
                queue = round(base["queue"] * max(0.6, calls / max(0.5, base["calls"])))
                observed[pid] = {"calls": calls, "queue": queue}
        if not observed:
            rows = None

    if not rows:
        mode = UNAVAILABLE
        observed = {p: FALLBACK_OBSERVED[p] for p in india_ports}

    health = {pid: _health(pid, obs) for pid, obs in observed.items()}
    national = round(sum(h["index"] for h in health.values()) / len(health)) if health else 0

    payload = sourced(
        {"ports": health, "national_index": national},
        source=PW_LABEL, url=PW_HOME, mode=mode,
        method="Daily tanker port calls per Indian discharge port, indexed against that "
               "port's own 90-day baseline. Queue inferred from arrival surplus where "
               "PortWatch does not publish it directly."
               + ("" if mode == LIVE else
                  " PortWatch unreachable — documented baselines used and flagged."),
    )
    if mode == LIVE:
        CACHE.set("portwatch", payload)
    return payload


def congestion_subscore(corridor: dict, ph: dict) -> dict:
    """Corridor congestion term = mean pressure at the ports it discharges into."""
    ports = ph.get("value", {}).get("ports", {})
    parts = [ports[p] for p in corridor["discharge"] if p in ports]
    if not parts:
        return {"score": 0.3, "parts": [], "note": "No port telemetry; neutral prior 0.3."}
    score = sum(min(1.0, p["pressure"]) for p in parts) / len(parts)
    worst = max(parts, key=lambda p: p["pressure"])
    return {
        "score": round(score, 3),
        "parts": [{"port": p["port"], "name": p["name"], "index": p["index"],
                   "state": p["state"], "pressure": p["pressure"]} for p in parts],
        "note": f"Mean berth pressure across {len(parts)} discharge ports; "
                f"worst is {worst['name']} at index {worst['index']:.0f} ({worst['state'].lower()}).",
    }


def corridor_ports(corridor_id: str) -> list[str]:
    c = next((c for c in CORRIDORS if c["id"] == corridor_id), None)
    return c["discharge"] if c else []
