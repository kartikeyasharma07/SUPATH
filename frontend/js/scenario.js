/* SUPATH — Scenario Simulator: cause and effect, one day at a time.

   The agent model runs in the backend (abcEconomics). This file is a control
   surface and a playback head. It shows the cascade as a chain, because the
   chain is the argument: transit → supply → discharge → reroute → reserve →
   price → pump → economy. Any link can be disputed. That is the point.
*/

const ScenarioView = {
  picked: 'HORMUZ_CLOSURE',
  severity: 1.0,
  days: 30,
  result: null,
  day: 0,
  playing: false,
  timer: null,

  render() {
    const el = document.getElementById('view-scenario');
    const ref = STORE.reference;
    if (!ref) { el.innerHTML = UI.skeleton(400); return; }

    const scenarios = Object.entries(ref.scenarios);

    el.innerHTML = `
      <div class="stack">
        <section class="panel">
          <div class="panel-head">
            <h3>Simulate a disruption</h3>
          </div>
          <div class="panel-body">
            <p class="small faint" style="margin-bottom:14px">Agent-based model (abcEconomics) — exporters, shippers, refiners and the strategic reserve, each acting on its own rules</p>
            <div class="grid g-3" id="presets">
              ${scenarios.map(([id, s]) => `
                <button class="preset ${id === this.picked ? 'active' : ''}" data-id="${id}">
                  <div class="nm" style="font-size:14px">${UI.esc(s.name)}</div>
                  <div class="sb" style="font-size:12.5px">${UI.esc(s.subtitle)}</div>
                </button>`).join('')}
            </div>

            <div class="grid g-3" style="margin-top:16px;align-items:end">
              <div>
                <div class="eyebrow" style="margin-bottom:8px;font-size:11px">Severity <span class="num" id="sev-val">100%</span></div>
                <input type="range" id="sev" min="5" max="100" step="5" value="${this.severity * 100}" />
                <div class="tiny faint" style="margin-top:5px;font-size:12px">How much of the corridor is lost. 100% is the full closure case.</div>
              </div>
              <div>
                <div class="eyebrow" style="margin-bottom:8px;font-size:11px">Horizon <span class="num" id="day-val">30 days</span></div>
                <input type="range" id="days" min="10" max="90" step="5" value="${this.days}" />
                <div class="tiny faint" style="margin-top:5px;font-size:12px">Strategic reserve cover is 9.5 days. Anything past that is policy, not stock.</div>
              </div>
              <div class="row" style="justify-content:flex-end;gap:8px">
                <button class="btn" id="clear-sc">Clear</button>
                <button class="btn primary" id="run-sc">Run scenario</button>
              </div>
            </div>
          </div>
        </section>

        <div id="sc-result">${this.result ? '' : `
          <section class="panel"><div class="panel-body">
            <p class="small muted" style="line-height:1.6">
              Nothing is running. The map, the corridor scores and the advisor all describe the
              real world right now.</p>
          </div></section>`}</div>
      </div>`;

    el.querySelectorAll('.preset').forEach(b => b.addEventListener('click', () => {
      this.picked = b.dataset.id;
      el.querySelectorAll('.preset').forEach(x => x.classList.toggle('active', x === b));
    }));

    const sev = document.getElementById('sev'), dys = document.getElementById('days');
    sev.addEventListener('input', () => {
      this.severity = sev.value / 100;
      document.getElementById('sev-val').textContent = sev.value + '%';
    });
    dys.addEventListener('input', () => {
      this.days = +dys.value;
      document.getElementById('day-val').textContent = dys.value + ' days';
    });

    document.getElementById('run-sc').addEventListener('click', () => this.run());
    document.getElementById('clear-sc').addEventListener('click', () => App.clearScenario());

    if (this.result) this.renderResult();
  },

  async run() {
    const btn = document.getElementById('run-sc');
    btn.disabled = true; btn.textContent = 'Running agent model…';
    try {
      const r = await API.runScenario({ scenario: this.picked, severity: this.severity, days: this.days });
      this.result = r; this.day = 0; this.playing = false;
      STORE.set('scenario', r);
      STORE.scenarioId = r.scenario;
      this.renderResult();
      await App.refresh();          // map, risk and advisor all move with it
      App.showScenarioBanner(r);
    } catch (e) {
      UI.modal('Scenario', '<p class="small muted">The model failed to run. See the server log.</p>');
    } finally {
      btn.disabled = false; btn.textContent = 'Run scenario';
    }
  },

  renderResult() {
    const r = this.result;
    if (!r) return;
    const h = r.headline;
    const el = document.getElementById('sc-result');
    if (!el) return;

    el.innerHTML = `
      <div class="stack">
        <section class="panel">
          <div class="panel-head">
            <h3>${UI.esc(r.name)} · severity ${(r.severity * 100).toFixed(0)}%</h3>
            <span class="spacer"></span>
            <span class="chip green">${UI.esc(r.engine)}</span>
            <span class="chip">${r.agents.exporters + r.agents.shippers + r.agents.refiners + r.agents.reserve} agents</span>
          </div>
          <div class="panel-body">
            <div class="stat-row">
              <div class="stat-card" style="--accent:var(--r-high)">
                <div class="l">Peak Brent Price</div>
                <div class="v">$${h.peak_brent.toFixed(0)}</div>
                <div class="s">${UI.pct(h.peak_brent_chg_pct)} · day ${h.peak_brent_day}</div>
              </div>
              <div class="stat-card" style="--accent:var(--r-elev)">
                <div class="l">Supply Gap</div>
                <div class="v">${UI.num(h.peak_gap_kbd)}</div>
                <div class="s">kb/d unmet · day ${h.peak_gap_day}</div>
              </div>
              <div class="stat-card" style="--accent:var(--r-high)">
                <div class="l">Retail Fuel Price Hike</div>
                <div class="v">${UI.pct(h.final_pump_pct)}</div>
                <div class="s">at horizon</div>
              </div>
              <div class="stat-card" style="--accent:var(--r-elev)">
                <div class="l">Consumer Price Index</div>
                <div class="v">${h.final_cpi_pp >= 0 ? '+' : ''}${h.final_cpi_pp}<span style="font-size:14px"> pp</span></div>
                <div class="s">inflation add</div>
              </div>
              <div class="stat-card" style="--accent:var(--moss)">
                <div class="l">GDP drag</div>
                <div class="v">${h.final_gdp_drag_pct.toFixed(2)}%</div>
                <div class="s">at horizon</div>
              </div>
              <div class="stat-card" style="--accent:var(--teal)">
                <div class="l">Refinery Run Rate</div>
                <div class="v">${h.min_refinery_util.toFixed(0)}%</div>
                <div class="s">worst day</div>
              </div>
            </div>
            <div class="row" style="justify-content:space-between;margin-top:10px">
              <span class="tiny faint">Reserve Cover Left: ${h.spr_exhausted_day ? `exhausted day ${h.spr_exhausted_day}` : this.lastDay().spr_days_left.toFixed(1) + ' days left at horizon'}</span>
            </div>
          </div>
        </section>

        <!-- playback -->
        <section class="panel">
          <div class="panel-head">
            <h3 id="day-head">Day ${this.day + 1} of ${r.days}</h3>
            <span class="spacer"></span>
            <button class="btn sm" id="play">${this.playing ? 'Pause' : 'Play'}</button>
          </div>
          <div class="panel-body">
            <div class="timeline">
              <input type="range" id="scrub" min="0" max="${r.days - 1}" value="${this.day}" />
            </div>
            <div class="grid g-4" style="gap:0;margin-top:10px" id="day-metrics">${this.dayMetrics()}</div>
            <div class="grid g-2" style="margin-top:16px">
              <div>
                <div class="eyebrow" style="margin-bottom:6px">Brent ($/bbl)</div>
                <div class="chart" id="ch-brent"></div>
              </div>
              <div>
                <div class="eyebrow" style="margin-bottom:6px">Unmet import demand (kb/d)</div>
                <div class="chart" id="ch-gap"></div>
              </div>
              <div>
                <div class="eyebrow" style="margin-bottom:6px">Strategic reserve cover (days)</div>
                <div class="chart" id="ch-spr"></div>
              </div>
              <div>
                <div class="eyebrow" style="margin-bottom:6px">Refinery utilisation (%)</div>
                <div class="chart" id="ch-util"></div>
              </div>
            </div>
          </div>
        </section>

        <div class="grid g-2">
          <section class="panel">
            <div class="panel-head"><h3 style="font-size:15px">The cascade</h3></div>
            <div class="panel-body">
              <p class="tiny muted" style="margin-bottom:12px;line-height:1.6"><em>${UI.esc(r.precedent)}</em></p>
              ${r.explanation.chain.filter(s => s.step !== 'Reroute').map(s => `
                <div class="cascade-step">
                  <div class="st">${UI.esc(s.step)}</div>
                  <div class="tx">${UI.esc(s.text)}</div>
                </div>`).join('')}
            </div>
          </section>

          <section class="panel">
            <div class="panel-head"><h3 style="font-size:15px">Downstream Impact</h3></div>
            <div class="panel-body">
              <table class="data" style="font-size:13px">
                <thead><tr><th style="font-weight:700">Sector</th><th style="font-weight:700">Input cost</th><th style="font-weight:700">Share of products</th><th style="font-weight:700">Lands</th></tr></thead>
                <tbody>${r.sector_impact.map(s => `
                  <tr>
                    <td><strong>${UI.esc(s.name)}</strong><div class="tiny faint">${UI.esc(s.note)}</div></td>
                    <td class="n">${UI.pct(s.cost_increase_pct)}</td>
                    <td class="n">${s.share_of_products_pct}%</td>
                    <td class="n" style="white-space:nowrap">day ${s.impact_day}</td>
                  </tr>`).join('')}
                </tbody>
              </table>
            </div>
          </section>
        </div>

        <section class="panel">
          <div class="disclosure">
            <button class="disclosure-head" style="padding:13px 16px">
              ${UI.chevron()}
              <span class="disclosure-title" style="font-size:13.5px">Assumptions</span>
              <span class="disclosure-meta">every constant behind the numbers above</span>
            </button>
            <div class="disclosure-body plain" style="padding:0 16px 16px">
              <p class="small muted" style="line-height:1.6;margin-bottom:12px">
                Historical precedent used to sanity-check this scenario:
                <em>${UI.esc(r.precedent)}</em>
                ${r.precedent_source && r.precedent_source.url && !r.precedent_source.url.startsWith('internal://')
                  ? `<a href="${UI.esc(r.precedent_source.url)}" target="_blank" rel="noopener"> Source</a>` : ''}
              </p>
              <table class="data">
                <tbody>
                  ${this.calibRows(r.calibration)}
                </tbody>
              </table>
              <div style="margin-top:12px">
                ${(r.calibration.sources || []).map(s =>
                  `<a class="evidence-link" href="${UI.esc(s.url)}" target="_blank" rel="noopener">${UI.esc(s.label)}</a>`).join('')}
              </div>
            </div>
          </div>
        </section>
      </div>`;

    this.charts();

    const scrub = document.getElementById('scrub');
    scrub.addEventListener('input', () => { this.day = +scrub.value; this.onDay(); });
    document.getElementById('play').addEventListener('click', () => this.togglePlay());
  },

  calibRows(c) {
    const rows = [
      ['World supply', c.world_supply_mbd + ' mb/d'],
      ['Price curve', c.price_curve],
      ['OPEC spare capacity', c.opec_spare_mbd + ' mb/d'],
      ['IEA collective release', c.iea_collective_release_mbd + ' mb/d, tapering over 21 days'],
      ['Pass-through to pump', (c.pass_through_to_pump * 100) + '%'],
      ['Fuel weight in CPI', (c.cpi_weight_fuel * 100) + '%'],
      ['Demand response', (c.demand_response_share * 100) + '% of the shortfall'],
      ['Strategic reserve', UI.num(c.spr_stock_kb) + ' kb, max draw ' + UI.num(c.spr_max_draw_kbd) + ' kb/d'],
      ['GDP base', '$' + UI.num(c.gdp_usd_bn) + ' bn']
    ];
    return rows.map(([k, v]) => `<tr><td style="color:var(--muted)">${UI.esc(k)}</td><td class="n">${UI.esc(v)}</td></tr>`).join('');
  },

  lastDay() { return this.result.series.at(-1); },

  dayMetrics() {
    const d = this.result.series[this.day];
    return `
      <div class="metric" style="padding-left:0">
        <div class="l">Brent</div><div class="v">$${d.brent.toFixed(1)}</div>
        <div class="d up tiny">${UI.pct(d.brent_chg_pct)}</div>
      </div>
      <div class="metric">
        <div class="l">Landed in India</div><div class="v">$${d.landed_usd.toFixed(1)}</div>
        <div class="d faint tiny">freight premium $${d.freight_usd.toFixed(2)} · scarcity premium $${d.scarcity_usd.toFixed(1)}</div>
      </div>
      <div class="metric">
        <div class="l">Delivered</div><div class="v">${UI.num(d.delivered_kbd)}</div>
        <div class="d faint tiny">kb/d · gap ${UI.num(d.gap_kbd)}</div>
      </div>
      <div class="metric">
        <div class="l">Reserve cover</div><div class="v">${d.spr_days_left.toFixed(1)}</div>
        <div class="d faint tiny">days · drawing ${UI.num(d.spr_drawn_kbd)} kb/d</div>
      </div>`;
  },

  charts() {
    const s = this.result.series;
    UI.chart(document.getElementById('ch-brent'), s.map(d => ({ v: d.brent })),
      { colour: '#A6432B', marker: this.day, format: v => '$' + v.toFixed(0) });
    UI.chart(document.getElementById('ch-gap'), s.map(d => ({ v: d.gap_kbd })),
      { colour: '#B07819', marker: this.day, format: v => v.toFixed(0) });
    UI.chart(document.getElementById('ch-spr'), s.map(d => ({ v: d.spr_days_left })),
      { colour: '#1F6F43', marker: this.day, format: v => v.toFixed(1) });
    UI.chart(document.getElementById('ch-util'), s.map(d => ({ v: d.refinery_util })),
      { colour: '#4C7C5C', marker: this.day, format: v => v.toFixed(0) + '%' });
  },

  onDay() {
    const head = document.getElementById('day-head');
    if (head) head.textContent = `Day ${this.day + 1} of ${this.result.days}`;
    const dm = document.getElementById('day-metrics');
    if (dm) dm.innerHTML = this.dayMetrics();
    this.charts();
  },

  togglePlay() {
    this.playing = !this.playing;
    document.getElementById('play').textContent = this.playing ? 'Pause' : 'Play';
    clearInterval(this.timer);
    if (!this.playing) return;
    this.timer = setInterval(() => {
      this.day = (this.day + 1) % this.result.days;
      const scrub = document.getElementById('scrub');
      if (!scrub) { clearInterval(this.timer); return; }
      scrub.value = this.day;
      this.onDay();
    }, 420);
  },

  reset() {
    this.result = null; this.day = 0; this.playing = false;
    clearInterval(this.timer);
    this.render();
  }
};
