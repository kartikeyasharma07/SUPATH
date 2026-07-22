/* SUPATH — Decision Brief: what to do about it.

   Everything here is ranked, quantified, and cited. A recommendation that cannot
   say how many barrels it covers, what it costs, how long it takes and what it is
   based on does not belong on this page.

   One structural rule added on top of that: an action that covers zero barrels
   and moves zero risk points is preparedness, not impact, and it must not carry
   the same visual weight as one that does. They're bucketed apart on purpose.
*/

const CATEGORY = {
  REROUTE_SUPPLY: ['SOURCE', 'cat-source'],
  SPR_DRAW: ['RESERVE', 'cat-reserve'],
  PORT_CLEARANCE: ['PORT OPS', 'cat-portops'],
  DEMAND_MGMT: ['DEMAND', 'cat-demand'],
};

function categoryOf(id) {
  if (id && id.startsWith('REROUTE_') && id !== 'REROUTE_SUPPLY') return ['CORRIDOR', 'cat-corridor'];
  return CATEGORY[id] || ['ACTION', 'cat-source'];
}

const Brief = {

  render() {
    const el = document.getElementById('view-brief');
    const data = STORE.brief;
    if (!data) { el.innerHTML = UI.skeleton(500); return; }

    const b = data.brief.value;
    const allRecs = data.recommendations.value.recommendations || [];
    const impactRecs = allRecs.filter(r => r.covers_kbd || r.risk_points);
    const prepRecs = allRecs.filter(r => !impactRecs.includes(r));
    const conf = b.confidence;
    const col = UI.bandColour(data.national.band);

    el.innerHTML = `
      <div class="stack">

        <section class="call">
          <div class="row" style="justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:10px">
            <div class="eyebrow">The call${data.scenario_name ? ' · under scenario: ' + UI.esc(data.scenario_name) : ' · live world'}</div>
          </div>
          <div class="row" style="align-items:center;gap:14px;flex-wrap:wrap;margin-top:2px">
            <div class="posture">${UI.esc(b.posture)}</div>
            <span class="chip" style="background:${col};color:#fff;border-color:${col};font-size:11.5px;padding:4px 11px">${data.national.score} · ${data.national.band}</span>
          </div>
          <p class="narrative">${UI.esc(b.narrative)}</p>
          <p class="playbook"><strong>Standing playbook:</strong> ${UI.esc(b.playbook)}</p>
          <div class="row" style="margin-top:16px;gap:16px;flex-wrap:wrap">
            <div>
              <div class="tiny faint">Confidence</div>
              <div class="row" style="gap:8px">
                <div class="bar band-${conf.score >= 70 ? 'low' : conf.score >= 40 ? 'elevated' : 'high'}" style="width:110px">
                  <span style="width:${conf.score}%"></span>
                </div>
                <span class="num small">${conf.score}% · ${UI.esc(conf.label)}</span>
              </div>
            </div>
            <span class="spacer" style="flex:1"></span>
            <button class="btn primary" id="pdf-full">Situation brief (PDF)</button>
          </div>
        </section>

        <div class="stack">
          <div class="section-title">Recommended actions</div>
          ${impactRecs.length ? impactRecs.map((r, i) => this.rec(r, i + 1, false)).join('')
            : `<section class="panel"><div class="panel-body">
                 <p class="small muted" style="line-height:1.6">No corridor is scored elevated or worse and no
                 scenario is running, so SUPATH is not recommending action. Holding position is a decision, and it
                 is the right one today.</p></div></section>`}

          ${prepRecs.length ? `
            <div class="tier-divider">Prepare — no immediate barrel impact</div>
            ${prepRecs.map((r, i) => this.rec(r, impactRecs.length + i + 1, true)).join('')}
          ` : ''}

          <section class="panel">
            <div class="disclosure open">
              <button class="disclosure-head" style="padding:13px 16px">
                ${UI.chevron()}
                <span class="disclosure-title">Sources behind this brief</span>
                <span class="disclosure-meta">${b.citations.length} citation${b.citations.length === 1 ? '' : 's'}</span>
              </button>
              <div class="disclosure-body plain" style="padding:0 16px 14px">
                ${this.evidenceChips(b.citations)}
              </div>
            </div>
          </section>

        </div>
      </div>`;

    el.querySelectorAll('.rec-head').forEach(h =>
      h.addEventListener('click', () => h.closest('.rec').classList.toggle('open')));

    el.querySelectorAll('[data-goto-risk]').forEach(b2 =>
      b2.addEventListener('click', e => {
        e.stopPropagation();
        App.go('risk', { corridor: b2.dataset.gotoRisk });
      }));

    document.getElementById('pdf-full').addEventListener('click', () => window.open(API.reportURL('full'), '_blank'));
  },

  /* Deduplicate exact-URL repeats (wire-service syndication) and render as
     compact chips — publisher + date + relevance, not a raw URL block. */
  evidenceChips(citations) {
    const seen = new Set();
    const deduped = citations.filter(c => {
      const key = (c.url || '').split('?')[0].replace(/\/$/, '');
      if (key && seen.has(key)) return false;
      seen.add(key);
      return true;
    });
    const dupeCount = citations.length - deduped.length;
    return deduped.map(c => `
      <a class="evidence-link" href="${UI.esc(c.url)}" target="_blank" rel="noopener">
        ${UI.esc(c.title)}
        <span class="d">${UI.esc(c.publisher)} · used for ${UI.esc(c.used_for.toLowerCase())}</span>
      </a>`).join('')
      + (dupeCount ? `<p class="tiny faint" style="margin-top:8px">${dupeCount} duplicate wire-service link${dupeCount === 1 ? '' : 's'} collapsed.</p>` : '');
  },

  rec(r, rank, prepOnly) {
    const [catLabel, catClass] = categoryOf(r.id);
    const corridorMatch = (r.options && r.options[0] && r.options[0].corridor_id) || null;
    const corridorLabel = (r.options && r.options[0] && r.options[0].corridor) || '';
    return `
      <section class="rec ${prepOnly ? 'prep-only' : ''}">
        <button class="rec-head">
          <span class="rec-rank">${rank}</span>
          <span style="flex:1">
            <span class="cat-tag ${catClass}" style="margin-right:7px">${catLabel}</span>
            <span class="rec-title">${UI.esc(r.title)}</span>
            <span class="rec-sub">
              ${r.covers_kbd ? UI.num(r.covers_kbd) + ' kb/d covered · ' : ''}
              ${r.risk_points ? '−' + r.risk_points + ' risk points · ' : ''}
              ${r.lead_days} day lead
            </span>
          </span>
          <span class="chip">${r.cost_usd_m_day ? '$' + r.cost_usd_m_day + ' m/day' : 'no incremental cost'}</span>
        </button>
        <div class="rec-body">
          <div class="eyebrow" style="margin-bottom:5px">What to do</div>
          <p style="line-height:1.6;color:var(--ink-2);margin-bottom:14px">${UI.esc(r.action)}</p>

          <div class="rec-impact">
            ${r.covers_kbd ? `<div class="i"><div class="v">${UI.num(r.covers_kbd)}</div><div class="l">kb/d covered${r.covers_pct ? ' (' + r.covers_pct + '% of gap)' : ''}</div></div>` : ''}
            ${r.risk_points ? `<div class="i"><div class="v">−${r.risk_points}</div><div class="l">risk points</div></div>` : ''}
            <div class="i"><div class="v">${r.lead_days}</div><div class="l">days to effect</div></div>
            ${r.cost_usd_m_day ? `<div class="i"><div class="v">$${r.cost_usd_m_day}m</div><div class="l">per day</div></div>` : ''}
          </div>

          <div class="eyebrow" style="margin-bottom:5px">Why</div>
          <p style="line-height:1.6;color:var(--ink-2);margin-bottom:${r.tradeoff ? '10px' : '0'}">${UI.esc(r.why)}</p>
          ${r.tradeoff ? `
          <div class="eyebrow" style="margin-bottom:5px;color:var(--r-elev)">Trade-off</div>
          <p style="line-height:1.6;color:var(--ink-2)">${UI.esc(r.tradeoff)}</p>` : ''}
          ${r.workings ? `<div class="equation" style="margin-top:12px">${UI.esc(r.workings)}</div>` : ''}

          ${corridorMatch ? `<button class="jump-link" style="margin-top:12px" data-goto-risk="${UI.esc(corridorMatch)}">${UI.jumpIcon()} See ${UI.esc(corridorLabel)} risk derivation</button>` : ''}

          ${r.options && r.options.length ? `
            <div style="margin-top:16px">
              <div class="eyebrow" style="margin-bottom:7px">Where the barrels come from</div>
              <table class="data">
                <thead><tr><th>Supplier</th><th>Lift</th><th>Premium</th><th>Corridor</th><th>Lead</th></tr></thead>
                <tbody>${r.options.map(o => `
                  <tr>
                    <td>${UI.esc(o.supplier)}
                      <div class="tiny faint">sanctions exposure: ${UI.esc(o.sanctions_exposure)}</div></td>
                    <td class="n">${UI.num(o.lift_kbd)} kb/d</td>
                    <td class="n">${o.premium_usd >= 0 ? '+' : ''}$${o.premium_usd}/bbl</td>
                    <td class="n">${UI.esc(o.corridor)} <span class="faint">(${o.corridor_score})</span></td>
                    <td class="n">${o.lead_days} d</td>
                  </tr>`).join('')}
                </tbody>
              </table>
            </div>` : ''}

          ${r.screening && r.screening.length ? `
            <div style="margin-top:12px">
              <div class="eyebrow" style="margin-bottom:6px">Screened before recommending</div>
              <div class="row" style="flex-wrap:wrap;gap:6px">
                ${r.screening.map(s => `
                  <span class="chip ${s.clear ? 'green' : 'rust'}">${UI.esc(s.supplier)} — ${s.clear ? 'clear' : s.hits + ' hits'}
                  </span>`).join('')}
                <span class="tiny faint">against ${UI.esc(r.screening[0].checked_against)}</span>
              </div>
            </div>` : ''}

          ${r.evidence && r.evidence.length ? `
            <div style="margin-top:14px">
              <div class="eyebrow" style="margin-bottom:2px">Evidence</div>
              ${r.evidence.slice(0, 4).map(e => `
                <a class="evidence-link" href="${UI.esc(e.url)}" target="_blank" rel="noopener">
                  ${UI.esc(e.title)}<span class="d">${UI.esc(e.domain)} · ${UI.timeAgo(e.seen)}</span>
                </a>`).join('')}
            </div>` : ''}
        </div>
      </section>`;
  },

  /* ---------------- the advisor rail, present on every tab ---------------- */

  rail() {
    const body = document.getElementById('rail-body');
    const data = STORE.brief;
    if (!data) { body.innerHTML = UI.skeleton(140); return; }

    const b = data.brief.value;
    const conf = b.confidence;
    const n = data.national;
    const col = UI.bandColour(n.band);
    const allRecs = data.recommendations.value.recommendations || [];
    const top = allRecs.find(r => r.covers_kbd || r.risk_points) || allRecs[0];

    body.innerHTML = `
      <div class="eyebrow">The call</div>
      <div class="text-display" style="color:${col};margin-top:2px;font-size:21px">
        ${UI.esc(b.posture)}
      </div>
      <p class="small" style="line-height:1.6;margin-top:8px;color:var(--ink-2)">${UI.esc(b.headline)}</p>

      <div id="rail-gauge" class="gauge" style="margin-top:12px;height:26px"></div>

      <div style="margin-top:10px">
        <div class="kv"><span class="k">National risk</span><span class="v" style="color:${col}">${n.score} · ${n.band}</span></div>
        <div class="kv"><span class="k">Exposed</span><span class="v">${UI.num(n.exposed_kbd)} kb/d</span></div>
        <div class="kv"><span class="k">Strategic cover</span><span class="v">${n.spr_cover_days} days</span></div>
        <div class="kv"><span class="k">Confidence</span><span class="v">${conf.score}%</span></div>
      </div>

      ${top ? `
        <div style="margin-top:16px;padding-top:14px;border-top:1px solid var(--line)">
          <div class="eyebrow" style="margin-bottom:5px">Lead action</div>
          <div class="small" style="line-height:1.55;color:var(--ink)"><strong>${UI.esc(top.title)}</strong></div>
          <div class="tiny muted" style="margin-top:5px;line-height:1.55">${UI.esc(top.why)}</div>
          <button class="btn sm" style="margin-top:9px" data-goto="brief">Open the brief</button>
        </div>` : ''}

      <div style="margin-top:16px;padding-top:14px;border-top:1px solid var(--line)">
        <div class="eyebrow" style="margin-bottom:6px">Tripwires</div>
        ${b.tripwires.slice(0, 3).map(t => `
          <div style="padding:7px 0;border-top:1px solid var(--line)">
            <div class="small" style="color:var(--ink);line-height:1.45">${UI.esc(t.trigger)}</div>
            <div class="row" style="gap:6px;margin-top:4px">
              <div class="bar band-${UI.proximityBand(t.progress)}" style="width:38px">
                <span style="width:${Math.round((t.progress || 0) * 100)}%"></span>
              </div>
              <span class="tiny faint num">now: ${UI.esc(t.current)}</span>
            </div>
          </div>`).join('')}
      </div>

      <div style="margin-top:16px;padding-top:14px;border-top:1px solid var(--line)">
        <div class="eyebrow" style="margin-bottom:6px">Cited</div>
        ${b.citations.slice(0, 4).map(c => `
          <a class="evidence-link" href="${UI.esc(c.url)}" target="_blank" rel="noopener" style="font-size:11.5px">
            ${UI.esc(c.title.split('—')[0].trim())}<span class="d">${UI.esc(c.used_for)}</span>
          </a>`).join('')}
      </div>

      <p class="tiny faint" style="margin-top:14px;line-height:1.55">
        ${UI.esc(data.brief.method || '')}
      </p>`;

    UI.gauge(document.getElementById('rail-gauge'), n.score);

    body.querySelectorAll('[data-goto]').forEach(b2 =>
      b2.addEventListener('click', () => App.go(b2.dataset.goto)));
  }
};
