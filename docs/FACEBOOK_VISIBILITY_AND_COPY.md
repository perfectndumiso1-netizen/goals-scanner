# Picture-first posts, public visibility and caption changes

## What changed

- Statistical community posts and honest prediction reviews now render original 1080×1350 pictures, like match cards and weekly features. The workflow installs the existing locked Pillow dependency for community editions too. A graphic failure skips the post instead of falling back to an unwanted text-only stats post.
- Community/card captions are shorter: an actual statistical observation, the match/time and one football question. Sample sizes, form, goals and date ranges remain on the picture; complete evidence is retained in the planning manifest. Weekly copy remains factual and includes the known forward fixtures.
- No `PlayReport ZA` banner or `Source:` credit appears in new feed captions or new stats pictures. Source/provenance remains internal. This does not override a supplier's mandatory attribution terms: any new provider requiring public attribution must remain disabled unless the publication arrangement permits this format. Scores/roundups remain disabled pending the existing coverage/rights checks.
- Facebook Reel captions remove the branded/technical `16:9 widescreen`, `selection(s)` boilerplate. They retain the actual pick count, date, morning record (including losses) and 18+ warning. Telegram text is passed through unchanged. Existing video visuals/logo, renderer, native Reel publisher, music, schedules, picks and deletion/error handling are not changed.
- These changes affect future editions. No old post is deleted, edited, reuploaded or duplicated, and no extra Reel is generated.

## Why an API success can still be invisible to other people

The old check established that the owning Page token could read the published post and expected message. **That does not establish public visibility.** The updated notice makes this distinction explicit. Text publication now explicitly sets `published=true`; photo publication already did so. Neither parameter can override Meta app mode or Page restrictions.

Meta's official [App Modes documentation](https://developers.facebook.com/docs/development/build-and-test/app-modes/) states that data generated in Development mode, including test posts, is visible only to role users. Switching to Live makes that data visible to non-role users. Meta also says to complete development/App Review requirements before switching modes. This is a likely explanation for an admin seeing a post that other people cannot see, **not a remotely verified diagnosis of this specific app**.

### Owner check on a phone

1. Open Meta for Developers → **My Apps → Daily Workflow** (the app used to obtain the publishing token).
2. Check **Development / Live** status in the dashboard (or its Publish section). Complete any required settings, permissions review or verification before making it Live. Repository code cannot switch the Meta dashboard for you.
3. Check the Page's age/country restrictions and whether the post is hidden. Test the **direct post link** from an ordinary Facebook account with no admin/developer/tester role. Seeing nothing in somebody's News Feed is not by itself evidence that the post is private; distribution is a separate issue.
4. Do not repost merely to test visibility. Meta documents that existing Development-mode data becomes accessible after the switch; first inspect the original post again.

### Read-only diagnostic workflow

After this PR is merged, Actions → **Check Facebook post visibility (read only)**. Supply the numeric suffix of the existing post, not a token. The default is the first confirmed community post, `122152496451000672`. The script combines it with the configured Page ID and uses GET only. It checks reported publication, hidden state, audience and publishing-app name, and saves a credential-free JSON report. It never edits privacy, creates another post or changes app mode.

Even `is_published=true` and audience `EVERYONE` are not sufficient to prove a non-role user can see a Development-mode post. Therefore the report always leaves `public_visibility_verified=false`; a real non-role viewer check is still required. Missing/unsupported Graph fields or permissions fail safely rather than invent a public result. The app mode itself is not inferred from this endpoint.

## Validation

Offline tests cover picture rendering (including losing reviews), removal of public branding/source boilerplate, retention of sample evidence, humanised video counts/records, unchanged Telegram/media delivery, explicit published text requests, read-only visibility diagnostics and non-public/unknown audience handling. Dry-run previews use actual published archive records and make no Facebook calls. A successful mock test is not a successful public photo-post or external-viewer integration test.
