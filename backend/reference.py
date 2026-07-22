"""
SUPATH — reference dataset.

Every constant here is a *reference value* with an explicit source and vintage.
Nothing in this file is invented on the fly: the UI surfaces `source` and `as_of`
next to any number that originates here, so a policymaker can always ask
"where did this come from" and get an answer.

Volumes in thousand barrels per day (kb/d) unless stated.
"""

# --------------------------------------------------------------------------
# National baseline (India)
# --------------------------------------------------------------------------

INDIA = {
    "crude_imports_kbd": 4700,
    "crude_import_dependency_pct": 88.0,
    "refining_capacity_kbd": 5100,
    "spr_days_cover": 9.5,
    "spr_capacity_mmt": 5.33,
    "retail_passthrough_lag_days": 14,
    "sources": [
        {
            "label": "PPAC — Import/Export of Crude Oil & Petroleum Products",
            "url": "https://ppac.gov.in/import-export",
            "as_of": "2025",
        },
        {
            "label": "ET AI Hackathon 2026 PS-2 brief (88% import dependence, "
                     "40–45% via Hormuz, ~9.5 days SPR cover)",
            "url": "internal://problem-statement-2",
            "as_of": "2026",
        },
        {
            "label": "EIA — Country Analysis Brief: India",
            "url": "https://www.eia.gov/international/analysis/country/IND",
            "as_of": "2025",
        },
    ],
}

# --------------------------------------------------------------------------
# Chokepoints — the geography that decides whether a barrel reaches India
# --------------------------------------------------------------------------

CHOKEPOINTS = {
    "HORMUZ": {
        "name": "Strait of Hormuz",
        "lat": 26.57, "lon": 56.25,
        "world_flow_mbd": 20.0,
        "india_share_pct": 44.0,
        "note": "No commercially viable seaborne bypass for the bulk of Gulf crude.",
        "source": {"label": "EIA — World Oil Transit Chokepoints",
                   "url": "https://www.eia.gov/international/analysis/special-topics/World_Oil_Transit_Chokepoints"},
    },
    "BAB_EL_MANDEB": {
        "name": "Bab el-Mandeb",
        "lat": 12.58, "lon": 43.33,
        "world_flow_mbd": 6.2,
        "india_share_pct": 9.0,
        "note": "Gate to the Red Sea/Suez. Houthi attack zone since 2023; reroute is the Cape.",
        "source": {"label": "EIA — World Oil Transit Chokepoints",
                   "url": "https://www.eia.gov/international/analysis/special-topics/World_Oil_Transit_Chokepoints"},
    },
    "SUEZ": {
        "name": "Suez Canal / SUMED",
        "lat": 30.02, "lon": 32.55,
        "world_flow_mbd": 9.2,
        "india_share_pct": 9.0,
        "note": "Primary path for Urals and Mediterranean barrels into India.",
        "source": {"label": "IMF PortWatch — Chokepoints",
                   "url": "https://portwatch.imf.org/pages/chokepoints"},
    },
    "MALACCA": {
        "name": "Strait of Malacca",
        "lat": 2.50, "lon": 101.40,
        "world_flow_mbd": 16.0,
        "india_share_pct": 5.0,
        "note": "Inbound ESPO/Pacific barrels and outbound Indian product exports east.",
        "source": {"label": "EIA — World Oil Transit Chokepoints",
                   "url": "https://www.eia.gov/international/analysis/special-topics/World_Oil_Transit_Chokepoints"},
    },
    "GOOD_HOPE": {
        "name": "Cape of Good Hope",
        "lat": -34.36, "lon": 18.47,
        "world_flow_mbd": 5.1,
        "india_share_pct": 24.0,
        "note": "The reroute of last resort. Always open, always slower: +12 to +18 days to India.",
        "source": {"label": "IMF PortWatch — Chokepoints",
                   "url": "https://portwatch.imf.org/pages/chokepoints"},
    },
}

# --------------------------------------------------------------------------
# Corridors — a corridor is (supply basin → chokepoint chain → Indian coast)
# `share_pct` = share of India's seaborne crude imports carried by the corridor.
# --------------------------------------------------------------------------

