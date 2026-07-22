/* SUPATH — the shell: routing, boot, refresh, and the single world state.

   One rule holds this together: there is exactly one world at a time. If a
   scenario is running, the map, the corridor scores, the advisor and the PDF all
   describe that world. Nothing on screen is ever answering a different question
   from the panel beside it.
*/

const App = {
  view: 'situation',
  refreshTimer: null,

  TITLES: {
    situation: ['Live Overview', 'India-bound crude corridors'],
    risk: ['Risk Intelligence', 'How each score was derived'],
    scenario: ['Scenario Simulator', ''],
    brief: ['Recommendations', '']
  },

  async boot() {
    this.wire();

    try {
      STORE.set('reference', await API.reference());
    } catch (e) { /* the views degrade rather than blank */ }

    await this.refresh();
    Situation.render();
    Brief.rail();
    SetuMap.poll(6000);
    this.feeds();

    STORE.on('vessels', v => { Situation.onVessels(v); });

    /* the world moves on its own, slowly, so the picture is never stale */
    this.refreshTimer = setInterval(() => this.refresh(true), 120000);
  },

  wire() {
    document.getElementById('nav').addEventListener('click', e => {
      const b = e.target.closest('.nav-item');
      if (b) this.go(b.dataset.view);
    });

    document.getElementById('collapse-rail').addEventListener('click', () => {
      document.getElementById('rail').classList.toggle('collapsed');
      setTimeout(() => SetuMap.map && SetuMap.map.invalidateSize(), 240);
    });

    document.getElementById('refresh').addEventListener('click', async () => {
      const b = document.getElementById('refresh');
      b.disabled = true; b.textContent = 'Refreshing…';
      await this.refresh();
      this.rerender();
      b.disabled = false; b.textContent = 'Refresh';
    });

    document.getElementById('clear-scenario').addEventListener('click', () => this.clearScenario());
  },

  go(view, opts) {
    if (!this.TITLES[view]) return;
    this.view = view;
    if (opts && opts.corridor) STORE.selectedCorridor = opts.corridor;
    document.querySelectorAll('.nav-item').forEach(b =>
      b.classList.toggle('active', b.dataset.view === view));
    ['situation', 'risk', 'scenario', 'brief'].forEach(v =>
      document.getElementById('view-' + v).hidden = (v !== view));

    const [t, c] = this.TITLES[view];
    document.getElementById('view-title').textContent = t;
    document.getElementById('view-ctx').textContent = c;

    this.rerender();
    document.getElementById('view-' + view).scrollTop = 0;
  },

  rerender() {
    if (this.view === 'situation') Situation.render();
    if (this.view === 'risk') RiskView.render();
    if (this.view === 'scenario') ScenarioView.render();
    if (this.view === 'brief') Brief.render();
    Brief.rail();
  },

  async refresh(quiet) {
    const jobs = [
      API.situation().then(d => STORE.set('situation', d)).catch(() => {}),
      API.risk().then(d => STORE.set('risk', d)).catch(() => {}),
      API.brief().then(d => STORE.set('brief', d)).catch(() => {}),
      API.vessels().then(d => STORE.set('vessels', d)).catch(() => {})
    ];
    await Promise.all(jobs);
    this.posture();
    this.feeds();
    if (quiet && this.view === 'situation') Situation.render();
    if (quiet) Brief.rail();
  },

  posture() {
    const n = STORE.situation && STORE.situation.national;
    if (!n) return;
    const col = UI.bandColour(n.band);
    document.getElementById('posture-dot').style.background = col;
    document.getElementById('posture-label').textContent = n.posture;
    document.getElementById('posture-score').textContent = n.score + ' · ' + n.band;
  },

  /* the honest bit: which feeds are actually live right now */
  feeds() {
    const s = STORE.situation, v = STORE.vessels, b = STORE.brief;
    if (!s) return;
    const rows = [
      ['AIS', v ? v.mode : 'unavailable'],
      ['Prices (Yahoo Finance)', s.prices.brent.mode],
      ['News (GDELT)', s.attribution.mode === 'modelled' && s.corridors[0]
        ? (STORE.risk && STORE.risk.corridors[0].news_mode) || 'unavailable' : 'unavailable'],
      ['Ports (PortWatch)', s.port_health.mode],
      ['Weather (Open-Meteo)', s.weather.mode],
      ['Sanctions (OFAC)', STORE.risk ? STORE.risk.sanctions_landscape.mode : 'unavailable']
    ];
    document.getElementById('feeds').innerHTML = rows.map(([n, m]) => `
      <div class="feed" title="${UI.esc(m)}">
        <span class="dot ${UI.feedDot(m)}"></span>${UI.esc(n)}
      </div>`).join('');
  },

  showScenarioBanner(r) {
    const el = document.getElementById('scenario-banner');
    el.classList.add('on');
    document.getElementById('scenario-banner-text').innerHTML =
      `<strong>Scenario running:</strong> ${UI.esc(r.name)} at ${(r.severity * 100).toFixed(0)}% severity. ` +
      `Every panel — map, corridor scores, advisor, PDF — now describes this world, not the live one.`;
  },

  async clearScenario() {
    try { await API.clearScenario(); } catch (e) { /* ignore */ }
    STORE.scenario = null; STORE.scenarioId = null;
    ScenarioView.result = null; ScenarioView.day = 0;
    clearInterval(ScenarioView.timer); ScenarioView.playing = false;
    document.getElementById('scenario-banner').classList.remove('on');
    await this.refresh();
    this.rerender();
  }
};

window.addEventListener('DOMContentLoaded', () => App.boot());
