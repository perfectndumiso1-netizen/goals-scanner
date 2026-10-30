# Facebook Reels delivery — PlayReport ZA

Facebook receives **native 9:16 Reels only**, never the 16:9 Telegram/YouTube video and never an ordinary `/videos` post. Telegram keeps its existing videos, captions, dimensions and schedule. YouTube and Drive delivery remain unchanged.

## Configuration and rendering

The existing `FACEBOOK_PAGE_ACCESS_TOKEN` and numeric `FACEBOOK_PAGE_ID` Actions secrets are unchanged. The token needs permission to publish on PlayReport ZA; Meta's current app/Page access and review requirements still apply. No token is stored in source, receipts, artifacts, URLs or logs.

When Facebook is configured, the daily renderer creates an additional **1080×1920** portrait cut using the same filmed picks, evidence, music and readable timing as the 1920×1080 Telegram cut. It lays the slides out vertically rather than cropping the landscape picture. It does not add another scheduled edition or another Telegram post. If portrait rendering fails, Telegram still runs and the landscape source is retained for recovery; it is never substituted into Facebook.

The one-shot briefing workflow sends landscape sources to Telegram only and sends its `briefing-reel.mp4` / `breakdown-9x16.mp4` sources through the Reels publisher. If a configured Facebook delivery has only a landscape source and its portrait counterpart is missing, it logs a failure and retains that source rather than uploading landscape. The uploader inspects the actual video stream with ffprobe (or ffmpeg fallback), enforcing 9:16, square pixels, no rotation workaround, and at least 540×960. Unknown dimensions and landscape/square videos are rejected **before any Facebook API call**, regardless of the filename or caller's declared dimensions. Both workflows install ffmpeg.

## Native Reels publishing protocol

`facebook_post.py` uses the standard library and the versioned API (`v25.0`):

