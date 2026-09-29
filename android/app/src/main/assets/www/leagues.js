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
    let seg = state.lgSeg;
    if (seg === 'table' && !(d.table && d.table.length)) seg = 'results';
    const items = [];
    if (d.table && d.table.length) items.push(['table', `${icon('chart', 'sm')} Table`]);
    items.push(['results', `${icon('ball', 'sm')} Results`], ['fixtures', `${icon('calendar', 'sm')} Fixtures`]);
    parts.push(`<div class="card compact">${segmented(items, seg, 'lseg')}</div>`);
    if (seg === 'table') {
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
  };

  // expose for tests
  PR.leaguesApi = { loadIndex, loadDetail };
})(window.PR);
