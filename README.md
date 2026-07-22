# SUPATH — Strategic Energy Transit Unit

An AI decision-support system for India's crude oil supply chain, built for the
ET AI Hackathon 2026 (Problem Statement 2 — AI-Driven Energy Supply Chain
Resilience for Import-Dependent Economies).

SUPATH does not show a dashboard. It answers four questions a government
official actually asks, in order:

1. **Situation** — what is happening right now, and why did the price move
2. **Risk Intelligence** — why is each corridor's risk score what it is
3. **Scenario Simulator** — if X happens, what does it cost India, day by day
4. **Decision Brief** — what should be done about it, ranked, costed, and cited

Every number on screen carries a provenance chip — *live*, *cached*,
*reference*, *modelled*, or *simulated* — and links to the source it came
from. Nothing is presented as an observation that is actually an estimate.

---

## Live demo

**➡ [https://YOUR-APP-NAME.onrender.com](https://YOUR-APP-NAME.onrender.com)** *(update this link once deployed — see below)*

No installation needed — click it. The map runs on a deterministic corridor
simulator (clearly labelled `SIM` throughout), prices come live from Yahoo
Finance, and everything else runs exactly as described below. **First load
after a period of inactivity can take 20–40 seconds** — this app runs on
Render's free tier, which sleeps a service after 15 minutes with no traffic
and wakes it back up on the next request. That's expected, not broken.

---

## Deploying your own copy (Render, free tier)

This repo includes `render.yaml`, so Render can configure almost everything
automatically. You don't need to install Python, Docker, or anything else on
your own machine to do this.

1. **Push this repo to your own GitHub account** if you haven't already (see
   *Repository structure* below for what belongs where).
