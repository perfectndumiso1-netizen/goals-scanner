/* PlayReport — tab views: Home, Bets, Live, Matches, Days. */
(function (PR) {
  'use strict';
  const { $, $$, esc, pct, f1, f2, signed, state, settings, fx, pill, koShort, koTime, dayName, toast, selLabel, selShort, selGroup,
    GROUPS, GROUP_ICON, liveVerdict, isLive, isFT, segmented, select, contactCard, matchRow, tzNow, parseLocal, ymd, icon, flag, badge, fxBadge } = PR;
  const sh = (ico, title, cls) => `<h2><span class="ico ${cls || ''}">${icon(ico)}</span>${title}</h2>`;
  const view = () => $('#view');
  const MK = { O15: 'Over 1.5 goals', O25: 'Over 2.5 goals', BTTS: 'Both teams to score' };
  const FAMILY = { goals: ['goals', 'btts', 'team'], corners: ['corners'], cards: ['cards'] };
  const majorOnly = () => settings.leagues === 'major';
  const inScope = (f) => !majorOnly() || !f || f.major;

  // ------------------------------------------------------------------ live data (shared by Live tab, Home strip, match page)
  const live = PR.live;
  live.for = (f) => f && f.livescore_id ? state.live[f.livescore_id] : null;
  live.tracked = function () {
    const d = state.data; const ids = new Set(d.tracked || []);
    if (PR.ticketFixtures) PR.ticketFixtures().forEach((id) => ids.add(id));
    if (PR.favList) PR.favList().forEach((f) => ids.add(f.fixture));
    return (d.fixtures || []).filter((f) => ids.has(f.id)).sort((a, b) => a.kickoff.localeCompare(b.kickoff));
  };
  const LIVE_STATUS = (e) => e.Eps || '';
  live.refresh = async function (manual) {
    const d = state.data; if (!d) return;
    const tracked = live.tracked().filter((f) => f.livescore_id);
    const now = tzNow(); const days = new Set(tracked.map((f) => f.kickoff.slice(0, 10))); days.add(ymd(now));
    if (now.getHours() < 3) days.add(ymd(new Date(now.getTime() - 86400000)));
    const want = new Set(tracked.map((f) => f.livescore_id));
    const byEid = {}; (d.fixtures || []).forEach((f) => { if (f.livescore_id) byEid[f.livescore_id] = f; });
    const goalEvents = []; const all = []; const seenAll = new Set(); const phaseEvents = [];
    for (const day of days) {
      try {
        const j = await PR.getJson(`https://prod-public-api.livescore.com/v1/api/app/date/soccer/${day.replace(/-/g, '')}/${settings.tzOffset}?MD=1`);
        (j.Stages || []).forEach((st) => (st.Events || []).forEach((e) => {
          const eid = String(e.Eid); const status = LIVE_STATUS(e);
          const ns = !status || status === 'NS';
          const cur = { status, hg: !ns && e.Tr1 != null && e.Tr1 !== '' ? +e.Tr1 : null, ag: !ns && e.Tr2 != null && e.Tr2 !== '' ? +e.Tr2 : null, ht: [e.Trh1, e.Trh2], t: Date.now() };
          const prev = state.live[eid];
          state.live[eid] = cur;
          if (want.has(eid) && prev && prev.hg != null && cur.hg != null && (cur.hg + cur.ag) > (prev.hg + prev.ag)) goalEvents.push(eid);
          if (want.has(eid) && prev && prev.status !== cur.status && (cur.status === 'HT' || isFT(cur))) phaseEvents.push(eid);
          if (isLive(cur) && !seenAll.has(eid)) {
            seenAll.add(eid);
            const t1 = (e.T1 || [])[0] || {}, t2 = (e.T2 || [])[0] || {};
            all.push({ eid, status, hg: cur.hg, ag: cur.ag, home: t1.Nm || '?', away: t2.Nm || '?', img: [t1.Img, t2.Img], country: st.Cnm || '', league: st.Snm || '', fixture: byEid[eid] ? byEid[eid].id : null, esd: String(e.Esd || '') });
          }
        }));
      } catch (e) { if (manual) toast('Live scores unavailable (' + e.message + ')'); }
    }
    state.liveAll = all; state.lastLiveAll = Date.now();
    state.lastLive = Date.now();
    const dot = $('#live-dot'); if (dot) dot.classList.toggle('on', live.inPlay().length > 0);
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
    phaseEvents.forEach(announcePhase);
    if (PR.settleTickets) PR.settleTickets(true);
  };
  function announcePhase(eid) {
    const f = live.tracked().find((x) => x.livescore_id === eid); const s = state.live[eid]; if (!f || !s) return;
    const ht = s.status === 'HT';
    if (ht && !settings.htAlerts) return; if (!ht && !settings.ftAlerts) return;
    const bets = betsFor(f.id).map((b) => `${b.label}: ${liveVerdict(b.sel, s).text}`).join(' · ');
    const title = `${ht ? '⏸ Half-time' : '🏁 Full-time'}  ${f.home} ${s.hg} – ${s.ag} ${f.away}`;
    const text = (bets ? bets + ' · ' : '') + f.competition;
    if (PR.native && PR.native.notify) { try { PR.native.notify('match', (ht ? 5000 : 6000) + (parseInt(eid, 10) % 1000), title, text, 'live'); } catch (e) { /* ignore */ } } else toast(title);
  }
  function betsFor(fid) {
    const d = state.data, out = [], sf = d.safe || { bets: [] };
    ((sf.today && sf.today.bets) || []).filter((b) => b.fixture === fid).forEach((b) => out.push({ label: b.label, sel: b.sel }));
    (sf.bets || []).filter((b) => b.fixture === fid && !out.some((o) => o.sel === b.sel)).forEach((b) => out.push({ label: b.label, sel: b.sel }));
    if (PR.tickets) PR.tickets().forEach((t) => { if (t.status === 'pending') t.legs.filter((l) => l.fixture === fid && !out.some((o) => o.sel === l.sel)).forEach((l) => out.push({ label: '🎫 ' + l.label, sel: l.sel })); });
    return out;
  }
  function announceGoal(eid) {
    if (!settings.goalAlerts) return;
    const f = live.tracked().find((x) => x.livescore_id === eid); const s = state.live[eid]; if (!f || !s) return;
    const inc = state.incidents[eid]; const goals = inc ? inc.items.filter((it) => ['goal', 'own goal', 'penalty'].includes(it.type)) : [];
    const last = goals.length ? goals[goals.length - 1] : null;
    const scorer = last ? `${last.player || ''} ${last.min != null ? last.min + "'" : ''}${last.type !== 'goal' ? ' (' + last.type + ')' : ''}`.trim() : '';
    const title = `⚽ GOAL  ${f.home} ${s.hg} – ${s.ag} ${f.away}`;
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
      const active = (state.tab === 'live' && state.liveView === 'all') || live.tracked().some((f) => { const s = live.for(f); const ko = parseLocal(f.kickoff); return isLive(s) || (ko && !isFT(s) && Math.abs(now - ko) < 3 * 3600 * 1000); });
      if (active) live.refresh(false);
    }, Math.max(20, settings.liveEvery) * 1000);
  };
  live.inPlay = () => live.tracked().filter((f) => isLive(live.for(f)));

  // ------------------------------------------------------------------ bets helpers
  function safeList(group) {
    const sf = state.data.safe || { bets: [] };
    let lst = (sf.bets || []).filter((b) => inScope(fx(b.fixture)));
    if (group && group !== 'all') lst = lst.filter((b) => (FAMILY[group] || [group]).includes(b.group));
    return lst;
  }
  function betStatus(b) {
    if (b.status && b.status !== 'pending') return b.status === 'hit' || b.status === 'won' ? { cls: 'good', text: '✅ won' } : b.status === 'void' ? { cls: '', text: 'void' } : { cls: 'bad', text: '❌ lost' };
    const f = fx(b.fixture); const s = live.for(f);
    return liveVerdict(b.sel, s);
  }
  function safeRow(b, opts) {
    opts = opts || {}; const f = fx(b.fixture); const st = betStatus(b);
    const tap = f ? `class="tap" data-fx="${esc(b.fixture)}"` : '';
    return `<tr ${tap}><td class="tiny muted nowrap">${esc(opts.time ? koTime(b.kickoff) : koShort(b.kickoff))}</td>
      <td><div class="row" style="gap:6px">${badge(b.home, b.badges && b.badges.home, 20)}${badge(b.away, b.badges && b.badges.away, 20)}<div class="b grow">${esc(b.home)} <span class="muted">v</span> ${esc(b.away)}</div></div>
      <div class="sel"><b>${esc(b.label)}</b></div><div class="tiny muted">${flag(b.country)} ${esc(b.league)}${st.text !== 'not started' ? ` · <span class="${st.cls}">${esc(st.text)}</span>` : ''}</div></td>
      <td class="right nowrap"><b>${f2(b.odds)}</b></td><td class="right"><div class="row" style="gap:0;justify-content:flex-end">${pill(b.p, 0.8, 0.7)}${PR.addBtn ? PR.addBtn(b.fixture, b.sel, b.odds) : ''}</div></td></tr>`;
  }
  function selRow(f, s) {
    return `<tr class="tap" data-fx="${esc(f.id)}"><td class="tiny muted nowrap">${esc(koShort(f.kickoff))}</td>
      <td><div class="match">${esc(f.home)} <span class="muted">v</span> ${esc(f.away)}</div><div class="sel"><b>${esc(selLabel(s.sel, f.home, f.away))}</b></div><div class="tiny muted">${flag(f.country)} ${esc(f.competition)}${s.diff ? ' · <span class="warn">views differ</span>' : ''}</div></td>
      <td class="right nowrap">${s.odds ? `<b>${f2(s.odds)}</b>` : '<span class="muted">–</span>'}</td><td class="right"><div class="row" style="gap:0;justify-content:flex-end">${pill(s.p, 0.8, 0.7)}${PR.addBtn ? PR.addBtn(f.id, s.sel, s.odds) : ''}</div></td></tr>`;
  }
  function botdCard(compact) {
    const sf = state.data.safe || {}; const today = sf.today || { bets: [] }; const bets = today.bets || []; const groups = today.groups || [];
    const settled = bets.filter((b) => b.status && b.status !== 'pending'); const won = settled.filter((b) => b.status === 'hit' || b.status === 'won').length;
    const rec = (sf.summary && sf.summary.botd) || {};
    const head = `<div class="section-head">${sh('star', 'Bets of the day', 'amber')}${compact ? `<button class="link" data-bets="today">Details ${icon('next')}</button>` : `<span class="tiny muted">${esc(dayName(today.date || ''))}</span>`}</div>`;
    if (!bets.length) return head + `<div class="card empty small">Today's card is built from the first analysis of the day (07:00) and topped up section by section during the day.</div>`;
    const sec = (g) => `<div class="botd-sec">${esc(g.title)}</div><table class="tbl">${g.bets.slice(0, compact ? 2 : 3).map((b) => safeRow(b, { time: true })).join('')}</table>`;
    const body = groups.length ? groups.map(sec).join('') : `<table class="tbl">${bets.map((b) => safeRow(b, { time: true })).join('')}</table>`;
    return head + `<div class="card botd">${body}
      <div class="row tiny muted" style="margin-top:6px"><div class="grow">${settled.length ? `Today: ${won}/${settled.length} won${bets.length > settled.length ? ` · ${bets.length - settled.length} to play` : ''}` : `${bets.length} singles in ${groups.length || 1} section${groups.length === 1 ? '' : 's'} · overs only`}</div>${rec.all && rec.all.n ? `<div>record ${rec.all.won}/${rec.all.n} (${pct(rec.all.rate)})</div>` : ''}</div></div>`;
  }
  PR.safeRow = safeRow; PR.betStatus = betStatus;

  // ------------------------------------------------------------------ HOME
  PR.views.home = function () {
    const d = state.data, m = d.meta, sf = d.safe || { bets: [] }; const parts = [];
    const inPlay = live.inPlay(); const cov = m.coverage || {};
    const safe = safeList('all');
    parts.push(`<div class="card hero"><div class="eyebrow">Live analysis · updated every 30 minutes</div><div class="b" style="font-size:17px">${esc(dayName(m.generated))} · ${esc(koTime(m.generated))} ${esc(m.tz)}</div>
      <div class="tiny muted">Next update ${esc(koTime(m.next_run || ''))} · ${cov.competitions || '–'} competitions worldwide · ${cov.priced || 0} priced by Sportybet</div>
      <div class="hero-nums"><div><b>${m.fixtures}</b><span>matches</span></div><div><b>${(sf.today && sf.today.bets ? sf.today.bets.length : 0)}</b><span>bets of the day</span></div><div><b>${safe.length}</b><span>safest bets</span></div><div><b>${(state.liveAll || []).length || inPlay.length}</b><span>in play</span></div></div>
      ${inPlay.length ? `<div class="live-strip" data-tab-go="live"><span class="status-dot live"></span><div class="grow"><b>${inPlay.length} tracked in play</b> · ${inPlay.slice(0, 2).map((f) => { const s = live.for(f); return `${esc(f.home)} ${s.hg}–${s.ag} ${esc(f.away)}`; }).join(' · ')}${inPlay.length > 2 ? ' …' : ''}</div>${icon('next', 'sm')}</div>` : ''}</div>`);
    if (PR.APP_VERSION && settings.seenVersion !== PR.APP_VERSION) {
      parts.push(`<div class="card whatsnew"><div class="row"><div class="grow"><b>${icon('sparkle', 'sm')} New in PlayReport ${esc(PR.APP_VERSION)}</b></div><button class="link" id="wn-close">${icon('x')}</button></div>
        <ul><li>⚡ Instant pages: analysed matches, day history and team pages are saved on your phone and open at once — even offline</li><li>🔄 Updates keep your tickets, favourites and settings; new versions announce themselves with their release notes</li><li>📥 <b>Download stats (CSV)</b> on every analysed match, and the whole day's analysis from the ☰ menu — opens in Google Sheets</li><li>⭐ Bets of the day rebuilt: strong on Over 1.5 & team goals; 1X2, BTTS and Over 2.5 only with strong supporting form; one market per match</li><li>📊 One tracked market per match in Performance, so markets can be compared fairly</li><li>✅ Every publication is checked before it reaches the app; more league history archived from past seasons</li></ul></div>`);
    }
    parts.push(botdCard(true));
    if (PR.ticketsCard && PR.tickets().some((t) => t.status === 'pending')) parts.push(PR.ticketsCard(true));
    const favs = (PR.favList ? PR.favList() : []).map((x) => fx(x.fixture)).filter(Boolean).sort((a, b) => a.kickoff.localeCompare(b.kickoff));
    if (favs.length) parts.push(`<div class="section-head"><h2><span class="ico amber">${icon('star')}</span>Your matches</h2><button class="link" data-tab-go="matches" data-mf-go="fav">All ${favs.length} ${icon('next')}</button></div><div class="card compact">${favs.slice(0, 5).map((f) => { const s = live.for(f); return matchRow(f, { live: s, sub: `${flag(f.country)} ${esc(f.competition)}${f.safe ? ` · 🔒 <b>${esc(selShort(f.safe[0]))}</b> ${pct(f.safe[1])}` : ''}`, right: s && s.hg != null ? '' : `<span class="pill ${f.p.O25 >= 0.6 ? 'hi' : ''}">O2.5 ${pct(f.p.O25)}</span>` }); }).join('')}</div>`);
    parts.push(`<div class="section-head">${sh('lock', 'Safest bets', 'green')}<button class="link" data-bets="safest">All ${safe.length} ${icon('next')}</button></div>`);
    if (!safe.length) parts.push(`<div class="card empty small">Nothing priced at ≥ ${f2(sf.min_odds || 1.3)} reached ${pct(sf.min_p || 0.7)} on both views${majorOnly() ? ' in the major leagues' : ''}.</div>`);
    else parts.push(`<div class="card compact"><table class="tbl">${safe.slice(0, 5).map((b) => safeRow(b)).join('')}</table></div>`);
    const pk = d.picks || {};
    parts.push(`<div class="card compact"><div class="row" style="flex-wrap:wrap"><div class="grow b">Explore</div></div>
      <div class="chips">${['O15', 'O25', 'BTTS'].map((k) => `<button class="chip tapchip" data-bets="picks">${icon('star', 'sm')} ${esc(MK[k])} <b>${(pk[k] || []).length}</b></button>`).join('')}<button class="chip tapchip" data-bets="corners">${icon('corner', 'sm')} Corners</button><button class="chip tapchip" data-bets="cards">${icon('card', 'sm')} Cards</button><button class="chip tapchip" data-page-go="guide">${icon('info', 'sm')} Guide to the markets</button></div></div>`);
    const now = tzNow(); const upcoming = d.fixtures.filter((f) => inScope(f) && f.data_ok && f.priced && parseLocal(f.kickoff) > now - 2 * 3600000).sort((a, b) => a.kickoff.localeCompare(b.kickoff)).slice(0, 6);
    parts.push(`<div class="section-head">${sh('calendar', 'Next kick-offs')}<button class="link" data-tab-go="matches">All matches ${icon('next')}</button></div><div class="card compact">${upcoming.map((f) => { const s = live.for(f); const best = f.top;
      return matchRow(f, { live: s, sub: `${flag(f.country)} ${esc(f.competition)}${best ? ` · <b>${esc(selShort(best[0]))}</b> ${pct(best[1])} @ ${f2(best[2])}` : ''}`, right: s && s.hg != null ? '' : `<span class="pill ${f.p.O25 >= 0.6 ? 'hi' : ''}">O2.5 ${pct(f.p.O25)}</span><span class="tiny muted">BTTS ${pct(f.p.BTTS)}</span>` }); }).join('') || '<div class="empty small">No upcoming matches in the window.</div>'}</div>`);
    parts.push(PR.editorCard(true));
    parts.push(contactCard(true));
    view().innerHTML = parts.join('');
    wireCommon(); if (PR.wireTickets) PR.wireTickets();
    const wn = $('#wn-close'); if (wn) wn.onclick = () => { settings.seenVersion = PR.APP_VERSION; PR.saveSettings(); PR.render(); };
  };
  function wireCommon() {
    $$('[data-bets]').forEach((b) => { b.onclick = (e) => { e.stopPropagation(); state.betsView = b.dataset.bets; PR.setTab('bets'); }; });
    $$('[data-tab-go]').forEach((b) => { b.onclick = (e) => { e.stopPropagation(); if (b.dataset.mfGo) state.matchFilter = b.dataset.mfGo; PR.setTab(b.dataset.tabGo); }; });
    $$('[data-page-go]').forEach((b) => { b.onclick = (e) => { e.stopPropagation(); PR.push({ type: b.dataset.pageGo }); }; });
  }

  // ------------------------------------------------------------------ BETS
  const leagueChips = () => `<div class="chips small-chips"><button class="chip tapchip ${!majorOnly() ? 'on' : ''}" data-lg="all">🌍 All leagues</button><button class="chip tapchip ${majorOnly() ? 'on' : ''}" data-lg="major">🏆 Major leagues</button></div>`;
  PR.views.bets = function () {
    const parts = []; const v = state.betsView || 'today';
    parts.push(`<div class="card compact sticky-ish">${segmented([['today', `${icon('star')} Today`], ['top', `${icon('shield')} Top leagues`], ['safest', `${icon('lock')} Safest`], ['goals', `${icon('ball')} Goals`], ['corners', `${icon('corner')} Corners`], ['cards', `${icon('card')} Cards`], ['picks', `${icon('trend')} Shortlist`]], v, 'bv')}</div>`);
    if (v === 'today') renderToday(parts);
    else if (v === 'top') renderTop(parts);
    else if (v === 'safest') renderSafest(parts);
    else if (v === 'picks') renderPicks(parts);
    else renderFamily(parts, v);
    parts.push(`<div class="card compact tap" id="guide-link"><div class="row"><span class="ico">${icon('info')}</span><div class="grow"><b>What do these markets mean?</b><div class="tiny muted">Over/Under, BTTS, team goals, corners, cards — and how the probabilities are made.</div></div>${icon('next')}</div></div>`);
    view().innerHTML = parts.join('');
    $$('[data-bv]').forEach((b) => { b.onclick = () => { state.betsView = b.dataset.bv; PR.render(); window.scrollTo(0, 0); }; });
    $$('[data-lg]').forEach((b) => { b.onclick = () => { settings.leagues = b.dataset.lg; PR.saveSettings(); PR.render(); }; });
    const hp = $('#f-hip'); if (hp) hp.onchange = (e) => { settings.hiP = +e.target.value; PR.saveSettings(); PR.render(); };
    const mg = $('#f-group'); if (mg) mg.onchange = (e) => { state.betGroup = e.target.value; PR.render(); };
    $$('[data-more]').forEach((b) => { b.onclick = () => { state.expanded[b.dataset.more] = true; PR.render(); }; });
    const g = $('#guide-link'); if (g) g.onclick = () => PR.push({ type: 'guide' });
    $$('[data-board]').forEach((b) => { b.onclick = () => { state.board = b.dataset.board; PR.render(); }; });
    wireCommon(); if (PR.wireTickets) PR.wireTickets();
  };
  const BOARDS = [['H', 'Home wins'], ['A', 'Away wins'], ['O15', 'Over 1.5'], ['O25', 'Over 2.5'], ['BTTS', 'BTTS'], ['CO95', 'Corners 9.5+'], ['KO35', 'Bookings 3.5+']];
  function renderTop(parts) {
    const key = state.board || 'H'; const title = (BOARDS.find((b) => b[0] === key) || [])[1] || key;
    parts.push(`<div class="card compact">${leagueChips()}<div class="chips small-chips" style="margin-top:6px">${BOARDS.map(([k, l]) => `<button class="chip tapchip ${key === k ? 'on' : ''}" data-board="${k}">${l}</button>`).join('')}</div>
      <div class="tiny muted" style="margin-top:4px">${majorOnly() ? 'The 38 major leagues (top divisions of Europe, the Americas and Asia plus England / Scotland / Germany / Italy / Spain / France lower tiers)' : 'Every competition'} ranked by the probability of <b>${esc(title)}</b>. Price = Sportybet where the match is priced; + adds the selection to your slip.</div></div>`);
    const now = tzNow();
    const lst = (state.data.fixtures || []).filter((f) => inScope(f) && f.data_ok && f.bo && f.bo[key] && parseLocal(f.kickoff) > now).map((f) => ({ f, p: f.bo[key][0], odds: f.bo[key][1] })).sort((a, b) => b.p - a.p);
    if (!lst.length) { parts.push(`<div class="card empty">Nothing to show for ${esc(title)}${key === 'CO95' || key === 'KO35' ? ' — corners and bookings need match statistics for both teams' : ''}.</div>`); return; }
    const max = state.expanded['top_' + key] ? lst.length : 20;
    parts.push(`<div class="card compact"><table class="tbl head"><tr><th></th><th>Match</th><th class="right">Price</th><th class="right">Prob.</th></tr>${lst.slice(0, max).map(({ f, p, odds }) => `<tr class="tap" data-fx="${esc(f.id)}"><td class="tiny muted nowrap">${esc(koShort(f.kickoff))}</td><td><div class="row" style="gap:6px">${fxBadge(f, 'home').replace('s24', 's20')}${fxBadge(f, 'away').replace('s24', 's20')}<div class="b grow">${esc(f.home)} <span class="muted">v</span> ${esc(f.away)}</div></div><div class="tiny muted">${flag(f.country)} ${esc(f.competition)} · ${esc(selLabel(key, f.home, f.away))}</div></td><td class="right nowrap">${odds ? `<b>${f2(odds)}</b>` : '<span class="muted">–</span>'}</td><td class="right"><div class="row" style="gap:0;justify-content:flex-end">${pill(p, 0.7, 0.6)}${PR.addBtn ? PR.addBtn(f.id, key, odds) : ''}</div></td></tr>`).join('')}</table>${lst.length > max ? `<button class="btn wide" data-more="top_${key}">Show all ${lst.length}</button>` : ''}</div>`);
  }
  function renderToday(parts) {
    parts.push(botdCard(false));
    if (PR.ticketsCard) parts.push(PR.ticketsCard(false));
    const rec = ((state.data.safe || {}).summary || {}).botd || {};
    parts.push(`<div class="card small"><b>How the card is picked</b><div class="muted" style="margin-top:4px">Strong on <b>Over 1.5 & team goals</b> (≥70%, up to five picks). <b>1X2</b>, <b>Both teams to score</b> and <b>Over 2.5</b> only appear with strong supporting signals: ≥70% on both the model and the market view <i>and</i> recent form backing the pick (up to two each). Bookings and Corners need ≥65%. Overs only, Sportybet price ≥ 1.30, one market per match across the whole card. Picks are made by the first analysis that sees them and kept for the day; every one is graded automatically.</div>
      ${rec.all && rec.all.n ? `<table class="tbl head" style="margin-top:8px"><tr><th>Bets of the day</th><th class="right">Won</th><th class="right">Hit</th><th class="right">Exp.</th><th class="right">Return</th></tr>${[['All time', rec.all], ['Last 30 days', rec['30d']]].filter(([, s]) => s && s.n).map(([n, s]) => `<tr><td>${n}</td><td class="right">${s.won}/${s.n}</td><td class="right"><b>${pct(s.rate)}</b></td><td class="right muted">${pct(s.exp_rate)}</td><td class="right ${s.roi > 0 ? 'good' : s.roi < 0 ? 'bad' : ''}">${signed(s.roi)}</td></tr>`).join('')}</table>` : '<div class="tiny muted" style="margin-top:6px">The record starts with the first settled card.</div>'}</div>`);
  }
  function renderSafest(parts) {
    const sf = state.data.safe || {}; const lst = safeList(state.betGroup || 'all');
    const groupOptions = [['all', 'All markets'], ['goals', 'Goals (incl. BTTS, team goals)'], ['corners', 'Corners'], ['cards', 'Cards']];
    parts.push(`<div class="card compact">${leagueChips()}<div class="filters" style="margin-top:6px"><label>Market ${select('f-group', groupOptions, state.betGroup || 'all')}</label></div>
      <div class="tiny muted">Safest = at least ${pct(sf.min_p || 0.7)} on <b>both</b> the calibrated model and the de-margined Sportybet price, price ≥ ${f2(sf.min_odds || 1.3)}, in the goals, corners and cards markets. New ones are added every 30 minutes and announced. Each one is graded in Days.</div></div>`);
    if (!lst.length) parts.push(`<div class="card empty">No safest bet in this window${majorOnly() ? ' for the major leagues' : ''}.</div>`);
    else {
      const max = state.expanded.safest ? lst.length : 30;
      parts.push(`<div class="card compact"><table class="tbl head"><tr><th></th><th>Match · selection</th><th class="right">Price</th><th class="right">Prob.</th></tr>${lst.slice(0, max).map((b) => safeRow(b)).join('')}</table>
        ${lst.length > max ? `<button class="btn wide" data-more="safest">Show all ${lst.length}</button>` : ''}</div>`);
    }
    const ss = (sf.summary || {}).bets || {};
    if (ss.all && ss.all.n) parts.push(`<div class="card small"><b>Track record</b> — safest bets settled: ${ss.all.won}/${ss.all.n} hit (${pct(ss.all.rate)}, expected ${pct(ss.all.exp_rate)}) · flat-stake return ${signed(ss.all.roi)}${ss['30d'] && ss['30d'].n ? ` · last 30 days ${ss['30d'].won}/${ss['30d'].n}` : ''} · ${ss.pending || 0} pending. Full breakdown under ☰ › Performance.</div>`);
  }
  function renderFamily(parts, fam) {
    const minP = settings.hiP || 0.7; const groups = FAMILY[fam] || [fam];
    const safe = safeList(fam);
    const title = { goals: 'Goals markets', corners: 'Corners', cards: 'Cards & bookings' }[fam] || fam;
    parts.push(`<div class="card compact">${leagueChips()}<div class="filters" style="margin-top:6px"><label>Probability ≥ ${select('f-hip', [[0.7, '70%'], [0.75, '75%'], [0.8, '80%'], [0.85, '85%'], [0.9, '90%']], minP)}</label></div>
      <div class="tiny muted">${fam === 'goals' ? 'Over/Under, both teams to score and team goals.' : fam === 'corners' ? 'Total corners — modelled for the leagues with corner statistics (the 22 main European leagues) and priced by Sportybet.' : 'Total cards (yellow = 1, red = 2 on Sportybet) — modelled for the 22 main European leagues from team and referee averages.'} Safest bets first, then every other selection at or above the threshold.</div></div>`);
    if (safe.length) parts.push(`<div class="card compact"><div class="row"><div class="grow b">${icon('lock', 'sm')} Safest ${title.toLowerCase()}</div><span class="chip good">${safe.length}</span></div><table class="tbl">${safe.map((b) => safeRow(b)).join('')}</table></div>`);
    // other high-probability selections need the per-match details; use the index's top/safe and the priced flag
    const lst = [];
    (state.data.fixtures || []).forEach((f) => { if (!inScope(f) || !f.data_ok) return; (f.hi || []).forEach((x) => { const s = { sel: x[0], p: x[1], odds: x[2] }; if (s.p >= minP && groups.includes(selGroup(s.sel)) && !safe.some((b) => b.fixture === f.id && b.sel === s.sel)) lst.push({ f, s }); }); });
    lst.sort((a, b) => b.s.p - a.s.p);
    if (lst.length) {
      const key = 'fam_' + fam; const max = state.expanded[key] ? lst.length : 25;
      parts.push(`<div class="card compact"><div class="row"><div class="grow b">${icon('trend', 'sm')} Other selections ≥ ${pct(minP)}</div><span class="chip">${lst.length}</span></div><table class="tbl">${lst.slice(0, max).map((x) => selRow(x.f, x.s)).join('')}</table>${lst.length > max ? `<button class="btn wide" data-more="${key}">Show all ${lst.length}</button>` : ''}</div>`);
    } else if (!safe.length) parts.push(`<div class="card empty">Nothing at or above ${pct(minP)} in ${title.toLowerCase()} right now.</div>`);
  }
  function renderPicks(parts) {
    const d = state.data, m = d.meta;
    parts.push(`<div class="card small">${leagueChips()}<div style="margin-top:6px"><b>Goals shortlists</b> — the matches most likely to produce goals, ranked by probability (⭐ = threshold, ⭐⭐⭐ = very strong). These are match ratings, not priced bets: use them to pick games to watch or to build your own selections.</div></div>`);
    for (const mk of ['O15', 'O25', 'BTTS']) {
      const lst = (d.picks[mk] || []).filter((p) => inScope(fx(p.fixture)));
      parts.push(`<div class="card compact"><div class="row"><div class="grow"><b>${MK[mk]}</b> <span class="muted small">· threshold ${pct(m.thresholds[mk])}</span></div><span class="chip">${lst.length}</span></div>`);
      if (!lst.length) parts.push(`<div class="muted small">None met the criteria.</div>`);
      else parts.push(`<table class="tbl">${lst.map((p) => { const f = fx(p.fixture); if (!f) return ''; return `<tr class="tap" data-fx="${esc(f.id)}"><td class="tiny muted nowrap">${esc(koShort(f.kickoff))}</td><td><div class="row" style="gap:6px">${fxBadge(f, 'home').replace('s24', 's20')}${fxBadge(f, 'away').replace('s24', 's20')}<div class="b grow">${esc(f.home)} v ${esc(f.away)}</div></div><div class="tiny muted">${flag(f.country)} ${esc(f.competition)}</div></td><td class="right">${p.sportybet ? `<b>${f2(p.sportybet)}</b>` : '<span class="muted">–</span>'}</td><td class="right">${pill(p.p, 0.7, 0.6)}<div class="stars">${esc(p.stars)}</div></td></tr>`; }).join('')}</table>`);
      parts.push(`<div class="tiny muted" style="margin-top:6px">Backtest: ${esc(m.backtest[mk] || '')}</div></div>`);
    }
    const t = d.tracker || {};
    parts.push(`<div class="card"><b>Shortlist tracker</b><table class="tbl head" style="margin-top:6px"><tr><th>Market</th><th class="right">Settled</th><th class="right">Hit</th><th class="right">30d</th><th class="right">Pending</th></tr>${['O15', 'O25', 'BTTS'].map((mk) => { const s = t[mk] || {}; return `<tr><td>${MK[mk]}</td><td class="right">${s.settled || 0}</td><td class="right">${pct(s.rate)}</td><td class="right">${pct(s.recent_rate)}</td><td class="right">${s.pending || 0}</td></tr>`; }).join('')}</table></div>`);
  }

  // ------------------------------------------------------------------ LIVE
  PR.views.live = function () {
    const d = state.data; const tracked = live.tracked(); const parts = []; const v = state.liveView || 'tracked';
    const nLive = tracked.filter((f) => isLive(live.for(f))).length; const all = state.liveAll || [];
    parts.push(`<div class="card row compact"><div class="grow small"><span class="status-dot ${nLive || all.length ? 'live' : ''}"></span>${v === 'all' ? `${all.length} match${all.length === 1 ? '' : 'es'} in play worldwide` : `${tracked.length} tracked · ${nLive} in play`}${state.lastLive ? ' · updated ' + new Date(state.lastLive).toTimeString().slice(0, 5) : ''}</div><button class="btn" id="live-refresh">Refresh</button></div>`);
    parts.push(`<div class="card compact">${segmented([['tracked', `${icon('target')} Tracked (${tracked.length})`], ['all', `${icon('live')} All in play (${all.length})`]], v, 'lv')}</div>`);
    if (v === 'all') {
      if (state.liveAll == null) parts.push(PR.skeleton(6));
      else if (!all.length) parts.push(`<div class="card empty">No match is in play right now.</div>`);
      else {
        const groups = {}; all.forEach((e) => { const k = `${e.country} · ${e.league}`; (groups[k] = groups[k] || []).push(e); });
        const keys = Object.keys(groups).sort((a, b) => (groups[b].some((e) => e.fixture) ? 1 : 0) - (groups[a].some((e) => e.fixture) ? 1 : 0) || a.localeCompare(b));
        parts.push('<div class="card compact">');
        keys.forEach((k) => {
          const g = groups[k]; parts.push(`<div class="comp-head">${flag(g[0].country)} ${esc(k)}</div>`);
          g.forEach((e) => { const m = { id: e.fixture || 'live:' + e.eid, home: e.home, away: e.away, badges: { home: e.img[0], away: e.img[1] }, country: e.country, competition: e.league, kickoff: '' };
            const f = e.fixture ? fx(e.fixture) : null; const sub = f ? `<span class="chip brand">analysed</span>${f.safe ? ` <b>${esc(selLabel(f.safe[0], f.home, f.away))}</b> · ${esc(liveVerdict(f.safe[0], state.live[e.eid]).text)}` : ''}` : '';
            parts.push(matchRow(m, { live: state.live[e.eid], tap: !!f, short: true, sub, right: '' })); });
        });
        parts.push('</div>');
      }
    } else {
      if (!tracked.length) parts.push(`<div class="card empty">Nothing to follow in this window.</div>`);
      const betsByFx = {}; const sf = d.safe || { bets: [] };
      ((sf.today && sf.today.bets) || []).forEach((b) => { (betsByFx[b.fixture] = betsByFx[b.fixture] || []).push({ label: b.label, sel: b.sel, odds: b.odds, kind: 'botd' }); });
      (sf.bets || []).forEach((b) => { (betsByFx[b.fixture] = betsByFx[b.fixture] || []).push({ label: b.label, sel: b.sel, odds: b.odds, kind: 'safe' }); });
      Object.entries(d.picks || {}).forEach(([mk, lst]) => lst.forEach((p) => { (betsByFx[p.fixture] = betsByFx[p.fixture] || []).push({ label: MK[mk], sel: mk, kind: 'pick' }); }));
      const rank = (f) => { const s = live.for(f); return isLive(s) ? 0 : isFT(s) ? 2 : 1; };
      const ordered = tracked.slice().sort((x, y) => rank(x) - rank(y) || x.kickoff.localeCompare(y.kickoff));
      let lastGroup = null; const GROUP_LABEL = ['In play', 'Upcoming', 'Finished'];
      parts.push('<div class="card compact">');
      ordered.forEach((f) => {
        const g = rank(f); if (g !== lastGroup) { parts.push(`<div class="comp-head">${GROUP_LABEL[g]}</div>`); lastGroup = g; }
        const s = live.for(f); const inc = f.livescore_id && state.incidents[f.livescore_id];
        const seen = new Set();
        const chips = (betsByFx[f.id] || []).filter((b) => { const k = b.sel; if (seen.has(k)) return false; seen.add(k); return true; })
          .map((b) => { const vd = liveVerdict(b.sel, s); return `<span class="chip ${vd.cls}">${b.kind === 'botd' ? '⭐ ' : b.kind === 'safe' ? '🔒 ' : ''}${esc(b.label)}${b.odds ? ' @ ' + f2(b.odds) : ''} · ${esc(vd.text)}</span>`; }).join('');
        const goals = inc && g !== 1 ? inc.items.filter((it) => ['goal', 'own goal', 'penalty'].includes(it.type)) : [];
        parts.push(matchRow(f, { live: s, sub: `${flag(f.country)} ${esc(f.competition)}`, right: '' }) + `<div class="mrow-extra"><div class="chips">${chips}</div>${goals.length ? `<div class="tiny muted">${goals.map((it) => `⚽ ${esc(it.player || '')} ${it.min != null ? it.min + "'" : ''}${it.team === 'A' ? ' (away)' : ''}`).join(' · ')}</div>` : ''}</div>`);
      });
      parts.push('</div>');
    }
    parts.push(`<div class="tiny muted" style="padding:0 6px">Scores from a public live feed (unofficial). Auto-refresh every ${settings.liveEvery}s while this tab is open. The settled results in Days are the final word.</div>`);
    view().innerHTML = parts.join('');
    const b = $('#live-refresh'); if (b) b.onclick = (e) => { e.stopPropagation(); toast('Refreshing…'); live.refresh(true); };
    $$('[data-lv]').forEach((x) => { x.onclick = () => { state.liveView = x.dataset.lv; PR.render(); if (x.dataset.lv === 'all' && Date.now() - state.lastLiveAll > 20000) live.refresh(false); }; });
  };
  function incidentLine(it) {
    const ico = { goal: '⚽', 'own goal': '⚽ (og)', penalty: '⚽ (pen)', 'missed penalty': '❌ pen', yellow: '🟨', 'second yellow': '🟨🟥', red: '🟥' }[it.type] || '';
    return `${ico} ${it.min != null ? it.min + "'" : ''} ${esc(it.player || '')}${it.score ? ` <span class="muted">(${it.score[0]}–${it.score[1]})</span>` : ''}`;
  }
  PR.incidentLine = incidentLine;

  // ------------------------------------------------------------------ MATCHES
  const PINNED = ['England', 'Spain', 'Italy', 'Germany', 'France', 'Netherlands', 'Portugal', 'Belgium', 'Turkiye', 'Scotland', 'South Africa', 'UEFA Champions League', 'UEFA Europa League'];
  function matchSub(f, withComp) {
    const b = f.safe || (f.top && f.top[2] >= 1.3 ? f.top : null);
    return `${withComp ? flag(f.country) + ' ' + esc(f.competition) + ' · ' : ''}xG ${f1(f.xg[0])}–${f1(f.xg[1])}${b ? ` · ${f.safe ? '🔒 ' : ''}<b>${esc(selShort(b[0]))}</b> ${pct(b[1])} @ ${f2(b[2])}` : f.priced ? '' : ' · <span class="muted">no price</span>'}${f.data_ok ? '' : ' · <span class="warn">low data</span>'}${f.time_known === false ? ' · <span class="muted">time tbc</span>' : ''}`;
  }
  function matchRight(f, s) { return s && s.hg != null ? '' : `<span class="tiny muted">O2.5 ${pill(f.p.O25, 0.6, 0.5)}</span><span class="tiny muted">BTTS ${pill(f.p.BTTS, 0.6, 0.5)}</span>`; }
  PR.views.matches = function () {
    const d = state.data; const q = (state.search || '').trim().toLowerCase(); const key = state.sort || 'ko'; const filt = state.matchFilter || 'all'; const mode = state.matchesView || 'time';
    let lst = d.fixtures.filter((f) => !q || `${f.home} ${f.away} ${f.competition} ${f.country}`.toLowerCase().includes(q));
    if (filt === 'priced') lst = lst.filter((f) => f.priced);
    else if (filt === 'safe') lst = lst.filter((f) => f.safe);
    else if (filt === 'major') lst = lst.filter((f) => f.major);
    else if (filt === 'ok') lst = lst.filter((f) => f.data_ok);
    else if (filt === 'live') lst = lst.filter((f) => isLive(live.for(f)));
    else if (filt === 'fav') lst = lst.filter((f) => PR.isFav(f.id));
    const best = (f) => (f.top && f.top[2] >= 1.3 ? f.top[1] : 0);
    const parts = [`<div class="card compact"><div class="searchbar"><div class="field">${icon('search')}<input id="fx-search" placeholder="Search team, league or country" value="${esc(state.search || '')}">${q ? `<button class="link" id="fx-clear">${icon('x')}</button>` : ''}</div></div>
      <div style="margin-top:8px">${segmented([['time', `${icon('clock')} By time`], ['comp', `${icon('trend')} By country & competition`]], mode, 'mmode')}</div>
      <div class="chips small-chips" style="margin-top:6px">${[['all', `All ${d.fixtures.length}`], ['live', '🔴 Live'], ['fav', '★ Favourites'], ['major', '🏆 Major'], ['priced', 'Priced'], ['safe', '🔒 Safest bet'], ['ok', 'Enough data']].map(([k, l]) => `<button class="chip tapchip ${filt === k ? 'on' : ''}" data-mf="${k}">${l}</button>`).join('')}
      ${mode === 'time' ? select('fx-sort', [['ko', 'Kick-off'], ['safe', 'Best bet first'], ['O25', 'Over 2.5'], ['O15', 'Over 1.5'], ['BTTS', 'BTTS'], ['H', 'Home win']], key) : ''}</div></div>`];
    if (!lst.length) parts.push(`<div class="card empty">${filt === 'fav' ? 'No favourite matches yet — open a match and tap ☆ in its header.' : `No matches found${q ? ` for “${esc(q)}”` : ''}.`}</div>`);
    else if (mode === 'time') {
      lst = lst.slice().sort((a, b) => key === 'ko' ? a.kickoff.localeCompare(b.kickoff) || a.competition.localeCompare(b.competition) : key === 'safe' ? best(b) - best(a) : key === 'H' ? (b.x12[0] || 0) - (a.x12[0] || 0) : (b.p[key] || 0) - (a.p[key] || 0));
      const max = state.expanded.matches ? lst.length : 250; let lastDay = null, lastHour = null;
      lst.slice(0, max).forEach((f) => {
        const day = f.kickoff.slice(0, 10), hour = f.kickoff.slice(11, 13) + ':00';
        if (key === 'ko' && day !== lastDay) { if (lastDay) parts.push('</div>'); parts.push(`<h2 class="section">${esc(dayName(day))}</h2><div class="card compact">`); lastDay = day; lastHour = null; }
        else if (key !== 'ko' && !lastDay) { parts.push('<div class="card compact">'); lastDay = 'x'; }
        if (key === 'ko' && hour !== lastHour) { parts.push(`<div class="hour-head">${esc(hour)}</div>`); lastHour = hour; }
        const s = live.for(f);
        parts.push(matchRow(f, { live: s, short: true, sub: matchSub(f, true), right: matchRight(f, s) }));
      });
      if (lastDay) parts.push('</div>');
      if (lst.length > max) parts.push(`<button class="btn wide" data-more="matches">Show all ${lst.length}</button>`);
    } else {
      // country -> competition accordions
      const byC = {}; lst.forEach((f) => { (byC[f.country] = byC[f.country] || {}); (byC[f.country][f.competition] = byC[f.country][f.competition] || []).push(f); });
      const countries = Object.keys(byC).sort((a, b) => { const pa = PINNED.indexOf(a), pb = PINNED.indexOf(b); return (pa < 0 ? 99 : pa) - (pb < 0 ? 99 : pb) || a.localeCompare(b); });
      const open = state.openCountries || (state.openCountries = new Set(q ? countries : countries.slice(0, 3)));
      if (q) countries.forEach((c) => open.add(c));
      parts.push(`<div class="row" style="padding:0 6px 4px"><div class="grow tiny muted">${countries.length} countries · ${Object.values(byC).reduce((a, c) => a + Object.keys(c).length, 0)} competitions</div><button class="link" id="acc-all">${open.size >= countries.length ? 'Collapse all' : 'Expand all'}</button></div>`);
      parts.push('<div class="card compact">');
      countries.forEach((c) => {
        const comps = byC[c]; const n = Object.values(comps).reduce((a, l) => a + l.length, 0); const nl = Object.values(comps).reduce((a, l) => a + l.filter((f) => isLive(live.for(f))).length, 0); const isOpen = open.has(c);
        parts.push(`<div class="acc-head ${isOpen ? 'open' : ''}" data-acc="${esc(c)}"><span>${flag(c)}</span><span>${esc(c)}</span>${nl ? `<span class="status-dot live"></span>` : ''}<span class="cnt">${Object.keys(comps).length} · ${n} match${n === 1 ? '' : 'es'}</span><span class="chev">${icon('next')}</span></div>`);
        if (!isOpen) return;
        Object.keys(comps).sort().forEach((comp) => {
          parts.push(`<div class="comp-head">${esc(comp.replace(c + ' · ', ''))}</div>`);
          comps[comp].sort((a, b) => a.kickoff.localeCompare(b.kickoff)).forEach((f) => { const s = live.for(f); parts.push(matchRow(f, { live: s, short: false, sub: matchSub(f, false), right: matchRight(f, s) })); });
        });
      });
      parts.push('</div>');
    }
    view().innerHTML = parts.join('');
    const inp = $('#fx-search');
    inp.oninput = (e) => { state.search = e.target.value; PR.render(); const i = $('#fx-search'); i.focus(); i.setSelectionRange(i.value.length, i.value.length); };
    if (state.focusSearch) { state.focusSearch = false; inp.focus(); }
    const cl = $('#fx-clear'); if (cl) cl.onclick = () => { state.search = ''; PR.render(); };
    const so = $('#fx-sort'); if (so) so.onchange = (e) => { state.sort = e.target.value; PR.render(); };
    $$('[data-mf]').forEach((b) => { b.onclick = () => { state.matchFilter = b.dataset.mf; PR.render(); }; });
    $$('[data-mmode]').forEach((b) => { b.onclick = () => { state.matchesView = b.dataset.mmode; PR.render(); }; });
    $$('[data-more]').forEach((b) => { b.onclick = () => { state.expanded[b.dataset.more] = true; PR.render(); }; });
    $$('[data-acc]').forEach((b) => { b.onclick = () => { const o = state.openCountries; if (o.has(b.dataset.acc)) o.delete(b.dataset.acc); else o.add(b.dataset.acc); PR.render(); }; });
    const all = $('#acc-all'); if (all) all.onclick = () => { const cs = Object.keys(d.fixtures.reduce((a, f) => { a[f.country] = 1; return a; }, {})); if (state.openCountries.size >= cs.length) state.openCountries = new Set(); else state.openCountries = new Set(cs); PR.render(); };
  };

  // ------------------------------------------------------------------ DAYS
  PR.views.days = function () {
    const d = state.data; const days = (d.history && d.history.days) || []; const parts = [];
    parts.push(`<div class="card small"><b>Day by day</b> — every analysed match of each day with the final score, and how the bets of the day, safest bets and shortlists did. Results fill in within a few hours of the final whistle; 60 days are kept.</div>`);
    if (!days.length) parts.push(`<div class="card empty">History starts with the next analysis.</div>`);
    const rate = (o, hitKey) => { if (!o || !o.n) return '–'; const settled = o.n - (o.pending || 0); return settled ? `${o[hitKey]}/${settled}${o.pending ? ' · ' + o.pending + ' open' : ''}` : `${o.n} open`; };
    parts.push(`<div class="card compact">${days.map((x) => `<div class="list-item tap day" data-day="${esc(x.date)}"><div class="main"><div class="match">${esc(dayName(x.date))}</div>
      <div class="meta">${x.n} matches${x.finished ? ` · ${x.finished} finished` : ''}${x.goals_avg != null ? ` · ${f1(x.goals_avg)} goals/match · O2.5 ${pct(x.o25_rate)} · BTTS ${pct(x.btts_rate)}` : ''}</div>
      <div class="chips">${x.botd && x.botd.n ? `<span class="chip ${chipCls(x.botd, 'hit')}">⭐ day card ${rate(x.botd, 'hit')}</span>` : ''}${x.safes && x.safes.n ? `<span class="chip ${chipCls(x.safes, 'hit')}">${icon('lock')} safest ${rate(x.safes, 'hit')}</span>` : ''}${x.picks && x.picks.n ? `<span class="chip ${chipCls(x.picks, 'hit')}">${icon('star')} shortlist ${rate(x.picks, 'hit')}</span>` : ''}</div></div><div class="chev">${icon('next')}</div></div>`).join('')}</div>`);
    view().innerHTML = parts.join('');
    $$('[data-day]').forEach((b) => { b.onclick = () => { state.dayView = 'results'; PR.push({ type: 'day', date: b.dataset.day }); }; });
  };
  function chipCls(o, k) { const settled = o.n - (o.pending || 0); if (!settled) return ''; const r = o[k] / settled; return r >= 0.6 ? 'good' : r <= 0.35 ? 'bad' : 'warn'; }
  PR.chipCls = chipCls;
})(window.PR);
