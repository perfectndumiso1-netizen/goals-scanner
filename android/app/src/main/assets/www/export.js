/* PlayReport — CSV exports (Google Sheets / Excel friendly): one analysed match, or the whole day's analysis. */
(function (PR) {
  'use strict';
  const { state, toast, selLabel, tzNow, ymd } = PR;
  const BOM = '\ufeff';
  const cell = (v) => {
    if (v == null) return '';
    if (typeof v === 'number') return Number.isInteger(v) ? String(v) : String(Math.round(v * 1000) / 1000);
    const s = String(v);
    return /[",\n\r;]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const row = (arr) => arr.map(cell).join(',');
  const pc = (p) => (p == null ? '' : Math.round(p * 1000) / 10);          // 0.734 -> 73.4 (percent, numeric)
  const fileName = (s) => s.replace(/[^A-Za-z0-9._-]+/g, '_').replace(/^_+|_+$/g, '');

  /** hand a text file to the phone (system "save as" picker); browsers get a download */
  PR.saveTextFile = function (name, text, mime) {
    const type = mime || 'text/csv';
    if (PR.native && PR.native.saveText) {
      try { PR.native.saveText(name, type, text); toast('Choose where to save the file…'); return; } catch (e) { /* fall through */ }
    }
    try {
      const blob = new Blob([text], { type: type + ';charset=utf-8' });
      const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = name; document.body.appendChild(a); a.click();
      setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 2000);
      toast(`Downloaded ${name}`);
    } catch (e) { toast('Could not save the file'); }
  };

  const wdl = (gf, ga) => (gf > ga ? 'W' : gf < ga ? 'L' : 'D');
  const teamBlock = (name, t, side) => {
    const lines = [];
    lines.push(row([`${side} team`, name]));
    lines.push(row(['Matches used', t.n, 'Home/away sample', t.venue_n]));
    lines.push(row(['Goals for / game', t.gf, 'Goals against / game', t.ga]));
    lines.push(row(['At this venue: for / game', t.venue_gf, 'against / game', t.venue_ga]));
    lines.push(row(['Attack rating (1 = league average)', t.att, 'Defence rating', t.def]));
    lines.push(row(['Over 1.5 %', pc(t.o15), 'Over 2.5 %', pc(t.o25), 'Over 3.5 %', pc(t.o35)]));
    lines.push(row(['BTTS %', pc(t.btts), 'Clean sheets %', pc(t.cs), 'Failed to score %', pc(t.fts)]));
    lines.push(row([`Last ${t.last_n || 0}: Over 1.5`, t.last_o15, 'Over 2.5', t.last_o25, 'BTTS', t.last_btts]));
    if (t.xg_for != null || t.sot_for != null) lines.push(row(['xG for / game', t.xg_for, 'xG against / game', t.xg_against, 'Shots on target for', t.sot_for, 'against', t.sot_against]));
    return lines;
  };

  /** CSV of one analysed match: header block, markets, team profiles, recent form, head-to-head, trends, corners & cards */
  PR.matchCsv = function (x, live, extraStats) {
    const L = [];
    const teams = x.teams || { home: {}, away: {} };
    const xg = x.xg || {}; const p = x.p || {}; const x12 = x.x12 || {}; const tg = x.team_goals || {};
    L.push(row(['PlayReport match analysis']));
    L.push(row(['Match', `${x.home} v ${x.away}`]));
    L.push(row(['Competition', x.competition, 'Country', x.country]));
    L.push(row(['Kick-off (SAST)', x.kickoff, 'Date', x.date]));
    L.push(row(['Analysis published', state.data && state.data.meta ? state.data.meta.generated : '']));
    if (live && live.hg != null) L.push(row(['Score', `${live.hg}-${live.ag}`, 'Status', live.status || '']));
    L.push(row(['Data quality', x.data_ok ? 'ok' : 'low data', 'Basis', x.basis || '']));
    L.push('');
    L.push(row(['Expected goals', 'Home', 'Away', 'Total']));
    L.push(row(['Model', xg.model_home, xg.model_away, xg.model_home != null && xg.model_away != null ? xg.model_home + xg.model_away : '']));
    L.push(row(['Market', xg.market_home, xg.market_away, xg.market_home != null && xg.market_away != null ? xg.market_home + xg.market_away : '']));
    L.push(row(['Final', xg.home, xg.away, xg.total]));
    L.push('');
    L.push(row(['Probability (%)', 'Value']));
    L.push(row(['Home win', pc(x12.H)])); L.push(row(['Draw', pc(x12.D)])); L.push(row(['Away win', pc(x12.A)]));
    L.push(row(['1X', pc(x12['1X'])])); L.push(row(['12', pc(x12['12'])])); L.push(row(['X2', pc(x12.X2)]));
    L.push(row(['Over 1.5 goals', pc(p.O15)])); L.push(row(['Over 2.5 goals', pc(p.O25)])); L.push(row(['Over 3.5 goals', pc(p.O35)])); L.push(row(['Both teams to score', pc(p.BTTS)]));
    L.push(row([`${x.home} to score`, pc(tg.H_o05)])); L.push(row([`${x.home} 2+ goals`, pc(tg.H_o15)])); L.push(row([`${x.away} to score`, pc(tg.A_o05)])); L.push(row([`${x.away} 2+ goals`, pc(tg.A_o15)]));
    L.push('');
    L.push(row(['Market selection', 'Code', 'Combined %', 'Model %', 'Market %', 'Sportybet price', 'Fair price', 'Views agree']));
    (x.sels || []).forEach((s) => L.push(row([selLabel(s.sel, x.home, x.away), s.sel, pc(s.p), pc(s.p_model), pc(s.p_sb), s.odds, s.p ? Math.round(100 / s.p) / 100 : '', s.diff ? 'no' : 'yes'])));
    L.push('');
    L.push(...teamBlock(x.home, teams.home || {}, 'Home'));
    L.push('');
    L.push(...teamBlock(x.away, teams.away || {}, 'Away'));
    L.push('');
    L.push(row(['Recent form', 'Team', 'Date', 'Venue', 'Opponent', 'Goals for', 'Goals against', 'Result', 'Competition']));
    ['home', 'away'].forEach((side) => ((teams[side] || {}).last5 || []).forEach((m) => L.push(row(['', x[side], m.date, m.venue === 'H' ? 'Home' : 'Away', m.opp, m.gf, m.ga, wdl(m.gf, m.ga), m.league]))));
    if ((x.h2h || []).length) {
      L.push('');
      L.push(row(['Head to head', 'Date', 'Home', 'Away', 'Home goals', 'Away goals', 'Competition']));
      x.h2h.forEach((m) => L.push(row(['', m.date, m.home, m.away, m.hg, m.ag, m.league])));
    }
    const tr = x.trends || {};
    const trendRows = [];
    ['home', 'away'].forEach((side) => (((tr[side] || {}).all) || []).forEach((t) => trendRows.push([x[side], t.t, t.k, t.n, pc(t.r), t.kind])));
    (tr.match || []).forEach((t) => trendRows.push(['Both teams', t.t, t.k, t.n, pc(t.r), t.kind]));
    (tr.h2h || []).forEach((t) => trendRows.push(['Head to head', t.t, t.k, t.n, pc(t.r), t.kind]));
    if (trendRows.length) {
      L.push('');
      L.push(row(['Trends', 'Team', 'Trend', 'Hits', 'Of', 'Rate %', 'Kind']));
      trendRows.forEach((r) => L.push(row([''].concat(r))));
    }
    ['corners', 'cards'].forEach((k) => {
      const c = x[k]; if (!c) return;
      L.push('');
      L.push(row([k === 'corners' ? 'Corners' : 'Cards (bookings)', 'Home', 'Away', 'Total']));
      L.push(row(['Expected', c.home, c.away, c.total]));
      Object.entries((c.p || {}).total || {}).forEach(([line, pr]) => L.push(row([`Over ${line} total %`, '', '', pc(pr)])));
      Object.entries((c.p || {}).home || {}).forEach(([line, pr]) => L.push(row([`Over ${line} home %`, pc(pr), '', ''])));
      Object.entries((c.p || {}).away || {}).forEach(([line, pr]) => L.push(row([`Over ${line} away %`, '', pc(pr), ''])));
    });
    if (extraStats && extraStats.length) {
      L.push('');
      L.push(row(['Match statistics', x.home, x.away]));
      extraStats.forEach(([k, a, b, unit]) => L.push(row([k, a == null ? '' : `${a}${unit || ''}`, b == null ? '' : `${b}${unit || ''}`])));
    }
    if (x.sportybet) {
      L.push('');
      L.push(row(['Sportybet prices', 'Selection', 'Price']));
      const sb = x.sportybet;
      if (sb['1X2']) { L.push(row(['1X2', 'Home', sb['1X2'][0]])); L.push(row(['1X2', 'Draw', sb['1X2'][1]])); L.push(row(['1X2', 'Away', sb['1X2'][2]])); }
      Object.entries(sb.DC || {}).forEach(([k, v]) => L.push(row(['Double chance', k, v])));
      if (sb.BTTS) { L.push(row(['Both teams to score', 'Yes', sb.BTTS[0]])); L.push(row(['Both teams to score', 'No', sb.BTTS[1]])); }
      Object.entries(sb.OU || {}).sort((a, b) => +a[0] - +b[0]).forEach(([line, v]) => { L.push(row(['Total goals', `Over ${line}`, v[0]])); L.push(row(['Total goals', `Under ${line}`, v[1]])); });
    }
    return BOM + L.join('\r\n') + '\r\n';
  };

  PR.downloadMatchCsv = function (x, live, extraStats) {
    const name = fileName(`PlayReport_${x.date}_${x.home}_v_${x.away}`) + '.csv';
    PR.saveTextFile(name, PR.matchCsv(x, live, extraStats), 'text/csv');
  };

  /** the day's analysis table published with every report (reports/<date>.csv) */
  PR.downloadDayCsv = async function (date) {
    const d = date || (state.data && state.data.meta ? state.data.meta.generated.slice(0, 10) : ymd(tzNow()));
    toast('Preparing the file…');
    try {
      const r = await PR.nfetch(PR.rawUrl(`reports/${d}.csv`) + '?t=' + Math.floor(Date.now() / 300000));
      if (r.code !== 200) throw new Error(`HTTP ${r.code}`);
      const text = r.body.charCodeAt(0) === 0xfeff ? r.body : BOM + r.body;
      PR.saveTextFile(`PlayReport_${d}_analysis.csv`, text, 'text/csv');
    } catch (e) {
      toast(`Today's data file is not available yet (${e.message})`);
    }
  };
})(window.PR);
