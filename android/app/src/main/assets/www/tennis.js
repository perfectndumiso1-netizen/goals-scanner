/* PlayReport — TENNIS (separate section). Reads the tennis scanner's own published files
   (data/app/tennis/…, tennis-data branch). Nothing here touches the football data, views or trackers;
   the football pages never read tennis data. Wording is statistical: model probability, fair odds,
   bookmaker odds, edge, data quality — never "safe" / "banker" / "lock". */
(function (PR) {
  'use strict';
  const { $, esc, state, icon, koShort } = PR;
  const TENNIS_BASE = 'https://raw.githubusercontent.com/perfectndumiso1-netizen/goals-scanner/tennis-data/';
  const T = { data: null, details: {}, view: 'highlights', loading: false, error: null, loadedAt: 0 };
  PR.tennis = T;
  const view = () => $('#view');
  if (!document.getElementById('tennis-css')) {
    const st = document.createElement('style'); st.id = 'tennis-css';
    st.textContent = `.tn-item{padding:9px 0;border-top:1px solid var(--line-2)}.tn-item:first-child{border-top:0;padding-top:4px}
.tn-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:4px;margin-top:6px}.tn-grid>div{background:var(--chip);border-radius:8px;padding:4px 2px;text-align:center;font-size:12px;font-weight:600;line-height:1.25}
.tn-grid .cap{display:block;font-size:9px;font-weight:700;color:var(--muted);letter-spacing:.3px}.tn-grid>div.hi{background:var(--accent-soft);color:var(--good)}.tn-grid>div.mid{background:var(--warn-soft);color:var(--warn)}
.tn-grid>div.neg{color:var(--bad)}.tn-grid>div.pos{color:var(--good)}`;
    document.head.appendChild(st);
  }
  const cell = (cap, val, cls) => `<div class="${cls || ''}"><span class="cap">${cap}</span>${val}</div>`;
  const edgeCls = (x) => (x == null || isNaN(x)) ? '' : x >= 0 ? 'pos' : 'neg';
  const head = (title, sub, right) => `<div class="detail-head"><button class="back" id="back" aria-label="Back">${icon('back')}</button><div class="grow"><div class="b">${title}</div>${sub ? `<div class="tiny muted">${sub}</div>` : ''}</div>${right || ''}</div>`;
  const wireBack = () => { const b = $('#back'); if (b) b.onclick = () => PR.back(); };
  const pc = (x, d) => (x == null || isNaN(x)) ? 'N/A' : (x * 100).toFixed(d == null ? 1 : d) + '%';
  const od = (x) => (x == null || isNaN(x)) ? 'N/A' : Number(x).toFixed(2);
  const pp = (x) => (x == null || isNaN(x)) ? 'N/A' : (x >= 0 ? '+' : '') + Number(x).toFixed(1) + ' pp';
  const qcls = (s) => s >= 80 ? 'hi' : s >= 60 ? 'mid' : '';
  const fmtStart = (s) => koShort((s || '').replace(' ', 'T').slice(0, 16).replace('T', ' '));
  const MARKET = { winner: 'Match winner', total_games: 'Total games', p1_games: 'Player games', p2_games: 'Player games', game_handicap: 'Game handicap' };
  /** UTC "YYYY-MM-DD HH:MM" → local (SAST by default) "Day HH:MM" */
  function localStart(s) {
    if (!s) return '';
    const m = String(s).match(/(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})/); if (!m) return s;
    const d = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5]) + (PR.settings.tzOffset || 0) * 3600000);
    return `${PR.DAYS[d.getUTCDay()]} ${String(d.getUTCHours()).padStart(2, '0')}:${String(d.getUTCMinutes()).padStart(2, '0')}`;
  }

  // ------------------------------------------------------------------ data
  T.load = async function (force) {
    if (T.loading) return;
    if (!force && T.data && Date.now() - T.loadedAt < 5 * 60000) return;
    T.loading = true; T.error = null;
    if (!T.data) { try { const c = localStorage.getItem('pr_tennis_latest'); if (c) T.data = JSON.parse(c); } catch (e) { /* ignore */ } }
    try {
      const j = await PR.getJson(TENNIS_BASE + 'data/app/tennis/latest.json?t=' + Math.floor(Date.now() / 60000));
      if (j && j.meta && j.meta.sport === 'tennis') { T.data = j; T.loadedAt = Date.now(); try { localStorage.setItem('pr_tennis_latest', JSON.stringify(j)); } catch (e) { /* quota */ } }
    } catch (e) { T.error = String(e.message || e); }
    T.loading = false;
    const top = state.stack[state.stack.length - 1]; if (top && (top.type === 'tennis' || top.type === 'tennisMatch')) PR.render();
  };
  T.detail = function (id) {
    const key = String(id);
    if (T.details[key]) return T.details[key];
    T.details[key] = { loading: true };
    PR.getJson(TENNIS_BASE + `data/app/tennis/matches/${key}.json?t=` + Math.floor(Date.now() / 60000))
      .then((j) => { T.details[key] = j; }).catch((e) => { T.details[key] = { error: String(e.message || e) }; })
      .then(() => { const top = state.stack[state.stack.length - 1]; if (top && top.type === 'tennisMatch' && String(top.id) === key) PR.render(); });
    return T.details[key];
  };

  // ------------------------------------------------------------------ list page
  PR.pages.tennis = function (page) {
    if (!T.data) T.load(false);
    const d = T.data;
    const parts = [head('🎾 Tennis Scanner', d ? `Separate from football · generated ${esc(d.meta.generated_sast)} SAST` : 'Separate from football')];
    parts.push(`<div class="card compact"><div class="tiny muted">Tennis has its own data, model, tracker and reports. Shown per match: MODEL PROBABILITY, BOOKMAKER ODDS, MARKET IMPLIED, FAIR ODDS, EDGE and DATA QUALITY. Data quality describes the evidence behind a probability — it is not a win probability.</div></div>`);
    if (!d) {
      parts.push(`<div class="card empty">${T.error ? `Tennis analysis could not be loaded (${esc(T.error)}). It is published after the first tennis scan — pull down to refresh later.` : 'Loading tennis analysis…'}</div>`);
      view().innerHTML = parts.join(''); wireBack(); return;
    }
    const meta = d.meta; const matches = d.matches || []; const hl = d.highlights || [];
    const priced = matches.filter((m) => m.odds).length;
    parts.push(`<div class="card compact"><div class="chips small-chips"><span class="chip">${matches.length} matches</span><span class="chip">${priced} priced</span><span class="chip">${hl.length} highlights</span><span class="chip">${esc(meta.coverage)}</span>${meta.tracker && meta.tracker.settled ? `<span class="chip">tracker ${meta.tracker.won}/${meta.tracker.settled} settled</span>` : ''}</div></div>`);
    parts.push(PR.segmented([['highlights', 'Highlights'], ['all', 'All matches']], T.view, 'tv'));
    if (T.view === 'highlights') {
      if (!hl.length) parts.push('<div class="card empty">No model/market disagreements meet the publication rules right now (price ≥ 1.30, model ≥ 55%, edge 5–20 pp, data quality ≥ 60, both players with 30+ rated matches).</div>');
      else parts.push(`<div class="card"><div class="tiny muted" style="margin-bottom:4px">Model above market — a disagreement flag with its evidence, not a recommendation. Confidence = data quality band.</div>
        ${hl.map((h) => `<div class="tn-item tap" data-tennis="${esc(h.match_id)}"><div class="b">${esc(h.label)}</div><div class="tiny muted">${esc(h.match)} · ${esc(h.tournament)} · ${esc(localStart(h.start))} · ${esc(MARKET[h.market] || h.market)}</div>
          <div class="tn-grid">${cell('MODEL', pc(h.model_p))}${cell('ODDS', od(h.book_odds))}${cell('IMPLIED', pc(h.implied_fair))}${cell('EDGE', pp(h.edge_pp), edgeCls(h.edge_pp))}${cell('QUALITY', h.quality + '%', qcls(h.quality))}</div></div>`).join('')}</div>`);
    } else {
      const groups = new Map();
      matches.slice().sort((a, b) => (a.tournament + a.start).localeCompare(b.tournament + b.start)).forEach((m) => { const k = `${m.category} · ${m.tournament}`; if (!groups.has(k)) groups.set(k, []); groups.get(k).push(m); });
      groups.forEach((list, k) => {
        const m0 = list[0];
        parts.push(`<div class="card"><div class="row"><div class="grow b">${esc(k)}</div><span class="chip">${esc(m0.surface || 'surface N/A')}</span><span class="chip">Bo${m0.best_of}</span></div>
          <table class="tbl">${list.map((m) => `<tr class="tap" data-tennis="${esc(m.id)}"><td><div>${esc(m.p1.name)} <span class="tiny muted">${m.p1.rating != null ? Math.round(m.p1.rating) : 'unrated'} · ${m.p1.n}m</span></div><div>${esc(m.p2.name)} <span class="tiny muted">${m.p2.rating != null ? Math.round(m.p2.rating) : 'unrated'} · ${m.p2.n}m</span></div><div class="tiny muted">${esc(localStart(m.start))}${m.qualifying ? ' · qualifying' : ''}</div></td>
            <td class="right"><div>${pc(m.p.a, 0)}</div><div>${pc(m.p.b, 0)}</div><div class="tiny muted">model</div></td>
            <td class="right"><div>${m.odds ? od(m.odds.a) : 'N/A'}</div><div>${m.odds ? od(m.odds.b) : 'N/A'}</div><div class="tiny muted">odds</div></td>
            <td class="right"><span class="pill ${qcls(m.quality.score)}">${m.quality.score}%</span><div class="tiny muted">quality</div></td></tr>`).join('')}</table></div>`);
      });
      if (!matches.length) parts.push('<div class="card empty">No ATP/WTA/Challenger singles matches in the next 36 hours.</div>');
    }
    parts.push(`<div class="card"><div class="tiny muted">${esc(meta.note || '')} ${esc(meta.licence || '')} Statistical information, not betting advice. 18+.</div></div>`);
    view().innerHTML = parts.join('');
    wireBack();
    document.querySelectorAll('[data-tv]').forEach((b) => { b.onclick = () => { T.view = b.dataset.tv; PR.render(); }; });
  };

  // ------------------------------------------------------------------ match page
  PR.pages.tennisMatch = function (page) {
    const det = T.detail(page.id);
    const slim = ((T.data && T.data.matches) || []).find((m) => String(m.id) === String(page.id));
    const title = det && det.p1 ? `${esc(det.p1.name)} v ${esc(det.p2.name)}` : slim ? `${esc(slim.p1.name)} v ${esc(slim.p2.name)}` : 'Tennis match';
    const parts = [head(title, det && det.tournament ? `${esc(det.category)} · ${esc(det.tournament)} · ${esc(det.surface || 'surface N/A')} · best of ${det.best_of} · ${esc(localStart(det.start))}` : '')];
    if (!det || det.loading) { parts.push('<div class="card empty">Loading match analysis…</div>'); view().innerHTML = parts.join(''); wireBack(); return; }
    if (det.error) { parts.push(`<div class="card empty">This analysis could not be loaded (${esc(det.error)}).</div>`); view().innerHTML = parts.join(''); wireBack(); return; }
    const p1 = det.p1, p2 = det.p2, q = det.quality || {};
    // probabilities
    parts.push(`<div class="card"><div class="row"><div class="grow b">Model probability</div><span class="pill ${qcls(q.score)}">DATA QUALITY ${q.score}%</span></div>
      <table class="tbl"><tr><td>${esc(p1.name)} <span class="tiny muted">${p1.ioc ? esc(p1.ioc) + ' · ' : ''}rating ${p1.rating != null ? Math.round(p1.rating) : 'N/A'} · ${p1.n} rated matches</span></td><td class="right b">${pc(det.p.a)}</td></tr>
      <tr><td>${esc(p2.name)} <span class="tiny muted">${p2.ioc ? esc(p2.ioc) + ' · ' : ''}rating ${p2.rating != null ? Math.round(p2.rating) : 'N/A'} · ${p2.n} rated matches</span></td><td class="right b">${pc(det.p.b)}</td></tr></table>
      <div class="tiny muted" style="margin-top:6px">Set probability ${pc(det.p.set)} · expected total ${det.games && det.games.expected_total != null ? det.games.expected_total.toFixed(1) : 'N/A'} games. P(A) + P(B) = 100%.</div></div>`);
    // set scores
    const ss = det.set_scores || {};
    parts.push(`<div class="card"><div class="b">Set scores (best of ${det.best_of})</div><table class="tbl head"><tr><th>Score</th><th>${esc(p1.name)}</th><th>${esc(p2.name)}</th></tr>
      ${Object.keys(ss).filter((k) => +k.split('-')[0] > +k.split('-')[1]).sort().map((k) => { const r = k.split('-').reverse().join('-'); return `<tr><td>${k} / ${r}</td><td>${pc(ss[k])}</td><td>${pc(ss[r])}</td></tr>`; }).join('')}</table></div>`);
    // markets
    const rows = det.markets || [];
    if (rows.length) {
      parts.push(`<div class="card"><div class="b">Markets</div><div class="tiny muted" style="margin-bottom:4px">MODEL = model probability · FAIR = 1 / model · ODDS = Sportybet price (comparison only, never a model input) · IMPLIED = bookmaker probability with the margin removed · EDGE = model − implied.</div>
        ${rows.map((r) => `<div class="tn-item"><div class="${r.flag ? 'b' : ''}">${esc(r.label)} <span class="tiny muted">· ${esc(MARKET[r.market] || r.market)}</span>${r.low_confidence ? ' <span class="chip warn">low data confidence</span>' : ''}${r.flag ? ` <span class="chip ok">${esc(r.flag)}</span>` : ''}</div>
          <div class="tn-grid">${cell('MODEL', pc(r.model_p))}${cell('FAIR', od(r.fair_odds))}${cell('ODDS', od(r.book_odds))}${cell('IMPLIED', pc(r.implied_fair))}${cell('EDGE', pp(r.edge_pp), edgeCls(r.edge_pp))}</div></div>`).join('')}</div>`);
    } else parts.push('<div class="card empty">No bookmaker prices found for this match — model probabilities only.</div>');
    // warnings
    if (det.warnings && det.warnings.length) parts.push(`<div class="card"><div class="b">Warnings</div><ul class="notes">${det.warnings.map((w) => `<li>${esc(w)}</li>`).join('')}</ul></div>`);
    // player evidence
    const pe = (p) => { const f = p.features || {}; const fm = f.form || {}; const sf = f.surface_form || {}; const sv = f.serve || {}; const rt = f.ret || {}; const pr = f.profile || {};
      const line = (o) => o && o.n ? `${o.wins}/${o.n} (${pc(o.rate, 0)})` : 'N/A';
      return `<div class="card"><div class="b">${esc(p.name)}</div><table class="tbl">
        <tr><td>Form · last 5 / 10 / 20</td><td class="right">${line(fm.last5)} · ${line(fm.last10)} · ${line(fm.last20)}</td></tr>
        <tr><td>${esc(det.surface || 'Surface')} form · last 5 / 10 / 20</td><td class="right">${line(sf.last5)} · ${line(sf.last10)} · ${line(sf.last20)}</td></tr>
        <tr><td>Serve points won<div class="tiny muted">${sv.n ? `${Math.round(sv.n)} matches with statistics, to ${esc(sv.as_of)}${sv.stale ? ' (stale)' : ''}` : 'no serve statistics'}</div></td><td class="right">${sv.spw != null ? pc(sv.spw) : 'N/A'}</td></tr>
        <tr><td>1st serve in / won · 2nd won</td><td class="right">${sv.first_in != null ? `${pc(sv.first_in, 0)} / ${pc(sv.first_won, 0)} · ${pc(sv.second_won, 0)}` : 'N/A'}</td></tr>
        <tr><td>Hold · aces / DFs per match</td><td class="right">${sv.hold != null ? pc(sv.hold, 0) : 'N/A'} · ${sv.aces_per_match != null ? sv.aces_per_match.toFixed(1) : 'N/A'} / ${sv.df_per_match != null ? sv.df_per_match.toFixed(1) : 'N/A'}</td></tr>
        <tr><td>Return points won · break points saved (on serve)</td><td class="right">${rt.rpw != null ? pc(rt.rpw) : 'N/A'} · ${sv.bp_saved != null ? pc(sv.bp_saved, 0) : 'N/A'}</td></tr>
        <tr><td>Break points converted / created per match</td><td class="right">${rt.bp_converted != null ? pc(rt.bp_converted, 0) : 'N/A'} / ${rt.bp_created_per_match != null ? rt.bp_created_per_match.toFixed(1) : 'N/A'}</td></tr>
        <tr><td>Avg games · straight sets · deciding set${pr.n ? ` <span class="tiny muted">(${pr.n})</span>` : ''}</td><td class="right">${pr.avg_total_games != null ? pr.avg_total_games.toFixed(1) : 'N/A'} · ${pr.straight_sets_share != null ? pc(pr.straight_sets_share, 0) : 'N/A'} · ${pr.deciding_set_share != null ? pc(pr.deciding_set_share, 0) : 'N/A'}</td></tr>
        <tr><td>Tiebreaks per match · record</td><td class="right">${pr.tiebreaks_per_match != null ? pr.tiebreaks_per_match.toFixed(2) : 'N/A'} · ${pr.tiebreak_record ? `${pr.tiebreak_record[0]}–${pr.tiebreak_record[1]}` : 'N/A'}</td></tr>
        </table></div>`; };
    parts.push(pe(p1), pe(p2));
    // data quality
    if (q.items) parts.push(`<div class="card"><div class="row"><div class="grow b">Data quality ${q.score}% · ${esc(q.overall)}</div></div><div class="tiny muted" style="margin-bottom:6px">Quality of the evidence, not the chance of winning.</div>
      <table class="tbl">${q.items.map((it) => `<tr><td>${esc(it.check.replace(/_/g, ' '))}</td><td><span class="chip ${it.status === 'PASS' ? 'ok' : it.status === 'FAIL' ? 'bad' : 'warn'}">${esc(it.status)}</span></td><td class="tiny muted">${esc(it.detail)}</td></tr>`).join('')}</table></div>`);
    // explanation
    if (det.explain && det.explain.steps) parts.push(`<div class="card"><div class="b">How the probability was built</div><ol class="notes">${det.explain.steps.map((s) => `<li>${esc(s)}</li>`).join('')}</ol></div>`);
    parts.push(`<div class="card"><div class="tiny muted">${esc((T.data && T.data.meta && T.data.meta.licence) || '')} Statistical information, not betting advice. 18+.</div></div>`);
    view().innerHTML = parts.join('');
    wireBack();
  };

  // taps on tennis rows (separate attribute from football's data-fx / data-team)
  document.addEventListener('click', (e) => {
    const r = e.target.closest('[data-tennis]');
    if (r) { e.preventDefault(); PR.push({ type: 'tennisMatch', id: r.dataset.tennis }); }
  });
})(window.PR);
