"""Sanctions — OFAC SDN list and OpenSanctions.

Two jobs:

  1. Screen a named counterparty (vessel, IMO, shipowner, refiner, trader)
     before a procurement recommendation is made. A rerouting recommendation
     that puts an Indian refiner onto a designated vessel is worse than no
     recommendation at all — so screening runs *inside* the recommendation
     engine, not as a separate lookup the user has to remember to do.

  2. Produce the corridor sanctions-exposure term for the risk score, from the
     share of that corridor's barrels that originate with a sanctioned or
     sanctions-exposed supplier, plus the count of live designations touching
     the corridor's tanker fleet.

OFAC SDN is fetched as the published CSV/XML feed. OpenSanctions is used for
the entity-resolution search (it aggregates OFAC, EU, UK, UN and more, which
matters because a vessel de-listed by OFAC may still be under EU designation).
"""

from __future__ import annotations

import csv
import io

import httpx

from ..config import CACHE, CACHED, LIVE, SETTINGS, UNAVAILABLE, sourced
from ..reference import CORRIDORS, SUPPLIERS

OFAC_LABEL = "OFAC Specially Designated Nationals (SDN) list"
OFAC_HOME = "https://sanctionslist.ofac.treas.gov/Home/SdnList"
OS_LABEL = "OpenSanctions — consolidated global sanctions data"
OS_HOME = "https://www.opensanctions.org/"

# Exposure priors by supplier sanctions status. These are policy judgements, so
# they are written down here where they can be argued with, not buried in code.
EXPOSURE_PRIOR = {"none": 0.02, "low": 0.10, "medium": 0.45, "high": 0.85}

# No key is used for OFAC — it's a public CSV feed. When the banner shows this
# as "not live", the download itself failed; there's no credential involved.
STATUS: dict = {"ok": None, "detail": "not attempted yet"}


async def _ofac_sdn() -> list[dict] | None:
    cached = CACHE.get("ofac_sdn", ttl=86400)
    if cached:
        return cached
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            r = await client.get(SETTINGS.ofac_sdn_csv)
            if r.status_code != 200:
                STATUS.update(ok=False, detail=f"HTTP {r.status_code}")
                return None
        rows = []
        reader = csv.reader(io.StringIO(r.text))
        for row in reader:
            if len(row) < 12:
                continue
            rows.append({
                "uid": row[0], "name": row[1].strip('" '), "type": row[2],
                "programs": row[3], "remarks": row[11][:300],
            })
        if not rows:
            STATUS.update(ok=False, detail="download succeeded but parsed zero rows — "
                                           "OFAC may have changed the CSV format")
            return None
        STATUS.update(ok=True, detail=f"{len(rows)} SDN entries parsed")
        CACHE.set("ofac_sdn", rows)
        return rows
    except httpx.TimeoutException:
        STATUS.update(ok=False, detail=f"timed out after 30s")
        return None
    except Exception as exc:
        STATUS.update(ok=False, detail=f"{type(exc).__name__}: {exc}")
        return None


def status() -> dict:
    return STATUS


async def screen(name: str) -> dict:
    """Screen one counterparty across OFAC and OpenSanctions."""
    name_l = name.strip().lower()
    if not name_l:
        return sourced([], source=OFAC_LABEL, url=OFAC_HOME, mode=UNAVAILABLE)

    hits: list[dict] = []

    sdn = await _ofac_sdn()
    ofac_mode = LIVE if sdn else UNAVAILABLE
    if sdn:
        for row in sdn:
            if name_l in row["name"].lower():
                hits.append({
                    "match": row["name"], "list": "OFAC SDN", "type": row["type"],
                    "programs": row["programs"], "remarks": row["remarks"],
                    "url": OFAC_HOME, "confidence": 1.0 if row["name"].lower() == name_l else 0.7,
                })
                if len(hits) >= 12:
                    break

    os_mode = UNAVAILABLE
    try:
        headers = {}
        if SETTINGS.opensanctions_key:
            headers["Authorization"] = f"ApiKey {SETTINGS.opensanctions_key}"
        async with httpx.AsyncClient(timeout=SETTINGS.http_timeout) as client:
            r = await client.get(SETTINGS.opensanctions_url,
                                 params={"q": name, "limit": 8}, headers=headers)
            if r.status_code == 200:
                os_mode = LIVE
                for res in r.json().get("results", []):
                    props = res.get("properties", {})
                    hits.append({
                        "match": res.get("caption", ""),
                        "list": ", ".join(res.get("datasets", []))[:80] or "OpenSanctions",
                        "type": res.get("schema", ""),
                        "programs": ", ".join(props.get("program", []))[:120],
                        "remarks": ", ".join(props.get("topics", []))[:200],
                        "url": f"https://www.opensanctions.org/entities/{res.get('id','')}/",
                        "confidence": round(float(res.get("score", 0)), 2),
                    })
    except Exception:
        pass

    mode = LIVE if (ofac_mode == LIVE or os_mode == LIVE) else UNAVAILABLE
    payload = sourced(
        hits, source=f"{OFAC_LABEL} + {OS_LABEL}", url=OFAC_HOME, mode=mode,
        method="Substring match against the OFAC SDN CSV feed, plus OpenSanctions "
               "entity search (which consolidates EU, UK, UN and national lists). "
               "A hit is a screening flag requiring human legal review — not a legal finding.",
    )
    payload["query"] = name
    payload["ofac_available"] = ofac_mode == LIVE
    payload["opensanctions_available"] = os_mode == LIVE
    return payload


