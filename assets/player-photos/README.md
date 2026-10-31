# Reviewed real player photos — club jerseys only

Initial owner-requested pair, reviewed 31 October 2026:

- Evidence Makgopa — Orlando Pirates, black Pirates club jersey.
- Wandile Duba — Kaizer Chiefs, gold/black Chiefs club jersey.

Both images were visually checked against the official club player pages. No
national-team photos, AI faces, synthetic jerseys or simulated player cut-outs
are included. Only proportional resizing/PNG conversion was performed. The
Makgopa source already has transparency; Duba retains the original background.

`manifest.json` records the official identity page, actual source image URL,
original downloaded SHA-256, bundled PNG SHA-256, explicit club-kit check and
review dates. The images were obtained through image search referencing those
club sources; this is not an independently licensed photo feed. No watermark or
copyright notice was removed. A club portrait is a club visual, **not** a claim
that the player is starting, available, selected or endorsed by PLAYREPORT ZA.

## Rights are not established

The owner explicitly requested use of these public photos after being told
reuse permission was not established. **That request does not establish a
licence.** This repository does not claim copyright, permission, a commercial
licence, or that an official website grants republication rights. The rights
holder remains responsible for the photographs; the page operator is responsible
for having a lawful basis for publication and responding to rights requests.
Makgopa's source filename identifies Brandon Barnard Photography. Official
source pages and image URLs are provenance, not a licence certificate.

No required credit was intentionally removed from an image. No newly licensed
asset with an attribution requirement may be added while silently omitting its
required attribution. Disable/remove any asset if use is not permitted.

## Review and fail-safe behaviour

- Exactly one entry per country-qualified, registered club; no fuzzy match.
- `club_kit_verified` and `owner_requested_use` must both be true.
- Today's SAST date and the fixture date must both fall inside the documented
  review window (initially 31 October–30 November 2026). Club association must be
  checked again before extending this window; it is not automatically renewed.
- Missing, duplicate, expired, corrupt or unsafe files fall back to club crests.
- No image-search scraping, hotlinking, provider calls, extra quota consumption,
  paid subscriptions, or downloads occur while rendering or publishing.
- This is a two-player starting library, **not worldwide player-photo coverage**.
  A new club requires its own identity/kit/source review and asset entry.