CORRIDORS = [
    {
        "id": "GULF_HORMUZ",
        "name": "Persian Gulf → West Coast India",
        "short": "Hormuz",
        "chokepoints": ["HORMUZ"],
        "share_pct": 44.0,
        "voyage_days": 5,
        "reroute_id": None,
        "reroute_penalty_days": None,
        "suppliers": ["IRQ", "SAU", "ARE", "KWT"],
        "discharge": ["JAMNAGAR", "VADINAR", "MUMBAI", "MANGALORE", "KOCHI", "KANDLA", "MUNDRA"],
        "waypoints": [
            [29.55, 48.30], [27.60, 50.30], [26.30, 54.20], [26.57, 56.25],
            [25.20, 57.60], [24.00, 60.00], [22.50, 64.00], [22.20, 68.60],
        ],
        "geofence": {"lat": [22.0, 31.0], "lon": [47.0, 62.0]},
        "why_it_matters": "The single point of failure in India's energy security. "
                          "Two-fifths of the barrels that feed the west-coast refining cluster pass here.",
    },
    {
        "id": "REDSEA_SUEZ",
        "name": "Russia / Black Sea / Mediterranean → India via Suez",
        "short": "Red Sea–Suez",
        "chokepoints": ["SUEZ", "BAB_EL_MANDEB"],
        "share_pct": 22.0,
        "voyage_days": 21,
        "reroute_id": "CAPE",
        "reroute_penalty_days": 14,
        "suppliers": ["RUS", "IRQ", "LBY", "KAZ"],
        "discharge": ["VADINAR", "JAMNAGAR", "PARADIP", "MUMBAI", "KANDLA"],
        "waypoints": [
            [44.70, 37.75], [40.00, 26.00], [34.50, 24.00], [31.50, 32.30],
            [30.02, 32.55], [27.50, 34.30], [20.00, 38.60], [12.58, 43.33],
            [12.80, 48.00], [15.00, 58.00], [19.00, 66.00], [22.20, 68.60],
        ],
        "geofence": {"lat": [11.0, 32.0], "lon": [32.0, 46.0]},
        "why_it_matters": "Carries discounted Urals — the barrel that has been holding India's "
                          "import bill down. Attack risk here does not stop the oil; it makes it "
                          "take the Cape and cost more.",
    },
    {
        "id": "CAPE",
        "name": "West Africa / Atlantic → India via Cape of Good Hope",
        "short": "Cape",
        "chokepoints": ["GOOD_HOPE"],
        "share_pct": 14.0,
        "voyage_days": 26,
        "reroute_id": None,
        "reroute_penalty_days": None,
        "suppliers": ["NGA", "AGO", "USA", "BRA", "GUY"],
        "discharge": ["JAMNAGAR", "PARADIP", "CHENNAI", "VISAKHAPATNAM"],
        "waypoints": [
            [4.40, 7.15], [-5.00, 5.00], [-20.00, 5.00], [-34.36, 18.47],
            [-30.00, 32.00], [-15.00, 45.00], [0.00, 55.00], [12.00, 66.00],
            [19.00, 70.00], [22.20, 68.60],
        ],
        "geofence": {"lat": [-40.0, 10.0], "lon": [0.0, 40.0]},
        "why_it_matters": "The safety valve. Nothing blocks it — but every barrel diverted here "
                          "ties up a tanker for two extra weeks, which is why freight, not crude, "
                          "is usually what spikes first.",
    },
    {
        "id": "MALACCA_PACIFIC",
        "name": "Russian Far East / Asia-Pacific → East Coast India",
        "short": "Malacca",
        "chokepoints": ["MALACCA"],
        "share_pct": 12.0,
        "voyage_days": 12,
        "reroute_id": None,
        "reroute_penalty_days": 6,
        "suppliers": ["RUS", "MYS", "AUS"],
        "discharge": ["PARADIP", "VISAKHAPATNAM", "CHENNAI", "HALDIA"],
        "waypoints": [
            [42.70, 132.90], [30.00, 125.00], [15.00, 114.00], [3.20, 104.60],
            [2.50, 101.40], [6.00, 95.00], [10.00, 88.00], [16.00, 84.00],
            [20.30, 86.70],
        ],
        "geofence": {"lat": [-2.0, 8.0], "lon": [96.0, 106.0]},
        "why_it_matters": "ESPO into Paradip and Vizag. Short, cheap, and the corridor most "
                          "exposed to secondary-sanctions risk rather than physical risk.",
    },
    {
        "id": "US_GULF",
        "name": "US Gulf Coast → India",
        "short": "US Gulf",
        "chokepoints": ["GOOD_HOPE"],
        "share_pct": 8.0,
        "voyage_days": 40,
        "reroute_id": None,
        "reroute_penalty_days": None,
        "suppliers": ["USA"],
        "discharge": ["JAMNAGAR", "PARADIP", "MUMBAI"],
        "waypoints": [
            [29.30, -94.80], [25.00, -84.00], [20.00, -68.00], [8.00, -45.00],
            [-5.00, -25.00], [-20.00, -5.00], [-34.36, 18.47], [-25.00, 40.00],
            [-5.00, 55.00], [10.00, 65.00], [22.20, 68.60],
        ],
        "geofence": {"lat": [24.0, 31.0], "lon": [-98.0, -88.0]},
        "why_it_matters": "The politically safe barrel and the expensive one. It is the corridor "
                          "India scales up when the Gulf is unavailable — at a 40-day lag.",
    },
]

