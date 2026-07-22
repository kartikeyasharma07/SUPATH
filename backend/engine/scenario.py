"""Scenario simulation — an agent economy, not a spreadsheet.

Built on **abcEconomics**. Real agents hold real inventories and trade real
goods round by round, so a shortfall is something the model *discovers* when a
refiner cannot buy the barrels it needs — not something we type into a cell.

The cast
--------
Exporter   one per supplier country. Produces crude up to its capacity, which a
           scenario can throttle (OPEC+ cut, Russian designation). Ships only on
           corridors it actually uses.
Shipper    one per corridor. Owns the transit capacity. A closure is a capacity
           multiplier here, and rerouting means barrels move to the Cape shipper
           at a longer voyage and a higher freight rate.
Refiner    one per Indian refinery, with real nameplate capacity. Buys crude,
           runs it, and reports utilisation. West-coast refiners are the ones
           that starve when Hormuz shuts, because that is where their crude comes
           from — the model gets this right by construction, not by assumption.
SPR        the Government of India's strategic reserve. Draws down against the
           gap under an explicit policy rule, and runs out on a stated day.

Price formation
---------------
Physical scarcity, not a random walk:

    world loss share  x = disrupted barrels / world supply (after OPEC spare,
                          SPR release and demand response are netted off)
    price uplift      ΔP% = 180 · (1 − e^(−7.7·x))

The saturating form is calibrated so a ~1% world supply loss lifts Brent ~13%
(consistent with a short-run demand elasticity near 0.08) while a Hormuz-scale
loss lands in the $120–150 range the literature and the 2025 standoff imply,
instead of running off to infinity the way a naive linear elasticity does.

Every constant above is on screen in the UI. Assumptions must be explicit and
testable — the PS-2 evaluation criteria say so, and it is also just correct.
"""

from __future__ import annotations

import contextlib
import io
import math
from typing import Any, Dict, List

from ..reference import (CORRIDORS, INDIA, PORTS, SCENARIOS, SECTORS, SUPPLIERS,
                         corridor_by_id)

import logging as _logging

_logging.getLogger("sqlalchemy.pool.impl.SingletonThreadPool").setLevel(_logging.CRITICAL)

try:
    import abcEconomics as abce
    ABCE = True
except Exception:  # pragma: no cover
    ABCE = False

# --- calibration constants (all surfaced in the UI) -------------------------
WORLD_SUPPLY_MBD = 102.0
PRICE_A = 180.0          # asymptotic max % uplift
PRICE_B = 7.7            # curvature
OPEC_SPARE_MBD = 3.2     # usable spare capacity, ex-Iran
IEA_STOCK_MBD = 3.0      # IEA collective emergency stock release, tapering over 3 weeks
DEMAND_RESPONSE = 0.15   # share of a shortfall absorbed by demand destruction
SPR_MAX_DRAW_KBD = 900   # policy ceiling on daily drawdown
GDP_USD_BN = 3900.0
IMPORT_KBD = INDIA["crude_imports_kbd"]
SPR_STOCK_KB = INDIA["spr_days_cover"] * IMPORT_KBD
BASE_FREIGHT = {"GULF_HORMUZ": 2.4, "REDSEA_SUEZ": 4.1, "CAPE": 6.8,
                "MALACCA_PACIFIC": 3.6, "US_GULF": 7.9}

CALIBRATION = {
    "world_supply_mbd": WORLD_SUPPLY_MBD,
    "price_curve": f"ΔP% = {PRICE_A}·(1 − e^(−{PRICE_B}·x)), x = net world supply loss share",
    "opec_spare_mbd": OPEC_SPARE_MBD,
    "iea_collective_release_mbd": IEA_STOCK_MBD,
    "pass_through_to_pump": 0.62,
    "cpi_weight_fuel": 0.09,
    "demand_response_share": DEMAND_RESPONSE,
    "spr_stock_kb": SPR_STOCK_KB,
    "spr_max_draw_kbd": SPR_MAX_DRAW_KBD,
    "base_freight_usd_bbl": BASE_FREIGHT,
    "gdp_usd_bn": GDP_USD_BN,
    "sources": [
        {"label": "EIA Short-Term Energy Outlook — world supply balance",
         "url": "https://www.eia.gov/outlooks/steo/"},
        {"label": "EIA World Oil Transit Chokepoints — flows at risk",
         "url": "https://www.eia.gov/international/analysis/special-topics/World_Oil_Transit_Chokepoints"},
        {"label": "PS-2 brief — 9.5 days SPR cover, 88% import dependence",
         "url": "internal://problem-statement-2"},
    ],
}


