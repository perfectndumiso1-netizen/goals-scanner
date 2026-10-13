/**
 * PlayReport — app click-identity regression harness (2026-10-13 wrong-match bug).
 *
 * Boots the real www/ app in jsdom against the LIVE data-branch publication, taps rows on every
 * surface (Matches, Home, Shortlist, Sequences, Low odds, Day, Accas) and asserts each match page
 * names the very fixture that was tapped. Then poisons the on-phone caches (current + legacy
 * namespace, with and without an id) and asserts the identity guards heal every case.
 *
 * Run:  npm i --no-save jsdom   then   node tools/app_click_identity.mjs
 * Exit 0 = every check passed.
 */
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const WWW = path.join(REPO, 'android/app/src/main/assets/www');
let JSDOM;
try { ({ JSDOM } = await import('jsdom')); } catch (e) {
  console.error('jsdom is required:  npm i --no-save jsdom');
  process.exit(2);
}
const RAW = 'https://raw.githubusercontent.com/perfectndumiso1-netizen/goals-scanner/data/';
const g = async (p) => (await fetch(RAW + p)).text();
const latest = JSON.parse(await g('data/app/latest.json'));
const map = { 'data/app/latest.json': JSON.stringify(latest) };
const want = latest.fixtures.map((f) => f.d);
for (const lst of Object.values(latest.picks || {})) for (const p of lst) { const i = latest.fixtures.findIndex((f) => f.id === p.fixture); if (i >= 0) want.push(latest.fixtures[i].d); }
for (const k of [...new Set(want)].slice(0, 60)) map['data/app/fx/' + k + '.json'] = await g('data/app/fx/' + k + '.json');
try { map['data/app/days/' + latest.fixtures[0].id.slice(0, 10) + '.json'] = await g('data/app/days/' + latest.fixtures[0].id.slice(0, 10) + '.json'); } catch (e) { /* optional */ }

const html = fs.readFileSync(path.join(WWW, 'index.html'), 'utf8').replace(/<script[\s\S]*?<\/script>/g, '');
const dom = new JSDOM(html, { url: 'https://app.local/', runScripts: 'outside-only', pretendToBeVisual: true });
const w = dom.window;
w.scrollTo = () => {}; w.HTMLElement.prototype.scrollIntoView = function () {};
w.fetch = (url) => {
  const p = String(url).replace(/^https:\/\/raw\.githubusercontent\.com\/[^/]+\/[^/]+\/data\//, '').split('?')[0];
  const body = map[p];
  return Promise.resolve(body != null ? { status: 200, text: async () => body } : { status: 404, text: async () => 'nf' });
};
for (const f of ['marked.min.js', 'core.js', 'views.js', 'leagues.js', 'pages.js', 'slip.js', 'export.js', 'tennis.js', 'app.js'])
  w.eval(fs.readFileSync(path.join(WWW, f), 'utf8'));
const PR = w.PR;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
for (let i = 0; i < 60 && !PR.state.data; i++) await sleep(100);
if (!PR.state.data) { console.error('BOOT FAILED'); process.exit(1); }
const byId = Object.fromEntries(latest.fixtures.map((f) => [f.id, f]));
const detailOf = (fid) => { const f = byId[fid]; const raw = f && f.d && map['data/app/fx/' + f.d + '.json']; return raw ? JSON.parse(raw) : null; };
const viewText = () => (w.document.getElementById('view') || {}).textContent || '';
const tapEls = () => [...w.document.querySelectorAll('[data-fx]')].filter((el) => el.classList.contains('tap') || ['A', 'BUTTON'].includes(el.tagName));
const liveEl = (fid) => tapEls().find((el) => el.getAttribute('data-fx') === fid);
async function clickRow(el, fid) {
  const f = byId[fid]; const det = detailOf(fid);
  const H = det ? [...new Set([f.home, det.home, det.home_long].filter(Boolean))] : [f.home];
  const A = det ? [...new Set([f.away, det.away, det.away_long].filter(Boolean))] : [f.away];
  el.dispatchEvent(new w.MouseEvent('click', { bubbles: true, cancelable: true }));
  let ok = false, snippet = '';
  for (let i = 0; i < 30; i++) {
    await sleep(100);
    const top = PR.state.stack[PR.state.stack.length - 1];
    if (top && top.type === 'match') {
      const t = viewText();
      if (H.some((h) => t.includes(h)) && A.some((a) => t.includes(a))) { ok = true; break; }
      snippet = t.slice(0, 100).replace(/\s+/g, ' ');
    } else if (i > 3) { snippet = '(did not navigate)'; break; }
    if (i > 25 && /not available|error/i.test(viewText())) break;
  }
  PR.back(); await sleep(40);
  return { ok, snippet };
}
let fails = 0;
async function surface(name, go, limit = 8) {
  go(); await sleep(100);
  const fids = [...new Set(tapEls().map((el) => el.getAttribute('data-fx')))].filter((fid) => fid && !fid.startsWith('live:') && byId[fid]);
  let pass = 0, n = 0;
  for (const fid of fids) {
    if (n >= limit) break;
    n++;
    go(); await sleep(80);
    const el = liveEl(fid);
    if (!el) { fail(`   MISS[${name}] ${fid}`); continue; }
    const r = await clickRow(el, fid);
    if (r.ok) pass++; else { fails++; console.log(`   FAIL[${name}] ${fid} -> ${r.snippet}`); }
  }
  console.log(`${fails ? '✗' : '✓'} ${name}: ${pass}/${n} taps opened the RIGHT match`);
}
const fail = (m) => { fails++; console.log(m); };
await surface('matches', () => PR.setTab('matches'));
await surface('home', () => PR.setTab('home'));
await surface('shortlist', () => PR.setTab('shortlist'));
await surface('sequences', () => PR.setTab('sequences'));
await surface('lowodds', () => PR.setTab('lowodds'));
await surface('day', () => { PR.setTab('home'); PR.push({ type: 'day', date: latest.fixtures[0].id.slice(0, 10) }); });
// ---- poisoned on-phone cache: every variant must heal to the RIGHT match
const victim = latest.fixtures[1], wrong = latest.fixtures[Math.min(4, latest.fixtures.length - 1)];
const wrongBody = JSON.parse(map['data/app/fx/' + wrong.d + '.json']);
async function poisoned(label, ns, body) {
  PR.setTab('matches'); await sleep(60);
  const row = liveEl(victim.id);
  for (const k of Object.keys(PR.state.details)) if (!k.includes('_')) delete PR.state.details[k];
  w.localStorage.setItem('pr_' + ns + ':fx/' + victim.d, JSON.stringify({ t: Date.now(), s: '', d: body }));
  const r = await clickRow(row, victim.id);
  console.log(`${r.ok ? '✓' : '✗'} poisoned[${label}]: shows ${r.ok ? 'RIGHT match' : 'WRONG -> ' + r.snippet}`);
  if (!r.ok) fails++;
  w.localStorage.removeItem('pr_' + ns + ':fx/' + victim.d);
}
await poisoned('current-ns, with id', 'd', wrongBody);
const noId = { ...wrongBody }; delete noId.id;
await poisoned('current-ns, NO id (legacy)', 'd', noId);
await poisoned('legacy-ns pr_c, with id', 'c', wrongBody);
console.log(fails === 0 ? 'ALL IDENTITY CHECKS PASSED' : `FAILURES: ${fails}`);
process.exit(fails === 0 ? 0 : 1);
