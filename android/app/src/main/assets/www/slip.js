/* PlayReport — bet slip and tickets (kept on the phone; graded automatically from scores and match statistics). */
(function (PR) {
  'use strict';
  const { $, $$, esc, pct, f2, state, settings, fx, koShort, koTime, dayName, toast, selLabel, selGroup, settleSel, liveVerdict, isLive, isFT, icon, flag, badge, contactCard, parseLocal, tzNow, ymd } = PR;
  const view = () => $('#view');
  const head = (title, sub) => `<div class="detail-head"><button class="back" id="back" aria-label="Back">${icon('back')}</button><div class="grow"><div class="b">${title}</div>${sub ? `<div class="tiny muted">${sub}</div>` : ''}</div></div>`;
  const line = (code) => parseInt(code.replace(/\D/g, ''), 10) / 10;
  const load = (k, d) => { try { return JSON.parse(PR.stored(k)) || d; } catch (e) { return d; } };
  const slip = { items: load('pr_slip', { items: [] }).items || [], stake: load('pr_slip', {}).stake || '' };
  let tickets = load('pr_tickets_full', null);
  if (!tickets) { try { tickets = JSON.parse(localStorage.getItem('pr_tickets')) || []; } catch (e) { tickets = []; } }   // pre-1.4 key
  const saveSlip = () => PR.persist('pr_slip', JSON.stringify(slip));
  function saveTickets() {
    localStorage.setItem('pr_tickets', JSON.stringify(tickets));
    PR.persist('pr_tickets_full', JSON.stringify(tickets));
    if (PR.native && PR.native.setString) { try { PR.native.setString('tickets', JSON.stringify(tickets.filter((t) => t.status === 'pending').map((t) => ({ id: t.id, odds: t.odds, stake: t.stake, legs: t.legs.map((l) => ({ eid: l.eid, sel: l.sel, home: l.home, away: l.away, kickoff: l.kickoff, label: l.label })) })))); } catch (e) { /* ignore */ } }
  }
  const totalOdds = (legs) => legs.reduce((a, l) => a * (l.status === 'void' ? 1 : (l.odds || 1)), 1);

  // ------------------------------------------------------------------ slip
  function leg(f, s) {
    return { fixture: f.id, d: f.d || null, eid: f.livescore_id || null, home: f.home, away: f.away, kickoff: f.kickoff, competition: f.competition, country: f.country,
      badges: f.badges || null, sel: s.sel, label: selLabel(s.sel, f.home, f.away), odds: +s.odds, p: s.p };
  }
  PR.inSlip = (fid, sel) => slip.items.some((l) => l.fixture === fid && l.sel === sel);
  PR.slipToggle = function (fid, sel) {
    const f = fx(fid); if (!f) { toast('This match is no longer in the current analysis'); return; }
    const i = slip.items.findIndex((l) => l.fixture === fid && l.sel === sel);
    if (i >= 0) { slip.items.splice(i, 1); saveSlip(); bar(); PR.render(); return; }
    let s = null;
    const det = PR.detailCached(fid); if (det && det.sels) s = det.sels.find((x) => x.sel === sel);
    if (!s) { const b = ((state.data.safe || {}).bets || []).find((x) => x.fixture === fid && x.sel === sel); if (b) s = { sel: b.sel, odds: b.odds, p: b.p }; }
    if (!s) { const h = (f.hi || []).find((x) => x[0] === sel); if (h) s = { sel: h[0], p: h[1], odds: h[2] }; }
    if (!s && f.top && f.top[0] === sel) s = { sel: f.top[0], p: f.top[1], odds: f.top[2] };
    if (!s || !s.odds) { toast('No Sportybet price for this selection'); return; }
    const ko = parseLocal(f.kickoff); if (ko && ko < tzNow()) { toast('This match has already started'); return; }
    const same = slip.items.findIndex((l) => l.fixture === fid);
    if (same >= 0) { const old = slip.items[same]; slip.items.splice(same, 1); toast(`Replaced ${old.label}`); }
    slip.items.push(leg(f, s)); saveSlip(); bar(); PR.render();
    if (slip.items.length === 1 && same < 0) toast('Added to your slip — tap the slip bar when you are done');
  };
  /** small add / added button for any priced selection */
  PR.addBtn = function (fid, sel, odds) {
    if (!odds) return '';
    const f = fx(fid); const ko = f && parseLocal(f.kickoff); const started = ko && ko < tzNow();
    if (started) return '';
    const on = PR.inSlip(fid, sel);
    return `<button class="addsel ${on ? 'on' : ''}" data-add-fx="${esc(fid)}" data-add-sel="${esc(sel)}" title="${on ? 'Remove from slip' : 'Add to slip'}" aria-label="Add to slip">${on ? icon('check') : '+'}</button>`;
  };
  document.addEventListener('click', (e) => {
    const b = e.target.closest('[data-add-fx]'); if (!b) return;
    e.preventDefault(); e.stopPropagation(); PR.slipToggle(b.dataset.addFx, b.dataset.addSel);
  }, true);
  function bar() {
    const el = $('#slipbar'); if (!el) return;
    if (!slip.items.length) { el.classList.remove('show'); el.innerHTML = ''; document.body.classList.remove('has-slip'); return; }
    document.body.classList.add('has-slip');
    el.innerHTML = `<button class="slipbtn" id="slip-open"><span class="cnt">${slip.items.length}</span><span class="grow"><b>Bet slip</b> · ${slip.items.length} selection${slip.items.length > 1 ? 's' : ''} · odds <b>${f2(totalOdds(slip.items))}</b></span><span class="tiny">Done ${icon('next', 'sm')}</span></button>`;
    el.classList.add('show');
    $('#slip-open').onclick = () => { state.stack = []; PR.push({ type: 'slip' }); };
  }
  PR.slipBar = bar;

  PR.pages.slip = function () {
    const parts = [head('Bet slip', slip.items.length ? `${slip.items.length} selection${slip.items.length > 1 ? 's' : ''}` : 'empty')];
    if (!slip.items.length) {
      parts.push(`<div class="card empty">Your slip is empty.<br><span class="small muted">Tap <b>+</b> next to any priced selection (match page › Markets, safest bets, bets of the day) to add it.</span></div>`);
      if (tickets.length) parts.push(`<div class="card compact tap" id="go-tickets"><div class="row"><span class="ico">${icon('ticket')}</span><div class="grow b">My tickets (${tickets.length})</div>${icon('next')}</div></div>`);
    } else {
      const odds = totalOdds(slip.items); const stake = parseFloat(slip.stake) || 0;
      parts.push(`<div class="card compact"><table class="tbl">${slip.items.map((l, i) => `<tr><td class="tiny muted nowrap">${esc(koShort(l.kickoff))}</td><td><div class="row" style="gap:6px">${badge(l.home, l.badges && l.badges.home, 20)}${badge(l.away, l.badges && l.badges.away, 20)}<div class="b grow">${esc(l.home)} <span class="muted">v</span> ${esc(l.away)}</div></div><div class="sel"><b>${esc(l.label)}</b></div><div class="tiny muted">${flag(l.country)} ${esc(l.competition)} · ${pct(l.p)}</div></td><td class="right nowrap"><b>${f2(l.odds)}</b></td><td class="right"><button class="link" data-rm="${i}" aria-label="Remove">${icon('x')}</button></td></tr>`).join('')}</table></div>`);
      parts.push(`<div class="card"><div class="row"><div class="grow"><div class="k tiny muted">Total odds</div><div class="v" style="font-size:24px;font-weight:800">${f2(odds)}</div></div><div class="grow"><label class="tiny muted">Stake (optional)</label><input id="slip-stake" type="number" inputmode="decimal" placeholder="e.g. 50" value="${esc(slip.stake)}"></div></div>
        ${stake ? `<div class="small" style="margin-top:8px">Potential return <b>${f2(stake * odds)}</b> · profit ${f2(stake * odds - stake)}</div>` : ''}
        <div class="tiny muted" style="margin-top:8px">Model probability that every leg wins: <b>${pct(slip.items.reduce((a, l) => a * (l.p || 0), 1))}</b> (fair odds ${f2(1 / Math.max(1e-6, slip.items.reduce((a, l) => a * (l.p || 0), 1)))}). Prices are the Sportybet prices at the last analysis — check them before you bet.</div>
        <div class="row" style="margin-top:12px;gap:8px"><button class="btn primary grow" id="slip-place">${icon('lock', 'sm')} Done — lock this ticket</button><button class="btn" id="slip-clear">Clear</button></div>
        <div class="tiny muted" style="margin-top:6px">A locked ticket cannot be edited. PlayReport follows the scores and tells you when it is won or lost. This records your bet — it does not place it anywhere.</div></div>`);
      if (tickets.length) parts.push(`<div class="card compact tap" id="go-tickets"><div class="row"><span class="ico">${icon('ticket')}</span><div class="grow b">My tickets (${tickets.length})</div>${icon('next')}</div></div>`);
    }
    view().innerHTML = parts.join('');
    $('#back').onclick = () => PR.back();
    $$('[data-rm]').forEach((b) => { b.onclick = () => { slip.items.splice(+b.dataset.rm, 1); saveSlip(); bar(); PR.render(); }; });
    const st = $('#slip-stake'); if (st) st.oninput = (e) => { slip.stake = e.target.value; saveSlip(); };
    const g = $('#go-tickets'); if (g) g.onclick = () => PR.push({ type: 'tickets' });
    const c = $('#slip-clear'); if (c) c.onclick = () => { slip.items = []; saveSlip(); bar(); PR.render(); };
    const p = $('#slip-place'); if (p) p.onclick = async () => {
      const ok = await PR.confirmBox('Lock this ticket?', `${slip.items.length} selection${slip.items.length > 1 ? 's' : ''} · total odds ${f2(totalOdds(slip.items))}${slip.stake ? ` · stake ${slip.stake}` : ''}\n\nA locked ticket cannot be edited. It goes to Bets › Today and ☰ › My tickets, and is graded from the scores.`, 'Lock ticket');
      if (!ok) return;
      const t = { id: 'T' + Date.now().toString(36).toUpperCase(), created: tzNow().toISOString().slice(0, 16).replace('T', ' '), legs: slip.items.map((l) => Object.assign({ status: 'pending' }, l)), odds: +totalOdds(slip.items).toFixed(2), stake: parseFloat(slip.stake) || null, status: 'pending' };
      tickets.unshift(t); slip.items = []; slip.stake = ''; saveSlip(); saveTickets(); bar();
      toast('Ticket locked — good luck!'); state.stack = []; state.betsView = 'today'; PR.setTab('bets');
    };
  };

  // ------------------------------------------------------------------ settlement
  function scoreFor(l) {
    // live feed while the match is on, the published day file (final score + match statistics) afterwards
    const s = l.eid && state.live[l.eid];
    const day = state.days[l.kickoff.slice(0, 10)];
    const df = day && day.fixtures ? day.fixtures.find((x) => x.id === l.fixture) : null;
    const sc = df && df.score;
    if (s && s.hg != null && isLive(s)) return { hg: s.hg, ag: s.ag, status: s.status, live: true, ft: false };
    if (sc) return { hg: sc.hg, ag: sc.ag, status: sc.status, live: false, ft: sc.hg != null, hc: sc.hc, ac: sc.ac, hcards: sc.hcards, acards: sc.acards, postponed: sc.hg == null };
    if (s && s.hg != null) return { hg: s.hg, ag: s.ag, status: s.status, live: false, ft: isFT(s) };
    return null;
  }
  function settleLeg(l, sc) {
    if (!sc) return 'pending';
    if (sc.postponed) return 'void';
    if (!sc.ft) return 'pending';
    const g = selGroup(l.sel);
    if (g === 'corners' || g === 'cards') {
      const tot = g === 'corners' ? (sc.hc != null && sc.ac != null ? sc.hc + sc.ac : null) : (sc.hcards != null && sc.acards != null ? sc.hcards + sc.acards : null);
      if (tot == null) return 'pending';
      return (l.sel[1] === 'O' ? tot > line(l.sel) : tot < line(l.sel)) ? 'won' : 'lost';
    }
    const ok = settleSel(l.sel, sc.hg, sc.ag);
    return ok == null ? 'pending' : ok ? 'won' : 'lost';
  }
  function legLive(l, sc) {
    if (!sc) return { cls: '', text: 'not started' };
    if (l.status === 'won') return { cls: 'good', text: '✅ won' }; if (l.status === 'lost') return { cls: 'bad', text: '❌ lost' }; if (l.status === 'void') return { cls: '', text: 'void' };
    if (selGroup(l.sel) === 'corners' || selGroup(l.sel) === 'cards') return { cls: sc.ft ? '' : 'warn', text: sc.ft ? 'waiting for match stats' : 'in play' };
    return liveVerdict(l.sel, { status: sc.live ? sc.status : sc.ft ? 'FT' : 'NS', hg: sc.hg, ag: sc.ag });
  }
  PR.settleTickets = function (announce) {
    let changed = false; const now = tzNow();
    tickets.forEach((t) => {
      if (t.status !== 'pending') return;
      t.legs.forEach((l) => { if (l.status === 'pending') { const st = settleLeg(l, scoreFor(l)); if (st !== l.status) { l.status = st; changed = true; } } });
      const sts = t.legs.map((l) => l.status);
      let status = 'pending';
      if (sts.includes('lost')) status = 'lost';
      else if (sts.every((s) => s === 'won' || s === 'void')) status = sts.every((s) => s === 'void') ? 'void' : 'won';
      if (status !== 'pending') {
        t.status = status; t.settled = now.toISOString().slice(0, 16).replace('T', ' '); t.final_odds = +totalOdds(t.legs).toFixed(2); changed = true;
        if (announce !== false) {
          const title = status === 'won' ? `🎉 Ticket won · odds ${f2(t.final_odds)}` : status === 'lost' ? '❌ Ticket lost' : 'Ticket void';
          const text = t.legs.map((l) => `${l.status === 'won' ? '✅' : l.status === 'lost' ? '❌' : '∅'} ${l.label} (${l.home} v ${l.away})`).join('\n') + (t.stake && status === 'won' ? `\nReturn ${f2(t.stake * t.final_odds)}` : '');
          if (PR.native && PR.native.notify) { try { PR.native.notify('bets', 3000 + (t.id.split('').reduce((a, c) => a + c.charCodeAt(0), 0) % 1000), title, text, 'bets'); } catch (e) { /* ignore */ } }
          toast(title);
        }
      }
    });
    if (changed) saveTickets();
    return changed;
  };
  /** make sure the day files needed to grade pending legs are loaded, then settle */
  PR.reconcileTickets = async function () {
    const need = new Set(); const today = ymd(tzNow());
    tickets.forEach((t) => { if (t.status === 'pending') t.legs.forEach((l) => { if (l.status === 'pending' && l.kickoff.slice(0, 10) <= today && !(state.days[l.kickoff.slice(0, 10)] && state.days[l.kickoff.slice(0, 10)].fixtures)) need.add(l.kickoff.slice(0, 10)); }); });
    for (const d of need) { try { await PR.loadDay(d); } catch (e) { /* not published yet */ } }
    // refresh stale day files (stats arrive a few hours after full time)
    if (PR.settleTickets(true)) { const top = state.stack[state.stack.length - 1]; if (top && (top.type === 'tickets' || top.type === 'ticket')) PR.render(); }
  };
  PR.ticketFixtures = () => { const out = new Set(); tickets.forEach((t) => { if (t.status === 'pending') t.legs.forEach((l) => out.add(l.fixture)); }); return out; };

  // ------------------------------------------------------------------ tickets pages
  const stChip = (st) => `<span class="chip ${st === 'won' ? 'good' : st === 'lost' ? 'bad' : st === 'void' ? '' : 'warn'}">${st === 'won' ? '✅ won' : st === 'lost' ? '❌ lost' : st === 'void' ? 'void' : '⏳ pending'}</span>`;
  PR.pages.tickets = function () {
    PR.settleTickets();
    const settled = tickets.filter((t) => t.status === 'won' || t.status === 'lost');
    const won = settled.filter((t) => t.status === 'won');
    const staked = settled.reduce((a, t) => a + (t.stake || 0), 0); const ret = won.reduce((a, t) => a + (t.stake || 0) * (t.final_odds || t.odds), 0);
    const parts = [head('My tickets', tickets.length ? `${tickets.length} ticket${tickets.length > 1 ? 's' : ''} · ${won.length}/${settled.length} won` : 'no tickets yet')];
    if (settled.length) parts.push(`<div class="card"><div class="grid4"><div class="cell"><div class="k">Won</div><div class="v">${won.length}/${settled.length}</div><div class="tiny muted">${pct(won.length / settled.length)}</div></div><div class="cell"><div class="k">Pending</div><div class="v">${tickets.filter((t) => t.status === 'pending').length}</div></div>${staked ? `<div class="cell"><div class="k">Staked</div><div class="v">${f2(staked)}</div></div><div class="cell"><div class="k">Profit</div><div class="v ${ret - staked >= 0 ? 'good' : 'bad'}">${(ret - staked >= 0 ? '+' : '') + f2(ret - staked)}</div><div class="tiny muted">return ${f2(ret)}</div></div>` : ''}</div></div>`);
    if (!tickets.length) parts.push(`<div class="card empty">No tickets yet.<br><span class="small muted">Build a slip with the <b>+</b> buttons next to priced selections, then tap Done to lock it.</span></div>`);
    else parts.push(`<div class="card compact">${tickets.map((t) => `<div class="list-item tap" data-ticket="${esc(t.id)}"><div class="main"><div class="match">${stChip(t.status)} <b>${f2(t.final_odds || t.odds)}</b> <span class="muted small">· ${t.legs.length} leg${t.legs.length > 1 ? 's' : ''}${t.stake ? ` · stake ${f2(t.stake)}` : ''}</span></div><div class="meta">${t.legs.slice(0, 3).map((l) => `${esc(l.label)} (${esc(l.home)} v ${esc(l.away)})`).join(' · ')}${t.legs.length > 3 ? ' …' : ''}</div><div class="tiny muted">${esc(t.created)} · ${esc(t.id)}</div></div><div class="chev">${icon('next')}</div></div>`).join('')}</div>`);
    parts.push(`<div class="note">Tickets live only on this phone. Goals markets settle from the final score; corners and cards settle from the match statistics, which arrive a few hours after full time. Statistical record, not betting advice.</div>`);
    view().innerHTML = parts.join('');
    $('#back').onclick = () => PR.back();
    $$('[data-ticket]').forEach((b) => { b.onclick = () => PR.push({ type: 'ticket', id: b.dataset.ticket }); });
    PR.reconcileTickets();
  };
  PR.pages.ticket = function (page) {
    PR.settleTickets();
    const t = tickets.find((x) => x.id === page.id);
    if (!t) { PR.back(); return; }
    const parts = [head(`Ticket ${esc(t.id)}`, `${esc(t.created)} · ${t.legs.length} leg${t.legs.length > 1 ? 's' : ''}`)];
    parts.push(`<div class="card"><div class="row"><div class="grow"><div class="k tiny muted">Total odds</div><div class="v" style="font-size:24px;font-weight:800">${f2(t.final_odds || t.odds)}</div></div>${stChip(t.status)}</div>
      ${t.stake ? `<div class="small" style="margin-top:6px">Stake ${f2(t.stake)} · ${t.status === 'won' ? `<b class="good">return ${f2(t.stake * (t.final_odds || t.odds))}</b>` : t.status === 'lost' ? '<b class="bad">lost</b>' : `potential return ${f2(t.stake * t.odds)}`}</div>` : ''}
      ${t.settled ? `<div class="tiny muted">Settled ${esc(t.settled)}</div>` : '<div class="tiny muted">Locked — follows the live scores automatically.</div>'}</div>`);
    parts.push(`<div class="card compact"><table class="tbl">${t.legs.map((l) => { const sc = scoreFor(l); const v = legLive(l, sc); const f = fx(l.fixture);
      return `<tr ${f ? `class="tap" data-fx="${esc(l.fixture)}"` : ''}><td class="tiny muted nowrap">${esc(koShort(l.kickoff))}</td><td><div class="row" style="gap:6px">${badge(l.home, l.badges && l.badges.home, 20)}${badge(l.away, l.badges && l.badges.away, 20)}<div class="b grow">${esc(l.home)} <span class="muted">v</span> ${esc(l.away)}</div></div><div class="sel"><b>${esc(l.label)}</b></div><div class="tiny"><span class="${v.cls}">${esc(v.text)}</span>${sc && sc.hg != null ? ` · <b>${sc.hg}–${sc.ag}</b>${sc.live ? ' ' + esc(sc.status) : sc.ft ? ' FT' : ''}` : ''}</div></td><td class="right nowrap"><b>${f2(l.odds)}</b></td></tr>`; }).join('')}</table></div>`);
    view().innerHTML = parts.join('');
    $('#back').onclick = () => PR.back();
    PR.reconcileTickets();
  };
  PR.tickets = () => tickets;
  PR.ticketsCard = function (onlyOpen) {
    PR.settleTickets();
    const today = ymd(tzNow());
    const lst = tickets.filter((t) => t.status === 'pending' || (t.settled || '').slice(0, 10) === today || t.created.slice(0, 10) === today);
    const shown = onlyOpen ? lst.filter((t) => t.status === 'pending') : lst;
    const headRow = `<div class="section-head"><h2><span class="ico amber">${icon('ticket')}</span>My tickets</h2><button class="link" id="tk-all">All tickets ${icon('next')}</button></div>`;
    if (!shown.length) return headRow + `<div class="card empty small">No open ticket. Tap <b>+</b> next to any priced selection to start a slip, then press Done.</div>`;
    return headRow + `<div class="card compact">${shown.map((t) => `<div class="list-item tap" data-ticket="${esc(t.id)}"><div class="main"><div class="match">${stChip(t.status)} <b>odds ${f2(t.final_odds || t.odds)}</b>${t.stake ? ` <span class="muted small">· stake ${f2(t.stake)} → ${f2(t.stake * (t.final_odds || t.odds))}</span>` : ''}</div>
      ${t.legs.map((l) => { const sc = scoreFor(l); const v = legLive(l, sc); return `<div class="small"><span class="${v.cls}">${l.status === 'won' ? '✅' : l.status === 'lost' ? '❌' : sc && sc.live ? '🔴' : '•'}</span> ${esc(l.label)} <span class="muted">(${esc(l.home)} v ${esc(l.away)}${sc && sc.hg != null ? ` ${sc.hg}–${sc.ag}` : ` ${esc(koShort(l.kickoff))}`})</span></div>`; }).join('')}</div><div class="chev">${icon('next')}</div></div>`).join('')}</div>`;
  };
  PR.wireTickets = function () {
    $$('[data-ticket]').forEach((b) => { b.onclick = () => PR.push({ type: 'ticket', id: b.dataset.ticket }); });
    const a = $('#tk-all'); if (a) a.onclick = () => PR.push({ type: 'tickets' });
  };
  bar();
  if (PR.native && PR.native.setString) saveTickets();
})(window.PR);
