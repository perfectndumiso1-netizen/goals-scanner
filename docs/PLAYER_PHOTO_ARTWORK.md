# Real club-kit photos and derby labels

Owner direction: use real internet-sourced player photos, in the **club** jersey,
not a national-team jersey, without making text hard to read. Source/reuse
uncertainty was disclosed; owner explicitly requested use of the two portraits.
See `assets/player-photos/README.md`: no permission/licence is claimed.

## Implemented scope

- Initial reviewed library: Evidence Makgopa (Orlando Pirates) and Wandile Duba
  (Kaizer Chiefs). Other clubs retain crests until their own portraits are reviewed.
- Stats comparison: portraits and player names only in reserved header space;
  club badges remain visible. All ten verified rows, kickoff, sample scope,
  quotas, captions, schedules and factual verification are unchanged.
- Portrait Facebook cover/opening: at most **one actual filmed matchup** gets a
  photo pair, only when both club portraits are reviewed and one to five filmed
  matches fit. Six to eight matches retain the existing spacious crest-only
  layout. Exact filmed names/order, price validation and combined-odds
  calculation are unchanged. Never add a derby/PSL matchup just for its artwork.
- Relevant video 'the pick' overview: portraits occupy the club-art area, with
  smaller club badges; no chart, price, selection, form or kickoff is covered.
  Both portrait and landscape overviews supported. No other video stages or
  timing/music/upload/recovery/thumbnail verification logic changed.
- Reviewed exact derby map: Soweto, Manchester, North London, Merseyside, Madrid,
  Milan and Rome. Symmetric home/away matching, country-qualified existing club
  aliases; unrecognised pairs get no derby label. El Clásico and Der Klassiker
  are not incorrectly labelled local derbies. Registry is deliberately finite.

Derby identity references: https://derby.ist/all and
https://lowerblock.com/articles/the-biggest-rivalries-in-world-football/

## Operational limits

The library is local, hash-pinned and size/path checked. Both the current SAST
review date and fixture date must be in the review window. Missing/corrupt,
expired, ambiguous, unapproved or non-club-kit entries omit photos, not posts.
Do not extend validity without checking current club association. Do not
substitute a national-team shirt, generated face or another player's photo.

No assumption that pictured players are confirmed starters. No additional
Highlightly/API requests or paid-photo purchases. No public source/assessment
footer restored. No change to editorial reservation/hash/expiry/history/unknown
blocks, post frequency, scanner models, Android, audio or Meta delivery guards.

Tests are fully offline. Preview cards use blank stats and explicit demo labels,
not fabricated match facts. Template tests and a successful merge do not verify
Meta's preferred thumbnail or Facebook visibility. No test post/reupload or edit
to the existing Pirates–Chiefs post is authorised by this change.
