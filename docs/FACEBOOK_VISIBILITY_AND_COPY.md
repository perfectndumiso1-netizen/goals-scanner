# Reels-only update — owner decision, 30 October 2026

> **Approved artwork update (31 October 2026):** portrait covers now include the exact filmed combined-odds total and registered club crests. See [approved football artwork](APPROVED_FOOTBALL_ARTWORK.md). Earlier matches-only/no-price descriptions below are historical; caption, upload, recovery and no-reupload protections remain.

## Pause other Facebook posts

The owner has deferred text/community posts, stats cards, weekly features, live scores and roundups while Meta requests business verification. `config/facebook-feed.json` is now `enabled:false`, `dry_run:true`, `live.enabled:false`. Their workflows can still produce dry-run reports, but cannot publish. This gate is independent of the existing two Reels. There is no new API subscription and no extra Reel/manual delivery trigger.

Business verification/app access restrictions may also affect API-published Reels. Repository changes cannot bypass Meta review or prove that a non-role viewer can see a Reel. See Meta's official [App Modes guide](https://developers.facebook.com/docs/development/build-and-test/app-modes/).

## Exact Facebook Reel caption

The Facebook-only adapter now emits exactly:

```
Today's Football Predictions
30 October 2026

#FootballPredictions #Football #Soccer #SoccerPredictions #FootballTips
```

The date is calculated at send time in **Africa/Johannesburg**, not hard-coded or taken from yesterday's recap. No brand, source, odds, selection count, recap, extra commentary or technical aspect-ratio wording is added. Telegram captions are untouched. The existing 18+ / responsible-gambling warning remains inside the videos.

### Hashtag research and honest limits

These are a compact set of broad and subject-specific football terms, not a claim of the five most-used Facebook tags. Public hashtag directories mainly expose **Instagram** counts and do not establish Facebook search volume. The researched football-related lists include these terms [1](https://best-hashtags.com/hashtag/soccerpredictions/); they are used here for relevance, not as proof of reach. No paid hashtag service, follower manipulation, unrelated trending tag, `#surebet` or guaranteed-win tag is used.

Meta cautions against long distracting captions and excessive hashtags, which can reduce distribution [1](https://about.fb.com/news/2025/04/cracking-down-spammy-content-facebook/). Five relevant tags fit the owner's short caption request; no hashtag can guarantee views or search placement. Meta's [Reels publishing guide](https://developers.facebook.com/docs/video-api/guides/reels-publishing/) explicitly supports hashtags in `description`.

## Matches-only cover and opening frame

- After the renderer's final verification/filtering, the **exact same filmed picks**, in the same order, generate an original 1080×1920 JPEG named `<video>.cover.jpg`.
- The cover reads only team names. Selection, odds, price, model probability and reason fields are never read by the cover renderer. Every filmed match appears; duplicates, blank names, more than eight matches or unreadable overflow fail closed.
- For the Facebook portrait cut, that JPEG replaces the existing intro picture **without adding a slide or changing its hold time**. Telegram's landscape intro, all match/reason/record slides, pick logic, music and the two delivery slots remain unchanged.
- After the native Reel is confirmed published, the publisher makes one best-effort preferred-thumbnail request on the existing video ID. Meta's [Video Thumbnails reference](https://developers.facebook.com/docs/graph-api/reference/video/thumbnails/) documents multipart `source` and `is_preferred=true` plus additional permission requirements.
- A cover is reported verified only when the upload succeeds and a **new** preferred thumbnail ID is read back. Not every Page/app/Reel permission combination is established to support this endpoint. Rejection/timeout is logged as **unconfirmed**, not hidden or treated as successful.
- Cover failure never turns a published Reel into a failed video delivery and never creates/reuploads another Reel. The matches-only opening frame is still embedded in the video; Facebook may choose or crop thumbnails differently across surfaces. Without successful thumbnail read-back, the actual UI cover cannot be promised.
- No old Reel is rerendered or reuploaded. These settings are for the next normal edition, not an extra test video.

## Tests

Tests cover exact caption/date rollover; whitelisted cover text against poisoned market/odds fields; one-to-eight match bounds and duplicate rejection; real JPEG rendering; header-only token authentication; preferred-thumbnail read-back; ambiguous cover failures; already-published Reel idempotency; unchanged Telegram/media; paused non-Reel gates; unchanged calendar and locked music. Renderer/publisher invariant hashes were updated only for the explicitly requested cover feature; original calendar/music hashes remain fixed. Offline contracts and a layout preview are not a real Facebook thumbnail integration success.