1. `POST https://graph.facebook.com/v25.0/{page-id}/video_reels`, `upload_phase=start`.
2. Validate the returned session ID and upload URL; stream the raw MP4 bytes to the returned **HTTPS rupload.facebook.com/video-upload/** URL with `offset=0`, `file_size` and `Authorization: OAuth ...`.
3. `POST` to the same `/video_reels` endpoint with `upload_phase=finish`, `video_id`, `video_state=PUBLISHED`, title and description.
4. Poll `GET /{video-id}?fields=status` until `publishing_phase.status=complete`. A finish acknowledgement alone is **not** treated as successful publication. Processing/publication rejection or a bounded polling timeout retains the video and its session receipt.

Graph control calls use a bearer authorization header. Redirects are rejected so credentials cannot be forwarded to another host. Transfers are streamed in 1 MiB chunks, not buffered as a whole video in RAM. Logs expose only numeric Graph error codes, never API response bodies or raw network exception messages.

The protocol follows Meta's [Reels Publishing API sample](https://github.com/fbsamples/reels_publishing_apis/tree/main/fb_reels_publishing_api_sample). Sample/API requirements can change. We do **not** shorten slides, speed up the music, remove required matches, or silently fall back to a normal video to satisfy media limits. Meta's current duration/format/account rules determine whether it accepts a particular Reel; rejected media is retained with a clear error. Reel format does not guarantee reach.

## Receipts, deletion and recovery

Token-free local receipts record the file SHA-256, Page ID, Reel ID, publication kind and phase. An old ordinary-video receipt cannot be reused as a Reel receipt. A confirmed published Reel is not uploaded again for the same file/Page on the same runner. An in-progress finish is resumed by polling its existing ID, not by creating a duplicate Reel. Ambiguous byte-transfer failures require checking the saved ID before retrying; there is no blind POST retry.

The source is deleted only after the relevant delivery succeeds. For a daily landscape/portrait pair, both files are removed after Telegram succeeds **and** the portrait Reel's publication is confirmed. If Facebook fails or is still pending, both stay local and the failed portrait is copied to `tmp/video-recovery/` (or `VIDEO_RECOVERY_DIR`), along with any token-free session receipt. Telegram is still attempted. Telegram failure keeps the files, as before. Generic landscape Telegram sends have no automatic Facebook upload; portrait sends can use the Reels publisher.

Both Actions workflows have `always()` recovery artifact steps. Open the affected run in GitHub Actions on your phone and download **`video-recovery-<run-id>-<attempt>`**, retained for **7 days** subject to GitHub storage availability. The one-shot workflow also saves undeleted original briefing/breakdown sources and reports failure after attempting Telegram when Facebook fails. The scheduled scanner logs an explicit error and continues its existing scan/Telegram/state-publication behavior. Artifacts/receipts contain no credentials and MP4 files are never committed to Git or the data branch.

Runner files are temporary; artifacts are the durable recovery mechanism after the job ends. If disk/storage, artifact upload, or the runner itself fails, recovery cannot be guaranteed. Recovery files are not automatically republished: inspect the Page and saved Reel ID first to avoid duplicates. A Telegram-successful edition may already be marked delivered even if its Facebook Reel failed; that recovery is manual rather than an automatic new post.

## Verification

`tests/test_facebook_post.py` covers the native start/raw-transfer/finish/status sequence, strict portrait gate, endpoint/host/auth safety, receipt type separation, pending/error handling, polling-only resumption, recovery copies, and all Facebook/Telegram cleanup combinations. It executes the one-shot workflow with mocked APIs to prove that only portrait sources reach Facebook. `tests/test_facebook_render_routing.py` checks the daily dual-format renderer and confirms portrait-render errors do not block Telegram.

Tests do not post a real Reel. The first live workflow must verify that the configured Page token permits Reels and the actual generated video's format/duration is accepted by Meta.

## Automatic recovery and one-picture test (30 October 2026)

The normal scan now sets `FACEBOOK_AUTOMATION=1`. It verifies the target Page identity,
resolves an authorised user credential into that Page's credential in memory when needed,
and attempts delivery in four bounded rounds with backoff. Processing/publishing delays
resume the saved Reel ID; an acknowledged transfer or ambiguous finish is never uploaded
again. An interrupted/ambiguous byte transfer is deliberately **not** blindly retried.
Permanent permission/credential rejections are not spammed with repeated POSTs. Credentials,
raw Graph responses and signed URLs are never stored in recovery metadata.

Unconfirmed deliveries retain the portrait MP4, native receipt, exact filmed-match JPEG,
thumbnail checkpoint and caption manifest in the existing seven-day recovery artifact.
Only small queue metadata goes to `data/facebook_delivery_queue.json`. Subsequent ordinary
scans resume one pending item, choosing the least-attempted item first, for at most eight
same-day recovery scans. Expired editions are not published the following day. A missing
or corrupt required session receipt blocks recovery rather than starting another Reel.
No recovery rerenders selections or resends Telegram/YouTube/Drive deliveries. Original
scan cron, two 08:00/16:00 SAST edition rules, music and other channels are unchanged.

Cover failure does not change a published Reel into a failed upload. Published receipt
resumption can apply/verify the matches-only cover later. A thumbnail mutation is
checkpointed before sending; an accepted/ambiguous request is followed by reads, not
blind repeated thumbnail uploads. Confirmation requires a newly preferred thumbnail ID,
not merely the old default thumbnail still being preferred. Meta permissions/support may
still prevent custom Reel thumbnails; API confirmation is not a visual inspection of
every Facebook surface/cache.

### Explicit one-picture exception — not a general feed restart

`Facebook ONE match picture and existing Reel cover` is a **manual, main-only** workflow,
with date/expiry and exact-match controls in `config/facebook-one-match-test.json`.
It prepares just one original 1080×1350 card using five available scored competitive
records per team from the fresh scanner publication, disclosing differing sample windows.
If evidence is insufficient/stale, it posts nothing; it never substitutes another match.
It saves evidence plus a durable reservation artifact **before** the photo POST. Reruns
cannot send another photo, even if a prior send's outcome was ambiguous. A returned ID is
saved immediately and read-back verification alone is retried. No narration, odds, match
selections, external photographs or club badges are used.

That same one-off can repair **only the cover** of already-posted Reel `1477189940972866`.
It requires the original receipt/hash and an unambiguous five-pick filmed history, then
checks the known Reel's publication status before touching its thumbnails. It has no
video upload route. The broader feed configuration remains disabled/dry-run/live-off.
The old retained-file retry must **not** be run to recreate this already-published video.

The prior owner retry's failure report showed transfer complete and Meta still processing,
not a confirmed rejection. The owner subsequently confirmed the Reel appeared. A verified
photo post ID / `is_published` proves API publication, **not** non-role visibility or reach.
Check from a non-admin/non-app-role Facebook account and inspect Page insights separately;
this code cannot bypass Development mode, business verification, app review or audience
restrictions. The GitHub integration previously returned workflow-dispatch HTTP 403; the
owner may need to click Run workflow once for this isolated test. Normal Reel recovery
uses the existing scheduled scans and requires no per-edition owner dispatch.
