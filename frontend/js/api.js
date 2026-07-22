/* SUPATH — API client and shared state.
   One store, one fetch per endpoint, everything else reads from here. */

const API = {
  base: '',
  async get(path) {
    const r = await fetch(this.base + path);
    if (!r.ok) throw new Error(path + ' → ' + r.status);
    return r.json();
  },
  async post(path, body) {
    const r = await fetch(this.base + path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body || {})
    });
    if (!r.ok) throw new Error(path + ' → ' + r.status);
    return r.json();
  },

  health:      () => API.get('/api/health'),
  reference:   () => API.get('/api/reference'),
  situation:   () => API.get('/api/situation'),
  vessels:     () => API.get('/api/vessels'),
  risk:        () => API.get('/api/risk'),
  news:        (c, t) => API.get('/api/news' + (c ? `?corridor=${c}&timespan=${t || '24h'}` : '')),
  impact:      (b) => API.post('/api/impact', b),
  screen:      (name) => API.post('/api/screen', { name }),
  runScenario: (b) => API.post('/api/scenario', b),
  clearScenario: () => API.post('/api/scenario/clear', {}),
  recommendations: () => API.get('/api/recommendations'),
  brief:       () => API.get('/api/brief'),
  reportURL:   (kind) => `/api/report.pdf?kind=${kind || 'full'}`
};

/* Shared state. Views subscribe; nothing fetches twice. */
const STORE = {
  reference: null,
  situation: null,
  risk: null,
  vessels: null,
  brief: null,
  scenario: null,        // last scenario result
  scenarioId: null,
  selectedCorridor: null,
  listeners: {},

  on(evt, fn) { (this.listeners[evt] ||= []).push(fn); },
  emit(evt, data) { (this.listeners[evt] || []).forEach(fn => fn(data)); },
  set(key, val) { this[key] = val; this.emit(key, val); }
};