async def sanctions_landscape() -> dict:
    """Counts of energy/shipping-relevant designations, used by the risk engine."""
    cached = CACHE.get("sanctions_landscape", ttl=21600)
    if cached:
        cached["mode"] = CACHED
        return cached

    sdn = await _ofac_sdn()
    if not sdn:
        payload = sourced(
            {"total": None, "vessels": None, "programs": {}},
            source=OFAC_LABEL, url=OFAC_HOME, mode=UNAVAILABLE,
            method="OFAC SDN feed unreachable. Corridor sanctions term falls back to the "
                   "documented supplier-exposure priors, which the UI marks as reference.")
        return payload

    programs: dict[str, int] = {}
    vessels = 0
    for row in sdn:
        if row["type"].strip().lower() == "vessel":
            vessels += 1
        for p in row["programs"].split(";"):
            p = p.strip()
            if p:
                programs[p] = programs.get(p, 0) + 1

    relevant = {k: v for k, v in programs.items()
                if any(t in k.upper() for t in
                       ("RUSSIA", "IRAN", "VENEZUELA", "SYRIA", "NPWMD", "SDGT", "IFSR"))}

    payload = sourced(
        {"total": len(sdn), "vessels": vessels,
         "programs": dict(sorted(relevant.items(), key=lambda kv: -kv[1])[:8])},
        source=OFAC_LABEL, url=OFAC_HOME, mode=LIVE,
        method="Full SDN list parsed; vessel-type designations counted separately because "
               "a designated hull, not a designated country, is what strands a cargo.")
    CACHE.set("sanctions_landscape", payload)
    return payload


def sanctions_subscore(corridor: dict, landscape: dict) -> dict:
    """Corridor sanctions term.

    Barrel-weighted exposure of the suppliers that use this corridor, lifted by
    the intensity of live designation activity in the programs that touch it.
    """
    sups = [(s, SUPPLIERS[s]) for s in corridor["suppliers"] if s in SUPPLIERS]
    total_share = sum(v["share_pct"] for _, v in sups) or 1.0

    parts = []
    weighted = 0.0
    for code, v in sups:
        prior = EXPOSURE_PRIOR.get(v["sanctions_exposure"], 0.1)
        w = v["share_pct"] / total_share
        weighted += w * prior
        parts.append({
            "supplier": v["name"], "code": code,
            "corridor_share_pct": round(w * 100, 1),
            "exposure": v["sanctions_exposure"], "prior": prior,
            "contribution": round(w * prior, 3),
        })

    lv = landscape.get("value", {}) or {}
    vessels = lv.get("vessels")
    # Vessel designations are the transmission mechanism into freight.
    fleet_term = min(0.25, (vessels or 0) / 4000) if vessels else 0.0

    score = round(min(1.0, weighted + fleet_term), 3)
    return {
        "score": score,
        "parts": sorted(parts, key=lambda p: -p["contribution"]),
        "fleet_term": round(fleet_term, 3),
        "designated_vessels": vessels,
        "note": (f"Barrel-weighted supplier exposure {weighted:.2f}"
                 + (f", lifted {fleet_term:.2f} by {vessels} vessel designations live on the "
                    f"SDN list." if vessels else ", with no live vessel-designation feed.")),
    }


def corridors_for_supplier(code: str) -> list[str]:
    return [c["id"] for c in CORRIDORS if code in c["suppliers"]]
