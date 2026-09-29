/* PlayReport — Leagues tab: worldwide football league tables, previous results and fixtures.
   Data: data/app/leagues/index.json + one detail file per competition, published from the public
   feed's stage archive on every scan. Read-only for the app; cached on the phone like every other
   data file, refreshed in the background when the publication is newer. */
(function (PR) {
  'use strict';
  const { $, $$, esc, state, toast, segmented, icon, flag, badge, skeleton, parseLocal, niceDate, koTime, dayName, koShort, getJson, rawUrl, formBadges, wdl } = PR;
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
    parts.push(`<div class="lg-head"><div class="grow"><div class="b">${icon('trophy', 'sm')} Leagues</div><div class="tiny muted">Tables, results &amp; fixtures — every competition on the public feed</div></div>
      ${LG.idx ? `<span class="tiny muted">${LG.idx.count} competitions · ${new Set((LG.idx.leagues || []).map((x) => x.country)).size} countries${LG.idxStale ? ' · saved copy' : ''}</span>` : ''}</div>`);
    parts.push(`<div class="searchbar"><div class="field">${icon('search', 'sm')}<input id="lg-search" type="search" placeholder="Search a league or country" value="${esc(state.lgQ)}" autocomplete="off"></div></div>`);
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
    const rows = (LG.idx.leagues || []).filter((x) => !q || (x.league || '').toLowerCase().includes(q) || (x.country || '').toLowerCase().includes(q));
    if (!rows.length) parts.push(`<div class="card empty small">No league matches “${esc(state.lgQ)}”.</div>`);
    let lastCountry = null;
    rows.forEach((x) => {
      if (x.country !== lastCountry) {
        if (lastCountry !== null) parts.push('</div>');
        parts.push(`<div class="card compact"><div class="comp-head">${flag(x.country)} ${esc(x.country || 'Other')}</div>`);
        lastCountry = x.country;
      }
      const meta = [x.teams ? `${x.teams} teams` : null, x.played ? `${x.played} played` : null, x.season || null].filter(Boolean).join(' · ');
      parts.push(`<div class="lg-row tap" data-lg="${esc(x.slug)}"><div class="lg-ic">${x.table ? icon('trophy') : flag(x.country)}</div>
        <div class="grow"><div class="b">${esc(x.league)}</div><div class="tiny muted">${meta}</div></div>
        <div class="lg-right">${x.next ? `<div class="tiny muted">next</div><div class="b" style="font-size:13px">${esc(koShort(x.next))}</div>` : ''}</div></div>`);
    });
    if (lastCountry !== null) parts.push('</div>');
    parts.push(`<div class="tiny muted" style="margin:10px 4px 18px">Updated every 30 minutes from the public live-score archive · ${LG.idx.count} competitions · season history accumulates each matchday.</div>`);
    view().innerHTML = parts.join('');
    const s = $('#lg-search'); if (s) { s.oninput = (e) => { state.lgQ = e.target.value; PR.render(); const n = $('#lg-search'); if (n) { n.focus(); n.setSelectionRange(n.value.length, n.value.length); } }; }
    $$('#view [data-lg]').forEach((el) => { el.onclick = () => openLeague(el.dataset.lg); });
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
    if (st) {
      const cls = st === 'ACTIVE' ? 'good' : (st === 'FINISHED' ? '' : 'warn');
      const label = { ACTIVE: 'active', UPCOMING: 'upcoming', FINISHED: 'finished', INSUFFICIENT_HISTORY: 'insufficient history', INSUFFICIENT_STATS: 'insufficient stats', DATA_ERROR: 'data error', NOT_SUPPORTED: 'not supported' }[st] || st;
      parts.push(`<div class="chips small-chips" style="margin-top:-4px"><span class="chip ${cls}">${icon('shield', 'sm')} ${label}</span>${idxRow && idxRow.eligible === true ? '<span class="chip good">model-eligible</span>' : (idxRow && idxRow.eligible === false ? '<span class="chip warn">not model-eligible</span>' : '')}${d.status_reason ? `<span class="chip">${esc(d.status_reason)}</span>` : ''}</div>`);
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
      parts.push(`<div class="card compact"><div class="b">Standings</div><div class="tiny muted" style="margin-bottom:4px">Points, goal difference, then goals scored · form is the last five matches</div>
        <table class="tbl head table" style="margin-top:4px"><tr><th>#</th><th>Team</th><th class="right">P</th><th class="right">W-D-L</th><th class="right">GD</th><th class="right">Pts</th><th class="right">Form</th></tr>
        ${d.table.map((x) => `<tr><td class="muted">${x.pos}</td><td><div class="tname">${badge(x.team, null, 22)}<span class="nm">${esc(x.team)}</span></div></td><td class="right">${x.p}</td><td class="right">${x.w}-${x.d}-${x.l}</td><td class="right">${x.gd > 0 ? '+' : ''}${x.gd}</td><td class="right b">${x.pts}</td><td class="right">${x.form ? formBadges(x.form.split('')) : '<span class="tiny muted">–</span>'}</td></tr>`).join('')}</table></div>`);
    } else if (seg === 'results') {
      if (!(d.results && d.results.length)) parts.push(`<div class="card empty">No finished matches in the archive yet.</div>`);
      else {
        const byDay = {};
        d.results.forEach((r) => { const day = r.ko.slice(0, 10); (byDay[day] = byDay[day] || []).push(r); });
        const resRow = (r) => `<tr><td class="tiny muted nowrap">${esc(koTime(r.ko))}</td><td><div class="res-line">${badge(r.home, null, 20)}<span class="tm ${r.hg > r.ag ? 'won' : ''}">${esc(r.home)}</span><span class="sc">${r.hg} – ${r.ag}</span><span class="tm ${r.ag > r.hg ? 'won' : ''}">${esc(r.away)}</span>${badge(r.away, null, 20)}</div>${r.hth != null ? `<div class="tiny muted">HT ${r.hth}–${r.hta}</div>` : ''}</td></tr>`;
        const days = Object.keys(byDay).sort((a, b) => b.localeCompare(a));
        parts.push(`<div class="card compact">${days.map((day) => `<div class="comp-head">${esc(dayName(day))} · ${byDay[day].length}</div><table class="tbl" style="margin-top:2px">${byDay[day].map(resRow).join('')}</table>`).join('')}</div>`);
      }
    } else {
      if (!(d.fixtures && d.fixtures.length)) parts.push(`<div class="card empty">No scheduled fixtures in the next three days.</div>`);
      else {
        const byDay = {};
        d.fixtures.forEach((f) => { const day = f.ko.slice(0, 10); (byDay[day] = byDay[day] || []).push(f); });
        const days = Object.keys(byDay).sort((a, b) => a.localeCompare(b));
        parts.push(`<div class="card compact">${days.map((day) => `<div class="comp-head">${esc(dayName(day))}</div><table class="tbl" style="margin-top:2px">${byDay[day].map((f) => `<tr><td class="tiny muted nowrap">${esc(koTime(f.ko))}</td><td><div class="res-line">${badge(f.home, null, 20)}<span class="tm">${esc(f.home)}</span><span class="sc muted">v</span><span class="tm">${esc(f.away)}</span>${badge(f.away, null, 20)}</div></td></tr>`).join('')}</table>`).join('')}</div>`);
      }
    }
    parts.push(`<div class="tiny muted" style="margin:10px 4px 18px">Source: public live-score archive (all competitions it publishes). ${d.played} matches on record${d.table && d.table.length ? ' · knockout rounds have no table' : ''}.</div>`);
    view().innerHTML = parts.join('');
    wireBack();
    $$('[data-lseg]').forEach((b) => { b.onclick = () => { state.lgSeg = b.dataset.lseg; PR.render(); }; });
    const r = $('#lg-retry'); if (r) r.onclick = () => { delete LG.det[page.slug]; ensureDetail(page.slug); };
    if (seg === 'news' && PR.wireNewsLinks) PR.wireNewsLinks();
    $$('[data-lgteam]').forEach((el) => { el.onclick = () => PR.openTeam(el.dataset.lgteam, el.dataset.country, el.dataset.div); });
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
    parts.push(`<div class="card compact"><div class="b" style="margin-bottom:2px">Trend windows</div><div class="tiny muted" style="margin-bottom:4px">n = matches in window</div>${rows}</div>`);
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
      parts.push(`<div class="card compact"><div class="b">Teams (${d.table.length})</div><div class="tiny muted" style="margin-bottom:4px">tap a team for its profile, form and season numbers</div>
        <table class="tbl head table" style="margin-top:4px"><tr><th>#</th><th>Team</th><th class="right">P</th><th class="right">GD</th><th class="right">Pts</th><th class="right">Form</th></tr>
        ${d.table.map((x) => `<tr class="tap"${attrs(x.team)}><td class="muted">${x.pos}</td><td><div class="tname">${badge(x.team, null, 22)}<span class="nm">${esc(x.team)}</span></div></td><td class="right">${x.p}</td><td class="right">${x.gd > 0 ? '+' : ''}${x.gd}</td><td class="right b">${x.pts}</td><td class="right">${x.form ? formBadges(x.form.split('')) : '<span class="tiny muted">–</span>'}</td></tr>`).join('')}</table></div>`);
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
