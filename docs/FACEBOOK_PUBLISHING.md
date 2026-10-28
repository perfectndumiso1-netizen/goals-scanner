# Facebook Page delivery — PlayReport ZA

The existing scanner and one-shot briefing workflow now publish their MP4 videos directly to the Facebook Page **before** the Telegram sender can delete them. Existing Telegram captions, dimensions, scheduling, streaming settings and its boolean success result are preserved. YouTube and Drive delivery are unchanged.

## Configuration

Both workflows pass these existing GitHub Actions secrets as environment variables:

- `FACEBOOK_PAGE_ACCESS_TOKEN` — a Page access token with permission to publish videos/posts to the intended Page (including `pages_manage_posts`). The token must be valid and belong to the configured Page; Meta may require additional permissions, app review or Page access.
- `FACEBOOK_PAGE_ID` — the numeric ID of PlayReport ZA.

No token is stored in code, receipt files or recovery artifacts. The uploader uses a bearer header over HTTPS, not a token in a URL. Redirects are rejected to avoid forwarding credentials to another host. Logs contain only numeric Graph error codes, never API response bodies or raw network exception messages.

No new Python dependencies are required. `facebook_post.py` uses the standard library to stream a known-length multipart upload to the versioned Graph Video endpoint `https://graph-video.facebook.com/v25.0/{page-id}/videos`, with `published=true`, the caption as the description, and its first line as the title. The file is streamed in 1 MiB chunks rather than loaded into RAM. A returned video ID means Facebook accepted the upload; processing and visibility on Facebook can take longer.

## Delivery and deletion rules

1. Attempt Facebook publication first.
2. Regardless of Facebook failure, attempt the existing Telegram send.
3. Delete the source only when Telegram succeeds, `delete_after` is enabled, and Facebook succeeded (or neither Facebook secret is configured).
4. A partial Facebook configuration is an error: retain the video, but still send to Telegram.
5. Telegram failure also keeps the source, as before.

Successful uploads write a token-free SHA-256/Page/video-ID receipt next to the source. An identical file/Page is not uploaded again on the same runner; a different file or Page cannot reuse that receipt. Facebook-only success counts as a delivered daily slot, so missing/failed Telegram does not cause repeat Facebook posts on later scans. Existing daily slot state remains on the normal data branch.

There is no blind POST retry: a network timeout can happen after Facebook has accepted an upload. Check the Page before retrying an ambiguous failure. Recovery files are not automatically republished. When Telegram succeeds but Facebook fails, the daily slot can still be marked delivered by the existing delivery logic; the retained file/artifact is for manual recovery, not a promise of an automatic Facebook retry.

## Recovery from a phone

A failed Facebook upload leaves its original video untouched and also copies it into `tmp/video-recovery/` (or `VIDEO_RECOVERY_DIR`). Copies use a content-based filename to avoid the next scheduled render overwriting the failed video. No MP4 is committed to Git or the data branch.

Both Actions workflows have an `always()` artifact step. Open the failed/affected run in GitHub Actions and download **`video-recovery-<run-id>-<attempt>`**. Artifacts are retained for **7 days**, subject to GitHub storage availability. The one-shot workflow also saves any undeleted original briefing/breakdown files and exits with failure after attempting Telegram if Facebook failed. The scheduled scanner logs an explicit Facebook error but continues its existing scan/Telegram/state-publishing behavior.

Runner files are temporary: the artifact is the durable recovery mechanism after a job ends. If disk/storage or artifact upload itself fails, the error must be investigated before the runner disappears. Neither token values nor credentials are needed in chat to diagnose an expired token or permission issue.

## Verification

`tests/test_facebook_post.py` exercises streamed multipart requests, bearer-only authentication, redirect rejection, valid/invalid responses, expired-token error codes, log redaction, no automatic retry, receipts, recovery copies, and all Facebook/Telegram success/failure deletion combinations. It also executes the existing one-shot workflow's inline Python with mocked APIs to prove a Facebook failure does not stop Telegram or delete the file.

Tests do not post a real video. A live Page upload must be verified from the next workflow run and the returned Facebook video ID/Page; configured repository secrets are not read or exposed by local tests.
