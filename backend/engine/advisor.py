"""The advisor — what makes this a decision-support system rather than a dashboard.

A dashboard shows you the state of the world and leaves the thinking to you.
This layer does the opposite: it commits to a call, states the reasoning, shows
the evidence, and — the part almost nobody builds — states what would change its
mind. A recommendation with no falsification condition is an opinion; a
recommendation with tripwires is a decision aid.

The narrative is generated deterministically from the same numbers the rest of
the platform serves, so it can never drift from the evidence. If an Anthropic
API key is present it is used to *phrase* the brief more fluently — never to
invent a number, and never as the source of a claim.
"""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List

from ..config import CACHE, MODELLED, SETTINGS, sourced
from ..reference import INDIA

POSTURE_PLAYBOOK = {
    "Watch": "Normal operations. Keep the corridor picture under review; no procurement action.",
    "Monitor": "Raise reporting frequency. Confirm that the next 30 days of cargoes are fixed "
               "and that alternative suppliers have been contacted, without lifting anything.",
    "Prepare": "Pre-position. Open spot dialogue with unaffected suppliers, book optional tanker "
               "capacity, and put the SPR release paperwork in front of the decision-maker before "
               "you need it.",
    "Act": "Execute. Lift from the alternatives now, divert the cargoes that can be diverted, and "
           "authorise a partial SPR draw. Waiting for certainty costs more than acting early.",
    "Escalate": "Crisis footing. Convene the inter-ministerial group, execute the full "
                "procurement and reserve plan, and move to demand management before the "
                "shortfall reaches the pump.",
}


def _tripwires(assessment: dict, scenario: dict | None) -> List[dict]:
    """What would change this call. Concrete, observable, and tied to a source."""
    corridors = assessment["corridors"]
    top = corridors[0]
    brent = assessment["prices"]["brent"]["value"]
    ports = assessment["port_health"]["value"]["ports"]
    worst_port = min(ports.values(), key=lambda p: p["index"]) if ports else None

    wires = [
        {
            "trigger": f"{top['short']} risk crosses 70",
            "current": f"{top['score']}",
            # Progress toward the trip point, 0-1. Used only to draw a
            # "how close is this" bar — the trigger and current text above
            # remain the source of truth.
            "progress": round(min(1.0, max(0.0, top["score"] / 70.0)), 3),
            "means": "Corridor moves from Prepare to Act. Start lifting alternatives that day, "
                     "not that week.",
            "watch": "GDELT corridor signal + OFAC designations",
        },
        {
            "trigger": "Brent moves more than 5% in a session",
            "current": f"{brent.get('chg_1d_pct', 0):+.1f}% today",
            "progress": round(min(1.0, max(0.0, abs(brent.get("chg_1d_pct", 0)) / 5.0)), 3),
            "means": "The market has repriced a physical risk. Check which corridor's conflict "
                     "term moved with it before assuming it is macro.",
            "watch": "EIA daily spot series",
        },
        {
            "trigger": "Any Indian discharge port health index below 40",
            "current": (f"{worst_port['name']} at {worst_port['index']:.0f}"
                        if worst_port else "no telemetry"),
            "progress": (round(min(1.0, max(0.0, (100 - worst_port["index"]) / 60.0)), 3)
                        if worst_port else 0.0),
            "means": "Crude is arriving and not landing. Refinery runs will fall within a week "
                     "regardless of what the price does.",
            "watch": "IMF PortWatch daily calls",
        },
        {
            "trigger": "A vessel serving an Indian refiner appears on the SDN list",
            "current": "none in the current screening set",
            # Binary, not a gradient — a designation either exists or it doesn't.
            "progress": 0.0,
            "means": "Cargo is legally stranded. Re-nominate the vessel before it sails, not "
                     "after it is designated.",
            "watch": "OFAC SDN + OpenSanctions",
        },
    ]
    if scenario:
        h = scenario["headline"]
        spr_left = scenario["series"][-1]["spr_days_left"]
        wires.insert(0, {
            "trigger": f"The {scenario['name']} scenario persists past "
                       f"{h.get('spr_exhausted_day') or scenario['days']} days",
            "current": f"modelled to day {scenario['days']}",
            # How far the reserve has already been drawn down against its
            # normal 9.5-day cover — closer to fully drawn reads as closer to tripped.
            "progress": round(min(1.0, max(0.0, 1 - spr_left / INDIA["spr_days_cover"])), 3),
            "means": f"SPR cover falls to {scenario['series'][-1]['spr_days_left']} days. "
                     f"Beyond that point there is no buffer left to buy time with — the response "
                     f"has to be demand-side.",
            "watch": "Scenario simulator",
        })
    return wires


