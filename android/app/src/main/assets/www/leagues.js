/* PlayReport — Leagues tab: worldwide football league tables, previous results and fixtures.
   Data: data/app/leagues/index.json + one detail file per competition, published from the public
   feed's stage archive on every scan. Read-only for the app; cached on the phone like every other
   data file, refreshed in the background when the publication is newer. */
(function (PR) {
  'use strict';
  const { $, $$, esc, state, toast, segmented, select, icon, flag, badge, skeleton, parseLocal, niceDate, koTime, dayName, koShort, getJson, rawUrl, formBadges, wdl } = PR;
  const view = () => $('#view');
  const head = (title, sub, right) => `<div class="detail-head"><button class="back" id="back" aria-label="Back">${icon('back')}</button><div class="grow"><div class="b">${title}</div>${sub ? `<div class="tiny muted">${sub}</div>` : ''}</div>${right || ''}</div>`;
  function wireBack() { const b = $('#back'); if (b) b.onclick = () => PR.back(); }
  const LG = state.lg = state.lg || { idx: null, idxStale: false, loading: false, error: null, det: {} };
  state.lgSeg = state.lgSeg || 'table';
  state.lgQ = state.lgQ || '';

  // ------------------------------------------------------------------ data (on-phone cache first, network second)
  async function loadIndex(force) {
    if (LG.idx && !force) return LG.idx;
    if (LG.loading) return LG.idx;
    LG.loading = true; LG.error = null;
    try {
      const j = await getJson(rawUrl('data/app/leagues/index.json') + '?t=' + Math.floor(Date.now() / 600000));
      PR.cache.put('leag/idx', j, j.generated || '');
      LG.idx = j; LG.idxStale = false;
    } catch (e) {
      const c = PR.cache.get('leag/idx');
      if (c && c.d) { LG.idx = c.d; LG.idxStale = true; }
      else { LG.error = e.message; }
    } finally { LG.loading = false; }
    return LG.idx;
  }
  function detailCached(slug) { return LG.det[slug] || null; }
  async function loadDetail(slug) {
    const c = PR.cache.get('leag/' + slug);
    const fetchIt = async () => {
      const j = await getJson(rawUrl('data/app/leagues/' + slug) + '?t=' + Math.floor(Date.now() / 600000));
      LG.det[slug] = j; PR.cache.put('leag/' + slug, j, j.generated || ''); return j;
    };
    if (c && c.d) {
      LG.det[slug] = c.d;
      if (c.s !== (LG.idx && LG.idx.generated) && Date.now() - c.t > 10 * 60000) fetchIt().catch(() => { /* keep cache */ });
      return c.d;
    }
    return fetchIt();
  }
  function ensureDetail(slug) {
    if (detailCached(slug)) return;
    loadDetail(slug).then(() => PR.render()).catch((e) => { LG.det[slug] = { error: e.message }; PR.render(); });
  }
  const fetchStamp = (s) => { const d = parseLocal(s); return d ? `${niceDate(s)} · ${koTime(s)}` : (s || 'unknown'); };

  // ------------------------------------------------------------------ TAB: league browser
  PR.views.leagues = function () {
    const parts = [];
    const sum = LG.idx && LG.idx.summary;
    parts.push(`<div class="lg-head"><div class="grow"><div class="b">${icon('trophy', 'sm')} Leagues</div><div class="tiny muted">Tables, results &amp; fixtures — every competition on the public feed</div></div>
      ${LG.idx ? `<span class="tiny muted">${LG.idx.count} competitions · ${new Set((LG.idx.leagues || []).map((x) => x.country)).size} countries${LG.idxStale ? ' · saved copy' : ''}</span>` : ''}</div>`);
    if (sum) parts.push(`<div class="tiny muted" style="margin:2px 4px 0">Data collection: <b>${sum.active}</b> active · <b>${sum.eligible}</b> model-eligible${sum.collecting ? ` · <b>${sum.collecting}</b> still collecting stats` : ''}${sum.no_stats ? ` · <b>${sum.no_stats}</b> where the provider publishes no stats (corners/cards N/A)` : ''}${sum.data_error ? ` · ${sum.data_error} data error${sum.data_error === 1 ? '' : 's'}` : ''}. One bad league never stops the worldwide scan.</div>`);
    parts.push(`<div class="searchbar"><div class="field">${icon('search', 'sm')}<input id="lg-search" type="search" placeholder="Search a league, country or team" value="${esc(state.lgQ)}" autocomplete="off"></div></div>`);
    parts.push(`<div class="row" style="padding:0 4px 6px;gap:8px"><div class="grow tiny muted">${LG.idx ? `${LG.idx.count} competitions` : ''} · tap a league to open it</div>${select('lg-sort', [['country', 'Sort: Country'], ['name', 'Sort: Name'], ['next', 'Sort: Next fixture'], ['played', 'Sort: Most played'], ['teams', 'Sort: Most teams']], state.lgSort || 'country')}</div>`);
    if (!LG.idx) {
      if (!LG.loading) { state.lgQ = ''; parts.push(LG.error ? `<div class="card empty">Could not load the league data (${esc(LG.error)}).<br><button class="btn" id="lg-retry">Try again</button></div>` : skeleton(8)); }
      else parts.push(skeleton(8));
      view().innerHTML = parts.join('');
      const s = $('#lg-search'); if (s) s.oninput = (e) => { state.lgQ = e.target.value; PR.render(); s.focus(); };
      const r = $('#lg-retry'); if (r) r.onclick = () => loadIndex(true).then(() => PR.render());
      if (!LG.loading) loadIndex(true).then(() => PR.render());
      return;
    }
    const q = (state.lgQ || '').trim().toLowerCase();
    const sort = state.lgSort || 'country';
    let rows = (LG.idx.leagues || []).filter((x) => !q || (x.league || '').toLowerCase().includes(q) || (x.country || '').toLowerCase().includes(q));
    if (!rows.length) parts.push(`<div class="card empty small">No league matches “${esc(state.lgQ)}”.</div>`);
    const rowCard = (x, showCountry) => `<div class="lg-row tap" data-lg="${esc(x.slug)}"><div class="lg-ic">${x.table ? icon('trophy') : flag(x.country)}</div>
      <div class="grow"><div class="b">${showCountry ? `${flag(x.country)} ` : ''}${esc(x.league)}</div><div class="tiny muted">${showCountry ? (x.country || '') : ''}${showCountry && x.teams ? ' · ' : ''}${x.teams ? `${x.teams} teams` : ''}${x.played ? ` · ${x.played} played` : ''}${x.season ? ` · ${x.season}` : ''}</div></div>
      <div class="lg-right">${x.next ? `<div class="tiny muted">next</div><div class="b" style="font-size:13px">${esc(koShort(x.next))}</div>` : ''}</div></div>`;
    if (sort === 'country') {
      let lastCountry = null;
      rows.forEach((x) => {
        if (x.country !== lastCountry) {
          if (lastCountry !== null) parts.push('</div>');
          parts.push(`<div class="card compact"><div class="comp-head">${flag(x.country)} ${esc(x.country || 'Other')}</div>`);
          lastCountry = x.country;
        }
        parts.push(rowCard(x, false));
      });
      if (lastCountry !== null) parts.push('</div>');
    } else {
      const srt = rows.slice().sort((a, b) =>
        sort === 'name' ? (a.league || '').localeCompare(b.league || '') :
        sort === 'next' ? String(a.next || '9999-12-31').localeCompare(String(b.next || '9999-12-31')) :
        sort === 'played' ? (b.played || 0) - (a.played || 0) || (a.league || '').localeCompare(b.league || '') :
        (b.teams || 0) - (a.teams || 0) || (a.league || '').localeCompare(b.league || ''));
      parts.push(`<div class="card compact">${srt.map((x) => rowCard(x, true)).join('')}</div>`);
    }
    // team search: the query matches clubs worldwide (not just leagues)
    if (q) {
      if (!state.teamIdx) PR.loadTeamIndex().then((j) => { if (j) PR.render(); });
      const tIdx = state.teamIdx;
      const hits = tIdx ? (tIdx.teams || []).filter((t) => (t.n || '').toLowerCase().includes(q)).slice(0, 12) : [];
      if (hits.length) {
        parts.push(`<div class="card compact"><div class="comp-head">Teams (${hits.length}${tIdx && hits.length >= 12 ? '+' : ''})</div>${hits.map((t) => `<div class="lg-row tap" data-lgtm="${esc(t.n)}|${esc(t.c)}|${esc(t.d)}"><div class="lg-ic">${badge(t.n, null, 24)}</div><div class="grow"><div class="b">${esc(t.n)}</div><div class="tiny muted">${flag(t.c)} ${esc(t.c || '')} · ${esc(t.l || '')}</div></div></div>`).join('')}</div>`);
      } else if (tIdx && !rows.length) parts.push(`<div class="card empty small">No club matches “${esc(state.lgQ)}” either.</div>`);
    }
    parts.push(`<div class="tiny muted" style="margin:10px 4px 18px">Updated every 30 minutes from the public live-score archive · ${LG.idx.count} competitions · season history accumulates each matchday.</div>`);
    view().innerHTML = parts.join('');
    const s = $('#lg-search'); if (s) { s.oninput = (e) => { state.lgQ = e.target.value; PR.render(); const n = $('#lg-search'); if (n) { n.focus(); n.setSelectionRange(n.value.length, n.value.length); } }; }
    const so = $('#lg-sort'); if (so) so.onchange = (e) => { state.lgSort = e.target.value; PR.render(); };
    $$('#view [data-lg]').forEach((el) => { el.onclick = () => openLeague(el.dataset.lg); });
    $$('[data-lgtm]').forEach((el) => { el.onclick = () => { const p = el.dataset.lgtm.split('|'); PR.openTeam(p.slice(0, -2).join('|'), p[p.length - 2], p[p.length - 1]); }; });
  };

  // ------------------------------------------------------------------ PAGE: one league
  function openLeague(slug) {
    state.lgSeg = 'table';
    PR.push({ type: 'league', slug });
  }
  PR.openLeague = openLeague;
  PR.pages.league = function (page) {
    const d = detailCached(page.slug);
    const idxRow = (LG.idx && (LG.idx.leagues || []).find((x) => x.slug === page.slug)) || null;
    const parts = [head(
      esc(idxRow ? idxRow.league : (d ? d.league : 'League')),
      `${flag(idxRow ? idxRow.country : (d && d.country))} ${esc((idxRow && idxRow.country) || (d && d.country) || '')}${idxRow && idxRow.season ? ` · ${esc(idxRow.season)}` : ''} · ${(idxRow && idxRow.teams) || (d && d.teams) || '–'} teams · ${(idxRow && idxRow.played) || (d && d.played) || '–'} played`,
      `<span class="tiny muted">updated ${esc(fetchStamp((idxRow && idxRow.fetched) || (d && d.fetched)))}</span>`
    )];
    if (!d) {
      ensureDetail(page.slug);
      parts.push(skeleton(8));
      view().innerHTML = parts.join(''); wireBack(); return;
    }
    if (d.error) { parts.push(`<div class="card empty">Could not load this league (${esc(d.error)}).<br><button class="btn" id="lg-retry">Try again</button></div>`); view().innerHTML = parts.join(''); wireBack(); return; }
    // data-quality status from the coverage registry (the scanner's machine-readable registry)
    const st = d.status || (idxRow && idxRow.status);
    const sq = (idxRow && idxRow.stats) || d.stats || null;
    const reason = d.status_reason || '';
    if (st) {
      const cls = st === 'ACTIVE' ? 'good' : (st === 'FINISHED' ? '' : 'warn');
      const label = { ACTIVE: 'active', UPCOMING: 'upcoming', FINISHED: 'finished', DATA_ERROR: 'data error' }[st] || st;
      let statsChip = '';
      if (sq) {
        if (sq.publishes === false) statsChip = '<span class="chip warn">provider publishes no stats</span>';
        else if (sq.total == null) statsChip = '<span class="chip">no stats window yet</span>';
        else if (sq.pct >= 0.99) statsChip = `<span class="chip good">stats ${sq.n}/${sq.total} · up to date</span>`;
        else statsChip = `<span class="chip">stats ${sq.n}/${sq.total} (${Math.round(sq.pct * 100)}%) · collecting</span>`;
      }
      const earlier = (idxRow && idxRow.earlier) || d.earlier || {};
      const earlierTxt = Object.entries(earlier).slice(0, 2).map(([s, n]) => `${n} from ${s}`).join(' · ');
      parts.push(`<div class="chips small-chips" style="margin-top:-4px"><span class="chip ${cls}">${icon('shield', 'sm')} ${label}</span>${idxRow && idxRow.eligible === true ? '<span class="chip good">model-eligible</span>' : (idxRow && idxRow.eligible === false ? '<span class="chip warn">not model-eligible</span>' : '')}${statsChip}${earlierTxt ? `<span class="chip">${esc(earlierTxt)}</span>` : ''}${reason && !/^latest result \d{4}/.test(reason) ? `<span class="chip">${esc(reason)}</span>` : ''}</div>`);
    }
    let seg = state.lgSeg;
    if (seg === 'table' && !(d.table && d.table.length)) seg = 'results';
    const items = [];
    if (d.table && d.table.length) items.push(['table', `${icon('chart', 'sm')} Table`]);
    items.push(['trends', `${icon('trend', 'sm')} Trends`], ['results', `${icon('ball', 'sm')} Results`], ['fixtures', `${icon('calendar', 'sm')} Fixtures`], ['teams', `${icon('users', 'sm')} Teams`], ['news', `${icon('doc', 'sm')} News`]);
    parts.push(`<div class="card compact">${segmented(items, seg, 'lseg')}</div>`);
    if (seg === 'trends') {
      leagueTrends(parts, d);
    } else if (seg === 'teams') {
      leagueTeams(parts, d);
    } else if (seg === 'news') {
      leagueNews(parts, d);
    } else if (seg === 'table') {
      const teamAttrs = (name) => d.teams_div ? ` class="tap" data-lgteam="${esc(name)}" data-country="${esc(d.country || '')}" data-div="${esc(d.teams_div)}"` : '';
      const ts = state.lgTableSort || 'pts';
      const tbl = d.table.slice().sort((a, b) =>
        ts === 'gd' ? (b.gd - a.gd) || (b.pts - a.pts) || (a.team || '').localeCompare(b.team || '') :
        ts === 'gf' ? (b.gf - a.gf) || (b.pts - a.pts) || (a.team || '').localeCompare(b.team || '') :
        ts === 'name' ? (a.team || '').localeCompare(b.team || '') :
        (a.pos - b.pos));
      const gd = (x) => (x.gd > 0 ? '+' : '') + x.gd;
      parts.push(`<div class="card compact"><div class="row" style="gap:8px"><div class="grow"><div class="b">Standings</div><div class="tiny muted">pts · gd · gf · form = last five · tap a team for its profile</div></div>${select('lg-tsort', [['pts', 'Sort: Points'], ['gd', 'Sort: GD'], ['gf', 'Sort: Goals for'], ['name', 'Sort: Name']], ts)}</div>
        <div class="tbl-wrap"><table class="tbl head table" style="margin-top:6px;min-width:560px"><tr><th>#</th><th>Team</th><th class="right">P</th><th class="right">W-D-L</th><th class="right">GF</th><th class="right">GA</th><th class="right">GD</th><th class="right">Pts</th><th class="right">Form</th></tr>
        ${tbl.map((x) => `<tr${teamAttrs(x.team)}><td class="muted">${x.pos}</td><td><div class="tname">${badge(x.team, null, 22)}<span class="nm">${esc(x.team)}</span></div></td><td class="right">${x.p}</td><td class="right">${x.w}-${x.d}-${x.l}</td><td class="right">${x.gf}</td><td class="right">${x.ga}</td><td class="right">${gd(x)}</td><td class="right b">${x.pts}</td><td class="right">${x.form ? formBadges(x.form.split('')) : '<span class="tiny muted">–</span>'}</td></tr>`).join('')}</table></div></div>`);
      const half = (key, title) => {
        const rows = tbl.map((x) => ({ team: x.team, h: x[key] })).filter((r) => r.h && r.h.p)
          .sort((a, b) => (b.h.pts - a.h.pts) || ((b.h.gf - b.h.ga) - (a.h.gf - a.h.ga)) || (b.h.gf - a.h.gf));
        if (!rows.length) return '';
        return `<div class="b tiny" style="margin-top:10px">${title} record</div><div class="tbl-wrap"><table class="tbl head" style="margin-top:2px"><tr><th>Team</th><th class="right">P</th><th class="right">W-D-L</th><th class="right">GF</th><th class="right">GA</th><th class="right">Pts</th></tr>
          ${rows.map((r) => `<tr${teamAttrs(r.team)}><td><div class="tname">${badge(r.team, null, 20)}<span class="nm">${esc(r.team)}</span></div></td><td class="right">${r.h.p}</td><td class="right">${r.h.w}-${r.h.d}-${r.h.l}</td><td class="right">${r.h.gf}</td><td class="right">${r.h.ga}</td><td class="right b">${r.h.pts}</td></tr>`).join('')}</table></div>`;
      };
      if (d.table.some((x) => x.h && x.h.p)) {
        parts.push(`<div class="card compact"><div class="b">Home &amp; away splits</div>${half('h', 'Home')}${half('a', 'Away')}</div>`);
      }
    } else if (seg === 'results') {
      if (!(d.results && d.results.length)) parts.push(`<div class="card empty">No finished matches in the archive yet.</div>`);
      else {
        // the day archive only covers days the scanner analysed (newest first) — gate taps on that
        const availDays = new Set(((state.data.history || {}).days || []).map((x) => x.date));
        const oldest = [...availDays].sort()[0] || null;
        const byDay = {};
        d.results.forEach((r) => { const day = r.ko.slice(0, 10); (byDay[day] = byDay[day] || []).push(r); });
        const resRow = (r) => {
          const day = r.ko.slice(0, 10);
          const tap = availDays.has(day) ? ` class="tap" data-lgday="${day}" data-lghome="${esc(r.home)}" data-lgaway="${esc(r.away)}"` : '';
          return `<tr${tap}><td class="tiny muted nowrap">${esc(koTime(r.ko))}</td><td><div class="res-line">${badge(r.home, null, 20)}<span class="tm ${r.hg > r.ag ? 'won' : ''}">${esc(r.home)}</span><span class="sc">${r.hg} – ${r.ag}</span><span class="tm ${r.ag > r.hg ? 'won' : ''}">${esc(r.away)}</span>${badge(r.away, null, 20)}</div>${r.hth != null ? `<div class="tiny muted">HT ${r.hth}–${r.hta}</div>` : ''}</td></tr>`;
        };
        const days = Object.keys(byDay).sort((a, b) => b.localeCompare(a));
        parts.push(`<div class="card tiny muted" style="margin-top:-6px">Tap a match for the Match Center or that day's full archive${oldest ? ` (day archive from ${esc(dayName(oldest))})` : ''} — earlier results show the score here.</div>`);
        parts.push(`<div class="card compact">${days.map((day) => `<div class="comp-head">${esc(dayName(day))} · ${byDay[day].length}${availDays.has(day) ? '' : ' <span class="tiny muted">· final scores</span>'}</div><table class="tbl" style="margin-top:2px">${byDay[day].map(resRow).join('')}</table>`).join('')}</div>`);
      }
    } else {
      if (!(d.fixtures && d.fixtures.length)) parts.push(`<div class="card empty">No scheduled fixtures in the next three days.</div>`);
      else {
        const byDay = {};
        d.fixtures.forEach((f, i) => { const day = f.ko.slice(0, 10); (byDay[day] = byDay[day] || []).push([f, i]); });
        const days = Object.keys(byDay).sort((a, b) => a.localeCompare(b));
        parts.push(`<div class="card tiny muted" style="margin-top:-6px">Tap a fixture to open its Match Center once it enters the 24-hour analysis window.</div>`);
        parts.push(`<div class="card compact">${days.map((day) => `<div class="comp-head">${esc(dayName(day))}</div><table class="tbl" style="margin-top:2px">${byDay[day].map(([f, i]) => `<tr class="tap" data-lgfx="${i}"><td class="tiny muted nowrap">${esc(koTime(f.ko))}</td><td><div class="res-line">${badge(f.home, null, 20)}<span class="tm">${esc(f.home)}</span><span class="sc muted">v</span><span class="tm">${esc(f.away)}</span>${badge(f.away, null, 20)}</div></td></tr>`).join('')}</table>`).join('')}</div>`);
      }
    }
    parts.push(`<div class="tiny muted" style="margin:10px 4px 18px">Source: public live-score archive (all competitions it publishes). ${d.played} matches on record${d.table && d.table.length ? ' · knockout rounds have no table' : ''}.</div>`);
    view().innerHTML = parts.join('');
    wireBack();
    $$('[data-lseg]').forEach((b) => { b.onclick = () => { state.lgSeg = b.dataset.lseg; PR.render(); }; });
    const r = $('#lg-retry'); if (r) r.onclick = () => { delete LG.det[page.slug]; ensureDetail(page.slug); };
    if (seg === 'news' && PR.wireNewsLinks) PR.wireNewsLinks();
    const tsel = $('#lg-tsort'); if (tsel) tsel.onchange = (e) => { state.lgTableSort = e.target.value; PR.render(); };
    $$('[data-lgteam]').forEach((el) => { el.onclick = () => PR.openTeam(el.dataset.lgteam, el.dataset.country, el.dataset.div); });
    $$('[data-lgday]').forEach((el) => {
      el.onclick = () => {
        const day = el.dataset.lgday;
        const fid = `${day}|${d.country || ''}|${el.dataset.lghome}|${el.dataset.lgaway}`;
        if (PR.fx(fid) || PR.dayRecord(fid)) PR.openMatch(fid);
        else { state.dayView = 'results'; PR.push({ type: 'day', date: day }); }
      };
    });
    $$('[data-lgfx]').forEach((el) => {
      const f = (d.fixtures || [])[+el.dataset.lgfx];
      if (!f) return;
      const day = f.ko.slice(0, 10);
      const inWin = (state.data.fixtures || []).find((x) => x.kickoff.slice(0, 10) === day && ((x.home === f.home && x.away === f.away) || (x.home === f.away && x.away === f.home)));
      if (inWin) PR.openMatch(inWin.id, inWin.d);
      else toast('Outside the 24-hour analysis window — it appears in the app when its day is analysed (results open from the day archive once finished).');
    });
  };

  // ------------------------------------------------------------------ league TREND tab
  function leagueTrends(parts, d) {
    const t = d.trends;
    if (!t) { parts.push(`<div class="card empty">No finished matches on record yet — trends appear as results come in.</div>`); return; }
    const W = [['last5', 'L5'], ['last10', 'L10'], ['last20', 'L20'], ['season', 'Season'], ['previous_season', 'Prev. season']];
    const pctf = (v) => (v == null ? 'N/A' : Math.round(v * 100) + '%');
    const num2 = (v) => (v == null ? 'N/A' : String(Math.round(v * 100) / 100));
    const M = [
      ['avg_goals', 'Avg goals', num2], ['o05', 'Over 0.5', pctf], ['o15', 'Over 1.5', pctf],
      ['o25', 'Over 2.5', pctf], ['o35', 'Over 3.5', pctf], ['btts', 'BTTS', pctf],
      ['home_win', 'Home win', pctf], ['draw', 'Draw', pctf], ['away_win', 'Away win', pctf],
      ['home_goals', 'Home goals', num2], ['away_goals', 'Away goals', num2],
      ['home_clean_sheet', 'Home clean sheet', pctf], ['away_clean_sheet', 'Away clean sheet', pctf],
      ['home_failed_to_score', 'Home fails to score', pctf], ['away_failed_to_score', 'Away fails to score', pctf],
      ['avg_corners', 'Avg corners', num2], ['avg_cards', 'Avg cards', num2],
    ];
    const rows = M.map(([k, label, fmt]) => {
      const cells = W.map(([wk, wl]) => {
        const w = t[wk]; const v = w ? w[k] : null;
        const note = (k === 'avg_corners' || k === 'avg_cards') && w && w.n && w[k + '_n'] != null && w[k + '_n'] < w.n ? ` <span class="tiny muted">(${w[k + '_n']}/${w.n})</span>` : '';
        return `<div class="cell"><span class="cl">${wl}${w ? ` · ${w.n}` : ''}</span><b>${fmt(v)}</b></div>`;
      }).join('');
      return `<div class="trend-metric"><div class="k">${label}</div><div class="v">${cells}</div></div>`;
    }).join('');
    parts.push(`<div class="card tiny muted">Data-driven league trends, computed only from published results. A window needs at least 5 finished matches — thinner windows show N/A rather than a guess. Corners/cards use only the matches whose statistics the provider publishes.</div>`);
    parts.push(`<div class="card compact"><div class="b" style="margin-bottom:2px">Trend windows</div><div class="tiny muted" style="margin-bottom:4px">n = matches in window · swipe sideways for all windows</div><div class="tbl-wrap"><div class="trend-grid">${rows}</div></div></div>`);
    const ch = t.change_last10_vs_season;
    if (ch) {
      const pp = (v) => (v == null ? 'N/A' : (v > 0 ? '+' : '') + Math.round(v * 100) + ' pp');
      parts.push(`<div class="card compact"><div class="b">Last 10 vs season average</div><div class="tiny muted" style="margin-top:4px">descriptive only — the prediction model does not use these numbers</div>
        <div class="grid4" style="margin-top:6px"><div class="cell"><div class="k">Avg goals</div><div class="v">${ch.avg_goals > 0 ? '+' : ''}${ch.avg_goals}</div></div><div class="cell"><div class="k">Over 2.5</div><div class="v">${pp(ch.o25)}</div></div><div class="cell"><div class="k">BTTS</div><div class="v">${pp(ch.btts)}</div></div></div></div>`);
    }
  }

  // ------------------------------------------------------------------ league TEAMS tab
  function leagueTeams(parts, d) {
    const attrs = (name) => d.teams_div ? ` data-lgteam="${esc(name)}" data-country="${esc(d.country || '')}" data-div="${esc(d.teams_div)}"` : '';
    if (d.table && d.table.length) {
      const ts = state.lgTableSort || 'pts';
      const tbl = d.table.slice().sort((a, b) =>
        ts === 'gd' ? (b.gd - a.gd) || (b.pts - a.pts) || (a.team || '').localeCompare(b.team || '') :
        ts === 'gf' ? (b.gf - a.gf) || (b.pts - a.pts) || (a.team || '').localeCompare(b.team || '') :
        ts === 'name' ? (a.team || '').localeCompare(b.team || '') :
        (a.pos - b.pos));
      parts.push(`<div class="card compact"><div class="b">Teams (${d.table.length})</div><div class="tiny muted" style="margin-bottom:4px">tap a team for its profile, form and season numbers</div>
        <table class="tbl head table" style="margin-top:4px"><tr><th>#</th><th>Team</th><th class="right">P</th><th class="right">GF</th><th class="right">GA</th><th class="right">GD</th><th class="right">Pts</th><th class="right">Form</th></tr>
        ${tbl.map((x) => `<tr class="tap"${attrs(x.team)}><td class="muted">${x.pos}</td><td><div class="tname">${badge(x.team, null, 22)}<span class="nm">${esc(x.team)}</span></div></td><td class="right">${x.p}</td><td class="right">${x.gf}</td><td class="right">${x.ga}</td><td class="right">${x.gd > 0 ? '+' : ''}${x.gd}</td><td class="right b">${x.pts}</td><td class="right">${x.form ? formBadges(x.form.split('')) : '<span class="tiny muted">–</span>'}</td></tr>`).join('')}</table></div>`);
      return;
    }
    // knockout / insufficient data: list the teams that appear in the archived results
    const cnt = {};
    (d.results || []).forEach((r) => { cnt[r.home] = (cnt[r.home] || 0) + 1; cnt[r.away] = (cnt[r.away] || 0) + 1; });
    const teams = Object.entries(cnt).sort((a, b) => b[1] - a[1]).slice(0, 24);
    if (!teams.length) { parts.push(`<div class="card empty">No teams on record yet.</div>`); return; }
    parts.push(`<div class="card compact"><div class="b">Teams seen in the archive</div><div class="tiny muted" style="margin-bottom:4px">knockout / round format — no league table applies · matches in the archive</div>
      ${teams.map(([t, n]) => `<div class="lg-row tap"${attrs(t)}><div class="lg-ic">${badge(t, null, 24)}</div><div class="grow b">${esc(t)}</div><div class="lg-right tiny muted">${n} match${n === 1 ? '' : 'es'}</div></div>`).join('')}</div>`);
  }

  // ------------------------------------------------------------------ league NEWS tab
  function leagueNews(parts, d) {
    const news = d.news || {};
    const teams = Object.entries(news.teams || {}).filter(([, a]) => (a || []).length);
    if (!(news.league || []).length && !teams.length) {
      parts.push(`<div class="card empty">No recent headlines for this competition yet. News refreshes at most every 6 hours with each scan.</div>`);
      return;
    }
    const item = (it) => (PR.newsItem ? PR.newsItem(it) : `<div class="news-item"><b style="font-size:13px">${esc(it.title || '')}</b><div class="tiny muted">${esc(it.source || '')}</div></div>`);
    parts.push(`<div class="card tiny muted">Recent reporting about this competition and its leading teams — headlines only, from Google News. Clicking opens the original source. News is never used by the prediction model.</div>`);
    if ((news.league || []).length) parts.push(`<div class="card compact"><div class="b" style="margin-bottom:4px">${icon('trophy', 'sm')} ${esc(d.league || 'This competition')}</div>${news.league.map(item).join('')}</div>`);
    teams.forEach(([t, list]) => parts.push(`<div class="card compact"><div class="b" style="margin-bottom:4px">${badge(t, null, 20)} ${esc(t)}</div>${list.map(item).join('')}</div>`));
  }

  // expose for tests
  PR.leaguesApi = { loadIndex, loadDetail };
})(window.PR);
