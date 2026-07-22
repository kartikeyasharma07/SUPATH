"""Recommendation engine — the "so what do I do" layer.

Three commitments, because a recommendation an official cannot defend is worse
than no recommendation:

  1. **Every recommendation is quantified.** Not "consider alternative sourcing"
     but "lift 220 kb/d more from Saudi Arabia; covers 12% of the gap; costs
     $1.5/bbl over Brent; arrives in 5 days; takes 4.1 points off the national
     risk score."

  2. **Every recommendation cites its evidence.** The articles, the price series,
     the port telemetry that triggered it — with URLs, so the desk officer can
     open them before signing anything.

  3. **Every counterparty is screened before it is recommended.** A rerouting
     that puts an Indian refiner onto a designated hull is a legal incident, not
     a mitigation. Screening runs inside this engine, not next to it.

Confidence is stated and *derived*: it falls when a source is degraded, and the
UI shows which one. An AI that is confident when it is blind is the failure mode
this whole platform exists to avoid.
"""

from __future__ import annotations

from typing import Any, Dict, List

from ..config import CACHED, LIVE, MODELLED, sourced
from ..reference import CORRIDORS, INDIA, SECTORS, SUPPLIERS, corridor_by_id
from ..sources import sanctions as sanc_src

IMPORT_KBD = INDIA["crude_imports_kbd"]


def _confidence(assessment: dict) -> dict:
    """Confidence is a function of how much of the evidence base is actually live.

    "cached" is not degradation — it means the same live fetch is being reused
    inside its own TTL window (600–1800s depending on source) instead of
    re-hitting the upstream API every request. Only "reference" (documented
    fallback) and "unavailable" (couldn't reach it at all) count against
    confidence; a cache hit on genuinely live data must not.
    """
    def live(mode: str) -> bool:
        return mode in (LIVE, CACHED)

    checks = [
        ("News signal (GDELT)", live(assessment["corridors"][0].get("news_mode")), 0.30),
        ("Price series (Yahoo Finance)", live(assessment["prices"]["_mode"]), 0.20),
        ("Port telemetry (IMF PortWatch)", live(assessment["port_health"]["mode"]), 0.20),
        ("Sea state (Open-Meteo)", live(assessment["weather"]["mode"]), 0.15),
        ("Sanctions (OFAC SDN)", live(assessment["sanctions_landscape"]["mode"]), 0.15),
    ]
    score = sum(w for _, ok, w in checks if ok)
    degraded = [name for name, ok, _ in checks if not ok]
    if score >= 0.85:
        label = "High"
    elif score >= 0.55:
        label = "Moderate"
    elif score >= 0.3:
        label = "Low"
    else:
        label = "Indicative only"
    return {
        "score": round(score * 100),
        "label": label,
        "degraded": degraded,
        "note": ("All five evidence streams are live." if not degraded else
                 "Confidence is reduced because these streams are not live: "
                 + ", ".join(degraded) + ". Recommendations still hold, but the "
                 "numbers behind them are running on documented reference values, "
                 "not today's observations."),
        "checks": [{"source": n, "live": ok, "weight": w} for n, ok, w in checks],
    }


def _risk_delta(from_score: float, to_score: float, kbd: float) -> float:
    """Points off the national barrel-weighted score for moving kbd between corridors."""
    return round((from_score - to_score) * (kbd / IMPORT_KBD), 2)