def _call(assessment: dict, recs: dict, scenario: dict | None) -> Dict[str, Any]:
    national = assessment["national"]
    corridors = assessment["corridors"]
    top = corridors[0]
    rec_list = recs["value"]["recommendations"]
    lead = rec_list[0] if rec_list else None
    conf = recs["value"]["confidence"]
    brent = assessment["prices"]["brent"]["value"]

    if scenario:
        h = scenario["headline"]
        headline = (
            f"Under {scenario['name'].lower()} at {int(scenario['severity']*100)}% severity, "
            f"India loses {h['peak_gap_kbd']:,} kb/d at the peak, Brent reaches "
            f"${h['peak_brent']} (+{h['peak_brent_chg_pct']:.0f}%), and retail fuel rises "
            f"{h['final_pump_pct']:.1f}% — about {h['final_cpi_pp']:.2f} pp of CPI."
        )
    else:
        headline = (
            f"National corridor risk is {national['score']} ({national['band']}). "
            f"{top['short']} is the binding corridor at {top['score']}, driven by "
            f"{top['top_driver']['label'].lower()}. "
            f"{national['exposed_pct']:.0f}% of India's imports — "
            f"{national['exposed_kbd']:,} kb/d — sit on corridors scored elevated or worse."
        )

    reasoning = [
        {
            "step": "What the corridors say",
            "text": f"{top['short']} scores {top['score']} because "
                    f"{top['top_driver']['label'].lower()} contributes "
                    f"{top['top_driver']['contribution']:.1f} of those points. "
                    f"It carries {top['share_pct']:.0f}% of India's crude — "
                    f"{top['barrels_at_risk_kbd']:,} kb/d.",
        },
        {
            "step": "What the market says",
            "text": f"Brent is ${brent.get('last')} , {brent.get('chg_1d_pct', 0):+.1f}% on the "
                    f"day and {brent.get('chg_5d_pct', 0):+.1f}% over five sessions, with "
                    f"{brent.get('vol_annualised_pct', 0):.0f}% annualised volatility.",
        },
        {
            "step": "What it costs India",
            "text": f"India imports {INDIA['crude_imports_kbd']:,} kb/d — "
                    f"{INDIA['crude_import_dependency_pct']:.0f}% of consumption — against "
                    f"{INDIA['spr_days_cover']} days of strategic cover. Every $1/bbl on the "
                    f"landed price is roughly ${INDIA['crude_imports_kbd']*365/1e6*1:.1f} bn a year "
                    f"on the import bill.",
        },
    ]
    if lead:
        reasoning.append({
            "step": "What to do about it",
            "text": f"{lead['title']}. {lead['why']} Expected effect: "
                    f"{lead['risk_points']:.1f} points off the national score"
                    + (f", covering {lead['covers_pct']}% of the exposed volume"
                       if lead.get("covers_pct") else "") + ".",
        })

    return {
        "posture": national["posture"],
        "playbook": POSTURE_PLAYBOOK.get(national["posture"], ""),
        "headline": headline,
        "reasoning": reasoning,
        "confidence": conf,
        "lead_action": lead["title"] if lead else "No action required at current risk levels.",
        "tripwires": _tripwires(assessment, scenario),
        "citations": _citations(assessment, scenario),
    }


