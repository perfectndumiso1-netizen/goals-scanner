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
  /** localStorage first; when it is empty (fresh install, WebView data cleared) the copy kept in native preferences is restored */
  function stored(key) {
    let v = null;
    try { v = localStorage.getItem(key); } catch (e) { v = null; }
    if (v == null && native && native.getString) {
      try { v = native.getString(key.replace(/^pr_/, '')); if (v != null) localStorage.setItem(key, v); } catch (e) { v = null; }
    }
    return v;
  }
  function persist(key, value) {
    try { localStorage.setItem(key, value); } catch (e) { /* quota */ }
    if (native && native.setString) { try { native.setString(key.replace(/^pr_/, ''), value); } catch (e) { /* ignore */ } }
  }
  let savedSettings = {};
  try { savedSettings = JSON.parse(stored('pr_settings') || '{}'); } catch (e) { savedSettings = {}; }
  const settings = Object.assign({ liveEvery: 60, tzOffset: 2, goalAlerts: true, htAlerts: false, ftAlerts: true, betAlerts: true, reportAlerts: true, minP: 0.70, minOdds: 1.30, hiP: 0.70, theme: 'dark', seenVersion: '', leagues: 'all' },
    savedSettings);
  const state = { data: null, tab: 'home', stack: [], live: {}, incidents: {}, liveTimer: null, lastLive: 0, loading: false,
    update: null, updateStage: null, days: {}, teams: {}, reports: {}, details: {}, betsView: 'today', search: '', sort: 'ko', matchFilter: 'all',
    liveView: 'tracked', liveAll: null, lastLiveAll: 0, dayView: 'results', matchView: 'overview', teamView: 'overview', menuOpen: false, expanded: {}, badges: {}, dark: false };
  const BADGE_BASE = 'https://lsm-static-prod.livescore.com/medium/';

  const $ = (sel, root) => (root || document).querySelector(sel);
  const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));
  function saveSettings() { persist('pr_settings', JSON.stringify(settings)); }

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
  /** in-app confirm (Android WebView swallows window.confirm) */
  function confirmBox(title, text, okLabel) {
    return new Promise((resolve) => {
      const m = $('#modal'); if (!m) { resolve(window.confirm(`${title}\n\n${text}`)); return; }
      $('#modal-title').textContent = title; $('#modal-text').textContent = text || ''; $('#modal-ok').textContent = okLabel || 'OK';
      m.hidden = false;
      const done = (v) => { m.hidden = true; $('#modal-ok').onclick = null; $('#modal-cancel').onclick = null; m.onclick = null; resolve(v); };
      $('#modal-ok').onclick = () => done(true); $('#modal-cancel').onclick = () => done(false);
      m.onclick = (e) => { if (e.target === m) done(false); };
    });
  }
  // favourite matches (kept on the phone; tracked for goal / HT / FT alerts and kick-off reminders)
  let favs = [];
  try { favs = JSON.parse(stored('pr_favs_full') || localStorage.getItem('pr_favs') || '[]'); } catch (e) { favs = []; }
  const isFav = (id) => favs.some((f) => f.fixture === id);
  function saveFavs() {
    const keep = ymd(new Date(tzNow().getTime() - 2 * 86400000));
    favs = favs.filter((f) => f.kickoff.slice(0, 10) >= keep);
    persist('pr_favs_full', JSON.stringify(favs));
    if (native && native.setString) { try { native.setString('favs', JSON.stringify(favs.map((f) => ({ eid: f.eid, kickoff: f.kickoff, home: f.home, away: f.away, competition: f.competition })))); } catch (e) { /* ignore */ } }
  }
  function toggleFav(id) {
    const f = fx(id); if (!f) return;
    if (isFav(id)) { favs = favs.filter((x) => x.fixture !== id); toast('Removed from favourites'); }
    else { favs.push({ fixture: id, eid: f.livescore_id || null, kickoff: f.kickoff, home: f.home, away: f.away, competition: f.competition, country: f.country }); toast('Added to favourites — you will get goal and kick-off alerts'); }
    saveFavs(); render();
  }
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
  /** sels rows: [sel, p (model), p_model, p_market (implied, comparison only), odds, disagreement flag, diff pp, EV] */
  const selObj = (x) => Array.isArray(x) ? { sel: x[0], p: x[1], p_model: x[2], p_sb: x[3], odds: x[4], diff: !!x[5], diff_pp: x.length > 6 ? x[6] : (x[2] != null && x[3] != null ? Math.round(1000 * (x[2] - x[3])) / 10 : null), ev: x.length > 7 ? x[7] : (x[2] != null && x[4] ? Math.round(1000 * (x[2] * x[4] - 1)) / 1000 : null) } : x;
  function indexData(d) {
    d._byId = {}; (d.fixtures || []).forEach((f) => { d._byId[f.id] = f; f.sels = (f.sels || []).map(selObj); f.p = f.p || {}; f.xg = f.xg || [null, null]; f.x12 = f.x12 || [null, null, null]; f.major = f.tier !== 'world'; });
    if (d.safe && d.safe.bets) d.safe.bets.forEach((b) => { const f = d._byId[b.fixture]; b.major = f ? f.major : true; });
    return d;
  }
  const fx = (id) => state.data && state.data._byId[id];
  /** on-phone cache of the small data files (per-match analysis, day history, team pages): pages open instantly
   *  from the cache and are refreshed in the background when the publication is newer than the cached copy */
  const CACHE_MAX = 400;
  const cache = {
    key: (k) => 'pr_c:' + k,
    get(k) { try { const v = localStorage.getItem(this.key(k)); return v ? JSON.parse(v) : null; } catch (e) { return null; } },
    put(k, data, stamp) {
      const rec = { t: Date.now(), s: stamp || '', d: data };
      try { localStorage.setItem(this.key(k), JSON.stringify(rec)); } catch (e) { this.prune(true); try { localStorage.setItem(this.key(k), JSON.stringify(rec)); } catch (e2) { /* give up */ } }
      this.count = (this.count || 0) + 1; if (this.count % 25 === 0) this.prune(false);
    },
    prune(hard) {
      const keys = []; for (let i = 0; i < localStorage.length; i++) { const k = localStorage.key(i); if (k && k.startsWith('pr_c:')) keys.push(k); }
      if (!hard && keys.length <= CACHE_MAX) return;
      const items = keys.map((k) => { let t = 0; try { t = (JSON.parse(localStorage.getItem(k)) || {}).t || 0; } catch (e) { t = 0; } return { k, t }; }).sort((a, b) => a.t - b.t);
      const drop = hard ? Math.max(Math.ceil(items.length / 2), 1) : items.length - CACHE_MAX;
      items.slice(0, drop).forEach((x) => localStorage.removeItem(x.k));
    },
    size() { let n = 0, b = 0; for (let i = 0; i < localStorage.length; i++) { const k = localStorage.key(i); if (k && k.startsWith('pr_c:')) { n++; b += (localStorage.getItem(k) || '').length; } } return { n, kb: Math.round(b / 1024) }; },
    clear() { const keys = []; for (let i = 0; i < localStorage.length; i++) { const k = localStorage.key(i); if (k && k.startsWith('pr_c:')) keys.push(k); } keys.forEach((k) => localStorage.removeItem(k)); },
  };
  const pubStamp = () => (state.data && state.data.meta ? state.data.meta.generated.replace(/\D/g, '') : '');
  /** full analysis of one match (per-match file); session memory first, then the on-phone cache, then the network */
  const detailKey = (id, d) => d || (fx(id) && fx(id).d) || null;
  function detailCached(id, d) { const k = detailKey(id, d); return k ? state.details[k] || null : null; }
  function prepDetail(j) { j.sels = (j.sels || []).map(selObj); j.trends = j.trends || {}; j.teams = j.teams || { home: {}, away: {} }; j.h2h = j.h2h || []; return j; }
  async function fetchDetail(k, stamp) {
    const j = prepDetail(await getJson(rawUrl(`data/app/fx/${k}.json`) + '?t=' + (stamp || Math.floor(Date.now() / 900000))));
    state.details[k] = j; cache.put('fx/' + k, j, stamp); return j;
  }
  async function loadDetail(id, d) {
    const k = detailKey(id, d); if (!k) throw new Error('no detail key');
    if (state.details[k] && !state.details[k].error) return state.details[k];
    const stamp = pubStamp();
    const c = cache.get('fx/' + k);
    if (c && c.d) {
      const f = fx(id); const j = prepDetail(c.d); state.details[k] = j;
      // a match that is still in the current publication may have a fresher analysis: refresh quietly
      if (f && !f.frozen && c.s !== stamp) fetchDetail(k, stamp).then(() => render()).catch(() => { /* keep cache */ });
      return j;
    }
    return fetchDetail(k, stamp);
  }
  /** warm the cache for the pages the user is most likely to open (bets of the day, safest bets, favourites) */
  function prefetchDetails() {
    if (!state.data) return;
    const d = state.data; const stamp = pubStamp(); const want = [];
    ((d.safe && d.safe.today && d.safe.today.bets) || []).forEach((b) => want.push(b.fixture));
    ((d.safe && d.safe.bets) || []).slice(0, 12).forEach((b) => want.push(b.fixture));
    favs.forEach((f) => want.push(f.fixture));
    const keys = []; want.forEach((id) => { const k = detailKey(id); if (k && !keys.includes(k)) keys.push(k); });
    let i = 0;
    const next = () => {
      if (i >= keys.length || i >= 30) return;
      const k = keys[i++]; const c = cache.get('fx/' + k);
      if (c && c.s === stamp) { next(); return; }
      fetchDetail(k, stamp).catch(() => { /* ignore */ }).finally(() => setTimeout(next, 150));
    };
    next(); if (keys.length > 1) setTimeout(next, 300);
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
    const c = cache.get('days/' + date); const today = ymd(tzNow());
    const fetchIt = async () => { const j = await getJson(rawUrl(`data/app/days/${date}.json`) + '?t=' + Math.floor(Date.now() / 300000)); state.days[date] = j; cache.put('days/' + date, j, date < today ? 'final' : pubStamp()); return j; };
    if (c && c.d) {
      state.days[date] = c.d;
      // past days settle over a few hours (results, statistics); refresh them in the background until they are a day old
      if (date >= today || (c.s !== 'final' && Date.now() - c.t > 30 * 60000) || (date >= ymd(new Date(tzNow().getTime() - 86400000)) && Date.now() - c.t > 30 * 60000)) fetchIt().then(() => render()).catch(() => { /* keep cache */ });
      return c.d;
    }
    return fetchIt();
  }
  const slug = (div) => String(div || '').replace(/[^A-Za-z0-9]+/g, '_').replace(/^_+|_+$/g, '');
  async function loadTeams(div) {
    const k = slug(div); if (state.teams[k]) return state.teams[k];
    const c = cache.get('teams/' + k);
    const fetchIt = async () => { const j = await getJson(rawUrl(`data/app/teams/${k}.json`) + '?t=' + Math.floor(Date.now() / 3600000)); state.teams[k] = j; cache.put('teams/' + k, j, ymd(tzNow())); return j; };
    if (c && c.d) { state.teams[k] = c.d; if (c.s !== ymd(tzNow())) fetchIt().then(() => render()).catch(() => { /* keep cache */ }); return c.d; }
    return fetchIt();
  }
  function teamsCached(div) { return state.teams[slug(div)] || null; }
  async function loadBadges() {
    try { const c = localStorage.getItem('pr_badges'); if (c) state.badges = JSON.parse(c); } catch (e) { /* ignore */ }
    try { const j = await getJson(rawUrl('data/app/badges.json') + '?t=' + Math.floor(Date.now() / 86400000)); if (j && typeof j === 'object') { state.badges = j; localStorage.setItem('pr_badges', JSON.stringify(j)); } } catch (e) { /* offline: keep cache */ }
  }

  // ------------------------------------------------------------------ navigation
  const TABS = ['home', 'bets', 'live', 'matches', 'days', 'leagues'];
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
  /** The day-file record of a fixture (final score, half-time, statistics, goal incidents, bets) once its day is loaded. */
  function dayRecord(id) {
    if (!id) return null; const date = String(id).slice(0, 10); const day = state.days[date];
    return day && day.fixtures ? (day.fixtures.find((x) => x.id === id) || null) : null;
  }
  /** Final score + stats of a finished match from the archive (day files). Loads the day in the background for
   *  matches that kicked off more than two hours ago; returns null until it is there. */
  function finalFor(f) {
    if (!f || !f.kickoff) return null;
    const date = f.kickoff.slice(0, 10); const r = dayRecord(f.id);
    if (r) return r.score && r.score.hg != null ? r.score : null;
    const ko = parseLocal(f.kickoff);
    if (ko && tzNow() - ko > 2 * 3600000 && !(state.days[date] && state.days[date].fixtures) && !state.days[date + '_loading']) {
      state.days[date + '_loading'] = true; loadDay(date).then(() => render()).catch(() => { state.days[date + '_loading'] = false; });
    }
    return null;
  }
  /** Stored incidents ([minute, team, type, player, score] rows) in the live-incident item shape. */
  function storedIncidents(sc) {
    if (!sc || !Array.isArray(sc.inc)) return null;
    const T = { own_goal: 'own goal', second_yellow: 'second yellow', missed_penalty: 'missed penalty' };
    return sc.inc.map((r) => ({ min: r[0], team: r[1], type: T[r[2]] || r[2], player: r[3], score: r[4] }));
  }
  function openMatch(id, d) { if (fx(id) || d || dayRecord(id)) { state.matchView = 'overview'; push({ type: 'match', id, d: d || null }); } else toast('This match is no longer in the current analysis'); }
  function openTeam(name, country, div) { state.teamView = 'overview'; push({ type: 'team', name, country, div }); }
  function toggleMenu() { state.menuOpen = !state.menuOpen; $('#menu').classList.toggle('open', state.menuOpen); }
  function closeMenu() { state.menuOpen = false; const m = $('#menu'); if (m) m.classList.remove('open'); }

  // ------------------------------------------------------------------ shared UI fragments
  const EDITOR = { name: 'Ndumiso Msani', role: 'Editor & Lead Analyst', place: 'Mthwalume, KwaZulu-Natal', age: 37,
    bio: 'Sports bettor and football analyst with a data-first approach. Ndumiso built PlayReport to turn thousands of results, prices and match statistics into a small number of disciplined, graded selections every day — specialising in goals, corners and bookings markets across world football.' };
  function editorCard(compact) {
    // compact: round avatar next to the name (home page); full: portrait photo with the profile (About / Guide)
    if (!compact) return `<div class="card"><div class="editor full"><div class="portrait"><img src="editor.jpg" alt="${esc(EDITOR.name)}" onerror="this.parentNode.style.display='none'"></div><div class="grow"><div class="b" style="font-size:17px">${esc(EDITOR.name)}</div><div class="small muted">${esc(EDITOR.role)}</div><div class="small muted">${esc(EDITOR.place)} · ${EDITOR.age}</div><div class="small" style="margin-top:8px">${esc(EDITOR.bio)}</div></div></div>
      <div class="tiny muted" style="margin-top:8px">Every selection published here is graded automatically against the final result — the record under Performance is the only opinion that counts. Statistical information, not betting advice. 18+.</div></div>`;
    return `<div class="card"><div class="editor"><div class="avatar"><img src="editor_sq.jpg" alt="" onerror="this.style.display='none'"></div><div class="grow"><div class="b">${esc(EDITOR.name)}</div><div class="small muted">${esc(EDITOR.role)} · ${esc(EDITOR.place)}</div>${compact ? '' : `<div class="small" style="margin-top:6px">${esc(EDITOR.bio)}</div>`}</div></div>
      ${compact ? '' : `<div class="tiny muted" style="margin-top:8px">Every selection published here is graded automatically against the final result — the record under Performance is the only opinion that counts. Statistical information, not betting advice. 18+.</div>`}</div>`;
  }
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

  return { native, settings, state, $, $$, saveSettings, nfetch, getJson, rawUrl, esc, pct, f1, f2, signed, DAYS, MONTHS, parseLocal, tzNow, ymd, stored, persist, cache, prefetchDetails, pubStamp,
    dayName, niceDate, koTime, koShort, toast, pill, bar, wdl, formBadges, md, GROUPS, GROUP_ICON, selGroup, selLabel, selShort, settleSel,
    liveVerdict, isLive, isFT, indexData, fx, loadDetail, detailCached, detailKey, loadData, statusLine, loadDay, dayRecord, finalFor, storedIncidents, loadTeams, teamsCached, slug, TABS, render, setTab, push, replace,
    back, openMatch, openTeam, toggleMenu, closeMenu, contactCard, editorCard, teamLink, matchLine, matchRow, segmented, select, scoreBox, statusIcon, CONTACT, APP_VERSION,
    confirmBox, isFav, toggleFav, favList: () => favs, saveFavs,
    icon, flag, badge, fxBadge, skeleton, ring, applyTheme, loadBadges, BADGE_BASE,
    views: {}, pages: {}, live: {} };
})();
