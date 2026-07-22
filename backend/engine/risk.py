"""The risk engine.

One rule governs this file: **the score must be reconstructible by hand.**

A corridor's risk is a weighted sum of five terms, each in [0, 1], each derived
from one named source. The API returns not just the number but every input, the
normalisation applied, the weight, and the contribution in points — so the UI
can print the arithmetic and a sceptical official can check it on paper.

    risk = 100 × Σ wᵢ · sᵢ
    w = { conflict .32, sanctions .22, congestion .18, weather .16, market .12 }

Why these weights, in one line each:
  conflict   — highest, because it is the only term that can take a corridor to
               zero within hours (Hormuz 2025, Red Sea 2023–24).
  sanctions  — second, because for India it is the *live* binding constraint on
               35% of the barrel slate, and it moves by announcement, not weather.
  congestion — real but recoverable; it costs days, not cargoes.
  weather    — bounded and forecastable; a cyclone closes a port for a week.
  market     — lowest, because price is mostly a *consequence* of the other four;
               giving it a high weight would double-count.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List

from ..config import MODELLED, sourced
from ..reference import (CHOKEPOINTS, CORRIDORS, INDIA, RISK_WEIGHTS, SUPPLIERS,
                         band_for)
from ..sources import news as news_src
from ..sources import portwatch as pw_src
from ..sources import prices as price_src
from ..sources import sanctions as sanc_src
from ..sources import weather as wx_src

WEIGHT_RATIONALE = {
    "conflict": "Highest weight: the only term that can take a corridor to zero within hours.",
    "sanctions": "Binds 35% of India's slate today and moves by announcement, not by weather.",
    "congestion": "Costs days, not cargoes — recoverable, so weighted below the two above.",
    "weather": "Bounded and forecastable; closes a gate for days, rarely for weeks.",
    "market": "Lowest: price is mostly a consequence of the other four. A higher weight "
              "would double-count the same shock.",
}


def market_subscore(prices: dict) -> dict:
    """Market stress from the Brent series: level shock plus realised volatility."""
    b = prices["brent"]["value"]
    chg5 = abs(b.get("chg_5d_pct") or 0.0)
    vol = b.get("vol_annualised_pct") or 0.0

    move_term = min(1.0, chg5 / 10.0)   # a 10% five-day move = full stress
    vol_term = min(1.0, vol / 60.0)     # 60% annualised = full stress
    score = round(0.6 * move_term + 0.4 * vol_term, 3)

    return {
        "score": score,
        "chg_5d_pct": b.get("chg_5d_pct"),
        "vol_annualised_pct": vol,
        "move_term": round(move_term, 3),
        "vol_term": round(vol_term, 3),
        "note": f"Brent moved {b.get('chg_5d_pct'):+.1f}% over five sessions with "
                f"{vol:.0f}% annualised realised volatility."
                if b.get("chg_5d_pct") is not None else "Brent series incomplete.",
        "formula": "0.6·min(|5-day % move| / 10, 1) + 0.4·min(annualised vol / 60%, 1)",
    }


async def score_corridor(corridor: dict, ph: dict, wx: dict, prices: dict,
                         landscape: dict) -> dict:
    articles_env = await news_src.corridor_news(corridor["id"])
    articles = articles_env.get("value", [])

    terms = {
        "conflict": news_src.conflict_subscore(articles),
        "sanctions": sanc_src.sanctions_subscore(corridor, landscape),
        "congestion": pw_src.congestion_subscore(corridor, ph),
        "weather": wx_src.weather_subscore(corridor, wx),
        "market": market_subscore(prices),
    }

    breakdown = []
    total = 0.0
    for key, meta in RISK_WEIGHTS.items():
        s = float(terms[key]["score"])
        contrib = meta["weight"] * s * 100
        total += contrib
        breakdown.append({
            "key": key,
            "label": meta["label"],
            "weight": meta["weight"],
            "subscore": round(s, 3),
            "contribution": round(contrib, 1),
            "source": meta["source"],
            "rationale": WEIGHT_RATIONALE[key],
            "detail": terms[key],
        })

    score = round(total, 1)
    band = band_for(score)

    driver = max(breakdown, key=lambda b: b["contribution"])
    evidence = [
        {"title": a["title"], "url": a["url"], "domain": a["domain"], "seen": a["seen"],
         "escalation": a["escalation"]}
        for a in articles[:4]
    ]

    return {
        "corridor_id": corridor["id"],
        "name": corridor["name"],
        "short": corridor["short"],
        "share_pct": corridor["share_pct"],
        "voyage_days": corridor["voyage_days"],
        "why_it_matters": corridor["why_it_matters"],
        "chokepoints": [{"id": c, **{k: CHOKEPOINTS[c][k]
                                     for k in ("name", "lat", "lon", "world_flow_mbd")}}
                        for c in corridor["chokepoints"]],
        "waypoints": corridor["waypoints"],
        "discharge": corridor["discharge"],
        "score": score,
        "band": band["key"],
        "posture": band["action"],
        "breakdown": breakdown,
        "top_driver": {"key": driver["key"], "label": driver["label"],
                       "contribution": driver["contribution"]},
        "evidence": evidence,
        "news_mode": articles_env.get("mode"),
        "barrels_at_risk_kbd": round(INDIA["crude_imports_kbd"] * corridor["share_pct"] / 100),
        "equation": (
            "risk = 100 × ( "
            + " + ".join(f"{b['weight']}×{b['subscore']:.2f}" for b in breakdown)
            + f" ) = {score}"
        ),
    }


async def assess_all() -> dict:
    ph, wx, prices, landscape = await asyncio.gather(
        pw_src.port_health(),
        wx_src.chokepoint_weather(),
        price_src.get_prices(),
        sanc_src.sanctions_landscape(),
    )
    corridors = await asyncio.gather(
        *[score_corridor(c, ph, wx, prices, landscape) for c in CORRIDORS])
    corridors = list(corridors)

    # National exposure: barrel-weighted corridor risk. This is the number that
    # belongs in a Cabinet note — not the worst corridor, not the average one.
    weighted = sum(c["score"] * c["share_pct"] for c in corridors)
    shares = sum(c["share_pct"] for c in corridors) or 1
    national = round(weighted / shares, 1)
    nband = band_for(national)

    at_risk = [c for c in corridors if c["score"] >= 50]
    exposed_kbd = sum(c["barrels_at_risk_kbd"] for c in at_risk)

    return {
        "corridors": sorted(corridors, key=lambda c: -c["score"]),
        "national": {
            "score": national,
            "band": nband["key"],
            "posture": nband["action"],
            "method": "Barrel-weighted mean of corridor scores: Σ(risk_i × import share_i) / Σ(share_i). "
                      "Weighting by barrels, not by corridor count, is deliberate — a severe score "
                      "on a corridor carrying 2% of the slate is not a national emergency.",
            "equation": " + ".join(
                f"{c['score']}×{c['share_pct']}%" for c in corridors) + f" → {national}",
            "corridors_elevated": len(at_risk),
            "exposed_kbd": exposed_kbd,
            "exposed_pct": round(exposed_kbd / INDIA["crude_imports_kbd"] * 100, 1),
            "spr_cover_days": INDIA["spr_days_cover"],
        },
        "port_health": ph,
        "weather": wx,
        "prices": prices,
        "sanctions_landscape": landscape,
        "weights": RISK_WEIGHTS,
    }


def price_attribution(prices: dict, corridors: List[dict],
                      india_articles: List[dict]) -> Dict[str, Any]:
    """Explain the move, don't just print it.

    A 2.4% Brent day is meaningless on its own. We attribute it: which corridor's
    conflict term rose in the same window, which headlines carry the escalation
    terms, and how much of the move each explains. The attribution is a ranked
    hypothesis with its evidence attached — it is *not* a causal claim, and the
    UI says so in those words.
    """
    b = prices["brent"]["value"]
    chg = b.get("chg_1d_pct") or 0.0

    candidates = []
    for c in corridors:
        conflict = next(x for x in c["breakdown"] if x["key"] == "conflict")
        sanctions = next(x for x in c["breakdown"] if x["key"] == "sanctions")
        pressure = conflict["subscore"] * 0.7 + sanctions["subscore"] * 0.3
        # Explanatory power ∝ how stressed the corridor is × how much of India's
        # barrel it carries. A tense corridor nobody uses does not move the price.
        power = pressure * (c["share_pct"] / 100)
        if power > 0.02:
            candidates.append({
                "corridor_id": c["corridor_id"],
                "corridor": c["short"],
                "pressure": round(pressure, 3),
                "power": round(power, 3),
                "evidence": c["evidence"][:2],
                "driver": c["top_driver"]["label"],
            })

    candidates.sort(key=lambda x: -x["power"])
    total_power = sum(c["power"] for c in candidates) or 1.0
    for c in candidates:
        c["explains_pct"] = round(c["power"] / total_power * 100)

    lead = candidates[0] if candidates else None
    if abs(chg) < 0.4:
        headline = "Brent is flat. No corridor is generating a price-moving signal today."
    elif lead:
        headline = (
            f"Brent {'up' if chg > 0 else 'down'} {abs(chg):.1f}% today. The strongest "
            f"concurrent signal is {lead['corridor']} — {lead['driver'].lower()} — which "
            f"carries {next(c['share_pct'] for c in corridors if c['corridor_id'] == lead['corridor_id']):.0f}% "
            f"of India's imports."
        )
    else:
        headline = (f"Brent {'up' if chg > 0 else 'down'} {abs(chg):.1f}% today with no "
                    f"corridor signal to match it — likely demand-side or macro, not transit.")

    return sourced(
        {
            "chg_1d_pct": chg,
            "chg_5d_pct": b.get("chg_5d_pct"),
            "chg_30d_pct": b.get("chg_30d_pct"),
            "last": b.get("last"),
            "headline": headline,
            "candidates": candidates[:4],
            "caveat": "Attribution ranks concurrent signals by explanatory power. "
                      "Correlation in a 24-hour window is not causation, and SUPATH does not "
                      "claim it is — this is a lead to check, not a finding.",
            "top_india_headlines": india_articles[:3],
        },
        source="SUPATH attribution model over EIA price series and GDELT corridor signals",
        url="", mode=MODELLED,
        method="power = corridor conflict/sanctions pressure × corridor share of India's imports; "
               "candidates ranked and normalised to a share of the explained move.",
    )
