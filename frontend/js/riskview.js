/* SUPATH — Risk Intelligence: why the number is the number.

   Every score on this page can be opened until it bottoms out in an observation
   with a URL. If a term is running on a prior because a feed is down, it says
   so in plain words. A score a user cannot audit is a score a user should not act on.
*/

const RiskView = {
  news: null,
  selected: null,

  async render() {
    const el = document.getElementById('view-risk');
    const r = STORE.risk;
    if (!r) { el.innerHTML = UI.skeleton(500); return; }

    this.selected = STORE.selectedCorridor
      || (r.corridors[0] && r.corridors[0].corridor_id);

    el.innerHTML = `
      <div class="stack">
        <div class="grid g-risk">

          <!-- corridor list -->
          <div class="stack">
            <section class="panel">
              <div class="panel-head"><h3>National score</h3></div>
              <div class="panel-body">
                <div class="row" style="align-items:baseline;gap:8px">
                  <span class="num" style="font-size:30px;color:${UI.bandColour(r.national.band)}">${r.national.score}</span>
                  <span class="small muted">${r.national.band} · ${r.national.posture}</span>
                </div>
                <div class="equation" style="margin:12px 0">${UI.esc(r.national.equation)}</div>
                <p class="small muted" style="line-height:1.6">${UI.esc(r.national.method)}</p>
              </div>
            </section>

            <section class="panel">
              <div class="panel-head"><h3>Corridors</h3><span class="spacer"></span>
                <span class="chip">${r.corridors.length}</span></div>
              <div class="panel-body stack" style="gap:8px">
                ${r.corridors.map(c => this.card(c)).join('')}
              </div>
            </section>
          </div>

          <!-- derivation -->
          <div class="stack">
            <section class="panel" id="derivation-panel">${this.derivation(r)}</section>
          </div>
        </div>

        <!-- news, full width, below both columns -->
        <section class="panel">
          <div class="panel-head">
            <h3>News affecting this route</h3>
            <span class="spacer"></span>
            <span class="small faint">Click any headline to model what it does to India</span>
          </div>
          <div class="panel-body" id="news-body">${UI.skeleton(160)}</div>
        </section>
      </div>`;

    el.querySelectorAll('.corridor-card').forEach(b =>
      b.addEventListener('click', () => {
        STORE.selectedCorridor = b.dataset.id;
        this.selected = b.dataset.id;
        el.querySelectorAll('.corridor-card').forEach(x => x.classList.toggle('active', x === b));
        document.getElementById('derivation-panel').innerHTML = this.derivation(STORE.risk);
        this.wireDerivationLinks();
        this.drawWaterfall();
      }));

    this.wireDerivationLinks();
    this.drawWaterfall();
    this.loadNews();
  },

  wireDerivationLinks() {
    document.querySelectorAll('#derivation-panel [data-goto-brief]').forEach(b =>
      b.addEventListener('click', () => App.go('brief')));
  },

  drawWaterfall() {
    const r = STORE.risk;
    if (!r) return;
    const c = r.corridors.find(x => x.corridor_id === this.selected) || r.corridors[0];
    if (!c) return;
    UI.waterfall(document.getElementById(`waterfall-${c.corridor_id}`), c.breakdown);
  },

  card(c) {
    const active = c.corridor_id === this.selected;
    return `
      <button class="corridor-card band-${c.band} ${active ? 'active' : ''}" data-id="${c.corridor_id}">
        <div class="top">
          <span class="nm">${UI.esc(c.short)}</span>
          <span class="sc">${c.score}</span>
        </div>
        <div class="bar band-${c.band}" style="margin-top:7px"><span style="width:${c.score}%"></span></div>
        <div class="meta">${c.share_pct}% of imports · ${UI.num(c.barrels_at_risk_kbd)} kb/d exposed · led by ${UI.esc(c.top_driver.label.toLowerCase())}</div>
      </button>`;
  },

  derivation(r) {
    const c = r.corridors.find(x => x.corridor_id === this.selected) || r.corridors[0];
    if (!c) return '';
    return `
      <div class="panel-head">
        <h3>${UI.esc(c.short)}</h3>
        <span class="spacer"></span>
        <span class="num" style="color:${UI.bandColour(c.band)};font-size:15px;font-weight:700">${c.score}</span>
        <span class="chip" style="color:${UI.bandColour(c.band)}">${c.band} · ${c.posture}</span>
      </div>
      <div class="panel-body">
        <div class="eyebrow" style="margin-bottom:4px">Why</div>
        <p class="small muted" style="line-height:1.6;margin-bottom:14px">${UI.esc(c.why_it_matters)}</p>

        <div class="eyebrow" style="margin-bottom:6px">Component breakdown</div>
        <div id="waterfall-${c.corridor_id}" class="waterfall"></div>
        <div class="row" style="justify-content:space-between;margin-top:4px">
          ${c.breakdown.map(t => `<span class="tiny faint">${UI.esc(t.label.split(' ')[0])}</span>`).join('')}
        </div>

        <div class="derivation" style="margin-top:14px">
          ${c.breakdown.map(t => `
            <div class="term">
              <div class="term-head">
                <span class="lbl">${UI.esc(t.label)}</span>
                <span class="term-math">${(t.weight * 100).toFixed(0)}% × ${t.subscore.toFixed(2)} = ${t.contribution.toFixed(1)}</span>
              </div>
              <div class="bar band-${UI.bandOf(t.subscore * 100)}" style="margin-top:8px">
                <span style="width:${(t.subscore * 100).toFixed(0)}%"></span>
              </div>
              <div class="term-inputs" style="margin-top:5px">
                <span class="src">${UI.esc(t.source)}</span>
              </div>
            </div>`).join('')}
        </div>

        <div class="equation" style="margin-top:14px">${UI.esc(c.equation)}</div>

        <button class="jump-link" style="margin-top:14px" data-goto-brief="1">
          ${UI.jumpIcon()} See recommended actions for this posture
        </button>

        <div class="disclosure" style="margin-top:12px">
          <button class="disclosure-head">
            ${UI.chevron()}
            <span class="disclosure-title">Evidence</span>
            <span class="disclosure-meta">${c.evidence && c.evidence.length ? c.evidence.length + ' articles' : 'none in window'}</span>
          </button>
          <div class="disclosure-body plain">
            ${c.evidence && c.evidence.length ? c.evidence.slice(0, 4).map(e => `
              <a class="evidence-link" href="${UI.esc(e.url)}" target="_blank" rel="noopener">
                ${UI.esc(e.title)}
                <span class="d">${UI.esc(e.domain)} · ${UI.timeAgo(e.seen)} · escalation ${e.escalation}</span>
              </a>`).join('')
              : `<p class="tiny faint">No corridor articles retrieved in this window — the conflict term is running on its neutral prior, and the score should be read as provisional.</p>`}
          </div>
        </div>
      </div>`;
  },

  async loadNews() {
    const body = document.getElementById('news-body');
    try {
      const n = await API.news();
      this.news = n;
      const arts = n.articles || [];
      if (!arts.length) {
        body.innerHTML = `<p class="small muted" style="line-height:1.6">
          The GDELT feed returned nothing for these corridors in this window. That is either a
          quiet day or an unreachable source — SUPATH does not guess which, so the conflict term
          in every corridor score above is currently running on its documented neutral prior.</p>
          ${UI.source({ source: n.source, url: n.url, mode: n.mode })}`;
        return;
      }
      body.innerHTML = arts.slice(0, 14).map((a, i) => `
        <div class="news-item ${i >= 5 ? 'reveal-hidden' : ''}">
          <div class="t">${UI.esc(a.title)}</div>
          <div class="m">
            <span class="chip">${UI.esc(a.corridor_short)}</span>
            <span class="esc" title="Escalation weight ${a.escalation}"><span style="width:${a.escalation * 100}%"></span></span>
            <span class="tiny faint">${UI.esc(a.domain)} · ${UI.timeAgo(a.seen)}</span>
            ${(a.terms || []).slice(0, 3).map(t => `<span class="chip amber">${UI.esc(t)}</span>`).join('')}
            <span class="spacer" style="flex:1"></span>
            <button class="btn sm" data-impact='${UI.esc(JSON.stringify({ corridor: a.corridor, escalation: a.escalation, title: a.title, url: a.url }))}'>
              What does this do to India?</button>
            <a class="btn sm ghost" href="${UI.esc(a.url)}" target="_blank" rel="noopener">Source</a>
          </div>
        </div>`).join('')
        + (arts.length > 5 ? `<button class="reveal-more" data-reveals="news-body">Show ${Math.min(arts.length, 14) - 5} more signal${Math.min(arts.length, 14) - 5 === 1 ? '' : 's'}</button>` : '')
        + `<div style="margin-top:12px">${UI.source({ source: n.source, url: n.url, mode: n.mode })}</div>`;

      body.querySelectorAll('[data-impact]').forEach(b =>
        b.addEventListener('click', () => this.impact(JSON.parse(b.dataset.impact))));
    } catch (e) {
      body.innerHTML = '<p class="small muted">News feed unavailable.</p>';
    }
  },

  async impact(payload) {
    UI.modal('Modelling the consequence…', UI.skeleton(200));
    try {
      const r = await API.impact(payload);
      UI.modal('What this does to India', `
        <p class="serif" style="font-size:15px;line-height:1.6">${UI.esc(payload.title)}</p>
        <div class="grid g-3" style="margin:16px 0;gap:0">
          <div class="metric" style="padding-left:0">
            <div class="l">Imports at risk</div>
            <div class="v">${UI.num(r.import_reduction_kbd)}</div>
            <div class="d faint tiny">kb/d · ${r.import_reduction_pct}% of the slate</div>
          </div>
          <div class="metric">
            <div class="l">Brent</div>
            <div class="v">$${r.price_band_usd[0]}–${r.price_band_usd[1]}</div>
            <div class="d up tiny">${UI.pct(r.price_change_pct)} at peak</div>
          </div>
          <div class="metric">
            <div class="l">Pump price</div>
            <div class="v">${UI.pct(r.pump_pct)}</div>
            <div class="d faint tiny">at 62% pass-through</div>
          </div>
        </div>

        <div class="eyebrow" style="margin-bottom:6px">Who feels it first</div>
        <table class="data">
          <thead><tr><th>Sector</th><th>Input cost</th><th>Lands by</th></tr></thead>
          <tbody>${r.industries.map(s => `
            <tr><td>${UI.esc(s.name)}<div class="tiny faint">${UI.esc(s.note)}</div></td>
                <td class="n">${UI.pct(s.cost_increase_pct)}</td>
                <td class="n">day ${s.impact_day}</td></tr>`).join('')}
          </tbody>
        </table>

        <div style="margin-top:16px;padding-top:14px;border-top:1px solid var(--line)">
          <div class="eyebrow" style="margin-bottom:6px">How this was produced</div>
          <p class="small muted" style="line-height:1.6">${UI.esc(r.basis)}</p>
          <p class="small" style="line-height:1.6;margin-top:8px;color:var(--r-elev)">${UI.esc(r.caveat)}</p>
          <p class="tiny faint" style="margin-top:8px">Engine: ${UI.esc(r.engine)}</p>
        </div>`);
    } catch (e) {
      UI.modal('Impact', '<p class="small muted">The model could not be run for this article.</p>');
    }
  }
};
