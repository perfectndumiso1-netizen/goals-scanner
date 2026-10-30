# Mr 2 Odds — presentation-only rebrand

## Selected identity

The owner selected `assets/branding/mr-2-odds-logo.png` from two generated logo options. It is an AI-illustrated portrait based on the owner's existing bundled profile photograph, `android/app/src/main/assets/www/editor.jpg`. The original profile and square avatar photos are unchanged.

Run `python scripts/build_brand_assets.py` with the existing Pillow dependency to reproduce the exports:

- Identical 512×512 PNGs for the app header, Android splash and video renderers. The complete selected badge is retained; the outer square backdrop becomes transparent so it does not appear as a box over video slides.
- Adaptive launcher foregrounds at all five Android densities, padded so the complete badge remains in the central safe zone.
- Legacy launcher icons and a portrait-derived monochrome mask for Android's themed-icon mode (which cannot display full colour).

## Public surfaces

The app name is **Mr 2 Odds**, version **1.6.85**. Header, home/Settings/About/Guide, native notification text, tickets/CSV exports, report/PDF copy and future shortlist/breakdown video graphics use the new identity. The in-app silent briefing/download player uses the same new logo and copy. Historical report/release-note names are aliased to the new name when those text surfaces render in the new app.

The release workflow produces `Mr2Odds-1.6.85.apk` and a checksum with the matching filename. It retains archive, alignment, signature, previous-certificate, increasing-version-code and emulator install/upgrade checks. A separate read-only PR job compiles Android debug resources and runs native tests without release secrets; it does not publish a release. A new signed APK is not available until the approved change is merged and the release job succeeds.

## Intentionally stable identifiers

This must install **over the existing app**, not as a second app. Do not rename `com.playreport.app`, Kotlin packages, FileProvider authorities, signing secrets, `window.PR`, `pr_*` settings/favourites/ticket/cache keys, existing notification-channel IDs, the `playreport` comparison-probability field, Drive appProperties, temp/recovery paths, GitHub repository/branch or external folder IDs. These are compatibility contracts, not visible branding. Preserving them plus the signing key lets Android retain the app's existing records during an in-place upgrade.

Existing historical publications, receipts, audit fixtures and already-uploaded videos retain their original identity. Nothing is deleted, resent or retroactively edited. External Facebook Page/YouTube channel names and the owner's Drive/Zapier folder names are **not** changed by this repository patch; changing those accounts requires their separate owner settings and must not break existing handoff IDs.

## Unchanged behaviour

- Same prediction models, market filters, verification, eligibility, prices, pick count and combined-odds policy. The new brand does **not** mean every card is exactly 2.00 or that a result is guaranteed.
- Same two normal editions, **08:00 / 16:00 SAST**. No additional test Reel or recovery dispatch.
- Same supplied music, no narration, existing slide holds, responsibility warnings, landscape Telegram and portrait Facebook routing.
- Facebook caption remains exactly the requested title, current SAST date and relevant hashtags — no new brand name is injected into it.
- The preferred thumbnail/opening image remains the exact filmed-match list, without selection/odds/probability fields. Other Facebook feed posts remain disabled/dry-run.
- Meta business/app verification and preferred-thumbnail permission limits are not bypassed by a rebrand.

## Validation

Eight new branding tests cover identity/storage continuity, theme references and public copy, identical logo exports, adaptive/themed icons, future video/report text, exact Facebook-caption and cover separation, paused feed configuration and release safeguards. Existing rendering tests exercise both aspect ratios; original music, schedule, verification and insights hashes remain unchanged. Only the renderer/publisher display-branding pins were deliberately updated.

A mobile-width Chromium smoke test with read-only published fixture data verifies the new title/logo, Settings and Guide copy, retained settings and no page errors. Separate intro/disclaimer/closer layout renders verify both aspect ratios without producing or publishing a new video.