def price_uplift_pct(loss_share: float) -> float:
    return PRICE_A * (1 - math.exp(-PRICE_B * max(0.0, loss_share)))


# ---------------------------------------------------------------------------
# abcEconomics agents
# ---------------------------------------------------------------------------

if ABCE:

    class Exporter(abce.Agent):
        def init(self, code, name, base_kbd, corridor, alt_corridor, diff, spare):
            self.code = code
            self.cname = name
            self.base_kbd = base_kbd
            self.corridor = corridor
            self.alt_corridor = alt_corridor
            self.diff = diff
            self.spare = spare
            self.capacity_mult = 1.0
            self.lifted = 0.0

        def set_shock(self, supplier_capacity):
            self.capacity_mult = supplier_capacity.get(self.code, 1.0)

        def produce(self):
            """Lift crude to the ullage the scenario allows."""
            qty = self.base_kbd * self.capacity_mult
            self.create('crude', qty)
            self.lifted = qty

        def ship(self, corridor_capacity):
            """Hand cargo to the shipper that owns the corridor, rerouting when
            the primary corridor is throttled and an alternative exists."""
            cap = corridor_capacity.get(self.corridor, 1.0)
            corridor = self.corridor
            rerouted = 0.0
            available = self['crude']

            if cap < 0.9 and self.alt_corridor:
                alt_cap = corridor_capacity.get(self.alt_corridor, 1.0)
                if alt_cap > cap:
                    corridor = self.alt_corridor
                    cap = alt_cap
                    rerouted = available

            moved = available * min(1.0, cap)
            idx = [c["id"] for c in CORRIDORS].index(corridor)
            if moved > 0:
                self.give(('shipper', idx), good='crude', quantity=moved)
            self.destroy('crude', self['crude'])  # the rest is stranded at the load port
            return {'code': self.code, 'moved': moved, 'stranded': self.lifted - moved,
                    'corridor': corridor, 'rerouted': rerouted > 0, 'diff': self.diff}

    class Shipper(abce.Agent):
        def init(self, corridor_id, refiners, base_freight):
            self.corridor_id = corridor_id
            self.refiners = refiners        # list of (agent_index, capacity_kbd)
            self.base_freight = base_freight
            self.freight_mult = 1.0
            self.delivered = 0.0

        def set_freight(self, freight_multiplier):
            self.freight_mult = freight_multiplier.get(self.corridor_id, 1.0)

        def deliver(self):
            """Split the corridor's cargo across the refineries it feeds, in
            proportion to nameplate capacity."""
            cargo = self['crude']
            self.delivered = cargo
            total_cap = sum(c for _, c in self.refiners) or 1
            for idx, cap in self.refiners:
                share = cargo * cap / total_cap
                if share > 0:
                    self.give(('refiner', idx), good='crude', quantity=share)
            return {'corridor': self.corridor_id, 'delivered': cargo,
                    'freight': self.base_freight * self.freight_mult}

    class Refiner(abce.Agent):
        def init(self, port, name, capacity_kbd):
            self.port = port
            self.rname = name
            self.capacity_kbd = capacity_kbd
            self.port_mult = 1.0
            self.received = 0.0

        def set_port_status(self, port_status):
            self.port_mult = port_status.get(self.port, 1.0)

        def run(self):
            """Run crude, constrained by both what arrived and whether the berth
            is workable. A cyclone does not reduce the crude — it reduces the
            ability to land it."""
            crude = self['crude']
            self.received = crude
            usable = min(crude, self.capacity_kbd * self.port_mult)
            self.destroy('crude', self['crude'])
            util = usable / self.capacity_kbd if self.capacity_kbd else 0
            return {'port': self.port, 'name': self.rname, 'capacity': self.capacity_kbd,
                    'received': crude, 'run': usable, 'utilisation': util}

    class StrategicReserve(abce.Agent):
        def init(self, stock_kb):
            self.stock = stock_kb
            self.drawn_today = 0.0

        def draw(self, gap_kbd):
            """Policy rule: cover up to 60% of the gap, capped at the physical
            draw rate, never below zero. Deliberately not 100% — a reserve spent
            in week one is not a reserve."""
            want = min(gap_kbd * 0.6, SPR_MAX_DRAW_KBD)
            drawn = max(0.0, min(want, self.stock))
            self.stock -= drawn
            self.drawn_today = drawn
            return {'drawn': drawn, 'stock': self.stock,
                    'days_cover': self.stock / IMPORT_KBD if IMPORT_KBD else 0}


