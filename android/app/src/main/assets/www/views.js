/* PlayReport — tab views: Home, Bets, Live, Matches, Days. */
(function (PR) {
  'use strict';
  const { $, $$, esc, pct, f1, f2, signed, state, settings, fx, pill, bar, koShort, koTime, dayName, toast, selLabel, selShort, selGroup,
    GROUPS, GROUP_ICON, liveVerdict, isLive, isFT, segmented, select, contactCard, matchLine, scoreBox, statusIcon, tzNow, parseLocal, ymd } = PR;
  const view = () => $('#view');
  const MK = { O15: 'Over 1.5 goals', O25: 'Over 2.5 goals', BTTS: 'Both teams to score' };

  // ------------------------------------------------------------------ live data (shared by Live tab, Home strip, match page)
  const live = PR.live;
  live.for = (f) => f && f.livescore_id ? state.live[f.livescore_id] : null;
  live.tracked = function () {
    const d = state.data; const ids = new Set(d.tracked || []);
    return (d.fixtures || []).filter((f) => ids.has(f.id)).sort((a, b) => a.kickoff.localeCompare(b.kickoff));
  };
  live.refresh = async function (manual) {
    const d = state.data; if (!d) return;
    const tracked = live.tracked().filter((f) => f.livescore_id);
    if (!tracked.length) return;
    const now = tzNow(); const days = new Set(tracked.map((f) => f.kickoff.slice(0, 10))); days.add(ymd(now));
    const want = new Set(tracked.map((f) => f.livescore_id));
    const goalEvents = [];
    for (const day of days) {
      try {
        const j = await PR.getJson(`https://prod-public-api.livescore.com/v1/api/app/date/soccer/${day.replace(/-/g, '')}/${settings.tzOffset}?MD=1`);
        (j.Stages || []).forEach((st) => (st.Events || []).forEach((e) => {
          const eid = String(e.Eid); if (!want.has(eid)) return;
          const prev = state.live[eid];
          const ns = !e.Eps || e.Eps === 'NS'; const cur = { status: e.Eps || '', hg: !ns && e.Tr1 != null && e.Tr1 !== '' ? +e.Tr1 : null, ag: !ns && e.Tr2 != null && e.Tr2 !== '' ? +e.Tr2 : null, ht: [e.Trh1, e.Trh2], t: Date.now() };
          state.live[eid] = cur;
          if (prev && prev.hg != null && cur.hg != null && (cur.hg + cur.ag) > (prev.hg + prev.ag)) goalEvents.push(eid);
        }));
      } catch (e) { if (manual) toast('Live scores unavailable (' + e.message + ')'); }
    }
    state.lastLive = Date.now();
    for (const f of tracked) {
      const s = state.live[f.livescore_id]; if (!s || s.hg == null || (s.hg + s.ag) === 0) continue;
      const key = `${s.hg}-${s.ag}`; const c = state.incidents[f.livescore_id]; if (c && c.key === key) continue;
      try {
        const j = await PR.getJson(`https://prod-public-api.livescore.com/v1/api/app/incidents/soccer/${f.livescore_id}`);
        const items = [];
        Object.values(j.Incs || {}).forEach((lst) => lst.forEach((x) => { [x].concat(x.Incs || []).forEach((y) => {
          const t = { 36: 'goal', 37: 'own goal', 39: 'penalty', 40: 'missed penalty', 43: 'yellow', 44: 'second yellow', 45: 'red' }[y.IT];
          if (!t) return; items.push({ min: y.Min, team: y.Nm === 1 ? 'H' : 'A', type: t, player: y.Pn || [y.Fn, y.Ln].filter(Boolean).join(' '), score: y.Sc });
        }); }));
        items.sort((a, b) => (a.min || 0) - (b.min || 0));
        state.incidents[f.livescore_id] = { key, items };
      } catch (e) { /* ignore */ }
    }
    const top = state.stack[state.stack.length - 1];
    if ((state.tab === 'live' || state.tab === 'home') && !top) PR.render();
    if (top && top.type === 'match') PR.render();
    goalEvents.forEach(announceGoal);
  };
  function announceGoal(eid) {
    if (!settings.goalAlerts) return;
    const f = live.tracked().find((x) => x.livescore_id === eid); const s = state.live[eid]; if (!f || !s) return;
    const inc = state.incidents[eid]; const goals = inc ? inc.items.filter((it) => ['goal', 'own goal', 'penalty'].includes(it.type)) : [];
    const last = goals.length ? goals[goals.length - 1] : null;
    const scorer = last ? `${last.player || ''} ${last.min != null ? last.min + "'" : ''}${last.type !== 'goal' ? ' (' + last.type + ')' : ''}`.trim() : '';
    const title = `⚽ GOAL  ${f.home_long || f.home} ${s.hg} – ${s.ag} ${f.away_long || f.away}`;
    const text = (scorer ? scorer + ' · ' : '') + `${s.status} · ${f.competition}`;
    if (PR.native && PR.native.notifyGoal) PR.native.notifyGoal(eid, `${s.hg}-${s.ag}`, title, text); else toast(title);
  }
  live.schedule = function () {
    clearInterval(state.liveTimer);
    state.liveTimer = setInterval(() => {
      if (document.hidden || !state.data) return;
      const top = state.stack[state.stack.length - 1];
      if (!(state.tab === 'live' || state.tab === 'home' || (top && top.type === 'match'))) return;
      const now = tzNow();
      const active = live.tracked().some((f) => { const s = live.for(f); const ko = parseLocal(f.kickoff); return isLive(s) || (ko && !isFT(s) && Math.abs(now - ko) < 3 * 3600 * 1000); });
      if (active) live.refresh(false);
    }, Math.max(20, settings.liveEvery) * 1000);
  };
  live.inPlay = () => live.tracked().filter((f) => isLive(live.for(f)));

  // ------------------------------------------------------------------ bets helpers
  function safeBets(minP, minOdds, group) {
    const out = [];
    (state.data.fixtures || []).forEach((f) => { if (!f.data_ok) return; f.sels.forEach((s) => {
      if (!s.odds || s.odds < minOdds || s.p < minP || s.diff) return;
      if (group && group !== 'all' && selGroup(s.sel) !== group) return;
      out.push({ f, s });
    }); });
    out.sort((a, b) => b.s.p - a.s.p || b.s.odds - a.s.odds);
    return out;
  }
  function highProb(minP, group) {
    const out = [];
    (state.data.fixtures || []).forEach((f) => { if (!f.data_ok) return; f.sels.forEach((s) => {
      if (s.p < minP) return; if (group && group !== 'all' && selGroup(s.sel) !== group) return; out.push({ f, s });
    }); });
    out.sort((a, b) => b.s.p - a.s.p);
    return out;
  }
  function betRow({ f, s }, showMatch) {
    const sel = esc(selLabel(s.sel, f.home, f.away));
    const main = showMatch === false
      ? `<div class="b">${sel}</div><div class="tiny muted">${esc(GROUPS[selGroup(s.sel)])}${s.diff ? ' · <span class="warn">views differ</span>' : ''}</div>`
      : `<div class="match">${esc(f.home)} <span class="muted">v</span> ${esc(f.away)}</div><div class="sel"><b>${sel}</b></div><div class="tiny muted">${esc(koShort(f.kickoff))} · ${esc(f.competition)}${s.diff ? ' · <span class="warn">views differ</span>' : ''}</div>`;
    return `<tr class="tap" data-fx="${esc(f.id)}">${showMatch === false ? `<td class="tiny muted nowrap">${esc(koShort(f.kickoff))}</td>` : ''}<td>${main}</td>
      <td class="right nowrap">${s.odds ? `<b>${f2(s.odds)}</b>` : '<span class="muted">–</span>'}</td><td class="right">${pill(s.p, 0.8, 0.7)}</td></tr>`;
  }
  function trebleCard(t, i, opts) {
    opts = opts || {};
    const legs = t.legs.map((l) => { const f = fx(l.fixture); const s = f && live.for(f); const v = opts.live ? liveVerdict(l.sel, s) : null;
      return `<tr class="tap" data-fx="${esc(l.fixture)}"><td class="tiny muted nowrap">${esc(koShort(l.kickoff))}</td>
        <td><div class="b">${esc(l.home)} v ${esc(l.away)}</div><div class="tiny muted">${esc(l.league || '')}</div><div class="sel">${esc(l.label || selLabel(l.sel, l.home, l.away))}</div>${v ? `<div class="verdict ${v.cls}">${v.text}</div>` : ''}</td>
        <td class="right"><b>${f2(l.odds)}</b><div class="tiny muted">${pct(l.p)}</div></td></tr>`; }).join('');
    const st = opts.live ? multiVerdict(t.legs) : null;
    return `<div class="card acca"><div class="row"><div class="grow"><span class="chip brand">Treble ${i + 1}</span> <b>odds ${f2(t.odds)}</b> <span class="muted small">· win ${pct(t.p)}</span></div>${st ? `<span class="chip ${st.cls}">${st.text}</span>` : (t.id ? `<span class="tiny muted">${esc(t.id)}</span>` : '')}</div>
      <table class="tbl legs">${legs}</table></div>`;
  }
  function multiVerdict(legs) {
    let lost = false, allFt = true, started = false;
    legs.forEach((l) => { const s = live.for(fx(l.fixture)); if (!s || s.status === 'NS' || s.hg == null) { allFt = false; return; } started = true; if (!isFT(s)) allFt = false; const v = liveVerdict(l.sel, s); if (v.text === '❌ lost') lost = true; });
    if (lost) return { cls: 'bad', text: 'LOST' }; if (allFt && started) return { cls: 'good', text: 'WON' };
    return started ? { cls: 'warn', text: 'in play' } : { cls: '', text: 'pending' };
  }
  function parlayCard(p, i, isLiveView) {
    const st = isLiveView ? multiVerdict(p.legs) : null;
    const rows = p.legs.map((l) => { const f = fx(l.fixture); const v = isLiveView ? liveVerdict(l.sel, live.for(f)) : null;
      const flag = (l.edge != null && l.edge > 0.08) ? ' <span class="chip warn">price moved</span>' : '';
      return `<tr class="tap" data-fx="${esc(l.fixture)}"><td class="tiny muted nowrap">${esc(koShort(l.kickoff))}</td>
        <td><div class="b">${esc(l.home)} v ${esc(l.away)}</div><div class="tiny muted">${esc(l.competition || '')}</div><div class="sel">${esc(l.label || selLabel(l.sel, l.home, l.away))} <span class="muted tiny">· ${pct(l.p)} · fair ${f2(l.fair)}</span>${flag}</div>${v ? `<div class="verdict ${v.cls}">${v.text}</div>` : ''}</td>
        <td class="right"><b>${f2(l.odds)}</b></td></tr>`; }).join('');
    return `<div class="card acca"><div class="row"><div class="grow"><span class="chip">Parlay ${i + 1}</span> <b>odds ${f2(p.odds)}</b> <span class="muted small">· win ${pct(p.p)} · exp. ${signed(p.ev)}</span></div>${st ? `<span class="chip ${st.cls}">${st.text}</span>` : `<span class="tiny muted">${esc(p.id || '')}</span>`}</div>
      <table class="tbl legs">${rows}</table><div class="tiny muted" style="margin-top:4px">Prices: ${esc(p.source || '')}${p.extended ? ' · whole 24 h window' : ''}</div></div>`;
  }
  PR.betRow = betRow; PR.trebleCard = trebleCard; PR.parlayCard = parlayCard; PR.safeBets = safeBets;

  // ------------------------------------------------------------------ HOME
  PR.views.home = function () {
    const d = state.data, m = d.meta, sf = d.safe || { bets: [], trebles: [] }; const parts = [];
    const inPlay = live.inPlay();
    const priced = d.fixtures.filter((f) => f.sportybet).length;
    parts.push(`<div class="card hero"><div class="row"><div class="grow"><div class="tiny muted">LATEST ANALYSIS</div><div class="b">${esc(dayName(m.generated))} · ${esc(koTime(m.generated))} ${esc(m.tz)}</div>
      <div class="tiny muted">Next update ${esc(koShort(m.next_run || ''))} · window to ${esc(koShort(m.window_end))}</div></div>
      <div class="hero-nums"><div><b>${m.fixtures}</b><span>matches</span></div><div><b>${priced}</b><span>priced</span></div><div><b>${sf.bets.length}</b><span>safe bets</span></div></div></div>
      ${inPlay.length ? `<div class="live-strip" data-tab-go="live"><span class="status-dot live"></span><b>${inPlay.length} match${inPlay.length > 1 ? 'es' : ''} in play</b> · ${inPlay.slice(0, 2).map((f) => { const s = live.for(f); return `${esc(f.home)} ${s.hg}–${s.ag} ${esc(f.away)}`; }).join(' · ')}${inPlay.length > 2 ? ' …' : ''} ›</div>` : ''}</div>`);
    // safest trebles
    parts.push(`<div class="section-head"><h2>🔒 Safest trebles</h2><button class="link" data-bets="trebles">Details ›</button></div>`);
    if (!sf.trebles.length) parts.push(`<div class="card empty small">No treble met the safety rules in this window.</div>`);
    else parts.push(`<div class="card compact">${sf.trebles.map((t, i) => `<div class="treble-row"><div class="row"><div class="grow"><b>Treble ${i + 1}</b> <span class="muted small">· win ${pct(t.p)}</span></div><span class="chip brand">odds ${f2(t.odds)}</span></div>
      ${t.legs.map((l) => `<div class="leg tap" data-fx="${esc(l.fixture)}"><span class="tiny muted nowrap">${esc(koShort(l.kickoff))}</span> <span class="grow">${esc(l.home)} v ${esc(l.away)} — <b>${esc(l.label || selLabel(l.sel, l.home, l.away))}</b></span><span class="price">${f2(l.odds)}</span></div>`).join('')}</div>`).join('')}</div>`);
    // safest bets top 5
    parts.push(`<div class="section-head"><h2>🎯 Safest bets</h2><button class="link" data-bets="safest">All ${sf.bets.length} ›</button></div>`);
    if (!sf.bets.length) parts.push(`<div class="card empty small">Nothing priced at ≥ ${f2(sf.min_odds || 1.3)} reached ${pct(sf.min_p || 0.7)} on both views.</div>`);
    else parts.push(`<div class="card compact"><table class="tbl">${sf.bets.slice(0, 5).map((b) => `<tr class="tap" data-fx="${esc(b.fixture)}"><td class="tiny muted nowrap">${esc(koTime(b.kickoff))}</td><td><div class="b">${esc(b.home)} v ${esc(b.away)}</div><div class="tiny muted">${esc(b.label)}</div></td><td class="right"><b>${f2(b.odds)}</b></td><td class="right">${pill(b.p, 0.8, 0.7)}</td></tr>`).join('')}</table></div>`);
    // shortlist + parlays summary
    const pk = d.picks || {};
    parts.push(`<div class="card compact"><div class="row" style="flex-wrap:wrap"><div class="grow b">Today's shortlists & parlays</div></div>
      <div class="chips">${['O15', 'O25', 'BTTS'].map((k) => `<button class="chip tapchip" data-bets="picks">${esc(MK[k])} <b>${(pk[k] || []).length}</b></button>`).join('')}<button class="chip tapchip" data-bets="parlays">Parlays 2.70–3.50 <b>${(d.parlays || []).length}</b></button><button class="chip tapchip" data-bets="high">Markets ≥ 70% ›</button></div></div>`);
    // next kick-offs
    const now = tzNow(); const upcoming = d.fixtures.filter((f) => { const ko = parseLocal(f.kickoff); return ko && ko > now - 2 * 3600000; }).sort((a, b) => a.kickoff.localeCompare(b.kickoff)).slice(0, 6);
    parts.push(`<div class="section-head"><h2>📅 Next kick-offs</h2><button class="link" data-tab-go="matches">All matches ›</button></div><div class="card compact">${upcoming.map((f) => { const s = live.for(f); const best = f.sels.filter((x) => x.odds && x.odds >= 1.3 && !x.diff)[0];
      return `<div class="list-item tap" data-fx="${esc(f.id)}"><div class="ko">${esc(koShort(f.kickoff))}</div><div class="main"><div class="match">${esc(f.home)} <span class="muted">v</span> ${esc(f.away)}</div><div class="meta">${esc(f.competition)}${best ? ` · ${esc(selShort(best.sel))} ${pct(best.p)}` : ''}</div></div>${s && s.hg != null ? `<div class="nums"><div class="score">${s.hg} – ${s.ag}</div><div class="minute ${isFT(s) ? 'ft' : ''}">${esc(s.status)}</div></div>` : `<div class="nums"><span class="pill ${f.p.O25 >= 0.6 ? 'hi' : ''}">O2.5 ${pct(f.p.O25)}</span></div>`}</div>`; }).join('') || '<div class="empty small">No upcoming matches in the window.</div>'}</div>`);
    parts.push(contactCard(true));
    view().innerHTML = parts.join('');
    wireCommon();
  };
  function wireCommon() {
    $$('[data-bets]').forEach((b) => { b.onclick = (e) => { e.stopPropagation(); state.betsView = b.dataset.bets; PR.setTab('bets'); }; });
    $$('[data-tab-go]').forEach((b) => { b.onclick = (e) => { e.stopPropagation(); PR.setTab(b.dataset.tabGo); }; });
  }

  // ------------------------------------------------------------------ BETS
  PR.views.bets = function () {
    const d = state.data; const parts = [];
    const v = state.betsView || 'safest';
    parts.push(`<div class="card compact sticky-ish">${segmented([['safest', '🎯 Safest'], ['trebles', '🔒 Trebles'], ['high', '📈 ≥70%'], ['parlays', '🎟️ Parlays'], ['picks', '⭐ Shortlist']], v, 'bv')}</div>`);
    if (v === 'safest') renderSafest(parts);
    else if (v === 'trebles') renderTrebles(parts);
    else if (v === 'high') renderHigh(parts);
    else if (v === 'parlays') renderParlays(parts);
    else renderPicks(parts);
    view().innerHTML = parts.join('');
    $$('[data-bv]').forEach((b) => { b.onclick = () => { state.betsView = b.dataset.bv; PR.render(); window.scrollTo(0, 0); }; });
    const mp = $('#f-minp'); if (mp) mp.onchange = (e) => { settings.minP = +e.target.value; PR.saveSettings(); PR.render(); };
    const mo = $('#f-minodds'); if (mo) mo.onchange = (e) => { settings.minOdds = +e.target.value; PR.saveSettings(); PR.render(); };
    const mg = $('#f-group'); if (mg) mg.onchange = (e) => { state.betGroup = e.target.value; PR.render(); };
    const hp = $('#f-hip'); if (hp) hp.onchange = (e) => { settings.hiP = +e.target.value; PR.saveSettings(); PR.render(); };
    $$('[data-more]').forEach((b) => { b.onclick = () => { state.expanded[b.dataset.more] = true; PR.render(); }; });
  };
  const groupOptions = [['all', 'All markets']].concat(Object.entries(GROUPS));
  function renderSafest(parts) {
    const sf = state.data.safe || {}; const lst = safeBets(settings.minP, settings.minOdds, state.betGroup);
    parts.push(`<div class="card compact"><div class="filters"><label>Min probability ${select('f-minp', [[0.7, '70%'], [0.75, '75%'], [0.8, '80%'], [0.85, '85%'], [0.9, '90%']], settings.minP)}</label>
      <label>Min price ${select('f-minodds', [[1.01, 'any'], [1.1, '1.10'], [1.2, '1.20'], [1.3, '1.30'], [1.4, '1.40'], [1.5, '1.50']], settings.minOdds)}</label>
      <label>Market ${select('f-group', groupOptions, state.betGroup || 'all')}</label></div>
      <div class="tiny muted">Probability = average of the calibrated model and the de-margined Sportybet price; selections where the two views disagree by more than 12 points are hidden. The default rules (≥ ${pct(sf.min_p || 0.7)}, price ≥ ${f2(sf.min_odds || 1.3)}) are the graded "safest bets" you can follow in Days.</div></div>`);
    if (!lst.length) parts.push(`<div class="card empty">No selection matches these filters.</div>`);
    else {
      const max = state.expanded.safest ? lst.length : 30;
      parts.push(`<div class="card compact"><table class="tbl head"><tr><th>Match · selection</th><th class="right">Price</th><th class="right">Prob.</th></tr>${lst.slice(0, max).map((x) => betRow(x)).join('')}</table>
        ${lst.length > max ? `<button class="btn wide" data-more="safest">Show all ${lst.length}</button>` : ''}</div>`);
    }
    const ss = (sf.summary || {}).bets || {};
    if (ss.all && ss.all.n) parts.push(`<div class="card small"><b>Track record</b> — safest bets settled: ${ss.all.won}/${ss.all.n} hit (${pct(ss.all.rate)}, expected ${pct(ss.all.exp_rate)}) · flat-stake return ${signed(ss.all.roi)}${ss['30d'] && ss['30d'].n ? ` · last 30 days ${ss['30d'].won}/${ss['30d'].n}` : ''}</div>`);
  }
  function renderTrebles(parts) {
    const sf = state.data.safe || { trebles: [] };
    parts.push(`<div class="card small"><b>Safest trebles</b> — three 3-leg accumulators from the safest priced selections (≥ ${pct(sf.min_p || 0.7)} on both views, price ≥ ${f2(sf.min_odds || 1.3)}), one leg per match, no match repeated, ranked by probability.${sf.extended ? ' Legs come from the whole 24 h window (too few before the next update).' : ''}</div>`);
    if (!sf.trebles.length) parts.push(`<div class="card empty">No treble possible: fewer than three priced matches met the rules.</div>`);
    sf.trebles.forEach((t, i) => parts.push(trebleCard(t, i, { live: true })));
    const sa = (sf.summary || {}).accas || {};
    if (sa.all && sa.all.n) parts.push(`<div class="card small"><b>Track record</b> — trebles settled: ${sa.all.won}/${sa.all.n} won (${pct(sa.all.rate)}, expected ${pct(sa.all.exp_rate)}) · return ${signed(sa.all.roi)} per unit${sa.pending ? ` · ${sa.pending} pending` : ''}</div>`);
    parts.push(`<div class="note">A treble at ~2.2 needs to win about 45% of the time to break even. Three legs at 74% each give roughly 40%: safe legs, but still a bet with a cost. Everything here is graded automatically — check the Days tab before trusting it.</div>`);
  }
  function renderHigh(parts) {
    const minP = settings.hiP || 0.7; const lst = highProb(minP, state.betGroup);
    parts.push(`<div class="card compact"><div class="filters"><label>Probability ≥ ${select('f-hip', [[0.7, '70%'], [0.75, '75%'], [0.8, '80%'], [0.85, '85%'], [0.9, '90%']], minP)}</label><label>Market ${select('f-group', groupOptions, state.betGroup || 'all')}</label></div>
      <div class="tiny muted">Every modelled selection at or above the threshold, grouped by market — including ones without a Sportybet price (shown as –) and very short prices. For bets worth placing use the Safest view.</div></div>`);
    const groups = {};
    lst.forEach((x) => { (groups[selGroup(x.s.sel)] = groups[selGroup(x.s.sel)] || []).push(x); });
    Object.keys(GROUPS).forEach((g) => {
      const items = groups[g]; if (!items) return;
      const key = 'high_' + g; const max = state.expanded[key] ? items.length : 12;
      parts.push(`<div class="card compact"><div class="row"><div class="grow"><b>${GROUP_ICON[g]} ${GROUPS[g]}</b></div><span class="chip">${items.length}</span></div>
        <table class="tbl">${items.slice(0, max).map((x) => betRow(x)).join('')}</table>${items.length > max ? `<button class="btn wide" data-more="${key}">Show all ${items.length}</button>` : ''}</div>`);
    });
    if (!lst.length) parts.push(`<div class="card empty">Nothing at or above ${pct(minP)} for this market.</div>`);
  }
  function renderParlays(parts) {
    const d = state.data, m = d.meta;
    parts.push(`<div class="card small"><b>Parlays</b> — value-seeking accumulators (odds ${m.parlay_band && m.parlay_band.length ? m.parlay_band.map(f2).join('–') : '2.70–3.50'}) from 1X2, double chance and Over/Under 2.5 at real prices; each maximises probability × price. Riskier than the safest trebles by design.</div>`);
    if (!d.parlays.length) parts.push(`<div class="card empty">No parlay possible in this window.</div>`);
    d.parlays.forEach((p, i) => parts.push(parlayCard(p, i, true)));
    parts.push(`<div class="note">⚠️ Honest expectation: a parlay at ~3.1 must win about 1 in 3 to break even. In the 2023–26 backtest this construction won 30–33% and returned −4% to −13% per unit. Treat parlays as entertainment with a known cost.</div>`);
    const ps = d.parlay_summary || {}; const a = ps.all || {};
    if (a.n) parts.push(`<div class="card small"><b>Track record</b> — ${a.won}/${a.n} won (${pct(a.rate)}, expected ${pct(a.exp_rate)}) · return ${signed(a.roi)} · ${ps.pending || 0} pending. Full list under ☰ › Performance.</div>`);
  }
  function renderPicks(parts) {
    const d = state.data, m = d.meta;
    for (const mk of ['O15', 'O25', 'BTTS']) {
      const lst = d.picks[mk] || [];
      parts.push(`<div class="card compact"><div class="row"><div class="grow"><b>${MK[mk]}</b> <span class="muted small">· threshold ${pct(m.thresholds[mk])}</span></div><span class="chip">${lst.length}</span></div>`);
      if (!lst.length) parts.push(`<div class="muted small">None met the criteria.</div>`);
      else parts.push(`<table class="tbl">${lst.map((p) => { const f = fx(p.fixture); if (!f) return ''; return `<tr class="tap" data-fx="${esc(f.id)}"><td class="tiny muted nowrap">${esc(koShort(f.kickoff))}</td><td><div class="b">${esc(f.home)} v ${esc(f.away)}</div><div class="tiny muted">${esc(f.competition)}</div></td><td class="right">${p.sportybet ? `<b>${f2(p.sportybet)}</b>` : '<span class="muted">–</span>'}</td><td class="right">${pill(p.p, 0.7, 0.6)}<div class="stars">${esc(p.stars)}</div></td></tr>`; }).join('')}</table>`);
      parts.push(`<div class="tiny muted" style="margin-top:6px">Backtest: ${esc(m.backtest[mk] || '')}</div></div>`);
    }
    const t = d.tracker || {};
    parts.push(`<div class="card"><b>Shortlist tracker</b><table class="tbl head" style="margin-top:6px"><tr><th>Market</th><th class="right">Settled</th><th class="right">Hit</th><th class="right">30d</th><th class="right">Pending</th></tr>${['O15', 'O25', 'BTTS'].map((mk) => { const s = t[mk] || {}; return `<tr><td>${MK[mk]}</td><td class="right">${s.settled || 0}</td><td class="right">${pct(s.rate)}</td><td class="right">${pct(s.recent_rate)}</td><td class="right">${s.pending || 0}</td></tr>`; }).join('')}</table></div>`);
  }

  // ------------------------------------------------------------------ LIVE
  PR.views.live = function () {
    const d = state.data; const tracked = live.tracked(); const parts = []; const v = state.liveView || 'matches';
    const nLive = tracked.filter((f) => isLive(live.for(f))).length;
    parts.push(`<div class="card row compact"><div class="grow small"><span class="status-dot ${nLive ? 'live' : ''}"></span>${tracked.length} tracked match${tracked.length === 1 ? '' : 'es'} · ${nLive} in play${state.lastLive ? ' · updated ' + new Date(state.lastLive).toTimeString().slice(0, 5) : ''}</div><button class="btn" id="live-refresh">Refresh</button></div>`);
    const sf = d.safe || { trebles: [], bets: [] };
    const pend = (d.ledger || []).filter((p) => p.status === 'pending' && !d.parlays.some((q) => q.id === p.id));
    parts.push(`<div class="card compact">${segmented([['matches', '⚽ Matches'], ['trebles', `🔒 Trebles (${sf.trebles.length})`], ['parlays', `🎟️ Parlays (${d.parlays.length + pend.length})`]], v, 'lv')}</div>`);
    if (v === 'trebles') {
      if (!sf.trebles.length) parts.push(`<div class="card empty">No trebles in this window.</div>`);
      sf.trebles.forEach((t, i) => parts.push(trebleCard(t, i, { live: true })));
    } else if (v === 'parlays') {
      if (!d.parlays.length && !pend.length) parts.push(`<div class="card empty">No parlays in this window.</div>`);
      d.parlays.forEach((p, i) => parts.push(parlayCard(p, i, true)));
      if (pend.length) { parts.push(`<h2 class="section">Earlier parlays still open</h2>`); pend.forEach((p, i) => parts.push(parlayCard(p, i, true))); }
    } else {
      if (!tracked.length) parts.push(`<div class="card empty">Nothing to follow in this window.</div>`);
      const betsByFx = {};
      (sf.bets || []).forEach((b) => { (betsByFx[b.fixture] = betsByFx[b.fixture] || []).push({ label: b.label, sel: b.sel, odds: b.odds, kind: 'safe' }); });
      sf.trebles.forEach((t) => t.legs.forEach((l) => { (betsByFx[l.fixture] = betsByFx[l.fixture] || []).push({ label: l.label, sel: l.sel, odds: l.odds, kind: 'treble' }); }));
      d.parlays.concat(pend).forEach((p) => p.legs.forEach((l) => { (betsByFx[l.fixture] = betsByFx[l.fixture] || []).push({ label: l.label || selLabel(l.sel, l.home, l.away), sel: l.sel, odds: l.odds, kind: 'parlay' }); }));
      Object.entries(d.picks || {}).forEach(([mk, lst]) => lst.forEach((p) => { (betsByFx[p.fixture] = betsByFx[p.fixture] || []).push({ label: MK[mk], sel: mk, kind: 'pick' }); }));
      const rank = (f) => { const s = live.for(f); return isLive(s) ? 0 : isFT(s) ? 2 : 1; };
      const ordered = tracked.slice().sort((x, y) => rank(x) - rank(y) || x.kickoff.localeCompare(y.kickoff));
      let lastGroup = null; const GROUP_LABEL = ['In play', 'Upcoming', 'Finished'];
      parts.push('<div class="card compact">');
      ordered.forEach((f) => {
        const g = rank(f); if (g !== lastGroup) { parts.push(`<div class="comp-head">${GROUP_LABEL[g]}</div>`); lastGroup = g; }
        const s = live.for(f); const inc = f.livescore_id && state.incidents[f.livescore_id];
        const seen = new Set();
        const chips = (betsByFx[f.id] || []).filter((b) => { const k = b.sel + (b.kind === 'pick' ? 'p' : ''); if (seen.has(k)) return false; seen.add(k); return true; })
          .map((b) => { const vd = liveVerdict(b.sel, s); return `<span class="chip ${vd.cls}">${esc(b.label)}${b.odds ? ' @ ' + f2(b.odds) : ''} · ${esc(vd.text)}</span>`; }).join('');
        const goals = inc && g !== 1 ? inc.items.filter((it) => ['goal', 'own goal', 'penalty'].includes(it.type)) : [];
        parts.push(`<div class="list-item tap" data-fx="${esc(f.id)}"><div class="main"><div class="tiny muted">${esc(f.competition)}</div><div class="match">${esc(f.home)} <span class="muted">v</span> ${esc(f.away)}</div>
          <div class="chips">${chips}</div>${goals.length ? `<div class="tiny muted">${goals.map((it) => `⚽ ${esc(it.player || '')} ${it.min != null ? it.min + "'" : ''}${it.team === 'A' ? ' (away)' : ''}`).join(' · ')}</div>` : ''}</div>${scoreBox(s, f)}</div>`);
      });
      parts.push('</div>');
      parts.push(`<div class="tiny muted" style="padding:0 6px">Scores from a public live feed (unofficial). Auto-refresh every ${settings.liveEvery}s while a tracked match is in play. The settled results in Days are the final word.</div>`);
    }
    view().innerHTML = parts.join('');
    const b = $('#live-refresh'); if (b) b.onclick = (e) => { e.stopPropagation(); toast('Refreshing…'); live.refresh(true); };
    $$('[data-lv]').forEach((x) => { x.onclick = () => { state.liveView = x.dataset.lv; PR.render(); }; });
  };
  function incidentLine(it) {
    const ico = { goal: '⚽', 'own goal': '⚽ (og)', penalty: '⚽ (pen)', 'missed penalty': '❌ pen', yellow: '🟨', 'second yellow': '🟨🟥', red: '🟥' }[it.type] || '';
    return `${ico} ${it.min != null ? it.min + "'" : ''} ${esc(it.player || '')}${it.score ? ` <span class="muted">(${it.score[0]}–${it.score[1]})</span>` : ''}`;
  }
  PR.incidentLine = incidentLine;

  // ------------------------------------------------------------------ MATCHES
  PR.views.matches = function () {
    const d = state.data; const q = (state.search || '').toLowerCase(); const key = state.sort || 'ko';
    let lst = d.fixtures.filter((f) => !q || `${f.home} ${f.away} ${f.home_long} ${f.away_long} ${f.competition} ${f.country}`.toLowerCase().includes(q));
    const best = (f) => (f.sels.filter((x) => x.odds && x.odds >= 1.3 && !x.diff)[0] || {}).p || 0;
    lst = lst.slice().sort((a, b) => key === 'ko' ? a.kickoff.localeCompare(b.kickoff) : key === 'safe' ? best(b) - best(a) : key === 'H' ? (b.x12.H || 0) - (a.x12.H || 0) : (b.p[key] || 0) - (a.p[key] || 0));
    const parts = [`<div class="card compact"><div class="searchbar"><input id="fx-search" placeholder="Search team or league" value="${esc(state.search || '')}">
      ${select('fx-sort', [['ko', 'Kick-off'], ['safe', 'Safest first'], ['O25', 'Over 2.5'], ['O15', 'Over 1.5'], ['BTTS', 'BTTS'], ['H', 'Home win']], key)}</div></div>`];
    if (!lst.length) parts.push(`<div class="card empty">No matches found.</div>`);
    let lastDay = null;
    lst.forEach((f) => {
      const day = f.kickoff.slice(0, 10);
      if (key === 'ko' && day !== lastDay) { if (lastDay) parts.push('</div>'); parts.push(`<h2 class="section">${esc(dayName(day))}</h2><div class="card compact">`); lastDay = day; }
      else if (key !== 'ko' && !lastDay) { parts.push('<div class="card compact">'); lastDay = 'x'; }
      const s = live.for(f); const b = f.sels.filter((x) => x.odds && x.odds >= 1.3 && !x.diff)[0];
      parts.push(`<div class="list-item tap" data-fx="${esc(f.id)}"><div class="ko">${esc(koShort(f.kickoff))}</div>
        <div class="main"><div class="match">${esc(f.home)} <span class="muted">v</span> ${esc(f.away)}${f.data_ok ? '' : ' <span class="chip warn">low data</span>'}</div>
          <div class="meta">${esc(f.competition)} · xG ${f1(f.xg.home)}–${f1(f.xg.away)}${b ? ` · <b>${esc(selShort(b.sel))}</b> ${pct(b.p)} @ ${f2(b.odds)}` : ''}</div></div>
        ${s && s.hg != null ? `<div class="nums"><div class="score">${s.hg} – ${s.ag}</div><div class="minute ${isFT(s) ? 'ft' : ''}">${esc(s.status)}</div></div>` : `<div class="nums"><div class="tiny muted">O2.5 ${pill(f.p.O25, 0.6, 0.5)}</div><div class="tiny muted">BTTS ${pill(f.p.BTTS, 0.6, 0.5)}</div></div>`}</div>`);
    });
    if (lastDay) parts.push('</div>');
    view().innerHTML = parts.join('');
    $('#fx-search').oninput = (e) => { state.search = e.target.value; PR.render(); const i = $('#fx-search'); i.focus(); i.setSelectionRange(i.value.length, i.value.length); };
    $('#fx-sort').onchange = (e) => { state.sort = e.target.value; PR.render(); };
  };

  // ------------------------------------------------------------------ DAYS
  PR.views.days = function () {
    const d = state.data; const days = (d.history && d.history.days) || []; const parts = [];
    parts.push(`<div class="card small"><b>Day by day</b> — every match of each day with the final score, and how the picks, safest bets, trebles and parlays did. Days are added automatically; results fill in within a few hours of the final whistle.</div>`);
    if (!days.length) parts.push(`<div class="card empty">History starts with the next analysis.</div>`);
    const rate = (o, hitKey) => { if (!o || !o.n) return '–'; const settled = o.n - (o.pending || 0); return settled ? `${o[hitKey]}/${settled}${o.pending ? ' · ' + o.pending + ' open' : ''}` : `${o.n} open`; };
    parts.push(`<div class="card compact">${days.map((x) => `<div class="list-item tap day" data-day="${esc(x.date)}"><div class="main"><div class="match">${esc(dayName(x.date))}</div>
      <div class="meta">${x.n} matches${x.finished ? ` · ${x.finished} finished` : ''}${x.goals_avg != null ? ` · ${f1(x.goals_avg)} goals/match · O2.5 ${pct(x.o25_rate)} · BTTS ${pct(x.btts_rate)}` : ''}</div>
      <div class="chips">${x.safes && x.safes.n ? `<span class="chip ${chipCls(x.safes, 'hit')}">🎯 safest ${rate(x.safes, 'hit')}</span>` : ''}${x.accas && x.accas.n ? `<span class="chip ${chipCls(x.accas, 'won')}">🔒 trebles ${rate(x.accas, 'won')}</span>` : ''}${x.parlays && x.parlays.n ? `<span class="chip ${chipCls(x.parlays, 'won')}">🎟️ parlays ${rate(x.parlays, 'won')}</span>` : ''}${x.picks && x.picks.n ? `<span class="chip ${chipCls(x.picks, 'hit')}">⭐ picks ${rate(x.picks, 'hit')}</span>` : ''}</div></div><div class="chev">›</div></div>`).join('')}</div>`);
    view().innerHTML = parts.join('');
    $$('[data-day]').forEach((b) => { b.onclick = () => PR.push({ type: 'day', date: b.dataset.day }); });
  };
  function chipCls(o, k) { const settled = o.n - (o.pending || 0); if (!settled) return ''; const r = o[k] / settled; return r >= 0.6 ? 'good' : r <= 0.35 ? 'bad' : 'warn'; }
  PR.chipCls = chipCls;
})(window.PR);
