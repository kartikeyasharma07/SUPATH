/* SUPATH — Situation: what is happening now.

   BLUF, literally: the map is the first thing on the page, then the number,
   then the reasoning. Everything below the fold is one click away, not
   scrolled past — a rushed reader gets the picture without scrolling, and
   the detail is still there for the reader who has the time to check it.
*/

const Situation = {
  mounted: false,

  render() {
    const el = document.getElementById('view-situation');
    const s = STORE.situation;
    if (!s) { el.innerHTML = UI.skeleton(60) + '<div style="height:12px"></div>' + UI.skeleton(420); return; }

    const n = s.national;
    const p = s.prices.brent.value;
    const a = s.attribution.value;
    const band = n.band;
    const col = UI.bandColour(band);
    const top = a.candidates[0];

    el.innerHTML = `
      <div class="stack">

        ${this.freshnessBanner()}

        <!-- map — first, on purpose -->
        <section class="panel">
          <div class="panel-head">
            <h3>Corridor picture</h3>
            <span class="chip ${STORE.vessels ? Situation.aisChipClass(STORE.vessels.mode) : ''}"
                  id="ais-chip">${STORE.vessels ? Situation.aisChipLabel(STORE.vessels.mode) : '…'}</span>
            <span class="spacer"></span>
            <div class="layer-toggles" id="layers">
              <button class="toggle on" data-layer="vessels">Vessels</button>
              <button class="toggle on" data-layer="corridors">Corridors</button>
              <button class="toggle on" data-layer="ports">Ports</button>
              <button class="toggle on" data-layer="choke">Chokepoints</button>
              <button class="toggle" data-layer="density">Density</button>
            </div>
          </div>
          <div id="map"></div>
          <div class="map-legend">
            ${['low', 'moderate', 'elevated', 'high', 'severe'].map(b =>
              `<span class="legend-item"><span class="swatch" style="background:${UI.bandColour(b)}"></span>${b}</span>`).join('')}
            <span class="legend-item" style="margin-left:auto">
              <svg width="11" height="11" viewBox="0 0 20 20"><path d="M10 1 L16 18 L10 14.4 L4 18 Z" fill="#1F6F43"/></svg>
              Laden
            </span>
            <span class="legend-item">
              <svg width="11" height="11" viewBox="0 0 20 20"><path d="M10 1 L16 18 L10 14.4 L4 18 Z" fill="none" stroke="#1F6F43" stroke-width="1.7"/></svg>
              Simulated hull
            </span>
            <span class="legend-item" id="vessel-count">${STORE.vessels ? STORE.vessels.count + ' tankers tracked' : ''}</span>
          </div>
          ${STORE.vessels && STORE.vessels.mode === 'hybrid' ? `
          <div class="map-legend" style="border-top:none;padding-top:0">
            <span class="legend-item"><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#2E8FA6;margin-right:5px"></span>Live contact (unclassified) — real, inside the dashed boxes only</span>
          </div>` : ''}
          ${STORE.vessels && STORE.vessels.blocked && Object.keys(STORE.vessels.blocked).length ? `
          <div class="map-legend" style="border-top:none;padding-top:0">
            <span class="legend-item"><span class="swatch" style="background:#A6432B"></span>Blocked corridor</span>
            <span class="legend-item"><span class="swatch" style="background:#B07819"></span>Degraded</span>
            <span class="legend-item"><span class="swatch" style="background:#1E7A8C"></span>Reroute flow / diverted hull</span>
          </div>` : ''}
        </section>

        <!-- why the price moved — above the national posture card now -->
        <section class="panel">
          <div class="panel-head">
            <h3>Why the price moved</h3>
            <span class="spacer"></span>
            ${UI.source(s.prices.brent)}
          </div>
          <div class="panel-body">
            <div class="grid g-4" style="gap:0">
              ${this.metric('Brent', '$' + p.last.toFixed(2), p.chg_1d_pct, 'today')}
              ${this.metric('5 sessions', UI.pct(p.chg_5d_pct), p.chg_5d_pct, 'cumulative')}
              ${this.metric('30 days', UI.pct(p.chg_30d_pct), p.chg_30d_pct, 'cumulative')}
              ${this.metric('Volatility', p.vol_annualised_pct + '%', 0, 'annualised, 20d')}
            </div>
            <div id="spark" class="sparkline" style="margin:14px 0 6px"></div>
            <div class="row" style="justify-content:space-between">
              <span class="tiny faint">${p.history[0].d}</span>
              <span class="tiny faint">30-day range $${p.low_30d} – $${p.high_30d}</span>
              <span class="tiny faint">${p.date}</span>
            </div>

            ${top ? `
            <div style="margin-top:16px;border-top:1px solid var(--line);padding-top:12px">
              <div class="row" style="justify-content:space-between;align-items:flex-start;gap:10px">
                <div style="flex:1">
                  <span class="eyebrow">Strongest concurrent signal</span>
                  <div style="font-size:12.5px;color:var(--ink);margin-top:3px">
                    <strong>${UI.esc(top.corridor)}</strong> — ${UI.esc(top.driver)}, explaining an estimated ${top.explains_pct}% of today's move
                  </div>
                </div>
                <button class="jump-link" data-goto-risk="${UI.esc(top.corridor_id)}">${UI.jumpIcon()} Full derivation</button>
              </div>
            </div>` : ''}

            <div class="disclosure" style="margin-top:6px">
              <button class="disclosure-head">
                ${UI.chevron()}
                <span class="disclosure-title">All ${a.candidates.length} concurrent signals</span>
                <span class="disclosure-meta">ranked by pressure</span>
              </button>
              <div class="disclosure-body plain">
                <table class="data">
                  <thead><tr><th>Signal</th><th>Driver</th><th>Pressure</th><th>Explains</th></tr></thead>
                  <tbody>
                    ${a.candidates.map(c => `
                      <tr>
                        <td><strong>${UI.esc(c.corridor)}</strong>
                          ${c.evidence && c.evidence.length
                            ? `<div class="tiny faint" style="margin-top:3px">${UI.esc(c.evidence[0].title.slice(0, 78))}…</div>` : ''}</td>
                        <td>${UI.esc(c.driver)}</td>
                        <td class="n">${(c.pressure * 100).toFixed(0)}%</td>
                        <td class="n" style="width:110px">
                          <div class="row" style="gap:7px">
                            <div class="bar band-moderate" style="flex:1"><span style="width:${c.explains_pct}%"></span></div>
                            <span>${c.explains_pct}%</span>
                          </div>
                        </td>
                      </tr>`).join('')}
                  </tbody>
                </table>
                <p class="tiny muted" style="margin-top:11px;line-height:1.55">${UI.esc(a.caveat)}</p>
                ${UI.source(s.attribution)}
              </div>
            </div>
          </div>
        </section>

        <!-- the national posture card — compact, no dead space -->
        <section class="hero">
          <div class="hero-copy">
            <div class="eyebrow">National posture · ${new Date(s.time).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' })}</div>
            <h2>${UI.esc(a.headline)}</h2>
            <div class="gauge-block" style="margin-top:16px">
              <div class="gauge-readout">
                <span class="n" style="color:${col}">${n.score}</span>
                <span class="chip" style="background:${col};color:#fff;border-color:${col}">${band}</span>
              </div>
              <div id="nat-gauge" class="gauge"></div>
            </div>
            <div class="stat-row" style="margin-top:16px">
              <div class="stat-card" style="--accent:${col}">
                <div class="l">Strategic cover</div>
                <div class="v">${n.spr_cover_days}<span style="font-size:14px"> d</span></div>
              </div>
              <div class="stat-card" style="--accent:var(--r-elev)">
                <div class="l">Exposed</div>
                <div class="v">${UI.num(n.exposed_kbd)}<span style="font-size:14px"> kb/d</span></div>
              </div>
              <div class="stat-card" style="--accent:var(--moss)">
                <div class="l">Crude imported</div>
                <div class="v">${UI.num((STORE.reference && STORE.reference.india.crude_imports_kbd) || 4700)}<span style="font-size:14px"> kb/d</span></div>
              </div>
            </div>
          </div>
          <canvas id="globe" width="220" height="170"></canvas>
        </section>

        <!-- ports + sea state — compact, side by side, collapsed by default -->
        <div class="grid g-2">
          <section class="panel">
            <div class="disclosure">
              <button class="disclosure-head" style="padding:13px 16px">
                ${UI.chevron()}
                <span class="disclosure-title">Indian discharge ports</span>
                <span class="spacer"></span>
                ${UI.source(s.port_health)}
              </button>
              <div class="disclosure-body plain" style="padding:0 16px 14px">
                ${this.ports(s)}
              </div>
            </div>
          </section>

          <section class="panel">
            <div class="disclosure">
              <button class="disclosure-head" style="padding:13px 16px">
                ${UI.chevron()}
                <span class="disclosure-title">Sea state at the gates</span>
                <span class="spacer"></span>
                ${UI.source(s.weather)}
              </button>
              <div class="disclosure-body plain" style="padding:0 16px 14px">
                ${this.weather(s)}
              </div>
            </div>
          </section>
        </div>
      </div>`;

    /* map first, then the smaller decorative pieces */
    if (SetuMap.map) { SetuMap.map.remove(); SetuMap.map = null; }
    SetuMap.markers = new Map();
    SetuMap.init(document.getElementById('map'));
    Globe.init(document.getElementById('globe'));

    UI.gauge(document.getElementById('nat-gauge'), n.score);
    UI.sparkline(document.getElementById('spark'), p.history,
      p.chg_30d_pct >= 0 ? '#A6432B' : '#4C7C5C');

    document.getElementById('layers').addEventListener('click', e => {
      const b = e.target.closest('.toggle'); if (!b) return;
      const on = SetuMap.toggle(b.dataset.layer);
      b.classList.toggle('on', on);
    });

    el.querySelectorAll('[data-goto-risk]').forEach(b =>
      b.addEventListener('click', () => App.go('risk', { corridor: b.dataset.gotoRisk })));
  },

  freshnessBanner() {
    const data = STORE.brief;
    if (!data) return `<div class="freshness"><span class="icon">…</span> Assessing data freshness…</div>`;
    const conf = data.brief.value.confidence;
    const live = !conf.degraded || !conf.degraded.length;
    const icon = live
      ? '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#1F6F43" stroke-width="2.2"><path d="M20 6L9 17l-5-5"/></svg>'
      : '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#B07819" stroke-width="2.2"><path d="M12 3l9 16H3L12 3zM12 10v4M12 17h.01"/></svg>';
    const text = live
      ? '<strong>All streams live</strong> — every number on this page is from a fetch made this run.'
      : `<strong>Reference-data mode</strong> — ${UI.esc(conf.degraded.join(', '))} ${conf.degraded.length === 1 ? 'is' : 'are'} not live in this run. Directional guidance only.`;
    return `<div class="freshness ${live ? '' : 'warn'}"><span class="icon">${icon}</span><span>${text}</span></div>`;
  },

  metric(label, value, chg, note) {
    const cls = chg > 0.05 ? 'up' : chg < -0.05 ? 'down' : 'muted';
    return `
      <div class="metric">
        <div class="l">${label}</div>
        <div class="v">${value}</div>
        <div class="d ${cls}">${chg ? UI.pct(chg) + ' ' : ''}<span class="faint tiny">${note}</span></div>
      </div>`;
  },

  ports(s) {
    const ph = (s.port_health.value && s.port_health.value.ports) || {};
    const rows = Object.values(ph).sort((a, b) => a.index - b.index).slice(0, 7);
    if (!rows.length) return '<p class="small muted">No port telemetry.</p>';
    return rows.map(p => {
      const col = p.index >= 80 ? '#4C7C5C' : p.index >= 60 ? '#B07819' : '#A6432B';
      return `
        <div class="port-row">
          <div class="nm">${UI.esc(p.name)}<div class="tiny faint">${UI.esc(p.state)} · ${p.queue} at anchorage</div></div>
          <div class="health-bar"><span style="width:${p.index}%;background:${col}"></span></div>
          <div class="ix" style="color:${col}">${UI.num(p.index)}</div>
        </div>`;
    }).join('');
  },

  weather(s) {
    const w = (s.weather.value) || {};
    const gates = Object.values(w).filter(x => x.kind === 'chokepoint');
    if (!gates.length) return '<p class="small muted">No marine observations.</p>';
    return gates.map(g => {
      const col = g.score < 0.3 ? '#4C7C5C' : g.score < 0.55 ? '#B07819' : '#A6432B';
      const o = g.obs || {};
      return `
        <div class="port-row">
          <div class="nm">${UI.esc(g.name)}
            <div class="tiny faint">${o.wave_height_m != null ? `${o.wave_height_m} m swell · ${o.wind_kt} kt` : UI.esc(g.formula)}</div>
          </div>
          <div class="ix" style="color:${col}">${UI.esc(g.status)}</div>
        </div>`;
    }).join('');
  },

  /* live-ish bits that update without a full re-render */
  onVessels(v) {
    const chip = document.getElementById('ais-chip');
    if (chip) {
      chip.className = 'chip ' + this.aisChipClass(v.mode);
      chip.textContent = this.aisChipLabel(v.mode);
    }
    const c = document.getElementById('vessel-count');
    if (c) c.textContent = v.count + ' tankers tracked';
  },

  aisChipClass(mode) {
    return mode === 'live' ? 'green' : mode === 'hybrid' ? 'amber' : 'sim';
  },

  aisChipLabel(mode) {
    return mode === 'live' ? 'LIVE AIS' : mode === 'hybrid' ? 'PARTIAL LIVE AIS' : 'SIMULATED AIS';
  }
};
