/* SUPATH — the operating picture.

   An AIS-style chart, but built for one question rather than for shipping in
   general: which of India's crude corridors is under strain, and where are the
   barrels right now.

   Simulated hulls are drawn hollow and labelled SIM. The platform never lets a
   simulated vessel look like a real one — that is the difference between a
   decision-support system and a demo.
*/

const SetuMap = {
  map: null,
  layers: {},
  markers: new Map(),      // mmsi -> marker
  ports: [],
  built: false,
  wired: false,
  visible: { vessels: true, corridors: true, ports: true, choke: true, density: false },
  timer: null,

  init(el) {
    if (this.map || !el || typeof L === 'undefined') return;

    this.map = L.map(el, {
      center: [17.5, 60], zoom: 4, minZoom: 2, maxZoom: 9,
      zoomControl: true, worldCopyJump: true, preferCanvas: true,
      attributionControl: true
    });

    L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
      subdomains: 'abcd', maxZoom: 19,
      attribution: '&copy; OpenStreetMap contributors &copy; CARTO'
    }).addTo(this.map);

    this.layers.density   = L.layerGroup();
    this.layers.corridors = L.layerGroup().addTo(this.map);
    this.layers.ports     = L.layerGroup().addTo(this.map);
    this.layers.choke     = L.layerGroup().addTo(this.map);
    this.layers.vessels   = L.layerGroup().addTo(this.map);

    if (!this.wired) {
      this.wired = true;
      STORE.on('situation', () => this.drawStatic());
      STORE.on('vessels', v => this.drawVessels(v));
    }

    if (STORE.situation) this.drawStatic();
    if (STORE.vessels) this.drawVessels(STORE.vessels);

    setTimeout(() => this.map.invalidateSize(), 60);
  },

  /* ---------------- static geography: corridors, ports, chokepoints ------- */

  drawStatic() {
    const s = STORE.situation;
    if (!s || !this.map) return;

    /* corridors */
    this.layers.corridors.clearLayers();
    const blocked = (STORE.vessels && STORE.vessels.blocked) || {};
    const byId = Object.fromEntries(s.corridors.map(c => [c.corridor_id, c]));

    s.corridors.forEach(c => {
      const cap = blocked[c.corridor_id];
      const scenarioActive = cap !== undefined;
      const halted = scenarioActive && cap < 0.5;
      const degraded = scenarioActive && cap >= 0.5 && cap < 0.95;

      // Outside a running scenario the line reads the everyday risk score.
      // Inside one, status wins — a corridor a scenario has blocked must read
      // as blocked regardless of what its longer-run risk band happens to be.
      let colour = UI.bandColour(c.band);
      let statusLabel = '';
      if (halted) { colour = '#A6432B'; statusLabel = ' — BLOCKED'; }
      else if (degraded) { colour = '#B07819'; statusLabel = ' — degraded'; }

      const line = L.polyline(c.waypoints, {
        color: colour,
        weight: 1.6 + (c.share_pct / 44) * 2.4,
        opacity: halted ? 0.55 : 0.8,
        dashArray: halted ? '5 6' : null,
        lineCap: 'round', lineJoin: 'round'
      });
      line.bindPopup(`
        <div class="pop-t">${UI.esc(c.short)}${statusLabel}</div>
        <div class="pop-r"><span class="k">Risk</span><span class="v" style="color:${UI.bandColour(c.band)}">${c.score} · ${c.band}</span></div>
        ${scenarioActive ? `<div class="pop-r"><span class="k">Scenario capacity</span><span class="v" style="color:${colour}">${Math.round(cap * 100)}%</span></div>` : ''}
        <div class="pop-r"><span class="k">Share of imports</span><span class="v">${c.share_pct}%</span></div>
        <div class="pop-r"><span class="k">Barrels exposed</span><span class="v">${UI.num(c.barrels_at_risk_kbd)} kb/d</span></div>
        <div class="pop-r"><span class="k">Voyage</span><span class="v">${c.voyage_days} days</span></div>
        <div style="margin-top:8px;font-size:11.5px;color:#5A6B62;line-height:1.5;max-width:250px">${UI.esc(c.why_it_matters)}</div>`);
      line.on('click', () => { STORE.set('selectedCorridor', c.corridor_id); });
      line.addTo(this.layers.corridors);

      // Reroute-flow overlay: when this corridor is throttled and has a named
      // alternate, draw a second, teal, dashed line along that alternate so the
      // diversion is visible on the map itself, not just in the vessel count.
      if (halted && c.reroute_id && byId[c.reroute_id]) {
        const alt = byId[c.reroute_id];
        L.polyline(alt.waypoints, {
          color: '#1E7A8C', weight: 2.4, opacity: 0.55, dashArray: '2 7',
          lineCap: 'round', lineJoin: 'round'
        }).bindPopup(`
          <div class="pop-t">Reroute flow: ${UI.esc(c.short)} → ${UI.esc(alt.short)}</div>
          <div style="font-size:11.5px;color:#5A6B62;line-height:1.5;max-width:250px">
            Most of ${UI.esc(c.short)}'s traffic is redrawn moving along ${UI.esc(alt.short)}
            while the primary corridor is blocked.</div>`)
          .addTo(this.layers.corridors);
      }
    });

    /* live-window boundaries — exactly where VesselAPI's free-tier quota
       actually reaches, so nobody mistakes the rest of the map for live. */
    const windows = (STORE.vessels && STORE.vessels.live_windows) || [];
    windows.forEach(w => {
      L.rectangle([[w.latBottom, w.lonLeft], [w.latTop, w.lonRight]], {
        color: '#2E8FA6', weight: 1.2, opacity: 0.6, fill: false, dashArray: '3 4'
      }).bindPopup(`
        <div class="pop-t">Live window — ${UI.esc(w.label)}</div>
        <div style="font-size:11.5px;color:#5A6B62;line-height:1.5;max-width:230px">
          Real AIS contacts inside this box come from VesselAPI.com. Everything outside it
          is the corridor simulator.</div>`)
        .addTo(this.layers.corridors);
    });

    /* chokepoints */
    this.layers.choke.clearLayers();
    const seen = new Set();
    s.corridors.forEach(c => (c.chokepoints || []).forEach(k => {
      if (seen.has(k.id)) return;
      seen.add(k.id);
      const w = (s.weather && s.weather.value && s.weather.value[k.id]) || null;
      const cap = blocked[c.corridor_id];
      const halted = cap !== undefined && cap < 0.5;
      const degraded = cap !== undefined && cap >= 0.5 && cap < 0.95;
      const col = halted ? '#A6432B' : degraded ? '#B07819' : '#4C7C5C';
      L.marker([k.lat, k.lon], {
        icon: L.divIcon({
          className: '',
          iconSize: [16, 16], iconAnchor: [8, 8],
          html: `<div style="width:12px;height:12px;transform:rotate(45deg);margin:2px;
                   border:1.4px solid ${col};background:#fff;
                   box-shadow:0 1px 3px rgba(18,40,31,.18);${halted ? 'background:#FBEDE9;' : ''}"></div>`
        })
      }).bindPopup(`
        <div class="pop-t">${UI.esc(k.name)}</div>
        <div class="pop-r"><span class="k">World flow</span><span class="v">${k.world_flow_mbd} mb/d</span></div>
        <div class="pop-r"><span class="k">Sea state</span><span class="v">${w ? UI.esc(w.status) : '—'}</span></div>
        <div class="pop-r"><span class="k">Status</span><span class="v" style="color:${col}">${halted ? 'Restricted (scenario)' : 'Open'}</span></div>`)
        .addTo(this.layers.choke);
    }));

    /* Indian discharge ports, ringed by health, sized by real capacity */
    this.layers.ports.clearLayers();
    const ph = (s.port_health && s.port_health.value && s.port_health.value.ports) || {};
    const refPorts = (STORE.reference && STORE.reference.ports) || {};
    const capMax = Math.max(1, ...Object.values(refPorts)
      .filter(p => p.role === 'discharge').map(p => p.capacity_kbd || 0));
    Object.values(ph).forEach(p => {
      if (p.port === 'KANDLA') return; // stays in the data/simulation, just not drawn — too close to Jamnagar/Vadinar to read cleanly at this zoom
      const idx = p.index ?? 100;
      const col = idx >= 80 ? '#4C7C5C' : idx >= 60 ? '#B07819' : '#A6432B';
      const cap = (refPorts[p.port] && refPorts[p.port].capacity_kbd) || 0;
      const radius = 4 + Math.sqrt(cap / capMax) * 7;
      L.circleMarker([p.lat, p.lon], {
        radius, color: col, weight: 2, fillColor: '#fff', fillOpacity: 1
      }).bindPopup(`
        <div class="pop-t">${UI.esc(p.name)}</div>
        <div class="pop-r"><span class="k">Health index</span><span class="v" style="color:${col}">${UI.num(idx)}</span></div>
        <div class="pop-r"><span class="k">Capacity</span><span class="v">${UI.num(cap)} kb/d</span></div>
        <div class="pop-r"><span class="k">State</span><span class="v">${UI.esc(p.state)}</span></div>
        <div class="pop-r"><span class="k">Calls today</span><span class="v">${p.calls_today} vs ${p.calls_baseline}</span></div>
        <div class="pop-r"><span class="k">At anchorage</span><span class="v">${p.queue}</span></div>
        <div style="margin-top:8px;font-size:10.5px;color:#8B9A91;line-height:1.5;max-width:250px">${UI.esc(p.workings || '')}</div>`)
        .addTo(this.layers.ports);
    });

    this.applyVisibility();
  },

  /* ---------------- vessels ---------------------------------------------- */

  vesselIcon(v) {
    const flagTag = (v.flag && v.flag.emoji)
      ? `<span style="position:absolute;left:100%;top:50%;transform:translateY(-50%);
                      margin-left:1px;font-size:9px;line-height:1;white-space:nowrap;
                      text-shadow:0 0 2px #fff, 0 0 2px #fff">${v.flag.emoji}</span>` : '';
    if (v.unclassified) {
      // A real AIS contact we cannot confirm is a tanker — deliberately not
      // drawn as a ship. A dot, not an arrow, is the whole point.
      return L.divIcon({
        className: 'vessel-icon',
        iconSize: [9, 9], iconAnchor: [4.5, 4.5],
        html: `<div style="position:relative;width:8px;height:8px;border-radius:50%;
                 background:#2E8FA6;border:1.4px solid #fff;
                 box-shadow:0 0 0 1px #2E8FA6">${flagTag}</div>`
      });
    }
    const sim = v.mode === 'simulated';
    const col = v.rerouted ? '#1E7A8C' : v.laden ? '#1F6F43' : '#8B9A91';
    const size = v.class === 'VLCC' ? 15 : v.class === 'Suezmax' ? 13 : 11;
    return L.divIcon({
      className: 'vessel-icon',
      iconSize: [size, size], iconAnchor: [size / 2, size / 2],
      html: `<div style="position:relative;width:${size}px;height:${size}px">
               <svg width="${size}" height="${size}" viewBox="0 0 20 20"
                    style="transform:rotate(${v.heading || 0}deg);display:block">
                 <path d="M10 1 L16 18 L10 14.4 L4 18 Z"
                       fill="${sim ? 'none' : col}" stroke="${col}"
                       stroke-width="${sim ? 1.7 : 1}" stroke-linejoin="round"
                       opacity="${v.laden ? 1 : .75}"/>
               </svg>
               ${flagTag}
             </div>`
    });
  },

  drawVessels(data) {
    if (!this.map || !data) return;
    const list = data.vessels || [];
    const alive = new Set();

    list.forEach(v => {
      alive.add(v.mmsi);
      const m = this.markers.get(v.mmsi);
      if (m) {
        m.setLatLng([v.lat, v.lon]);
        m.setIcon(this.vesselIcon(v));
        m.getPopup() && m.setPopupContent(this.vesselPopup(v));
      } else {
        const mk = L.marker([v.lat, v.lon], { icon: this.vesselIcon(v), keyboard: false })
          .bindPopup(this.vesselPopup(v));
        mk.addTo(this.layers.vessels);
        this.markers.set(v.mmsi, mk);
      }
    });

    for (const [mmsi, mk] of this.markers) {
      if (!alive.has(mmsi)) { this.layers.vessels.removeLayer(mk); this.markers.delete(mmsi); }
    }

    /* density: quiet squares, off by default */
    this.layers.density.clearLayers();
    (data.density || []).forEach(d => {
      L.rectangle([[d.lat - 1, d.lon - 1], [d.lat + 1, d.lon + 1]], {
        stroke: false, fillColor: '#1F6F43',
        fillOpacity: Math.min(0.22, 0.04 + d.n * 0.025)
      }).addTo(this.layers.density);
    });

    if (STORE.situation) this.drawStatic();
  },

  vesselPopup(v) {
    if (v.unclassified) {
      return `
        <div class="pop-t">${UI.esc(v.name)}</div>
        <div class="pop-r"><span class="k">Flag</span><span class="v">${UI.flagBadge(v.flag)}</span></div>
        <div class="pop-r"><span class="k">MMSI</span><span class="v">${UI.esc(v.mmsi)}</span></div>
        <div class="pop-r"><span class="k">Speed / heading</span><span class="v">${v.speed} kt · ${Math.round(v.heading)}°</span></div>
        <div class="pop-r"><span class="k">AIS status</span><span class="v">${UI.esc(v.status)}</span></div>
        <div style="margin-top:8px">
          <span class="chip amber">LIVE · unclassified AIS contact</span>
        </div>
        <div style="margin-top:6px;font-size:11px;color:#5A6B62;line-height:1.5;max-width:230px">
          A real, live position from VesselAPI.com — but we haven't confirmed this hull is a
          crude tanker (that costs a separate request our free-tier quota doesn't cover), so
          it's shown as a plain contact, not a tanker icon. The flag is real — it's read
          straight from the MMSI, not from the same lookup.
        </div>`;
    }
    const sim = v.mode === 'simulated';
    return `
      <div class="pop-t">${UI.esc(v.name)} <span style="font-weight:400;color:#8B9A91">· ${UI.esc(v.class)}</span></div>
      <div class="pop-r"><span class="k">Flag</span><span class="v">${UI.flagBadge(v.flag)}</span></div>
      <div class="pop-r"><span class="k">Cargo</span><span class="v">${UI.num(v.cargo_kb)} kb ${UI.esc(v.grade || '')}</span></div>
      <div class="pop-r"><span class="k">Corridor</span><span class="v">${UI.esc(v.corridor_name)}${v.rerouted ? ' <span style="color:#1E7A8C">(diverted)</span>' : ''}</span></div>
      <div class="pop-r"><span class="k">Destination</span><span class="v">${UI.esc(v.destination)}</span></div>
      <div class="pop-r"><span class="k">ETA</span><span class="v">${v.eta_days != null ? v.eta_days + ' d' : '—'}</span></div>
      <div class="pop-r"><span class="k">Speed / heading</span><span class="v">${v.speed} kt · ${Math.round(v.heading)}°</span></div>
      <div class="pop-r"><span class="k">Status</span><span class="v" style="${v.rerouted ? 'color:#1E7A8C' : ''}">${UI.esc(v.status)}</span></div>
      <div style="margin-top:8px">
        ${sim ? '<span class="chip sim">SIM · corridor simulator, not a real hull</span>'
              : '<span class="chip green">LIVE · aisstream.io</span>'}
      </div>`;
  },

  /* ---------------- layers ------------------------------------------------ */

  toggle(key) {
    this.visible[key] = !this.visible[key];
    this.applyVisibility();
    return this.visible[key];
  },

  applyVisibility() {
    if (!this.map) return;
    Object.entries(this.visible).forEach(([k, on]) => {
      const layer = this.layers[k === 'choke' ? 'choke' : k];
      if (!layer) return;
      if (on && !this.map.hasLayer(layer)) this.map.addLayer(layer);
      if (!on && this.map.hasLayer(layer)) this.map.removeLayer(layer);
    });
  },

  focus(corridorId) {
    const s = STORE.situation;
    if (!s || !this.map) return;
    const c = s.corridors.find(x => x.corridor_id === corridorId);
    if (!c) return;
    this.map.fitBounds(L.latLngBounds(c.waypoints), { padding: [40, 40], maxZoom: 5 });
  },

  poll(ms = 6000) {
    clearInterval(this.timer);
    const tick = async () => {
      try { STORE.set('vessels', await API.vessels()); } catch (e) { /* keep last picture */ }
    };
    tick();
    this.timer = setInterval(tick, ms);
  }
};