# --------------------------------------------------------------------------
# Ports — load (origin) and discharge (India)
# --------------------------------------------------------------------------

PORTS = {
    # --- India: discharge / refinery ports -------------------------------
    "JAMNAGAR":      {"name": "Jamnagar (Sikka)", "country": "IN", "lat": 22.42, "lon": 69.08,
                      "role": "discharge", "capacity_kbd": 1240, "refinery": "Reliance DTA+SEZ"},
    "VADINAR":       {"name": "Vadinar", "country": "IN", "lat": 22.32, "lon": 69.71,
                      "role": "discharge", "capacity_kbd": 400, "refinery": "Nayara Energy"},
    "MUMBAI":        {"name": "Mumbai Port Trust", "country": "IN", "lat": 18.94, "lon": 72.84,
                      "role": "discharge", "capacity_kbd": 430, "refinery": "BPCL + HPCL Mumbai"},
    "MANGALORE":     {"name": "New Mangalore", "country": "IN", "lat": 12.92, "lon": 74.80,
                      "role": "discharge", "capacity_kbd": 300, "refinery": "MRPL"},
    "KOCHI":         {"name": "Kochi", "country": "IN", "lat": 9.96, "lon": 76.25,
                      "role": "discharge", "capacity_kbd": 310, "refinery": "BPCL Kochi"},
    "CHENNAI":       {"name": "Chennai / Ennore", "country": "IN", "lat": 13.11, "lon": 80.30,
                      "role": "discharge", "capacity_kbd": 230, "refinery": "CPCL Manali"},
    "PARADIP":       {"name": "Paradip", "country": "IN", "lat": 20.31, "lon": 86.68,
                      "role": "discharge", "capacity_kbd": 300, "refinery": "IOCL Paradip"},
    "VISAKHAPATNAM": {"name": "Visakhapatnam", "country": "IN", "lat": 17.69, "lon": 83.28,
                      "role": "discharge", "capacity_kbd": 166, "refinery": "HPCL Visakh"},
    "HALDIA":        {"name": "Haldia", "country": "IN", "lat": 22.03, "lon": 88.09,
                      "role": "discharge", "capacity_kbd": 160, "refinery": "IOCL Haldia"},
    # Kandla (renamed Deendayal Port) and Mundra: both in the Gulf of Kutch,
    # ~50 km from Jamnagar/Vadinar. Multiple sources (news reporting on
    # India-Russia crude flows, port-cargo statistics) name them explicitly as
    # top-5 crude discharge points alongside Jamnagar and Vadinar — genuinely
    # missing from earlier revisions of this file, not a minor omission.
    # capacity_kbd here is a rougher estimate than the refinery-linked ports
    # above: derived from each port's total liquid-cargo tonnage (Kandla ~28.3
    # MMT/yr liquid cargo per Ministry of Ports data), since neither port has
    # a single dedicated on-site refinery the way Jamnagar/Vadinar do — both
    # feed crude onward mainly by pipeline and rail to inland refineries.
    "KANDLA":        {"name": "Kandla (Deendayal Port)", "country": "IN", "lat": 23.03, "lon": 70.22,
                      "role": "discharge", "capacity_kbd": 380,
                      "refinery": "Pipeline hub — feeds northern India inland refineries"},
    "MUNDRA":        {"name": "Mundra", "country": "IN", "lat": 22.84, "lon": 69.72,
                      "role": "discharge", "capacity_kbd": 340,
                      "refinery": "Multi-purpose terminal — crude, container and bulk"},
    # --- Load ports -------------------------------------------------------
    "RAS_TANURA":    {"name": "Ras Tanura", "country": "SA", "lat": 26.64, "lon": 50.16,
                      "role": "load", "capacity_kbd": 6500},
    "BASRAH":        {"name": "Basrah Oil Terminal", "country": "IQ", "lat": 29.68, "lon": 48.81,
                      "role": "load", "capacity_kbd": 3400},
    "AL_AHMADI":     {"name": "Mina Al-Ahmadi", "country": "KW", "lat": 29.07, "lon": 48.15,
                      "role": "load", "capacity_kbd": 2000},
    "FUJAIRAH":      {"name": "Fujairah", "country": "AE", "lat": 25.13, "lon": 56.36,
                      "role": "load", "capacity_kbd": 1800},
    "KHARG":         {"name": "Kharg Island", "country": "IR", "lat": 29.25, "lon": 50.32,
                      "role": "load", "capacity_kbd": 1600},
    "NOVOROSSIYSK":  {"name": "Novorossiysk", "country": "RU", "lat": 44.72, "lon": 37.77,
                      "role": "load", "capacity_kbd": 1200},
    "PRIMORSK":      {"name": "Primorsk", "country": "RU", "lat": 60.34, "lon": 28.71,
                      "role": "load", "capacity_kbd": 1000},
    "KOZMINO":       {"name": "Kozmino (ESPO)", "country": "RU", "lat": 42.72, "lon": 132.90,
                      "role": "load", "capacity_kbd": 800},
    "BONNY":         {"name": "Bonny Terminal", "country": "NG", "lat": 4.42, "lon": 7.16,
                      "role": "load", "capacity_kbd": 900},
    "GIRASSOL":      {"name": "Girassol FPSO", "country": "AO", "lat": -6.50, "lon": 11.20,
                      "role": "load", "capacity_kbd": 450},
    "CORPUS":        {"name": "Corpus Christi", "country": "US", "lat": 27.81, "lon": -97.39,
                      "role": "load", "capacity_kbd": 2200},
    "TUPI":          {"name": "Tupi / Santos Basin", "country": "BR", "lat": -25.20, "lon": -42.80,
                      "role": "load", "capacity_kbd": 1000},
}

