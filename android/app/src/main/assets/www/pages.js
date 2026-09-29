/* PlayReport — stacked pages: match, team, day, analysis, performance, guide, settings. */
(function (PR) {
  'use strict';
  const { $, $$, esc, pct, f1, f2, signed, state, settings, fx, pill, koShort, koTime, dayName, niceDate, toast, selLabel, selGroup,
    GROUPS, liveVerdict, isLive, isFT, segmented, select, contactCard, teamLink, statusIcon, formBadges, wdl, md, icon, flag, badge, fxBadge, matchRow, ring, skeleton, parseLocal, tzNow } = PR;
  const GICON = { result: 'shield', dc: 'swap', goals: 'ball', btts: 'swap', team: 'target', corners: 'corner', cards: 'card' };
  const view = () => $('#view');
  const live = PR.live;
  const MK = { O15: 'Over 1.5 goals', O25: 'Over 2.5 goals', BTTS: 'Both teams to score' };
  const head = (title, sub, right) => `<div class="detail-head"><button class="back" id="back" aria-label="Back">${icon('back')}</button><div class="grow"><div class="b">${title}</div>${sub ? `<div class="tiny muted">${sub}</div>` : ''}</div>${right || ''}</div>`;
  function wireBack() { const b = $('#back'); if (b) b.onclick = () => PR.back(); }
  function ensureTeams(div) { if (!PR.teamsCached(div)) PR.loadTeams(div).then(() => PR.render()).catch(() => { state.teams[PR.slug(div)] = { missing: true }; }); }
  const rec = (div, name) => { const t = PR.teamsCached(div); return t && t.teams ? t.teams[name] : null; };
  const ord = (n) => { const s = ['th', 'st', 'nd', 'rd'], v = n % 100; return s[(v - 20) % 10] || s[v] || s[0]; };
  // index rows keep xg/x12 as arrays, detail files as objects — read both
  const xgH = (f) => Array.isArray(f.xg) ? f.xg[0] : (f.xg || {}).home;
  const xgA = (f) => Array.isArray(f.xg) ? f.xg[1] : (f.xg || {}).away;
  const x12 = (f, k) => Array.isArray(f.x12) ? f.x12[{ H: 0, D: 1, A: 2 }[k]] : (f.x12 || {})[k];

  // ------------------------------------------------------------------ live extras (statistics, line-ups) fetched on demand
  const LS = 'https://prod-public-api.livescore.com/v1/api/app';
  state.lsx = state.lsx || {};
  function lsx(kind, eid, ttlMs) {
    const key = `${kind}:${eid}`; const c = state.lsx[key];
    if (c && (c.loading || Date.now() - c.t < ttlMs)) return c.data || null;
    state.lsx[key] = { loading: true, t: Date.now(), data: c ? c.data : null };
    PR.getJson(`${LS}/${kind}/soccer/${eid}`).then((j) => { state.lsx[key] = { t: Date.now(), data: j || {} }; PR.render(); }).catch(() => { state.lsx[key] = { t: Date.now(), data: c ? c.data : {} }; });
    return c ? c.data : null;
  }
  const fmtValue = (v) => v == null ? '–' : v >= 1e9 ? `€${(v / 1e9).toFixed(2)}bn` : v >= 1e6 ? `€${(v / 1e6).toFixed(1)}M` : `€${Math.round(v / 1e3)}K`;
  PR.fmtValue = fmtValue;
  function statsCard(f, s, sc) {
    // in play / finished: Livescore statistics; older finished matches: the stats saved in the day file
    let st = null;
    if (f.livescore_id && s && s.hg != null) {
      const j = lsx('statistics', f.livescore_id, isLive(s) ? 60000 : 3600000);
      const T = j && j.Stat ? Object.fromEntries(j.Stat.map((t) => [t.Tnb, t])) : null;
      if (T && T[1] && T[2]) {
        const g = (t, k) => t[k] == null ? null : +t[k]; const shots = (t) => (g(t, 'Shon') || 0) + (g(t, 'Shof') || 0) + (g(t, 'Shbl') || 0);
        st = [['Possession', g(T[1], 'Pss'), g(T[2], 'Pss'), '%'], ['Shots', shots(T[1]), shots(T[2])], ['On target', g(T[1], 'Shon'), g(T[2], 'Shon')], ['Corners', g(T[1], 'Cos'), g(T[2], 'Cos')], ['Fouls', g(T[1], 'Fls'), g(T[2], 'Fls')], ['Offsides', g(T[1], 'Ofs'), g(T[2], 'Ofs')], ['Yellow cards', g(T[1], 'Ycs'), g(T[2], 'Ycs')], ['Red cards', g(T[1], 'Rcs'), g(T[2], 'Rcs')]];
      }
    }
    if (!st && sc && (sc.hc != null || sc.hs != null || sc.hposs != null)) st = [['Possession', sc.hposs, sc.aposs, '%'], ['Shots', sc.hs, sc.as], ['On target', sc.hst, sc.ast], ['Corners', sc.hc, sc.ac], ['Fouls', sc.hf, sc.af], ['Yellow cards', sc.hy, sc.ay], ['Red cards', sc.hr, sc.ar]];
    state.lastStats = st ? st.filter(([, a, b]) => a != null || b != null) : null;
    if (!st) return '';
    const rows = st.filter(([, a, b]) => a != null || b != null).map(([k, a, b, unit]) => { const tot = (a || 0) + (b || 0); const wa = tot ? (a || 0) / tot : 0, wb = tot ? (b || 0) / tot : 0;
      return `<div class="statbar"><span class="${a > b ? 'lead' : ''}">${a == null ? '–' : a}${unit || ''}</span><div><div class="k">${k}</div><div class="duo"><span class="l" style="width:${Math.round(wa * 50)}%"></span><span class="r" style="width:${Math.round(wb * 50)}%"></span></div></div><span class="${b > a ? 'lead' : ''}">${b == null ? '–' : b}${unit || ''}</span></div>`; }).join('');
    return rows ? `<div class="card compact"><div class="row"><div class="grow b">${icon('chart', 'sm')} Match statistics</div><span class="tiny muted">${s && isLive(s) ? 'live' : 'full time'}</span></div>${rows}</div>` : '';
  }
  function lineupsBlock(f, s) {
    if (!f.livescore_id) return `<div class="card tiny muted">Line-ups are not available for this match.</div>`;
    const ko = parseLocal(f.kickoff); const soon = ko && (ko - tzNow()) < 2 * 3600000;
    if (!soon && !(s && s.hg != null)) return `<div class="card empty">Line-ups are published about an hour before kick-off (${esc(koShort(f.kickoff))}).</div>`;
    const j = lsx('lineups', f.livescore_id, s && isLive(s) ? 300000 : 1800000);
    if (j == null) return skeleton(6);
    const lu = (j.Lu || []); if (!lu.length) return `<div class="card empty">Line-ups not published yet — check back closer to kick-off.</div>`;
    const team = (t, name, side) => { const ps = (t.Ps || []); const xi = ps.filter((p) => p.Pos >= 1 && p.Pos <= 4).sort((a, b) => a.Pos - b.Pos || (a.Fp || '').localeCompare(b.Fp || '')); const subs = ps.filter((p) => p.Pos === 5); const coach = ps.find((p) => p.Pos === 10);
      const pl = (p) => `<div class="pl"><span class="no">${p.Snu != null ? p.Snu : ''}</span><span class="grow">${esc(p.Snm || [p.Fn, p.Ln].filter(Boolean).join(' '))}</span>${p.Mo != null ? `<span class="pos">${p.Pos === 5 ? '▲' : '▼'} ${p.Mo}'</span>` : `<span class="pos">${esc((p.Pon || '').slice(0, 3).toUpperCase())}</span>`}</div>`;
      return `<div><div class="b row" style="gap:6px">${fxBadge(f, side).replace('s24', 's20')}${esc(name)}</div>${t.Fo ? `<div class="tiny muted">${t.Fo.join('-')}</div>` : ''}<h4>Starting XI</h4>${xi.map(pl).join('')}${subs.length ? `<h4>Substitutes</h4>${subs.map(pl).join('')}` : ''}${coach ? `<h4>Coach</h4><div class="pl"><span class="no"></span><span>${esc(coach.Snm || [coach.Fn, coach.Ln].filter(Boolean).join(' '))}</span></div>` : ''}</div>`; };
    const h = lu.find((t) => t.Tnb === 1) || lu[0], a = lu.find((t) => t.Tnb === 2) || lu[1];
    return `<div class="card"><div class="lineup">${h ? team(h, f.home, 'home') : ''}${a ? team(a, f.away, 'away') : ''}</div><div class="tiny muted" style="margin-top:8px">Source: public live feed. ▼ substituted off · ▲ came on.</div></div>`;
  }

  // ------------------------------------------------------------------ MATCH PAGE
  PR.pages.match = function (page) {
    const f0 = fx(page.id); const key = PR.detailKey(page.id, page.d);
    let x = PR.detailCached(page.id, page.d);
    if (!x && key && !state.details[key + '_loading']) {
      state.details[key + '_loading'] = true;
      PR.loadDetail(page.id, page.d).then(() => PR.render()).catch((e) => { state.details[key] = { error: e.message }; PR.render(); }).finally(() => { delete state.details[key + '_loading']; });
    }
    if (x && x.error) x = null;
    const drec = PR.dayRecord(page.id);
    const archived = !x && !f0 && drec && (state.details[key] && state.details[key].error || !key);
    if (archived) { archiveMatchPage(drec); return; }
    const f = x || f0;
    if (!f) { view().innerHTML = head('Match') + (state.details[key] && state.details[key].error ? `<div class="card empty">This match is no longer available (${esc(state.details[key].error)}).</div>` : skeleton(6)); wireBack(); return; }
    ensureTeams(f.div);
    const fin = PR.finalFor(f);
    const s0 = live.for(f); const s = s0 && s0.hg != null ? s0 : (fin ? { status: 'FT', hg: fin.hg, ag: fin.ag, ht: [fin.hth, fin.hta], t: 0, stored: true } : s0);
    const d = state.data; const v = state.matchView || 'overview';
    const th = rec(f.div, f.home), ta = rec(f.div, f.away);
    const fav = PR.isFav(f.id);
    const parts = [head(`${flag(f.country)} ${esc(f.competition)}`, `${esc(dayName(f.kickoff))} · ${esc(koTime(f.kickoff))} ${esc(d.meta.tz)}${f.time_known === false ? ' (time to be confirmed)' : ''}${f.referee ? ' · referee ' + esc(f.referee) : ''}`,
      f0 ? `<button class="favbtn ${fav ? 'on' : ''}" id="fav-btn" title="${fav ? 'Remove from favourites' : 'Add to favourites'}" aria-label="Favourite">${fav ? '★' : '☆'}</button>` : '')];
    const form = (p) => p && p.last5 ? formBadges(p.last5.slice().reverse().map((m) => wdl(m.gf, m.ga))) : '';
    const teams = (x && x.teams) || { home: {}, away: {} };
    const sq = (x && x.squad) || {}; const val = (side) => sq[side] && sq[side].value ? `<div class="value-tag">💶 ${fmtValue(sq[side].value)}</div>` : '';
    parts.push(`<div class="card mhead"><div class="teams">
      <div class="t">${fxBadge(f, 'home').replace('s24', 's56')}${teamLink(f, 'home')}<div class="tiny muted">${th && th.pos ? `${th.pos}${ord(th.pos)} · ${th.all.pts} pts` : 'Home'}</div>${form(teams.home)}${val('home')}</div>
      <div class="mid">${s && s.hg != null ? `<div class="score big">${s.hg} – ${s.ag}</div><div class="minute ${isLive(s) ? 'on' : 'ft'}">${esc(isFT(s) ? 'FT' : s.status)}</div>${s.ht && s.ht[0] != null && s.ht[0] !== '' ? `<div class="tiny muted">HT ${esc(s.ht[0])}–${esc(s.ht[1])}</div>` : ''}` : `<div class="score big muted">${esc(koTime(f.kickoff))}</div><div class="tiny muted">${esc(koShort(f.kickoff).split(' ')[0])} · ${esc(d.meta.tz)}</div>`}</div>
      <div class="t">${fxBadge(f, 'away').replace('s24', 's56')}${teamLink(f, 'away')}<div class="tiny muted">${ta && ta.pos ? `${ta.pos}${ord(ta.pos)} · ${ta.all.pts} pts` : 'Away'}</div>${form(teams.away)}${val('away')}</div></div>
      <div class="x12"><div class="lbl"><span>${esc(f.home)} ${pct(x12(f, 'H'))}</span><span>Draw ${pct(x12(f, 'D'))}</span><span>${esc(f.away)} ${pct(x12(f, 'A'))}</span></div>
        <div class="tri"><span class="h" style="width:${Math.round((x12(f, 'H') || 0) * 100)}%"></span><span class="d" style="width:${Math.round((x12(f, 'D') || 0) * 100)}%"></span><span class="a" style="width:${Math.round((x12(f, 'A') || 0) * 100)}%"></span></div></div>
      <div class="chips small-chips" style="margin-top:6px;justify-content:center">${qualityChip(f)}${f.data_ok ? '' : '<span class="chip warn">⚠️ low data — never shortlisted</span>'}</div></div>`);
    parts.push(`<div class="card compact">${segmented([['overview', 'Overview'], ['form', 'Form'], ['markets', 'Markets'], ['trends', 'Trends'], ['stats', 'Stats'], ['table', 'Table'], ['h2h', 'H2H'], ['news', 'News'], ['data', 'Data'], ['lineups', 'Line-ups']], v, 'mv')}</div>`);
    if (v === 'lineups') parts.push(lineupsBlock(f, s));
    else if (!x) parts.push(skeleton(5));
    else if (v === 'overview') matchOverview(parts, x, s);
    else if (v === 'form') matchForm(parts, f);
    else if (v === 'trends') matchTrends(parts, x);
    else if (v === 'markets') matchMarkets(parts, x);
    else if (v === 'stats') matchStats(parts, x, th, ta);
    else if (v === 'table') matchTable(parts, f, th, ta);
    else if (v === 'news') matchNews(parts, f, x);
    else if (v === 'data') matchData(parts, x);
    else matchH2H(parts, x);
    if (x) parts.push(`<div class="card compact"><div class="small muted">Detailed stats of this analysis as a spreadsheet file — probabilities, prices, team profiles, recent form, head-to-head, trends, corners & cards (opens in Google Sheets / Excel).</div><button class="btn" id="dl-csv" style="margin-top:8px;width:100%">${icon('download', 'sm')} Download stats (CSV)</button></div>`);
    view().innerHTML = parts.join('');
    wireBack();
    const fb = $('#fav-btn'); if (fb) fb.onclick = () => PR.toggleFav(f.id);
    const dl = $('#dl-csv'); if (dl) dl.onclick = () => PR.downloadMatchCsv(x, s, state.lastStats);
    $$('[data-mv]').forEach((b) => { b.onclick = () => { state.matchView = b.dataset.mv; PR.render(); }; });
  };
  /** Goals / red cards: live incidents while the match is on, the stored ones from the archive afterwards. */
  function eventsCard(f, fin) {
    const live = f.livescore_id && state.incidents[f.livescore_id];
    const items = live && live.items.length ? live.items : PR.storedIncidents(fin);
    if (!items || !items.length) return '';
    const side = (t) => `<div class="ev ${t === 'H' ? 'h' : 'a'}">`;
    return `<div class="card compact"><div class="row"><div class="grow b">${icon('ball', 'sm')} Match events</div><span class="tiny muted">${live && live.items.length ? 'live' : 'archive'}</span></div>
      <div class="events">${items.map((it) => `${side(it.team)}<span class="who">${it.team === 'H' ? esc(f.home) : esc(f.away)}</span><span class="what">${PR.incidentLine(it)}</span></div>`).join('')}</div></div>`;
  }
  /** Match page for a finished match whose detailed analysis file has been retired: everything comes from the
   *  day archive (final score, half-time, statistics, goals, the model's numbers at kick-off and the bets). */
  function archiveMatchPage(r) {
    const sc = r.score || {}; const fin = sc.hg != null ? sc : null; const d = state.data;
    const f = { id: r.id, home: r.home, away: r.away, home_long: r.home_long, away_long: r.away_long, country: r.country, league: r.league, competition: r.competition, div: r.div, kickoff: r.kickoff, livescore_id: r.livescore_id, badges: r.badges, p: r.p || {}, xg: r.xg, x12: r.x12, data_ok: r.data_ok };
    const s = fin ? { status: sc.status || 'FT', hg: sc.hg, ag: sc.ag, ht: [sc.hth, sc.hta], t: 0 } : (sc.status ? { status: sc.status, hg: null, ag: null } : null);
    const parts = [head(`${flag(f.country)} ${esc(f.competition || f.league || '')}`, `${esc(dayName(f.kickoff))} · ${esc(koTime(f.kickoff))} ${esc(d.meta.tz)} · archive`)];
    parts.push(`<div class="card mhead"><div class="teams">
      <div class="t">${fxBadge(f, 'home').replace('s24', 's56')}<div class="nm b">${esc(f.home_long || f.home)}</div><div class="tiny muted">Home</div></div>
      <div class="mid">${s && s.hg != null ? `<div class="score big">${s.hg} – ${s.ag}</div><div class="minute ft">FT</div>${s.ht && s.ht[0] != null ? `<div class="tiny muted">HT ${s.ht[0]}–${s.ht[1]}</div>` : ''}` : `<div class="score big muted">${esc(koTime(f.kickoff))}</div><div class="tiny muted">${esc(s && s.status ? s.status : 'no result recorded')}</div>`}</div>
      <div class="t">${fxBadge(f, 'away').replace('s24', 's56')}<div class="nm b">${esc(f.away_long || f.away)}</div><div class="tiny muted">Away</div></div></div>
      ${Array.isArray(f.x12) && f.x12[0] != null ? `<div class="x12"><div class="lbl"><span>${esc(f.home)} ${pct(f.x12[0])}</span><span>Draw ${pct(f.x12[1])}</span><span>${esc(f.away)} ${pct(f.x12[2])}</span></div><div class="tri"><span class="h" style="width:${Math.round(f.x12[0] * 100)}%"></span><span class="d" style="width:${Math.round(f.x12[1] * 100)}%"></span><span class="a" style="width:${Math.round(f.x12[2] * 100)}%"></span></div></div>` : ''}</div>`);
    const st = statsCard(f, s, fin); if (st) parts.push(st);
    else if (fin) parts.push(`<div class="card tiny muted">No match statistics were published for this competition. The final score${fin.inc ? ' and goals are' : ' is'} kept.</div>`);
    const evs = eventsCard(f, fin); if (evs) parts.push(evs);
    if (f.xg || (f.p && f.p.O25 != null)) parts.push(`<div class="card compact"><div class="b">Model at kick-off</div><div class="grid4" style="margin-top:6px">${Array.isArray(f.xg) ? `<div class="cell"><div class="k">Model xG</div><div class="v">${f1(f.xg[0])} – ${f1(f.xg[1])}</div></div>` : ''}<div class="cell"><div class="k">Over 1.5</div><div class="v">${pct(f.p.O15)}</div></div><div class="cell"><div class="k">Over 2.5</div><div class="v">${pct(f.p.O25)}</div></div><div class="cell"><div class="k">BTTS</div><div class="v">${pct(f.p.BTTS)}</div></div></div>
      ${(r.top || []).length ? `<div class="tiny muted" style="margin-top:6px">Top priced selections at the time: ${r.top.map((t) => `${esc(t.label || t[0] || '')}${t.p != null ? ' ' + pct(t.p) : ''}${t.odds ? ' @ ' + f2(t.odds) : ''}`).join(' · ')}</div>` : ''}</div>`);
    const bets = r.bets || [];
    if (bets.length) parts.push(`<div class="card compact"><div class="b">Bets on this match</div><div class="chips" style="margin-top:6px">${bets.map((b) => `<span class="chip ${b.status === 'hit' ? 'good' : b.status === 'miss' ? 'bad' : ''}">${b.botd ? '⭐ ' : ''}${esc(b.label)}${b.odds ? ' @ ' + f2(b.odds) : ''} ${statusIcon(b.status)}</span>`).join('')}</div></div>`);
    parts.push(`<div class="card tiny muted">The full pre-match analysis (trends, markets, data audit) is kept for 14 days; the result, statistics and goals stay in the day archive for 60 days.</div>`);
    view().innerHTML = parts.join('');
    wireBack();
  }
  function matchOverview(parts, f, s) {
    const xg = f.xg || {}; const q = f.quality || null; const conf = f.confidence || {};
    const mk = xg.market_home != null ? `<div class="cell" style="display:inline-block;margin-left:10px"><div class="k">Market xG</div><div class="v muted">${f1(xg.market_home)} – ${f1(xg.market_away)}</div><div class="tiny muted">total ${f2(xg.market_total)}</div></div>` : `<div class="cell" style="display:inline-block;margin-left:10px"><div class="k">Market xG</div><div class="v muted">N/A</div><div class="tiny muted">no prices</div></div>`;
    parts.push(`<div class="card"><div class="row"><div class="grow"><div class="cell" style="display:inline-block"><div class="k">Model xG</div><div class="v">${f1(xgH(f))} – ${f1(xgA(f))}</div><div class="tiny muted">total ${f2(xg.total)}</div></div>${mk}</div>
      <div class="rings" style="flex:2">${ring(f.p.O15, 'Over 1.5')}${ring(f.p.O25, 'Over 2.5')}${ring(f.p.BTTS, 'BTTS')}</div></div>
      <div class="tiny muted" style="margin-top:8px"><b>Model probabilities</b> from football data only (goals, form, venue, league baseline) — bookmaker prices are compared, never blended in. Confidence ${esc(conf.O25 || 'N/A')}${q ? ` · data quality ${esc(q.overall)}` : ''} · samples ${(f.teams.home || {}).n || 0} / ${(f.teams.away || {}).n || 0} matches · league avg ${f2((f.league_avg.home_goals || 0) + (f.league_avg.away_goals || 0))} goals, O2.5 in ${pct(f.league_avg.o25)}${xg.market_total != null ? ` · model v market total ${(xg.total - xg.market_total) >= 0 ? '+' : ''}${f2(xg.total - xg.market_total)}` : ''}</div></div>`);
    const warns = (f.warnings || []).filter((w) => w.level === 'warn');
    if (warns.length) parts.push(`<div class="card compact"><div class="b">${icon('alert', 'sm')} Checks</div><div class="small" style="margin-top:4px">${warns.slice(0, 4).map((w) => `<div>⚠️ ${esc(w.text)}</div>`).join('')}</div><div class="tiny muted" style="margin-top:4px">All checks under Data.</div></div>`);
    const fin0 = PR.finalFor(f);
    const sc0 = statsCard(f, s, fin0); if (sc0) parts.push(sc0);
    else if (s && s.hg != null && !isLive(s)) parts.push(`<div class="card tiny muted">No match statistics were published for this competition (Livescore covers statistics for the bigger leagues only). The final score and goals are kept.</div>`);
    const evs = eventsCard(f, fin0); if (evs) parts.push(evs);
    const bets = betsOn(f.id);
    if (bets.length) parts.push(`<div class="card compact"><div class="b">Bets on this match</div><div class="chips" style="margin-top:6px">${bets.map((b) => { const vd = liveVerdict(b.sel, s); return `<span class="chip ${vd.cls}">${esc(b.kind)}: ${esc(b.label)}${b.odds ? ' @ ' + f2(b.odds) : ''} · ${esc(vd.text)}</span>`; }).join('')}</div></div>`);
    const best = f.sels.filter((x) => x.odds && x.odds >= 1.25 && !x.diff).slice(0, 5);
    if (best.length) parts.push(`<div class="card compact"><div class="row"><div class="grow b">${icon('target', 'sm')} Highest model probabilities (priced)</div><span class="tiny muted">+ adds to your slip</span></div><table class="tbl">${best.map((x) => `<tr><td><div class="b">${esc(selLabel(x.sel, f.home, f.away))}</div><div class="tiny muted">${esc(GROUPS[selGroup(x.sel)])} · market implied ${pct(x.p_sb)}${x.diff_pp != null ? ` · ${x.diff_pp >= 0 ? '+' : ''}${f1(x.diff_pp)} pp` : ''}</div></td><td class="right"><b>${f2(x.odds)}</b></td><td class="right"><div class="row" style="gap:0;justify-content:flex-end">${pill(x.p, 0.8, 0.7)}${PR.addBtn ? PR.addBtn(f.id, x.sel, x.odds) : ''}</div></td></tr>`).join('')}</table></div>`);
    const tr = f.trends || {}; const topTrends = [].concat((tr.match || []).filter((t) => t.kind !== 'info'), (tr.home && tr.home.all || []).slice(0, 2), (tr.away && tr.away.all || []).slice(0, 2), (tr.h2h || []).slice(0, 1)).slice(0, 5);
    if (topTrends.length) parts.push(`<div class="card compact tap" id="go-trends"><div class="row"><div class="grow b">${icon('trend', 'sm')} Trends</div><span class="tiny muted">all ${icon('next', 'sm')}</span></div><div class="trends">${topTrends.map(trendLine).join('')}</div></div>`);
    const sb = f.sportybet || {};
    if (Object.keys(sb).length) {
      const ou = sb.OU || {};
      parts.push(`<div class="card compact"><div class="b">Sportybet prices</div><table class="tbl head" style="margin-top:6px"><tr><th>Market</th><th class="right">1 / Over / Yes</th><th class="right">X</th><th class="right">2 / Under / No</th></tr>
        ${sb['1X2'] ? `<tr><td>Match result</td><td class="right">${f2(sb['1X2'][0])}</td><td class="right">${f2(sb['1X2'][1])}</td><td class="right">${f2(sb['1X2'][2])}</td></tr>` : ''}
        ${sb.DC ? `<tr><td>Double chance 1X · 12 · X2</td><td class="right">${f2(sb.DC['1X'])}</td><td class="right">${f2(sb.DC['12'])}</td><td class="right">${f2(sb.DC.X2)}</td></tr>` : ''}
        ${['0.5', '1.5', '2.5', '3.5', '4.5'].filter((l) => ou[l]).map((l) => `<tr><td>Goals ${l}</td><td class="right">${f2(ou[l][0])}</td><td></td><td class="right">${f2(ou[l][1])}</td></tr>`).join('')}
        ${sb.BTTS ? `<tr><td>Both teams to score</td><td class="right">${f2(sb.BTTS[0])}</td><td></td><td class="right">${f2(sb.BTTS[1])}</td></tr>` : ''}</table>
        <div class="tiny muted" style="margin-top:4px">Prices are payout information and a comparison layer — they never change the model probability. All lines under Markets.</div></div>`);
    } else parts.push(`<div class="card tiny muted">No Sportybet price for this match — no market comparison available.</div>`);
    setTimeout(() => { const g = $('#go-trends'); if (g) g.onclick = () => { state.matchView = 'trends'; PR.render(); }; }, 0);
  }
  const TICON = { goals: '⚽', ht: '⏱️', corners: '🚩', cards: '🟨', form: '📈', info: 'ℹ️' };
  function trendLine(t) {
    const r = t.r == null ? null : Math.round(t.r * 100);
    const ev = t.n > 0 && t.kind !== 'info' ? `<span class="tiny muted"> · ${t.n} match${t.n === 1 ? '' : 'es'}, ${evidenceLabel(t.n).toLowerCase()} evidence</span>` : '';
    return `<div class="trend ${t.kind}"><span class="ti">${TICON[t.kind] || '•'}</span><span class="tt">${esc(t.t)}${ev}</span>${r != null && t.n > 0 && t.kind !== 'form' ? `<span class="tr" title="historical frequency"><span class="bar"><span class="fill ${r >= 80 ? 'hi' : r >= 65 ? 'mid' : ''}" style="width:${r}%"></span></span><b>${r}%</b></span>` : ''}</div>`;
  }
  function matchTrends(parts, f) {
    const tr = f.trends || {}; const any = (tr.match || []).length || (tr.home && tr.home.all.length) || (tr.away && tr.away.all.length) || (tr.h2h || []).length;
    parts.push(`<div class="card tiny muted">Streaks and <b>historical frequencies</b> from the last 10 matches of each team (and the last 5 at this venue), all competitions. "9 of 10" is what happened (90% frequency), not a probability — the model probabilities on the Overview already include recent form. Samples this small are weak evidence on their own.</div>`);
    if (!any) { parts.push(`<div class="card empty">Not enough recent matches for trends.</div>`); return; }
    const block = (title, items, sub) => items && items.length ? `<div class="card compact"><div class="row"><div class="grow b">${title}</div>${sub ? `<span class="tiny muted">${sub}</span>` : ''}</div><div class="trends">${items.map(trendLine).join('')}</div></div>` : '';
    parts.push(block(`${icon('swap', 'sm')} Match trends`, tr.match));
    parts.push(block(`${fxBadge(f, 'home').replace('s24', 's20')} ${esc(f.home)}`, tr.home && tr.home.all, `last ${tr.home ? tr.home.n : 0}`));
    parts.push(block(`${fxBadge(f, 'home').replace('s24', 's20')} ${esc(f.home)} at home`, tr.home && tr.home.venue));
    parts.push(block(`${fxBadge(f, 'away').replace('s24', 's20')} ${esc(f.away)}`, tr.away && tr.away.all, `last ${tr.away ? tr.away.n : 0}`));
    parts.push(block(`${fxBadge(f, 'away').replace('s24', 's20')} ${esc(f.away)} away`, tr.away && tr.away.venue));
    parts.push(block(`${icon('history', 'sm')} Head to head`, tr.h2h));
  }
  function betsOn(fid) {
    const d = state.data, out = [], sf = d.safe || { bets: [] };
    ((sf.today && sf.today.bets) || []).filter((b) => b.fixture === fid).forEach((b) => out.push({ kind: '⭐ Bet of the day', label: b.label, sel: b.sel, odds: b.odds }));
    sf.bets.filter((b) => b.fixture === fid && !out.some((o) => o.sel === b.sel)).forEach((b) => out.push({ kind: '📈 High probability', label: b.label, sel: b.sel, odds: b.odds }));
    Object.entries(d.picks || {}).forEach(([mk, lst]) => lst.filter((p) => p.fixture === fid).forEach(() => out.push({ kind: 'Shortlist', label: MK[mk], sel: mk })));
    if (PR.tickets) PR.tickets().forEach((t) => { if (t.status === 'pending') t.legs.filter((l) => l.fixture === fid).forEach((l) => out.push({ kind: '🎫 My ticket', label: l.label, sel: l.sel, odds: l.odds })); });
    return out;
  }
  function matchMarkets(parts, f) {
    const groups = {};
    f.sels.forEach((s) => { (groups[selGroup(s.sel)] = groups[selGroup(s.sel)] || []).push(s); });
    parts.push(`<div class="card tiny muted">Every modelled market. <b>Model</b> = football-data model probability (used for ranking). <b>Market</b> = Sportybet price with the margin removed — a comparison, never an input. <b>Diff</b> = model − market in points; <b>EV</b> = model % × price − 1. Rows at ≥ 70% model probability are highlighted; ⚠ = model / market disagreement of more than 12 points. Tap <b>+</b> to put a priced selection on your bet slip.</div>`);
    Object.keys(GROUPS).forEach((g) => {
      const items = groups[g]; if (!items) return;
      const order = { result: ['H', 'D', 'A'], dc: ['1X', '12', 'X2'], btts: ['BTTS', 'NBTTS'] }[g];
      const sorted = order ? items.slice().sort((a, b) => order.indexOf(a.sel) - order.indexOf(b.sel)) : items.slice().sort((a, b) => a.sel.localeCompare(b.sel, undefined, { numeric: true }));
      parts.push(`<div class="card compact"><div class="row" style="margin:4px 0 2px"><span class="ico">${icon(GICON[g] || 'ball')}</span><b>${GROUPS[g]}</b>${(g === 'corners' || g === 'cards') && lowCount(f, g) ? '<span class="chip warn" style="margin-left:6px">LOW DATA CONFIDENCE</span>' : ''}</div><table class="tbl head" style="margin-top:4px"><tr><th>Selection</th><th class="right">Market</th><th class="right">Diff</th><th class="right">Price · EV</th><th class="right">Model</th></tr>
        ${sorted.map((s) => `<tr class="${s.p >= 0.7 ? 'hl' : ''}"><td>${esc(selLabel(s.sel, f.home, f.away))}${s.diff ? ' <span class="warn">⚠</span>' : ''}</td><td class="right muted">${pct(s.p_sb)}</td><td class="right muted">${s.diff_pp == null ? '–' : `${s.diff_pp >= 0 ? '+' : ''}${Math.round(s.diff_pp)}`}</td><td class="right">${s.odds ? `<b>${f2(s.odds)}</b><div class="tiny ${s.ev > 0.02 ? 'pos' : 'muted'}">${s.ev == null ? '' : (s.ev >= 0 ? '+' : '') + Math.round(100 * s.ev) + '%'}</div>` : '<span class="muted">–</span>'}</td><td class="right"><div class="row" style="gap:0;justify-content:flex-end">${pill(s.p_model, 0.8, 0.7)}${PR.addBtn ? PR.addBtn(f.id, s.sel, s.odds) : ''}</div></td></tr>`).join('')}</table></div>`);
    });
    const sb = f.sportybet || {};
    const lines = (obj, label) => obj ? `<tr><td>${label}</td><td colspan="4" class="tiny">${Object.entries(obj).sort((a, b) => +a[0] - +b[0]).map(([k, v]) => `<span class="chip">${k}: ${f2(v[0])} / ${f2(v[1])}</span>`).join(' ')}</td></tr>` : '';
    if (sb.CORN || sb.CARDS || sb.CORNH || sb.CORN1H) parts.push(`<div class="card compact"><div class="b">More Sportybet lines (over / under)</div><table class="tbl" style="margin-top:4px">${lines(sb.CORN, 'Corners')}${lines(sb.CORN1H, '1st-half corners')}${lines(sb.CORNH, 'Home corners')}${lines(sb.CORNA, 'Away corners')}${lines(sb.CARDS, 'Cards')}${lines(sb.CARDSH, 'Home cards')}${lines(sb.CARDSA, 'Away cards')}</table></div>`);
    if (f.corners || f.cards) parts.push(`<div class="card compact"><div class="b">Expected counts (own corner / card models)</div><div class="grid4" style="margin-top:6px">${f.corners ? `<div class="cell"><div class="k">Corners</div><div class="v">${f1(f.corners.total)}</div><div class="tiny muted">${f1(f.corners.home)} – ${f1(f.corners.away)}${countN(f.corners)}</div></div>` : ''}${f.cards ? `<div class="cell"><div class="k">Cards</div><div class="v">${f1(f.cards.total)}</div><div class="tiny muted">${f1(f.cards.home)} – ${f1(f.cards.away)}${countN(f.cards)}</div></div>` : ''}</div></div>`);
    else parts.push(`<div class="card tiny muted">Corners and cards are modelled for the 22 main European leagues, where match statistics are published.</div>`);
  }
  // ------------------------------------------------------------------ DATA / AUDIT TAB (data-first engine)
  const EVIDENCE = [[40, 'Very strong'], [20, 'Strong'], [10, 'Moderate'], [5, 'Small'], [1, 'Very small']];
  function evidenceLabel(n) { if (!n || n < 1) return 'No data'; for (const [lo, name] of EVIDENCE) if (n >= lo) return name; return 'Very small'; }
  function evChip(n) { const l = evidenceLabel(n); const cls = n >= 20 ? 'ok' : n >= 10 ? '' : 'warn'; return `<span class="chip ${cls}">${n || 0} match${n === 1 ? '' : 'es'} · ${l}</span>`; }
  function qualityChip(f) { const q = f.quality || (f.q ? { overall: f.q } : null); if (!q) return ''; const cls = q.overall === 'High' ? 'ok' : q.overall === 'Low' ? 'warn' : ''; return `<span class="chip ${cls}">data quality ${esc(q.overall)}${q.score != null ? ' · ' + q.score : ''}</span>`; }
  function lowCount(f, g) { const c = g === 'corners' ? f.corners : f.cards; return c && c.low_confidence; }
  function countN(c) { return c && c.n ? ` · ${c.n[0]} / ${c.n[1]} matches with stats${c.low_confidence ? ' · LOW DATA CONFIDENCE' : ''}` : ''; }
  const na = (v, fmt) => v == null ? '<span class="muted">N/A</span>' : (fmt || ((x) => x))(v);
  function expandMatches(m) { return m && m.cols ? (m.rows || []).map((r) => { const o = {}; m.cols.forEach((c, i) => { o[c] = r[i]; }); return o; }) : (m || []); }
  function matchData(parts, f) {
    const q = f.quality, ev = f.evidence, ex = f.explain, mk = f.market, h2h = f.h2h_meta, conf = f.confidence || {};
    if (!q || !ev) { parts.push(`<div class="card empty">No data audit for this match yet — it was analysed before the data-first engine. The next scan adds it.</div>`); return; }
    parts.push(`<div class="card tiny muted"><b>Vocabulary.</b> Historical frequency = what happened in the sample ("scored in 9 of 10" = 90%). Model probability = the football-data model. Market implied = the bookmaker price with the margin removed (comparison only, never a model input). Missing data is shown as N/A, never as 0.</div>`);
    // 1. data quality
    const qcls = q.overall === 'High' ? 'ok' : q.overall === 'Low' ? 'warn' : '';
    parts.push(`<div class="card compact"><div class="row"><div class="grow b">${icon('shield', 'sm')} Data quality</div><span class="chip ${qcls}">${esc(q.overall)} · ${q.score}</span></div>
      <table class="tbl" style="margin-top:6px">${Object.entries(q.components || {}).map(([k, v]) => `<tr><td class="nowrap" style="text-transform:capitalize">${esc(k)}</td><td class="right"><b>${Math.round(v.score * 100)}%</b></td><td class="tiny muted">${esc(v.reason)}</td></tr>`).join('')}</table>
      <div class="tiny muted" style="margin-top:6px">${q.missing_fields && q.missing_fields.length ? `Missing: ${esc(q.missing_fields.join(', '))}. ` : ''}Sources: ${esc((q.sources || []).join('; '))}. Collected ${esc(q.collected || '')}. ${esc(q.note || '')}</div></div>`);
    // 2. warnings
    const ws = f.warnings || [];
    parts.push(`<div class="card compact"><div class="b">${icon('alert', 'sm')} Checks &amp; warnings</div><div class="small" style="margin-top:4px">${ws.length ? ws.map((w) => `<div style="margin:3px 0">${w.level === 'warn' ? '⚠️' : 'ℹ️'} ${esc(w.text)}</div>`).join('') : '<span class="muted">No warnings — the model and the raw data agree, samples are adequate.</span>'}</div></div>`);
    // 3. model explanation
    if (ex) {
      const lg = ex.league || {}, lh = ex.lambda_home || {}, la = ex.lambda_away || {};
      const rt = (r) => r ? `raw ${na(r.att_raw, f2)} / ${na(r.def_raw, f2)} → venue blend ${na(r.att_blend, f2)} / ${na(r.def_blend, f2)} (venue weight ${na(r.venue_share, pct)}) → <b>after shrinkage ${na(r.att, f2)} / ${na(r.def, f2)}</b>, weighted matches ${na(r.n_eff, f1)}${r.opp_att_faced != null ? `<div class="tiny muted">opponents faced: attack ${f2(r.opp_att_faced)} / defence ${f2(r.opp_def_faced)} (info only; opponent-adjusted raw ${na(r.att_opp_adj, f2)} / ${na(r.def_opp_adj, f2)})</div>` : ''}` : 'N/A';
      parts.push(`<div class="card compact"><div class="b">${icon('trend', 'sm')} Why ${f1(f.xg.total)} goals? — the model's own numbers</div>
        <div class="small" style="margin-top:6px"><div><b>League baseline</b> (${esc([f.country, f.league].filter(Boolean).join(' · ') || lg.div || f.div)}${lg.n_eff ? `, ${Math.round(lg.n_eff)} weighted league matches` : ''}): ${na(lg.mu_home, f2)} home + ${na(lg.mu_away, f2)} away goals per match · O2.5 in ${na(lg.o25_rate, pct)}, BTTS in ${na(lg.btts_rate, pct)} of league matches</div>
        <div style="margin-top:6px"><b>${esc(f.home)}</b> attack / defence (1.00 = league average): ${rt(ex.home)}</div>
        <div style="margin-top:6px"><b>${esc(f.away)}</b> attack / defence: ${rt(ex.away)}</div>
        <div style="margin-top:8px" class="b">Model xG ${esc(f.home)} ${na(lh.value, f2)} = ${(lh.terms || []).map(f2).join(' × ')}</div><div class="tiny muted">${esc(lh.formula || '')}</div>
        <div style="margin-top:4px" class="b">Model xG ${esc(f.away)} ${na(la.value, f2)} = ${(la.terms || []).map(f2).join(' × ')}</div><div class="tiny muted">${esc(la.formula || '')}</div>
        <table class="tbl head" style="margin-top:8px"><tr><th>Market</th><th class="right">Model</th><th class="right">Confidence</th></tr>
        <tr><td>Over 1.5 / 2.5 / 3.5</td><td class="right">${pct(f.p.O15)} / ${pct(f.p.O25)} / ${pct(f.p.O35)}</td><td class="right">${esc(conf.O25 || 'N/A')}</td></tr>
        <tr><td>Both teams to score</td><td class="right">${pct(f.p.BTTS)}</td><td class="right">${esc(conf.BTTS || 'N/A')}</td></tr>
        <tr><td>Home / draw / away</td><td class="right">${pct(x12(f, 'H'))} / ${pct(x12(f, 'D'))} / ${pct(x12(f, 'A'))}</td><td class="right">${esc(conf.X12 || 'N/A')}</td></tr></table>
        <details style="margin-top:6px"><summary class="tiny muted">How the number is built (steps)</summary><ol class="tiny muted" style="padding-left:18px;margin:4px 0">${(ex.steps || []).map((t) => `<li>${esc(t.replace(/^\d+\. /, ''))}</li>`).join('')}</ol></details></div></div>`);
    }
    // 4. team samples
    ['home', 'away'].forEach((side) => {
      const e = ev[side]; if (!e) return; const c = e.composition || {}; const sp = e.splits || {}; const rc = e.recent || {};
      const comps = Object.entries(c.competitions || {}).map(([k, v]) => `${esc(k)} ${v}`).join(', ');
      const srow = (name, st) => st ? `<tr><td class="nowrap">${name}<div class="tiny muted">${st.n} · ${esc(st.label)}</div></td><td class="right">${f2(st.gf)} / ${f2(st.ga)}</td><td class="right">${st.o15}/${st.n}</td><td class="right">${st.o25}/${st.n}</td><td class="right">${st.btts}/${st.n}</td><td class="right">${st.cs}/${st.n}</td><td class="right tiny">${st.sot_for == null ? '<span class="muted">N/A</span>' : `${f1(st.sot_for)} / ${f1(st.sot_against)}`}</td><td class="right tiny">${st.corners_for == null ? '<span class="muted">N/A</span>' : `${f1(st.corners_for)} / ${f1(st.corners_against)}`}</td></tr>` : `<tr><td class="nowrap">${name}<div class="tiny muted">0 · No data</div></td><td colspan="7" class="muted tiny">N/A</td></tr>`;
      const ms = expandMatches(e.matches);
      parts.push(`<div class="card compact"><div class="row"><div class="grow b row" style="gap:6px">${fxBadge(f, side)}${esc(f[side])}</div>${evChip(c.n)}</div>
        <div class="tiny muted" style="margin-top:4px">Sample: ${esc(c.first_date || '')} → ${esc(c.last_date || '')}, last match ${na(c.days_since_last)} days ago · current season ${c.current_season || 0}, previous ${c.previous_season || 0} · home ${c.home || 0}, away ${c.away || 0} · ${comps}${c.mixed_competitions ? ' · <b>mixed competitions</b>' : ''}${c.friendlies_included ? ` · <b>${c.friendlies_included} friendlies included</b>` : ''}${c.friendlies_excluded ? ` · ${c.friendlies_excluded} friendlies excluded` : ''}<br>Fields present: xG ${c.with_xg || 0}, shots on target ${c.with_shots || 0}, corners ${c.with_corners || 0}, cards ${c.with_cards || 0} of ${c.n || 0} matches</div>
        <div class="small" style="margin-top:6px"><b>Recent form v baseline</b> (historical, informational): last 5 ${rc.last5 ? `${f2(rc.last5.gf)} scored / ${f2(rc.last5.ga)} conceded` : 'N/A'} · last 10 ${rc.last10 ? `${f2(rc.last10.gf)} / ${f2(rc.last10.ga)}` : 'N/A'} · weighted baseline ${na(rc.baseline_gf, f2)} / ${na(rc.baseline_ga, f2)}<br>Recent attack: <b>${esc(rc.attack || 'N/A (fewer than 5 matches)')}</b> · recent defence: <b>${esc(rc.defence || 'N/A')}</b></div>
        <div style="overflow-x:auto;margin-top:6px"><table class="tbl head" style="min-width:100%"><tr><th>Split</th><th class="right">GF / GA</th><th class="right">O1.5</th><th class="right">O2.5</th><th class="right">BTTS</th><th class="right">CS</th><th class="right">SOT f/a</th><th class="right">Corn f/a</th></tr>
        ${srow('All', sp.all)}${srow('Home', sp.home)}${srow('Away', sp.away)}${srow('This season', sp.current)}${srow('Previous', sp.previous)}</table></div>
        <div class="tiny muted">Historical frequencies of the sample (plain counts). The model uses time-weighted, league-normalised versions of these.</div>
        ${(e.outliers || []).length ? `<div class="small" style="margin-top:6px"><b>Extreme results</b> (kept, flagged):${e.outliers.map((o) => `<div>• ${esc(o.date)} ${esc(o.score)} ${o.venue === 'H' ? 'v' : '@'} ${esc(o.opp)}${o.last10_gf_with != null ? ` — last-10 goals for ${f2(o.last10_gf_with)} with / ${f2(o.last10_gf_without)} without` : ''}</div>`).join('')}</div>` : ''}
        <details style="margin-top:6px"><summary class="tiny muted">Matches used (${ms.length}) — raw observations</summary><table class="tbl" style="margin-top:4px">${ms.map((m) => `<tr class="${m.outlier ? 'hl' : ''}"><td class="tiny muted nowrap">${esc(m.date)}</td><td><div class="row" style="gap:6px"><i class="f ${wdl(m.gf, m.ga)}">${wdl(m.gf, m.ga)}</i><span class="nowrap">${m.venue === 'H' ? 'v' : '@'} ${esc(m.opp)}</span></div><div class="tiny muted">${esc(m.league || '')} · ${esc(m.season || '')}${m.friendly ? ' · friendly' : ''}${m.outlier ? ' · extreme' : ''}</div></td><td class="right nowrap"><b>${m.gf} – ${m.ga}</b></td><td class="tiny muted right nowrap">${m.xg_for != null ? `xG ${f2(m.xg_for)}/${f2(m.xg_against)}` : ''}${m.sot_for != null ? `<br>SOT ${m.sot_for}/${m.sot_against}` : ''}${m.corners_for != null ? `<br>corn ${m.corners_for}/${m.corners_against}` : ''}</td></tr>`).join('')}</table></details></div>`);
    });
    // 5. head-to-head strength
    if (h2h) parts.push(`<div class="card compact"><div class="row"><div class="grow b">${icon('history', 'sm')} Head-to-head evidence</div><span class="chip ${h2h.n >= 5 ? '' : 'warn'}">H2H sample: ${h2h.n} · ${esc(h2h.label)}</span></div><div class="tiny muted" style="margin-top:4px">${h2h.n ? `${esc(h2h.first_date)} → ${esc(h2h.last_date)} · avg ${f1(h2h.avg_goals)} goals · O2.5 in ${h2h.o25}/${h2h.n} · BTTS in ${h2h.btts}/${h2h.n} · ` : ''}used by the model: <b>no</b>. ${esc(h2h.note || '')}</div></div>`);
    // 6. market comparison
    if (mk) {
      const x = mk.xg || {}; const xm = mk.x12_market;
      parts.push(`<div class="card compact"><div class="b">${icon('tag', 'sm')} Market comparison (separate layer)</div>
        <table class="tbl head" style="margin-top:6px"><tr><th></th><th class="right">Home</th><th class="right">Away</th><th class="right">Total</th></tr>
        <tr><td>Model xG</td><td class="right"><b>${f2(x.model_home)}</b></td><td class="right"><b>${f2(x.model_away)}</b></td><td class="right"><b>${f2(x.model_total)}</b></td></tr>
        <tr><td>Market xG${x.market_source ? `<div class="tiny muted">${esc(x.market_source)}</div>` : ''}</td><td class="right">${na(x.market_home, f2)}</td><td class="right">${na(x.market_away, f2)}</td><td class="right">${na(x.market_total, f2)}${x.gap_total != null ? `<div class="tiny muted">gap ${x.gap_total >= 0 ? '+' : ''}${f2(x.gap_total)}</div>` : ''}</td></tr>
        ${xm ? `<tr><td>1X2 model</td><td class="right">${pct(x12(f, 'H'))}</td><td class="right">${pct(x12(f, 'A'))}</td><td class="right tiny muted">draw ${pct(x12(f, 'D'))}</td></tr><tr><td>1X2 market implied<div class="tiny muted">${esc(xm.source || '')}</div></td><td class="right">${pct(xm.H)}</td><td class="right">${pct(xm.A)}</td><td class="right tiny muted">draw ${pct(xm.D)}</td></tr>` : ''}</table>
        <div class="tiny muted" style="margin-top:4px">Per-selection model / market / difference / EV: see the Markets tab. The model is never tuned to agree with the bookmaker.</div></div>`);
    }
    parts.push(`<div class="card tiny muted"><b>Traceability:</b> final probability ← Dixon-Coles score matrix ← model xG ← league baseline × shrunk ratings ← time-weighted, league-normalised goals of the matches listed above ← results feeds (football-data.co.uk / Livescore).</div>`);
  }
  function cmpRow(label, a, b, fmt, higherBetter) {
    fmt = fmt || f2; const av = a == null || isNaN(a) ? null : +a, bv = b == null || isNaN(b) ? null : +b;
    if (av == null && bv == null) return '';
    const tot = (av || 0) + (bv || 0); const wa = tot ? (av || 0) / tot : 0.5;
    const cls = (x, y) => (x == null || y == null || x === y) ? '' : ((x > y) === !!higherBetter ? 'lead' : '');
    return `<tr><td class="right ${cls(av, bv)}">${fmt(av)}</td><td class="mid"><div class="k">${label}</div><div class="duo"><span class="l" style="width:${Math.round(wa * 100)}%"></span><span class="r" style="width:${Math.round((1 - wa) * 100)}%"></span></div></td><td class="${cls(bv, av)}">${fmt(bv)}</td></tr>`;
  }
  function matchStats(parts, f, th, ta) {
    const H = f.teams.home || {}, A = f.teams.away || {};
    const outOf = (n) => (x) => x == null ? '–' : `${x}/${n}`;
    const sq = f.squad || {};
    parts.push(`<div class="card compact"><div class="row"><div class="grow b row" style="gap:6px">${fxBadge(f, 'home')}${esc(f.home)}</div><div class="tiny muted">team samples</div><div class="b row" style="gap:6px">${esc(f.away)}${fxBadge(f, 'away')}</div></div>
      <div class="row small-chips" style="gap:6px;margin-top:4px;flex-wrap:wrap"><span class="tiny muted">${esc(f.home)}:</span>${evChip(H.n || 0)}<span class="grow"></span><span class="tiny muted">${esc(f.away)}:</span>${evChip(A.n || 0)}</div>
      <table class="cmp">${sq.home || sq.away ? cmpRow('Squad value (Transfermarkt)', sq.home && sq.home.value, sq.away && sq.away.value, fmtValue, true) + cmpRow('Average age', sq.home && sq.home.avg_age, sq.away && sq.away.avg_age, f1, false) : ''}${cmpRow('Goals scored / game', H.gf, A.gf, f2, true)}${cmpRow('Goals conceded / game', H.ga, A.ga, f2, false)}
      ${cmpRow('Home / away goals for', H.venue_gf, A.venue_gf, f2, true)}${cmpRow('Home / away goals against', H.venue_ga, A.venue_ga, f2, false)}
      ${cmpRow('Attack strength', H.att, A.att, f2, true)}${cmpRow('Defence (lower = better)', H.def, A.def, f2, false)}
      ${cmpRow('xG for (last 10)', H.xg_for, A.xg_for, f2, true)}${cmpRow('xG against (last 10)', H.xg_against, A.xg_against, f2, false)}
      ${cmpRow('Shots on target for', H.sot_for, A.sot_for, f1, true)}${cmpRow('Shots on target against', H.sot_against, A.sot_against, f1, false)}
      ${cmpRow('Over 1.5 rate', H.o15, A.o15, pct, true)}${cmpRow('Over 2.5 rate', H.o25, A.o25, pct, true)}${cmpRow('Over 3.5 rate', H.o35, A.o35, pct, true)}
      ${cmpRow('Over 2.5 at home / away', H.venue_o25, A.venue_o25, pct, true)}${cmpRow('BTTS at home / away', H.venue_btts, A.venue_btts, pct, true)}
      ${cmpRow('BTTS rate', H.btts, A.btts, pct, true)}${cmpRow('Clean sheets', H.cs, A.cs, pct, true)}${cmpRow('Failed to score', H.fts, A.fts, pct, false)}
      ${cmpRow('Goals / game, last 5', H.form5_goals, A.form5_goals, f2, true)}${cmpRow('Over 1.5 in last matches', H.last_o15, A.last_o15, outOf(H.last_n || 10), true)}${cmpRow('Over 2.5 in last matches', H.last_o25, A.last_o25, outOf(H.last_n || 10), true)}${cmpRow('BTTS in last matches', H.last_btts, A.last_btts, outOf(H.last_n || 10), true)}</table>
      <div class="tiny muted">${H.n || 0} / ${A.n || 0} matches used (time-weighted ${f1(H.n_eff)} / ${f1(A.n_eff)}); ${H.venue_n || 0} home / ${A.venue_n || 0} away games in the venue splits (${evidenceLabel(H.venue_n || 0)} / ${evidenceLabel(A.venue_n || 0)}). Rates are historical frequencies of each sample, not model probabilities; xG and shots on target are N/A where the feed has none. Bars compare the two teams.</div></div>`);
    const t = PR.teamsCached(f.div);
    if (th && ta) {
      const sp = (r) => r.all;
      parts.push(`<div class="card compact"><div class="row"><div class="grow b">This season</div><div class="tiny muted">since ${esc(th.season_from)} · ${sp(th).p || 0} / ${sp(ta).p || 0} matches (${sp(th).evidence || evidenceLabel(sp(th).p)} / ${sp(ta).evidence || evidenceLabel(sp(ta).p)})</div></div>
        <table class="cmp">${cmpRow('League position', th.pos, ta.pos, (x) => x == null ? '–' : x + ord(x), false)}${cmpRow('Points (played)', sp(th).pts, sp(ta).pts, (x) => x == null ? '–' : x, true)}
        ${cmpRow('Points per game', sp(th).ppg, sp(ta).ppg, f2, true)}${cmpRow('Won', sp(th).w, sp(ta).w, (x) => x, true)}${cmpRow('Drawn', sp(th).d, sp(ta).d, (x) => x, true)}${cmpRow('Lost', sp(th).l, sp(ta).l, (x) => x, false)}
        ${cmpRow('Goals for / game', sp(th).gf_avg, sp(ta).gf_avg, f2, true)}${cmpRow('Goals against / game', sp(th).ga_avg, sp(ta).ga_avg, f2, false)}
        ${cmpRow('Corners for / game', th.avg.corners_for, ta.avg.corners_for, f1, true)}${cmpRow('Corners against / game', th.avg.corners_against, ta.avg.corners_against, f1, false)}
        ${cmpRow('Cards / game', th.avg.cards_for, ta.avg.cards_for, f1, false)}${cmpRow('Scored in last 10', th.scored_in_last, ta.scored_in_last, (x) => x == null ? '–' : x + '/10', true)}</table>
        <div class="tiny muted">Home record ${esc(f.home)}: ${th.home.w}W ${th.home.d}D ${th.home.l}L · away record ${esc(f.away)}: ${ta.away.w}W ${ta.away.d}D ${ta.away.l}L. Tap a team name for the full page.</div></div>`);
    } else if (t && t.missing) parts.push(`<div class="card tiny muted">Season table not available for this competition yet.</div>`);
    else parts.push(`<div class="card tiny muted">Loading season stats…</div>`);
  }
  function h2hTable(rows, f) {
    return `<table class="tbl" style="margin-top:6px">${rows.map((m) => `<tr><td class="tiny muted nowrap">${esc(m.date)}</td><td class="${m.hg > m.ag ? 'b' : ''}"><div class="row" style="gap:6px">${badge(m.home, m.home === f.home ? (f.badges || {}).home : m.home === f.away ? (f.badges || {}).away : null, 22)}<span>${esc(m.home)}</span></div></td><td class="right nowrap"><b>${m.hg} – ${m.ag}</b></td><td class="${m.ag > m.hg ? 'b' : ''}"><div class="row" style="gap:6px;justify-content:flex-end"><span>${esc(m.away)}</span>${badge(m.away, m.away === f.home ? (f.badges || {}).home : m.away === f.away ? (f.badges || {}).away : null, 22)}</div></td><td class="tiny muted">${esc(m.league || '')}</td></tr>`).join('')}</table>`;
  }
  function matchH2H(parts, f) {
    const h2h = f.h2h || [];
    const hm = f.h2h_meta;
    if (hm && hm.n) parts.push(`<div class="card compact"><div class="row" style="gap:6px;flex-wrap:wrap"><span class="b">H2H sample</span>${evChip(hm.n)}<span class="chip ${hm.used_by_model ? '' : 'warn'}">${hm.used_by_model ? 'used by the model' : 'context only — not a model input'}</span></div><div class="tiny muted" style="margin-top:4px">${esc(hm.note || '')}${hm.first_date ? ` Meetings ${esc(hm.first_date)} → ${esc(hm.last_date)}` : ''}${(hm.competitions || []).length ? ` · ${esc(hm.competitions.join(', '))}` : ''}. Figures below are historical frequencies of ${hm.n} match${hm.n === 1 ? '' : 'es'}.</div></div>`);
    if (h2h.length) {
      const tot = h2h.map((m) => m.hg + m.ag);
      const wins = (name) => h2h.filter((m) => (m.home === name && m.hg > m.ag) || (m.away === name && m.ag > m.hg)).length;
      const draws = h2h.filter((m) => m.hg === m.ag).length;
      parts.push(`<div class="card compact"><div class="row"><div class="grow b">Head to head · last ${h2h.length}</div><span class="chip">${f1(tot.reduce((a, b) => a + b, 0) / tot.length)} goals avg</span><span class="chip">O2.5 ${tot.filter((t) => t >= 3).length}/${tot.length}</span><span class="chip">BTTS ${h2h.filter((m) => m.hg > 0 && m.ag > 0).length}/${tot.length}</span></div>
        <div class="h2h-bar"><span class="h" style="flex:${wins(f.home) || 0.001}">${wins(f.home)}</span><span class="d" style="flex:${draws || 0.001}">${draws}</span><span class="a" style="flex:${wins(f.away) || 0.001}">${wins(f.away)}</span></div><div class="lbl tiny muted row"><span class="grow">${esc(f.home)} wins</span><span>draws</span><span class="grow right">${esc(f.away)} wins</span></div>
        ${h2hTable(h2h.slice(0, 5), f)}${h2h.length > 5 ? `<details><summary class="tiny muted">Earlier meetings (${h2h.length - 5})</summary>${h2hTable(h2h.slice(5), f)}</details>` : ''}</div>`);
      const venue = h2h.filter((m) => m.home === f.home);
      if (venue.length) parts.push(`<div class="card compact"><div class="row"><div class="grow b">At ${esc(f.home)} · last ${Math.min(5, venue.length)}</div><span class="chip">O2.5 ${venue.slice(0, 5).filter((m) => m.hg + m.ag >= 3).length}/${Math.min(5, venue.length)}</span><span class="chip">BTTS ${venue.slice(0, 5).filter((m) => m.hg > 0 && m.ag > 0).length}/${Math.min(5, venue.length)}</span></div>${h2hTable(venue.slice(0, 5), f)}</div>`);
    } else parts.push(`<div class="card tiny muted">No previous meeting on record between these two teams.</div>`);
    const recent = (p, name, side, list, title) => `<div class="card compact"><div class="b row" style="gap:6px">${fxBadge(f, side)}${esc(name)} <span class="muted" style="font-weight:500">— ${title}</span></div><table class="tbl" style="margin-top:4px">${(list || []).map((m) => `<tr><td class="tiny muted nowrap">${esc(m.date)}</td><td><div class="row" style="gap:6px"><i class="f ${wdl(m.gf, m.ga)}">${wdl(m.gf, m.ga)}</i>${badge(m.opp, null, 22)}<span class="nowrap">${m.venue === 'H' ? 'v' : '@'} ${esc(m.opp)}</span></div></td><td class="right nowrap"><b>${m.gf} – ${m.ga}</b></td><td class="tiny muted">${esc(m.league || '')}</td></tr>`).join('') || '<tr><td class="muted">no matches</td></tr>'}</table></div>`;
    const H = f.teams.home || {}, A = f.teams.away || {};
    parts.push(recent(H, f.home_long || f.home, 'home', H.last5, 'last 5'));
    parts.push(recent(H, f.home_long || f.home, 'home', H.venue_last5, 'last 5 at home'));
    parts.push(recent(A, f.away_long || f.away, 'away', A.last5, 'last 5'));
    parts.push(recent(A, f.away_long || f.away, 'away', A.venue_last5, 'last 5 away'));
  }

  // ------------------------------------------------------------------ FORM TAB
  function matchForm(parts, f) {
    const tp = teamsCached(f.div) || {};
    const rec = (side) => ((tp.teams || {})[side === 'home' ? f.home : f.away]) || null;
    const rowsOf = (ms) => (ms || []).map((m) =>
      `<tr><td class="tiny muted nowrap">${esc(m.date)}</td><td><div class="row" style="gap:6px"><i class="f ${wdl(m.gf, m.ga)}">${wdl(m.gf, m.ga)}</i>${badge(m.opp, null, 22)}<span class="nowrap">${m.venue === 'H' ? 'v' : '@'} ${esc(m.opp)}</span></div></td><td class="right nowrap"><b>${m.gf} – ${m.ga}</b></td><td class="tiny muted nowrap">${esc(m.league || '')}</td></tr>`).join('');
    const block = (side, name, r) => {
      const last = (r && r.last) || [];
      const venue = side === 'home' ? 'H' : 'A';
      const ven = last.filter((m) => m.venue === venue).slice(0, 5);
      const t10 = (r && r.trends && r.trends.last10) || null;
      const t5 = (r && r.trends && r.trends.last5) || null;
      const chips = [];
      if (t10) chips.push(`<span class="chip">last 10: ${t10.pts} pts · ${t10.gf_avg} gf / ${t10.ga_avg} ga</span>`);
      if (t10) chips.push(`<span class="chip">O1.5 ${pct(t10.o15)} · O2.5 ${pct(t10.o25)}</span>`);
      if (t5) chips.push(`<span class="chip">last 5: ${t5.pts} pts</span>`);
      return `<div class="card compact"><div class="row" style="gap:6px;flex-wrap:wrap"><div class="grow b row" style="gap:6px">${fxBadge(f, side)}${esc(name)}</div>${chips.join('')}</div>
        ${last.length ? `<table class="tbl" style="margin-top:4px"><tr><th>Date</th><th>Match (all comps.)</th><th class="right">Score</th><th>Competition</th></tr>${rowsOf(last)}</table>` : `<div class="tiny muted" style="margin-top:6px">N/A — not enough recent matches to show form.</div>`}
        ${ven.length ? `<div class="b tiny" style="margin-top:8px">Last ${ven.length} ${side === 'home' ? 'at home' : 'away'}</div><table class="tbl" style="margin-top:2px">${rowsOf(ven)}</table>` : ''}</div>`;
    };
    parts.push(`<div class="card tiny muted">Recent results of both clubs (all competitions, most recent first). Points and rates are historical frequencies, not model inputs — the model's own numbers live on the Overview.</div>`);
    parts.push(block('home', f.home_long || f.home, rec('home')));
    parts.push(block('away', f.away_long || f.away, rec('away')));
  }

  // ------------------------------------------------------------------ TABLE TAB
  function matchTable(parts, f, th, ta) {
    const tp = teamsCached(f.div);
    const tbl = tp && tp.table;
    if (!tbl || !tbl.length) {
      parts.push(`<div class="card empty">No standings for this competition${(f.competition || '').toLowerCase().includes('cup') || (f.league || '').toLowerCase().includes('cup') ? ' (knockout format — a bracket is not a table)' : ''}.</div>`);
      return;
    }
    const hl = (name) => name === f.home || name === f.away;
    parts.push(`<div class="card compact"><div class="row" style="gap:6px;flex-wrap:wrap"><div class="grow b">${icon('chart', 'sm')} ${esc(f.competition || f.league || 'Standings')}</div><span class="tiny muted">${tp.season_from ? 'season from ' + esc(tp.season_from) : ''} · ${tbl.length} teams</span></div>
      <table class="tbl table head" style="margin-top:4px"><tr><th>#</th><th>Team</th><th class="right">P</th><th class="right">W-D-L</th><th class="right">GF</th><th class="right">GA</th><th class="right">GD</th><th class="right">Pts</th><th class="right">Form</th></tr>
      ${tbl.map((r) => `<tr class="${hl(r.team) ? 'hl' : ''}"><td class="muted">${r.pos}</td><td><div class="tname">${badge(r.team, null, 20)}<span class="nm">${esc(r.team)}${r.team === f.home ? ' <span class="tiny">H</span>' : r.team === f.away ? ' <span class="tiny">A</span>' : ''}</span></div></td><td class="right">${r.p}</td><td class="right">${r.w}-${r.d}-${r.l}</td><td class="right">${r.gf}</td><td class="right">${r.ga}</td><td class="right">${r.gd > 0 ? '+' : ''}${r.gd}</td><td class="right b">${r.pts}</td><td class="right">${r.form ? formBadges(r.form.split('')) : '<span class="tiny muted">–</span>'}</td></tr>`).join('')}</table></div>`);
    // home / away record of the two clubs
    const rec = (side) => ((tp.teams || {})[side === 'home' ? f.home : f.away]) || null;
    const half = (side, name, r) => {
      if (!r) return '';
      const s = side === 'home' ? r.home : r.away;
      if (!s || !s.p) return '';
      return `<div class="card compact"><div class="b row" style="gap:6px">${fxBadge(f, side)}${esc(name)} <span class="muted" style="font-weight:500">— ${side === 'home' ? 'home' : 'away'} record</span></div>
        <div class="grid4" style="margin-top:6px"><div class="cell"><div class="k">P</div><div class="v">${s.p}</div></div><div class="cell"><div class="k">W-D-L</div><div class="v">${s.w}-${s.d}-${s.l}</div></div><div class="cell"><div class="k">GF / GA</div><div class="v">${s.gf} / ${s.ga}</div></div><div class="cell"><div class="k">O2.5</div><div class="v">${pct(s.o25)}</div></div></div></div>`;
    };
    parts.push(half('home', f.home_long || f.home, rec('home')));
    parts.push(half('away', f.away_long || f.away, rec('away')));
  }

  // ------------------------------------------------------------------ NEWS TAB
  PR.wireNewsLinks = function () {
    setTimeout(() => {
      $$('[data-newslink]').forEach((el) => { if (el.dataset.wired) return; el.dataset.wired = '1'; el.onclick = () => { const u = el.dataset.newslink; if (!u) return; if (PR.native && PR.native.openUrl) PR.native.openUrl(u); else window.open(u, '_blank'); }; });
    }, 0);
  };
  function newsItem(it) {
    const when = it.when ? esc(String(it.when).replace('T', ' ').slice(0, 16)) : '';
    const b = { '24h': 'chip good', '3d': 'chip', '7d': 'chip warn' }[it.bucket] || 'chip';
    return `<div class="news-item tap" data-newslink="${esc(it.link || '')}"><div class="row" style="gap:6px;align-items:flex-start"><div class="grow"><div class="b" style="font-size:13px">${esc(it.title || '(untitled)')}</div><div class="tiny muted" style="margin-top:2px">${esc(it.source || 'Google News')}${when ? ' · ' + when : ''} ${b ? `<span class="${b}" style="margin-left:4px">${it.bucket === '24h' ? '24 h' : it.bucket === '3d' ? '3 d' : '7 d'}</span>` : ''}</div></div></div></div>`;
  }
  PR.newsItem = newsItem;
  function matchNews(parts, f, x) {
    const news = x.news || {};
    const sec = (title, items) => (items && items.length ? `<div class="card compact"><div class="b" style="margin-bottom:4px">${title}</div>${items.map(newsItem).join('')}</div>` : '');
    const total = (news.match || []).length + (news.home || []).length + (news.away || []).length;
    if (!total) {
      parts.push(`<div class="card empty">No recent headlines found for this match or either club. News refreshes at most every 6 hours with each scan.</div>`);
    } else {
      parts.push(`<div class="card tiny muted">Recent reporting from Google News — headlines only, for your reference. Clicking an item opens the original source. News is never used by the prediction model.</div>`);
      parts.push(sec(`${icon('sparkle', 'sm')} This match`, news.match));
      parts.push(sec(`${icon('ball', 'sm')} ${esc(f.home)}`, news.home));
      parts.push(sec(`${icon('ball', 'sm')} ${esc(f.away)}`, news.away));
    }
    PR.wireNewsLinks();
  }

  // ------------------------------------------------------------------ team TREND tab
  function teamTrends(parts, r) {
    const t = r.trends;
    if (!t || (!t.last5 && !t.last10 && !t.season)) {
      parts.push(`<div class="card empty">Not enough finished matches yet to compute trend windows (minimum 3 per window).</div>`);
      return;
    }
    const W = [['last5', 'L5'], ['last10', 'L10'], ['last20', 'L20'], ['season', 'Season'], ['previous_season', 'Prev. season']];
    const pctf = (v) => (v == null ? 'N/A' : Math.round(v * 100) + '%');
    const num2 = (v) => (v == null ? 'N/A' : String(Math.round(v * 100) / 100));
    const inN = (w, k) => (w && w.n ? `${w[k]}/${w.n}` : 'N/A');
    const M = [
      ['pts', 'Points', (w) => (w ? w.pts : null)], ['ppg', 'Pts / game', (w) => (w ? w.ppg : null), num2],
      ['gf_avg', 'Goals for / game', (w) => (w ? w.gf_avg : null), num2], ['ga_avg', 'Goals against / game', (w) => (w ? w.ga_avg : null), num2],
      ['o15', 'Over 1.5 goals', (w) => (w ? w.o15 : null), pctf], ['o25', 'Over 2.5 goals', (w) => (w ? w.o25 : null), pctf], ['o35', 'Over 3.5 goals', (w) => (w ? w.o35 : null), pctf],
      ['btts', 'Both teams scored', (w) => (w ? w.btts : null), pctf], ['cs', 'Clean sheets', (w) => (w ? w.cs : null), pctf], ['fts', 'Failed to score', (w) => (w ? w.fts : null), pctf],
      ['win', 'Win rate', (w) => (w ? w.win : null), pctf],
      ['scored_in_n', 'Scored in', (w) => (w ? `${w.scored_in_n}/${w.n}` : null)], ['conceded_in_n', 'Conceded in', (w) => (w ? `${w.conceded_in_n}/${w.n}` : null)],
    ];
    const rows = M.map(([k, label, get, fmt]) => {
      const cells = W.map(([wk, wl]) => {
        const w = t[wk]; const v = get(w);
        return `<div class="cell"><span class="cl">${wl}${w ? ` · ${w.n}` : ''}</span><b>${v == null ? 'N/A' : (fmt ? fmt(v) : v)}</b></div>`;
      }).join('');
      return `<div class="trend-metric"><div class="k">${label}</div><div class="v">${cells}</div></div>`;
    }).join('');
    parts.push(`<div class="card tiny muted">Trend windows for ${esc(pageName(r))}, computed only from published results. A window needs at least 3 finished matches — thinner windows show N/A, never a guess. “Prev. season” is the part of the archive before the current season start; it is N/A when the archive does not reach back that far. These are historical frequencies, not model probabilities.</div>`);
    parts.push(`<div class="card compact"><div class="b" style="margin-bottom:2px">Trend windows</div><div class="tiny muted" style="margin-bottom:4px">n = matches in window</div>${rows}</div>`);
  }
  function pageName(r) { return r && r.name ? r.name : 'this team'; }

  // ------------------------------------------------------------------ TEAM PAGE
  PR.pages.team = function (page) {
    ensureTeams(page.div);
    const t = PR.teamsCached(page.div); const v = state.teamView || 'overview';
    const parts = [head(esc(page.name), esc(page.country))];
    if (!t) { parts.push(skeleton(6)); view().innerHTML = parts.join(''); wireBack(); return; }
    const r = t.teams && t.teams[page.name];
    if (!r) { parts.push(`<div class="card empty">No season data for ${esc(page.name)} yet.</div>`); view().innerHTML = parts.join(''); wireBack(); return; }
    const a = r.all;
    parts.push(`<div class="card"><div class="thead">${badge(page.name, null, 56)}<div class="grow"><div class="h1">${esc(page.name)}</div><div class="small muted">${flag(page.country)} ${esc(t.league)} · ${r.pos ? `${r.pos}${ord(r.pos)} of ${r.teams_in_league}` : ''} · ${a.pts} pts from ${a.p}</div>${r.squad && r.squad.value ? `<div class="value-tag">💶 Squad value ${fmtValue(r.squad.value)} · avg age ${f1(r.squad.avg_age)} · ${r.squad.size} players</div>` : ''}<div style="margin-top:4px">${formBadges(r.form.split(''))}</div></div></div>
      <div class="grid4" style="margin-top:8px"><div class="cell"><div class="k">Record</div><div class="v">${a.w}-${a.d}-${a.l}</div><div class="tiny muted">W-D-L</div></div><div class="cell"><div class="k">Goals</div><div class="v">${a.gf} : ${a.ga}</div><div class="tiny muted">${f2(a.gf_avg)} / ${f2(a.ga_avg)} per game</div></div><div class="cell"><div class="k">Points / game</div><div class="v">${f2(a.ppg)}</div><div class="tiny muted">streak ${esc(r.streak || '–')}</div></div><div class="cell"><div class="k">Over 2.5</div><div class="v">${pct(a.o25)}</div><div class="tiny muted">BTTS ${pct(a.btts)}</div></div></div></div>`);
    parts.push(`<div class="card compact">${segmented([['overview', 'Overview'], ['trends', 'Trends'], ['matches', 'Matches'], ['table', 'Table']], v, 'tv')}</div>`);
    if (v === 'trends') teamTrends(parts, r);
    else if (v === 'overview') {
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
        <div class="tiny muted" style="margin-top:4px">Season since ${esc(r.season_from)} · sample ${a.p || 0} match${a.p === 1 ? '' : 'es'} (${a.evidence || evidenceLabel(a.p)}; home ${r.home.p || 0}, away ${r.away.p || 0}) · historical frequencies, not model probabilities${r.avg_n ? ` · xG in ${r.avg_n.xg}, shots on target in ${r.avg_n.sot}, corners in ${r.avg_n.corners}, cards in ${r.avg_n.cards} of them (missing = N/A)` : ''} · league average ${f2(t.avg_goals)} goals, O2.5 ${pct(t.o25_rate)}, BTTS ${pct(t.btts_rate)}.</div></div>`);
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
    parts.push(`<div class="card"><div class="grid4">${box('⭐ Bets of the day', s.botd, 'hit')}${box(icon('trend', 'sm') + ' High probability', s.safes, 'hit')}${box(icon('star', 'sm') + ' Shortlist', s.picks, 'hit')}</div>
      ${s.finished ? `<div class="tiny muted" style="margin-top:6px">Finished matches: Over 2.5 in ${pct(s.o25_rate)}, BTTS in ${pct(s.btts_rate)}.</div>` : ''}</div>`);
    parts.push(`<div class="card compact">${segmented([['results', 'Results'], ['bets', 'Bets']], v, 'dv')}</div>`);
    const openable = (f) => true;   // live analysis, retained detail file, or the archive record itself
    const tapAttrs = (f) => openable(f) ? `class="tap" data-fx="${esc(f.id)}" ${f.d ? `data-d="${esc(f.d)}"` : ''}` : '';
    if (v === 'results') {
      let lastComp = null;
      const fxs = day.fixtures.slice().sort((a, b) => a.competition.localeCompare(b.competition) || a.kickoff.localeCompare(b.kickoff));
      parts.push('<div class="card compact">');
      fxs.forEach((f) => {
        if (f.competition !== lastComp) { parts.push(`<div class="comp-head">${flag(f.country)} ${esc(f.competition)}</div>`); lastComp = f.competition; }
        const sc = f.score; const fin = sc && sc.hg != null;
        const seenB = new Set();
        const marks = (f.bets || []).filter((b) => { const k = b.sel; if (seenB.has(k)) return false; seenB.add(k); return true; }).map((b) => `<span class="chip ${b.status === 'hit' ? 'good' : b.status === 'miss' ? 'bad' : ''}">${b.botd ? '⭐' : icon(b.kind === 'safe' ? 'trend' : 'star')} ${esc(b.label)}${b.odds ? ' @ ' + f2(b.odds) : ''} ${statusIcon(b.status)}</span>`).join('');
        const stats = fin && sc.hc != null ? `<span class="tiny muted">HT ${sc.hth != null ? `${sc.hth}–${sc.hta}` : '–'} · corners ${sc.hc}–${sc.ac}${sc.hy != null ? ` · 🟨 ${sc.hy}–${sc.ay}` : ''}${sc.hr ? ` · 🟥 ${sc.hr}` : ''}${sc.ar ? `–${sc.ar}` : ''}</span>` : fin && sc.hth != null ? `<span class="tiny muted">HT ${sc.hth}–${sc.hta}</span>` : '';
        const row = matchRow(f, { tap: !!openable(f), short: true, sub: (stats ? stats : '') + (marks ? `<div class="chips">${marks}</div>` : ''), right: fin ? '' : `<span class="tiny muted">xG ${f1(f.xg[0])}–${f1(f.xg[1])}</span><span class="tiny muted">O2.5 ${pct(f.p.O25)}</span>` });
        parts.push(f.d ? row.replace('<div class="mrow', `<div data-d="${esc(f.d)}" class="mrow`) : row);
      });
      parts.push('</div>');
    } else {
      const botd = []; const safeBets = []; const picks = [];
      day.fixtures.forEach((f) => (f.bets || []).forEach((b) => { if (b.botd) botd.push({ f, b }); else if (b.kind === 'safe') safeBets.push({ f, b }); else if (b.kind === 'pick') picks.push({ f, b }); }));
      const table = (lst, showP) => `<div class="card compact"><table class="tbl">${lst.map(({ f, b }) => `<tr ${tapAttrs(f)}><td class="tiny muted nowrap">${esc(koTime(f.kickoff))}</td><td><div class="b">${esc(f.home)} v ${esc(f.away)}</div><div class="tiny muted">${esc(b.label)}${showP ? ` · ${pct(b.p)}` : ''} · ${flag(f.country)} ${esc(f.competition)}</div></td><td class="right nowrap">${f.score && f.score.hg != null ? `<b>${f.score.hg}–${f.score.ag}</b>` : '<span class="muted">–</span>'}</td><td class="right nowrap">${b.odds ? f2(b.odds) + ' ' : ''}${statusIcon(b.status)}</td></tr>`).join('')}</table></div>`;
      if (botd.length) parts.push(`<h2 class="section">⭐ Bets of the day</h2>` + table(botd));
      if (safeBets.length) parts.push(`<h2 class="section">${icon('trend')} High-probability selections</h2>` + table(safeBets));
      if (picks.length) parts.push(`<h2 class="section">${icon('star')} Shortlist picks</h2>` + table(picks, true));
      if (!botd.length && !safeBets.length && !picks.length) parts.push(`<div class="card empty">No bets were recorded for this day.</div>`);
    }
    view().innerHTML = parts.join('');
    wireBack();
    $$('[data-dv]').forEach((b) => { b.onclick = () => { state.dayView = b.dataset.dv; PR.render(); }; });
  };

  // ------------------------------------------------------------------ ANALYSIS (full report)
  PR.pages.analysis = function (page) {
    const d = state.data; const dates = d.history.reports || []; const date = page.date || dates[0] || (d.meta.generated || '').slice(0, 10);
    const key = `${date}|report`;
    if (!state.reports[key]) {
      state.reports[key] = { loading: true };
      PR.nfetch(PR.rawUrl(`reports/${date}.md`) + '?t=' + Math.floor(Date.now() / 60000)).then((r) => { state.reports[key] = r.code === 200 ? { md: r.body } : { md: `_This analysis could not be loaded (HTTP ${r.code})._` }; PR.render(); });
    }
    const rep = state.reports[key];
    const parts = [head('Full analysis', esc(niceDate(date)))];
    if (dates.length > 1) parts.push(`<div class="card compact"><div class="row"><div class="grow tiny muted">Archive</div>${select('an-date', dates.map((r) => [r, r]), date)}</div></div>`);
    parts.push(`<div class="card md">${rep.md ? md(rep.md) : '<div class="empty">Loading analysis…</div>'}</div>`);
    view().innerHTML = parts.join('');
    wireBack();
    const sel = $('#an-date'); if (sel) sel.onchange = (e) => PR.replace({ type: 'analysis', date: e.target.value });
  };

  // ------------------------------------------------------------------ PERFORMANCE
  PR.pages.performance = function () {
    const d = state.data; const sf = (d.safe || {}).summary || {}; const parts = [head('Performance', 'Auto-graded from official results')];
    const row = (name, s, wonKey) => s && s.n ? `<tr><td>${name}</td><td class="right">${s[wonKey || 'won']}/${s.n}</td><td class="right"><b>${pct(s.rate)}</b></td><td class="right muted">${pct(s.exp_rate)}</td><td class="right">${f2(s.avg_odds)}</td><td class="right ${s.roi > 0 ? 'good' : s.roi < 0 ? 'bad' : ''}"><b>${signed(s.roi)}</b></td></tr>` : `<tr><td>${name}</td><td class="right muted">0/0</td><td class="right muted">–</td><td class="right muted">–</td><td class="right muted">–</td><td class="right muted">–</td></tr>`;
    const tbl = (rows) => `<table class="tbl head perf" style="margin-top:6px"><tr><th>Scope</th><th class="right">Won</th><th class="right">Hit</th><th class="right">Exp.</th><th class="right">Odds</th><th class="right">Return</th></tr>${rows}</table>`;
    const bo = sf.botd || {};
    parts.push(`<div class="card"><div class="row"><span class="ico amber">${icon('star')}</span><b>Bets of the day</b></div>${tbl(row('All time', bo.all) + row('Last 30 days', bo['30d']) + Object.values(bo.by_section || {}).map((s) => row(s.title || '', s)).join(''))}<div class="tiny muted">${bo.pending || 0} pending. Up to three picks per section (1X2 · Over 1.5 & team goals · BTTS · Over 2.5 · Bookings · Corners), overs only.</div></div>`);
    const bg = (sf.bets || {}).by_group || {};
    parts.push(`<div class="card"><div class="row"><span class="ico green">${icon('trend')}</span><b>High-probability selections</b></div>${tbl(row('All time', (sf.bets || {}).all) + row('Last 30 days', (sf.bets || {})['30d']) + Object.entries(bg).map(([g, s]) => row(GROUPS[g] || g, s)).join(''))}<div class="tiny muted">${(sf.bets || {}).pending || 0} pending. "Exp." is the model's own predicted hit rate — if the real rate stays below it for weeks, the model is over-confident. Return = flat-stake profit per unit staked.</div></div>`);
    const t = d.tracker || {};
    parts.push(`<div class="card"><div class="row"><span class="ico">${icon('trend')}</span><b>Goals shortlists</b></div><table class="tbl head" style="margin-top:6px"><tr><th>Market</th><th class="right">Settled</th><th class="right">Hit</th><th class="right">30d</th><th class="right">Pending</th></tr>${['O15', 'O25', 'BTTS'].map((mk) => { const s = t[mk] || {}; return `<tr><td>${MK[mk]}</td><td class="right">${s.settled || 0}</td><td class="right">${pct(s.rate)}</td><td class="right">${pct(s.recent_rate)}</td><td class="right">${s.pending || 0}</td></tr>`; }).join('')}</table>
      <div class="tiny muted">Backtest 2023–26 (52,000 matches): Over 1.5 shortlist 87%, Over 2.5 67%, BTTS 64%.</div></div>`);
    parts.push(`<div class="note">Everything on this page is graded automatically from final scores. Bookings and corner bets settle from the match statistics feed a few hours after full time. Statistical information, not betting advice.</div>`);
    view().innerHTML = parts.join('');
    wireBack();
  };

  // ------------------------------------------------------------------ GUIDE
  PR.pages.guide = function () {
    const parts = [head('Guide', 'Markets, probabilities and how to read PlayReport')];
    const sec = (ico, title, body) => `<div class="card guide"><div class="row"><span class="ico">${icon(ico)}</span><b>${title}</b></div><div class="small" style="margin-top:6px">${body}</div></div>`;
    parts.push(sec('ball', 'Over / Under goals', `<p><b>Over 1.5</b> wins when the match has 2 or more goals; <b>Over 2.5</b> needs 3 or more; <b>Under 3.5</b> wins with 3 or fewer. The half-goal line means there is never a push. Own goals count, extra time does not (90 minutes plus stoppage time only).</p><p>Typical prices: Over 1.5 around 1.20–1.40 in open leagues; Over 2.5 around 1.70–2.10.</p>`));
    parts.push(sec('swap', 'Both teams to score (BTTS / GG)', `<p><b>Yes</b> wins if each team scores at least once, whatever the result — 1-1 and 3-2 win, 2-0 loses. <b>No</b> is the opposite. On Sportybet this is the "GG / NG" market.</p><p>PlayReport's BTTS shortlist looks for two teams that both score and both concede regularly.</p>`));
    parts.push(sec('target', 'Team goals', `<p><b>Home team over 0.5</b> = the home team scores at least once; <b>away team over 1.5</b> = the away team scores twice or more; <b>under 1.5</b> = one goal or none for that team. These are good ways to back a strong attack (or a leaky defence) without needing the other team to do anything.</p>`));
    parts.push(sec('corner', 'Corners', `<p><b>Over 9.5 corners</b> wins with 10 or more corners in the match (both teams together). Corners awarded but not taken before the final whistle still count. Modelled for the 22 main European leagues, from each team's corners for and against; average is about 10 per match.</p>`));
    parts.push(sec('card', 'Cards / bookings', `<p><b>Over 3.5 cards</b> wins with 4 or more cards. On Sportybet a yellow counts 1 and a straight red 2 (a second yellow = yellow + red = 3 for that player); some books use "booking points" (10/25) instead — check the market name. Cards to the bench or after the whistle usually do not count. Modelled from team and referee averages in the main European leagues.</p>`));
    parts.push(sec('shield', 'Match result & double chance', `<p><b>1X2</b>: home win, draw or away win after 90 minutes. <b>Double chance 1X</b> wins if the home team wins or draws — two of the three outcomes covered, at a shorter price. Shown on every match page for context; PlayReport's high-probability selections stay in the goals, corners and cards markets.</p>`));
    parts.push(sec('trend', 'How the probabilities are made (data-first)', `<p>Every probability comes from <b>football data only</b>. Each team gets a time-weighted attack and defence rating from its last 40 competitive matches (recent games weighted most, league-normalised, home and away blended, shrunk towards the league average when the sample is small). League baseline × attack × opponent's defence gives the <b>Model xG</b> of each team, and a Dixon-Coles Poisson score matrix turns that into a probability for every line.</p><p>Bookmaker prices are a <b>separate comparison layer</b>: the margin is removed and the implied probability is shown next to the model with the difference in points and the EV. The market never changes a model probability, and the model is not tuned to agree with the bookmaker. <b>Market xG</b> (from the prices) is shown next to Model xG, never blended.</p><p>Every statistic carries its sample size — Very small 1–4, Small 5–9, Moderate 10–19, Strong 20–39, Very strong 40+ — and each match has a <b>data quality</b> assessment (completeness, sample, recency, consistency, competition, home/away relevance, source) under the <b>Data</b> tab, with the raw matches used, the extreme results flagged and the model's own numbers. Data quality drives the confidence wording, never the probability. Missing data is shown as N/A, never as 0.</p><p><b>High-probability selection</b> = model probability ≥ 70% with the de-margined price not contradicting it (no more than 12 points apart), price ≥ 1.30, goals/BTTS/team goals/corners/cards only. <b>⭐ Bets of the day</b> = the best of those at 07:00, one market per match. <b>Low data</b> = fewer than four useful matches for a team; those games are shown but never selected. No selection is ever certain — a 75% probability loses one time in four.</p>`));
    parts.push(sec('ticket', 'Bet slip & tickets', `<p>Tap <b>+</b> next to any priced selection (match page › Markets, high-probability selections, bets of the day) to put it on your slip — one selection per match, like a real multiple. Press <b>Done</b> to lock the ticket: PlayReport multiplies the prices, records an optional stake, and then follows the scores. Goals markets settle from the final score; corners and cards settle from the match statistics a few hours after full time. You get a notification when the ticket is won or lost, and ☰ › <b>My tickets</b> keeps your record.</p><p>This is a private record on your phone — nothing is placed with a bookmaker.</p>`));
    parts.push(sec('info', 'Reading the numbers honestly', `<p>A 75% bet loses one time in four. A card of five 75% singles has all five winning only about 24% of the time — that is why PlayReport shows singles and grades every one of them, and does not build accumulators. Compare the <b>Hit</b> and <b>Exp.</b> columns under Performance: they should be close over a few weeks.</p><p>Coverage: every competition on the live feed, worldwide, including women's and youth leagues, priced by Sportybet South Africa. Prices move; check the price before you bet. Statistical information, not betting advice. 18+, bet responsibly.</p>`));
    parts.push(sec('star', 'Bets of the day, favourites & alerts', `<p><b>⭐ Bets of the day</b> is strong on Over 1.5 & team goals (up to five picks); 1X2, Both teams to score and Over 2.5 only appear with strong supporting signals (model ≥70%, market not below it, recent form backing them, up to two each); Bookings and Corners follow. Overs only, one market per match, picked by the first analysis of the day and graded separately — so the performance page can compare the markets fairly. Every match page has <b>Download stats (CSV)</b> and the ☰ menu downloads the whole day's analysis as a spreadsheet file. <b>Top leagues</b> ranks the major leagues by home wins, away wins, overs, corners and bookings.</p><p>Tap <b>☆</b> in a match header to make it a favourite: you get goal, half-time, full-time and kick-off alerts for it, it appears under Your matches on Home, and in the ★ filter of Matches.</p>`));
    parts.push(PR.editorCard(false));
    parts.push(contactCard(false));
    view().innerHTML = parts.join('');
    wireBack();
  };

  // ------------------------------------------------------------------ SETTINGS
  function notifState() { if (!PR.native || !PR.native.notificationsAllowed) return null; try { return !!PR.native.notificationsAllowed(); } catch (e) { return null; } }
  PR.pages.settings = function () {
    const parts = [head('Settings')];
    const allowed = notifState();
    parts.push(`<div class="card settings"><h2>${icon('bell')} Notifications</h2>
      <div class="row"><div class="grow small">${allowed === false ? '<span class="chip bad">off</span> Allow notifications to get new bets, analysis, goal and update alerts.' : allowed ? '<span class="chip good">on</span> Checked about every 15 minutes in the background' : 'Notifications are only available in the Android app.'}</div>
      ${allowed === false ? '<button class="btn primary" id="s-notif">Allow</button>' : ''}</div>
      <label class="row" style="margin-top:10px"><input type="checkbox" id="s-bets" ${settings.betAlerts !== false ? 'checked' : ''}> <span class="grow">📈 New high-probability selections (found by the half-hourly refresh)</span></label>
      <label class="row" style="margin-top:6px"><input type="checkbox" id="s-reports" ${settings.reportAlerts !== false ? 'checked' : ''}> <span class="grow">📊 Full analysis published (07:00 · 12:00 · 17:00)</span></label>
      <label class="row" style="margin-top:6px"><input type="checkbox" id="s-goals" ${settings.goalAlerts ? 'checked' : ''}> <span class="grow">⚽ Score changes (goals with the scorer) in tracked matches — bets of the day, high-probability selections, shortlist and your tickets</span></label>
      <label class="row" style="margin-top:6px"><input type="checkbox" id="s-ht" ${settings.htAlerts ? 'checked' : ''}> <span class="grow">⏸ Half-time results of tracked matches</span></label>
      <label class="row" style="margin-top:6px"><input type="checkbox" id="s-ft" ${settings.ftAlerts !== false ? 'checked' : ''}> <span class="grow">🏁 Full-time results of tracked matches · tickets won / lost</span></label>
      <label class="row" style="margin-top:6px"><input type="checkbox" id="s-ko" ${settings.koAlerts !== false ? 'checked' : ''}> <span class="grow">⏰ Kick-off reminders (15 min before) for favourites and ticket matches</span></label>
      <label class="row" style="margin-top:6px"><input type="checkbox" id="s-tennis" ${settings.tennisAlerts !== false ? 'checked' : ''}> <span class="grow">🎾 Tennis favourites — finished matches with the set score</span></label></div>`);
    const SOUNDS = [['goals', 'goal', '⚽ Goal (crowd & horn)'], ['tennis', 'tennis', '🎾 Tennis — finished match'], ['tickets', 'tickets', '🎫 Ticket won / lost'], ['kickoff', 'kickoff', '⏰ Kick-off'], ['match', 'fulltime', '🏁 Half / full time'], ['bets', 'selection', '📈 New selection'], ['reports', 'report', '📊 Report published'], ['', 'card', '🟨 Referee whistle (gallery)']];
    parts.push(`<div class="card settings"><h2>${icon('bell')} Notification sounds</h2>
      <div class="small muted">Each alert type has its own short sound so you know what arrived without looking. Tap ▶ to preview; the gear opens Android's settings for that alert (sound, vibration, silent).</div>
      <div class="sounds">${SOUNDS.map(([ch, file, label]) => `<div class="row snd"><button class="btn sm" data-play="${file}">▶</button><span class="grow">${label}</span>${ch && PR.native && PR.native.openChannelSettings ? `<button class="btn sm" data-chan="${ch}" title="Android settings">${icon('settings', 'sm')}</button>` : ''}</div>`).join('')}</div></div>`);
    parts.push(`<div class="card settings"><h2>${icon('moon')} Appearance</h2>${segmented([['system', 'System'], ['light', 'Light'], ['dark', 'Dark']], settings.theme || 'system', 'th')}
      <div class="tiny muted" style="margin-top:6px">System follows your phone's dark-mode setting.</div></div>`);
    parts.push(`<div class="card settings"><h2>${icon('clock')} Display</h2>
      <label>Leagues shown in Bets and on Home</label>${segmented([['all', '🌍 All leagues'], ['major', '🏆 Major leagues only']], settings.leagues || 'all', 'lgs')}
      <label>Live auto-refresh (seconds, min 20)</label><input id="s-live" type="number" value="${settings.liveEvery}">
      <label>Analysis timezone offset from UTC (hours; South Africa = 2)</label><input id="s-tz" type="number" value="${settings.tzOffset}">
      <div style="margin-top:12px"><button class="btn primary" id="s-save">Save</button><button class="btn" id="s-clear">Clear saved data</button></div>
      <div class="tiny muted" style="margin-top:6px">${(() => { const c = PR.cache.size(); return `${c.n} analysed pages saved on this phone (${c.kb} KB) — they open instantly and refresh in the background.`; })()}</div></div>`);
    parts.push(`<div class="card settings"><h2>${icon('info')} App</h2><div class="row"><div class="grow small">PlayReport ${PR.APP_VERSION ? 'v' + PR.APP_VERSION : '(browser preview)'}${state.update ? ` · <b>v${esc(state.update.version)} available</b>` : ' · up to date'}</div>
      ${state.update ? `<button class="btn primary" id="s-install">Update</button>` : `<button class="btn" id="s-check">Check for update</button>`}</div>
      ${state.update && PR.notesList(state.update.notes).length ? `<div class="small" style="margin-top:8px"><b>What's new in ${esc(state.update.version)}</b><ul class="notes">${PR.notesList(state.update.notes).map((x) => `<li>${esc(x)}</li>`).join('')}</ul></div>` : ''}
      <div class="tiny muted" style="margin-top:6px">PlayReport checks for updates automatically and downloads them for you; Android asks for one confirmation before installing. Your tickets, favourites and settings are kept.</div>
      <div style="margin-top:8px"><button class="btn" id="s-whatsnew">What's new in this version</button></div></div>`);
    parts.push(PR.editorCard(false));
    parts.push(contactCard(false));
    parts.push(`<div class="card small"><b>About PlayReport</b><div class="muted" style="margin-top:4px">Football analysis for every competition worldwide, refreshed every 30 minutes with a full report at 07:00, 12:00 and 17:00 SAST: expected goals, probabilities for every market, high-probability selections, bets of the day, trends, head-to-head, live scores and an audited day-by-day record. Live scores come from a public feed and never influence the model.</div>
      <div class="muted" style="margin-top:6px">Statistical information, not betting advice. Bet responsibly — 18+.</div></div>`);
    view().innerHTML = parts.join('');
    wireBack();
    const pref = (k, v) => { if (PR.native && PR.native.setPref) { try { PR.native.setPref(k, !!v); } catch (e) { /* ignore */ } } };
    $('#s-save').onclick = () => { settings.liveEvery = Math.max(20, +$('#s-live').value || 60); settings.tzOffset = +$('#s-tz').value || 0; PR.saveSettings(); live.schedule(); toast('Saved'); PR.back(); };
    $('#s-clear').onclick = () => { localStorage.removeItem('pr_latest'); PR.cache.clear(); state.data = null; state.days = {}; state.teams = {}; state.details = {}; toast('Saved data cleared'); state.stack = []; PR.loadData(true); };
    $('#s-goals').onchange = (e) => { settings.goalAlerts = e.target.checked; PR.saveSettings(); pref('goals', settings.goalAlerts); };
    $('#s-bets').onchange = (e) => { settings.betAlerts = e.target.checked; PR.saveSettings(); pref('bets', settings.betAlerts); };
    $('#s-reports').onchange = (e) => { settings.reportAlerts = e.target.checked; PR.saveSettings(); pref('reports', settings.reportAlerts); };
    $('#s-ht').onchange = (e) => { settings.htAlerts = e.target.checked; PR.saveSettings(); pref('ht', settings.htAlerts); };
    $('#s-ko').onchange = (e) => { settings.koAlerts = e.target.checked; PR.saveSettings(); pref('ko', settings.koAlerts); };
    $('#s-tennis').onchange = (e) => { settings.tennisAlerts = e.target.checked; PR.saveSettings(); pref('tennis', settings.tennisAlerts); };
    $('#s-ft').onchange = (e) => { settings.ftAlerts = e.target.checked; PR.saveSettings(); pref('ft', settings.ftAlerts); };
    $$('[data-th]').forEach((b) => { b.onclick = () => { settings.theme = b.dataset.th; PR.saveSettings(); PR.applyTheme(); PR.render(); }; });
    $$('[data-lgs]').forEach((b) => { b.onclick = () => { settings.leagues = b.dataset.lgs; PR.saveSettings(); PR.render(); }; });
    const n = $('#s-notif'); if (n) n.onclick = () => { if (PR.native && PR.native.requestNotifications) PR.native.requestNotifications(); };
    const wn = $('#s-whatsnew'); if (wn) wn.onclick = () => { settings.seenVersion = ''; PR.saveSettings(); state.stack = []; PR.setTab('home'); };
    const c = $('#s-check'); if (c) c.onclick = () => { toast('Checking…'); state.updateChecked = 'manual'; if (PR.native && PR.native.checkUpdate) PR.native.checkUpdate(); else toast('Updates are only available in the Android app'); };
    const i = $('#s-install'); if (i) i.onclick = () => PR.startUpdate();
    $$('[data-play]').forEach((b) => { b.onclick = () => { try { const a = new Audio(`sounds/pr_${b.dataset.play}.ogg`); a.volume = 0.9; a.play().catch(() => toast('Preview not available here')); } catch (e) { toast('Preview not available here'); } }; });
    $$('[data-chan]').forEach((b) => { b.onclick = () => { try { PR.native.openChannelSettings(b.dataset.chan); } catch (e) { toast('Open Android Settings → Apps → PlayReport → Notifications'); } }; });
  };
})(window.PR);