def _citations(assessment: dict, scenario: dict | None) -> List[dict]:
    """Everything the call rests on, in one list, each with a link."""
    cites = []
    seen = set()
    for c in assessment["corridors"][:3]:
        for e in c["evidence"][:2]:
            if e["url"] and e["url"] not in seen:
                seen.add(e["url"])
                cites.append({"type": "News signal", "title": e["title"],
                              "url": e["url"], "publisher": e["domain"],
                              "used_for": f"{c['short']} conflict term", "seen": e["seen"]})
    p = assessment["prices"]["brent"]
    cites.append({"type": "Price series", "title": p["source"], "url": p["url"],
                  "publisher": "U.S. Energy Information Administration",
                  "used_for": "Market stress term and all price-linked estimates",
                  "seen": p["as_of"]})
    ph = assessment["port_health"]
    cites.append({"type": "Port telemetry", "title": ph["source"], "url": ph["url"],
                  "publisher": "International Monetary Fund",
                  "used_for": "Congestion term and port health index", "seen": ph["as_of"]})
    wx = assessment["weather"]
    cites.append({"type": "Sea state", "title": wx["source"], "url": wx["url"],
                  "publisher": "Open-Meteo", "used_for": "Weather term at chokepoints",
                  "seen": wx["as_of"]})
    sl = assessment["sanctions_landscape"]
    cites.append({"type": "Sanctions", "title": sl["source"], "url": sl["url"],
                  "publisher": "US Treasury / OpenSanctions",
                  "used_for": "Sanctions term and counterparty screening", "seen": sl["as_of"]})
    if scenario:
        cites.append({"type": "Precedent", "title": scenario["precedent_source"]["label"],
                      "url": scenario["precedent_source"]["url"], "publisher": "Scenario basis",
                      "used_for": scenario["name"], "seen": ""})
    return cites


async def brief(assessment: dict, recs: dict, scenario: dict | None = None) -> Dict[str, Any]:
    call = _call(assessment, recs, scenario)
    call["narrative"] = await _phrase(call, scenario)
    return sourced(call, source="SUPATH advisor", url="", mode=MODELLED,
                   method="Deterministic reasoning over the live corridor assessment, the "
                          "recommendation set and (if running) the scenario result. Language "
                          "may be polished by an LLM; numbers and citations never are.")


async def _phrase(call: dict, scenario: dict | None) -> str:
    """Optional fluency pass. Falls back to the deterministic text, which is
    already complete — the LLM is a nicety, not a dependency.

    Cached by content, not time: /api/brief can be polled every couple of
    minutes by every open tab, and the underlying facts don't change faster
    than the sources feeding them already refresh (600-1800s TTLs). Without
    this, an ANTHROPIC_API_KEY on a public deployment pays for a fresh call on
    every poll of every visitor's browser for no reason — a real, unbounded
    cost for zero additional information.
    """
    base = call["headline"] + " " + (call["reasoning"][-1]["text"] if call["reasoning"] else "")
    if not SETTINGS.anthropic_key:
        return base

    facts = {
        "posture": call["posture"],
        "headline": call["headline"],
        "reasoning": [r["text"] for r in call["reasoning"]],
        "lead_action": call["lead_action"],
        "scenario": scenario["name"] if scenario else None,
    }
    cache_key = "advisor_phrase:" + hashlib.sha256(str(facts).encode()).hexdigest()[:16]
    cached = CACHE.get(cache_key, ttl=1800)
    if cached is not None:
        return cached

    try:
        import httpx
        prompt = (
            "You are drafting the opening paragraph of a briefing note for India's Ministry of "
            "Petroleum and Natural Gas. Use ONLY the facts below. Do not add numbers, do not "
            "soften the recommendation, do not editorialise. Three sentences, plain official "
            "English, no bullet points.\n\n" + str(facts)
        )
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": SETTINGS.anthropic_key,
                         "anthropic-version": "2023-06-01",
                         "content-type": "application/json"},
                json={"model": "claude-sonnet-4-6", "max_tokens": 400,
                      "messages": [{"role": "user", "content": prompt}]})
            if r.status_code == 200:
                parts = [b.get("text", "") for b in r.json().get("content", [])]
                text = "".join(parts).strip()
                if text:
                    CACHE.set(cache_key, text)
                    return text
    except Exception:
        pass
    # Cache the fallback too (short-lived) — an unreachable Anthropic API
    # shouldn't cost every subsequent poll a 20s timeout until the facts
    # actually change.
    CACHE.set(cache_key, base)
    return base
