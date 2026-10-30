# Mr 2 Odds 1.6.87 — Home visuals and collections

## User-authorised scope

Refresh the app visuals, put Bet Advisor and Bets of the Day on Home, add an 80%+ probability-market collection, then validate, merge and publish the update without another approval prompt.

## Implementation

- Three visible, colour-coded Home buttons: **Bet Advisor**, **Bets of the Day**, **80%+ Markets**. Buttons exist even when collections are empty. The advisor uses the existing page and record, not a second implementation.
- Original CSS football-pitch artwork, a green stadium-style overview, clear section headings and mobile match-card layout. No remote artwork, font, production dependency or extra network request. Existing portrait branding is retained.
- Light/dark themes, visible keyboard focus, explicit selected state and reduced-motion compatibility. Phone tables reflow into cards instead of overflowing the page; larger displays retain the table.
- Board shortcuts reset market/sort/pagination filters, focus the collection heading and scroll it into view. Existing sorting, market chips, match/team links, bet-slip actions and back navigation remain available.
- Today's fixture/analysed counters now share the same date scope; analysed count cannot exceed the displayed fixture count merely because the cached publication also includes another date.

## 80%+ semantics

A display filter over existing published selections; it does not change predictions, calibration, prices or the server shortlist.

1. Reuse `homeBets`: today, selected league scope, existing market restrictions/outlier checks and the existing 1.16 odds floor.
2. Require a finite numeric published `s.p >= 0.80`. A 79.999% probability does **not** qualify even if the ordinary percentage formatter rounds it to 80%. Bookmaker-implied probability is not substituted.
3. Filter **before** the existing one-market-per-match ranking. A sub-80% corner line that wins the ordinary board ranking cannot suppress another qualifying 80% line in this collection.
4. Preserve the ordinary Bets of the Day, legacy High probability and Positive EV collections, with their existing bars/ranking.
5. While the 80%+ collection is open, unrelated strong-market, favourite and pending-ticket Home panels are hidden, not removed. They reappear on the ordinary Home board and remain accessible elsewhere.
6. No qualifying selections means an explicit empty state, not a lowered threshold or invented pick. Cache status remains visible; 80% is a model estimate, never a guaranteed outcome.

## Exact changed/new files

| File | Purpose |
|---|---|
| `android/app/src/main/assets/www/views.js` | Home artwork markup, shortcuts, display-only collection, navigation and scoped counters |
| `android/app/src/main/assets/www/app.css` | Home visuals, theme-aware cards, accessible focus and narrow-screen reflow |
| `android/app/build.gradle.kts` | Default version 1.6.87/code 87; release code still comes from CI run number |
| `android/RELEASE_NOTES.md` | User-facing update notes |
| `.github/workflows/build-app.yml` | Only two existing hard-coded version labels changed to 1.6.87; workflow logic unchanged |
| `android/home_visual_test.cjs` | Eight dependency-free collection/navigation-markup regressions |
| `android/home_visual_browser_test.cjs` | Optional real Chromium visual/navigation/boundary/offline-UI test |
| `tests/test_android_home_visuals.py` | Existing Python CI runs the Node regressions and local-asset/responsiveness contracts |
| `docs/ANDROID_HOME_VISUALS.md` | This implementation and validation record |

## Validation before PR creation

- Full Python suite: **732 passed, 1 skipped, 8 subtests passed** (80.94 seconds).
- Existing cache repository regressions: **25 passed**. New Home collection regressions: **8 passed**, also invoked by Python CI.
- Real Chromium, using bundled app assets and a read-only published snapshot: light/dark at **320, 412 and 768 px**, all without horizontal page overflow; all three Home buttons visible.
- Actual advisor navigation/back, Bets of the Day navigation, strict 80% boundary, sorting/market filters, match detail/back and empty in-memory offline UI passed. No uncaught JavaScript errors.
- Synthetic boundary selections exist only inside the isolated browser/VM tests. They are never stored in production assets or published football data. Downloaded snapshots, dev dependencies, results and screenshots remain ignored under `tmp/`.
- `git diff --check` and secret scanning passed before staging. PR CI and the existing signed-release pipeline must be checked separately before claiming publication.

## Preservation and limitations

No backend Python/model/formula, JSON schema, GitHub retrieval/cache repository, native storage bridge, branding asset, package ID, signing configuration, saved-preference key, publishing schedule or notification behaviour is changed. No paid service added. Existing release automation still verifies package/signature/key continuity, increasing version code, emulator installation/in-place upgrade and unit tests before publication.

Desktop Chromium layout checks are not Android screenshots or physical-phone validation. Device-specific font scaling, TalkBack, very large fixture lists and physical-phone visual checks remain untested here. The existing emulator upgrade smoke test does not constitute full visual/accessibility/cache instrumentation.
