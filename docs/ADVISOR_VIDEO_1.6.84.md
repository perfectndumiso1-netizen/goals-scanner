# Bet Advisor editions and performance — 1.6.84

## Video contract

Two slots, 08:00 and 16:00 Africa/Johannesburg (UTC+2, no DST). The half-hour scanner may deliver late due to GitHub cron delays and processing; it does not promise second-accurate delivery. The window is that hour, and a successful slot is never repeated, even with manual force. One landscape video per edition; legacy breakdown publishing is disabled. Drive/Zapier remains the preferred delivery lane; direct posting remains a fallback. A successful delivery on any lane records the edition, preventing duplicate publication on later scans.

The candidate universe is exactly the visible Bet Advisor sections: daily recommendations (six per section), the first five edges, the first five strong signals, and the first five today's high-confidence selections. No shortlist-only or invented alternative markets are added. Deduplicate the same match/market; preserve distinct published markets as alternatives until card composition. One selection per club pair in a card, never a club pair already filmed today. Kickoff must be in the future.

Try O15 and C[HA]?O<number> first. Only if no qualifying card exists consider published O25 lines. Keep the Advisor quality floors (O25 >=55%, others >=65%), odds >=1.16. Missing/nonfinite prices and probabilities are excluded. Gate recent results for both teams, recent H2H, and the existing internet fixture/contradiction search. A headline search does **not** independently establish every numerical statistic; unverified coverage is reported rather than claimed confirmed. Corner picks additionally need >=5 recorded corner samples per club and usable expectations.

A deterministic bounded price-frontier search composes 5–8 fixtures with product 2.00–3.30, closest to 2.50; model probability breaks price ties, then total corners over team corners. It never rewrites probabilities to achieve a price. A 0.001 price bucket bounds search cost; this is not an exhaustive mathematical optimizer. If infeasible, log the failure and skip: no short video, no filler or guessed prices. Never trim selections after composition to fit duration. Preserve readable three-stage slides and the supplied music, without narration. The last screen multiplies the exact filmed decimal prices and warns all legs must win.

## Performance

`data/advisor_ledger.json` on the existing state/data publication is forward-only, beginning with the first accepted publication under this version. Capture exactly the visible Advisor selections before kickoff, unique by date/country/home/away/market. Freeze first price and probability. Do not backfill historical winners, silently replace losing selections, or count repeated appearances as new bets. Only persist candidate ledger updates after publication is accepted.

Grade using the established goals/corner settlement logic against the exact fixture date. Missing statistics stay pending (the existing 21-day unresolved policy eventually voids them). Hit rate = wins / (wins + losses). Profit = sum(odds − 1 on wins, −1 on losses); ROI = profit / settled stakes. Pending and void rows are excluded. Display the aggregate, per-market sample sizes/record, and recent selections. These are 1-unit singles, **not** combined-card returns. Video history now preserves exact selected markets/prices/kickoff; morning recap reads their settled ledger entries, not unrelated shortlist results.

## Android distribution

Release name 1.6.84, run-number version code must increase. Existing signing key is mandatory. Sign v1/v2/v3; verify ZIP, zipalign, apksigner for API26+, package/version, certificate continuity with latest release, then install previous APK and upgrade in an Android 15 emulator. Publish a versioned APK plus SHA256 only after checks succeed. This proves package/upgrade validity on the test device, not compatibility with every phone. Root cause of the reported phone error remains unconfirmed until exact device/error information or successful installation is available.

## Verification

Run `python -m pytest leagues/tests tests tennis/tests -q`. `tests/test_advisor_video.py` covers planner bounds, fallback, dedupe, slots, forward-only tracking, frozen prices, settlement, missing corner results and release safeguards. Rendering smoke test exercised the real ffmpeg rotation graph at 1920×1080. Android installation is verified by GitHub Actions, not asserted from local Python tests.