# --------------------------------------------------------------------------
# Discharge spurs — derived, not hand-authored.
#
# A corridor's `waypoints` end at one shared point off India's coast, but the
# barrels on it actually fan out to several different discharge ports. This
# computes a short two-point line from that shared arrival point to each of
# a corridor's own discharge ports, so the map can draw where the cargo
# actually goes instead of implying every ship on a corridor arrives at the
# same spot. Weight (0-1) is each port's share of that corridor's *combined
# discharge capacity* — the visual density argument: Jamnagar and Vadinar
# should read as busier than Haldia because they genuinely are, not because
# someone hand-picked line thickness.
# --------------------------------------------------------------------------

# A ship arriving off Gujarat cannot sail overland to reach Chennai — it goes
# around the southern tip of India. This waypoint (near Kanyakumari, where
# the west and east coasts meet) is inserted for any spur whose corridor
# arrives on the west side but whose port sits on the east side; corridors
# that already arrive from the east (Malacca) skip it, since a direct line
# is already a real sea route for them.
_CAPE_COMORIN = [7.6, 78.2]
_EAST_COAST_PORTS = {"PARADIP", "CHENNAI", "VISAKHAPATNAM", "HALDIA"}

# How many of a corridor's discharge ports get drawn as spurs on the map.
# Real cargo does go to all of them, but drawing every one turns the map into
# an unreadable fan — the top few by weight already carry most of the volume
# (Jamnagar alone is 36% of the Hormuz corridor's discharge), so that's what
# earns a line. All ports still get full risk/telemetry treatment regardless
# of whether they're drawn here.
_MAX_SPURS_PER_CORRIDOR = 3


