/* PlayReport — boot: header menu, update banner, native callbacks, timers. */
(function (PR) {
  'use strict';
  const { $, $$, state, settings, esc, toast } = PR;

  // header buttons + menu
  $$('#tabs button').forEach((b) => { b.onclick = () => PR.setTab(b.dataset.tab); });
  $('#btn-refresh').onclick = () => { PR.loadData(true); if (state.tab === 'live' || state.tab === 'home') PR.live.refresh(true); };
  $('#btn-menu').onclick = (e) => { e.stopPropagation(); PR.toggleMenu(); };
  $('#btn-search').onclick = (e) => { e.stopPropagation(); PR.closeMenu(); state.focusSearch = true; state.stack = []; if (state.tab === 'matches') PR.render(); else PR.setTab('matches'); const i = $('#fx-search'); if (i) { i.focus(); i.scrollIntoView({ block: 'start', behavior: 'smooth' }); } };
  $$('#menu [data-page]').forEach((b) => { b.onclick = () => { PR.closeMenu(); const t = b.dataset.page; state.stack = []; PR.push({ type: t }); }; });
  $('#menu [data-contact]').onclick = () => { PR.closeMenu(); if (PR.native && PR.native.openUrl) PR.native.openUrl(`https://wa.me/${PR.CONTACT.whatsapp}`); else window.open(`https://wa.me/${PR.CONTACT.whatsapp}`); };
  document.addEventListener('visibilitychange', () => { if (!document.hidden && (state.tab === 'live' || state.tab === 'home')) PR.live.refresh(false); });

  // updates
  PR.startUpdate = function () {
    if (!state.update || !PR.native || !PR.native.installUpdate) return;
    state.updateStage = 'downloading'; renderBanner(); toast('Downloading update…');
    PR.native.installUpdate(state.update.url);
  };
  function renderBanner() {
    const b = $('#banner'); const u = state.update;
    if (!u) { b.innerHTML = ''; return; }
    const stage = state.updateStage;
    b.innerHTML = `<div class="update"><div class="grow"><b>PlayReport v${esc(u.version)} is ready</b><div class="tiny">${stage === 'downloading' ? 'Downloading…' : stage === 'installing' ? 'Opening the installer — tap Install when Android asks.' : stage === 'failed' ? 'Download failed — check your connection and try again.' : 'Tap Update to install the new version.'}</div></div>
      ${stage === 'downloading' || stage === 'installing' ? '<span class="spinner"></span>' : '<button class="btn primary" id="b-update">Update</button>'}</div>`;
    const btn = $('#b-update'); if (btn) btn.onclick = PR.startUpdate;
  }
  window.__updateInfo = function (info) {
    state.update = info || null; state.updateStage = null; renderBanner();
    if (state.updateChecked === 'manual') { toast(info ? `Version ${info.version} available` : 'You have the latest version'); state.updateChecked = null; }
    const top = state.stack[state.stack.length - 1]; if (top && top.type === 'settings') PR.render();
  };
  window.__updateProgress = function (stage) { state.updateStage = stage; renderBanner(); if (stage === 'failed') toast('Update download failed'); };

  // native entry points
  window.app = {
    refresh() { PR.loadData(true).then(() => { if (state.tab === 'live' || state.tab === 'home') PR.live.refresh(true); }); },
    back: () => PR.back(),
    setTab: (t) => PR.setTab(t),
    onResume() { if (state.data && Date.now() - (state.data._loadedAt || 0) > 5 * 60000) PR.loadData(false); if (state.tab === 'live' || state.tab === 'home') PR.live.refresh(false); const top = state.stack[state.stack.length - 1]; if (top && top.type === 'settings') PR.render(); },
    onPermission(granted) { toast(granted ? 'Notifications on — new bets, analysis, goals and updates' : 'Notifications are off — you can enable them in Settings'); const top = state.stack[state.stack.length - 1]; if (top && top.type === 'settings') PR.render(); },
    state, settings, PR,
  };

  // boot: cached first, then network
  const cached = localStorage.getItem('pr_latest');
  if (cached) { try { state.data = PR.indexData(JSON.parse(cached)); PR.statusLine(); PR.render(); } catch (e) { /* ignore */ } }
  PR.loadBadges().then(() => { if (state.data) PR.render(); });
  PR.loadData(false).then(() => { if (state.data) PR.live.refresh(false); });
  PR.live.schedule();
  if (PR.native && PR.native.setPref) { try { PR.native.setPref('goals', !!settings.goalAlerts); PR.native.setPref('ht', !!settings.htAlerts); PR.native.setPref('ft', settings.ftAlerts !== false); PR.native.setPref('ko', settings.koAlerts !== false); if (PR.saveFavs) PR.saveFavs(); PR.native.setPref('bets', settings.betAlerts !== false); PR.native.setPref('reports', settings.reportAlerts !== false); } catch (e) { /* ignore */ } }
  if (PR.reconcileTickets) setTimeout(() => PR.reconcileTickets(), 2500);
  if (PR.native && PR.native.checkUpdate) setTimeout(() => { try { PR.native.checkUpdate(); } catch (e) { /* ignore */ } }, 4000);
})(window.PR);
