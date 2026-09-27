/* PlayReport — core: settings, data access, native bridge, helpers, navigation.
   The published analysis (latest.json, day files, team files) is read through the native bridge;
   nothing about the publishing backend is ever shown. */
window.PR = (function () {
  'use strict';
  const native = window.Android || null;
  const RAW_BASE = (native && native.rawBase && native.rawBase()) || 'https://raw.githubusercontent.com/perfectndumiso1-netizen/goals-scanner/data/';
  const DATA_URL = (native && native.dataUrl && native.dataUrl()) || (RAW_BASE + 'data/app/latest.json');
  const CONTACT = { whatsapp: '27738212664', whatsappShown: '073 821 2664', email: 'msanindumiso@gmail.com' };
  const APP_VERSION = (native && native.version && native.version()) || '';
  const settings = Object.assign({ liveEvery: 60, tzOffset: 2, goalAlerts: true, htAlerts: false, ftAlerts: true, betAlerts: true, reportAlerts: true, minP: 0.70, minOdds: 1.30, hiP: 0.70, theme: 'system', seenVersion: '', leagues: 'all' },
    JSON.parse(localStorage.getItem('pr_settings') || '{}'));
  const state = { data: null, tab: 'home', stack: [], live: {}, incidents: {}, liveTimer: null, lastLive: 0, loading: false,
    update: null, updateStage: null, days: {}, teams: {}, reports: {}, details: {}, betsView: 'today', search: '', sort: 'ko', matchFilter: 'all',
    liveView: 'tracked', liveAll: null, lastLiveAll: 0, dayView: 'results', matchView: 'overview', teamView: 'overview', menuOpen: false, expanded: {}, badges: {}, dark: false };
  const BADGE_BASE = 'https://lsm-static-prod.livescore.com/medium/';

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
  const icon = (name, cls) => `<svg class="ic ${cls || ''}" aria-hidden="true"><use href="#i-${name}"/></svg>`;
  const FLAGS = { England: '🏴󠁧󠁢󠁥󠁮󠁧󠁿', Scotland: '🏴󠁧󠁢󠁳󠁣󠁴󠁿', Wales: '🏴󠁧󠁢󠁷󠁬󠁳󠁿', Spain: '🇪🇸', Italy: '🇮🇹', Germany: '🇩🇪', France: '🇫🇷', Netherlands: '🇳🇱', Belgium: '🇧🇪', Portugal: '🇵🇹', Turkey: '🇹🇷', Greece: '🇬🇷',
    USA: '🇺🇸', Mexico: '🇲🇽', Argentina: '🇦🇷', Brazil: '🇧🇷', Japan: '🇯🇵', China: '🇨🇳', Norway: '🇳🇴', Sweden: '🇸🇪', Denmark: '🇩🇰', Finland: '🇫🇮', Poland: '🇵🇱', Romania: '🇷🇴', Russia: '🇷🇺',
    Austria: '🇦🇹', Switzerland: '🇨🇭', Ireland: '🇮🇪', Australia: '🇦🇺', 'South Africa': '🇿🇦', Turkiye: '🇹🇷', Croatia: '🇭🇷', Serbia: '🇷🇸', Czechia: '🇨🇿', 'Czech Republic': '🇨🇿',
    Slovakia: '🇸🇰', Slovenia: '🇸🇮', Hungary: '🇭🇺', Bulgaria: '🇧🇬', Ukraine: '🇺🇦', Israel: '🇮🇱', Egypt: '🇪🇬', Morocco: '🇲🇦', Algeria: '🇩🇿', Tunisia: '🇹🇳', Nigeria: '🇳🇬', Ghana: '🇬🇭', Kenya: '🇰🇪',
    'Saudi Arabia': '🇸🇦', Qatar: '🇶🇦', 'United Arab Emirates': '🇦🇪', UAE: '🇦🇪', Iran: '🇮🇷', Iraq: '🇮🇶', India: '🇮🇳', 'South Korea': '🇰🇷', 'Korea Republic': '🇰🇷', Colombia: '🇨🇴', Chile: '🇨🇱',
    Uruguay: '🇺🇾', Peru: '🇵🇪', Ecuador: '🇪🇨', Paraguay: '🇵🇾', Bolivia: '🇧🇴', Venezuela: '🇻🇪', Canada: '🇨🇦', Iceland: '🇮🇸', Cyprus: '🇨🇾', 'Northern Ireland': '🇬🇧', Guatemala: '🇬🇹', 'Costa Rica': '🇨🇷',
    Honduras: '🇭🇳', 'El Salvador': '🇸🇻', Panama: '🇵🇦', Jamaica: '🇯🇲', Estonia: '🇪🇪', Latvia: '🇱🇻', Lithuania: '🇱🇹', Belarus: '🇧🇾', Kazakhstan: '🇰🇿', Georgia: '🇬🇪', Armenia: '🇦🇲', Azerbaijan: '🇦🇿',
    Uzbekistan: '🇺🇿', Vietnam: '🇻🇳', Thailand: '🇹🇭', Indonesia: '🇮🇩', Malaysia: '🇲🇾', Singapore: '🇸🇬', Philippines: '🇵🇭', 'New Zealand': '🇳🇿', Bosnia: '🇧🇦', 'Bosnia and Herzegovina': '🇧🇦',
    'North Macedonia': '🇲🇰', Albania: '🇦🇱', Montenegro: '🇲🇪', Kosovo: '🇽🇰', Moldova: '🇲🇩', Luxembourg: '🇱🇺', Malta: '🇲🇹', 'Faroe Islands': '🇫🇴', Andorra: '🇦🇩', Gibraltar: '🇬🇮', Tanzania: '🇹🇿',
    Uganda: '🇺🇬', Zambia: '🇿🇲', Zimbabwe: '🇿🇼', Cameroon: '🇨🇲', Senegal: '🇸🇳', 'Ivory Coast': '🇨🇮', "Cote d'Ivoire": '🇨🇮', Angola: '🇦🇴', Mozambique: '🇲🇿', Botswana: '🇧🇼', Namibia: '🇳🇦',
    Ethiopia: '🇪🇹', Rwanda: '🇷🇼', Sudan: '🇸🇩', Libya: '🇱🇾', Jordan: '🇯🇴', Kuwait: '🇰🇼', Bahrain: '🇧🇭', Oman: '🇴🇲', Lebanon: '🇱🇧', Syria: '🇸🇾', 'Hong Kong': '🇭🇰', Bangladesh: '🇧🇩',
    'Costa Rica ': '🇨🇷', Nicaragua: '🇳🇮', 'Dominican Republic': '🇩🇴', Cuba: '🇨🇺', 'Trinidad and Tobago': '🇹🇹', Haiti: '🇭🇹', Fiji: '🇫🇯' };
  const flag = (country) => FLAGS[country] || (/^(UEFA|CONMEBOL|CONCACAF|CAF|AFC|FIFA|World|Europe|International|Friendl|Olympic|Africa|Asia|Copa)/i.test(country || '') ? '🏆' : '🌍');
  function hue(name) { let h = 0; for (const c of String(name || '')) h = (h * 31 + c.charCodeAt(0)) % 360; return h; }
  const initials = (name) => String(name || '?').replace(/\b(FC|CF|SC|AFC|Utd|United|City|Town|Athletic|Club|De|Los|Las|La|El)\b/g, '').trim().split(/\s+/).map((w) => w[0]).join('').slice(0, 2).toUpperCase() || '?';
  /** team badge: Livescore image when known, otherwise an initials disc coloured from the name */
  function badge(name, img, size) {
    img = img || state.badges[name];
    const cls = `badge s${size || 24}`;
    if (!img) return `<span class="${cls} nb" style="--h:${hue(name)}"><i>${esc(initials(name))}</i></span>`;
    return `<span class="${cls}" style="--h:${hue(name)}"><img src="${esc(BADGE_BASE + img)}" alt="" loading="lazy" onerror="this.parentNode.classList.add('nb');this.remove()"><i>${esc(initials(name))}</i></span>`;
  }
  const fxBadge = (f, side) => badge(f[side], f.badges && f.badges[side]);
  /** Sofascore-style match row: kick-off / status column, two team lines with badges and score, optional right block */
  function matchRow(m, opts) {
    opts = opts || {}; const s = opts.live; const sc = s && s.hg != null ? s : (m.score && m.score.hg != null ? m.score : null);
    const status = sc ? (sc.status || '') : ''; const liveNow = sc && isLive(sc); const ft = sc && isFT(sc);
    const left = sc ? `<div class="minute ${liveNow ? 'on' : 'ft'}">${esc(liveNow ? status : ft ? 'FT' : status)}</div>${ft || liveNow ? '' : ''}` : `<div class="ko">${esc(opts.short ? koTime(m.kickoff) : koShort(m.kickoff)).replace(' ', '<br>')}</div>`;
    const hw = sc && sc.hg > sc.ag, aw = sc && sc.ag > sc.hg;
    const tm = (side, won) => `<div class="tm ${won ? 'won' : ''}">${badge(m[side], m.badges && m.badges[side], 22)}<span class="nm">${esc(opts.long ? (m[side + '_long'] || m[side]) : m[side])}</span>${sc ? `<span class="sc">${side === 'home' ? sc.hg : sc.ag}</span>` : ''}</div>`;
    return `<div class="mrow ${opts.tap === false ? '' : 'tap'} ${liveNow ? 'is-live' : ''}" data-fx="${esc(m.id)}"><div class="mrow-l">${left}</div>
      <div class="mrow-m">${tm('home', hw)}${tm('away', aw)}${opts.sub != null ? `<div class="sub">${opts.sub}</div>` : `<div class="sub">${flag(m.country)} ${esc(m.competition || m.league || '')}</div>`}</div>
      ${opts.right ? `<div class="mrow-r">${opts.right}</div>` : ''}</div>`;
  }
  const skeleton = (n) => `<div class="card sk">${Array.from({ length: n || 3 }).map(() => '<div class="sk-row"><span class="sk-b"></span><span class="sk-l"></span></div>').join('')}</div>`;
  /** 0–1 → SVG ring */
  function ring(p, label, size) {
    size = size || 64; const r = (size - 8) / 2, c = 2 * Math.PI * r, v = Math.max(0, Math.min(1, p || 0));
    const cls = v >= 0.8 ? 'hi' : v >= 0.6 ? 'mid' : 'lo';
    return `<div class="ring ${cls}" style="width:${size}px"><svg viewBox="0 0 ${size} ${size}" width="${size}" height="${size}"><circle class="tr" cx="${size / 2}" cy="${size / 2}" r="${r}"/><circle class="pr" cx="${size / 2}" cy="${size / 2}" r="${r}" stroke-dasharray="${c.toFixed(1)}" stroke-dashoffset="${(c * (1 - v)).toFixed(1)}"/></svg><div class="rv">${pct(p)}</div>${label ? `<div class="rl">${label}</div>` : ''}</div>`;
  }
  // ------------------------------------------------------------------ theme
  const darkMedia = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;
  function applyTheme() {
    const t = settings.theme || 'system'; document.documentElement.dataset.theme = t;
    state.dark = t === 'dark' || (t === 'system' && !!(darkMedia && darkMedia.matches));
    if (native && native.setTheme) { try { native.setTheme(state.dark); } catch (e) { /* ignore */ } }
  }
  if (darkMedia && darkMedia.addEventListener) darkMedia.addEventListener('change', () => { if ((settings.theme || 'system') === 'system') applyTheme(); });
  applyTheme();
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
  const selObj = (x) => Array.isArray(x) ? { sel: x[0], p: x[1], p_model: x[2], p_sb: x[3], odds: x[4], diff: !!x[5] } : x;
  function indexData(d) {
    d._byId = {}; (d.fixtures || []).forEach((f) => { d._byId[f.id] = f; f.sels = (f.sels || []).map(selObj); f.p = f.p || {}; f.xg = f.xg || [null, null]; f.x12 = f.x12 || [null, null, null]; f.major = f.tier !== 'world'; });
    if (d.safe && d.safe.bets) d.safe.bets.forEach((b) => { const f = d._byId[b.fixture]; b.major = f ? f.major : true; });
    return d;
  }
  const fx = (id) => state.data && state.data._byId[id];
  /** full analysis of one match (per-match file); cached for the session */
  const detailKey = (id, d) => d || (fx(id) && fx(id).d) || null;
  function detailCached(id, d) { const k = detailKey(id, d); return k ? state.details[k] || null : null; }
  async function loadDetail(id, d) {
    const k = detailKey(id, d); if (!k) throw new Error('no detail key');
    if (state.details[k] && !state.details[k].error) return state.details[k];
    const stamp = state.data && state.data.meta ? state.data.meta.generated.replace(/\D/g, '') : Math.floor(Date.now() / 900000);
    const j = await getJson(rawUrl(`data/app/fx/${k}.json`) + '?t=' + stamp);
    j.sels = (j.sels || []).map(selObj); j.trends = j.trends || {}; j.teams = j.teams || { home: {}, away: {} }; j.h2h = j.h2h || [];
    state.details[k] = j; return j;
  }
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
    $('#status-line').textContent = `Updated ${koShort(m.generated)} · next ${koTime(m.next_run || '')} · ${m.fixtures} matches`;
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
  async function loadBadges() {
    try { const c = localStorage.getItem('pr_badges'); if (c) state.badges = JSON.parse(c); } catch (e) { /* ignore */ }
    try { const j = await getJson(rawUrl('data/app/badges.json') + '?t=' + Math.floor(Date.now() / 86400000)); if (j && typeof j === 'object') { state.badges = j; localStorage.setItem('pr_badges', JSON.stringify(j)); } } catch (e) { /* offline: keep cache */ }
  }

  // ------------------------------------------------------------------ navigation
  const TABS = ['home', 'bets', 'live', 'matches', 'days'];
  function render() {
    if (!state.data && !(state.stack.length && state.stack[state.stack.length - 1].type === 'settings')) return;
    closeMenu();
    const top = state.stack[state.stack.length - 1];
    if (state.data && (state.data.version || 1) < 3 && !(top && top.type === 'settings')) {
      $('#view').innerHTML = `<div class="card empty">This version of PlayReport needs the new analysis format.<br>It arrives with the next scheduled analysis — pull down to refresh later.</div>`;
      return;
    }
    const v = $('#view'); v.classList.remove('enter'); void v.offsetWidth; v.classList.add('enter');
    document.body.classList.toggle('depth', !!top);
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
  function openMatch(id, d) { if (fx(id) || d) { state.matchView = 'overview'; push({ type: 'match', id, d: d || null }); } else toast('This match is no longer in the current analysis'); }
  function openTeam(name, country, div) { state.teamView = 'overview'; push({ type: 'team', name, country, div }); }
  function toggleMenu() { state.menuOpen = !state.menuOpen; $('#menu').classList.toggle('open', state.menuOpen); }
  function closeMenu() { state.menuOpen = false; const m = $('#menu'); if (m) m.classList.remove('open'); }

  // ------------------------------------------------------------------ shared UI fragments
  function contactCard(compact) {
    return `<div class="card contact"><div class="row"><div class="grow"><b>Contact</b>${compact ? '' : '<div class="small muted">Questions, feedback or a request? Get in touch.</div>'}</div></div>
      <div class="contact-row"><a class="btn wa" href="https://wa.me/${CONTACT.whatsapp}">${icon('chat')} WhatsApp ${esc(CONTACT.whatsappShown)}</a>
      <a class="btn" href="mailto:${esc(CONTACT.email)}">${icon('mail')} ${esc(CONTACT.email)}</a></div></div>`;
  }
  function teamLink(f, side) {
    const name = side === 'home' ? f.home : f.away; const long = side === 'home' ? (f.home_long || f.home) : (f.away_long || f.away);
    return `<a class="team" href="#" data-team="${esc(name)}" data-country="${esc(f.country)}" data-div="${esc(f.div)}">${esc(long)}</a>`;
  }
  function matchLine(f, extra) { return matchRow(f, { right: extra || '' }); }
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
    if (m && (m.classList.contains('tap') || m.tagName === 'A' || m.tagName === 'BUTTON')) { e.preventDefault(); openMatch(m.dataset.fx, m.dataset.d || null); return; }
    const a = e.target.closest('a[href]');
    if (a && /^(https?:|mailto:|tel:)/.test(a.getAttribute('href')) && native && native.openUrl) { e.preventDefault(); native.openUrl(a.href); return; }
    if (state.menuOpen && !e.target.closest('#menu') && !e.target.closest('#btn-menu') && !e.target.closest('#btn-search')) closeMenu();
  });

  return { native, settings, state, $, $$, saveSettings, nfetch, getJson, rawUrl, esc, pct, f1, f2, signed, DAYS, MONTHS, parseLocal, tzNow, ymd,
    dayName, niceDate, koTime, koShort, toast, pill, bar, wdl, formBadges, md, GROUPS, GROUP_ICON, selGroup, selLabel, selShort, settleSel,
    liveVerdict, isLive, isFT, indexData, fx, loadDetail, detailCached, detailKey, loadData, statusLine, loadDay, loadTeams, teamsCached, slug, TABS, render, setTab, push, replace,
    back, openMatch, openTeam, toggleMenu, closeMenu, contactCard, teamLink, matchLine, matchRow, segmented, select, scoreBox, statusIcon, CONTACT, APP_VERSION,
    icon, flag, badge, fxBadge, skeleton, ring, applyTheme, loadBadges, BADGE_BASE,
    views: {}, pages: {}, live: {} };
})();
