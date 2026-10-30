## What's new — Mr 2 Odds 1.6.86

- **Saved data first.** Previously downloaded fixtures, predictions, match details, team statistics, standings and history can open from local storage while a background check looks for updates.
- **Less repeated downloading.** Conditional GitHub requests, shared background-sync snapshots and duplicate-request protection reuse unchanged data.
- **Better offline behaviour.** Useful saved data stays available after network errors. Cached/offline and freshness indicators distinguish saved information from a successful current check. Screens need one successful download before their data is available offline; image availability still depends on the WebView image cache.
- **Safer local storage.** An asynchronous, size-limited Android SQLite cache preserves validated snapshots and keeps large JSON writes out of synchronous localStorage. Invalid responses do not replace useful saved data.
- **Same app and analysis.** Mr 2 Odds branding, com.playreport.app, signing configuration, preferences, favourites, tickets, GitHub backend and prediction calculations are unchanged. Install this update over the current app rather than uninstalling it.
- **Validation.** Android compilation/unit tests and automated cache/browser tests passed before release preparation. Browser timing results are not phone benchmarks; physical-device cache, low-storage, Doze and battery testing remain outstanding. The existing release pipeline separately checks signing continuity and an emulator in-place upgrade before publishing.

Older release notes remain available with the previous GitHub releases.
