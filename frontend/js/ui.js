/* SUPATH — UI primitives.
   Small, boring, reused everywhere. The interesting thinking lives in the views. */

const UI = {

  bandColour(band) {
    return ({
      low: '#4C7C5C', moderate: '#1F6F43', elevated: '#B07819',
      high: '#A6432B', severe: '#7E2418'
    })[band] || '#4C7C5C';
  },

  bandOf(score) {
    if (score < 25) return 'low';
    if (score < 50) return 'moderate';
    if (score < 70) return 'elevated';
    if (score < 85) return 'high';
    return 'severe';
  },

  num(v, d = 0) {
    if (v === null || v === undefined || Number.isNaN(v)) return '—';
    return Number(v).toLocaleString('en-IN', { minimumFractionDigits: d, maximumFractionDigits: d });
  },

  pct(v, d = 1) {
    if (v === null || v === undefined) return '—';
    const s = Number(v) >= 0 ? '+' : '';
    return s + Number(v).toFixed(d) + '%';
  },

  esc(s) {
    return String(s ?? '').replace(/[&<>"']/g, c =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  },

  /* Provenance chip. Every number on this platform can produce one of these. */
  source(env, extra) {
    if (!env) return '';
    const mode = env.mode || env._mode || 'reference';
    const label = { live: 'Live', cached: 'Cached', reference: 'Reference value',
                    modelled: 'Modelled', simulated: 'Simulated',
                    unavailable: 'Source unreachable' }[mode] || mode;
    const url = env.url
      ? `<a href="${UI.esc(env.url)}" target="_blank" rel="noopener">${UI.esc(env.source)}</a>`
      : UI.esc(env.source || '');
    return `<span class="src" title="${UI.esc(env.method || '')}">${label} · ${url}${extra ? ' · ' + UI.esc(extra) : ''}</span>`;
  },

  feedDot(mode) {
    if (mode === 'live') return 'live';
    if (mode === 'cached') return 'live';
    if (mode === 'unavailable') return 'off';
    return 'ref';
  },

  timeAgo(iso) {
    if (!iso) return '';
    const t = new Date(iso).getTime();
    if (Number.isNaN(t)) return iso;
    const m = Math.round((Date.now() - t) / 60000);
    if (m < 1) return 'just now';
    if (m < 60) return m + 'm ago';
    const h = Math.round(m / 60);
    if (h < 24) return h + 'h ago';
    return Math.round(h / 24) + 'd ago';
  },

  /* --- sparkline: price history, drawn small and quiet --- */
  sparkline(el, points, colour) {
    if (!el || !points || points.length < 2) return;
    const w = el.clientWidth || 280, h = el.clientHeight || 44;
    const xs = points.map(p => p.p);
    const min = Math.min(...xs), max = Math.max(...xs), span = (max - min) || 1;
    const step = w / (points.length - 1);
    const path = points.map((p, i) =>
      `${i ? 'L' : 'M'}${(i * step).toFixed(1)},${(h - 4 - ((p.p - min) / span) * (h - 10)).toFixed(1)}`
    ).join(' ');
    const last = points.at(-1);
    const lx = w - 1, ly = h - 4 - ((last.p - min) / span) * (h - 10);
    el.innerHTML = `
      <svg width="100%" height="${h}" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">
        <path d="${path} L${w},${h} L0,${h} Z" fill="${colour}" opacity=".07"/>
        <path d="${path}" fill="none" stroke="${colour}" stroke-width="1.5"
              stroke-linejoin="round" stroke-linecap="round"/>
        <circle cx="${lx - 2}" cy="${ly}" r="2.6" fill="${colour}"/>
      </svg>`;
  },

  /* --- line chart: scenario series --- */
  chart(el, series, opts) {
    if (!el) return;
    const o = Object.assign({ colour: '#1F6F43', fill: true, marker: null, format: v => v }, opts || {});
    const w = el.clientWidth || 500, h = el.clientHeight || 150;
    const pad = { l: 42, r: 10, t: 12, b: 20 };
    const vals = series.map(s => s.v);
    let min = Math.min(...vals), max = Math.max(...vals);
    if (min === max) { min -= 1; max += 1; }
    const pd = (max - min) * 0.12; min -= pd; max += pd;
    const X = i => pad.l + (i / Math.max(1, series.length - 1)) * (w - pad.l - pad.r);
    const Y = v => pad.t + (1 - (v - min) / (max - min)) * (h - pad.t - pad.b);

    const line = series.map((s, i) => `${i ? 'L' : 'M'}${X(i).toFixed(1)},${Y(s.v).toFixed(1)}`).join(' ');
    const area = `${line} L${X(series.length - 1).toFixed(1)},${h - pad.b} L${pad.l},${h - pad.b} Z`;
    const gridY = [min + (max - min) * 0.15, (min + max) / 2, max - (max - min) * 0.15];

    const markerLine = (o.marker != null && o.marker >= 0 && o.marker < series.length)
      ? `<line x1="${X(o.marker).toFixed(1)}" y1="${pad.t}" x2="${X(o.marker).toFixed(1)}" y2="${h - pad.b}"
              stroke="#12281F" stroke-width="1" stroke-dasharray="3 3" opacity=".45"/>
         <circle cx="${X(o.marker).toFixed(1)}" cy="${Y(series[o.marker].v).toFixed(1)}" r="3.5"
              fill="#fff" stroke="${o.colour}" stroke-width="2"/>` : '';

    el.innerHTML = `
      <svg width="100%" height="${h}" viewBox="0 0 ${w} ${h}">
        ${gridY.map(g => `
          <line x1="${pad.l}" y1="${Y(g).toFixed(1)}" x2="${w - pad.r}" y2="${Y(g).toFixed(1)}"
                stroke="#E1E9E3" stroke-width="1"/>
          <text x="${pad.l - 6}" y="${(Y(g) + 3).toFixed(1)}" text-anchor="end"
                font-size="9" fill="#8B9A91" font-family="IBM Plex Mono, monospace">${o.format(g)}</text>`).join('')}
        ${o.fill ? `<path d="${area}" fill="${o.colour}" opacity=".08"/>` : ''}
        <path d="${line}" fill="none" stroke="${o.colour}" stroke-width="1.8"
              stroke-linejoin="round" stroke-linecap="round"/>
        ${markerLine}
        <text x="${pad.l}" y="${h - 6}" font-size="9" fill="#8B9A91">Day 1</text>
        <text x="${w - pad.r}" y="${h - 6}" font-size="9" fill="#8B9A91" text-anchor="end">Day ${series.length}</text>
      </svg>`;
  },

  /* --- risk gauge: five band zones, a needle at the score --- */
  gauge(el, score, opts) {
    if (!el) return;
    const o = Object.assign({ bands: [[0,25,'#4C7C5C'],[25,50,'#1F6F43'],[50,70,'#B07819'],
                                       [70,85,'#A6432B'],[85,100,'#7E2418']] }, opts || {});
    const w = el.clientWidth || 260, h = 30, barY = 8, barH = 13;
    const zones = o.bands.map(([lo, hi, col]) => {
      const x = (lo / 100) * w, ww = ((hi - lo) / 100) * w;
      return `<rect x="${x.toFixed(1)}" y="${barY}" width="${Math.max(0,ww-1).toFixed(1)}" height="${barH}" fill="${col}"/>`;
    }).join('');
    const ticks = [25, 50, 70, 85].map(b => {
      const x = (b / 100) * w;
      return `<text x="${x.toFixed(1)}" y="${h}" font-size="8" fill="#8B9A91" text-anchor="middle" font-family="IBM Plex Mono, monospace">${b}</text>`;
    }).join('');
    const nx = (Math.max(0, Math.min(100, score)) / 100) * w;
    el.innerHTML = `
      <svg width="100%" height="${h}" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">
        ${zones}
        <polygon points="${(nx-4).toFixed(1)},0 ${(nx+4).toFixed(1)},0 ${nx.toFixed(1)},${barY+barH-1}"
                 fill="#12281F" stroke="#fff" stroke-width="0.6"/>
        ${ticks}
      </svg>`;
  },

  /* --- waterfall: stacked segments building to a total, for score derivation --- */
  waterfall(el, terms, opts) {
    if (!el) return;
    const o = Object.assign({ scale: 100, colours: {
      'Conflict & Security': '#A6432B', 'Sanctions Exposure': '#B07819',
      'Port Congestion': '#4C7C5C', 'Weather & Sea State': '#2E7A8C',
      'Market Stress': '#123F27' } }, opts || {});
    const w = el.clientWidth || 260, h = 30, barY = 5, barH = 20;
    const fallback = ['#A6432B', '#B07819', '#4C7C5C', '#2E7A8C', '#123F27'];
    let x = 0, segs = '';
    terms.forEach((t, i) => {
      const colour = o.colours[t.label] || fallback[i % fallback.length];
      const ww = Math.max(0, (t.contribution / o.scale) * w);
      segs += `<rect x="${x.toFixed(1)}" y="${barY}" width="${Math.max(0,ww-0.6).toFixed(1)}" height="${barH}" fill="${colour}"/>`;
      if (ww > 20) {
        segs += `<text x="${(x+ww/2).toFixed(1)}" y="${barY+barH/2+3}" font-size="9" fill="#fff"
                       text-anchor="middle" font-family="IBM Plex Mono, monospace" font-weight="600">${t.contribution.toFixed(0)}</text>`;
      }
      x += ww;
    });
    const total = terms.reduce((s, t) => s + t.contribution, 0);
    el.innerHTML = `
      <svg width="100%" height="${h}" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">
        ${segs}
        <text x="${Math.min(x + 6, w - 4).toFixed(1)}" y="${barY+barH/2+4}" font-size="12" fill="#12281F"
              font-weight="700" font-family="IBM Plex Mono, monospace">${total.toFixed(0)}</text>
      </svg>`;
  },

  /* --- how close a tripwire is to firing: reuses the band bar classes --- */
  proximityBand(progress) {
    const p = progress || 0;
    if (p >= 0.85) return 'high';
    if (p >= 0.5) return 'elevated';
    return 'low';
  },

  /* --- flag badge: emoji (best-effort) + a guaranteed-readable ISO code --- */
  flagBadge(flag) {
    if (!flag) return '<span class="flag-badge"><span class="fc">unflagged</span></span>';
    return `<span class="flag-badge"><span class="fe">${flag.emoji || ''}</span><span class="fc">${UI.esc(flag.iso2)}</span></span>`;
  },

  chevron() {
    return '<svg class="disclosure-chevron" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 6l6 6-6 6"/></svg>';
  },

  jumpIcon() {
    return '<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4"><path d="M7 17L17 7M9 7h8v8"/></svg>';
  },

  modal(title, html) {
    document.getElementById('modal-title').textContent = title;
    document.getElementById('modal-body').innerHTML = html;
    document.getElementById('modal-bg').classList.add('on');
  },

  closeModal() { document.getElementById('modal-bg').classList.remove('on'); },

  skeleton(h = 120) { return `<div class="skeleton" style="height:${h}px"></div>`; }
};

document.addEventListener('click', e => {
  if (e.target.id === 'modal-bg' || e.target.closest('#modal-close')) UI.closeModal();

  const dh = e.target.closest('.disclosure-head');
  if (dh) dh.closest('.disclosure').classList.toggle('open');

  const rm = e.target.closest('.reveal-more');
  if (rm) {
    const list = document.getElementById(rm.dataset.reveals);
    if (list) {
      list.querySelectorAll('.reveal-hidden').forEach(x => x.classList.remove('reveal-hidden'));
      rm.remove();
    }
  }
});
document.addEventListener('keydown', e => { if (e.key === 'Escape') UI.closeModal(); });