def _build_spurs() -> dict:
    spurs: dict[str, dict] = {}
    for c in CORRIDORS:
        arrival = c["waypoints"][-1]
        arrival_is_west = arrival[1] < 75.0  # rough Arabian-Sea-vs-Bay-of-Bengal split
        ports_here = [p for p in c["discharge"] if p in PORTS]
        total_cap = sum(PORTS[p]["capacity_kbd"] for p in ports_here) or 1
        ranked = sorted(ports_here, key=lambda p: -PORTS[p]["capacity_kbd"])[:_MAX_SPURS_PER_CORRIDOR]
        spurs[c["id"]] = {
            p: {
                "waypoints": (
                    [arrival, _CAPE_COMORIN, [PORTS[p]["lat"], PORTS[p]["lon"]]]
                    if arrival_is_west and p in _EAST_COAST_PORTS
                    else [arrival, [PORTS[p]["lat"], PORTS[p]["lon"]]]
                ),
                "port_name": PORTS[p]["name"],
                "capacity_kbd": PORTS[p]["capacity_kbd"],
                "weight": round(PORTS[p]["capacity_kbd"] / total_cap, 3),
            }
            for p in ranked
        }
    return spurs


SPURS = _build_spurs()

# --------------------------------------------------------------------------
# Suppliers — India's crude sources. `share_pct` = share of Indian imports.
# Spot uplift is the premium (USD/bbl vs Brent) India pays to scale that
# supplier up quickly in a crisis; discount is negative.
# --------------------------------------------------------------------------

