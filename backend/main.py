"""SUPATH — API surface.

Endpoints, in the order a user meets them:

  GET  /api/health                 what is live, what is degraded, and why
  GET  /api/reference              corridors, ports, chokepoints, suppliers, sectors
  GET  /api/situation              the Overview tab in one call
  GET  /api/vessels                AIS positions (live or simulated) + density grid
  GET  /api/risk                   corridor scores with full derivation
  GET  /api/news?corridor=         corridor news signal with escalation terms
  GET  /api/impact/{article_hash}  "what does this news do to India"
  POST /api/screen                 sanctions screening for a named counterparty
  POST /api/scenario               run a scenario through the abcEconomics model
  GET  /api/recommendations        ranked, quantified, cited actions
  GET  /api/brief                  the advisor's call, reasoning and tripwires
  GET  /api/report.pdf             situation brief (or ?kind=24h)

A note on state: a running scenario is held per-session in memory so the map,
the risk panel and the advisor all reflect the same world. This is deliberate.
A simulator that only changes one panel teaches the user nothing.
"""

from __future__ import annotations

import asyncio
import hashlib
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import SETTINGS, now_iso
from .engine import advisor as advisor_engine
from .engine import recommend as rec_engine
from .engine import report as report_engine
from .engine import risk as risk_engine
from .engine import scenario as scenario_engine
from .reference import (CHOKEPOINTS, CORRIDORS, INDIA, PORTS, RISK_WEIGHTS,
                        SCENARIOS, SECTORS, SPURS, SUPPLIERS, SUPPLIER_SOURCE)
from .sources import ais, gdeltcloud, news, portwatch, prices, sanctions, vesselapi, weather

# The active scenario. None = the real world.
ACTIVE: dict = {"scenario": None, "result": None}


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(ais.aisstream_task())
    va_task = asyncio.create_task(vesselapi.vesselapi_task())
    yield
    task.cancel()
    va_task.cancel()