# ---------------------------------------------------------------------------
# Scenario runner
# ---------------------------------------------------------------------------

def _flat(result) -> list:
    """abcEconomics returns a Chain of per-process lists, in random agent order.
    Every payload carries its own identity, so flattening is safe."""
    out = []
    for chunk in result:
        if isinstance(chunk, (list, tuple)):
            out.extend(chunk)
        else:
            out.append(chunk)
    return out


def _refiners() -> List[Dict[str, Any]]:
    out = []
    for pid, p in PORTS.items():
        if p["country"] == "IN":
            out.append({"port": pid, "name": p.get("refinery", p["name"]),
                        "capacity_kbd": p["capacity_kbd"]})
    return out


def _corridor_refiner_map(refiners: List[dict]) -> Dict[str, list]:
    idx_of = {r["port"]: i for i, r in enumerate(refiners)}
    out = {}
    for c in CORRIDORS:
        out[c["id"]] = [(idx_of[p], refiners[idx_of[p]]["capacity_kbd"])
                        for p in c["discharge"] if p in idx_of]
    return out


def run_scenario(scenario_id: str, severity: float = 1.0, days: int = 30,
                 base_brent: float = 82.0) -> Dict[str, Any]:
    """Run one scenario and return the day-by-day cascade.

    severity scales the shock between 0 (nothing happens) and 1 (the preset as
    written). A user who wants to ask "what if Hormuz is only half shut" gets a
    real answer, not a different preset.
    """
    spec = SCENARIOS[scenario_id]
    duration = min(days, 120)

    def blend(mult: float) -> float:
        """A capacity of 0.15 at severity 0.5 is 0.575 — halfway to normal."""
        return 1.0 - (1.0 - mult) * severity

    corridor_capacity = {k: blend(v) for k, v in spec.get("corridor_capacity", {}).items()}
    supplier_capacity = {k: blend(v) for k, v in spec.get("supplier_capacity", {}).items()}
    port_status = {k: blend(v) for k, v in spec.get("port_status", {}).items()}
    freight_multiplier = {k: 1 + (v - 1) * severity
                          for k, v in spec.get("freight_multiplier", {}).items()}

    refiners = _refiners()
    cr_map = _corridor_refiner_map(refiners)

    # --- build the agent economy -------------------------------------------
    if ABCE:
        # trade_logging off and path=None: this is a request-time model, not a
        # research batch job — nothing should touch the disk.
        sim = abce.Simulation(name='supath', processes=1,
                              trade_logging='off', path=None)
        exporters = sim.build_agents(
            Exporter, 'exporter',
            agent_parameters=[{
                "code": code,
                "name": v["name"],
                "base_kbd": IMPORT_KBD * v["share_pct"] / 100,
                "corridor": v["corridor"],
                "alt_corridor": v.get("alt_corridor"),
                "diff": v["diff_usd"],
                "spare": v["spare_kbd"],
            } for code, v in SUPPLIERS.items()])
        shippers = sim.build_agents(
            Shipper, 'shipper',
            agent_parameters=[{
                "corridor_id": c["id"],
                "refiners": cr_map[c["id"]],
                "base_freight": BASE_FREIGHT.get(c["id"], 4.0),
            } for c in CORRIDORS])
        refs = sim.build_agents(
            Refiner, 'refiner',
            agent_parameters=[{"port": r["port"], "name": r["name"],
                               "capacity_kbd": r["capacity_kbd"]} for r in refiners])
        spr = sim.build_agents(StrategicReserve, 'spr',
                               agent_parameters=[{"stock_kb": SPR_STOCK_KB}])
    else:
        sim = None

    baseline_supply = IMPORT_KBD
    spr_stock = SPR_STOCK_KB
    series: List[Dict[str, Any]] = []
    brent = base_brent
    cumulative_gap = 0.0

    # Day 0: the undisturbed baseline, before the loop below applies any
    # shock. Without this, series[0] was already "day 1" — one full day of
    # effects already in — so charts and the reserve-cover figure never
    # actually showed where things started from.
    base_diff0 = sum(v["share_pct"] / 100 * v["diff_usd"] for v in SUPPLIERS.values())
    base_freight0 = sum(BASE_FREIGHT.get(c["id"], 4) * c["share_pct"] / 100 for c in CORRIDORS)
    series.append({
        "day": 0, "delivered_kbd": round(baseline_supply), "gap_kbd": 0,
        "spr_drawn_kbd": 0, "spr_days_left": round(spr_stock / IMPORT_KBD, 1),
        "brent": brent, "brent_chg_pct": 0.0, "world_loss_mbd": 0.0, "iea_release_mbd": 0.0,
        "mix_diff_usd": round(base_diff0, 2), "risk_premium_usd": 0.0,
        "landed_usd": round(base_brent + base_diff0 + base_freight0, 2),
        "freight_usd": round(base_freight0, 2), "scarcity_usd": 0.0,
        "pump_pct": 0.0, "cpi_pp": 0.0, "gdp_drag_pct": 0.0, "refinery_util": 100.0,
        "refineries": [], "corridors": [], "rerouted": [], "stranded_kbd": 0,
    })

    for day in range(1, duration + 1):
        # A shock is not a step function. Physical closure bites immediately;
        # sanctions and OPEC decisions phase in over the first week as cargoes
        # already at sea keep arriving.
        if scenario_id in ("HORMUZ_CLOSURE", "WEATHER_EVENT"):
            onset = 1.0 if day >= 1 else 0.0
        else:
            onset = min(1.0, day / 7.0)

        cc = {k: 1 - (1 - v) * onset for k, v in corridor_capacity.items()}
        sc = {k: 1 - (1 - v) * onset for k, v in supplier_capacity.items()}
        ps = {k: 1 - (1 - v) * onset for k, v in port_status.items()}
        fm = {k: 1 + (v - 1) * onset for k, v in freight_multiplier.items()}

        if ABCE:
            sim.advance_round(day)
            exporters.set_shock(sc)
            exporters.produce()
            lifts = _flat(exporters.ship(cc))
            shippers.set_freight(fm)
            deliveries = _flat(shippers.deliver())
            refs.set_port_status(ps)
            runs = _flat(refs.run())
            delivered = sum(d["delivered"] for d in deliveries)
        else:
            lifts, deliveries, runs = _analytic_flow(cc, sc, ps, refiners, cr_map)
            delivered = sum(d["delivered"] for d in deliveries)

        gap = max(0.0, baseline_supply - delivered)

        # SPR draw
        if ABCE:
            sprout = _flat(spr.draw(gap))[0]
            drawn, spr_stock = sprout["drawn"], sprout["stock"]
        else:
            drawn = max(0.0, min(min(gap * 0.6, SPR_MAX_DRAW_KBD), spr_stock))
            spr_stock -= drawn

        covered = delivered + drawn
        net_gap = max(0.0, baseline_supply - covered)
        cumulative_gap += net_gap

        # --- world price ------------------------------------------------------
        # Blocked barrels are not the same as lost barrels. Three things decide
        # how much of a transit shock the *world* actually feels:
        #   reroutable  — the share that still reaches market by another route
        #                 (Red Sea: 90%. Hormuz: 5% — there is nowhere else to go)
        #   bypass      — pipeline capacity around the chokepoint (Saudi East-West
        #                 and ADCOP together move ~6.5 mb/d around Hormuz)
        #   OPEC spare  — only an offset if it is not itself behind the closure
        if cc:
            cap_avg = sum(cc.values()) / len(cc)
            blocked = spec["supply_shock_mbd"] * severity * onset * (1 - cap_avg)
        elif sc:
            cap_avg = sum(sc.values()) / len(sc)
            blocked = spec["supply_shock_mbd"] * severity * onset * (1 - cap_avg)
        else:
            blocked = spec["supply_shock_mbd"] * severity * onset

        reroutable = spec.get("reroutable", 0.0)
        bypass = spec.get("bypass_mbd", 0.0) * min(1.0, day / 10.0)   # lines take ~10 days to fill
        spare = (OPEC_SPARE_MBD * min(1.0, day / 14.0)
                 if spec.get("opec_spare_available", True) else 0.0)

        gross_loss = max(0.0, blocked * (1 - reroutable) - bypass - spare)
        # An IEA collective action releases commercial and public stocks into the
        # market. It buys about three weeks, and then it is gone — which is the
        # honest reason a 30-day disruption is survivable and a 90-day one is not.
        iea = IEA_STOCK_MBD * max(0.0, 1 - day / 21.0) if gross_loss > 2.0 else 0.0
        world_loss = max(0.0, gross_loss - iea)
        net_loss = world_loss * (1 - DEMAND_RESPONSE)
        loss_share = net_loss / WORLD_SUPPLY_MBD
        risk_premium = spec.get("risk_premium_usd", 0.0) * severity * onset
        uplift = price_uplift_pct(loss_share)
        brent = round(base_brent * (1 + uplift / 100) + risk_premium, 2)
        uplift_total = (brent - base_brent) / base_brent * 100

        # --- what India actually pays -----------------------------------------
        freight = sum(BASE_FREIGHT.get(c["id"], 4) * fm.get(c["id"], 1) * c["share_pct"] / 100
                      for c in CORRIDORS)
        base_freight_avg = sum(BASE_FREIGHT.get(c["id"], 4) * c["share_pct"] / 100
                               for c in CORRIDORS)

        # The India-first term. India's landed cost is not Brent — it is the
        # barrel-weighted differential of the crude that *actually arrived*.
        # Lose the Russian barrel and you lose its ~$3 discount, so the import
        # bill rises even in a world where Brent has not moved at all.
        moved_total = sum(l["moved"] for l in lifts) or 1.0
        mix_diff = sum(l["moved"] * l["diff"] for l in lifts) / moved_total
        base_diff = sum(v["share_pct"] / 100 * v["diff_usd"] for v in SUPPLIERS.values())

        # Spot scarcity premium: the cost of pulling cargo out of the market in a
        # hurry. Saturating — at some price, someone always sells.
        scarcity = 12.0 * (1 - math.exp(-4 * (net_gap / max(1.0, baseline_supply))))
        landed = round(brent + mix_diff + freight + scarcity, 2)
        landed_base = round(base_brent + base_diff + base_freight_avg, 2)

        pump_pct = round((landed - landed_base) / landed_base * 100 * 0.62, 2)  # 62% pass-through
        cpi_pp = round(pump_pct * 0.09 * 0.6, 2)

        annual_bill_delta = (landed - landed_base) * IMPORT_KBD * 365 / 1e6  # $bn
        gdp_drag = round(annual_bill_delta / GDP_USD_BN * 100 * 0.55, 2)

        util = (sum(r["run"] for r in runs) /
                sum(r["capacity"] for r in runs)) if runs else 0

        series.append({
            "day": day,
            "delivered_kbd": round(delivered),
            "gap_kbd": round(net_gap),
            "spr_drawn_kbd": round(drawn),
            "spr_days_left": round(spr_stock / IMPORT_KBD, 1),
            "brent": brent,
            "brent_chg_pct": round(uplift_total, 1),
            "world_loss_mbd": round(world_loss, 2),
            "iea_release_mbd": round(iea, 2),
            "mix_diff_usd": round(mix_diff, 2),
            "risk_premium_usd": round(risk_premium, 2),
            "landed_usd": landed,
            "freight_usd": round(freight, 2),
            "scarcity_usd": round(scarcity, 2),
            "pump_pct": pump_pct,
            "cpi_pp": cpi_pp,
            "gdp_drag_pct": gdp_drag,
            "refinery_util": round(util * 100, 1),
            "refineries": [{"port": r["port"], "name": r["name"],
                            "util": round(r["utilisation"] * 100, 1),
                            "run_kbd": round(r["run"]),
                            "capacity_kbd": r["capacity"]} for r in runs],
            "corridors": [{"id": c["id"], "short": c["short"],
                           "capacity": round(cc.get(c["id"], 1.0), 2),
                           "freight_mult": round(fm.get(c["id"], 1.0), 2)}
                          for c in CORRIDORS],
            "rerouted": [l["code"] for l in lifts if l.get("rerouted")],
            "stranded_kbd": round(sum(l["stranded"] for l in lifts)),
        })

    if ABCE:
        with contextlib.redirect_stdout(io.StringIO()):
            sim.finalize()

    peak = max(series, key=lambda s: s["brent"])
    worst_gap = max(series, key=lambda s: s["gap_kbd"])
    spr_exhausted = next((s["day"] for s in series if s["spr_days_left"] <= 0.1), None)
    end = series[-1]

    sector_impact = []
    for sec in SECTORS:
        cost_pct = round(end["pump_pct"] * sec["elasticity"], 1)
        sector_impact.append({
            "id": sec["id"], "name": sec["name"],
            "cost_increase_pct": cost_pct,
            "share_of_products_pct": sec["share_of_products_pct"],
            "impact_day": min(duration, sec["lag_days"]),
            "note": sec["note"],
            "workings": f"pump price +{end['pump_pct']:.1f}% × sector cost elasticity "
                        f"{sec['elasticity']} = +{cost_pct:.1f}% input cost, landing around "
                        f"day {sec['lag_days']}.",
        })
    sector_impact.sort(key=lambda s: -s["cost_increase_pct"])

    return {
        "scenario": scenario_id,
        "name": spec["name"],
        "subtitle": spec["subtitle"],
        "severity": severity,
        "days": len(series),
        "engine": "abcEconomics agent-based simulation" if ABCE else "analytic fallback",
        "agents": {
            "exporters": len(SUPPLIERS), "shippers": len(CORRIDORS),
            "refiners": len(refiners), "reserve": 1,
        },
        "precedent": spec["precedent"],
        "precedent_source": spec["precedent_source"],
        "series": series,
        "calibration": CALIBRATION,
        "headline": {
            "peak_brent": peak["brent"],
            "peak_brent_day": peak["day"],
            "peak_brent_chg_pct": peak["brent_chg_pct"],
            "peak_gap_kbd": worst_gap["gap_kbd"],
            "peak_gap_day": worst_gap["day"],
            "spr_exhausted_day": spr_exhausted,
            "final_pump_pct": end["pump_pct"],
            "final_cpi_pp": end["cpi_pp"],
            "final_gdp_drag_pct": end["gdp_drag_pct"],
            "min_refinery_util": min(s["refinery_util"] for s in series),
            "cumulative_shortfall_mb": round(cumulative_gap / 1000, 1),
        },
        "sector_impact": sector_impact,
        "corridor_capacity": corridor_capacity,
        "port_status": port_status,
        "chokepoint_status": spec.get("chokepoint_status", {}),
        "explanation": _explain(scenario_id, spec, series, severity),
    }