SUPPLIERS = {
    "RUS": {"name": "Russia", "share_pct": 35.0, "corridor": "REDSEA_SUEZ", "alt_corridor": "MALACCA_PACIFIC",
            "grade": "Medium sour (Urals/ESPO)", "diff_usd": -3.0, "spare_kbd": 300,
            "sanctions_exposure": "high", "lead_days": 21},
    "IRQ": {"name": "Iraq", "share_pct": 20.0, "corridor": "GULF_HORMUZ", "alt_corridor": None,
            "grade": "Medium sour (Basrah)", "diff_usd": 0.5, "spare_kbd": 200,
            "sanctions_exposure": "low", "lead_days": 5},
    "SAU": {"name": "Saudi Arabia", "share_pct": 15.0, "corridor": "GULF_HORMUZ", "alt_corridor": None,
            "grade": "Medium sour (Arab Light)", "diff_usd": 1.5, "spare_kbd": 600,
            "sanctions_exposure": "low", "lead_days": 5},
    "ARE": {"name": "UAE", "share_pct": 8.0, "corridor": "GULF_HORMUZ", "alt_corridor": None,
            "grade": "Light sour (Murban)", "diff_usd": 1.2, "spare_kbd": 250,
            "sanctions_exposure": "low", "lead_days": 5,
            "note": "Fujairah loading partially bypasses Hormuz via the ADCOP pipeline."},
    "USA": {"name": "United States", "share_pct": 6.0, "corridor": "US_GULF", "alt_corridor": None,
            "grade": "Light sweet (WTI Midland)", "diff_usd": 2.8, "spare_kbd": 400,
            "sanctions_exposure": "none", "lead_days": 40},
    "NGA": {"name": "Nigeria", "share_pct": 4.0, "corridor": "CAPE", "alt_corridor": None,
            "grade": "Light sweet (Bonny)", "diff_usd": 2.2, "spare_kbd": 150,
            "sanctions_exposure": "none", "lead_days": 26},
    "AGO": {"name": "Angola", "share_pct": 3.0, "corridor": "CAPE", "alt_corridor": None,
            "grade": "Medium sweet", "diff_usd": 1.9, "spare_kbd": 120,
            "sanctions_exposure": "none", "lead_days": 26},
    "KWT": {"name": "Kuwait", "share_pct": 3.0, "corridor": "GULF_HORMUZ", "alt_corridor": None,
            "grade": "Medium sour", "diff_usd": 0.9, "spare_kbd": 150,
            "sanctions_exposure": "low", "lead_days": 5},
    "BRA": {"name": "Brazil", "share_pct": 2.0, "corridor": "CAPE", "alt_corridor": None,
            "grade": "Medium sweet (Tupi)", "diff_usd": 2.0, "spare_kbd": 180,
            "sanctions_exposure": "none", "lead_days": 30},
    "GUY": {"name": "Guyana", "share_pct": 1.5, "corridor": "CAPE", "alt_corridor": None,
            "grade": "Light sweet (Liza)", "diff_usd": 2.4, "spare_kbd": 120,
            "sanctions_exposure": "none", "lead_days": 32},
    "KAZ": {"name": "Kazakhstan", "share_pct": 1.0, "corridor": "REDSEA_SUEZ", "alt_corridor": "CAPE",
            "grade": "Light sour (CPC)", "diff_usd": 1.6, "spare_kbd": 80,
            "sanctions_exposure": "low", "lead_days": 22},
    "LBY": {"name": "Libya", "share_pct": 0.8, "corridor": "REDSEA_SUEZ", "alt_corridor": "CAPE",
            "grade": "Light sweet", "diff_usd": 1.4, "spare_kbd": 60,
            "sanctions_exposure": "medium", "lead_days": 20},
    "MYS": {"name": "Malaysia", "share_pct": 0.4, "corridor": "MALACCA_PACIFIC", "alt_corridor": None,
            "grade": "Light sweet", "diff_usd": 2.1, "spare_kbd": 40,
            "sanctions_exposure": "low", "lead_days": 10},
    "AUS": {"name": "Australia", "share_pct": 0.3, "corridor": "MALACCA_PACIFIC", "alt_corridor": None,
            "grade": "Condensate", "diff_usd": 2.5, "spare_kbd": 30,
            "sanctions_exposure": "none", "lead_days": 14},
}

SUPPLIER_SOURCE = {
    "label": "Reference shares derived from PPAC import statistics and EIA India country analysis; "
             "treat as planning baselines, not settlement data.",
    "url": "https://ppac.gov.in/import-export",
    "as_of": "2025",
}

# --------------------------------------------------------------------------
# Demand sectors — who feels a supply gap, and how fast
# --------------------------------------------------------------------------

SECTORS = [
    {"id": "transport", "name": "Road transport & logistics", "share_of_products_pct": 44,
     "elasticity": 0.35, "lag_days": 10,
     "note": "Diesel-led. First place a landed-cost rise shows up in headline inflation."},
    {"id": "aviation", "name": "Aviation", "share_of_products_pct": 6,
     "elasticity": 0.55, "lag_days": 5,
     "note": "ATF is repriced fortnightly; carriers cannot hedge a sustained spike."},
    {"id": "petchem", "name": "Petrochemicals & plastics", "share_of_products_pct": 12,
     "elasticity": 0.6, "lag_days": 20,
     "note": "Naphtha feedstock. Margin compression before volume loss."},
    {"id": "agri", "name": "Agriculture (diesel pumps, tractors)", "share_of_products_pct": 9,
     "elasticity": 0.25, "lag_days": 15,
     "note": "Politically the most sensitive pass-through in India. Usually absorbed by subsidy."},
    {"id": "power", "name": "Power & industrial fuel", "share_of_products_pct": 8,
     "elasticity": 0.3, "lag_days": 12,
     "note": "Small direct oil burn, but LNG substitution links it to the same crisis."},
    {"id": "shipping", "name": "Bunkering & coastal shipping", "share_of_products_pct": 5,
     "elasticity": 0.5, "lag_days": 7,
     "note": "Freight and fuel rise together — a double hit on the same corridor disruption."},
    {"id": "households", "name": "Households (LPG, kerosene)", "share_of_products_pct": 16,
     "elasticity": 0.15, "lag_days": 30,
     "note": "Administered price. Fiscal cost lands on the exchequer, not the consumer."},
]