app = FastAPI(title="SUPATH — Strategic Energy Transit Unit", version="1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ---------------------------------------------------------------------------
# Health & reference
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health():
    try:
        await prices.get_prices()  # so status() below reflects a real, current attempt
        await portwatch.port_health()
        await weather.chokepoint_weather()
        await sanctions.sanctions_landscape()
    except Exception:
        pass
    return {
        "time": now_iso(),
        "build": "2026-07-22-16-scenario-polish",  # bump this string on every
                                                            # fix — compare it against
                                                            # what you were told to expect;
                                                            # a mismatch means the running
                                                            # server is not the code you
                                                            # think it is, full stop.
        "ais": ais.ais_status(),
        "prices": prices.status(),
        "portwatch": portwatch.status(),
        "weather": weather.status(),
        "sanctions": sanctions.status(),
        "news_gdelt_cloud": gdeltcloud.status(),
        "keys": {
            "aisstream": bool(SETTINGS.aisstream_key),
            "eia": bool(SETTINGS.eia_key),
            "opensanctions": bool(SETTINGS.opensanctions_key),
            "anthropic": bool(SETTINGS.anthropic_key),
            "vesselapi": bool(SETTINGS.vesselapi_key),
            "gdelt_cloud": bool(SETTINGS.gdelt_cloud_key),
        },
        "engine": "abcEconomics" if scenario_engine.ABCE else "analytic fallback",
        "active_scenario": ACTIVE["scenario"],
    }


@app.get("/api/reference")
async def reference():
    return {
        "india": INDIA,
        "corridors": CORRIDORS,
        "ports": PORTS,
        "chokepoints": CHOKEPOINTS,
        "suppliers": SUPPLIERS,
        "supplier_source": SUPPLIER_SOURCE,
        "sectors": SECTORS,
        "scenarios": {k: {kk: vv for kk, vv in v.items() if kk != "corridor_capacity"}
                      | {"corridor_capacity": v.get("corridor_capacity", {})}
                      for k, v in SCENARIOS.items()},
        "weights": RISK_WEIGHTS,
        "calibration": scenario_engine.CALIBRATION,
    }


# ---------------------------------------------------------------------------
# Situation
# ---------------------------------------------------------------------------

@app.get("/api/situation")
async def situation():
    assessment, india_news = await asyncio.gather(
        risk_engine.assess_all(), news.india_news())
    attribution = risk_engine.price_attribution(
        assessment["prices"], assessment["corridors"], india_news.get("value", []))
    return {
        "national": assessment["national"],
        "corridors": [{k: c[k] for k in
                       ("corridor_id", "name", "short", "share_pct", "score", "band",
                        "posture", "top_driver", "waypoints", "chokepoints", "discharge",
                        "barrels_at_risk_kbd", "why_it_matters", "voyage_days")}
                      | {"reroute_id": next((cc["reroute_id"] for cc in CORRIDORS
                                             if cc["id"] == c["corridor_id"]), None)}
                      | {"spurs": SPURS.get(c["corridor_id"], {})}
                      for c in assessment["corridors"]],
        "prices": assessment["prices"],
        "attribution": attribution,
        "port_health": assessment["port_health"],
        "weather": assessment["weather"],
        "scenario": ACTIVE["result"]["headline"] if ACTIVE["result"] else None,
        "scenario_id": ACTIVE["scenario"],
        "time": now_iso(),
    }


@app.get("/api/vessels")
async def vessels():
    blocked = None
    if ACTIVE["result"]:
        last = ACTIVE["result"]["series"][-1]
        blocked = {c["id"]: c["capacity"] for c in last["corridors"]}
    env = ais.vessels(blocked)
    data = env["value"]
    return {
        "vessels": data,
        "density": ais.density_grid(data),
        "live_windows": vesselapi.LIVE_WINDOWS if env["mode"] == "hybrid" else [],
        "count": len(data),
        "source": env["source"],
        "mode": env["mode"],
        "method": env["method"],
        "status": ais.ais_status(),
        "blocked": blocked or {},
    }


# ---------------------------------------------------------------------------
# Risk
# ---------------------------------------------------------------------------

@app.get("/api/risk")
async def risk():
    a = await risk_engine.assess_all()
    return {
        "national": a["national"],
        "corridors": a["corridors"],
        "weights": a["weights"],
        "port_health": a["port_health"],
        "weather": a["weather"],
        "sanctions_landscape": a["sanctions_landscape"],
        "time": now_iso(),
    }


@app.get("/api/news")
async def corridor_news(corridor: Optional[str] = None,
                        timespan: str = Query("24h", pattern=r"^\d+[hd]$")):
    if corridor:
        return await news.corridor_news(corridor, timespan)
    out = await asyncio.gather(*[news.corridor_news(c["id"], timespan) for c in CORRIDORS])
    merged = []
    for c, env in zip(CORRIDORS, out):
        for a in env.get("value", []):
            merged.append({**a, "corridor": c["id"], "corridor_short": c["short"],
                           "id": hashlib.sha1(a["url"].encode()).hexdigest()[:10]})
    merged.sort(key=lambda a: (-a["escalation"], a["seen"]), reverse=False)
    merged.sort(key=lambda a: -a["escalation"])
    return {"articles": merged[:40], "source": "GDELT DOC 2.0",
            "url": "https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/",
            "mode": out[0].get("mode") if out else "unavailable", "time": now_iso()}


class ImpactRequest(BaseModel):
    corridor: str
    escalation: float = 0.5
    title: str = ""
    url: str = ""


@app.post("/api/impact")
async def impact(req: ImpactRequest):
    """"What does this headline do to India?" — the click-through behind every article.

    We take the corridor the article touches, apply the article's escalation
    weight as a capacity haircut, and run the same agent model the simulator
    uses. The answer is therefore consistent with everything else on screen,
    which is the whole point: one model, not a second opinion.
    """
    corridor = next((c for c in CORRIDORS if c["id"] == req.corridor), None)
    if not corridor:
        raise HTTPException(404, "Unknown corridor")

    # An article is not an event. Escalation maps to a *possible* capacity loss,
    # and we say so in the response rather than pretending to a forecast.
    haircut = max(0.15, 1 - req.escalation * 0.7)
    scenario_id = {
        "GULF_HORMUZ": "HORMUZ_CLOSURE",
        "REDSEA_SUEZ": "RED_SEA_ATTACK",
        "MALACCA_PACIFIC": "RUSSIA_SANCTIONS",
        "REDSEA": "RED_SEA_ATTACK",
    }.get(req.corridor, "RED_SEA_ATTACK")

    result = await asyncio.to_thread(
        scenario_engine.run_scenario, scenario_id, min(1.0, req.escalation), 14)
    h = result["headline"]
    kbd = round(INDIA["crude_imports_kbd"] * corridor["share_pct"] / 100 * (1 - haircut))

    return {
        "corridor": corridor["short"],
        "article": {"title": req.title, "url": req.url},
        "escalation": req.escalation,
        "import_reduction_kbd": kbd,
        "import_reduction_pct": round(kbd / INDIA["crude_imports_kbd"] * 100, 1),
        "price_band_usd": [round(h["peak_brent"] * 0.92, 1), round(h["peak_brent"] * 1.06, 1)],
        "price_change_pct": h["peak_brent_chg_pct"],
        "pump_pct": h["final_pump_pct"],
        "industries": result["sector_impact"][:4],
        "basis": (f"Modelled as a {int(req.escalation*100)}% severity {result['name']} — the "
                  f"article's escalation weight applied as a capacity haircut on {corridor['short']}, "
                  f"then run through the same agent model as the scenario simulator."),
        "caveat": "This is a conditional estimate — what would follow *if* this report describes "
                  "a real disruption of this severity. It is not a prediction that it will.",
        "engine": result["engine"],
    }


# ---------------------------------------------------------------------------
# Sanctions screening
# ---------------------------------------------------------------------------

class ScreenRequest(BaseModel):
    name: str


@app.post("/api/screen")
async def screen(req: ScreenRequest):
    return await sanctions.screen(req.name)


# ---------------------------------------------------------------------------
# Scenario
# ---------------------------------------------------------------------------

class ScenarioRequest(BaseModel):
    scenario: str
    severity: float = 1.0
    days: int = 30


@app.post("/api/scenario")
async def run_scenario(req: ScenarioRequest):
    if req.scenario not in SCENARIOS:
        raise HTTPException(404, f"Unknown scenario: {req.scenario}")
    p = await prices.get_prices()
    base = p["brent"]["value"]["last"]
    result = await asyncio.to_thread(
        scenario_engine.run_scenario, req.scenario,
        max(0.05, min(1.0, req.severity)), max(5, min(120, req.days)), base)
    ACTIVE["scenario"] = req.scenario
    ACTIVE["result"] = result
    return result


@app.post("/api/scenario/clear")
async def clear_scenario():
    ACTIVE["scenario"] = None
    ACTIVE["result"] = None
    return {"cleared": True}


# ---------------------------------------------------------------------------
# Recommendations, brief, report
# ---------------------------------------------------------------------------

@app.get("/api/recommendations")
async def recommendations():
    a = await risk_engine.assess_all()
    r = await rec_engine.build(a, ACTIVE["result"])
    return r


@app.get("/api/brief")
async def get_brief():
    a = await risk_engine.assess_all()
    r = await rec_engine.build(a, ACTIVE["result"])
    b = await advisor_engine.brief(a, r, ACTIVE["result"])
    return {"brief": b, "recommendations": r, "national": a["national"],
            "scenario": ACTIVE["result"]["headline"] if ACTIVE["result"] else None,
            "scenario_name": ACTIVE["result"]["name"] if ACTIVE["result"] else None,
            "sectors": rec_engine.sector_brace(ACTIVE["result"]),
            "time": now_iso()}


@app.get("/api/report.pdf")
async def report(kind: str = Query("full", pattern="^(full|24h)$")):
    a = await risk_engine.assess_all()
    r = await rec_engine.build(a, ACTIVE["result"])
    b = await advisor_engine.brief(a, r, ACTIVE["result"])
    pdf = await asyncio.to_thread(report_engine.build_pdf, a, r, b, ACTIVE["result"], kind)
    name = "SUPATH_Situation_Brief.pdf" if kind == "full" else "SUPATH_Last_24_Hours.pdf"
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{name}"'})


# ---------------------------------------------------------------------------
# Frontend
# ---------------------------------------------------------------------------

import os  # noqa: E402

FRONTEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")


@app.middleware("http")
async def _no_cache_frontend(request, call_next):
    """Without this, browsers can silently keep serving yesterday's JS/CSS
    after a fresh deploy — "I changed the code but nothing changed" is almost
    always this, not a real bug. Forces revalidation on every load instead of
    trusting a long browser cache lifetime for our own static files."""
    response = await call_next(request)
    if request.url.path in ("/", "") or request.url.path.startswith(("/js/", "/css/")):
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
    return response


if os.path.isdir(FRONTEND):
    app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")
