/* SUPATH — the corridor globe.

   The one piece of theatre in the whole interface, and it earns its place: it is
   the only view that shows India's crude problem as it actually is — a set of
   long, thin threads reaching across half the planet into one coastline, each
   one carrying a colour that means something.

   Orthographic projection on canvas. Land in pale wash, India in green, corridors
   coloured by their live risk band, cargo moving along them at a walking pace.
   No neon, no bloom, no starfield. It rotates slowly and it stops when the
   viewer has asked the operating system for less motion.
*/

const Globe = {
  canvas: null, ctx: null, land: null, ready: false,
  rot: [-68, -12], raf: null, t0: performance.now(),

  async init(canvas) {
    this.canvas = canvas;
    if (!canvas || typeof d3 === 'undefined') return;
    const dpr = window.devicePixelRatio || 1;
    const w = canvas.clientWidth || 380, h = canvas.clientHeight || 240;
    canvas.width = w * dpr; canvas.height = h * dpr;
    this.ctx = canvas.getContext('2d');
    this.ctx.scale(dpr, dpr);
    this.w = w; this.h = h;

    this.projection = d3.geoOrthographic()
      .scale(Math.min(w, h) / 2 - 8)
      .translate([w / 2, h / 2])
      .clipAngle(90);
    this.path = d3.geoPath(this.projection, this.ctx);

    try {
      const res = await fetch('https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json');
      const topo = await res.json();
      this.land = topojson.feature(topo, topo.objects.countries);
      this.india = this.land.features.find(f => f.id === '356');
      this.ready = true;
    } catch (e) {
      this.ready = true;   // globe still renders: sphere, graticule, corridors
    }

    this.graticule = d3.geoGraticule10();
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    this.spin = !reduced;
    this.loop();
  },

  corridors() {
    const s = STORE.situation;
    if (!s) return [];
    return s.corridors.map(c => ({
      pts: c.waypoints.map(p => [p[1], p[0]]),   // [lon, lat] for d3
      colour: UI.bandColour(c.band),
      score: c.score,
      blocked: STORE.scenario
        ? (STORE.scenario.corridor_capacity?.[c.corridor_id] ?? 1) < 0.5
        : false
    }));
  },

  densify(pts) {
    /* Great-circle interpolation, so a corridor bends the way a ship actually sails. */
    const out = [];
    for (let i = 0; i < pts.length - 1; i++) {
      const interp = d3.geoInterpolate(pts[i], pts[i + 1]);
      for (let k = 0; k < 12; k++) out.push(interp(k / 12));
    }
    out.push(pts.at(-1));
    return out;
  },

  loop() {
    const draw = () => {
      const t = (performance.now() - this.t0) / 1000;
      if (this.spin) this.rot[0] = -68 + t * 1.6;
      this.projection.rotate(this.rot);
      this.render(t);
      this.raf = requestAnimationFrame(draw);
    };
    draw();
  },

  render(t) {
    const ctx = this.ctx, path = this.path;
    if (!ctx) return;
    ctx.clearRect(0, 0, this.w, this.h);

    /* ocean */
    ctx.beginPath(); path({ type: 'Sphere' });
    const g = ctx.createRadialGradient(this.w * 0.42, this.h * 0.36, 10,
                                       this.w / 2, this.h / 2, this.w * 0.55);
    g.addColorStop(0, '#F4F9F6'); g.addColorStop(1, '#DFEAE3');
    ctx.fillStyle = g; ctx.fill();

    /* graticule */
    ctx.beginPath(); path(this.graticule);
    ctx.strokeStyle = 'rgba(31,111,67,.10)'; ctx.lineWidth = 0.5; ctx.stroke();

    /* land */
    if (this.land) {
      ctx.beginPath(); path(this.land);
      ctx.fillStyle = '#EFF3EF'; ctx.fill();
      ctx.strokeStyle = '#D6E1D9'; ctx.lineWidth = 0.5; ctx.stroke();
      if (this.india) {
        ctx.beginPath(); path(this.india);
        ctx.fillStyle = '#CFE3D5'; ctx.fill();
        ctx.strokeStyle = '#1F6F43'; ctx.lineWidth = 0.8; ctx.stroke();
      }
    }

    /* corridors */
    for (const c of this.corridors()) {
      const line = { type: 'LineString', coordinates: this.densify(c.pts) };
      ctx.beginPath(); path(line);
      ctx.strokeStyle = c.colour;
      ctx.globalAlpha = c.blocked ? 0.3 : 0.75;
      ctx.lineWidth = 1.5;
      ctx.setLineDash(c.blocked ? [3, 3] : []);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.globalAlpha = 1;

      /* cargo in motion — one dot per corridor, deliberately slow */
      if (!c.blocked) {
        const dense = this.densify(c.pts);
        for (let k = 0; k < 2; k++) {
          const f = ((t * 0.035) + k * 0.5) % 1;
          const idx = Math.floor(f * (dense.length - 1));
          const p = this.projection(dense[idx]);
          if (!p) continue;
          const visible = d3.geoDistance(dense[idx], [-this.rot[0], -this.rot[1]]) < Math.PI / 2;
          if (!visible) continue;
          ctx.beginPath(); ctx.arc(p[0], p[1], 2.1, 0, 2 * Math.PI);
          ctx.fillStyle = c.colour; ctx.fill();
          ctx.beginPath(); ctx.arc(p[0], p[1], 4.2, 0, 2 * Math.PI);
          ctx.strokeStyle = c.colour; ctx.globalAlpha = 0.25; ctx.stroke();
          ctx.globalAlpha = 1;
        }
      }
    }

    /* rim */
    ctx.beginPath(); path({ type: 'Sphere' });
    ctx.strokeStyle = 'rgba(18,40,31,.18)'; ctx.lineWidth = 0.8; ctx.stroke();
  },

  destroy() { if (this.raf) cancelAnimationFrame(this.raf); }
};