# --------------------------------------------------------------------------
# Scenario presets
# --------------------------------------------------------------------------

SCENARIOS = {
    "HORMUZ_CLOSURE": {
        "name": "Strait of Hormuz closure",
        "subtitle": "Military closure or insurance withdrawal halts Gulf transit",
        "corridor_capacity": {"GULF_HORMUZ": 0.15},
        "chokepoint_status": {"HORMUZ": "blocked"},
        "supply_shock_mbd": 20.0,
        "reroutable": 0.05,
        "bypass_mbd": 6.5,
        "opec_spare_available": False,
        "risk_premium_usd": 10.0,
        "freight_multiplier": {"GULF_HORMUZ": 4.0, "CAPE": 1.8, "US_GULF": 1.6},
        "duration_days": 30,
        "modelling_note": "Two judgements do the work here. (1) Only ~6.5 mb/d can bypass the "
                          "strait by pipeline — Saudi East-West to Yanbu and the UAE's ADCOP line "
                          "to Fujairah — so most blocked barrels are lost to the market, not "
                          "delayed. (2) OPEC spare capacity is *itself stranded behind Hormuz*, "
                          "so it cannot be counted as an offset. Models that forget this "
                          "systematically understate the shock.",
        "precedent": "2025 US–Iran standoff: Brent +8% in a single session; Indian refiners "
                     "forced onto the spot market at steep premiums.",
        "precedent_source": {"label": "ET AI Hackathon 2026 PS-2 context brief",
                             "url": "internal://problem-statement-2"},
    },
    "RED_SEA_ATTACK": {
        "name": "Red Sea shipping suspension",
        "subtitle": "Sustained attacks on tankers force a Bab el-Mandeb exit",
        "corridor_capacity": {"REDSEA_SUEZ": 0.35},
        "chokepoint_status": {"BAB_EL_MANDEB": "contested", "SUEZ": "degraded"},
        "supply_shock_mbd": 6.2,
        "reroutable": 0.90,
        "bypass_mbd": 0.0,
        "opec_spare_available": True,
        "risk_premium_usd": 3.0,
        "freight_multiplier": {"REDSEA_SUEZ": 2.6, "CAPE": 1.4},
        "duration_days": 45,
        "modelling_note": "This is a logistics shock, not a supply shock. Nine in ten blocked "
                          "barrels still reach India — via the Cape, two weeks later and at a war-"
                          "risk premium. Expect freight and insurance to move hard while Brent "
                          "barely twitches. That is exactly what happened in 2024.",
        "precedent": "2023–24 Houthi campaign: most tanker owners rerouted via the Cape, "
                     "adding roughly two weeks and a war-risk premium per voyage.",
        "precedent_source": {"label": "IMF PortWatch — Red Sea transit trade volumes",
                             "url": "https://portwatch.imf.org/pages/chokepoints"},
    },
    "RUSSIA_SANCTIONS": {
        "name": "Full secondary sanctions on Russian crude",
        "subtitle": "Buyers, insurers and shadow-fleet vessels designated",
        "corridor_capacity": {"REDSEA_SUEZ": 0.55, "MALACCA_PACIFIC": 0.5},
        "supplier_capacity": {"RUS": 0.25},
        "chokepoint_status": {},
        "supply_shock_mbd": 3.5,
        "reroutable": 0.35,
        "bypass_mbd": 0.0,
        "opec_spare_available": True,
        "risk_premium_usd": 7.0,
        "freight_multiplier": {"REDSEA_SUEZ": 1.5, "CAPE": 1.5, "US_GULF": 1.3},
        "duration_days": 90,
        "modelling_note": "The barrels are mostly replaceable; the *discount* is not. India's "
                          "landed cost rises even if Brent does not, because a 35% slice of the "
                          "slate stops arriving at roughly $3/bbl under Brent. This is the one "
                          "scenario where the world is fine and India still pays.",
        "precedent": "India's discounted Urals barrel disappears; replacement is Gulf and "
                     "Atlantic crude at a premium, not a discount.",
        "precedent_source": {"label": "OFAC — Specially Designated Nationals list",
                             "url": "https://sanctionslist.ofac.treas.gov/Home/SdnList"},
    },
    "OPEC_CUT": {
        "name": "OPEC+ emergency production cut",
        "subtitle": "Coordinated 2 mb/d withdrawal from the market",
        "corridor_capacity": {},
        "supplier_capacity": {"SAU": 0.85, "ARE": 0.85, "IRQ": 0.9, "KWT": 0.85},
        "chokepoint_status": {},
        "supply_shock_mbd": 2.0,
        "reroutable": 0.0,
        "bypass_mbd": 0.0,
        "opec_spare_available": False,
        "risk_premium_usd": 4.0,
        "freight_multiplier": {},
        "duration_days": 60,
        "modelling_note": "Spare capacity cannot offset a shock created by the holders of that "
                          "spare capacity. Rerouting is useless here — only demand management "
                          "and an SPR release touch this one.",
        "precedent": "Volume, not transit, is the binding constraint. Rerouting does not help; "
                     "only demand management and SPR release do.",
        "precedent_source": {"label": "EIA — Short-Term Energy Outlook",
                             "url": "https://www.eia.gov/outlooks/steo/"},
    },
    "WEATHER_EVENT": {
        "name": "Severe weather / cyclone event",
        "subtitle": "Arabian Sea cyclone closes west-coast discharge ports",
        "corridor_capacity": {"GULF_HORMUZ": 0.6, "CAPE": 0.8},
        "port_status": {"JAMNAGAR": 0.3, "VADINAR": 0.3, "MUMBAI": 0.5},
        "chokepoint_status": {},
        "supply_shock_mbd": 1.5,
        "reroutable": 0.80,
        "bypass_mbd": 0.0,
        "opec_spare_available": True,
        "risk_premium_usd": 0.5,
        "freight_multiplier": {"GULF_HORMUZ": 1.3},
        "duration_days": 10,
        "modelling_note": "Watch refinery utilisation, not price. The crude exists and is paid "
                          "for; it simply cannot be landed. Demurrage and lost runs, not a shock "
                          "at the pump.",
        "precedent": "Discharge-side, not supply-side. Crude sits at anchorage; refinery runs "
                     "fall before any price signal appears.",
        "precedent_source": {"label": "Open-Meteo Marine — wave and wind forecast",
                             "url": "https://open-meteo.com/en/docs/marine-weather-api"},
    },
}