2. Go to **[render.com](https://render.com)** and sign up — the free plan
   needs no credit card.
3. From the Render dashboard, click **New → Blueprint**.
4. Connect your GitHub account if prompted, then select this repository.
   Render reads `render.yaml` automatically and pre-fills the service:
   name `supath`, Python environment, the correct build and start commands.
5. Render will list a handful of **optional** environment variables
   (`EIA_API_KEY`, `AISSTREAM_API_KEY`, etc.) with blank values — you can
   leave every single one empty and the app will run correctly, using Yahoo
   Finance for prices and the simulator for the map. Only fill one in if you
   specifically want that source live (see `.env.example` for what each one
   unlocks and where to get a free key).
6. Click **Apply** / **Create Web Service**. Render will build (installs
   dependencies, then patches and installs abcEconomics — this step takes a
   few minutes the first time) and deploy.
7. When the build finishes, Render shows your live URL — something like
   `https://supath-xxxx.onrender.com`. Open it. If the first load hangs for
   20-40 seconds, that's the free-tier service waking up — refresh once it
   responds and it'll be fast from then on until it sleeps again.
8. Paste that URL into the *Live demo* link at the top of this README (and
   into your competition submission form).

**Keeping it awake for judging day (optional):** free-tier Render services
sleep after 15 minutes of no traffic. If you want to avoid the wake-up delay
during a specific judging window, a free service like
[UptimeRobot](https://uptimerobot.com) can ping your `/api/health` endpoint
every 10 minutes to keep it warm — not required, just a nice-to-have.

**If the build fails:** check the build logs in the Render dashboard first —
the abcEconomics install step is the most likely place for something
environment-specific to go wrong. The scenario simulator has a documented
analytic fallback (see `backend/engine/scenario.py`) that runs automatically
if abcEconomics genuinely can't install, so a failed abcEconomics build
doesn't have to block the whole deploy — but it's worth checking the logs
either way.

---

## Repository structure

```
supath/
├── render.yaml              # Render deployment config — read this first
├── requirements.txt
├── .env.example              # documents every optional key; never put real keys here
├── .gitignore                 # excludes .env, __pycache__, etc.
├── scripts/
│   └── install_abce.py         # patches and installs abcEconomics (see below)
├── backend/
│   ├── main.py                  # FastAPI app, every /api/* endpoint
│   ├── config.py                  # Settings (reads keys from environment only)
│   ├── reference.py                 # India's baseline data: corridors, ports, suppliers
│   ├── flags.py                       # MMSI → flag-state lookup
│   ├── sources/                        # one file per external data source
│   │   ├── yahoo.py                      # primary price source (no key)
│   │   ├── eia.py                          # fallback price source (needs a key)
│   │   ├── news.py, gdeltcloud.py            # GDELT DOC 2.0 + optional GDELT Cloud
│   │   ├── ais.py, vesselapi.py                # corridor simulator + optional live AIS
│   │   ├── portwatch.py, weather.py, sanctions.py
│   └── engine/                           # risk scoring, scenario simulation, PDF report
├── frontend/
│   ├── index.html
│   ├── css/app.css
│   └── js/                              # one file per tab, plus shared api.js/ui.js
├── run.sh, SUPATH-Mac-Linux.command, SUPATH-Windows.bat   # local-run launchers (optional —
│                                                          the live Render deployment is
│                                                          the primary way to use this)
```

Everything under `backend/` and `frontend/` gets committed as-is. The only
things that must **never** be committed are real API key values — `.env` is
git-ignored specifically for this; `.env.example` (which has empty values) is
the only one that belongs in the repo.

---

## Running it locally (optional — most people won't need this)

The Render deployment above is the primary way to use SUPATH. Run it locally
only if you want to develop on it, or want live behavior your Render env
vars aren't configured for during local testing.

**Mac or Linux:** double-click `SUPATH-Mac-Linux.command` (first time, you may need to right-click → Open, since it's from an unidentified developer).
**Windows:** double-click `SUPATH-Windows.bat`.

Either one installs what's missing, starts the server, and opens Chrome to
`http://localhost:8000` automatically. Leave the black terminal window open —
closing it stops the site. **Python 3.10+ must already be installed** (from
[python.org](https://www.python.org/downloads/)) — that's the one thing that
can't be skipped, because the risk engine and the abcEconomics scenario
simulator are real Python running on your machine, not a static page. Opening
`frontend/index.html` directly in Chrome will not work — the browser blocks
the API calls that drive every tab.

## Running it — the terminal way

```bash
./run.sh
```

This installs dependencies (including a one-off patch for a broken
`abcEconomics` release — see below), then serves the whole application,
frontend and API together, at **http://localhost:8000**.

No API keys are required to run it. Every external source has a documented
fallback: a corridor tanker simulator, a reference Brent price series, a
neutral-prior news signal, and so on. The UI always says, per number, which
mode it is in — this is a deliberate feature, not a limitation to hide.

To move a source from reference/simulated to live, copy `.env.example` to
`.env` and add the relevant key (see that file for what each one unlocks),
then run `./run.sh` again.

### Manually, if you'd rather not use the script

```bash
pip install -r requirements.txt --break-system-packages
python3 scripts/install_abce.py
uvicorn backend.main:app --reload --port 8000
```

---

## Architecture

```
frontend/            static HTML/CSS/JS served directly by FastAPI
  index.html          shell: sidebar, topbar, 4 views, advisor rail, modal
  css/app.css          the whole design system
  js/
    api.js             fetch wrapper + a tiny pub/sub STORE
    ui.js               shared render primitives (charts, chips, sparklines)
    globe.js            the corridor globe (d3-geo, canvas)
    map.js               the Leaflet operating picture (AIS, ports, chokepoints)
    situation.js, riskview.js, scenario.js, brief.js   one file per tab
    app.js                router, boot sequence, refresh loop

backend/
  main.py              FastAPI app — every endpoint the frontend calls
  config.py             provenance envelopes (`sourced()`), settings, TTL cache
  reference.py           India's baseline numbers: corridors, ports, suppliers,
                          chokepoints, sectors, scenario definitions — the one
                          file that encodes "what does India's oil map look like"
  sources/              one module per external API, each with a real client
                          and a documented, honest fallback
    ais.py               aisstream.io client + deterministic corridor simulator
    prices.py             EIA Brent/WTI spot prices
    news.py                GDELT DOC 2.0 corridor and India news signal
    portwatch.py           IMF PortWatch port congestion
    weather.py              Open-Meteo sea state at each chokepoint
    sanctions.py             OFAC SDN + OpenSanctions screening
  engine/
    risk.py               the 5-term weighted corridor risk score + national
                            barrel-weighted aggregate + price attribution
    scenario.py             the abcEconomics agent-based simulator
    recommend.py             turns risk + scenario state into ranked, costed,
                              cited actions
    advisor.py                the decision layer: posture, reasoning chain,
                                tripwires, citations
    report.py                   PDF generation (reportlab)
```

**One world at a time.** A running scenario is held in memory (`ACTIVE` in
`main.py`) and every endpoint reads it — the map, the risk scores, the
advisor, and the PDF all describe the same world simultaneously. There is no
mode where the simulator changes one panel and leaves the others describing
the old picture.

---

## The abcEconomics agent model

`backend/engine/scenario.py` builds four agent types on top of
[abcEconomics](https://pypi.org/project/abcEconomics/) — a spatial,
double-entry-accounting agent-based economics framework:

- **Exporter** (one per supplier) — reroutes cargo when its usual corridor is
  throttled, subject to how much of its supply is actually reroutable
- **Shipper** (one per corridor) — applies the scenario's freight multiplier
  and splits cargo across refineries by capacity
- **Refiner** (one per Indian refinery) — landed crude is gated by port
  capacity before it can be run
- **StrategicReserve** — draws down to cover up to 60% of the shortfall,
  capped at 900 kb/d/day, same as India's actual SPR release rate

Price is computed from net world supply loss (after reroutable share,
pipeline bypass capacity, OPEC spare capacity, and a tapering IEA collective
release), converted to a Brent move via a saturating exponential curve, then
converted to an *India-specific landed cost* — which is not just Brent:
losing a discounted grade (e.g. Urals) raises India's cost even when Brent
itself is flat, because the model tracks which barrels actually arrive, not
just the benchmark price.

Every coefficient in that chain (pass-through rate, CPI weight, demand
response, freight assumptions, OPEC spare capacity) is listed in
`CALIBRATION` and shown to the user under **Assumptions** in the Scenario tab
— nothing is a hidden constant.

### The abcEconomics install problem

The published `abcEconomics` 0.9.7b2 sdist has an invalid
`install_requires` entry (`numpy >= 1.10.2p` — not a valid version
specifier), which makes `pip install abcEconomics` fail on any modern pip
before it even reaches the library's code. `scripts/install_abce.py`
downloads the sdist, rewrites that one line, and installs from the patched
source. If abcEconomics still can't be imported at runtime for any reason,
`scenario.py` falls back to an analytic model using the same calibration
constants — the simulator degrades gracefully rather than breaking the tab.

---

## The VesselAPI live-window layer

`backend/sources/vesselapi.py` adds a second, deliberately partial live-AIS
source, used only when aisstream is not connected. It exists because
VesselAPI's free tier — 150 requests/month, and a 4-degree cap on any single
bounding-box query — cannot cover five ocean corridors continuously. Rather
than spread that budget thin and unreliably, it watches two small, high-value
windows (the Strait of Hormuz approach and the Gulf of Kutch approach into
Jamnagar/Vadinar), refreshed twice a day, and lets the corridor simulator
carry everything else — exactly as it already does when no live key is
configured at all. A local monthly counter (`MONTHLY_CEILING`, set below
VesselAPI's own cap) refuses to call upstream past a safety margin, so a bug
can't spend the month's quota before judging day.

Every contact from this layer is drawn as an **unclassified** dot, never the
tanker icon — the bounding-box endpoint returns any AIS-transmitting vessel in
the box, not just tankers, and confirming a hull's type would cost a second
request per ship the budget doesn't allow. The map also draws the two windows
as dashed boxes, so it's visible exactly where the real data reaches and
where the simulator is still doing the work.

## Data sources

| Source | Used for | Fallback when unreachable |
|---|---|---|
| aisstream.io | Live tanker AIS positions, all corridors | Deterministic corridor simulator (named vessels, real speeds, real routes) |
| VesselAPI.com | Live, unclassified AIS contacts in two narrow windows (Hormuz approach, Gulf of Kutch approach) — only used when aisstream is not connected | Corridor simulator, same as above — this source only ever fills a small patch of the map, never replaces the simulator entirely |
| Yahoo Finance | Brent/WTI daily prices — primary source, no key needed | EIA Open Data, then a documented static reference series |
| EIA Open Data | Brent/WTI daily prices — used only if Yahoo Finance is unreachable | Documented reference series through 2026-07-10 |
| GDELT DOC 2.0 | Corridor conflict/escalation signal | Neutral prior (0.35), clearly marked |
| GDELT Cloud | Optional richer conflict signal (classified Events, Goldstein-scored) — enriches, never replaces, DOC 2.0 | Falls back to DOC 2.0 alone |
| IMF PortWatch | Port call counts vs. 90-day baseline | Documented reference port state |
| Open-Meteo | Sea state at each chokepoint | Neutral prior (0.25), clearly marked |
| OFAC SDN + OpenSanctions | Counterparty and vessel screening | Documented supplier sanctions-exposure priors |

Note on the two price sources: Yahoo Finance's tickers (BZ=F, CL=F) are
**futures** prices — the same benchmark most financial tickers and news
sites quote. EIA's series are the physical **spot** price — a different,
equally legitimate benchmark that can genuinely differ by a few dollars.
That's why Yahoo goes first: it's the number a reader expects to see, and it
needs no registration at all. It's also unofficial (Yahoo doesn't publish or
support this endpoint), which is exactly why EIA — official, but requiring a
free key — sits behind it as a fallback, not a replacement.

Reference figures for India (import volume, dependency ratio, refining
capacity, strategic reserve cover) come from PPAC, the EIA India country
brief, and the hackathon's own problem statement, cited in
`backend/reference.py`.

---

## What each tab is actually for

- **Situation** — the globe and the operating-picture map, Brent's move
  explained against concurrent corridor signals (not just quoted), Indian
  port health, and sea state at every chokepoint.
- **Risk Intelligence** — every corridor's score broken into its five
  weighted terms (conflict, sanctions, congestion, weather, market), each
  traceable to a source and an equation; a live GDELT feed where any headline
  can be clicked to run "what does this do to India" through the same model
  as the simulator; ad-hoc sanctions screening.
- **Scenario Simulator** — five preset disruptions (Hormuz closure, Red Sea
  attack, Russia sanctions escalation, OPEC cut, a weather event) with
  adjustable severity and horizon, a day-by-day playback of Brent, the import
  gap, strategic reserve cover, and refinery utilisation, and the full causal
  chain in plain language.
- **Decision Brief** — the advisor's call and posture, ranked recommendations
  with quantified coverage/cost/lead-time and pre-screened counterparties,
  tripwires that say what would change the call, and a downloadable PDF.

---

## Design

Light, low-contrast, government-facing: white and pale green, serif
(Newsreader) for the narrative writing, sans (Inter) for the interface,
monospace (IBM Plex Mono) for every number. Risk bands are the only place
saturated colour appears. No neon, no unnecessary motion — the one piece of
animation, the corridor globe, spins slowly and stops entirely for anyone
whose OS asks for reduced motion.