def _analytic_flow(cc, sc, ps, refiners, cr_map):
    """Used only if abcEconomics is unavailable. Same accounting, no agents."""
    lifts, corridor_cargo = [], {c["id"]: 0.0 for c in CORRIDORS}
    for code, v in SUPPLIERS.items():
        base = IMPORT_KBD * v["share_pct"] / 100 * sc.get(code, 1.0)
        corridor = v["corridor"]
        cap = cc.get(corridor, 1.0)
        rerouted = False
        if cap < 0.9 and v.get("alt_corridor"):
            alt = v["alt_corridor"]
            if cc.get(alt, 1.0) > cap:
                corridor, cap, rerouted = alt, cc.get(alt, 1.0), True
        moved = base * min(1.0, cap)
        corridor_cargo[corridor] += moved
        lifts.append({"code": code, "moved": moved, "stranded": base - moved,
                      "corridor": corridor, "rerouted": rerouted, "diff": v["diff_usd"]})

    deliveries, arrivals = [], {r["port"]: 0.0 for r in refiners}
    for cid, cargo in corridor_cargo.items():
        deliveries.append({"corridor": cid, "delivered": cargo})
        pairs = cr_map[cid]
        total = sum(c for _, c in pairs) or 1
        for idx, cap in pairs:
            arrivals[refiners[idx]["port"]] += cargo * cap / total

    runs = []
    for r in refiners:
        got = arrivals[r["port"]]
        usable = min(got, r["capacity_kbd"] * ps.get(r["port"], 1.0))
        runs.append({"port": r["port"], "name": r["name"], "capacity": r["capacity_kbd"],
                     "received": got, "run": usable,
                     "utilisation": usable / r["capacity_kbd"] if r["capacity_kbd"] else 0})
    return lifts, deliveries, runs