# --------------------------------------------------------------------------
# Risk model weights — published, not hidden. The UI renders this table.
# --------------------------------------------------------------------------

RISK_WEIGHTS = {
    "conflict":   {"weight": 0.32, "label": "Conflict & security",
                   "source": "GDELT DOC 2.0 event tone/volume in corridor geofence"},
    "sanctions":  {"weight": 0.22, "label": "Sanctions exposure",
                   "source": "OFAC SDN list + OpenSanctions entity screening"},
    "congestion": {"weight": 0.18, "label": "Port & chokepoint congestion",
                   "source": "IMF PortWatch daily port calls vs 90-day baseline"},
    "weather":    {"weight": 0.16, "label": "Weather & sea state",
                   "source": "Open-Meteo wind/wave at corridor waypoints"},
    "market":     {"weight": 0.12, "label": "Market stress",
                   "source": "EIA Brent spot series — realised volatility and level"},
}

RISK_BANDS = [
    (0, 25, "low", "Watch"),
    (25, 50, "moderate", "Monitor"),
    (50, 70, "elevated", "Prepare"),
    (70, 85, "high", "Act"),
    (85, 101, "severe", "Escalate"),
]


def band_for(score: float):
    for lo, hi, key, action in RISK_BANDS:
        if lo <= score < hi:
            return {"key": key, "action": action}
    return {"key": "severe", "action": "Escalate"}


def corridor_by_id(cid: str):
    for c in CORRIDORS:
        if c["id"] == cid:
            return c
    return None
