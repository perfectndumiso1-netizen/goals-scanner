/* PlayReport — stacked pages: match, team, day, analysis, performance, settings. */
(function (PR) {
  'use strict';
  const { $, $$, esc, pct, f1, f2, signed, state, settings, fx, pill, bar, koShort, koTime, dayName, niceDate, toast, selLabel, selShort, selGroup,
    GROUPS, GROUP_ICON, liveVerdict, isLive, isFT, segmented, select, contactCard, teamLink, scoreBox, statusIcon, formBadges, wdl, md, settleSel, icon, flag, badge, fxBadge, matchRow, ring, skeleton } = PR;
  const GICON = { result: 'shield', dc: 'swap', goals: 'ball', btts: 'swap', team: 'target', corners: 'corner', cards: 'card' };
  const sh = (ico, title, cls) => `<h2><span class="ico ${cls || ''}">${icon(ico)}</span>${title}</h2>`;
  const view = () => $('#view');
  const live = PR.live;
  const MK = { O15: 'Over 1.5 goals', O25: 'Over 2.5 goals', BTTS: 'Both teams to score' };
  const head = (title, sub) => `<div class="detail-head"><button class="back" id="back" aria-label="Back">${icon('back')}</button><div class="grow"><div class="b">${title}</div>${sub ? `<div class="tiny muted">${sub}</div>` : ''}</div></div>`;
  function wireBack() { const b = $('#back'); if (b) b.onclick = () => PR.back(); }
  function ensureTeams(div) { if (!PR.teamsCached(div)) PR.loadTeams(div).then(() => PR.render()).catch(() => { state.teams[PR.slug(div)] = { missing: true }; }); }
  const rec = (div, name) => { const t = PR.teamsCached(div); return t && t.teams ? t.teams[name] : null; };

  // ------------------------------------------------------------------ MATCH PAGE
  PR.pages.match = function (page) {
    const f = fx(page.id); if (!f) { PR.back(); return; }
    ensureTeams(f.div);
    const s = live.for(f); const d = state.data; const v = state.matchView || 'overview';
    const th = rec(f.div, f.home), ta = rec(f.div, f.away);
    const parts = [head(`${flag(f.country)} ${esc(f.competition)}`, `${esc(dayName(f.kickoff))} · ${esc(koTime(f.kickoff))} ${esc(d.meta.tz)}${f.referee ? ' · referee ' + esc(f.referee) : ''}`)];
    const form = (p) => formBadges((p.last5 || []).slice().reverse().map((m) => wdl(m.gf, m.ga)));
    parts.push(`<div class="card mhead"><div class="teams">
      <div class="t">${fxBadge(f, 'home').replace('s24', 's56')}${teamLink(f, 'home')}<div class="tiny muted">${th && th.pos ? `${th.pos}${ord(th.pos)} · ${th.all.pts} pts` : 'Home'}</div>${form(f.teams.home)}</div>
      <div class="mid">${s && s.hg != null ? `<div class="score big">${s.hg} – ${s.ag}</div><div class="minute ${isLive(s) ? 'on' : 'ft'}">${esc(s.status)}</div>` : `<div class="score big muted">${esc(koTime(f.kickoff))}</div><div class="tiny muted">${esc(koShort(f.kickoff).split(' ')[0])} · ${esc(d.meta.tz)}</div>`}</div>
      <div class="t">${fxBadge(f, 'away').replace('s24', 's56')}${teamLink(f, 'away')}<div class="tiny muted">${ta && ta.pos ? `${ta.pos}${ord(ta.pos)} · ${ta.all.pts} pts` : 'Away'}</div>${form(f.teams.away)}</div></div>
      <div class="x12"><div class="lbl"><span>${esc(f.home)} ${pct(f.x12.H)}</span><span>Draw ${pct(f.x12.D)}</span><span>${esc(f.away)} ${pct(f.x12.A)}</span></div>
        <div class="tri"><span class="h" style="width:${Math.round(f.x12.H * 100)}%"></span><span class="d" style="width:${Math.round(f.x12.D * 100)}%"></span><span class="a" style="width:${Math.round(f.x12.A * 100)}%"></span></div></div>
      ${f.data_ok ? '' : '<div class="chip warn" style="margin-top:6px">⚠️ low data — never shortlisted</div>'}</div>`);
    parts.push(`<div class="card compact">${segmented([['overview', 'Overview'], ['markets', 'Markets'], ['stats', 'Stats'], ['h2h', 'H2H']], v, 'mv')}</div>`);
    if (v === 'overview') matchOverview(parts, f, s);
    else if (v === 'markets') matchMarkets(parts, f);
    else if (v === 'stats') matchStats(parts, f, th, ta);
    else matchH2H(parts, f);
    view().innerHTML = parts.join('');
    wireBack();
    $$('[data-mv]').forEach((b) => { b.onclick = () => { state.matchView = b.dataset.mv; PR.render(); }; });
  };
  const ord = (n) => { const s = ['th', 'st', 'nd', 'rd'], v = n % 100; return s[(v - 20) % 10] || s[v] || s[0]; };
  function matchOverview(parts, f, s) {
    const d = state.data;
    parts.push(`<div class="card"><div class="row"><div class="grow"><div class="cell" style="display:inline-block"><div class="k">Expected goals</div><div class="v">${f1(f.xg.home)} – ${f1(f.xg.away)}</div><div class="tiny muted">total ${f2(f.xg.total)}</div></div></div>
      <div class="rings" style="flex:2">${ring(f.p.O15, 'Over 1.5')}${ring(f.p.O25, 'Over 2.5')}${ring(f.p.BTTS, 'BTTS')}</div></div>
      <div class="tiny muted" style="margin-top:8px">${f.basis === 'market+model' ? '90% market / 10% team-form model' : 'team-form model only (no reference odds)'} · league avg ${f2((f.league_avg.home_goals || 0) + (f.league_avg.away_goals || 0))} goals, O2.5 in ${pct(f.league_avg.o25)}</div></div>`);
    const best = f.sels.filter((x) => x.odds && x.odds >= 1.3 && !x.diff).slice(0, 4);
    if (best.length) parts.push(`<div class="card compact"><div class="row"><div class="grow b">${icon('target', 'sm')} Best priced selections</div></div><table class="tbl">${best.map((x) => `<tr><td><div class="b">${esc(selLabel(x.sel, f.home, f.away))}</div><div class="tiny muted">${esc(GROUPS[selGroup(x.sel)])} · model ${pct(x.p_model)} · Sportybet ${pct(x.p_sb)}</div></td><td class="right"><b>${f2(x.odds)}</b></td><td class="right">${pill(x.p, 0.8, 0.7)}</td></tr>`).join('')}</table></div>`);
    const bets = betsOn(f.id);
    if (bets.length) parts.push(`<div class="card compact"><div class="b">Bets on this match</div><div class="chips" style="margin-top:6px">${bets.map((b) => { const vd = liveVerdict(b.sel, s); return `<span class="chip ${vd.cls}">${esc(b.kind)}: ${esc(b.label)}${b.odds ? ' @ ' + f2(b.odds) : ''} · ${esc(vd.text)}</span>`; }).join('')}</div></div>`);
    const sb = f.sportybet || {};
    if (Object.keys(sb).length) {
      const ou = sb.OU || {};
      parts.push(`<div class="card compact"><div class="b">Sportybet prices</div><table class="tbl head" style="margin-top:6px"><tr><th>Market</th><th class="right">1 / Over / Yes</th><th class="right">X</th><th class="right">2 / Under / No</th></tr>
        ${sb['1X2'] ? `<tr><td>Match result</td><td class="right">${f2(sb['1X2'][0])}</td><td class="right">${f2(sb['1X2'][1])}</td><td class="right">${f2(sb['1X2'][2])}</td></tr>` : ''}
        ${sb.DC ? `<tr><td>Double chance 1X · 12 · X2</td><td class="right">${f2(sb.DC['1X'])}</td><td class="right">${f2(sb.DC['12'])}</td><td class="right">${f2(sb.DC.X2)}</td></tr>` : ''}
        ${['1.5', '2.5', '3.5'].filter((l) => ou[l]).map((l) => `<tr><td>Goals ${l}</td><td class="right">${f2(ou[l][0])}</td><td></td><td class="right">${f2(ou[l][1])}</td></tr>`).join('')}
        ${sb.BTTS ? `<tr><td>Both teams to score</td><td class="right">${f2(sb.BTTS[0])}</td><td></td><td class="right">${f2(sb.BTTS[1])}</td></tr>` : ''}</table>
        <div class="tiny muted" style="margin-top:4px">Prices are payout information only; they never enter the model. All lines under Markets.</div></div>`);
    } else parts.push(`<div class="card tiny muted">No Sportybet price for this match.</div>`);
    const inc = f.livescore_id && state.incidents[f.livescore_id];
    if (inc && inc.items.length) parts.push(`<div class="card compact"><div class="b">Match events</div><div class="small" style="margin-top:6px">${inc.items.map((it) => `<div>${it.team === 'H' ? '' : '<span class="muted">(away) </span>'}${PR.incidentLine(it)}</div>`).join('')}</div></div>`);
    const hl = [f.home_long, f.away_long, f.home, f.away].map((t) => d.headlines && d.headlines[t]).filter(Boolean);
    if (hl.length) parts.push(`<div class="card compact"><div class="b">Recent headlines <span class="muted small">(context only)</span></div>${hl.map((items) => items.map((h) => `<div class="list-item"><div class="main"><a href="${esc(h.link)}">${esc(h.title)}</a><div class="meta">${esc(h.when || '')} · ${esc(h.source || '')}</div></div></div>`).join('')).join('')}</div>`);
  }
  function betsOn(fid) {
    const d = state.data, out = [], sf = d.safe || { bets: [], trebles: [] };
    sf.bets.filter((b) => b.fixture === fid).forEach((b) => out.push({ kind: 'Safest', label: b.label, sel: b.sel, odds: b.odds }));
    sf.trebles.forEach((t, i) => t.legs.filter((l) => l.fixture === fid).forEach((l) => out.push({ kind: `Treble ${i + 1}`, label: l.label, sel: l.sel, odds: l.odds })));
    (d.parlays || []).forEach((p, i) => p.legs.filter((l) => l.fixture === fid).forEach((l) => out.push({ kind: `Parlay ${i + 1}`, label: l.label || selLabel(l.sel), sel: l.sel, odds: l.odds })));
    Object.entries(d.picks || {}).forEach(([mk, lst]) => lst.filter((p) => p.fixture === fid).forEach(() => out.push({ kind: 'Shortlist', label: MK[mk], sel: mk })));
    return out;
  }
  function matchMarkets(parts, f) {
    const groups = {};
    f.sels.forEach((s) => { (groups[selGroup(s.sel)] = groups[selGroup(s.sel)] || []).push(s); });
    parts.push(`<div class="card tiny muted">Every modelled market. <b>Prob.</b> = the probability used for ranking (average of the model and the de-margined Sportybet price where a price exists). Rows at ≥ 70% are highlighted; ⚠ = the two views differ by more than 12 points.</div>`);
    Object.keys(GROUPS).forEach((g) => {
      const items = groups[g]; if (!items) return;
      const order = { result: ['H', 'D', 'A'], dc: ['1X', '12', 'X2'], btts: ['BTTS', 'NBTTS'] }[g];
      const sorted = order ? items.slice().sort((a, b) => order.indexOf(a.sel) - order.indexOf(b.sel)) : items.slice().sort((a, b) => a.sel.localeCompare(b.sel, undefined, { numeric: true }));
      parts.push(`<div class="card compact"><div class="row" style="margin:4px 0 2px"><span class="ico">${icon(GICON[g] || 'ball')}</span><b>${GROUPS[g]}</b></div><table class="tbl head" style="margin-top:4px"><tr><th>Selection</th><th class="right">Model</th><th class="right">Sportybet</th><th class="right">Price</th><th class="right">Prob.</th></tr>
        ${sorted.map((s) => `<tr class="${s.p >= 0.7 ? 'hl' : ''}"><td>${esc(selLabel(s.sel, f.home, f.away))}${s.diff ? ' <span class="warn">⚠</span>' : ''}</td><td class="right muted">${pct(s.p_model)}</td><td class="right muted">${pct(s.p_sb)}</td><td class="right">${s.odds ? `<b>${f2(s.odds)}</b>` : '<span class="muted">–</span>'}</td><td class="right">${pill(s.p, 0.8, 0.7)}</td></tr>`).join('')}</table></div>`);
    });
    const sb = f.sportybet || {};
    const lines = (obj, label) => obj ? `<tr><td>${label}</td><td colspan="4" class="tiny">${Object.entries(obj).sort((a, b) => +a[0] - +b[0]).map(([k, v]) => `<span class="chip">${k}: ${f2(v[0])} / ${f2(v[1])}</span>`).join(' ')}</td></tr>` : '';
    if (sb.CORN || sb.CARDS || sb.CORNH || sb.CORN1H) parts.push(`<div class="card compact"><div class="b">More Sportybet lines (over / under)</div><table class="tbl" style="margin-top:4px">${lines(sb.CORN, 'Corners')}${lines(sb.CORN1H, '1st-half corners')}${lines(sb.CORNH, 'Home corners')}${lines(sb.CORNA, 'Away corners')}${lines(sb.CARDS, 'Cards')}${lines(sb.CARDSH, 'Home cards')}${lines(sb.CARDSA, 'Away cards')}</table></div>`);
    if (f.corners || f.cards) parts.push(`<div class="card compact"><div class="b">Expected counts</div><div class="grid4" style="margin-top:6px">${f.corners ? `<div class="cell"><div class="k">Corners</div><div class="v">${f1(f.corners.total)}</div><div class="tiny muted">${f1(f.corners.home)} – ${f1(f.corners.away)}</div></div>` : ''}${f.cards ? `<div class="cell"><div class="k">Cards</div><div class="v">${f1(f.cards.total)}</div><div class="tiny muted">${f1(f.cards.home)} – ${f1(f.cards.away)}</div></div>` : ''}</div></div>`);
  }
  function cmpRow(label, a, b, fmt, higherBetter) {
    fmt = fmt || f2; const av = a == null || isNaN(a) ? null : +a, bv = b == null || isNaN(b) ? null : +b;
    if (av == null && bv == null) return '';
    const tot = (av || 0) + (bv || 0); const wa = tot ? (av || 0) / tot : 0.5;
    const cls = (x, y) => (x == null || y == null || x === y) ? '' : ((x > y) === !!higherBetter ? 'lead' : '');
    return `<tr><td class="right ${cls(av, bv)}">${fmt(av)}</td><td class="mid"><div class="k">${label}</div><div class="duo"><span class="l" style="width:${Math.round(wa * 100)}%"></span><span class="r" style="width:${Math.round((1 - wa) * 100)}%"></span></div></td><td class="${cls(bv, av)}">${fmt(bv)}</td></tr>`;
  }
  function matchStats(parts, f, th, ta) {
    const H = f.teams.home, A = f.teams.away;
    parts.push(`<div class="card compact"><div class="row"><div class="grow b row" style="gap:6px">${fxBadge(f, 'home')}${esc(f.home)}</div><div class="tiny muted">form model · last 2 seasons</div><div class="b row" style="gap:6px">${esc(f.away)}${fxBadge(f, 'away')}</div></div>
      <table class="cmp">${cmpRow('Goals scored / game', H.gf, A.gf, f2, true)}${cmpRow('Goals conceded / game', H.ga, A.ga, f2, false)}
      ${cmpRow('Home / away goals for', H.venue_gf, A.venue_gf, f2, true)}${cmpRow('Home / away goals against', H.venue_ga, A.venue_ga, f2, false)}
      ${cmpRow('Attack strength', H.att, A.att, f2, true)}${cmpRow('Defence (lower = better)', H.def, A.def, f2, false)}
      ${cmpRow('xG for (last 10)', H.xg_for, A.xg_for, f2, true)}${cmpRow('xG against (last 10)', H.xg_against, A.xg_against, f2, false)}
      ${cmpRow('Shots on target for', H.sot_for, A.sot_for, f1, true)}${cmpRow('Shots on target against', H.sot_against, A.sot_against, f1, false)}
      ${cmpRow('Over 1.5 rate', H.o15, A.o15, pct, true)}${cmpRow('Over 2.5 rate', H.o25, A.o25, pct, true)}${cmpRow('Over 3.5 rate', H.o35, A.o35, pct, true)}
      ${cmpRow('BTTS rate', H.btts, A.btts, pct, true)}${cmpRow('Clean sheets', H.cs, A.cs, pct, true)}${cmpRow('Failed to score', H.fts, A.fts, pct, false)}
      ${cmpRow('Goals / game, last 5', H.form5_goals, A.form5_goals, f2, true)}${cmpRow('Over 2.5 in last 10', H.last_o25, A.last_o25, (x) => x == null ? '–' : x + '/10', true)}${cmpRow('BTTS in last 10', H.last_btts, A.last_btts, (x) => x == null ? '–' : x + '/10', true)}</table>
      <div class="tiny muted">${H.n} / ${A.n} matches used (time-weighted ${f1(H.n_eff)} / ${f1(A.n_eff)}). Bars compare the two teams.</div></div>`);
    const t = PR.teamsCached(f.div);
    if (th && ta) {
      const sp = (r) => r.all;
      parts.push(`<div class="card compact"><div class="row"><div class="grow b">This season</div><div class="tiny muted">since ${esc(th.season_from)}</div></div>
        <table class="cmp">${cmpRow('League position', th.pos, ta.pos, (x) => x == null ? '–' : x + ord(x), false)}${cmpRow('Points (played)', sp(th).pts, sp(ta).pts, (x) => x == null ? '–' : x, true)}
        ${cmpRow('Points per game', sp(th).ppg, sp(ta).ppg, f2, true)}${cmpRow('Won', sp(th).w, sp(ta).w, (x) => x, true)}${cmpRow('Drawn', sp(th).d, sp(ta).d, (x) => x, true)}${cmpRow('Lost', sp(th).l, sp(ta).l, (x) => x, false)}
        ${cmpRow('Goals for / game', sp(th).gf_avg, sp(ta).gf_avg, f2, true)}${cmpRow('Goals against / game', sp(th).ga_avg, sp(ta).ga_avg, f2, false)}
        ${cmpRow('Corners for / game', th.avg.corners_for, ta.avg.corners_for, f1, true)}${cmpRow('Corners against / game', th.avg.corners_against, ta.avg.corners_against, f1, false)}
        ${cmpRow('Cards / game', th.avg.cards_for, ta.avg.cards_for, f1, false)}${cmpRow('Scored in last 10', th.scored_in_last, ta.scored_in_last, (x) => x == null ? '–' : x + '/10', true)}</table>
        <div class="tiny muted">Home record ${esc(f.home)}: ${th.home.w}W ${th.home.d}D ${th.home.l}L · away record ${esc(f.away)}: ${ta.away.w}W ${ta.away.d}D ${ta.away.l}L. Tap a team name for the full page.</div></div>`);
    } else if (t && t.missing) parts.push(`<div class="card tiny muted">Season table not available for this competition yet.</div>`);
    else parts.push(`<div class="card tiny muted">Loading season stats…</div>`);
  }
  function matchH2H(parts, f) {
    const h2h = f.h2h || [];
    if (h2h.length) {
      const tot = h2h.map((m) => m.hg + m.ag);
      parts.push(`<div class="card compact"><div class="row"><div class="grow b">Head to head</div><span class="chip">${f1(tot.reduce((a, b) => a + b, 0) / tot.length)} goals avg</span><span class="chip">O2.5 ${tot.filter((t) => t >= 3).length}/${tot.length}</span><span class="chip">BTTS ${h2h.filter((m) => m.hg > 0 && m.ag > 0).length}/${tot.length}</span></div>
        <table class="tbl" style="margin-top:6px">${h2h.map((m) => `<tr><td class="tiny muted nowrap">${esc(m.date)}</td><td class="${m.hg > m.ag ? 'b' : ''}"><div class="row" style="gap:6px">${badge(m.home, null, 22)}<span>${esc(m.home)}</span></div></td><td class="right nowrap"><b>${m.hg} – ${m.ag}</b></td><td class="${m.ag > m.hg ? 'b' : ''}"><div class="row" style="gap:6px;justify-content:flex-end"><span>${esc(m.away)}</span>${badge(m.away, null, 22)}</div></td></tr>`).join('')}</table></div>`);
    } else parts.push(`<div class="card tiny muted">No head-to-head in the last two seasons.</div>`);
    const recent = (p, name, side) => `<div class="card compact"><div class="b row" style="gap:6px">${fxBadge(f, side)}${esc(name)} <span class="muted" style="font-weight:500">— last 5</span></div><table class="tbl" style="margin-top:4px">${(p.last5 || []).map((m) => `<tr><td class="tiny muted nowrap">${esc(m.date)}</td><td><div class="row" style="gap:6px"><i class="f ${wdl(m.gf, m.ga)}">${wdl(m.gf, m.ga)}</i>${badge(m.opp, null, 22)}<span class="nowrap">${m.venue === 'H' ? 'v' : '@'} ${esc(m.opp)}</span></div></td><td class="right nowrap"><b>${m.gf} – ${m.ga}</b></td><td class="tiny muted">${esc(m.league || '')}</td></tr>`).join('') || '<tr><td class="muted">no matches</td></tr>'}</table></div>`;
    parts.push(recent(f.teams.home, f.home_long || f.home, 'home'));
    parts.push(recent(f.teams.away, f.away_long || f.away, 'away'));
  }

  // ------------------------------------------------------------------ TEAM PAGE
  PR.pages.team = function (page) {
    ensureTeams(page.div);
    const t = PR.teamsCached(page.div); const v = state.teamView || 'overview';
    const parts = [head(esc(page.name), esc(page.country))];
    if (!t) { parts.push(skeleton(6)); view().innerHTML = parts.join(''); wireBack(); return; }
    const r = t.teams && t.teams[page.name];
    if (!r) { parts.push(`<div class="card empty">No season data for ${esc(page.name)} yet.</div>`); view().innerHTML = parts.join(''); wireBack(); return; }
    const a = r.all;
    parts.push(`<div class="card"><div class="thead">${badge(page.name, null, 56)}<div class="grow"><div class="h1">${esc(page.name)}</div><div class="small muted">${flag(page.country)} ${esc(t.league)} · ${r.pos ? `${r.pos}${ord(r.pos)} of ${r.teams_in_league}` : ''} · ${a.pts} pts from ${a.p}</div><div style="margin-top:4px">${formBadges(r.form.split(''))}</div></div></div>
      <div class="grid4" style="margin-top:8px"><div class="cell"><div class="k">Record</div><div class="v">${a.w}-${a.d}-${a.l}</div><div class="tiny muted">W-D-L</div></div><div class="cell"><div class="k">Goals</div><div class="v">${a.gf} : ${a.ga}</div><div class="tiny muted">${f2(a.gf_avg)} / ${f2(a.ga_avg)} per game</div></div><div class="cell"><div class="k">Points / game</div><div class="v">${f2(a.ppg)}</div><div class="tiny muted">streak ${esc(r.streak || '–')}</div></div><div class="cell"><div class="k">Over 2.5</div><div class="v">${pct(a.o25)}</div><div class="tiny muted">BTTS ${pct(a.btts)}</div></div></div></div>`);
    parts.push(`<div class="card compact">${segmented([['overview', 'Overview'], ['matches', 'Matches'], ['table', 'Table']], v, 'tv')}</div>`);
    if (v === 'overview') {
      const row = (label, k, fmt) => `<tr><td>${label}</td><td class="right">${(fmt || pct)(r.all[k])}</td><td class="right">${(fmt || pct)(r.home[k])}</td><td class="right">${(fmt || pct)(r.away[k])}</td></tr>`;
      parts.push(`<div class="card compact"><div class="b">Season splits</div><table class="tbl head" style="margin-top:4px"><tr><th></th><th class="right">All</th><th class="right">Home</th><th class="right">Away</th></tr>
        <tr><td>Played</td><td class="right">${r.all.p}</td><td class="right">${r.home.p}</td><td class="right">${r.away.p}</td></tr>
        <tr><td>W-D-L</td><td class="right">${r.all.w}-${r.all.d}-${r.all.l}</td><td class="right">${r.home.w}-${r.home.d}-${r.home.l}</td><td class="right">${r.away.w}-${r.away.d}-${r.away.l}</td></tr>
        ${row('Points / game', 'ppg', f2)}${row('Goals for / game', 'gf_avg', f2)}${row('Goals against / game', 'ga_avg', f2)}${row('Win rate', 'win')}
        ${row('Over 1.5 goals', 'o15')}${row('Over 2.5 goals', 'o25')}${row('Over 3.5 goals', 'o35')}${row('Both teams scored', 'btts')}${row('Clean sheets', 'cs')}${row('Failed to score', 'fts')}</table></div>`);
      const av = r.avg;
      parts.push(`<div class="card compact"><div class="b">Averages per game</div><div class="grid4" style="margin-top:6px">
        ${av.xg_for != null ? `<div class="cell"><div class="k">xG for / against</div><div class="v">${f2(av.xg_for)} / ${f2(av.xg_against)}</div></div>` : ''}
        ${av.sot_for != null ? `<div class="cell"><div class="k">Shots on target</div><div class="v">${f1(av.sot_for)} / ${f1(av.sot_against)}</div><div class="tiny muted">for / against</div></div>` : ''}
        ${av.corners_for != null ? `<div class="cell"><div class="k">Corners</div><div class="v">${f1(av.corners_for)} / ${f1(av.corners_against)}</div><div class="tiny muted">for / against</div></div>` : ''}
        ${av.cards_for != null ? `<div class="cell"><div class="k">Cards</div><div class="v">${f1(av.cards_for)} / ${f1(av.cards_against)}</div><div class="tiny muted">for / against</div></div>` : ''}
        <div class="cell"><div class="k">Scored in</div><div class="v">${r.scored_in_last}/10</div><div class="tiny muted">last 10 matches</div></div><div class="cell"><div class="k">Conceded in</div><div class="v">${r.conceded_in_last}/10</div><div class="tiny muted">last 10 matches</div></div></div>
        <div class="tiny muted" style="margin-top:4px">Season since ${esc(r.season_from)} · league average ${f2(t.avg_goals)} goals, O2.5 ${pct(t.o25_rate)}, BTTS ${pct(t.btts_rate)}.</div></div>`);
      const upcoming = state.data.fixtures.filter((f) => f.country === page.country && (f.home === page.name || f.away === page.name));
      if (upcoming.length) parts.push(`<div class="card compact"><div class="b">In this analysis</div>${upcoming.map((f) => PR.matchLine(f, `<div class="nums"><span class="pill ${f.p.O25 >= 0.6 ? 'hi' : ''}">O2.5 ${pct(f.p.O25)}</span></div>`)).join('')}</div>`);
    } else if (v === 'matches') {
      parts.push(`<div class="card compact"><div class="b">Last ${r.last.length} matches</div><table class="tbl" style="margin-top:4px">${r.last.map((m) => `<tr><td class="tiny muted nowrap">${esc(m.date)}</td><td><div class="row" style="gap:6px"><i class="f ${m.r}">${m.r}</i>${badge(m.opp, null, 22)}<a href="#" class="team" data-team="${esc(m.opp)}" data-country="${esc(page.country)}" data-div="${esc(page.div)}">${m.venue === 'H' ? 'v' : '@'} ${esc(m.opp)}</a></div></td><td class="right nowrap"><b>${m.gf} – ${m.ga}</b></td><td class="tiny muted">${esc(m.league || '')}</td></tr>`).join('')}</table></div>`);
    } else {
      parts.push(`<div class="card compact"><div class="b">${esc(t.league)} table</div><div class="tiny muted">${t.matches} matches since ${esc(t.season_from)}</div><table class="tbl head table" style="margin-top:4px"><tr><th>#</th><th>Team</th><th class="right">P</th><th class="right">W</th><th class="right">D</th><th class="right">L</th><th class="right">GD</th><th class="right">Pts</th></tr>
        ${t.table.map((x) => `<tr class="${x.team === page.name ? 'hl' : ''}"><td class="muted">${x.pos}</td><td><div class="tname">${badge(x.team, null, 22)}<a href="#" class="team" data-team="${esc(x.team)}" data-country="${esc(page.country)}" data-div="${esc(page.div)}">${esc(x.team)}</a></div></td><td class="right">${x.p}</td><td class="right">${x.w}</td><td class="right">${x.d}</td><td class="right">${x.l}</td><td class="right">${x.gd > 0 ? '+' : ''}${x.gd}</td><td class="right b">${x.pts}</td></tr>`).join('')}</table></div>`);
    }
    view().innerHTML = parts.join('');
    wireBack();
    $$('[data-tv]').forEach((b) => { b.onclick = () => { state.teamView = b.dataset.tv; PR.render(); }; });
  };

  // ------------------------------------------------------------------ DAY PAGE
  PR.pages.day = function (page) {
    const day = state.days[page.date];
    if (!day) {
      if (!state.days[page.date + '_loading']) { state.days[page.date + '_loading'] = true; PR.loadDay(page.date).then(() => PR.render()).catch((e) => { state.days[page.date] = { error: e.message }; PR.render(); }); }
      view().innerHTML = head(esc(dayName(page.date))) + skeleton(8); wireBack(); return;
    }
    if (day.error) { view().innerHTML = head(esc(dayName(page.date))) + `<div class="card empty">Could not load this day (${esc(day.error)}).</div>`; wireBack(); return; }
    const s = day.summary || {}; const v = state.dayView || 'results';
    const parts = [head(esc(dayName(page.date)), `${s.n || 0} matches · ${s.finished || 0} finished${s.goals_avg != null ? ` · ${f1(s.goals_avg)} goals/match` : ''}`)];
    const box = (label, o, k) => { if (!o || !o.n) return `<div class="cell"><div class="k">${label}</div><div class="v muted">–</div><div class="tiny muted">none</div></div>`; const settled = o.n - (o.pending || 0);
      return settled ? `<div class="cell"><div class="k">${label}</div><div class="v ${PR.chipCls(o, k)}">${o[k]}/${settled}</div><div class="tiny muted">${o.pending ? o.pending + ' still open' : 'all settled'}</div></div>` : `<div class="cell"><div class="k">${label}</div><div class="v">${o.n}</div><div class="tiny muted">open · not settled yet</div></div>`; };
    parts.push(`<div class="card"><div class="grid4">${box(icon('target', 'sm') + ' Safest bets', s.safes, 'hit')}${box(icon('lock', 'sm') + ' Trebles', s.accas, 'won')}${box(icon('ticket', 'sm') + ' Parlays', s.parlays, 'won')}${box(icon('star', 'sm') + ' Shortlist', s.picks, 'hit')}</div>
      ${s.finished ? `<div class="tiny muted" style="margin-top:6px">Finished matches: Over 2.5 in ${pct(s.o25_rate)}, BTTS in ${pct(s.btts_rate)}.</div>` : ''}</div>`);
    parts.push(`<div class="card compact">${segmented([['results', 'Results'], ['bets', 'Bets']], v, 'dv')}</div>`);
    if (v === 'results') {
      let lastComp = null;
      const fxs = day.fixtures.slice().sort((a, b) => a.competition.localeCompare(b.competition) || a.kickoff.localeCompare(b.kickoff));
      parts.push('<div class="card compact">');
      fxs.forEach((f) => {
        if (f.competition !== lastComp) { parts.push(`<div class="comp-head">${flag(f.country)} ${esc(f.competition)}</div>`); lastComp = f.competition; }
        const sc = f.score; const fin = sc && sc.hg != null;
        const seenB = new Set();
        const marks = (f.bets || []).filter((b) => { const k = b.kind + '|' + b.sel; if (seenB.has(k)) return false; seenB.add(k); return true; }).map((b) => `<span class="chip ${b.status === 'hit' ? 'good' : b.status === 'miss' ? 'bad' : ''}">${icon(b.kind === 'safe' ? 'target' : b.kind === 'acca' ? 'lock' : b.kind === 'parlay' ? 'ticket' : 'star')} ${esc(b.label)}${b.odds ? ' @ ' + f2(b.odds) : ''} ${statusIcon(b.status)}</span>`).join('');
        parts.push(matchRow(f, { tap: !!fx(f.id), short: true, sub: marks ? `<div class="chips">${marks}</div>` : '', right: fin ? '' : `<span class="tiny muted">xG ${f1(f.xg[0])}–${f1(f.xg[1])}</span><span class="tiny muted">O2.5 ${pct(f.p.O25)}</span>` }));
      });
      parts.push('</div>');
    } else {
      const safeBets = []; day.fixtures.forEach((f) => (f.bets || []).filter((b) => b.kind === 'safe').forEach((b) => safeBets.push({ f, b })));
      const picks = []; day.fixtures.forEach((f) => (f.bets || []).filter((b) => b.kind === 'pick').forEach((b) => picks.push({ f, b })));
      const multi = (lst, title, icon) => lst.length ? `<h2 class="section">${icon} ${title}</h2>` + lst.map((m, i) => `<div class="card acca"><div class="row"><div class="grow"><b>${title.replace(/s$/, '')} ${i + 1}</b> <span class="muted small">· odds ${f2(m.odds)} · win ${pct(m.p)}</span></div><span class="chip ${m.status === 'won' ? 'good' : m.status === 'lost' ? 'bad' : ''}">${esc(m.status)} ${statusIcon(m.status)}</span></div>
        <table class="tbl legs">${m.legs.map((l) => `<tr><td class="tiny muted nowrap">${esc(koShort(l.kickoff))}</td><td><div class="b">${esc(l.home)} v ${esc(l.away)}</div><div class="sel">${esc(l.label)}</div></td><td class="right nowrap">${l.score ? `<b>${esc(l.score)}</b>` : '<span class="muted">–</span>'}</td><td class="right">${f2(l.odds)} ${statusIcon(l.status)}</td></tr>`).join('')}</table></div>`).join('') : '';
      parts.push(multi(day.accas || [], 'Safest trebles', icon('lock')));
      if (safeBets.length) parts.push(`<h2 class="section">${icon('target')} Safest bets</h2><div class="card compact"><table class="tbl">${safeBets.map(({ f, b }) => `<tr class="${fx(f.id) ? 'tap' : ''}" data-fx="${esc(f.id)}"><td class="tiny muted nowrap">${esc(koTime(f.kickoff))}</td><td><div class="b">${esc(f.home)} v ${esc(f.away)}</div><div class="tiny muted">${esc(b.label)}</div></td><td class="right nowrap">${f.score && f.score.hg != null ? `<b>${f.score.hg}–${f.score.ag}</b>` : '<span class="muted">–</span>'}</td><td class="right nowrap">${f2(b.odds)} ${statusIcon(b.status)}</td></tr>`).join('')}</table></div>`);
      parts.push(multi(day.parlays || [], 'Parlays', icon('ticket')));
      if (picks.length) parts.push(`<h2 class="section">${icon('star')} Shortlist picks</h2><div class="card compact"><table class="tbl">${picks.map(({ f, b }) => `<tr class="${fx(f.id) ? 'tap' : ''}" data-fx="${esc(f.id)}"><td class="tiny muted nowrap">${esc(koTime(f.kickoff))}</td><td><div class="b">${esc(f.home)} v ${esc(f.away)}</div><div class="tiny muted">${esc(b.label)} · ${pct(b.p)}</div></td><td class="right nowrap">${f.score && f.score.hg != null ? `<b>${f.score.hg}–${f.score.ag}</b>` : '<span class="muted">–</span>'}</td><td class="right">${statusIcon(b.status)}</td></tr>`).join('')}</table></div>`);
      if (!safeBets.length && !picks.length && !(day.accas || []).length && !(day.parlays || []).length) parts.push(`<div class="card empty">No bets were recorded for this day.</div>`);
    }
    view().innerHTML = parts.join('');
    wireBack();
    $$('[data-dv]').forEach((b) => { b.onclick = () => { state.dayView = b.dataset.dv; PR.render(); }; });
  };

  // ------------------------------------------------------------------ ANALYSIS (report / dossier)
  PR.pages.analysis = function (page) {
    const d = state.data; const dates = d.history.reports || []; const date = page.date || dates[0] || (d.meta.generated || '').slice(0, 10); const kind = page.kind || 'report';
    const key = `${date}|${kind}`;
    if (!state.reports[key]) {
      state.reports[key] = { loading: true };
      PR.nfetch(PR.rawUrl(kind === 'dossier' ? `reports/${date}-parlays.md` : `reports/${date}.md`) + '?t=' + Math.floor(Date.now() / 60000)).then((r) => { state.reports[key] = r.code === 200 ? { md: r.body } : { md: `_This analysis could not be loaded (HTTP ${r.code})._` }; PR.render(); });
    }
    const rep = state.reports[key];
    const parts = [head(kind === 'report' ? 'Full analysis' : 'Parlay dossier', esc(niceDate(date)))];
    parts.push(`<div class="card compact">${segmented([['report', `${icon('doc')} Full analysis`], ['dossier', `${icon('ticket')} Parlay dossier`]], kind, 'ak')}${dates.length > 1 ? `<div class="row" style="margin-top:8px"><div class="grow tiny muted">Archive</div>${select('an-date', dates.map((r) => [r, r]), date)}</div>` : ''}</div>`);
    parts.push(`<div class="card md">${rep.md ? md(rep.md) : '<div class="empty">Loading analysis…</div>'}</div>`);
    view().innerHTML = parts.join('');
    wireBack();
    $$('[data-ak]').forEach((b) => { b.onclick = () => PR.replace({ type: 'analysis', kind: b.dataset.ak, date }); });
    const sel = $('#an-date'); if (sel) sel.onchange = (e) => PR.replace({ type: 'analysis', kind, date: e.target.value });
  };

  // ------------------------------------------------------------------ PERFORMANCE (ledgers)
  PR.pages.performance = function () {
    const d = state.data; const ps = d.parlay_summary || {}; const sf = (d.safe || {}).summary || {}; const parts = [head('Performance', 'Auto-graded from official results')];
    const row = (name, s, wonKey) => s && s.n ? `<tr><td>${name}</td><td class="right">${s[wonKey || 'won']}/${s.n}</td><td class="right"><b>${pct(s.rate)}</b></td><td class="right muted">${pct(s.exp_rate)}</td><td class="right">${f2(s.avg_odds)}</td><td class="right ${s.roi > 0 ? 'good' : s.roi < 0 ? 'bad' : ''}"><b>${signed(s.roi)}</b></td></tr>` : `<tr><td>${name}</td><td class="right muted">0/0</td><td class="right muted">–</td><td class="right muted">–</td><td class="right muted">–</td><td class="right muted">–</td></tr>`;
    const tbl = (rows) => `<table class="tbl head perf" style="margin-top:6px"><tr><th>Scope</th><th class="right">Won</th><th class="right">Hit</th><th class="right">Exp.</th><th class="right">Odds</th><th class="right">Return</th></tr>${rows}</table>`;
    parts.push(`<div class="card"><div class="row"><span class="ico">${icon('lock')}</span><b>Safest trebles</b></div>${tbl(row('All time', (sf.accas || {}).all) + row('Last 30 days', (sf.accas || {})['30d']))}<div class="tiny muted">${(sf.accas || {}).pending || 0} pending.</div></div>`);
    const bg = (sf.bets || {}).by_group || {};
    parts.push(`<div class="card"><div class="row"><span class="ico green">${icon('target')}</span><b>Safest bets</b></div>${tbl(row('All time', (sf.bets || {}).all) + row('Last 30 days', (sf.bets || {})['30d']) + Object.entries(bg).map(([g, s]) => row(GROUPS[g] || g, s)).join(''))}<div class="tiny muted">${(sf.bets || {}).pending || 0} pending. "Expected" is the model's own predicted hit rate — if the real rate stays below it for weeks, the model is over-confident.</div></div>`);
    parts.push(`<div class="card"><div class="row"><span class="ico amber">${icon('ticket')}</span><b>Parlays</b></div>${tbl(row('All time', ps.all) + row('Last 30 days', ps['30d']) + Object.entries(ps.by_run || {}).filter(([k]) => /^\d\d:\d\d$/.test(k)).map(([k, v]) => row('Run ' + k, v)).join(''))}<div class="tiny muted">${ps.pending || 0} pending.</div></div>`);
    const t = d.tracker || {};
    parts.push(`<div class="card"><div class="row"><span class="ico">${icon('star')}</span><b>Shortlist tracker</b></div><table class="tbl head" style="margin-top:6px"><tr><th>Market</th><th class="right">Settled</th><th class="right">Hit</th><th class="right">30d</th><th class="right">Pending</th></tr>${['O15', 'O25', 'BTTS'].map((mk) => { const s = t[mk] || {}; return `<tr><td>${MK[mk]}</td><td class="right">${s.settled || 0}</td><td class="right">${pct(s.rate)}</td><td class="right">${pct(s.recent_rate)}</td><td class="right">${s.pending || 0}</td></tr>`; }).join('')}</table></div>`);
    parts.push(`<div class="card compact"><b>Parlay ledger</b>${(d.ledger || []).map((p) => `<div class="list-item"><div class="main"><div class="match">${statusIcon(p.status)} ${esc(p.id)} <span class="muted small">· ${esc(p.created)} · run ${esc(p.run)}</span></div>${p.legs.map((l) => `<div class="small">${esc(l.home)} v ${esc(l.away)} — <b>${esc(selLabel(l.sel, l.home, l.away))}</b> @ ${f2(l.odds)}</div>`).join('')}${p.note ? `<div class="tiny muted">${esc(p.note)}</div>` : ''}</div><div class="nums"><div><b>${f2(p.odds)}</b></div><div class="muted">${pct(p.p)}</div></div></div>`).join('') || '<div class="empty small">No parlays recorded yet.</div>'}</div>`);
    view().innerHTML = parts.join('');
    wireBack();
  };

  // ------------------------------------------------------------------ SETTINGS
  function notifState() { if (!PR.native || !PR.native.notificationsAllowed) return null; try { return !!PR.native.notificationsAllowed(); } catch (e) { return null; } }
  PR.pages.settings = function () {
    const parts = [head('Settings')];
    const allowed = notifState();
    parts.push(`<div class="card settings"><h2>${icon('bell')} Notifications</h2>
      <div class="row"><div class="grow small">${allowed === false ? '<span class="chip bad">off</span> Allow notifications to get new-analysis, goal and update alerts.' : allowed ? '<span class="chip good">on</span> New analysis · goals in tracked matches · app updates' : 'Notifications are only available in the Android app.'}</div>
      ${allowed === false ? '<button class="btn primary" id="s-notif">Allow</button>' : ''}</div>
      <label class="row" style="margin-top:10px"><input type="checkbox" id="s-goals" ${settings.goalAlerts ? 'checked' : ''}> <span class="grow">Goal alerts with the scorer for tracked matches (safest bets, trebles, parlays, shortlist)</span></label>
      <div class="tiny muted" style="margin-top:6px">Alerts arrive within about 15 minutes when the app is closed and instantly while the app is open.</div></div>`);
    parts.push(`<div class="card settings"><h2>${icon('moon')} Appearance</h2>${segmented([['system', 'System'], ['light', 'Light'], ['dark', 'Dark']], settings.theme || 'system', 'th')}
      <div class="tiny muted" style="margin-top:6px">System follows your phone's dark-mode setting.</div></div>`);
    parts.push(`<div class="card settings"><h2>${icon('clock')} Display</h2>
      <label>Live auto-refresh (seconds, min 20)</label><input id="s-live" type="number" value="${settings.liveEvery}">
      <label>Analysis timezone offset from UTC (hours; South Africa = 2)</label><input id="s-tz" type="number" value="${settings.tzOffset}">
      <div style="margin-top:12px"><button class="btn primary" id="s-save">Save</button><button class="btn" id="s-clear">Clear saved data</button></div></div>`);
    parts.push(`<div class="card settings"><h2>${icon('info')} App</h2><div class="row"><div class="grow small">PlayReport ${PR.APP_VERSION ? 'v' + PR.APP_VERSION : '(browser preview)'}${state.update ? ` · <b>v${esc(state.update.version)} available</b>` : ' · up to date'}</div>
      ${state.update ? `<button class="btn primary" id="s-install">Update</button>` : `<button class="btn" id="s-check">Check for update</button>`}</div>
      <div class="tiny muted" style="margin-top:6px">PlayReport checks for updates automatically and downloads them for you; Android asks for one confirmation before installing.</div></div>`);
    parts.push(contactCard(false));
    parts.push(`<div class="card small"><b>About PlayReport</b><div class="muted" style="margin-top:4px">Football analysis three times a day (07:00, 12:00 and 17:00 SAST): expected goals, probabilities for every market, safest bets and trebles, value parlays, live scores and an audited day-by-day record. Live scores come from a public feed and never influence the model.</div>
      <div class="muted" style="margin-top:6px">Statistical information, not betting advice. Bet responsibly — 18+.</div></div>`);
    view().innerHTML = parts.join('');
    wireBack();
    $('#s-save').onclick = () => { settings.liveEvery = Math.max(20, +$('#s-live').value || 60); settings.tzOffset = +$('#s-tz').value || 0; PR.saveSettings(); live.schedule(); toast('Saved'); PR.back(); };
    $('#s-clear').onclick = () => { localStorage.removeItem('pr_latest'); state.data = null; state.days = {}; state.teams = {}; toast('Saved data cleared'); state.stack = []; PR.loadData(true); };
    $('#s-goals').onchange = (e) => { settings.goalAlerts = e.target.checked; PR.saveSettings(); };
    $$('[data-th]').forEach((b) => { b.onclick = () => { settings.theme = b.dataset.th; PR.saveSettings(); PR.applyTheme(); PR.render(); }; });
    const n = $('#s-notif'); if (n) n.onclick = () => { if (PR.native && PR.native.requestNotifications) PR.native.requestNotifications(); };
    const c = $('#s-check'); if (c) c.onclick = () => { toast('Checking…'); state.updateChecked = 'manual'; if (PR.native && PR.native.checkUpdate) PR.native.checkUpdate(); else toast('Updates are only available in the Android app'); };
    const i = $('#s-install'); if (i) i.onclick = () => PR.startUpdate();
  };
})(window.PR);
