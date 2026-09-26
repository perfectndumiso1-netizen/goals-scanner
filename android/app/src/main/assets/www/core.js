/* PlayReport — core: settings, data access, native bridge, helpers, navigation.
   The published analysis (latest.json, day files, team files) is read through the native bridge;
   nothing about the publishing backend is ever shown. */
window.PR = (function () {
  'use strict';
  const native = window.Android || null;
  const RAW_BASE = (native && native.rawBase && native.rawBase()) || 'https://raw.githubusercontent.com/perfectndumiso1-netizen/goals-scanner/main/';
  const DATA_URL = (native && native.dataUrl && native.dataUrl()) || (RAW_BASE + 'data/app/latest.json');
  const CONTACT = { whatsapp: '27738212664', whatsappShown: '073 821 2664', email: 'msanindumiso@gmail.com' };
  const APP_VERSION = (native && native.version && native.version()) || '';
  const settings = Object.assign({ liveEvery: 60, tzOffset: 2, goalAlerts: true, minP: 0.70, minOdds: 1.30, hiP: 0.70 },
    JSON.parse(localStorage.getItem('pr_settings') || '{}'));
  const state = { data: null, tab: 'home', stack: [], live: {}, incidents: {}, liveTimer: null, lastLive: 0, loading: false,
    update: null, updateStage: null, days: {}, teams: {}, reports: {}, betsView: 'safest', search: '', sort: 'ko',
    dayView: 'results', matchView: 'overview', teamView: 'overview', menuOpen: false, expanded: {} };

  const $ = (sel, root) => (root || document).querySelector(sel);
  const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));
  function saveSettings() { localStorage.setItem('pr_settings', JSON.stringify(settings)); }

  // ------------------------------------------------------------------ fetch bridge
  let fid = 0; const pending = {};
  window.__fetchDone = function (id, code, body) { const cb = pending[id]; delete pending[id]; if (cb) cb({ code, body }); };
  function nfetch(url, ua) {
    if (native && native.fetch) return new Promise((resolve) => { const id = ++fid; pending[id] = resolve; native.fetch(id, url, ua || null); });
    return fetch(url).then(async (r) => ({ code: r.status, body: await r.text() })).catch((e) => ({ code: 0, body: String(e) }));
  }
  async function getJson(url, ua) { const r = await nfetch(url, ua); if (r.code !== 200) throw new Error(`HTTP ${r.code}`); return JSON.parse(r.body); }
  const rawUrl = (path) => RAW_BASE + path;

  // ------------------------------------------------------------------ formatting helpers
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const pct = (x) => (x == null || isNaN(x)) ? '–' : Math.round(x * 100) + '%';
  const f1 = (x) => (x == null || isNaN(x)) ? '–' : Number(x).toFixed(1);
  const f2 = (x) => (x == null || isNaN(x)) ? '–' : Number(x).toFixed(2);
  const signed = (x) => (x == null || isNaN(x)) ? '–' : (x >= 0 ? '+' : '') + (x * 100).toFixed(1) + '%';
  const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  function parseLocal(s) { if (!s) return null; const m = String(s).match(/(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2}))?/); if (!m) return null; return new Date(+m[1], +m[2] - 1, +m[3], +(m[4] || 0), +(m[5] || 0)); }
  function tzNow() { const n = new Date(); return new Date(n.getTime() + (settings.tzOffset * 60 + n.getTimezoneOffset()) * 60000); }
  function ymd(d) { return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; }
  function dayName(dateStr) { const d = parseLocal(dateStr); if (!d) return dateStr; const t = tzNow(); const today = ymd(t); const tom = ymd(new Date(t.getTime() + 86400000)); const yest = ymd(new Date(t.getTime() - 86400000)); const ds = dateStr.slice(0, 10); const nice = `${DAYS[d.getDay()]} ${d.getDate()} ${MONTHS[d.getMonth()]}`; return ds === today ? `Today · ${nice}` : ds === tom ? `Tomorrow · ${nice}` : ds === yest ? `Yesterday · ${nice}` : nice; }
  function niceDate(dateStr) { const d = parseLocal(dateStr); return d ? `${DAYS[d.getDay()]} ${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}` : dateStr; }
  const koTime = (s) => (s || '').slice(11, 16);
  function koShort(s) { const d = parseLocal(s); if (!d) return s || ''; return `${DAYS[d.getDay()]} ${s.slice(11, 16)}`; }
  function toast(msg) { const t = $('#toast'); t.textContent = msg; t.classList.add('show'); clearTimeout(t._h); t._h = setTimeout(() => t.classList.remove('show'), 2400); }
  function pill(p, hi, mid) { const cls = p >= (hi || 0.7) ? 'hi' : p >= (mid || 0.6) ? 'mid' : ''; return `<span class="pill ${cls}">${pct(p)}</span>`; }
  function bar(p, cls) { return `<span class="bar"><span class="fill ${cls || ''}" style="width:${Math.round((p || 0) * 100)}%"></span></span>`; }
  function wdl(gf, ga) { return gf > ga ? 'W' : gf < ga ? 'L' : 'D'; }
  function formBadges(items) { return `<span class="form">${(items || []).map((r) => `<i class="f ${r}">${r}</i>`).join('')}</span>`; }
  function md(text) {
    let html;
    const clean = String(text || '').replace(/Goals Scanner/g, 'PlayReport').replace(/https?:\/\/(?:www\.)?(?:github\.com|raw\.githubusercontent\.com)\/\S*/g, '');
    try { html = marked.parse(clean, { gfm: true, breaks: false }); } catch (e) { return `<pre>${esc(clean)}</pre>`; }
    const box = document.createElement('div'); box.innerHTML = html;
    box.querySelectorAll('a[href]').forEach((a) => { if (/github\.com|githubusercontent\.com/i.test(a.href)) { const s = document.createElement('span'); s.textContent = a.textContent; a.replaceWith(s); } });
    box.querySelectorAll('table').forEach((t) => { const n = t.querySelector('tr') ? t.querySelector('tr').children.length : 0; if (n > 4) t.classList.add('wide'); });
    return box.innerHTML;
  }

  // ------------------------------------------------------------------ selections (codes shared with the model)
  const GROUPS = { result: 'Match result', dc: 'Double chance', goals: 'Total goals', btts: 'Both teams to score', team: 'Team goals', corners: 'Corners', cards: 'Cards' };
  const GROUP_ICON = { result: '🏆', dc: '🛡️', goals: '⚽', btts: '🔁', team: '🎯', corners: '🚩', cards: '🟨' };
  const line = (code) => parseInt(code.replace(/\D/g, ''), 10) / 10;
  function selGroup(sel) {
    if (sel === 'H' || sel === 'D' || sel === 'A') return 'result';
    if (sel === '1X' || sel === '12' || sel === 'X2') return 'dc';
    if (sel === 'BTTS' || sel === 'NBTTS') return 'btts';
    if (sel[0] === 'O' || sel[0] === 'U') return 'goals';
    if (sel[0] === 'H' || sel[0] === 'A') return 'team';
    if (sel[0] === 'C') return 'corners';
    return 'cards';
  }
  function selLabel(sel, home, away) {
    home = home || 'Home'; away = away || 'Away';
    if (sel === 'H') return `${home} to win`; if (sel === 'A') return `${away} to win`; if (sel === 'D') return 'Draw';
    if (sel === '1X') return `${home} or draw`; if (sel === '12') return `${home} or ${away}`; if (sel === 'X2') return `Draw or ${away}`;
    if (sel === 'BTTS') return 'Both teams to score'; if (sel === 'NBTTS') return 'Not both teams to score';
    if (/^[OU]\d+$/.test(sel)) return `${sel[0] === 'O' ? 'Over' : 'Under'} ${line(sel).toFixed(1)} goals`;
    if (/^[HA][OU]\d+$/.test(sel)) return `${sel[0] === 'H' ? home : away} ${sel[1] === 'O' ? 'over' : 'under'} ${line(sel).toFixed(1)} goals`;
    if (sel[0] === 'C') return `${sel[1] === 'O' ? 'Over' : 'Under'} ${line(sel).toFixed(1)} corners`;
    if (sel[0] === 'K') return `${sel[1] === 'O' ? 'Over' : 'Under'} ${line(sel).toFixed(1)} cards`;
    return sel;
  }
  function selShort(sel) {
    const m = { H: '1', D: 'X', A: '2', '1X': '1X', '12': '12', X2: 'X2', BTTS: 'BTTS', NBTTS: 'No BTTS' };
    if (m[sel]) return m[sel];
    if (/^[OU]\d+$/.test(sel)) return `${sel[0] === 'O' ? 'O' : 'U'}${line(sel)}`;
    if (/^[HA][OU]\d+$/.test(sel)) return `${sel[0] === 'H' ? 'Home' : 'Away'} ${sel[1] === 'O' ? 'O' : 'U'}${line(sel)}`;
    if (sel[0] === 'C') return `Corners ${sel[1]}${line(sel)}`;
    if (sel[0] === 'K') return `Cards ${sel[1]}${line(sel)}`;
    return sel;
  }
  /** true / false / null (undecidable from goals) for a finished score */
  function settleSel(sel, hg, ag) {
    if (hg == null || ag == null) return null;
    const tot = hg + ag;
    if (sel === 'H') return hg > ag; if (sel === 'D') return hg === ag; if (sel === 'A') return ag > hg;
    if (sel === '1X') return hg >= ag; if (sel === '12') return hg !== ag; if (sel === 'X2') return ag >= hg;
    if (sel === 'BTTS') return hg > 0 && ag > 0; if (sel === 'NBTTS') return !(hg > 0 && ag > 0);
    if (/^[OU]\d+$/.test(sel)) return sel[0] === 'O' ? tot > line(sel) : tot < line(sel);
    if (/^[HA][OU]\d+$/.test(sel)) { const g = sel[0] === 'H' ? hg : ag; return sel[1] === 'O' ? g > line(sel) : g < line(sel); }
    return null;
  }
  /** provisional verdict while a match is in play */
  function liveVerdict(sel, s) {
    if (!s || s.status === 'NS' || s.hg == null) return { cls: '', text: 'not started' };
    const h = s.hg, a = s.ag, tot = h + a, ft = isFT(s), ok = settleSel(sel, h, a);
    if (ok == null) return { cls: '', text: ft ? 'settled later' : 'in play' };
    if (ft) return ok ? { cls: 'good', text: '✅ won' } : { cls: 'bad', text: '❌ lost' };
    if (/^[OU]\d+$/.test(sel) || /^[HA][OU]\d+$/.test(sel)) {
      const L = line(sel); const over = sel.includes('O');
      const g = /^[HA]/.test(sel) ? (sel[0] === 'H' ? h : a) : tot;
      if (over) return g > L ? { cls: 'good', text: '✅ landed' } : { cls: 'warn', text: `needs ${Math.ceil(L - g)} more` };
      return g < L ? { cls: 'warn', text: `on track (${g} so far)` } : { cls: 'bad', text: '❌ lost' };
    }
    if (sel === 'BTTS') return ok ? { cls: 'good', text: '✅ landed' } : { cls: 'warn', text: 'waiting' };
    if (sel === 'NBTTS') return ok ? { cls: 'warn', text: 'on track' } : { cls: 'bad', text: '❌ lost' };
    return ok ? { cls: 'good', text: 'winning now' } : { cls: 'bad', text: 'losing now' };
  }
  const isLive = (s) => s && s.status && s.status !== 'NS' && !['FT', 'AET', 'AP', 'Postp.', 'Canc.', 'Aband.'].includes(s.status);
  const isFT = (s) => s && ['FT', 'AET', 'AP'].includes(s.status);

  // ------------------------------------------------------------------ data
  function indexData(d) {
    d._byId = {}; (d.fixtures || []).forEach((f) => { d._byId[f.id] = f; f.sels = (f.sels || []).map((x) => Array.isArray(x) ? { sel: x[0], p: x[1], p_model: x[2], p_sb: x[3], odds: x[4], diff: !!x[5] } : x); });
    return d;
  }
  const fx = (id) => state.data && state.data._byId[id];
  async function loadData(force) {
    if (state.loading) return; state.loading = true; $('#btn-refresh').classList.add('spin');
    try {
      const d = indexData(await getJson(DATA_URL + '?t=' + Date.now()));
      state.data = d; d._loadedAt = Date.now(); localStorage.setItem('pr_latest', JSON.stringify(d));
      statusLine(); render(); if (force) toast('Updated');
    } catch (e) {
      if (!state.data) { const c = localStorage.getItem('pr_latest'); if (c) { try { state.data = indexData(JSON.parse(c)); statusLine(); render(); } catch (e2) { /* ignore */ } } }
      toast('Could not reach the PlayReport server (' + e.message + ')' + (state.data ? ' — showing saved data' : ''));
      if (!state.data) $('#view').innerHTML = `<div class="empty">No data yet.<br>Check your connection and pull to refresh.</div>`;
    } finally { state.loading = false; $('#btn-refresh').classList.remove('spin'); if (native && native.refreshDone) native.refreshDone(); }
  }
  function statusLine() {
    const m = state.data && state.data.meta; if (!m) return;
    $('#status-line').textContent = `Analysis ${m.generated} · next ${koShort(m.next_run || '')} · ${m.fixtures} fixtures`;
  }
  async function loadDay(date) {
    if (state.days[date] && state.days[date].fixtures) return state.days[date];
    const j = await getJson(rawUrl(`data/app/days/${date}.json`) + '?t=' + Math.floor(Date.now() / 300000));
    state.days[date] = j; return j;
  }
  const slug = (div) => String(div || '').replace(/[^A-Za-z0-9]+/g, '_').replace(/^_+|_+$/g, '');
  async function loadTeams(div) {
    const k = slug(div); if (state.teams[k]) return state.teams[k];
    const j = await getJson(rawUrl(`data/app/teams/${k}.json`) + '?t=' + Math.floor(Date.now() / 3600000));
    state.teams[k] = j; return j;
  }
  function teamsCached(div) { return state.teams[slug(div)] || null; }

  // ------------------------------------------------------------------ navigation
  const TABS = ['home', 'bets', 'live', 'matches', 'days'];
  function render() {
    if (!state.data && !(state.stack.length && state.stack[state.stack.length - 1].type === 'settings')) return;
    closeMenu();
    const top = state.stack[state.stack.length - 1];
    if (top) return PR.pages[top.type](top);
    PR.views[state.tab]();
  }
  function setTab(tab) {
    if (tab === 'today') tab = 'home';
    if (!TABS.includes(tab)) tab = 'home';
    state.tab = tab; state.stack = [];
    $$('#tabs button').forEach((b) => b.classList.toggle('active', b.dataset.tab === tab));
    render(); window.scrollTo(0, 0);
    if (tab === 'live' && state.data && Date.now() - state.lastLive > 15000) PR.live.refresh(false);
  }
  function push(page) { state.stack.push(page); render(); window.scrollTo(0, 0); }
  function replace(page) { state.stack[state.stack.length - 1] = page; render(); }
  function back() {
    if (state.menuOpen) { closeMenu(); return true; }
    if (state.stack.length) { state.stack.pop(); render(); window.scrollTo(0, 0); return true; }
    if (state.tab !== 'home') { setTab('home'); return true; }
    return false;
  }
  function openMatch(id) { if (fx(id)) push({ type: 'match', id }); else toast('This match is not in the current analysis'); }
  function openTeam(name, country, div) { push({ type: 'team', name, country, div }); }
  function toggleMenu() { state.menuOpen = !state.menuOpen; $('#menu').classList.toggle('open', state.menuOpen); }
  function closeMenu() { state.menuOpen = false; const m = $('#menu'); if (m) m.classList.remove('open'); }

  // ------------------------------------------------------------------ shared UI fragments
  function contactCard(compact) {
    return `<div class="card contact"><div class="row"><div class="grow"><b>Contact</b>${compact ? '' : '<div class="small muted">Questions, feedback or a request? Get in touch.</div>'}</div></div>
      <div class="contact-row"><a class="btn wa" href="https://wa.me/${CONTACT.whatsapp}"><span class="ic">💬</span> WhatsApp ${esc(CONTACT.whatsappShown)}</a>
      <a class="btn" href="mailto:${esc(CONTACT.email)}"><span class="ic">✉️</span> ${esc(CONTACT.email)}</a></div></div>`;
  }
  function teamLink(f, side) {
    const name = side === 'home' ? f.home : f.away; const long = side === 'home' ? (f.home_long || f.home) : (f.away_long || f.away);
    return `<a class="team" href="#" data-team="${esc(name)}" data-country="${esc(f.country)}" data-div="${esc(f.div)}">${esc(long)}</a>`;
  }
  function matchLine(f, extra) {
    return `<div class="list-item tap" data-fx="${esc(f.id)}"><div class="ko">${esc(koShort(f.kickoff))}</div>
      <div class="main"><div class="match">${esc(f.home)} <span class="muted">v</span> ${esc(f.away)}</div><div class="meta">${esc(f.competition)}</div></div>${extra || ''}</div>`;
  }
  function segmented(items, current, attr) {
    return `<div class="seg">${items.map(([k, label]) => `<button class="${k === current ? 'on' : ''}" data-${attr}="${k}">${label}</button>`).join('')}</div>`;
  }
  function select(id, options, current) {
    return `<select id="${id}">${options.map(([v, l]) => `<option value="${esc(v)}" ${String(v) === String(current) ? 'selected' : ''}>${esc(l)}</option>`).join('')}</select>`;
  }
  function scoreBox(s, f) {
    if (s && s.hg != null) return `<div class="right"><div class="score">${s.hg} – ${s.ag}</div>${isFT(s) ? `<span class="minute ft">${esc(s.status)}</span>` : isLive(s) ? `<span class="minute">${esc(s.status)}</span>` : `<span class="minute ft">${esc(koShort(f.kickoff))}</span>`}</div>`;
    return `<div class="right"><div class="score muted">v</div><span class="minute ft">${esc(koShort(f.kickoff))}</span></div>`;
  }
  const statusIcon = (st) => ({ hit: '✅', won: '✅', miss: '❌', lost: '❌', void: '∅', pending: '⏳' }[st] || '');

  // ------------------------------------------------------------------ global click handling
  document.addEventListener('click', (e) => {
    const t = e.target.closest('[data-team]');
    if (t) { e.preventDefault(); e.stopPropagation(); openTeam(t.dataset.team, t.dataset.country, t.dataset.div); return; }
    const m = e.target.closest('[data-fx]');
    if (m && (m.classList.contains('tap') || m.tagName === 'A' || m.tagName === 'BUTTON')) { e.preventDefault(); openMatch(m.dataset.fx); return; }
    const a = e.target.closest('a[href]');
    if (a && /^(https?:|mailto:|tel:)/.test(a.getAttribute('href')) && native && native.openUrl) { e.preventDefault(); native.openUrl(a.href); return; }
    if (state.menuOpen && !e.target.closest('#menu') && !e.target.closest('#btn-menu')) closeMenu();
  });

  return { native, settings, state, $, $$, saveSettings, nfetch, getJson, rawUrl, esc, pct, f1, f2, signed, DAYS, MONTHS, parseLocal, tzNow, ymd,
    dayName, niceDate, koTime, koShort, toast, pill, bar, wdl, formBadges, md, GROUPS, GROUP_ICON, selGroup, selLabel, selShort, settleSel,
    liveVerdict, isLive, isFT, indexData, fx, loadData, statusLine, loadDay, loadTeams, teamsCached, slug, TABS, render, setTab, push, replace,
    back, openMatch, openTeam, toggleMenu, closeMenu, contactCard, teamLink, matchLine, segmented, select, scoreBox, statusIcon, CONTACT, APP_VERSION,
    views: {}, pages: {}, live: {} };
})();