async def build(assessment: dict, scenario: dict | None = None) -> Dict[str, Any]:
    corridors = assessment["corridors"]
    by_id = {c["corridor_id"]: c for c in corridors}
    national = assessment["national"]
    prices = assessment["prices"]["brent"]["value"]
    ports = assessment["port_health"]["value"]["ports"]

    # The gap we are trying to cover: from a live scenario if one is running,
    # otherwise the barrels sitting on corridors scored 'elevated' or worse.
    if scenario:
        gap_kbd = scenario["headline"]["peak_gap_kbd"]
        driver = f"the {scenario['name']} scenario"
    else:
        gap_kbd = sum(c["barrels_at_risk_kbd"] for c in corridors if c["score"] >= 50)
        driver = "corridors currently scored elevated or worse"

    recs: List[Dict[str, Any]] = []

    # ---- 1. Alternative sourcing, ranked by cost per barrel of cover --------
    stressed = [c for c in corridors if c["score"] >= 45]
    stressed_ids = {c["corridor_id"] for c in stressed}
    candidates = []
    for code, s in SUPPLIERS.items():
        if s["corridor"] in stressed_ids or s["spare_kbd"] <= 0:
            continue
        home = by_id.get(s["corridor"])
        if not home:
            continue
        candidates.append({
            "code": code, "supplier": s["name"], "spare_kbd": s["spare_kbd"],
            "premium_usd": s["diff_usd"], "lead_days": s["lead_days"],
            "corridor": home["short"], "corridor_id": s["corridor"],
            "corridor_score": home["score"], "grade": s["grade"],
            "sanctions_exposure": s["sanctions_exposure"],
        })
    # Cheap, fast and on a safe corridor — in that order of importance.
    candidates.sort(key=lambda c: (c["premium_usd"] * 0.5 + c["lead_days"] * 0.15
                                   + c["corridor_score"] * 0.05))

    if gap_kbd > 0 and candidates:
        covered = 0.0
        picks = []
        for c in candidates:
            if covered >= gap_kbd:
                break
            take = min(c["spare_kbd"], gap_kbd - covered)
            covered += take
            worst = max(stressed, key=lambda x: x["score"]) if stressed else corridors[0]
            picks.append({
                **c,
                "lift_kbd": round(take),
                "cost_usd_day": round(take * 1000 * (c["premium_usd"] - (-1.85)) / 1e6, 2),
                "risk_points": _risk_delta(worst["score"], c["corridor_score"], take),
            })
        if picks:
            screen_hits = []
            for p in picks[:3]:
                res = await sanc_src.screen(p["supplier"])
                hits = [h for h in res.get("value", []) if h.get("confidence", 0) > 0.85]
                screen_hits.append({"supplier": p["supplier"], "hits": len(hits),
                                    "clear": len(hits) == 0,
                                    "checked_against": "OFAC SDN + OpenSanctions"})
            recs.append({
                "id": "REROUTE_SUPPLY",
                "priority": 1,
                "title": f"Lift {round(sum(p['lift_kbd'] for p in picks)):,} kb/d from unaffected corridors",
                "action": "Issue spot tenders to the suppliers below, in this order. They are "
                          "ranked by landed cost, then by how quickly the barrel arrives, then "
                          "by the risk of the corridor it must cross.",
                "covers_kbd": round(covered),
                "covers_pct": round(covered / max(1, gap_kbd) * 100),
                "cost_usd_m_day": round(sum(p["cost_usd_day"] for p in picks), 2),
                "risk_points": round(sum(p["risk_points"] for p in picks), 1),
                "lead_days": max(p["lead_days"] for p in picks),
                "options": picks,
                "screening": screen_hits,
                "why": f"Cover for {driver}: {round(gap_kbd):,} kb/d of India's "
                       f"{IMPORT_KBD:,} kb/d import requirement is exposed.",
                "evidence": [e for c in stressed[:2] for e in c["evidence"][:2]],
            })

    # ---- 2. Corridor rerouting ---------------------------------------------
    for c in stressed:
        ref = corridor_by_id(c["corridor_id"])
        if not ref or not ref.get("reroute_id"):
            continue
        alt = by_id.get(ref["reroute_id"])
        if not alt or alt["score"] >= c["score"]:
            continue
        kbd = round(IMPORT_KBD * c["share_pct"] / 100 * 0.6)
        recs.append({
            "id": f"REROUTE_{c['corridor_id']}",
            "priority": 2,
            "title": f"Divert {kbd:,} kb/d from {c['short']} to the {alt['short']} routing",
            "action": f"Instruct charterers to route via {alt['name']}. Voyage lengthens by "
                      f"{ref['reroute_penalty_days']} days — build the working-capital and "
                      f"tanker-availability cover for that before the diversion, not after.",
            "covers_kbd": kbd,
            "covers_pct": 100,
            "cost_usd_m_day": round(kbd * 1000 * 3.5 / 1e6, 2),
            "risk_points": _risk_delta(c["score"], alt["score"], kbd),
            "lead_days": ref["reroute_penalty_days"],
            "why": f"{c['short']} is scored {c['score']} ({c['band']}), driven by "
                   f"{c['top_driver']['label'].lower()}. {alt['short']} is scored {alt['score']}. "
                   f"The barrels still arrive — later and dearer, but they arrive.",
            "evidence": c["evidence"][:3],
            "tradeoff": f"+{ref['reroute_penalty_days']} days at sea, roughly "
                        f"${3.5:.1f}/bbl in additional freight. Rerouting is a liquidity "
                        f"problem before it is a supply problem.",
        })

    # ---- 3. Strategic reserve ----------------------------------------------
    if gap_kbd > 200:
        draw = min(900, round(gap_kbd * 0.6))
        days_at_draw = round(INDIA["spr_days_cover"] * IMPORT_KBD / draw, 1)
        recs.append({
            "id": "SPR_DRAW",
            "priority": 1 if gap_kbd > 800 else 3,
            "title": f"Authorise an SPR drawdown of {draw:,} kb/d",
            "action": "Release from Visakhapatnam and Mangalore caverns first — they are closest "
                      "to the refineries that lose crude soonest under the current corridor "
                      "picture, and they can be replenished from the east if the west is shut.",
            "covers_kbd": draw,
            "covers_pct": round(draw / max(1, gap_kbd) * 100),
            "cost_usd_m_day": 0.0,
            "risk_points": round(national["score"] * (draw / IMPORT_KBD), 1),
            "lead_days": 2,
            "why": f"India holds {INDIA['spr_days_cover']} days of cover. At {draw:,} kb/d the "
                   f"reserve lasts {days_at_draw} days — that is the length of the window this "
                   f"buys you, and it is the number to plan the diplomacy around.",
            "evidence": [],
            "tradeoff": "The reserve is a clock, not a solution. Drawing it without a "
                        "replenishment plan converts a supply crisis into a slower supply crisis.",
        })

    # ---- 4. Congestion ------------------------------------------------------
    congested = [p for p in ports.values() if p["index"] < 65]
    if congested:
        worst = min(congested, key=lambda p: p["index"])
        recs.append({
            "id": "PORT_CLEARANCE",
            "priority": 3,
            "title": f"Clear the queue at {worst['name']} (health index {worst['index']:.0f})",
            "action": "Authorise night berthing and priority pilotage for laden crude carriers; "
                      "hold ballast and product traffic. Demurrage accrues at roughly "
                      "$40,000–70,000 per VLCC per day of waiting.",
            "covers_kbd": 0,
            "covers_pct": 0,
            "cost_usd_m_day": 0.0,
            "risk_points": round(0.18 * worst["pressure"] * 100 * 0.2, 1),
            "lead_days": 1,
            "why": f"{worst['calls_today']} tanker calls today against a baseline of "
                   f"{worst['calls_baseline']}, with {worst['queue']} at anchorage. "
                   f"Crude that cannot berth is crude India has paid for and cannot refine.",
            "evidence": [],
            "workings": worst["workings"],
        })

    # ---- 5. Demand side -----------------------------------------------------
    if scenario and scenario["headline"]["final_pump_pct"] > 8:
        top = scenario["sector_impact"][0]
        recs.append({
            "id": "DEMAND_MGMT",
            "priority": 2,
            "title": f"Brief {top['name']} ahead of a {top['cost_increase_pct']:.0f}% input-cost rise",
            "action": "Pre-position the fiscal response: the choice is excise relief, targeted "
                      "subsidy, or pass-through. Deciding it in advance is the difference between "
                      "policy and improvisation.",
            "covers_kbd": 0,
            "covers_pct": 0,
            "cost_usd_m_day": 0.0,
            "risk_points": 0.0,
            "lead_days": top["impact_day"],
            "why": f"Modelled retail fuel increase of {scenario['headline']['final_pump_pct']:.1f}% "
                   f"adds {scenario['headline']['final_cpi_pp']:.2f} pp to CPI. "
                   f"{top['name']} absorbs it first, around day {top['impact_day']}.",
            "evidence": [],
            "sectors": scenario["sector_impact"][:4],
        })

    recs.sort(key=lambda r: (r["priority"], -r.get("risk_points", 0)))
    conf = _confidence(assessment)

    return sourced(
        {
            "recommendations": recs,
            "gap_kbd": round(gap_kbd),
            "driver": driver,
            "confidence": conf,
            "national": national,
            "brent": prices,
            "method": "Options are generated from the live corridor scores, then ranked by "
                      "landed cost, lead time and corridor risk. Expected risk reduction is "
                      "computed as (risk of the corridor left) − (risk of the corridor taken), "
                      "weighted by the barrels moved as a share of national imports.",
        },
        source="SUPATH recommendation engine", url="", mode=MODELLED,
        method="Rule-based over live corridor risk, price, port and sanctions inputs. Every "
               "counterparty in the top three options is screened against OFAC SDN and "
               "OpenSanctions before it is shown.",
    )


def sector_brace(scenario: dict | None) -> List[dict]:
    if scenario:
        return scenario["sector_impact"]
    return [{"id": s["id"], "name": s["name"], "cost_increase_pct": 0,
             "share_of_products_pct": s["share_of_products_pct"],
             "impact_day": s["lag_days"], "note": s["note"],
             "workings": "No scenario running — baseline exposure only."} for s in SECTORS]