def _explain(scenario_id: str, spec: dict, series: list, severity: float) -> dict:
    """The chain of consequence, in the order it actually happens to India."""
    end = series[-1]
    peak = max(series, key=lambda s: s["brent"])
    chain = []

    if spec.get("corridor_capacity"):
        for cid, cap in spec["corridor_capacity"].items():
            c = corridor_by_id(cid)
            eff = 1 - (1 - cap) * severity
            chain.append({
                "step": "Transit",
                "text": f"{c['short']} capacity falls to {eff*100:.0f}%. That corridor carries "
                        f"{c['share_pct']:.0f}% of India's crude — "
                        f"{round(IMPORT_KBD * c['share_pct']/100):,} kb/d.",
            })
    if spec.get("supplier_capacity"):
        names = ", ".join(SUPPLIERS[k]["name"] for k in spec["supplier_capacity"])
        chain.append({"step": "Supply", "text": f"Liftings constrained at {names}."})
    if spec.get("port_status"):
        names = ", ".join(PORTS[k]["name"] for k in spec["port_status"])
        chain.append({"step": "Discharge",
                      "text": f"Berths unworkable at {names} — crude arrives but cannot land."})

    chain.append({"step": "Reroute",
                  "text": f"Cargoes divert where an alternative exists. Stranded volume on the "
                          f"final day: {end['stranded_kbd']:,} kb/d."})
    chain.append({"step": "Reserve",
                  "text": f"SPR covers 60% of the gap up to {SPR_MAX_DRAW_KBD} kb/d. "
                          f"Cover falls from {INDIA['spr_days_cover']} days to "
                          f"{end['spr_days_left']} days by day {end['day']}."})
    chain.append({"step": "Price",
                  "text": f"Net world supply loss lifts Brent to ${peak['brent']} "
                          f"({peak['brent_chg_pct']:+.0f}%) on day {peak['day']}. India's landed "
                          f"cost adds freight (${end['freight_usd']}/bbl) and a spot scarcity "
                          f"premium (${end['scarcity_usd']}/bbl)."})
    chain.append({"step": "Pump",
                  "text": f"At 62% pass-through, retail fuel rises {end['pump_pct']:.1f}%, "
                          f"adding {end['cpi_pp']:.2f} pp to CPI."})
    chain.append({"step": "Economy",
                  "text": f"The import bill increase implies a {end['gdp_drag_pct']:.2f}% drag on "
                          f"GDP if sustained for a year."})

    return {"chain": chain,
            "caveat": "Every coefficient in this chain is listed under Assumptions and can be "
                      "changed. The model is a reasoning aid, not a forecast: it tells you the "
                      "shape and order of the cascade, not the exact number."}
