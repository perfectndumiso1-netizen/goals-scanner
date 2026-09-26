/* Goals Scanner — app UI. Data: data/app/latest.json in the GitHub repo (the backend).
   Live scores: Livescore.com public JSON, fetched on the phone through the native bridge. */
(function () {
  'use strict';

  // ------------------------------------------------------------------ settings / state
  const native = window.Android || null;
  const DEFAULT_REPO = (native && native.repo && native.repo()) || 'perfectndumiso1-netizen/goals-scanner';
  const settings = Object.assign({ repo: DEFAULT_REPO, branch: 'main', liveEvery: 60, tzOffset: 2 },
    JSON.parse(localStorage.getItem('gs_settings') || '{}'));
  const state = { data: null, tab: 'today', detail: null, live: {}, incidents: {}, liveTimer: null, lastLive: 0,
    report: null, reportMd: '', search: '', sort: 'O25', loading: false };

  const $ = (sel) => document.querySelector(sel);
  const view = $('#view');

  function saveSettings() { localStorage.setItem('gs_settings', JSON.stringify(settings)); }
  function rawUrl(path) { return `https://raw.githubusercontent.com/${settings.repo}/${settings.branch}/${path}`; }
  function ghUrl(path) { return `https://github.com/${settings.repo}/blob/${settings.branch}/${path}`; }

  // ------------------------------------------------------------------ fetch bridge
  let fid = 0; const pending = {};
  window.__fetchDone = function (id, code, body) { const cb = pending[id]; delete pending[id]; if (cb) cb({ code, body }); };
  function nfetch(url, ua) {
    if (native && native.fetch) {
      return new Promise((resolve) => { const id = ++fid; pending[id] = resolve; native.fetch(id, url, ua || null); });
    }
    return fetch(url).then(async (r) => ({ code: r.status, body: await r.text() }))
      .catch((e) => ({ code: 0, body: String(e) }));
  }
  async function getJson(url, ua) {
    const r = await nfetch(url, ua);
    if (r.code !== 200) throw new Error(`HTTP ${r.code}`);
    return JSON.parse(r.body);
  }

  // ------------------------------------------------------------------ helpers
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const pct = (x) => (x == null || isNaN(x)) ? '–' : Math.round(x * 100) + '%';
  const f2 = (x) => (x == null || isNaN(x)) ? '–' : Number(x).toFixed(2);
  const signed = (x) => (x == null || isNaN(x)) ? '–' : (x >= 0 ? '+' : '') + (x * 100).toFixed(1) + '%';
  const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  function parseLocal(s) { // "YYYY-MM-DD HH:MM" in report timezone -> Date (treated as device local for display only)
    if (!s) return null; const m = s.match(/(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})/); if (!m) return null;
    return new Date(+m[1], +m[2] - 1, +m[3], +m[4], +m[5]);
  }
  function koText(s) { const d = parseLocal(s); if (!d) return s || ''; return `${DAYS[d.getDay()]} ${s.slice(8, 10)}/${s.slice(5, 7)}<br>${s.slice(11, 16)}`; }
  function koShort(s) { const d = parseLocal(s); if (!d) return s || ''; return `${DAYS[d.getDay()]} ${s.slice(11, 16)}`; }
  function tzNow() { // current time in the report timezone
    const n = new Date(); return new Date(n.getTime() + (settings.tzOffset * 60 + n.getTimezoneOffset()) * 60000);
  }
  function pill(p, hi, mid) { const cls = p >= hi ? 'hi' : p >= mid ? 'mid' : ''; return `<span class="pill ${cls}">${pct(p)}</span>`; }
  function toast(msg) { const t = $('#toast'); t.textContent = msg; t.classList.add('show'); clearTimeout(t._h); t._h = setTimeout(() => t.classList.remove('show'), 2200); }
  function md(text) {
    let html;
    try { html = marked.parse(text || '', { gfm: true, breaks: false }); } catch (e) { return `<pre>${esc(text)}</pre>`; }
    // wide tables: keep cells on one line and scroll sideways instead of breaking words
    const box = document.createElement('div'); box.innerHTML = html;
    box.querySelectorAll('table').forEach((t) => { const n = t.querySelector('tr') ? t.querySelector('tr').children.length : 0; if (n > 4) t.classList.add('wide'); });
    return box.innerHTML;
  }
  const MK = { O15: 'Over 1.5 goals', O25: 'Over 2.5 goals', BTTS: 'Both teams to score' };
  const SEL = { H: 'Home win', D: 'Draw', A: 'Away win', '1X': 'Home or draw (1X)', '12': 'Home or away (12)', X2: 'Draw or away (X2)', O25: 'Over 2.5 goals', U25: 'Under 2.5 goals' };
  function fx(id) { return state.data && state.data._byId[id]; }

  // ------------------------------------------------------------------ data loading
  function indexData(d) {
    d._byId = {}; (d.fixtures || []).forEach((f) => { d._byId[f.id] = f; });
    return d;
  }
  async function loadData(force) {
    if (state.loading) return; state.loading = true; $('#btn-refresh').classList.add('spin');
    try {
      const url = rawUrl('data/app/latest.json') + '?t=' + Date.now();
      const d = indexData(await getJson(url));
      state.data = d; localStorage.setItem('gs_latest', JSON.stringify(d));
      statusLine(); render();
      if (force) toast('Updated');
    } catch (e) {
      if (!state.data) { const c = localStorage.getItem('gs_latest'); if (c) { state.data = indexData(JSON.parse(c)); statusLine(); render(); } }
      toast('Could not reach GitHub (' + e.message + ')' + (state.data ? ' — showing cached data' : ''));
      if (!state.data) view.innerHTML = `<div class="empty">No data yet.<br>Check your connection and pull to refresh.</div>`;
    } finally {
      state.loading = false; $('#btn-refresh').classList.remove('spin'); if (native && native.refreshDone) native.refreshDone();
    }
  }
  function statusLine() {
    const m = state.data && state.data.meta; if (!m) return;
    const run = String(m.run || '').startsWith('manual') ? 'manual run ' + m.run.slice(7) : 'run ' + m.run;
    $('#status-line').textContent = `${m.generated} ${m.tz} · ${run} · ${m.fixtures} fixtures`;
  }

  // ------------------------------------------------------------------ rendering: today
  function legRows(legs, live) {
    return legs.map((l) => {
      const f = fx(l.fixture); const v = live ? legVerdict(l, liveFor(f)) : null;
      const flag = (l.edge != null && l.edge > 0.08) ? ' <span class="chip warn">price moved — check news</span>' : '';
      return `<tr><td class="muted tiny" style="width:52px">${koShort(l.kickoff)}</td>
        <td><div><b>${esc(l.home)} v ${esc(l.away)}</b></div><div class="tiny muted">${esc(l.competition || '')}</div>
            <div class="sel">${esc(l.label || SEL[l.sel] || l.sel)} <span class="muted tiny">· fair ${f2(l.fair)} · ${pct(l.p)} · edge ${signed(l.edge)}</span>${flag}</div>
            ${v ? `<div class="verdict ${v.cls}">${v.text}</div>` : ''}</td>
        <td class="price">${f2(l.odds)}</td></tr>`;
    }).join('');
  }
  function parlayCard(p, i, live) {
    const st = live ? parlayVerdict(p) : null;
    return `<div class="card">
      <div class="row"><div class="grow"><b>Parlay ${i + 1}</b> — ${p.legs.length} legs @ <b>${f2(p.odds)}</b>
        <span class="muted small">· win ${pct(p.p)} · exp. return ${signed(p.ev)}</span></div>
        ${st ? `<span class="chip ${st.cls}">${st.text}</span>` : `<span class="chip">${esc(p.id)}</span>`}</div>
      <table class="legs">${legRows(p.legs, live)}</table>
      <div class="tiny muted" style="margin-top:6px">Prices: ${esc(p.source)}${p.extended ? ' · whole 24 h window (few priced matches before the next run)' : ''}</div>
    </div>`;
  }
  function renderToday() {
    const d = state.data, m = d.meta; const parts = [];
    parts.push(`<div class="card"><div class="small">Scan window <b>${esc(m.window_start.slice(5))}</b> → <b>${esc(m.window_end.slice(5))}</b> ${esc(m.tz)} · parlays for kick-offs before <b>${esc(m.parlay_window_end.slice(5))}</b></div>
      ${(m.notes || []).map((n) => `<div class="tiny muted">• ${esc(n)}</div>`).join('')}
      <div style="margin-top:8px"><a class="btn" href="${ghUrl(m.report_md)}">Full report</a><a class="btn" href="${ghUrl(m.dossier_md)}">Parlay dossier</a><a class="btn" href="https://github.com/${settings.repo}/releases/latest">App updates</a></div></div>`);
    parts.push(`<h2 style="margin:12px 4px 6px;font-size:18px">🎟️ Parlays <span class="muted small">odds ${m.parlay_band && m.parlay_band.length ? m.parlay_band.map(f2).join('–') : '2.70–3.50'}</span></h2>`);
    if (!d.parlays.length) parts.push(`<div class="card empty">No parlay possible in this window.</div>`);
    d.parlays.forEach((p, i) => parts.push(parlayCard(p, i, false)));
    parts.push(`<div class="note">⚠️ Honest expectation: a parlay at ~3.1 must win about 1 in 3 to break even. In the 2023–26 backtest this construction won 30–33% and returned −4% to −13% per unit. Treat parlays as entertainment with a known cost.</div>`);
    for (const mk of ['O15', 'O25', 'BTTS']) {
      const lst = d.picks[mk] || [];
      parts.push(`<div class="card"><h2>${MK[mk]} <span class="muted small">— ${lst.length} pick(s) · threshold ${pct(m.thresholds[mk])}</span></h2>`);
      if (!lst.length) parts.push(`<div class="muted small">None met the criteria.</div>`);
      lst.forEach((p) => { const f = fx(p.fixture); if (!f) return;
        parts.push(`<div class="list-item tap" data-fx="${esc(f.id)}"><div class="ko">${koText(f.kickoff)}</div>
          <div class="main"><div class="match">${esc(f.home)} v ${esc(f.away)}</div><div class="meta">${esc(f.competition)} · ${f.basis === 'market+model' ? '📈 market+model' : '🧮 model only'}${p.sportybet ? ' · Sportybet ' + f2(p.sportybet) : ''}</div></div>
          <div class="nums">${pill(p.p, 0.7, 0.6)}<div class="stars">${esc(p.stars)}</div></div></div>`);
      });
      parts.push(`<div class="tiny muted" style="margin-top:6px">Backtest: ${esc(m.backtest[mk] || '')}</div></div>`);
    }
    const t = d.tracker || {};
    parts.push(`<div class="card"><h2>Shortlist tracker</h2>${['O15', 'O25', 'BTTS'].map((mk) => { const s = t[mk] || {};
      return `<div class="row small" style="padding:4px 0;border-top:1px solid var(--line)"><div class="grow">${MK[mk]}</div><div>${s.settled || 0} settled · hit ${pct(s.rate)} · 30d ${pct(s.recent_rate)} · ${s.pending || 0} pending${s.roi != null ? ' · return ' + signed(s.roi) : ''}</div></div>`; }).join('')}</div>`);
    view.innerHTML = parts.join('');
  }

  // ------------------------------------------------------------------ live
  function liveFor(f) { return f && f.livescore_id ? state.live[f.livescore_id] : null; }
  function isLive(s) { return s && s.status && s.status !== 'NS' && !['FT', 'AET', 'AP', 'Postp.', 'Canc.', 'Aband.'].includes(s.status); }
  function isFT(s) { return s && ['FT', 'AET', 'AP'].includes(s.status); }
  function legVerdict(l, s) {
    if (!s || s.status === 'NS' || s.hg == null) return { cls: '', text: 'not started' };
    const h = s.hg, a = s.ag, tot = h + a, ft = isFT(s);
    const win = { H: h > a, D: h === a, A: a > h, '1X': h >= a, '12': h !== a, X2: a >= h, O25: tot >= 3, U25: tot <= 2 }[l.sel];
    if (ft) return win ? { cls: 'good', text: '✅ won' } : { cls: 'bad', text: '❌ lost' };
    if (l.sel === 'O25') return tot >= 3 ? { cls: 'good', text: '✅ landed' } : { cls: 'warn', text: `needs ${3 - tot} more goal${3 - tot > 1 ? 's' : ''}` };
    if (l.sel === 'U25') return tot <= 2 ? { cls: 'warn', text: `on track (${tot} goals so far)` } : { cls: 'bad', text: '❌ lost' };
    return win ? { cls: 'good', text: 'winning now' } : { cls: 'bad', text: 'losing now' };
  }
  function parlayVerdict(p) {
    let lost = false, allFt = true, started = false;
    p.legs.forEach((l) => { const s = liveFor(fx(l.fixture)); if (!s || s.status === 'NS' || s.hg == null) { allFt = false; return; }
      started = true; if (!isFT(s)) allFt = false; const v = legVerdict(l, s); if (v.text === '❌ lost') lost = true; });
    if (lost) return { cls: 'bad', text: 'LOST' }; if (allFt && started) return { cls: 'good', text: 'WON' };
    return started ? { cls: 'warn', text: 'in play' } : { cls: '', text: 'pending' };
  }
  function pickVerdict(mk, s) {
    if (!s || s.status === 'NS' || s.hg == null) return '';
    const tot = s.hg + s.ag, ft = isFT(s);
    const ok = mk === 'O15' ? tot >= 2 : mk === 'O25' ? tot >= 3 : (s.hg > 0 && s.ag > 0);
    if (ok) return `<span class="chip good">${MK[mk].replace(' goals', '').replace('Both teams to score', 'BTTS')} ✅</span>`;
    return ft ? `<span class="chip bad">${MK[mk].replace(' goals', '').replace('Both teams to score', 'BTTS')} ❌</span>` : `<span class="chip">${MK[mk].replace(' goals', '').replace('Both teams to score', 'BTTS')} ⏳</span>`;
  }
  function trackedFixtures() {
    const d = state.data; const ids = new Set(d.tracked || []);
    return (d.fixtures || []).filter((f) => ids.has(f.id)).sort((a, b) => a.kickoff.localeCompare(b.kickoff));
  }
  async function refreshLive(manual) {
    const d = state.data; if (!d) return;
    const tracked = trackedFixtures().filter((f) => f.livescore_id);
    if (!tracked.length) return;
    const now = tzNow(); const days = new Set();
    tracked.forEach((f) => { days.add(f.kickoff.slice(0, 10)); });
    const todayStr = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
    days.add(todayStr);
    const want = new Set(tracked.map((f) => f.livescore_id));
    let got = 0;
    for (const day of days) {
      try {
        const j = await getJson(`https://prod-public-api.livescore.com/v1/api/app/date/soccer/${day.replace(/-/g, '')}/${settings.tzOffset}?MD=1`);
        (j.Stages || []).forEach((st) => (st.Events || []).forEach((e) => {
          const eid = String(e.Eid); if (!want.has(eid)) return; got++;
          state.live[eid] = { status: e.Eps || '', hg: e.Tr1 != null ? +e.Tr1 : null, ag: e.Tr2 != null ? +e.Tr2 : null, ht: [e.Trh1, e.Trh2], t: Date.now() };
        }));
      } catch (e) { if (manual) toast('Livescore unavailable (' + e.message + ')'); }
    }
    state.lastLive = Date.now();
    // scorers for matches with goals (cache by eid+score)
    for (const f of tracked) {
      const s = state.live[f.livescore_id]; if (!s || s.hg == null || (s.hg + s.ag) === 0) continue;
      const key = `${s.hg}-${s.ag}`; const c = state.incidents[f.livescore_id];
      if (c && c.key === key) continue;
      try {
        const j = await getJson(`https://prod-public-api.livescore.com/v1/api/app/incidents/soccer/${f.livescore_id}`);
        const items = [];
        Object.values(j.Incs || {}).forEach((lst) => lst.forEach((x) => { [x].concat(x.Incs || []).forEach((y) => {
          const t = { 36: 'goal', 37: 'own goal', 39: 'penalty', 40: 'missed penalty', 43: 'yellow', 44: 'second yellow', 45: 'red' }[y.IT];
          if (!t) return; items.push({ min: y.Min, team: y.Nm === 1 ? 'H' : 'A', type: t, player: y.Pn || [y.Fn, y.Ln].filter(Boolean).join(' '), score: y.Sc });
        }); }));
        items.sort((a, b) => (a.min || 0) - (b.min || 0));
        state.incidents[f.livescore_id] = { key, items };
      } catch (e) { /* ignore */ }
    }
    if (state.tab === 'live' && !state.detail) renderLive();
    return got;
  }
  function scheduleLive() {
    clearInterval(state.liveTimer);
    state.liveTimer = setInterval(() => {
      if (state.tab !== 'live' || document.hidden) return;
      const tracked = trackedFixtures(); const now = tzNow();
      const active = tracked.some((f) => { const s = liveFor(f); const ko = parseLocal(f.kickoff);
        return isLive(s) || (ko && !isFT(s) && Math.abs(now - ko) < 3 * 3600 * 1000); });
      if (active) refreshLive(false);
    }, Math.max(20, settings.liveEvery) * 1000);
  }
  function incidentLine(it) {
    const ico = { goal: '⚽', 'own goal': '⚽ (og)', penalty: '⚽ (pen)', 'missed penalty': '❌ pen', yellow: '🟨', 'second yellow': '🟨🟥', red: '🟥' }[it.type] || '';
    return `${ico} ${it.min != null ? it.min + "'" : ''} ${esc(it.player || '')}${it.score ? ` <span class="muted">(${it.score[0]}–${it.score[1]})</span>` : ''}`;
  }
  function renderLive() {
    const d = state.data; const tracked = trackedFixtures(); const parts = [];
    const nLive = tracked.filter((f) => isLive(liveFor(f))).length;
    parts.push(`<div class="card row"><div class="grow small"><span class="status-dot ${nLive ? 'live' : ''}"></span>${tracked.length} tracked match(es) · ${nLive} in play${state.lastLive ? ' · updated ' + new Date(state.lastLive).toTimeString().slice(0, 5) : ''}</div><button class="btn" id="live-refresh">Refresh</button></div>`);
    if (d.parlays.length) { parts.push(`<h2 style="margin:8px 4px 6px;font-size:17px">Parlays</h2>`); d.parlays.forEach((p, i) => parts.push(parlayCard(p, i, true))); }
    // pending parlays from earlier runs still in play
    const pend = (d.ledger || []).filter((p) => p.status === 'pending' && !d.parlays.some((q) => q.id === p.id));
    if (pend.length) { parts.push(`<h2 style="margin:8px 4px 6px;font-size:17px">Earlier parlays still open</h2>`); pend.forEach((p, i) => parts.push(parlayCard(p, i, true))); }
    parts.push(`<h2 style="margin:8px 4px 6px;font-size:17px">Tracked matches</h2>`);
    if (!tracked.length) parts.push(`<div class="card empty">Nothing to follow in this window.</div>`);
    const legsByFx = {};
    d.parlays.concat(pend).forEach((p) => p.legs.forEach((l) => { (legsByFx[l.fixture] = legsByFx[l.fixture] || []).push(l); }));
    const picksByFx = {};
    Object.entries(d.picks || {}).forEach(([mk, lst]) => lst.forEach((p) => { (picksByFx[p.fixture] = picksByFx[p.fixture] || []).push(mk); }));
    tracked.forEach((f) => {
      const s = liveFor(f); const inc = f.livescore_id && state.incidents[f.livescore_id];
      const score = s && s.hg != null ? `${s.hg} – ${s.ag}` : 'v';
      const minute = s ? (isFT(s) ? `<span class="minute ft">${esc(s.status)}</span>` : isLive(s) ? `<span class="minute">${esc(s.status)}</span>` : `<span class="minute ft">${koShort(f.kickoff)}</span>`) : `<span class="minute ft">${f.livescore_id ? koShort(f.kickoff) : 'no live feed'}</span>`;
      parts.push(`<div class="card" data-fx="${esc(f.id)}">
        <div class="row"><div class="grow"><div class="tiny muted">${esc(f.competition)}</div><div><b>${esc(f.home_long || f.home)}</b><br><b>${esc(f.away_long || f.away)}</b></div></div>
        <div class="right"><div class="score">${score}</div>${minute}</div></div>
        <div style="margin-top:6px">${(legsByFx[f.id] || []).map((l) => { const v = legVerdict(l, s); return `<span class="chip ${v.cls}">${esc(l.label || SEL[l.sel])} @ ${f2(l.odds)} · ${esc(v.text)}</span>`; }).join('')}
          ${(picksByFx[f.id] || []).map((mk) => pickVerdict(mk, s) || `<span class="chip">${esc(MK[mk])} pick</span>`).join('')}</div>
        ${inc && inc.items.length ? `<div class="small" style="margin-top:6px">${inc.items.map((it) => `<div>${it.team === 'H' ? '' : '<span class="muted">(away) </span>'}${incidentLine(it)}</div>`).join('')}</div>` : ''}
        <div class="tiny muted" style="margin-top:6px">Model: O2.5 ${pct(f.p.O25)} · BTTS ${pct(f.p.BTTS)} · 1X2 ${pct(f.x12.H)} / ${pct(f.x12.D)} / ${pct(f.x12.A)} · <a href="#" data-open="${esc(f.id)}">data sheet</a></div>
      </div>`);
    });
    parts.push(`<div class="tiny muted" style="padding:0 6px">Scores from Livescore.com (public feed, unofficial). Auto-refresh every ${settings.liveEvery}s while a tracked match is in play. Unofficial feeds can lag or change — the final word is always the settled ledger.</div>`);
    view.innerHTML = parts.join('');
    const b = $('#live-refresh'); if (b) b.onclick = () => { toast('Refreshing…'); refreshLive(true); };
  }

  // ------------------------------------------------------------------ fixtures + detail
  function renderFixtures() {
    const d = state.data; const q = state.search.toLowerCase();
    let lst = d.fixtures.filter((f) => !q || `${f.home} ${f.away} ${f.competition} ${f.country}`.toLowerCase().includes(q));
    const key = state.sort;
    lst = lst.slice().sort((a, b) => key === 'ko' ? a.kickoff.localeCompare(b.kickoff) : key === 'H' ? (b.x12.H || 0) - (a.x12.H || 0) : (b.p[key] || 0) - (a.p[key] || 0));
    const parts = [`<div class="searchbar"><input id="fx-search" placeholder="Search team / league" value="${esc(state.search)}">
      <select id="fx-sort"><option value="O25" ${key === 'O25' ? 'selected' : ''}>Over 2.5</option><option value="O15" ${key === 'O15' ? 'selected' : ''}>Over 1.5</option><option value="BTTS" ${key === 'BTTS' ? 'selected' : ''}>BTTS</option><option value="H" ${key === 'H' ? 'selected' : ''}>Home win</option><option value="ko" ${key === 'ko' ? 'selected' : ''}>Kick-off</option></select></div>`];
    parts.push(`<div class="card">`);
    lst.forEach((f) => parts.push(`<div class="list-item tap" data-fx="${esc(f.id)}"><div class="ko">${koText(f.kickoff)}</div>
      <div class="main"><div class="match">${esc(f.home)} v ${esc(f.away)}${f.data_ok ? '' : ' <span class="chip warn">low data</span>'}</div>
        <div class="meta">${esc(f.competition)} · xG ${f2(f.xg.home)}–${f2(f.xg.away)} · 1X2 ${pct(f.x12.H)}/${pct(f.x12.D)}/${pct(f.x12.A)}${f.sportybet && f.sportybet['1X2'] ? ' · SB ' + f.sportybet['1X2'].map(f2).join('/') : ''}</div></div>
      <div class="nums"><div>O1.5 ${pill(f.p.O15, 0.84, 0.75)}</div><div>O2.5 ${pill(f.p.O25, 0.6, 0.5)}</div><div>BTTS ${pill(f.p.BTTS, 0.6, 0.5)}</div></div></div>`));
    if (!lst.length) parts.push(`<div class="empty">No fixtures match.</div>`);
    parts.push(`</div>`);
    view.innerHTML = parts.join('');
    $('#fx-search').oninput = (e) => { state.search = e.target.value; renderFixtures(); const i = $('#fx-search'); i.focus(); i.setSelectionRange(i.value.length, i.value.length); };
    $('#fx-sort').onchange = (e) => { state.sort = e.target.value; renderFixtures(); };
  }
  function lineRows(obj, label) {
    if (!obj) return '';
    return `<div class="small" style="margin-top:4px"><b>${label}:</b> ${Object.entries(obj).map(([k, v]) => Array.isArray(v) ? `O${k} ${f2(v[0])} / U ${f2(v[1])}` : `${k} ${f2(v)}`).join(' · ')}</div>`;
  }
  function renderDetail(id) {
    const f = fx(id); if (!f) { state.detail = null; render(); return; }
    const s = liveFor(f); const d = state.data;
    const sb = f.sportybet || {};
    const parts = [`<div class="detail-head"><button class="back" id="back">‹ Back</button><div class="grow"><div class="tiny muted">${esc(f.competition)} · ${esc(f.kickoff)} ${esc(d.meta.tz)}</div></div></div>`];
    parts.push(`<div class="card"><div class="row"><div class="grow"><h2 style="margin:0">${esc(f.home_long || f.home)}<br>${esc(f.away_long || f.away)}</h2></div>
      ${s && s.hg != null ? `<div class="right"><div class="score">${s.hg} – ${s.ag}</div>${isFT(s) ? `<span class="minute ft">${esc(s.status)}</span>` : `<span class="minute">${esc(s.status)}</span>`}</div>` : ''}</div>
      <div class="grid"><div class="cell"><div class="k">Exp. goals</div><div class="v">${f2(f.xg.home)} – ${f2(f.xg.away)}</div></div>
        <div class="cell"><div class="k">Over 1.5</div><div class="v">${pct(f.p.O15)}</div></div><div class="cell"><div class="k">Over 2.5</div><div class="v">${pct(f.p.O25)}</div></div>
        <div class="cell"><div class="k">BTTS</div><div class="v">${pct(f.p.BTTS)}</div></div><div class="cell"><div class="k">1X2</div><div class="v small">${pct(f.x12.H)} / ${pct(f.x12.D)} / ${pct(f.x12.A)}</div></div>
        <div class="cell"><div class="k">Double chance</div><div class="v small">1X ${pct(f.x12['1X'])} · X2 ${pct(f.x12.X2)}</div></div>
        ${f.corners ? `<div class="cell"><div class="k">Corners exp.</div><div class="v">${f2(f.corners.total)}</div><div class="tiny muted">O9.5 ${pct(f.corners.p.total && f.corners.p.total['9.5'])}</div></div>` : ''}
        ${f.cards ? `<div class="cell"><div class="k">Cards exp.</div><div class="v">${f2(f.cards.total)}</div><div class="tiny muted">O4.5 ${pct(f.cards.p.total && f.cards.p.total['4.5'])}</div></div>` : ''}</div>
      <div class="tiny muted">${f.basis === 'market+model' ? '📈 90% market / 10% model' : '🧮 model only (no odds in feed)'}${f.data_ok ? '' : ' · ⚠️ low data — never shortlisted'}${f.referee ? ' · referee ' + esc(f.referee) : ''}</div>
      ${Object.keys(sb).length ? `<h3>Sportybet</h3>${sb['1X2'] ? `<div class="small">1X2 <b>${sb['1X2'].map(f2).join(' / ')}</b>${sb.DC ? ' · DC ' + Object.entries(sb.DC).map(([k, v]) => k + ' ' + f2(v)).join(' · ') : ''}${sb.BTTS ? ' · BTTS ' + sb.BTTS.map(f2).join(' / ') : ''}</div>` : ''}
        ${lineRows(sb.OU, 'Goals')}${lineRows(sb.TGH, 'Home goals')}${lineRows(sb.TGA, 'Away goals')}${lineRows(sb.CORN, 'Corners')}${lineRows(sb.CORN1H, '1st-half corners (market only)')}${lineRows(sb.CORNH, 'Home corners')}${lineRows(sb.CORNA, 'Away corners')}${lineRows(sb.CARDS, 'Cards')}` : '<div class="tiny muted" style="margin-top:6px">No Sportybet price for this match.</div>'}
      ${f.odds && f.odds.over25 ? `<div class="tiny muted" style="margin-top:4px">Feed reference: 1X2 ${f2(f.odds.home)} / ${f2(f.odds.draw)} / ${f2(f.odds.away)} · O/U 2.5 ${f2(f.odds.over25)} / ${f2(f.odds.under25)}</div>` : ''}
    </div>`);
    parts.push(`<div class="card md">${md(f.sheet_md)}</div>`);
    const hl = [f.home_long, f.away_long, f.home, f.away].map((t) => d.headlines && d.headlines[t]).filter(Boolean);
    if (hl.length) {
      parts.push(`<div class="card"><h2>Recent headlines <span class="muted small">(context only, not used by the model)</span></h2>${hl.map((items, i) => items.map((h) => `<div class="list-item"><div class="main"><a href="${esc(h.link)}">${esc(h.title)}</a><div class="meta">${esc(h.when || '')} · ${esc(h.source || '')}</div></div></div>`).join('')).join('')}</div>`);
    }
    view.innerHTML = parts.join('');
    $('#back').onclick = () => { state.detail = null; render(); };
    window.scrollTo(0, 0);
  }

  // ------------------------------------------------------------------ reports
  async function openReport(name) {
    state.report = name; state.reportMd = ''; renderReports();
    try { const r = await nfetch(rawUrl(`reports/${name}.md`) + '?t=' + Math.floor(Date.now() / 60000)); if (r.code !== 200) throw new Error('HTTP ' + r.code); state.reportMd = r.body; }
    catch (e) { state.reportMd = `_Could not load report (${e.message})._`; }
    if (state.tab === 'reports') renderReports();
  }
  function renderReports() {
    const d = state.data; const parts = [];
    if (state.report) {
      parts.push(`<div class="detail-head"><button class="back" id="back">‹ Back</button><div class="grow"><b>${esc(state.report)}</b></div><a class="btn" href="${ghUrl('reports/' + state.report + '.md')}">GitHub</a></div>`);
      parts.push(`<div class="card md">${state.reportMd ? md(state.reportMd) : '<div class="empty">Loading…</div>'}</div>`);
      view.innerHTML = parts.join(''); $('#back').onclick = () => { state.report = null; renderReports(); window.scrollTo(0, 0); };
      return;
    }
    parts.push(`<div class="card"><h2>Reports</h2><div class="small muted">Full Markdown reports and parlay dossiers, as committed to GitHub by each run (the latest run of a day overwrites that day's file).</div></div>`);
    parts.push(`<div class="card">`);
    (d.history.reports || []).forEach((r) => parts.push(`<div class="list-item"><div class="main"><div class="match">${esc(r)}</div></div><div><button class="btn" data-report="${esc(r)}">Report</button><button class="btn" data-report="${esc(r)}-parlays">Dossier</button></div></div>`));
    parts.push(`</div>`);
    view.innerHTML = parts.join('');
    view.querySelectorAll('[data-report]').forEach((b) => { b.onclick = () => openReport(b.dataset.report); });
  }

  // ------------------------------------------------------------------ ledger
  function renderLedger() {
    const d = state.data; const ps = d.parlay_summary || {}; const parts = [];
    const row = (name, s) => s && s.n ? `<tr><td>${name}</td><td>${s.n}</td><td>${s.won}</td><td>${pct(s.rate)}</td><td>${pct(s.exp_rate)}</td><td>${f2(s.avg_odds)}</td><td><b>${signed(s.roi)}</b></td></tr>` : `<tr><td>${name}</td><td>0</td><td>0</td><td>–</td><td>–</td><td>–</td><td>–</td></tr>`;
    parts.push(`<div class="card"><h2>Parlay performance</h2><div class="md"><table class="wide"><tr><th>Scope</th><th>Settled</th><th>Won</th><th>Hit</th><th>Expected</th><th>Avg odds</th><th>Return</th></tr>${row('All time', ps.all)}${row('Last 30 days', ps['30d'])}${Object.entries(ps.by_run || {}).map(([k, v]) => row('Run ' + k, v)).join('')}</table></div>
      <div class="tiny muted">${ps.pending || 0} pending. "Expected" is the model's own predicted win rate for those parlays — if the real hit rate stays below it for weeks, the model is over-confident.</div></div>`);
    parts.push(`<div class="card"><h2>Ledger</h2>`);
    (d.ledger || []).forEach((p) => {
      const icon = { won: '✅', lost: '❌', pending: '⏳', void: '∅' }[p.status] || '';
      parts.push(`<div class="list-item"><div class="main"><div class="match">${icon} ${esc(p.id)} <span class="muted small">· ${esc(p.created)} · run ${esc(p.run)} · ${esc(p.source)}</span></div>
        ${p.legs.map((l) => `<div class="small">${esc(l.home)} v ${esc(l.away)} — <b>${esc(SEL[l.sel] || l.sel)}</b> @ ${f2(l.odds)}</div>`).join('')}
        ${p.note ? `<div class="tiny muted">${esc(p.note)}</div>` : ''}</div>
        <div class="nums"><div><b>${f2(p.odds)}</b></div><div class="muted">${pct(p.p)}</div></div></div>`);
    });
    if (!(d.ledger || []).length) parts.push(`<div class="empty">No parlays recorded yet.</div>`);
    parts.push(`</div>`);
    view.innerHTML = parts.join('');
  }

  // ------------------------------------------------------------------ settings
  function renderSettings() {
    const parts = [`<div class="detail-head"><button class="back" id="back">‹ Back</button><div class="grow"><b>Settings</b></div></div>`];
    parts.push(`<div class="card settings"><label>GitHub repository (owner/name)</label><input id="s-repo" value="${esc(settings.repo)}">
      <label>Branch</label><input id="s-branch" value="${esc(settings.branch)}">
      <label>Live auto-refresh (seconds, min 20)</label><input id="s-live" type="number" value="${settings.liveEvery}">
      <label>Report timezone offset from UTC (hours; South Africa = 2)</label><input id="s-tz" type="number" value="${settings.tzOffset}">
      <div style="margin-top:12px"><button class="btn primary" id="s-save">Save</button><button class="btn" id="s-clear">Clear cache</button></div></div>`);
    parts.push(`<div class="card small"><b>About</b><div class="muted">Goals Scanner app ${native && native.version ? 'v' + native.version() : '(browser)'} · data from <a href="https://github.com/${esc(settings.repo)}">github.com/${esc(settings.repo)}</a>.</div>
      <div class="muted" style="margin-top:6px">The scanner runs three times a day on GitHub Actions; this app only reads what it publishes. Live scores come from Livescore.com's public feed and never influence the model. Statistical information, not advice.</div>
      <div style="margin-top:8px"><a class="btn" href="https://github.com/${esc(settings.repo)}/releases/latest">Check for app update</a></div></div>`);
    view.innerHTML = parts.join('');
    $('#back').onclick = () => { state.detail = null; render(); };
    $('#s-save').onclick = () => { settings.repo = $('#s-repo').value.trim() || DEFAULT_REPO; settings.branch = $('#s-branch').value.trim() || 'main';
      settings.liveEvery = Math.max(20, +$('#s-live').value || 60); settings.tzOffset = +$('#s-tz').value || 0; saveSettings(); scheduleLive(); toast('Saved'); state.detail = null; loadData(true); };
    $('#s-clear').onclick = () => { localStorage.removeItem('gs_latest'); state.data = null; toast('Cache cleared'); state.detail = null; loadData(true); };
  }

  // ------------------------------------------------------------------ router
  function render() {
    if (!state.data && state.detail !== 'settings') return;
    if (state.detail === 'settings') return renderSettings();
    if (state.detail) return renderDetail(state.detail);
    ({ today: renderToday, live: renderLive, fixtures: renderFixtures, reports: renderReports, ledger: renderLedger }[state.tab] || renderToday)();
  }
  function setTab(tab) {
    state.tab = tab; state.detail = null; state.report = null;
    document.querySelectorAll('#tabs button').forEach((b) => b.classList.toggle('active', b.dataset.tab === tab));
    render(); window.scrollTo(0, 0);
    if (tab === 'live' && state.data && Date.now() - state.lastLive > 15000) refreshLive(false);
  }
  document.querySelectorAll('#tabs button').forEach((b) => { b.onclick = () => setTab(b.dataset.tab); });
  $('#btn-refresh').onclick = () => { loadData(true); if (state.tab === 'live') refreshLive(true); };
  $('#btn-settings').onclick = () => { state.detail = 'settings'; render(); };
  view.addEventListener('click', (e) => {
    const open = e.target.closest('[data-open]'); if (open) { e.preventDefault(); state.detail = open.dataset.open; render(); return; }
    const item = e.target.closest('[data-fx]');
    if (item && item.classList.contains('tap')) { state.detail = item.dataset.fx; render(); return; }
    const a = e.target.closest('a[href]');
    if (a && /^https?:/.test(a.getAttribute('href')) && native && native.openUrl) { e.preventDefault(); native.openUrl(a.href); }
  });
  document.addEventListener('visibilitychange', () => { if (!document.hidden && state.tab === 'live') refreshLive(false); });

  window.app = {
    refresh() { loadData(true).then(() => { if (state.tab === 'live') refreshLive(true); }); },
    back() { if (state.detail) { state.detail = null; render(); return true; } if (state.report) { state.report = null; render(); return true; } if (state.tab !== 'today') { setTab('today'); return true; } return false; },
    onResume() { if (state.data && Date.now() - (state.data._loadedAt || 0) > 5 * 60000) loadData(false); if (state.tab === 'live') refreshLive(false); },
    state, settings,
  };

  // boot: cached first, then network
  const cached = localStorage.getItem('gs_latest');
  if (cached) { try { state.data = indexData(JSON.parse(cached)); statusLine(); render(); } catch (e) { /* ignore */ } }
  loadData(false).then(() => { if (state.data) state.data._loadedAt = Date.now(); });
  scheduleLive();
})();
